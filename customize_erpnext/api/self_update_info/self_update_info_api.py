"""
Employee Self Update Info API

A dynamic, field-picker driven self-service page. HR chooses any Employee field
(including custom fields) in `Employee Self Update Info Setting`; employees review
the current value of each field and update what changed. Submissions are stored as
JSON on `Employee Self Update Info` and exported to Excel — they are NOT synced back
to the Employee record.

Public (allow_guest=True):
    get_field_config        -> field list built from settings + Employee meta
    get_eligible_employees  -> employees configured in the setting
    get_form_data           -> current Employee values overlaid with any draft
    save_form_data          -> store submitted values as JSON

HR (login required):
    download_excel          -> xlsx with old (Employee) vs new (submitted) columns
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

SETTING_DT = "Employee Self Update Info Setting"
INFO_DT = "Employee Self Update Info"
# Reserved key inside data_json for the employee's free-text remarks.
REMARKS_KEY = "__remarks"

# Fieldtypes the dynamic renderer knows how to handle (v1: flat + Link + Text).
_ALLOWED_FIELDTYPES = {
	"Data", "Date", "Datetime", "Time", "Int", "Float", "Currency",
	"Select", "Check", "Small Text", "Text", "Long Text", "Link", "Phone",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_hr():
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)
	roles = frappe.get_roles()
	if not any(r in roles for r in ("HR Manager", "HR User", "System Manager")):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _get_setting():
	return frappe.get_cached_doc(SETTING_DT)


def _selected_rows(setting):
	# Only rows explicitly enabled (enable=1) are exposed on the public page.
	# This single chokepoint governs rendering, save validation and export.
	return [r for r in (setting.selected_fields or []) if r.employee_fieldname and r.enable]


def _build_config():
	"""Resolve the configured fields against the live Employee meta."""
	setting = _get_setting()
	rows = _selected_rows(setting)
	meta = frappe.get_meta("Employee")
	df_by_name = {df.fieldname: df for df in meta.fields}

	sections = {}
	order = []
	for row in rows:
		# Skip fields explicitly disabled via the "Enable" toggle.
		if not row.enable:
			continue
		if row.is_custom:
			# Free-form field that does NOT exist on Employee — defined entirely
			# by the row. Stored in the submission only.
			fieldtype = row.custom_fieldtype or "Data"
			if fieldtype not in _ALLOWED_FIELDTYPES:
				continue
			options = None
			if fieldtype == "Select" and row.custom_options:
				options = [o.strip() for o in row.custom_options.split("\n")]
			field = {
				"fieldname": row.employee_fieldname,
				"label": row.label_vi or row.employee_fieldname,
				"employee_label": row.label_vi or row.employee_fieldname,
				"fieldtype": fieldtype,
				"options": options,
				"required": bool(row.required),
				"read_only": bool(row.read_only),
				"widget": "Auto",
				"custom": True,
				**_validation_meta(row),
			}
		else:
			df = df_by_name.get(row.employee_fieldname)
			if not df or df.fieldtype not in _ALLOWED_FIELDTYPES:
				# Field removed/renamed on Employee, or type unsupported — skip.
				continue

			options = None
			if df.fieldtype == "Select" and df.options:
				options = [o for o in df.options.split("\n")]
			elif df.fieldtype == "Link":
				options = df.options  # the linked doctype name

			field = {
				"fieldname": df.fieldname,
				# UI label: prefer the Vietnamese label, fall back to the Employee
				# field's default label.
				"label": row.label_vi or df.label or df.fieldname,
				# Excel/import label: always the Employee field's own label so the
				# exported file can be re-imported into Employee (Data Import).
				"employee_label": df.label or df.fieldname,
				"fieldtype": df.fieldtype,
				"options": options,
				"required": bool(row.required),
				"read_only": bool(row.read_only),
				"widget": row.widget or "Auto",
				"custom": False,
				**_validation_meta(row),
			}

		sec = row.section_label or "General"
		if sec not in sections:
			sections[sec] = {"label": sec, "fields": []}
			order.append(sec)
		sections[sec]["fields"].append(field)

	return {"sections": [sections[s] for s in order]}


def _validation_meta(row):
	"""Validation attributes copied from a config row into the field dict."""
	return {
		"validation": row.validation or "",
		"min_length": int(row.min_length or 0),
		"max_length": int(row.max_length or 0),
		"regex": row.regex or "",
	}


# Built-in patterns for the preset validation types.
_VALIDATION_PATTERNS = {
	"Digits": (r"^\d+$", "chỉ gồm chữ số"),
	"Phone": (r"^0\d{9}$", "số điện thoại VN 10 số, bắt đầu bằng 0"),
	"Email": (r"^[^@\s]+@[^@\s]+\.[^@\s]+$", "email hợp lệ"),
	"CCCD": (r"^\d{12}$", "đúng 12 chữ số"),
	"CMND": (r"^\d{9}$", "đúng 9 chữ số"),
}


def _validate_value(field, value):
	"""Return an error message (str) if `value` fails the field's validation,
	else None. Empty values pass here (handled by the required check)."""
	import re

	val = "" if value is None else str(value).strip()
	if val == "":
		return None

	label = field.get("label") or field.get("fieldname")
	min_len = field.get("min_length") or 0
	max_len = field.get("max_length") or 0
	if min_len and len(val) < min_len:
		return _("{0}: tối thiểu {1} ký tự").format(label, min_len)
	if max_len and len(val) > max_len:
		return _("{0}: tối đa {1} ký tự").format(label, max_len)

	vtype = field.get("validation") or ""
	if not vtype:
		return None

	if vtype in ("Past", "Future"):
		try:
			dv = frappe.utils.getdate(val)
		except Exception:
			return None  # not a parseable date → don't block
		tv = frappe.utils.getdate(frappe.utils.today())
		if vtype == "Past" and dv > tv:
			return _("{0}: không được ở tương lai").format(label)
		if vtype == "Future" and dv < tv:
			return _("{0}: không được ở quá khứ").format(label)
		return None

	if vtype == "Regex":
		pattern = field.get("regex") or ""
		if not pattern:
			return None
		try:
			ok = re.match(pattern, val) is not None
		except re.error:
			return None  # invalid config regex → don't block the employee
		return None if ok else _("{0}: không đúng định dạng").format(label)

	spec = _VALIDATION_PATTERNS.get(vtype)
	if not spec:
		return None
	pattern, desc = spec
	if re.match(pattern, val) is None:
		return _("{0}: phải là {1}").format(label, desc)
	return None


def _config_fieldnames(config):
	return [f["fieldname"] for sec in config["sections"] for f in sec["fields"]]


def _eligible_ids(setting):
	ids = [r.employee for r in (setting.employees or []) if r.employee]
	return ids


def _dob_day(employee_id):
	"""Day-of-month of the employee's date of birth, zero-padded, e.g.
	1984-09-01 -> '01'."""
	dob = frappe.db.get_value("Employee", employee_id, "date_of_birth")
	if not dob:
		return None
	return str(dob)[-2:]  # 'YYYY-MM-DD' -> last 2 chars = 'DD'


def _num_eq(a, b):
	"""Compare two short numeric codes, tolerant of leading zeros."""
	try:
		return int(a) == int(b)
	except (TypeError, ValueError):
		return str(a).strip() == str(b).strip()


def _code_ok(setting, employee_id, code):
	"""True if the supplied code matches the DOB day or the bypass code."""
	code = (str(code or "")).strip()
	if not code:
		return False
	bypass = setting.bypass_code
	if bypass and _num_eq(code, bypass):
		return True
	day = _dob_day(employee_id)
	return bool(day) and _num_eq(code, day)


def _gate(setting, employee_id, code):
	"""Throw unless verification passes (no-op when validate_by_dob is off)."""
	if not setting.validate_by_dob:
		return
	if not _code_ok(setting, employee_id, code):
		frappe.throw(_("Verification failed. Please check the code."), frappe.ValidationError)


# ---------------------------------------------------------------------------
# Public APIs
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_field_config():
	"""Return the dynamic field configuration for the web form."""
	setting = _get_setting()
	config = _build_config()
	config["require_dob"] = bool(setting.validate_by_dob)
	return config


@frappe.whitelist(allow_guest=True)
def verify_employee(employee_id, code):
	"""Verify the DOB digits / bypass code before showing the form.

	Returns {valid: bool}. Always valid when validate_by_dob is off.
	"""
	if not employee_id:
		frappe.throw(_("Missing employee"))
	setting = _get_setting()
	if employee_id not in _eligible_ids(setting):
		frappe.throw(_("Employee not eligible for self update"), frappe.PermissionError)
	if not setting.validate_by_dob:
		return {"valid": True}
	return {"valid": _code_ok(setting, employee_id, code)}


@frappe.whitelist(allow_guest=True)
def get_eligible_employees():
	"""Return employees configured in the setting (optionally filtered by group)."""
	setting = _get_setting()
	ids = _eligible_ids(setting)
	if not ids:
		return []

	rows = frappe.get_all(
		"Employee",
		filters={"name": ["in", ids]},
		fields=["name as employee_id", "employee_name as display_name"],
		order_by="employee_name asc",
	)
	submitted = set(
		frappe.get_all(
			INFO_DT,
			filters={"employee": ["in", ids], "status": "Submitted"},
			pluck="employee",
		)
	)
	for r in rows:
		r["submitted"] = r["employee_id"] in submitted
	return rows


@frappe.whitelist(allow_guest=True)
def get_form_data(employee_id, code=None):
	"""Return current Employee values overlaid with any saved draft/submission.

	`code` = DOB digits / bypass code, required only when validate_by_dob is on.

	Returns:
	    {
	      original: {fieldname: value},   # live Employee values
	      values:   {fieldname: value},   # what to show (draft overrides original)
	      has_existing: bool,
	      status: "Draft"|"Submitted"|None,
	      employee_name: str,
	    }
	"""
	if not employee_id:
		frappe.throw(_("Missing employee"))

	setting = _get_setting()
	if employee_id not in _eligible_ids(setting):
		frappe.throw(_("Employee not eligible for self update"), frappe.PermissionError)
	_gate(setting, employee_id, code)

	config = _build_config()
	fieldnames = _config_fieldnames(config)
	# Only real Employee fields can be read from the Employee record; custom
	# fields have no source value.
	real_fields = [
		f["fieldname"]
		for sec in config["sections"]
		for f in sec["fields"]
		if not f.get("custom")
	]

	emp = frappe.db.get_value(
		"Employee", employee_id, ["employee_name"] + real_fields, as_dict=True
	) or {}
	employee_name = emp.get("employee_name")
	original = {fn: (emp.get(fn) if fn in real_fields else None) for fn in fieldnames}

	values = dict(original)
	status = None
	has_existing = False
	remarks = ""
	if frappe.db.exists(INFO_DT, employee_id):
		doc = frappe.get_doc(INFO_DT, employee_id)
		status = doc.status
		has_existing = True
		saved = json.loads(doc.data_json or "{}")
		remarks = saved.get(REMARKS_KEY, "")
		for fn in fieldnames:
			if fn in saved:
				values[fn] = saved[fn]

	return {
		"original": original,
		"values": values,
		"has_existing": has_existing,
		"status": status,
		"employee_name": employee_name,
		"remarks": remarks,
	}


@frappe.whitelist(allow_guest=True)
def save_form_data(employee_id, data, code=None):
	"""Store submitted values as JSON. Does NOT write back to Employee."""
	if not employee_id:
		frappe.throw(_("Missing employee"))

	setting = _get_setting()
	if employee_id not in _eligible_ids(setting):
		frappe.throw(_("Employee not eligible for self update"), frappe.PermissionError)
	_gate(setting, employee_id, code)

	if isinstance(data, str):
		data = json.loads(data or "{}")

	config = _build_config()
	allowed = set(_config_fieldnames(config))

	# Keep only configured, editable fields.
	editable = {
		f["fieldname"]
		for sec in config["sections"]
		for f in sec["fields"]
		if not f["read_only"]
	}
	clean = {k: v for k, v in (data or {}).items() if k in allowed and k in editable}

	# Free-text remarks (always allowed, stored under a reserved key).
	remarks = (data or {}).get(REMARKS_KEY)
	if remarks not in (None, ""):
		clean[REMARKS_KEY] = str(remarks).strip()

	# Validate required fields.
	missing = []
	for sec in config["sections"]:
		for f in sec["fields"]:
			if f["required"] and not f["read_only"]:
				val = clean.get(f["fieldname"])
				if val is None or str(val).strip() == "":
					missing.append(f["label"])
	if missing:
		frappe.throw(_("Please fill required fields: {0}").format(", ".join(missing)))

	# Format validation (mirrors the client; server is the source of truth).
	errors = []
	for sec in config["sections"]:
		for f in sec["fields"]:
			if f["read_only"]:
				continue
			err = _validate_value(f, clean.get(f["fieldname"]))
			if err:
				errors.append(err)
	if errors:
		frappe.throw("<br>".join(errors))

	employee_name = frappe.db.get_value("Employee", employee_id, "employee_name")

	if frappe.db.exists(INFO_DT, employee_id):
		doc = frappe.get_doc(INFO_DT, employee_id)
	else:
		doc = frappe.new_doc(INFO_DT)
		doc.employee = employee_id

	doc.employee_name = employee_name
	doc.data_json = json.dumps(clean, ensure_ascii=False)
	doc.status = "Submitted"
	doc.submitted_on = now_datetime()
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	return {"status": "success", "message": _("Your information has been submitted.")}


@frappe.whitelist(allow_guest=True)
def download_submission_pdf(employee_id, code=None):
	"""Return a PDF receipt of the employee's submitted information."""
	if not employee_id:
		frappe.throw(_("Missing employee"))
	setting = _get_setting()
	if employee_id not in _eligible_ids(setting):
		frappe.throw(_("Employee not eligible for self update"), frappe.PermissionError)
	_gate(setting, employee_id, code)

	if not frappe.db.exists(INFO_DT, employee_id):
		frappe.throw(_("No submission found for this employee."))

	doc = frappe.get_doc(INFO_DT, employee_id)
	saved = json.loads(doc.data_json or "{}")
	config = _build_config()

	html = _build_submission_html(doc, saved, config)
	from frappe.utils.pdf import get_pdf

	stamp = frappe.utils.format_datetime(now_datetime(), "yyyyMMdd_HHmm")
	name_part = (doc.employee_name or "").strip()
	frappe.response["filename"] = f"{employee_id} {name_part} {stamp}.pdf".strip()
	frappe.response["filecontent"] = get_pdf(html)
	frappe.response["type"] = "pdf"


