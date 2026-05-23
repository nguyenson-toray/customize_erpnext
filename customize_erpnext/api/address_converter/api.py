"""
Address Converter API — Địa chỉ hành chính Việt Nam 2025 (sau sáp nhập 07/2025)

Cấu trúc dữ liệu JSON:
- Top level: Tỉnh/TP  [{ma, ten, xa:[...]}]
- xa[]:  Đơn vị hành chính cấp Quận/Huyện mới  [{ma, ten, xa_cu:[...]}]
- xa_cu[]: Phường/Xã cũ trước sáp nhập          [{ma, ten, ghi_chu, quan_huyen_cu, ...}]

API for web page (allow_guest=True):
  get_provinces     → Danh sách Tỉnh/TP
  get_districts     → Đơn vị mới dưới Tỉnh (xa array)
  get_wards         → Phường/Xã cũ trong một đơn vị mới (xa_cu array)
  convert_address   → Chuyển đổi 1 mã phường/xã cũ ↔ mới
  convert_batch     → Chuyển đổi nhiều mã
"""

import json
import os
import frappe
from frappe import _

_DATA_PATH = os.path.join(os.path.dirname(__file__), "dia_chi_hanh_chinh_2025.json")
_CACHE_KEY = "vn_address_data_2025"


def _load_data():
	"""Load and cache address data (24h TTL)."""
	cached = frappe.cache().get_value(_CACHE_KEY)
	if cached:
		return cached
	with open(_DATA_PATH, encoding="utf-8") as f:
		data = json.load(f)
	frappe.cache().set_value(_CACHE_KEY, data, expires_in_sec=86400)
	return data


@frappe.whitelist(allow_guest=True)
def get_provinces():
	"""Return list of all provinces/cities. [{ma, ten}]"""
	data = _load_data()
	return [{"ma": p["ma"], "ten": p["ten"]} for p in data]


@frappe.whitelist(allow_guest=True)
def get_districts(province_code):
	"""Return new administrative units under a province (xa array). [{ma, ten}]"""
	data = _load_data()
	for province in data:
		if province["ma"] == province_code:
			return [{"ma": d["ma"], "ten": d["ten"]} for d in province.get("xa", [])]
	return []


@frappe.whitelist(allow_guest=True)
def get_wards(district_code):
	"""Return old wards (xa_cu) that merged into a new district unit. [{ma, ten, ghi_chu}]"""
	data = _load_data()
	for province in data:
		for district in province.get("xa", []):
			if district["ma"] == district_code:
				return [
					{
						"ma": w["ma"],
						"ten": w["ten"],
						"ghi_chu": w.get("ghi_chu", ""),
					}
					for w in district.get("xa_cu", [])
				]
	return []


@frappe.whitelist(allow_guest=True)
def convert_address(ward_code, direction="old_to_new"):
	"""
	Convert a single ward code between old and new addresses.
	direction: "old_to_new" → find xa_cu by old ma → return {old: {...}, new: {...}}
	           "new_to_old" → find new district by ma → return {new: {...}, old: [old wards]}
	"""
	data = _load_data()

	if direction == "old_to_new":
		for province in data:
			for district in province.get("xa", []):
				for old_ward in district.get("xa_cu", []):
					if old_ward["ma"] == ward_code:
						return {
							"old": {
								"ma": old_ward["ma"],
								"ten": old_ward["ten"],
								"quan_huyen": old_ward.get("quan_huyen_cu", ""),
								"tinh": old_ward.get("tinh_cu", ""),
								"ghi_chu": old_ward.get("ghi_chu", ""),
							},
							"new": {
								"ma": district["ma"],
								"ten": district["ten"],
								"tinh_ma": province["ma"],
								"tinh": province["ten"],
							},
						}
	elif direction == "new_to_old":
		for province in data:
			for district in province.get("xa", []):
				if district["ma"] == ward_code:
					return {
						"new": {
							"ma": district["ma"],
							"ten": district["ten"],
							"tinh_ma": province["ma"],
							"tinh": province["ten"],
						},
						"old": [
							{
								"ma": w["ma"],
								"ten": w["ten"],
								"quan_huyen": w.get("quan_huyen_cu", ""),
								"tinh": w.get("tinh_cu", ""),
								"ghi_chu": w.get("ghi_chu", ""),
							}
							for w in district.get("xa_cu", [])
						],
					}

	frappe.throw(_("Address code not found: {0}").format(ward_code))


