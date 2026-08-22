# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Dựng `Employee.permanent_address` / `current_address` bằng **tiếng Anh**.

Hai field này là field lõi kiểu Small Text, trước đây bỏ trống hoàn toàn (0/2.437). Nay chúng
được sinh ra từ bộ field tiếng Việt:

    custom_<loại>_address_village   thôn/xóm   -> giữ nguyên, không dịch được
    custom_<loại>_address_commune   xã/phường  -> wards.full_name_en
    custom_<loại>_address_province  tỉnh/TP    -> provinces.full_name_en

Ví dụ: `TDP Liên Hiệp 1C, Xã Bình An, Tỉnh Gia Lai` -> `Lien Hiep 1C Group, Binh An Commune,
Gia Lai Province`.

## Từ vựng lấy từ `api/address_converter/address.csv`

File đó là 2.398 địa chỉ HR đã dịch tay. Cột tiếng Anh của nó **lệch dòng ở nhiều chỗ** (dòng
`Xã Tây Vinh, huyện Tây Sơn, tỉnh Bình Định` lại ghép với `Lien Hiep 1C Group, Binh An Commune,
Gia Lai Province`) nên KHÔNG dùng làm bảng tra 1-1 được. Thứ lấy được từ nó là **quy ước dùng
từ**, đếm trên toàn cột tiếng Anh:

    Province 2.346 · Commune 2.132 · Village 1.909 · District 643 · Ward 215 · City 211 ·
    Group 169 · Town 28

Và quan trọng không kém — thứ nó **không** dùng: `Hamlet` 1, `Area` 0, `Quarter` 0,
`Residential` 0, `Team` 0, `Block` 0. Nên `Thôn` là **Village** chứ không phải Hamlet, và `KDC`
xếp vào `Group` thay vì bịa ra "Residential Area" không có trong từ vựng của HR.

## 🔴 Tra xã PHẢI kèm mã tỉnh

Tên xã **trùng nhau giữa các tỉnh**: đo trên bảng `wards`, `Xã Tân Thanh` có ở **13 tỉnh**,
`Xã Vĩnh Thanh` 7 tỉnh. Tra bằng mỗi tên xã là bốc trúng tỉnh nào thì trúng — sai âm thầm, và sai
đúng vào địa chỉ của người lao động. Nên khoá tra cứu là cặp `(mã tỉnh, tên xã)`.

## Không tra được thì GIỮ NGUYÊN tiếng Việt

Bảng `provinces` chỉ chứa đơn vị hành chính **sau sáp nhập 2025**, trong khi dữ liệu Employee còn
tên cũ (`Tỉnh Quảng Nam`, `TP Đà Nẵng`, `Tỉnh Bình Định`… — 28/2.046 hồ sơ) và cả những ô nhập tay
lộn xộn (`Xã Thăng Điền- Thành phố Đà Nẵng`). Đo được: **2.018/2.046** tra được tỉnh,
**1.993/2.046** tra được xã.

