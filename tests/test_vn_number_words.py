"""Bench-free unit tests for customize_erpnext.api.vn_number_words.

Run from the app root without a site:

    cd apps/customize_erpnext && python -m unittest discover tests

The module is loaded by file path rather than imported normally, because
`customize_erpnext/__init__.py` imports the overrides package (and therefore
frappe), which needs a live bench. vn_number_words.py itself is pure stdlib.
"""

import importlib.util
import unittest
from pathlib import Path

_MODULE_PATH = Path(__file__).resolve().parents[1] / "customize_erpnext" / "api" / "vn_number_words.py"
_spec = importlib.util.spec_from_file_location("vn_number_words", _MODULE_PATH)
vnw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vnw)

money_in_words_vi = vnw.money_in_words_vi
format_vnd = vnw.format_vnd


class TestMoneyInWordsVi(unittest.TestCase):
    def test_zero(self):
        self.assertEqual(money_in_words_vi(0), "Không đồng")

    def test_single_digits(self):
        self.assertEqual(money_in_words_vi(1), "Một đồng")
        self.assertEqual(money_in_words_vi(9), "Chín đồng")

    def test_teens_use_muoi(self):
        self.assertEqual(money_in_words_vi(10), "Mười đồng")
        self.assertEqual(money_in_words_vi(11), "Mười một đồng")
        self.assertEqual(money_in_words_vi(14), "Mười bốn đồng")  # not "mười tư"
        self.assertEqual(money_in_words_vi(15), "Mười lăm đồng")  # not "mười năm"

    def test_tens_use_mot_tu_lam(self):
        self.assertEqual(money_in_words_vi(20), "Hai mươi đồng")
        self.assertEqual(money_in_words_vi(21), "Hai mươi mốt đồng")  # not "một"
        self.assertEqual(money_in_words_vi(24), "Hai mươi tư đồng")  # USE_TU_FOR_FOUR
        self.assertEqual(money_in_words_vi(25), "Hai mươi lăm đồng")

    def test_hundreds_use_le(self):
        self.assertEqual(money_in_words_vi(100), "Một trăm đồng")
        self.assertEqual(money_in_words_vi(101), "Một trăm lẻ một đồng")
        self.assertEqual(money_in_words_vi(105), "Một trăm lẻ năm đồng")  # not "lẻ lăm"
        self.assertEqual(money_in_words_vi(999), "Chín trăm chín mươi chín đồng")

    def test_thousands_and_millions(self):
        self.assertEqual(money_in_words_vi(1_000), "Một nghìn đồng")
        self.assertEqual(money_in_words_vi(1_000_000), "Một triệu đồng")
        self.assertEqual(
            money_in_words_vi(1_234_567),
            "Một triệu hai trăm ba mươi tư nghìn năm trăm sáu mươi bảy đồng",
        )

    def test_zero_groups_are_skipped(self):
        self.assertEqual(money_in_words_vi(1_000_500), "Một triệu năm trăm đồng")

    def test_non_leading_group_gets_khong_tram(self):
        self.assertEqual(money_in_words_vi(1_067), "Một nghìn không trăm sáu mươi bảy đồng")

    def test_billions_and_above(self):
        self.assertEqual(money_in_words_vi(1_000_000_000), "Một tỷ đồng")
        # Above 10^12 the scale word repeats with " tỷ" — the upstream version
        # silently dropped these positions.
        self.assertEqual(money_in_words_vi(2_000_000_000_000), "Hai nghìn tỷ đồng")
        self.assertEqual(money_in_words_vi(3_000_000_000_000_000), "Ba triệu tỷ đồng")

    def test_negative_is_prefixed_with_am(self):
        self.assertEqual(money_in_words_vi(-1_000), "Âm một nghìn đồng")

    def test_rounding_is_half_up(self):
        self.assertEqual(money_in_words_vi(1_000.5), "Một nghìn không trăm lẻ một đồng")
        self.assertEqual(money_in_words_vi(1_000.4), "Một nghìn đồng")

    def test_four_reading_is_switchable(self):
        vnw.USE_TU_FOR_FOUR = False
        try:
            self.assertEqual(money_in_words_vi(24), "Hai mươi bốn đồng")
        finally:
            vnw.USE_TU_FOR_FOUR = True

    def test_custom_currency(self):
        self.assertEqual(money_in_words_vi(5, currency="đồng chẵn"), "Năm đồng chẵn")
        self.assertEqual(money_in_words_vi(5, currency=""), "Năm")

    def test_bad_input_returns_empty_string(self):
        for value in (None, "", "abc", object()):
            self.assertEqual(money_in_words_vi(value), "")

    def test_numeric_string_is_accepted(self):
        self.assertEqual(money_in_words_vi("1234567"), money_in_words_vi(1_234_567))

    def test_alias_matches(self):
        self.assertIs(vnw.so_tien_bang_chu, money_in_words_vi)


class TestFormatVnd(unittest.TestCase):
    def test_thousand_separator_is_dot(self):
        self.assertEqual(format_vnd(1_234_567), "1.234.567 ₫")
        self.assertEqual(format_vnd(0), "0 ₫")
        self.assertEqual(format_vnd(999), "999 ₫")

    def test_negative(self):
        self.assertEqual(format_vnd(-1_234_567), "-1.234.567 ₫")

    def test_rounding_is_half_up(self):
        self.assertEqual(format_vnd(1_000.5), "1.001 ₫")

    def test_custom_symbol(self):
        self.assertEqual(format_vnd(1_000, symbol="VND"), "1.000 VND")
        self.assertEqual(format_vnd(1_000, symbol=""), "1.000")

    def test_bad_input_returns_empty_string(self):
        self.assertEqual(format_vnd(None), "")
        self.assertEqual(format_vnd("abc"), "")


if __name__ == "__main__":
    unittest.main()
