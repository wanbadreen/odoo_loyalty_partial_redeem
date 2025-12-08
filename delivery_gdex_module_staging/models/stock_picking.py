import json
import logging
import requests

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = "stock.picking"

    gdex_cn = fields.Char(string="GDEX CN", copy=False, readonly=True)

    def _gdex_get_base_url(self):
        """Return sandbox or production base URL based on config."""
        ICP = self.env["ir.config_parameter"].sudo()
        use_sandbox = ICP.get_param("delivery_gdex.use_sandbox", "True") in ("1", "True", "true")
        if use_sandbox:
            return "https://myopenapi.gdexpress.com/api/demo/prime"
        return "https://myopenapi.gdexpress.com/api/prime"

    def _gdex_get_credentials(self):
        """Read API token, account no and subscription key from System Parameters."""
        ICP = self.env["ir.config_parameter"].sudo()
        token = ICP.get_param("delivery_gdex.api_token") or ""
        acct = ICP.get_param("delivery_gdex.account_no") or ""
        sub_key = ICP.get_param("delivery_gdex.subscription_key") or ""
        if not token or not acct or not sub_key:
            raise UserError(_(
                "Please configure GDEX API Token, Account No. and Subscription Key "
                "in System Parameters (delivery_gdex.api_token, "
                "delivery_gdex.account_no, delivery_gdex.subscription_key)."
            ))
        return token, acct, sub_key

    def _gdex_build_payload_for_receivers(self):
        """Build minimal payload from the picking to the GDEX 'ShipmentReceiversArray'."""
        self.ensure_one()
        partner = self.partner_id  # delivery address

        # Require mobile number (your system uses mobile)
        phone = partner.mobile
        if not phone:
            raise UserError(_("Receiver mobile number is required for GDEX. Please fill Customer Mobile."))

        if not (partner.zip and partner.city):
            raise UserError(_("Receiver must have City and Postcode (ZIP)."))

        # Weight: use picking.weight, fallback to 1kg
        weight = self.weight or 1.0
        try:
            weight = float(weight)
        except Exception:
            weight = 1.0

        receiver_mobile = phone
        receiver_email = partner.email or "no-reply@example.com"
        company_name = self.company_id.name or "Company"

        addr1 = partner.street or ""
        addr2 = partner.street2 or ""
        addr3 = partner.city or ""
        postcode = partner.zip or ""
        state = partner.state_id and partner.state_id.name or ""
        country = partner.country_id and partner.country_id.code or "MY"

        shipment = {
            "shipmentType": "Parcel",
            "totalPiece": 1,
            "shipmentContent": "Goods",
            "shipmentValue": 0,
            "shipmentWeight": max(1, round(weight)),
            "shipmentLength": 20,
            "shipmentWidth": 15,
            "shipmentHeight": 10,
            "isDangerousGoods": False,
            "companyName": company_name,
            "receiverName": partner.name or "Receiver",
            "receiverMobile": receiver_mobile,
            "receiverEmail": receiver_email,
            "receiverAddress1": addr1[:50],
            "receiverAddress2": addr2[:50],
            "receiverAddress3": addr3[:50],
            "receiverPostcode": postcode,
            "receiverCity": partner.city or "",
            "receiverState": state,
            "receiverCountry": country,
        }
        return [shipment]

    def action_gdex_create(self):
        """Create consignment on GDEX and save CN back to picking."""
        for picking in self:
            if picking.picking_type_code != "outgoing":
                raise UserError(_("GDEX consignment can only be created for outgoing deliveries."))

            if picking.gdex_cn:
                raise UserError(_("A GDEX consignment already exists for this delivery: %s") % picking.gdex_cn)

            token, account_no, sub_key = picking._gdex_get_credentials()
            base = picking._gdex_get_base_url()
            url = f"{base}/CreateConsignment?accountNo={account_no}"

            headers = {
                "ApiToken": token,
                "Content-Type": "application/json",
                "Ocp-Apim-Subscription-Key": sub_key,
            }
            payload = {
                "ShipmentReceiversArray": picking._gdex_build_payload_for_receivers()
            }

            _logger.info("GDEX POST %s payload=%s", url, payload)
            try:
                resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
            except Exception as e:
                _logger.exception("GDEX call failed")
                raise UserError(_("Failed to contact GDEX: %s") % e)

            if resp.status_code != 200:
                raise UserError(_("GDEX returned HTTP %s: %s") % (resp.status_code, resp.text))

            try:
                data = resp.json()
            except Exception:
                raise UserError(_("GDEX response is not JSON: %s") % resp.text)

            cn = None
            if isinstance(data, dict):
                # Adapt these keys once you see the real GDEX response for your account
                if "data" in data and isinstance(data["data"], list) and data["data"]:
                    first = data["data"][0]
                    cn = first.get("cn") or first.get("CN") or first.get("cnNo") or first.get("consignmentNo")
                if not cn:
                    cn = (
                        data.get("cn")
                        or data.get("CN")
                        or data.get("cnNo")
                        or data.get("consignmentNo")
                    )

            if not cn:
                _logger.warning("Unexpected GDEX response: %s", data)
                raise UserError(_("Could not find CN in GDEX response. Please check logs."))

            picking.write({"gdex_cn": cn})
            picking.message_post(body=_("GDEX consignment created: %s") % cn)
        return True
