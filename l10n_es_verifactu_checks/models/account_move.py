from odoo import _, fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _verifactu_missing_info_messages(self):
        self.ensure_one()
        messages = []
        partner = self.partner_id
        if not partner.country_id:
            messages.append(
                _("El partner no tiene pais asignado.")
            )
        simplified = bool(getattr(partner, "aeat_simplified_invoice", False))
        if not simplified and not partner.vat:
            messages.append(
                _("El partner no tiene NIF asignado.")
            )
        if messages:
            messages.append(
                _("Advertencia: esta factura sera rechazada en Verifactu y deberá ser subsanada.")
            )
        return messages

    def action_post(self):
        for move in self:
            if (
                move.is_invoice(include_receipts=True)
                and not self.env.context.get("skip_verifactu_checks")
            ):
                if move.date != fields.Date.today():
                    move.date = fields.Date.today()
                messages = move._verifactu_missing_info_messages()
                if messages:
                    view = self.env.ref(
                        "l10n_es_verifactu_checks.post_warning_wizard_view_form"
                    )
                    return {
                        "type": "ir.actions.act_window",
                        "name": _("Confirmar igualmente"),
                        "res_model": "l10n_es_verifactu_checks.post_warning",
                        "view_mode": "form",
                        "views": [(view.id, "form")],
                        "target": "new",
                        "context": {
                            "default_move_id": move.id,
                            "default_message": "\n".join(messages),
                        },
                    }
        return super().action_post()
