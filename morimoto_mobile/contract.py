"""Transport contract, independent of Odoo so validation can run locally."""
import re


def validate_cart(data, key):
    if not isinstance(key, str) or not re.fullmatch(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', key):
        raise ValueError('Invalid request key')
    if not isinstance(data, dict) or set(data) != {'lines'}:
        raise ValueError('Only lines may be submitted')
    lines = data['lines']
    if not isinstance(lines, list) or not 1 <= len(lines) <= 50:
        raise ValueError('Invalid cart size')
    seen = set()
    for line in lines:
        if not isinstance(line, dict) or set(line) != {'product_id', 'quantity'}:
            raise ValueError('Invalid line fields')
        product_id, quantity = line['product_id'], line['quantity']
        if type(product_id) is not int or product_id <= 0 or product_id in seen:
            raise ValueError('Invalid product')
        if type(quantity) is not int or not 1 <= quantity <= 99:
            raise ValueError('Invalid quantity')
        seen.add(product_id)
    return sorted(lines, key=lambda line: line['product_id'])


def quotation_payload(order):
    return {
        'name': order.name, 'state': order.state,
        'amount_total': order.amount_total, 'currency': order.currency_id.name,
        'lines': [{
            'name': line.name, 'quantity': line.product_uom_qty,
            'subtotal': line.price_subtotal,
            'is_delivery': bool('is_delivery' in line._fields and line.is_delivery),
            'is_promotion_reward': bool(
                'is_motogene_promo_reward' in line._fields
                and line.is_motogene_promo_reward
            ),
        } for line in order.order_line if not line.display_type],
    }
