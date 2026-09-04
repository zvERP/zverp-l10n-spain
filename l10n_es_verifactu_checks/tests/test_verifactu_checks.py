from copy import deepcopy
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.l10n_es_verifactu_oca.tests.common import TestVerifactuCommon


@tagged("post_install", "-at_install")
class TestVerifactuChecks(TestVerifactuCommon):
    def _get_warning_wizard(self, move=None):
        move = move or self.invoice
        action = move.action_post()
        self.assertEqual(action["res_model"], "l10n_es_verifactu_checks.post_warning")
        wizard = (
            self.env[action["res_model"]].with_context(**action["context"]).create({})
        )
        return wizard

    def test_missing_country_opens_warning_without_changing_invoice(self):
        original_date = self.invoice.date
        self.partner.country_id = False
        wizard = self._get_warning_wizard()
        self.assertEqual(self.invoice.state, "draft")
        self.assertIn("país", wizard.message)
        self.assertEqual(
            self.invoice.date,
            original_date,
            "A validation must never change the accounting date silently.",
        )

    def test_editable_warnings_do_not_depend_on_parent_post_hook(self):
        self.partner.vat = False
        with patch.object(
            type(self.invoice),
            "_post",
            side_effect=AssertionError("The posting hook must not be reached"),
        ):
            wizard = self._get_warning_wizard()
        self.assertIn("identificación fiscal", wizard.message)
        self.assertEqual(self.invoice.state, "draft")

    def test_literal_nif_prefix_opens_actionable_warning(self):
        self.partner.with_context(no_vat_validation=True).write({"vat": "NIF47375017P"})
        wizard = self._get_warning_wizard()
        self.assertIn("NIF español del destinatario", wizard.message)
        self.assertIn("NIF47375017P", wizard.message)
        self.assertEqual(self.invoice.state, "draft")

    def test_invalid_nif_control_character_opens_warning(self):
        self.partner.with_context(no_vat_validation=True).write({"vat": "47375017Q"})
        wizard = self._get_warning_wizard()
        self.assertIn("carácter de control", wizard.message)
        self.assertIn("47375017Q", wizard.message)
        self.assertEqual(self.invoice.state, "draft")

    def test_future_invoice_date_opens_warning_without_changing_dates(self):
        future_date = fields.Date.add(fields.Date.context_today(self.invoice), days=1)
        self.invoice.invoice_date = future_date
        original_accounting_date = self.invoice.date
        wizard = self._get_warning_wizard()
        self.assertIn("fecha de factura", wizard.message)
        self.assertIn("futura", wizard.message)
        self.assertEqual(self.invoice.state, "draft")
        self.assertEqual(self.invoice.invoice_date, future_date)
        self.assertEqual(self.invoice.date, original_accounting_date)

    def test_user_can_consciously_emit_and_decision_is_audited(self):
        self.partner.vat = False
        wizard = self._get_warning_wizard()
        self.assertIn("identificación fiscal", wizard.message)
        wizard.action_confirm()
        self.assertEqual(self.invoice.state, "posted")
        self.assertTrue(
            any(
                "se emitió conscientemente" in (body or "")
                for body in self.invoice.message_ids.mapped("body")
            )
        )

    def test_xsd_error_uses_same_warning_and_can_be_overridden(self):
        self.verifactu_developer.sif_name = "X" * 31
        wizard = self._get_warning_wizard()
        self.assertEqual(self.invoice.state, "draft")
        self.assertIn("VERI*FACTU", wizard.message)
        self.assertIn("NombreSistemaInformatico", wizard.message)
        self.assertIn("maxLength", wizard.message)
        wizard.action_confirm()
        self.assertEqual(self.invoice.state, "posted")

    def test_batch_validation_uses_same_warning_wizard(self):
        second_invoice = self.invoice.copy({"invoice_date": self.invoice.invoice_date})
        invoices = self.invoice | second_invoice
        self.verifactu_developer.sif_name = "X" * 31
        validate_wizard = (
            self.env["validate.account.move"]
            .with_context(active_model="account.move", active_ids=invoices.ids)
            .create({"force_post": True})
        )

        action = validate_wizard.validate_move()

        self.assertEqual(action["res_model"], "l10n_es_verifactu_checks.post_warning")
        self.assertEqual(invoices.mapped("state"), ["draft", "draft"])
        warning = (
            self.env[action["res_model"]].with_context(**action["context"]).create({})
        )
        self.assertIn("NombreSistemaInformatico", warning.message)
        warning.action_confirm()
        self.assertEqual(invoices.mapped("state"), ["posted", "posted"])

    def test_unrelated_user_error_cannot_be_overridden(self):
        with patch.object(
            type(self.invoice), "_post", side_effect=UserError("Accounting error")
        ), self.assertRaisesRegex(UserError, "Accounting error"):
            self.invoice.action_post()

    def test_simplified_invoice_does_not_require_receiver(self):
        self.partner.aeat_simplified_invoice = True
        self.partner.country_id = False
        self.partner.vat = False
        self.invoice.action_post()
        self.assertEqual(self.invoice.state, "posted")

    def test_invalid_company_nif_opens_warning(self):
        self.company.partner_id.with_context(no_vat_validation=True).write(
            {"vat": "G87846953"}
        )
        wizard = self._get_warning_wizard()
        self.assertIn("NIF de la compañía emisora", wizard.message)
        self.assertIn("G87846953", wizard.message)
        self.assertEqual(self.invoice.state, "draft")

    def test_invalid_developer_nif_opens_warning(self):
        self.verifactu_developer.vat = "A12345675"
        wizard = self._get_warning_wizard()
        self.assertIn("NIF del desarrollador", wizard.message)
        self.assertIn("A12345675", wizard.message)
        self.assertEqual(self.invoice.state, "draft")

    def test_long_receiver_and_description_are_normalised(self):
        self.partner.name = "R" * 130
        self.invoice.verifactu_description = "D" * 510
        self.invoice.action_post()
        payload = self.invoice._get_verifactu_invoice_dict()["RegistroAlta"]
        receiver = payload["Destinatarios"]["IDDestinatario"]
        self.assertEqual(len(receiver["NombreRazon"]), 120)
        self.assertEqual(len(payload["DescripcionOperacion"]), 500)

    def test_developer_uses_only_one_identifier(self):
        developer = self.invoice._get_verifactu_developer_dict()
        self.assertTrue(developer["NIF"])
        self.assertNotIn("IDOtro", developer)

    def test_empty_tax_breakdown_is_rejected(self):
        self.invoice.action_post()
        payload = deepcopy(self.invoice._get_verifactu_invoice_dict())
        payload["RegistroAlta"]["Desglose"]["DetalleDesglose"] = []
        error = self.invoice._validate_verifactu_registro(payload)
        self.assertIn("DetalleDesglose", error)

    def test_empty_rectified_invoice_wrapper_is_rejected(self):
        self.invoice.action_post()
        payload = deepcopy(self.invoice._get_verifactu_invoice_dict())
        payload["RegistroAlta"]["FacturasRectificadas"] = []
        error = self.invoice._validate_verifactu_registro(payload)
        self.assertIn("FacturasRectificadas", error)

    def test_official_schema_is_loaded_from_this_addon(self):
        tree = self.invoice._get_verifactu_schema_tree()
        self.assertEqual(tree.getroot().tag.split("}")[-1], "schema")
