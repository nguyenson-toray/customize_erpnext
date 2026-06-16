import frappe
from frappe import _


def validate_invoice_numbers(doc, method=None):
	"""Chặn Submit nếu có dòng Stock Entry Detail thiếu Invoice Number (No#).

	Đây là chốt chặn server-side để bắt cả các luồng submit KHÔNG đi qua form
	(bulk action ở list view, REST API, bench/console). Validate phía client
	(stock_entry.js) có thể bị bỏ qua ở các luồng này.

	Gắn vào doc_event "before_submit" => chỉ chạy khi Submit, không chặn lưu nháp
	hay các lần save giữa chừng (ví dụ bấm 'Add Batch Nos').

	Chỉ áp dụng cho dòng có kho (s_warehouse hoặc t_warehouse) bắt đầu bằng 'Material'.
	"""

	def is_material(w):
		return bool(w) and str(w).startswith("Material")

	missing_rows = [
		str(row.idx)
		for row in (doc.items or [])
		if (is_material(row.s_warehouse) or is_material(row.t_warehouse))
		and not (row.custom_invoice_number and str(row.custom_invoice_number).strip())
	]

	if missing_rows:
		frappe.throw(
			_("The following rows have empty Invoice Number: {0}").format(", ".join(missing_rows)),
			title=_("Missing Invoice Number"),
		)
