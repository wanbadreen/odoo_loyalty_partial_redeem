from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    gdex_api_token = fields.Char(
        string="GDEX API Token",
        config_parameter="delivery_gdex.api_token",
        help="Paste the ApiToken provided by GDEX (Sandbox or Production).",
    )
    gdex_account_no = fields.Char(
        string="GDEX Account No.",
        config_parameter="delivery_gdex.account_no",
        help="Your myGDEX account number.",
    )
    gdex_use_sandbox = fields.Boolean(
        string="Use GDEX Sandbox",
        default=True,
        config_parameter="delivery_gdex.use_sandbox",
        help="If enabled, calls will go to the demo (sandbox) environment.",
    )
    gdex_subscription_key = fields.Char(
        string="GDEX Subscription Key",
        config_parameter="delivery_gdex.subscription_key",
        help="Ocp-Apim-Subscription-Key from GDEX API portal (Testing / Live).",
    )