@frappe.whitelist(allow_guest=True)
def convert_batch(codes, direction="old_to_new"):
	"""
	Convert multiple ward codes at once.
	codes: JSON string of list, e.g. '["00004","00013"]'
	Returns list of results (same structure as convert_address, or null if not found).
	"""
	if isinstance(codes, str):
		try:
			codes = json.loads(codes)
		except Exception:
			frappe.throw(_("Invalid codes format. Expected JSON array."))

	data = _load_data()

	# Build lookup maps for performance
	if direction == "old_to_new":
		old_to_new_map = {}
		for province in data:
			for district in province.get("xa", []):
				for old_ward in district.get("xa_cu", []):
					old_to_new_map[old_ward["ma"]] = {
						"old": {
							"ma": old_ward["ma"],
							"ten": old_ward["ten"],
							"quan_huyen": old_ward.get("quan_huyen_cu", ""),
							"tinh": old_ward.get("tinh_cu", ""),
							"ghi_chu": old_ward.get("ghi_chu", ""),
						},
						"new": {
							"ma": district["ma"],
							"ten": district["ten"],
							"tinh_ma": province["ma"],
							"tinh": province["ten"],
						},
					}
		return [old_to_new_map.get(code) for code in codes]

	elif direction == "new_to_old":
		new_to_old_map = {}
		for province in data:
			for district in province.get("xa", []):
				new_to_old_map[district["ma"]] = {
					"new": {
						"ma": district["ma"],
						"ten": district["ten"],
						"tinh_ma": province["ma"],
						"tinh": province["ten"],
					},
					"old": [
						{
							"ma": w["ma"],
							"ten": w["ten"],
							"quan_huyen": w.get("quan_huyen_cu", ""),
							"tinh": w.get("tinh_cu", ""),
							"ghi_chu": w.get("ghi_chu", ""),
						}
						for w in district.get("xa_cu", [])
					],
				}
		return [new_to_old_map.get(code) for code in codes]

	frappe.throw(_("Invalid direction. Use 'old_to_new' or 'new_to_old'."))


@frappe.whitelist(allow_guest=True)
def search_address_by_text(ward_name, district_name="", province_name=""):
	"""
	Find an old ward by text names and return the converted new administrative address.
	Used to convert CCCD QR text address (e.g. "Xóm 1, Bình Nguyên, Bình Sơn, Quảng Ngãi")
	to the new 2025 administrative format.

	Returns: {old: {ten, quan_huyen, tinh}, new: {ma, ten, tinh_ma, tinh}} or None
	"""
	import unicodedata

	def norm(s):
		s = unicodedata.normalize("NFD", (s or "").strip().lower())
		return "".join(c for c in s if unicodedata.category(c) != "Mn").strip()

	wn = norm(ward_name)
	dn = norm(district_name)
	pn = norm(province_name)

	if not wn:
		return None

	data = _load_data()
	best = None
	best_score = 0

	for province in data:
		p = norm(province["ten"])
		if pn and pn not in p and p not in pn:
			continue
		for district in province.get("xa", []):
			for old_ward in district.get("xa_cu", []):
				w = norm(old_ward["ten"])
				d = norm(old_ward.get("quan_huyen_cu", ""))

				# Ward name must match
				if wn == w:
					score = 10
				elif wn in w or w in wn:
					score = 5
				else:
					continue

				# Bonus for district match
				if dn and (dn in d or d in dn):
					score += 5

				if score > best_score:
					best_score = score
					best = {
						"old": {
							"ten": old_ward["ten"],
							"quan_huyen": old_ward.get("quan_huyen_cu", ""),
							"tinh": old_ward.get("tinh_cu", province["ten"]),
						},
						"new": {
							"ma": district["ma"],
							"ten": district["ten"],
							"tinh_ma": province["ma"],
							"tinh": province["ten"],
						},
					}

	return best
