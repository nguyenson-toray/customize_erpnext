"""
Vietnamese money formatting helpers for Print Formats.

Pure standard library on purpose — no `frappe` import — so the logic can be
unit-tested without a bench/site (see `tests/test_vn_number_words.py`).

Registered as Jinja methods in hooks.py, so Print Formats can call:

    {{ money_in_words_vi(doc.grand_total) }}   ->  Một triệu hai trăm ... đồng
    {{ so_tien_bang_chu(doc.grand_total) }}    ->  (alias, same output)
    {{ format_vnd(doc.grand_total) }}          ->  1.234.567 ₫

Adapted from the `so_tien_bang_chu` helper in github.com/mrhuychien/erpnextvn,
with fixes for negative amounts, amounts above 10^12, and non-numeric input.
"""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

# Digit words. Index == the digit itself, so _ONES[7] == "bảy".
_ONES = ["", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]

# Scale word for each group of 3 digits, counting from the right.
# Index 0..2 are handled directly; from index 3 up we append " tỷ" per full
# power of 10^9, giving "tỷ", "nghìn tỷ", "triệu tỷ", "tỷ tỷ", ...
_SCALE_BASE = ["", "nghìn", "triệu"]

# Both readings of a trailing 4 after "mươi" are correct Vietnamese:
# "hai mươi tư" (True) or "hai mươi bốn" (False). Flip if the accounting
# team prefers the other on printed vouchers.
USE_TU_FOR_FOUR = True


def _to_int(amount):
    """Round any numeric-ish input to a whole VND amount (half-up).

    Returns None when the value cannot be read as a number — Print Formats
    routinely pass empty/None fields and must not blow up on them.
    """
    if amount is None or amount == "":
        return None
    try:
        return int(Decimal(str(amount)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _scale_word(group_index):
    """Scale word for the Nth group of 3 digits (0 = units)."""
    if group_index < len(_SCALE_BASE):
        return _SCALE_BASE[group_index]
    base = _SCALE_BASE[group_index % 3]
    billions = " tỷ" * (group_index // 3)
    return (base + billions).strip()


def _read_three_digits(n, show_zero_hundred=False):
    """Read a 3-digit group (1..999) in Vietnamese.

    show_zero_hundred: prefix "không trăm" for values under 100. Used for
    non-leading groups so digit positions stay readable
    ("một tỷ không trăm sáu mươi bảy" rather than "một tỷ sáu mươi bảy").
    """
    if n == 0:
        return ""

    hundred, ten, one = n // 100, (n % 100) // 10, n % 10
    parts = []

    if hundred > 0:
        parts.append(f"{_ONES[hundred]} trăm")
    elif show_zero_hundred:
        parts.append("không trăm")

    if ten > 1:
        parts.append(f"{_ONES[ten]} mươi")
        if one == 1:
            parts.append("mốt")  # 21 -> hai mươi mốt
        elif one == 4 and USE_TU_FOR_FOUR:
            parts.append("tư")  # 24 -> hai mươi tư
        elif one == 5:
            parts.append("lăm")  # 25 -> hai mươi lăm
        elif one > 0:
            parts.append(_ONES[one])
    elif ten == 1:
        parts.append("mười")
        if one == 5:
            parts.append("lăm")  # 15 -> mười lăm (but 14 -> mười bốn)
        elif one > 0:
            parts.append(_ONES[one])
    elif one > 0:
        if hundred > 0 or show_zero_hundred:
            parts.append("lẻ")  # 105 -> một trăm lẻ năm
        parts.append(_ONES[one])

    return " ".join(parts)


def money_in_words_vi(amount, currency="đồng"):
    """Spell a monetary amount out in Vietnamese, capitalized.

    money_in_words_vi(1234567) -> "Một triệu hai trăm ba mươi bốn nghìn năm
    trăm sáu mươi bảy đồng"

    Negative amounts are prefixed with "Âm". Returns "" for unreadable input.
    """
    value = _to_int(amount)
    if value is None:
        return ""

    negative = value < 0
    value = abs(value)

    if value == 0:
        return f"Không {currency}".strip()

    # Split into groups of 3 digits, least significant first.
    groups = []
    while value > 0:
        groups.append(value % 1000)
        value //= 1000

    parts = []
    for i in range(len(groups) - 1, -1, -1):
        if groups[i] == 0:
            continue
        text = _read_three_digits(groups[i], show_zero_hundred=i < len(groups) - 1)
        if text:
            parts.append(f"{text} {_scale_word(i)}".strip())

    result = " ".join(parts)
    if negative:
        result = f"âm {result}"
    result = result[0].upper() + result[1:]
    return f"{result} {currency}".strip()


#: Alias — the term Vietnamese accountants expect to see in a Print Format.
so_tien_bang_chu = money_in_words_vi


def format_vnd(amount, symbol="₫"):
    """Format a number the Vietnamese way: "1.234.567 ₫".

    Pass symbol="" for a bare number, or symbol="VND" for the ISO code.
    Returns "" for unreadable input.
    """
    value = _to_int(amount)
    if value is None:
        return ""

    formatted = f"{value:,}".replace(",", ".")
    return f"{formatted} {symbol}".strip()
