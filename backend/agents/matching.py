"""Conservative requirement matching shared by discovery and comparison."""
import operator
import math
import re
from models.request import Requirement
from models.product import Spec

OPERATORS = {'<': operator.lt, '<=': operator.le, '>': operator.gt,
             '>=': operator.ge, '=': operator.eq, '==': operator.eq}
ALIASES = {
    'memory': 'ram', 'ram gb': 'ram', 'ram tb': 'ram',
    'storage gb': 'storage', 'storage tb': 'storage',
    'price': 'budget', 'price usd': 'budget', 'price pkr': 'budget',
    'linux': 'linux', 'linux support': 'linux', 'linux compatibility': 'linux',
    'os compatibility': 'linux', 'os/linux support': 'linux',
    'ram upgradeable': 'upgradeability', 'upgradeable': 'upgradeability',
    'weight lbs': 'weight', 'weight kg': 'weight',
    'display inches': 'display', 'screen size': 'display',
    'graphics': 'gpu', 'graphics card': 'gpu', 'graphics processor': 'gpu',
    'video memory': 'vram', 'gpu memory': 'vram', 'vram gb': 'vram',
    'manufacturer': 'brand',
}


def canonical_key(key: str) -> str:
    key = key.lower().replace('_', ' ').replace('-', ' ').strip()
    return ALIASES.get(key, key)


def money(value: str):
    """Parse explicit USD/PKR amounts; legacy bare amounts mean USD. No FX."""
    text = str(value).strip().upper()
    number = r'(\d+(?:,\d{3})*(?:\.\d+)?)'
    match = re.fullmatch(r'(USD|PKR|RS\.?|\$)?\s*' + number + r'\s*(USD|PKR)?', text)
    if not match:
        return None
    prefix, amount, suffix = match.groups()
    currency = {'$': 'USD', 'RS': 'PKR', 'RS.': 'PKR'}.get(prefix, prefix)
    if currency and suffix and currency != suffix:
        return None
    amount = float(amount.replace(',', ''))
    return (amount, suffix or currency or 'USD') if math.isfinite(amount) else None


def quantity(value: str, key: str):
    """Return one unambiguous number in canonical units; ranges/descriptions stay unknown."""
    value = value.lower().replace(',', '').strip()
    match = re.fullmatch(r'\$?\s*(\d+(?:\.\d+)?)\s*([a-z\"]*)', value)
    if not match:
        return None
    amount, unit = float(match[1]), match[2]
    units = {
        'budget': {'': 1, 'usd': 1},
        'ram': {'': 1, 'gb': 1, 'gib': 1.073741824, 'tb': 1000, 'tib': 1099.511627776, 'mb': .001},
        'vram': {'': 1, 'gb': 1, 'gib': 1.073741824, 'mb': .001},
        'storage': {'': 1, 'gb': 1, 'gib': 1.073741824, 'tb': 1000, 'tib': 1099.511627776, 'mb': .001},
        'weight': {'kg': 1, 'g': .001, 'lbs': .45359237, 'lb': .45359237},
        'display': {'inches': 1, 'inch': 1, 'in': 1, '"': 1},
    }
    factor = units.get(key, {}).get(unit)
    result = amount * factor if factor is not None else None
    return result if result is not None and math.isfinite(result) else None