def _logo_data_uri():
	"""Return the company logo as a base64 data URI (for the PDF), or ''."""
	import base64
	import os

	path = frappe.get_app_path("customize_erpnext", "public", "images", "logo_500.jpg")
	if not os.path.exists(path):
		return ""
	with open(path, "rb") as fh:
		b64 = base64.b64encode(fh.read()).decode()
	return f"data:image/jpeg;base64,{b64}"


def _build_submission_html(doc, saved, config):
	company = (
		frappe.defaults.get_global_default("company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or ""
	)
	logo = _logo_data_uri()
	submitted = frappe.utils.format_datetime(doc.submitted_on, "dd/MM/yyyy HH:mm") if doc.submitted_on else ""

	# The employee code is already shown in the header — skip any field that just
	# repeats it (e.g. a field mapped to `employee` / `name`).
	skip_fields = {"employee", "name"}
	rows = []
	for sec in config["sections"]:
		sec_rows = []
		for f in sec["fields"]:
			if f["fieldname"] in skip_fields:
				continue
			val = saved.get(f["fieldname"])
			val = "" if val is None else str(val)
			sec_rows.append(
				"<tr><td class='lbl'>{0}</td><td class='val'>{1}</td></tr>".format(
					frappe.utils.escape_html(f["label"]),
					frappe.utils.escape_html(val) or "&mdash;",
				)
			)
		if not sec_rows:
			continue  # drop a section that became empty
		rows.append(
			f'<tr><td colspan="2" class="sec">{frappe.utils.escape_html(sec["label"])}</td></tr>'
		)
		rows.extend(sec_rows)

	remarks = saved.get(REMARKS_KEY) or ""
	remarks_block = ""
	if remarks:
		remarks_block = (
			"<div class='remarks'><div class='rlabel'>Ghi chú thêm</div>"
			f"<div class='rtext'>{frappe.utils.escape_html(remarks)}</div></div>"
		)

	logo_img = f"<img src='{logo}' class='logo'/>" if logo else ""

	return f"""
<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  body{{font-family:'Helvetica Neue',Arial,sans-serif;color:#1f2733;font-size:12px;margin:0}}
  .head{{text-align:center;border-bottom:2px solid #1e3a8a;padding-bottom:10px;margin-bottom:14px}}
  .logo{{height:54px;margin-bottom:6px}}
  .company{{font-size:14px;font-weight:bold;color:#1e3a8a;text-transform:uppercase}}
  .title{{font-size:16px;font-weight:bold;margin-top:6px}}
  .meta{{margin:10px 0;font-size:12px}}
  .meta b{{display:inline-block;min-width:130px}}
  table{{width:100%;border-collapse:collapse;margin-top:6px}}
  td{{border:1px solid #d5dbe3;padding:6px 8px;vertical-align:top}}
  td.sec{{background:#eef2ff;font-weight:bold;color:#1e3a8a}}
  td.lbl{{width:40%;background:#f7f9fc;color:#475569}}
  td.val{{width:60%}}
  .remarks{{margin-top:14px;border:1px solid #d5dbe3;border-radius:6px;padding:10px}}
  .rlabel{{font-weight:bold;color:#1e3a8a;margin-bottom:4px}}
  .foot{{margin-top:18px;font-size:10px;color:#94a3b8;text-align:center}}
</style></head><body>
  <div class="head">
    {logo_img}
    <div class="company">{frappe.utils.escape_html(company)}</div>
    <div class="title">Phiếu cập nhật thông tin nhân viên</div>
  </div>
  <div class="meta">
    <div><b>Mã nhân viên:</b> {frappe.utils.escape_html(doc.employee)}</div>
    <div><b>Họ và tên:</b> {frappe.utils.escape_html(doc.employee_name or "")}</div>
    <div><b>Thời điểm gửi:</b> {submitted}</div>
  </div>
  <table>{''.join(rows)}</table>
  {remarks_block}
  <div class="foot">Phiếu này do nhân viên tự kê khai —  {frappe.utils.format_datetime(frappe.utils.now_datetime(), "dd/MM/yyyy HH:mm")}.</div>
</body></html>
"""


# ---------------------------------------------------------------------------
# HR APIs
# ---------------------------------------------------------------------------

@frappe.whitelist()
def download_excel(names=None):
	"""Export submissions to xlsx with two sheets — "New Data" (values submitted
	by employees) and "Old Data" (current Employee values).

	The file is designed to be re-imported into Employee via Data Import, so:
	  - the first column is "ID" (= Employee name → maps to the record on update),
	  - field column headers are the Employee field's own label (NOT label_vi),
	  - no Status / Submitted On columns (they would collide with Employee fields).

	"New Data" is the first sheet (the importable one); changed cells are
	highlighted. `names` = JSON list of Employee Self Update Info names, or None
	for all.
	"""
	_require_hr()
	import io

	from openpyxl import Workbook
	from openpyxl.styles import Font, PatternFill

	if isinstance(names, str):
		names = json.loads(names or "null")

	filters = {"name": ["in", names]} if names else {}
	records = frappe.get_all(
		INFO_DT,
		filters=filters,
		fields=["name", "employee", "employee_name", "data_json"],
		order_by="employee asc",
	)

	config = _build_config()
	fields = [f for sec in config["sections"] for f in sec["fields"]]
	# Headers use the Employee field label so the file can be imported back.
	# A trailing "Ghi chú" column holds the employee's free-text remarks.
	header = ["ID", "Employee Name"] + [f["employee_label"] for f in fields] + ["Ghi chú (nhân viên)"]
	real_fieldnames = [f["fieldname"] for f in fields if not f.get("custom")]

	bold = Font(bold=True)
	changed_fill = PatternFill(start_color="FFF3B0", end_color="FFF3B0", fill_type="solid")

	# Pre-compute old (Employee) and new (submitted) value maps per record.
	rows_data = []
	for rec in records:
		saved = json.loads(rec.get("data_json") or "{}")
		old_vals = frappe.db.get_value(
			"Employee", rec.employee, real_fieldnames, as_dict=True
		) or {} if real_fieldnames else {}
		rows_data.append({"rec": rec, "saved": saved, "old": old_vals})

	def _write_header(ws):
		ws.append(header)
		for cell in ws[1]:
			cell.font = bold

	wb = Workbook()

	# Sheet 1 — New Data (submitted values; this is the importable sheet).
	ws_new = wb.active
	ws_new.title = "New Data"
	_write_header(ws_new)
	for rd in rows_data:
		rec, saved, old_vals = rd["rec"], rd["saved"], rd["old"]
		row = [rec.employee, rec.employee_name]
		row += [_fmt(saved.get(f["fieldname"])) for f in fields]
		row.append(_fmt(saved.get(REMARKS_KEY)))
		ws_new.append(row)
		excel_row = ws_new.max_row
		for idx, f in enumerate(fields):
			fn = f["fieldname"]
			if fn in saved and _fmt(saved.get(fn)) != _fmt(old_vals.get(fn)):
				ws_new.cell(row=excel_row, column=3 + idx).fill = changed_fill

	# Sheet 2 — Old Data (current values on the Employee record, for reference).
	ws_old = wb.create_sheet("Old Data")
	_write_header(ws_old)
	for rd in rows_data:
		rec = rd["rec"]
		row = [rec.employee, rec.employee_name]
		row += [_fmt(rd["old"].get(f["fieldname"])) for f in fields]
		row.append("")  # no "old" remarks
		ws_old.append(row)

	buf = io.BytesIO()
	wb.save(buf)
	frappe.response["filename"] = "employee_self_update_info.xlsx"
	frappe.response["filecontent"] = buf.getvalue()
	frappe.response["type"] = "binary"


def _fmt(value):
	if value is None:
		return ""
	return str(value)
