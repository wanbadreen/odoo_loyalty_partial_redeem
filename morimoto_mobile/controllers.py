import base64
import hashlib
import json
from odoo import http
from odoo.http import request
from werkzeug.exceptions import BadRequest, Forbidden, Conflict
from .contract import validate_cart, quotation_payload
from .customer_contract import customer_request_key
from .customer_controllers import current_account

STAGING_HOST = 'percyianodoo-morimotoformulas-staging-37481016.dev.odoo.com'

class Mobile(http.Controller):
    def _context(self):
        # Mandatory explicit bearer header; do not accept session-cookie fallback.
        if not request.httprequest.headers.get('Authorization', '').startswith('Bearer '):
            raise Forbidden()
        params = request.env['ir.config_parameter'].sudo()
        if (params.get_param('morimoto_mobile.enabled') != 'staging'
                or request.httprequest.host.split(':')[0] != STAGING_HOST
                or params.get_param('morimoto_mobile.database') != request.env.cr.dbname
                or not request.env.user.has_group('morimoto_mobile.group_mobile_api')):
            raise Forbidden()
        try:
            partner_id = int(params.get_param('morimoto_mobile.test_partner_id', '0'))
            company_id = int(params.get_param('morimoto_mobile.company_id', '0'))
        except ValueError:
            raise Forbidden()
        company = request.env['res.company'].browse(company_id).exists()
        if not company or company not in request.env.user.company_ids:
            raise Forbidden()
        env = request.env(context=dict(request.env.context, allowed_company_ids=[company.id]))
        if request.httprequest.headers.get('X-Morimoto-Customer-Session'):
            partner_id = current_account().partner_id.id
        partner = env['res.partner'].browse(partner_id).exists()
        if not partner or not partner.active or (partner.company_id and partner.company_id != company):
            raise Forbidden()
        pricelist = partner.property_product_pricelist
        if not pricelist or not pricelist.active or (pricelist.company_id and pricelist.company_id != company):
            raise Forbidden()
        return env, partner, company

    def _domain(self, company):
        return [('morimoto_mobile_enabled', '=', True), ('sale_ok', '=', True), ('active', '=', True), ('company_id', 'in', [False, company.id])]

    @http.route('/morimoto/mobile/products', type='http', auth='bearer', methods=['GET'], csrf=False)
    def products(self):
        env, partner, company = self._context()
        pricelist = partner.property_product_pricelist
        products = env['product.product'].search(self._domain(company), limit=100, order='id')
        def catalog_item(product):
            image = product.image_128
            image_data = None
            if image and len(image) <= 262144:
                try:
                    raw = base64.b64decode(image, validate=True)
                    mime = ('image/png' if raw.startswith(b'\x89PNG\r\n\x1a\n') else
                            'image/jpeg' if raw.startswith(b'\xff\xd8\xff') else None)
                    if mime:
                        encoded = image.decode('ascii') if isinstance(image, bytes) else image
                        image_data = 'data:' + mime + ';base64,' + encoded
                except (ValueError, UnicodeError):
                    pass
            return {
                'id': product.id, 'name': product.display_name,
                'description': (product.description_sale or '')[:4000],
                'image_data': image_data,
                'price': pricelist._get_product_price(product, 1.0),
                'currency': pricelist.currency_id.name,
            }
        return request.make_json_response({'products': [catalog_item(p) for p in products]}, headers=[('Cache-Control', 'no-store')])

    @http.route('/morimoto/mobile/quotations', type='http', auth='bearer', methods=['POST'], csrf=False)
    def quotation(self):
        env, partner, company = self._context()
        raw = request.httprequest.get_data(cache=True)
        if len(raw) > 16384:
            raise BadRequest()
        key = request.httprequest.headers.get('Idempotency-Key', '')
        try:
            lines = validate_cart(json.loads(raw), key)
            seen = {line['product_id'] for line in lines}
        except (ValueError, TypeError):
            raise BadRequest()
        if request.httprequest.headers.get('X-Morimoto-Customer-Session'):
            key = customer_request_key(current_account().id, key)
        fingerprint = hashlib.sha256(json.dumps(sorted(lines, key=lambda l: l['product_id']), sort_keys=True).encode()).hexdigest()
        # Serialise same-key requests across workers; SQL uniqueness is the final guard.
        lock = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], 'big', signed=True)
        env.cr.execute('SELECT pg_advisory_xact_lock(%s)', [lock])
        order = env['sale.order'].search([('morimoto_mobile_key', '=', key)], limit=1)
        if order:
            if order.partner_id != partner or order.company_id != company or order.morimoto_mobile_fingerprint != fingerprint:
                raise Conflict()
        else:
            products = env['product.product'].search(self._domain(company) + [('id', 'in', list(seen))])
            if set(products.ids) != seen:
                raise BadRequest()
            # No sudo: dedicated service user must have ordinary sale/product ACLs.
            order = env['sale.order'].with_context(tracking_disable=True, mail_create_nosubscribe=True).create({
                'partner_id': partner.id, 'company_id': company.id,
                'pricelist_id': partner.property_product_pricelist.id,
                'morimoto_mobile_key': key, 'morimoto_mobile_fingerprint': fingerprint,
                'client_order_ref': 'MORIMOTO-STAGING-' + key,
                'order_line': [(0, 0, {'product_id': l['product_id'], 'product_uom_qty': l['quantity']}) for l in lines],
            })
            if order.state != 'draft':
                raise Conflict('Custom module changed quotation state; transaction rolled back')
        # Existing promotion create hooks have already run. Return all generated
        # rewards, even when the gift itself is not in the mobile catalog.
        return request.make_json_response(quotation_payload(order), headers=[('Cache-Control', 'no-store')])
