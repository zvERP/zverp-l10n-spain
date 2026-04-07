from odoo import _, fields, models


class L10nEsVerifactuPostWarning(models.TransientModel):
    _name = "l10n_es_verifactu_checks.post_warning"
    _description = "Verifactu post warning"

    move_id = fields.Many2one(
        comodel_name="account.move",
        string="Factura",
        required=True,
        ondelete="cascade",
    )
    message = fields.Text(string="Aviso", readonly=True)

    def action_confirm(self):
        self.ensure_one()
        return self.move_id.with_context(skip_verifactu_checks=True).action_post()

    def action_cancel(self):
        return {"type": "ir.actions.act_window_close"}
