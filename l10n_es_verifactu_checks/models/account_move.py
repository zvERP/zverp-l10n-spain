from odoo import _, models
from odoo.exceptions import UserError


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        for move in self:
            if move.is_invoice(include_receipts=True) and not move.partner_id.country_id:
                raise UserError(
                    _("No puedes confirmar una factura si el partner no tiene pais asignado.")
                )
        return super().action_post()