def match_requirement(req: Requirement, specs: list[Spec]) -> tuple[str, str, list[str]]:
    key = canonical_key(req.key)
    candidates = [s for s in specs if canonical_key(s.key) == key]
    if not candidates:
        return '?', f"No data found for '{req.key}'", []
    evidence = list(dict.fromkeys(e for s in candidates for e in s.evidence_ids))
    if any(s.status == 'conflicting' for s in candidates) or len({s.value.lower() for s in candidates}) > 1:
        return '?', f"'{req.key}' has conflicting information", evidence
    spec = candidates[0]
    value = spec.value.lower().strip()
    if spec.status == 'insufficient' or not evidence or value in ('', 'none', 'null') or re.search(r'\b(unknown|unconfirmed|unclear)\b|not found', value):
        return '?', f"'{req.key}' could not be confirmed", evidence
    if key in ('budget', 'ram', 'vram', 'storage', 'weight', 'display'):
        actual_text = value
        # Bare seed numbers have units encoded in their keys.
        if re.fullmatch(r'\d+(?:\.\d+)?', value):
            suffix = spec.key.lower().replace('_', ' ').split()[-1]
            if suffix in ('gb', 'tb', 'kg', 'lbs', 'inches'):
                actual_text += ' ' + suffix
        if key == 'budget':
            actual_money, expected_money = money(actual_text), money(req.value)
            if not actual_money or not expected_money or actual_money[1] != expected_money[1]:
                return '?', 'Budget currency is unknown or differs from the recorded price; no currency conversion applied', evidence
            actual, expected = actual_money[0], expected_money[0]
        else:
            actual, expected = quantity(actual_text, key), quantity(req.value, key)
        compare = OPERATORS.get(req.operator)
        if actual is None or expected is None or compare is None:
            return '?', f"Cannot compare '{req.key}' with the available units/operator", evidence
        met = compare(actual, expected)
        return ('✓' if met else '✕'), f'{req.key}: {spec.value}; requested {req.operator} {req.value}', evidence

    wanted = req.value.lower().strip()
    if key == 'linux' and wanted == 'linux' and req.operator in ('=', '==', 'supports'):
        if re.search(r'\b(no|not)\s+(linux|supported|compatible)|unsupported', value):
            return '✕', f'Linux support: {spec.value}', evidence
        if any(word in value for word in ('partial', 'mixed', 'not officially', 'not certified', 'not native')):
            return '?', f'Linux support is uncertain: {spec.value}', evidence
        if any(word in value for word in ('native', 'certified', 'strong', 'excellent', 'supported', 'pop!_os')):
            return '✓', f'Linux support: {spec.value}', evidence
        return '?', 'Linux support could not be confirmed', evidence

    if key in ('virtualization', 'upgradeability') and wanted in ('high', 'preferred', 'true', 'yes', 'supported') and req.operator in ('=', '==', 'supports'):
        if re.search(r'\b(no|false|disabled)\b|not (supported|upgradeable|replaceable)|non.upgradeable|unsupported|(?<!not )soldered', value):
            return '✕', f'{req.key}: {spec.value}', evidence
        if re.search(r'\bnot\b', value) and 'not soldered' not in value:
            return '?', f"'{req.key}' could not be confirmed", evidence
        positive = ('true', 'yes', 'supported', 'amd-v', 'vt-x', 'upgradeable', 'replaceable', 'so-dimm', 'not soldered')
        if any(word in value for word in positive):
            return '✓', f'{req.key}: {spec.value}', evidence
        return '?', f"'{req.key}' could not be confirmed", evidence

    if key == 'gpu' and req.operator in ('=', '==', 'contains'):
        # A GPU model identifies the chip, not the vendor prefix or VRAM suffix.
        chip = r'\b(?:rtx|gtx|rx|arc)\s*[- ]?\s*\d{3,4}(?:\s*(?:ti|super))?\b'
        actual_chip, wanted_chip = re.search(chip, value), re.search(chip, wanted)
        if actual_chip and not wanted_chip and re.fullmatch(r"\d{3,4}", wanted):
            met = re.fullmatch(r"(?:rtx|gtx|rx|arc)\s*[- ]?\s*" + re.escape(wanted), actual_chip[0]) is not None
            return ("✓" if met else "✕"), f"{req.key}: {spec.value}; requested {req.value}", evidence
        if actual_chip and wanted_chip:
            met = re.sub(r'\s|-', '', actual_chip[0]) == re.sub(r'\s|-', '', wanted_chip[0])
            return ('✓' if met else '✕'), f'{req.key}: {spec.value}; requested {req.value}', evidence
    if req.operator in ('=', '=='):
        met = value == wanted
    elif req.operator in ('contains', 'supports'):
        # A negated phrase is not positive evidence of support.
        if re.search(r'\b(no|not|unsupported)\b', value):
            return '?', f"'{req.key}' support could not be confirmed", evidence
        met = wanted in value
    else:
        return '?', f"Unsupported comparison for '{req.key}'", evidence
    return ('✓' if met else '✕'), f'{req.key}: {spec.value}; requested {req.value}', evidence
