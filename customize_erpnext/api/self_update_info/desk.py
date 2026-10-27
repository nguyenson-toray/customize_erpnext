"""Form Desk của Employee Self Update Info: xem / sửa phiếu, Tình trạng hồ sơ, Generate PDF.

Tách nguyên văn từ self_update_info_api.py (27/10/2026) — mặt tiền đó re-export mọi tên."""

import json

import frappe
from frappe import _

from customize_erpnext.api.employee.cccd_expiry import DOB_FIELD as CCCD_DOB_FIELD
from customize_erpnext.api.employee.cccd_expiry import EXPIRY_FIELD as CCCD_EXPIRY_FIELD
from customize_erpnext.api.employee.cccd_expiry import ISSUE_FIELD as CCCD_ISSUE_FIELD

from .rules import (
	DOCUMENTS_KEY,
	INFO_DT,
	REMARKS_KEY,
)
from .config import (
	_address_pairs,
	_build_config,
	_employee_scalar_fields,
	_info_for_sign_config,
	_is_table,
	_setting_documents,
)
from .values import (
	_apply_cccd_expiry,
	_apply_depends,
	_clean_documents,
	_clean_table_value,
	_document_status,
	_employee_tables,
	_fmt,
	_fmt_date_vn,
	_normalize_text,
	_table_list,
	_table_rows_equal,
	_table_text,
	_validate_value,
)
from .access import (
	_require_hr,
)
from .receipt import (
	_hr_receipt_pdf,
	_receipt_base,
)


@frappe.whitelist()
def download_pdf_for_hr(name):
	"""Nút "Generate PDF" trên form Desk: cùng phiếu PDF như trang www, cho HR (không cần mã),
	chỉ in field tick "Info for Sign" — xem _hr_receipt_html."""
	_require_hr()
	doc = frappe.get_doc(INFO_DT, name)
	doc.check_permission("read")
	pdf = _hr_receipt_pdf(doc, _info_for_sign_config(_build_config()))

	frappe.response["filename"] = f"{_receipt_base(doc)}.pdf"
	frappe.response["filecontent"] = pdf
	frappe.response["type"] = "download"   # attachment → tải về ngay; không lưu gì trên server
	frappe.response["content_type"] = "application/pdf"


def apply_document_status(doc):
	"""Tình trạng hồ sơ của phiếu (document_status, missing_documents) tính lại từ data_json.
	Gọi ở EmployeeSelfUpdateInfo.validate — mọi đường lưu (trang www, Desk, API)."""
	try:
		saved = json.loads(doc.data_json or "{}")
	except ValueError:
		saved = {}
	status, missing = _document_status(_clean_documents(saved.get(DOCUMENTS_KEY)))
	doc.document_status = status
	doc.missing_documents = "\n".join(missing)


# HR sửa trực tiếp giá trị đã khai ngay trên bảng của form Desk (data_view), rồi lưu bằng
# nút Save chuẩn: JS ghép vào data_json, controller validate gọi validate_desk_edit().
_TEXT_EDITABLE_TYPES = {"Data", "Small Text", "Text", "Long Text", "Int", "Float", "Currency", "Phone"}


_MULTILINE_TYPES = {"Small Text", "Text", "Long Text"}


def _hr_editor(f):
	"""Loại ô HR được sửa trên Desk: text | textarea | select | date | province | ward | table — hoặc None.

	Field read_only trên trang (NV không được sửa) thì HR cũng không sửa ở đây.
	Check/Datetime/Time/Link chưa hỗ trợ.
	"""
	if f.get("read_only") or f.get("fieldname") == CCCD_EXPIRY_FIELD:
		return None  # ngày hết hạn CCCD tự tính (validate_desk_edit) — không cho sửa tay
	if _is_table(f):
		return "table"  # bảng nhỏ sửa được, kiểm bằng _clean_table_value
	widget = f.get("widget") or "Auto"
	if widget == "Address Province":
		return "province"
	if widget == "Address Ward":
		return "ward"
	if widget != "Auto":
		return None
	ft = f.get("fieldtype")
	if ft == "Select" and f.get("options"):
		return "select"
	if ft == "Date":
		return "date"  # data_json lưu ISO yyyy-mm-dd, giống <input type=date> của trang www
	if ft in _TEXT_EDITABLE_TYPES:
		return "textarea" if ft in _MULTILINE_TYPES else "text"
	return None


