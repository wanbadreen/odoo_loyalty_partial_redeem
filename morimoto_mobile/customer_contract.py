"""Customer identity validation, shared by controllers and offline tests."""
import hashlib
import re


def email_address(value):
    value = str(value or '').strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[a-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?\.[a-z]{2,63}', value):
        raise ValueError('Email tidak sah.')
    return value


def phone_number(value):
    value = re.sub(r'[\s().-]', '', str(value or '').strip())
    if value.startswith('00'):
        value = '+' + value[2:]
    if value.startswith('01'):
        value = '+6' + value
    elif value.startswith('60'):
        value = '+' + value
    if not re.fullmatch(r'\+[1-9][0-9]{7,14}', value):
        raise ValueError('Gunakan nombor telefon dengan kod negara, contohnya +60123456789.')
    return value


def login_identifier(value):
    return ('email', email_address(value)) if '@' in str(value) else ('phone', phone_number(value))


def password_value(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 128:
        raise ValueError('Kata laluan mesti mengandungi 12 hingga 128 aksara.')
    return value


def token_digest(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value):
        raise ValueError('Token tidak sah.')
    return hashlib.sha256(value.encode()).hexdigest()


def customer_request_key(account_id, key):
    return hashlib.sha256(('customer:%s:%s' % (account_id, key)).encode()).hexdigest()


def delivery_values(data):
    required = {'name', 'phone', 'street', 'city', 'zip', 'state_id'}
    if not isinstance(data, dict) or not required <= set(data) or set(data) - required - {'street2'}:
        raise ValueError('Alamat tidak lengkap.')
    result = {}
    for field, maximum in {'name': 100, 'phone': 25, 'street': 200, 'street2': 200, 'city': 100, 'zip': 5, 'state_id': 10}.items():
        value = data.get(field, '')
        if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
            raise ValueError('Alamat tidak sah.')
        result[field] = value.strip()
        if field in required and not result[field]:
            raise ValueError('Alamat tidak lengkap.')
    result['phone'] = phone_number(result['phone'])
    if not re.fullmatch(r'[0-9]{5}', result['zip']) or not re.fullmatch(r'[1-9][0-9]*', result['state_id']):
        raise ValueError('Poskod atau negeri tidak sah.')
    result['state_id'] = int(result['state_id'])
    return result
