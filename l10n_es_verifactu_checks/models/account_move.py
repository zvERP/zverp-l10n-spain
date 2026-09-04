from textwrap import indent

from odoo import _, fields, models
from odoo.exceptions import UserError


class VerifactuValidationError(UserError):
    """An invalid payload which the user may consciously choose to emit."""


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_verifactu_description(self):
        """Normalise a value whose limit is fixed by the AEAT schema."""
        description = super()._get_verifactu_description()
        return description and description[:500]

    def _get_verifactu_receiver_dict(self):
        """The schema accepts at most 120 characters for the receiver name."""
        receiver = super()._get_verifactu_receiver_dict()
        receiver_data = receiver.get("IDDestinatario", {})
        if receiver_data.get("NombreRazon"):
            receiver_data["NombreRazon"] = receiver_data["NombreRazon"][:120]
        return receiver

    def _get_verifactu_tax_dict(self, tax_line, tax_lines, operation_type):
        """Odoo stores four decimals, while VERI*FACTU accepts only two."""
        tax_dict = super()._get_verifactu_tax_dict(tax_line, tax_lines, operation_type)
        for key in ("TipoImpositivo", "TipoRecargoEquivalencia"):
            if key in tax_dict:
                tax_dict[key] = str(round(float(tax_dict[key]), 2))
        return tax_dict

    def _get_verifactu_developer_dict(self):
        """NIF and IDOtro are mutually exclusive in SistemaInformatico."""
        developer = super()._get_verifactu_developer_dict()
        if developer.get("NIF"):
            developer.pop("IDOtro", None)
        return developer

    def _verifactu_checks_apply(self):
        self.ensure_one()
        return (
            not self.env.context.get("skip_verifactu_checks")
            and self.verifactu_enabled
            and self.move_type in ("out_invoice", "out_refund")
        )

    def _is_valid_spanish_vat(self, vat):
        """Validate a Spanish NIF, including its control character."""
        return bool(vat) and self.env["res.partner"].simple_vat_check("es", vat)

    def _verifactu_missing_info_messages(self):
        """Return data errors that can be detected before assigning a number."""
        self.ensure_one()
        if not self._verifactu_checks_apply():
            return []
        messages = []
        partner = self._aeat_get_partner()
        simplified = self._get_verifactu_document_type() in ("F2", "R5")
        if not self.invoice_date:
            messages.append(_("La factura no tiene fecha de factura."))
        elif self.invoice_date > fields.Date.context_today(self):
            messages.append(
                _(
                    "La fecha de factura (%(invoice_date)s) es futura. La AEAT "
                    "rechazará el registro VERI*FACTU.",
                    invoice_date=fields.Date.to_string(self.invoice_date),
                )
            )
        if not simplified:
            if not partner.name:
                messages.append(_("El destinatario no tiene nombre o razón social."))
            if not partner.country_id:
                messages.append(_("El destinatario no tiene país asignado."))
            if not partner.vat:
                messages.append(_("El destinatario no tiene identificación fiscal."))
            else:
                country_code, identifier_type, identifier = (
                    partner._parse_aeat_vat_info()
                )
                if (
                    country_code == "ES"
                    and not identifier_type
                    and not self._is_valid_spanish_vat(identifier)
                ):
                    messages.append(
                        _(
                            "El NIF español del destinatario «%(vat)s» no es "
                            "válido. Compruebe su formato y el carácter de control.",
                            vat=identifier or partner.vat,
                        )
                    )

        company_partner = self.company_id.partner_id
        company_vat = company_partner._parse_aeat_vat_info()[2]
        if not self._is_valid_spanish_vat(company_vat):
            messages.append(
                _(
                    "El NIF de la compañía emisora «%(vat)s» no es válido. "
                    "Compruebe su formato y el carácter de control.",
                    vat=company_vat or company_partner.vat or "-",
                )
            )

        developer = self.company_id.verifactu_developer_id
        if developer and not self._is_valid_spanish_vat(developer.vat):
            messages.append(
                _(
                    "El NIF del desarrollador VERI*FACTU «%(vat)s» no es válido. "
                    "Compruebe su formato y el carácter de control.",
                    vat=developer.vat,
                )
            )
        return messages

    def _verifactu_payload_errors(self):
        """Build and validate the exact record generated during posting."""
        self.ensure_one()
        try:
            payload = self._get_verifactu_invoice_dict()
        except UserError as error:
            return [str(error)]
        schema_error = self._validate_verifactu_registro(payload)
        return [schema_error] if schema_error else []

    def _raise_verifactu_errors(self, errors_by_move):
        if not errors_by_move:
            return
        details = []
        for move, errors in errors_by_move:
            unique_errors = list(dict.fromkeys(error for error in errors if error))
            details.append(
                "%s:\n%s"
                % (move.display_name, indent("\n".join(unique_errors), "    "))
            )
        raise VerifactuValidationError(
            _(
                "Las siguientes facturas tienen advertencias que pueden provocar "
                "el rechazo de su registro VERI*FACTU:\n\n%(details)s",
                details="\n\n".join(details),
            )
        )

    def _verifactu_preflight_errors(self):
        """Collect editable-data problems before any posting hook is entered."""
        errors_by_move = []
        for move in self:
            if move._verifactu_checks_apply():
                errors = move._verifactu_missing_info_messages()
                if errors:
                    errors_by_move.append((move, errors))
        return errors_by_move

    def _post(self, soft=True):
        """Validate after OCA has generated number, hash and chain data."""
        posted = super()._post(soft=soft)
        payload_errors = []
        for move in posted:
            if move._verifactu_checks_apply() and move.aeat_state == "not_sent":
                errors = move._verifactu_payload_errors()
                if errors:
                    payload_errors.append((move, errors))
        self._raise_verifactu_errors(payload_errors)
        return posted

    def _open_verifactu_warning(self, error):
        view = self.env.ref("l10n_es_verifactu_checks.post_warning_wizard_view_form")
        return {
            "type": "ir.actions.act_window",
            "name": _("Emitir con advertencias VERI*FACTU"),
            "res_model": "l10n_es_verifactu_checks.post_warning",
            "view_mode": "form",
            "views": [(view.id, "form")],
            "target": "new",
            "context": {
                "default_move_ids": [(6, 0, self.ids)],
                "default_message": str(error),
            },
        }

    def action_post(self):
        """Offer an explicit override only for VERI*FACTU validation errors."""
        if self.env.context.get("skip_verifactu_checks"):
            return super().action_post()
        try:
            self._raise_verifactu_errors(self._verifactu_preflight_errors())
            with self.env.cr.savepoint():
                return super().action_post()
        except VerifactuValidationError as error:
            return self._open_verifactu_warning(error)