# Field trên doc chỉ trang www được ghi (NV ký) — Desk không được đổi.
_PORTAL_ONLY_FIELDS = ("commitment_confirmed", "signed_on", "signature")


def validate_desk_edit(doc):
	"""Chốt chặn khi data_json / chữ ký bị đổi NGOÀI trang www (form Desk, API, import).

	Gọi từ EmployeeSelfUpdateInfo.validate; save_form_data đặt flags.from_portal để bỏ qua.
	- chữ ký / cam kết: không ai được sửa ngoài trang www;
	- data_json: chỉ HR, không khi Synced, chỉ field có _hr_editor, giá trị phải hợp lệ
	  (Select ∈ options, định dạng như trang www, cặp tỉnh/xã đúng).
	"""
	before = doc.get_doc_before_save()
	if not before:
		return

	for fn in _PORTAL_ONLY_FIELDS:
		if doc.has_value_changed(fn):
			frappe.throw(_("{0} can only be changed on the self-update page.").format(_(doc.meta.get_label(fn))))

	if (before.data_json or "") == (doc.data_json or ""):
		return

	_require_hr()
	old = json.loads(before.data_json or "{}")
	new = json.loads(doc.data_json or "{}")
	# Hồ sơ nộp kèm: HR tick khi NV nộp bổ sung — được cả khi phiếu đã Synced (Sync không đọc khoá này).
	if DOCUMENTS_KEY in new:
		new[DOCUMENTS_KEY] = _clean_documents(new[DOCUMENTS_KEY])
	only_documents = all(old.get(k) == new.get(k) for k in set(old) | set(new) if k != DOCUMENTS_KEY)
	if before.status == "Synced" and not only_documents:
		frappe.throw(_("Already synced to Employee — submitted data can no longer be edited."))

	config = _build_config()
	fields = {f["fieldname"]: f for sec in config["sections"] for f in sec["fields"]}

	changed = set()
	errors = []
	for k in set(old) | set(new):
		ov, nv = old.get(k), new.get(k)
		if ov == nv or k == DOCUMENTS_KEY:
			continue
		f = fields.get(k)
		if not f or not _hr_editor(f):
			frappe.throw(_("Field {0} cannot be edited here.").format(f["label"] if f else k))
		if _is_table(f):
			rows, errs = _clean_table_value(f, nv, doc.employee)
			new[k] = rows
			errors += errs
			continue
		nv = _normalize_text(f, "" if nv is None else str(nv).strip())
		new[k] = nv
		if str(ov or "") == nv:
			continue
		changed.add(k)
		if _hr_editor(f) == "select" and nv and nv not in (f.get("options") or []):
			errors.append(_("{0}: {1} is not a valid option").format(f["label"], nv))
			continue
		if _hr_editor(f) == "date" and nv:
			try:
				nv = new[k] = frappe.utils.getdate(nv).isoformat()
			except Exception:
				errors.append(_("{0}: {1} is not a valid date").format(f["label"], nv))
				continue
		err = _validate_value(f, nv)
		if err:
			errors.append(err)

	# Ngày sinh / ngày cấp vừa sửa → ngày hết hạn CCCD tính lại (sau vòng kiểm field ở trên).
	if {CCCD_DOB_FIELD, CCCD_ISSUE_FIELD} & changed:
		_apply_cccd_expiry(config, new, doc.employee)

	# Field "chỉ hiện khi…": điều kiện không thoả → xoá trắng; thoả mà trống (vừa đổi) → báo thiếu.
	for fn, vis in _apply_depends(config, new, doc.employee).items():
		f = fields[fn]
		if vis and not str(new.get(fn) or "").strip() and ({fn, f["depends_on"]["field"]} & changed):
			errors.append(_("Please fill required fields: {0}").format(f["label"]))

	from customize_erpnext.api.vn_address_search.vn_address_search_api import get_address_error

	for prov, ward in _address_pairs(config):
		if not ({prov, ward} & changed):
			continue
		err = get_address_error(new.get(prov) if prov else "", new.get(ward))
		if err:
			errors.append(f"{fields[ward]['label']}: {err}")

	if errors:
		frappe.throw("<br>".join(errors), title=_("Invalid Data"))
	doc.data_json = json.dumps(new, ensure_ascii=False)