Với phần không tra được, giữ nguyên chuỗi tiếng Việt thay vì bỏ trống hay đoán. Một địa chỉ lẫn
tiếng Việt vẫn gửi thư đến nơi; một địa chỉ trống hoặc dịch sai thì không.
"""

import json
import os

import frappe
from frappe.utils import cstr

# Từ vựng nằm ở `address_vocabulary.json` cạnh file này — KHÔNG hardcode, để HR sửa được cách
# dịch mà không cần đụng code.
_TTL = 86400

VOCAB_FILE = os.path.join(os.path.dirname(__file__), "address_vocabulary.json")
_CACHE_VOCAB = "tiqn:addr_en:vocab"


def _vocab() -> dict:
	"""Nạp từ vựng, đã sắp DÀI TRƯỚC NGẮN.

	Sắp lúc nạp chứ không bắt người sửa file phải để ý thứ tự: `tổ dân phố` phải được xét trước
	`tổ`, nếu không `tổ` khớp trước và ra `Dan Pho Group`.
	"""
	cached = frappe.cache().get_value(_CACHE_VOCAB)
	if cached:
		return {
			"local_suffix": [(tuple(k.split()), v) for k, v in cached["local_suffix"]],
			"local_prefix": [(tuple(k.split()), v) for k, v in cached["local_prefix"]],
			"admin_unit": [(tuple(k.split()), v) for k, v in cached["admin_unit"]],
			"translate_unmatched_admin": cached["translate_unmatched_admin"],
		}

	with open(VOCAB_FILE, encoding="utf-8") as f:
		raw = json.load(f)

	def rules(section):
		items = [(k, v) for k, v in (raw.get(section) or {}).items() if not k.startswith("_")]
		# nhiều từ trước, rồi tới chuỗi dài hơn — quyết định thứ tự khớp
		return sorted(items, key=lambda kv: (-len(kv[0].split()), -len(kv[0])))

	out = {
		"local_suffix": rules("local_suffix"),
		"local_prefix": rules("local_prefix"),
		"admin_unit": rules("admin_unit"),
		"translate_unmatched_admin": bool(raw.get("translate_unmatched_admin")),
	}
	frappe.cache().set_value(_CACHE_VOCAB, out, expires_in_sec=_TTL)
	return {k: ([(tuple(a.split()), b) for a, b in v] if isinstance(v, list) else v)
	        for k, v in out.items()}

_CACHE_PROVINCE = "tiqn:addr_en:provinces"
_CACHE_WARD = "tiqn:addr_en:wards"

# (field tiếng Việt) -> field lõi nhận bản tiếng Anh
ADDRESS_PAIRS = {
	"permanent": "permanent_address",
	"current": "current_address",
	# 🚧 "place_of_origin": không còn — field quê quán đã bị gỡ khỏi Employee 21/08/2026.
}


def _maps():
	"""`({tên tỉnh VN: (mã, tên EN)}, {(mã tỉnh, tên xã VN): tên xã EN})`, cache 1 ngày."""
	prov = frappe.cache().get_value(_CACHE_PROVINCE)
	ward = frappe.cache().get_value(_CACHE_WARD)
	if prov and ward:
		# Redis trả key của dict lồng về dạng chuỗi -> dựng lại tuple cho map xã.
		return prov, {tuple(k.split("\x1f", 1)): v for k, v in ward.items()}

	prov = {
		r.full_name: (r.code, r.full_name_en)
		for r in frappe.db.sql(
			"SELECT code, full_name, full_name_en FROM provinces", as_dict=True
		)
	}
	ward_rows = frappe.db.sql(
		"SELECT province_code, full_name, full_name_en FROM wards", as_dict=True
	)
	ward = {(r.province_code, r.full_name): r.full_name_en for r in ward_rows}

	frappe.cache().set_value(_CACHE_PROVINCE, prov, expires_in_sec=_TTL)
	frappe.cache().set_value(
		_CACHE_WARD, {f"{k[0]}\x1f{k[1]}": v for k, v in ward.items()}, expires_in_sec=_TTL
	)
	return prov, ward


def no_diacritics(text: str) -> str:
	"""Bỏ dấu tiếng Việt, giữ nguyên hoa/thường. `Phước Bình` -> `Phuoc Binh`, `Đội` -> `Doi`."""
	import unicodedata

	out = unicodedata.normalize("NFD", cstr(text))
	out = "".join(c for c in out if unicodedata.category(c) != "Mn")
	return out.replace("đ", "d").replace("Đ", "D")


def _translate_local(text: str) -> str:
	"""Dịch phần thôn/xóm/tổ: `Thôn Phước Bình` -> `Phuoc Binh Village`.

	Ô này là nhập tay nên có thể chứa nhiều cấp ngăn bởi dấu phẩy (`Xóm 3, Minh Thành`); xử lý
	từng đoạn một.

	Không khớp tiền tố nào thì vẫn **bỏ dấu** — cột tiếng Anh trong file mẫu của HR là ASCII.
	"""
	vocab = _vocab()
	segments = []
	for seg in cstr(text).split(","):
		seg = seg.strip()
		if not seg:
			continue

		words = seg.split()
		keys = tuple(no_diacritics(w).lower().rstrip(".") for w in words)

		for pref, suffix in vocab["local_suffix"]:
			if keys[: len(pref)] == pref and len(words) > len(pref):
				rest_words = words[len(pref):]

				# `Khu dân cư số 3` -> bỏ chữ "số" thừa, còn `3`
				if len(rest_words) > 1 and no_diacritics(rest_words[0]).lower().rstrip(".") == "so":
					rest_words = rest_words[1:]

				rest = no_diacritics(" ".join(rest_words))

				# Phần còn lại thuần số thì danh từ đứng TRƯỚC: `Tổ 23` -> `Group 23`,
				# `Xóm 3` -> `Village 3` — đúng cách file mẫu của HR viết (`Group 13`,
				# `Village 1`). Có chữ thì đứng sau: `Thôn An Đại 2` -> `An Dai 2 Village`.
				segments.append(
					f"{suffix} {rest}" if rest.replace(" ", "").isdigit() else f"{rest} {suffix}"
				)
				break
		else:
			for pref, head in vocab["local_prefix"]:
				if keys[: len(pref)] == pref and len(words) > len(pref):
					segments.append(head + no_diacritics(" ".join(words[len(pref):])))
					break
			else:
				segments.append(no_diacritics(seg))

	return ", ".join(segments)


def english_address(village: str, commune: str, province: str) -> str:
	"""Ghép địa chỉ tiếng Anh. Phần nào không tra được thì giữ nguyên tiếng Việt."""
	village, commune, province = cstr(village).strip(), cstr(commune).strip(), cstr(province).strip()
	if not (village or commune or province):
		return ""

	prov_map, ward_map = _maps()
	code, province_en = prov_map.get(province, (None, None))
	commune_en = ward_map.get((code, commune)) if code and commune else None

	# ⚠ Xã/tỉnh không tra được: mặc định GIỮ NGUYÊN tiếng Việt CÓ DẤU — đó là tín hiệu để lọc ra
	# dữ liệu cần sửa (`current_address LIKE '%Tỉnh %'`). Bật `translate_unmatched_admin` trong
	# `address_vocabulary.json` thì dịch máy bằng bảng `admin_unit`; đọc cảnh báo trong file đó
	# trước khi bật.
	# Phần thôn thì luôn dịch được, vì chỉ là bỏ dấu + đổi tiền tố, không phụ thuộc bảng tra.
	return ", ".join(
		p
		for p in (
			_translate_local(village),
			commune_en or _fallback_admin(commune),
			province_en or _fallback_admin(province),
		)
		if p
	)


def _fallback_admin(text: str) -> str:
	"""Xã/tỉnh không có trong bảng tra. Trả nguyên tiếng Việt, trừ khi cờ trong JSON bật."""
	text = cstr(text).strip()
	if not text:
		return ""

	vocab = _vocab()
	if not vocab["translate_unmatched_admin"]:
		return text

	words = text.split()
	keys = tuple(no_diacritics(w).lower().rstrip(".") for w in words)
	for pref, suffix in vocab["admin_unit"]:
		if keys[: len(pref)] == pref and len(words) > len(pref):
			return f"{no_diacritics(' '.join(words[len(pref):]))} {suffix}"
	return no_diacritics(text)


SOURCE_SUFFIXES = ("village", "commune", "province")


def _vn_parts(doc, prefix):
	return tuple(cstr(doc.get(f"custom_{prefix}_address_{s}")).strip() for s in SOURCE_SUFFIXES)


def sync_english_addresses(doc):
	"""Ghi 2 field địa chỉ tiếng Anh — **chỉ khi cần**. Gọi trong `validate`.

	Ba nhánh, theo đúng thứ tự:

	1. **Ô tiếng Anh đang rỗng** mà có dữ liệu tiếng Việt -> dịch và điền. Đây là đường cho hồ sơ
	   cũ và cho Data Import chỉ có cột tiếng Việt.
	2. **Bộ field tiếng Việt vừa đổi trong chính lần lưu này** -> dịch lại. So với
	   `get_doc_before_save()`, không so với giá trị đang tính ra.
	3. Còn lại -> **KHÔNG đụng vào**.

	## 🔴 Vì sao không dịch lại ở mọi lần lưu

	Bản đầu dịch lại mỗi lần `validate` chạy rồi ghi đè nếu khác. Hệ quả: **địa chỉ tiếng Anh
	import thẳng vào bị xoá mất** ở lần lưu kế tiếp — người ta nhập bản dịch tay đúng chuẩn hợp
	đồng, hệ thống lẳng lặng thay bằng bản máy dịch.

	Nay giá trị tiếng Anh có sẵn là **bất khả xâm phạm**, trừ khi chính nguồn tiếng Việt của nó
	đổi. Muốn dựng lại thì xoá trắng ô tiếng Anh rồi lưu (nhánh 1), hoặc sửa địa chỉ tiếng Việt
	(nhánh 2).

	⚠ Cũng đừng bỏ điều kiện "giá trị thực sự đổi": `validate` chạy ở mọi lần lưu, gán lại chuỗi
	y hệt vẫn khiến Frappe coi document là "đã đổi" và sinh một bản `Version` thừa mỗi lần lưu.
	"""
	before = doc.get_doc_before_save()

	for prefix, target in ADDRESS_PAIRS.items():
		current_en = cstr(doc.get(target)).strip()
		parts = _vn_parts(doc, prefix)

		if current_en:
			# Đã có bản tiếng Anh -> chỉ dựng lại khi nguồn tiếng Việt vừa đổi.
			if not before or _vn_parts(before, prefix) == parts:
				continue

		if not any(parts):
			continue

		value = english_address(*parts)
		if value and value != current_en:
			doc.set(target, value)


@frappe.whitelist()
def translate_address(village: str = "", commune: str = "", province: str = "") -> str:
	"""Dịch một địa chỉ — cho JS gọi khi người dùng vừa sửa ô tiếng Việt trên form.

	Chỉ đọc, không ghi gì: client tự `set_value` vào ô tiếng Anh. Nhờ vậy HR thấy kết quả ngay
	trước khi lưu, thay vì phải lưu xong mới biết máy dịch ra cái gì.
	"""
	return english_address(village, commune, province)
