import frappe
from frappe.model.naming import make_autoname
from frappe.utils import getdate, nowdate


def _starts_with_material(w):
	return bool(w) and str(w).startswith("Material")


def _get_prefix(doc):
	"""Có kho bắt đầu 'Material' → PN (Nhập) / PX (Xuất) / PC (Chuyển) theo loại phiếu.
	Không có kho 'Material' → mặc định SE."""
	has_material = (
		_starts_with_material(doc.get("from_warehouse"))
		or _starts_with_material(doc.get("to_warehouse"))
		or any(
			_starts_with_material(r.s_warehouse) or _starts_with_material(r.t_warehouse)
			for r in (doc.items or [])
		)
	)
	if not has_material:
		return "SE"
	return {
		"Material Receipt": "PN",
		"Material Issue": "PX",
		"Material Transfer": "PC",
	}.get(doc.stock_entry_type, "SE")


def autoname(doc, method=None):
	"""Đặt tên Stock Entry theo {PN|PX|PC|SE}{YYYYMM}-{####}.

	- Prefix theo loại phiếu + có kho bắt đầu 'Material'.
	- Số thứ tự độc lập theo từng prefix + tháng, tự reset 0001 mỗi tháng
	  (period nằm trong key của series → tháng mới = series mới).
	- Gắn ở doc_event 'autoname' → chạy TRƯỚC naming_series nên ưu tiên cao nhất.
	- custom_no: chỉ điền khi đang trống → giữ nguyên custom_no nhập tay / từ
	  import Excel (cột gom nhóm), không ghi đè.
	"""
	prefix = _get_prefix(doc)
	period = getdate(doc.posting_date or nowdate()).strftime("%Y%m")
	doc.name = make_autoname(f"{prefix}{period}-.####")
	if not (doc.custom_no and str(doc.custom_no).strip()):
		doc.custom_no = doc.name