@frappe.whitelist()
def get_submission_view(name):
	"""Human-readable view of a submission for HR (instead of raw JSON).

	Returns {sections:[{label, rows:[{label, value, old, changed, custom}]}],
	remarks}. `changed` compares the submitted value with the current Employee
	value (only for real Employee fields).
	"""
	_require_hr()
	doc = frappe.get_doc(INFO_DT, name)
	saved = json.loads(doc.data_json or "{}")
	config = _build_config()

	real = _employee_scalar_fields(config)
	emp_vals = frappe.db.get_value("Employee", doc.employee, real, as_dict=True) or {} if real else {}
	emp_tables = _employee_tables(doc.employee, config)

	prov_of = {ward: prov for prov, ward in _address_pairs(config)}
	sections = []
	for sec in config["sections"]:
		rows = []
		for f in sec["fields"]:
			fn = f["fieldname"]
			if fn in ("employee", "name"):
				continue  # identity — already shown on the record header
			if _is_table(f):
				new_rows = _table_list(saved.get(fn))
				old_rows = emp_tables.get(fn) or []
				# Auto Fill Data + phiếu chưa có dòng → hiện dòng Employee (như phiếu PDF, _fill_from_employee).
				filled = bool(f.get("auto_fill") and not new_rows and old_rows)
				rows.append({
					"fieldname": fn,
					"label": f["label"],
					"value": new_rows,
					"in_saved": fn in saved and isinstance(saved.get(fn), list),
					"old": old_rows,
					"display": _table_text(f, old_rows if filled else new_rows),
					"old_display": _table_text(f, old_rows),
					"changed": fn in saved and not filled and not _table_rows_equal(f, new_rows, old_rows),
					"auto_filled": filled,
					"custom": False,
					"editor": _hr_editor(f),
					"columns": f["columns"],
					"required_if": f.get("required_if"),
					"max_rows": f["max_rows"],
				})
				continue
			new_v = saved.get(fn)
			new_s = "" if new_v is None else str(new_v)
			old_s = "" if f.get("custom") else _fmt(emp_vals.get(fn))
			# Auto Fill Data + phiếu chưa có giá trị → hiện giá trị Employee (như phiếu PDF, _fill_from_employee).
			filled = bool(f.get("auto_fill") and not f.get("custom") and not new_s.strip() and old_s.strip())
			if filled:
				new_s = old_s
			is_date = f.get("fieldtype") == "Date"
			rows.append({
				"fieldname": fn,
				"label": f["label"],
				"value": new_s,
				"old": old_s,
				# Hiển thị: field Date → dd/mm/yyyy ("value"/"old" giữ ISO cho ô sửa + so sánh).
				"display": _fmt_date_vn(new_s) if is_date and new_s else new_s,
				"old_display": _fmt_date_vn(old_s) if is_date and old_s else old_s,
				"changed": (not f.get("custom")) and fn in saved and new_s != old_s,
				"auto_filled": filled,
				"custom": bool(f.get("custom")),
				"editor": _hr_editor(f),
				"options": f.get("options") if _hr_editor(f) == "select" else None,
				"province_field": prov_of.get(fn),
			})
		if rows:
			sections.append({"label": sec["label"], "rows": rows})

	# Hồ sơ nộp kèm: bản chụp trong phiếu; phiếu cũ chưa có → danh sách Setting chưa tick (HR tick → tạo bản chụp).
	has_docs = DOCUMENTS_KEY in saved
	documents = _clean_documents(saved.get(DOCUMENTS_KEY)) if has_docs else _setting_documents()
	return {"sections": sections, "remarks": saved.get(REMARKS_KEY) or "", "documents": documents,
		"documents_key": DOCUMENTS_KEY}
