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
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from customize_erpnext.api.employee.cccd_expiry import DOB_FIELD as CCCD_DOB_FIELD
from customize_erpnext.api.employee.cccd_expiry import EXPIRY_FIELD as CCCD_EXPIRY_FIELD
from customize_erpnext.api.employee.cccd_expiry import ISSUE_FIELD as CCCD_ISSUE_FIELD
from customize_erpnext.api.employee.cccd_expiry import cccd_expiry_iso

SETTING_DT = "Employee Self Update Info Setting"
INFO_DT = "Employee Self Update Info"
# Reserved key inside data_json for the employee's free-text remarks.
REMARKS_KEY = "__remarks"
# Chữ ký vẽ trên trang www: PNG data URL; canvas ~600x200 nét đen thường < 30 KB.
_SIGNATURE_PREFIX = "data:image/png;base64,"
_SIGNATURE_MAX_LEN = 400_000
# Câu cam kết — dùng chung cho trang www (qua get_field_config) và phiếu PDF/PNG.
COMMITMENT_TEXT = (
	"Tôi cam kết các thông tin đã khai ở trên là đúng sự thật và chịu trách nhiệm "
	"về thông tin đã cung cấp."
)


def _submit_device_info():
	"""Basic device/browser info of the submitting request: IP + User-Agent.

	Read-only audit only; no permission prompt, not synced to Employee.
	Returns '' when there is no HTTP request context (e.g. bench execute).
	"""
	try:
		ip = frappe.local.request_ip or ""
	except Exception:
		ip = ""
	def _h(name):
		try:
			return (frappe.get_request_header(name) or "").strip().strip('"')
		except Exception:
			return ""

	# User-Agent Client Hints (Chromium/Android; empty on Safari/iOS). Requires
	# the Accept-CH opt-in sent by the web page (see www/.../index.py).
	model = _h("Sec-CH-UA-Model")
	platform = " ".join(x for x in (_h("Sec-CH-UA-Platform"), _h("Sec-CH-UA-Platform-Version")) if x)

	parts = []
	if ip:
		parts.append(f"IP: {ip}")
	if model:
		parts.append(f"Model: {model}")
	if platform:
		parts.append(f"Platform: {platform}")
	return "\n".join(parts)

# Fieldtypes the dynamic renderer knows how to handle (v1: flat + Link + Text).
_ALLOWED_FIELDTYPES = {
	"Data", "Date", "Datetime", "Time", "Int", "Float", "Currency",
	"Select", "Check", "Small Text", "Text", "Long Text", "Link", "Phone",
	# 4 field Tỉnh/Xã của Employee là Autocomplete (api/vn_address_search). Thiếu dòng này
	# thì _build_config bỏ qua chúng im lặng → trang mất ô địa chỉ. Trang render theo widget
	# Address Province/Ward nên không cần biết fieldtype.
	"Autocomplete",
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
				"detail": row.detail or "",
				"placeholder": row.placeholder or "",
				"fieldtype": fieldtype,
				"options": options,
				"required": bool(row.required),
				"read_only": bool(row.read_only),
				"widget": "Auto",
				"custom": True,
				"auto_fill": bool(row.auto_fill_data),
				# Tick "Info for Sign" trong Setting → field có trong Excel Info for Sign.
				"info_for_sign": bool(row.get("info_for_sign")),
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
				# Optional guidance shown under the label on the page.
				"detail": row.detail or "",
				# Optional hint text inside the empty input.
				"placeholder": row.placeholder or "",
				"fieldtype": df.fieldtype,
				"options": options,
				"required": bool(row.required),
				"read_only": bool(row.read_only),
				"widget": row.widget or "Auto",
				"custom": False,
				"auto_fill": bool(row.auto_fill_data),
				# Tick "Info for Sign" trong Setting → field có trong Excel Info for Sign.
				"info_for_sign": bool(row.get("info_for_sign")),
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


# Tự chuẩn hoá chữ NV/HR nhập (16/10/2026). Cùng quy tắc với normalizeText() trên trang www — sửa
# một nơi thì sửa cả hai. Chỉ field chữ widget Auto, trừ Email.
_NORMALIZE_TYPES = {"Data", "Small Text", "Text", "Long Text"}
# Chèn dấu cách giữa CHỮ và SỐ khi phần chữ ≥ 2 ký tự và có chữ thường: "Xóm1" → "Xóm 1";
# giữ nguyên mã như "B2", "TDP1", "ABC123".
_WORD_DIGIT = re.compile(r"(?<![^\W\d_])([^\W\d_]{2,})(?=\d)")
_EMAIL_LIKE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _normalize_text(f, value):
	"""NFC, gộp khoảng trắng, chèn dấu cách chữ–số, viết hoa ký tự đầu (Person Name: hoa đầu mỗi từ).

	Không đụng: field không phải chữ, widget khác Auto, validation Email.
	"""
	import unicodedata

	if value is None or not isinstance(value, str):
		return value
	if f.get("fieldtype") not in _NORMALIZE_TYPES or (f.get("widget") or "Auto") != "Auto":
		return value
	# Email (theo Validation, hoặc giá trị trông như email dù field chưa gán Validation Email): chỉ bỏ khoảng trắng.
	if (f.get("validation") or "") == "Email" or _EMAIL_LIKE.match(value.strip()):
		return value.strip()
	v = unicodedata.normalize("NFC", value)
	multiline = f.get("fieldtype") != "Data"
	lines = v.split("\n") if multiline else [v]
	lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in lines]
	v = "\n".join(ln for ln in lines) if multiline else lines[0]
	v = v.strip()
	if (f.get("validation") or "") == "Person Name":
		# Hoa đầu mỗi từ, phần còn lại thường: "ĐOÀN THANH PHI" / "duong minh thang" → "Đoàn Thanh Phi".
		return " ".join(w[:1].upper() + w[1:].lower() for w in v.split(" ") if w)
	v = _WORD_DIGIT.sub(lambda m: m.group(1) + " " if any(c.islower() for c in m.group(1)) else m.group(1), v)
	return v[:1].upper() + v[1:]


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


def _apply_cccd_expiry(config, values, employee_id):
	"""Ghi ngày hết hạn CCCD vào `values` (dict data_json) = tính từ ngày sinh + ngày cấp.

	Ngày sinh / ngày cấp lấy trong `values` nếu có (NV vừa khai), không thì lấy Employee.
	Chỉ khi field ngày hết hạn có trên trang và không read_only. Thuật toán: api/employee/cccd_expiry.py.
	"""
	fields = {f["fieldname"]: f for sec in config["sections"] for f in sec["fields"]}
	f = fields.get(CCCD_EXPIRY_FIELD)
	if not f or f.get("read_only") or f.get("custom"):
		return
	emp = frappe.db.get_value("Employee", employee_id, [CCCD_DOB_FIELD, CCCD_ISSUE_FIELD], as_dict=True) or {}
	dob = values[CCCD_DOB_FIELD] if CCCD_DOB_FIELD in values else emp.get(CCCD_DOB_FIELD)
	issue = values[CCCD_ISSUE_FIELD] if CCCD_ISSUE_FIELD in values else emp.get(CCCD_ISSUE_FIELD)
	values[CCCD_EXPIRY_FIELD] = cccd_expiry_iso(dob, issue)


def _portal_address_errors(config, clean, employee_id):
	"""Lỗi cặp Tỉnh/Xã NV gửi từ trang www: tỉnh phải có trong danh mục, xã phải thuộc tỉnh.

	Trang dùng ô gõ-để-tìm (chỉ nhận giá trị trong danh sách) — đây là chốt chặn server cho mọi
	request gửi thẳng. Chỉ kiểm cặp có giá trị KHÁC Employee hiện tại: hồ sơ còn tên trước sáp
	nhập mà NV không đụng tới thì không bị chặn. Field read_only (không có trong `clean`) lấy
	giá trị Employee.
	"""
	pairs = _address_pairs(config)
	if not pairs:
		return []
	fields = {f["fieldname"]: f for sec in config["sections"] for f in sec["fields"]}
	real = [fn for pair in pairs for fn in pair if fn and not fields[fn].get("custom")]
	now = (frappe.db.get_value("Employee", employee_id, real, as_dict=True) or {}) if real else {}

	from customize_erpnext.api.vn_address_search.vn_address_search_api import get_address_error

	errors = []
	for prov, ward in pairs:
		keys = [k for k in (prov, ward) if k]
		value = {k: str(clean.get(k, now.get(k)) or "").strip() for k in keys}
		if not any(value[k] != str(now.get(k) or "").strip() for k in keys):
			continue
		err = get_address_error(value.get(prov, ""), value[ward])
		if err:
			errors.append(f"{fields[ward]['label']}: {err}")
	return errors


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


def _is_hr():
	"""True if the current session is a logged-in HR / System Manager."""
	if frappe.session.user in ("Guest", None):
		return False
	return any(r in frappe.get_roles() for r in ("HR Manager", "HR User", "System Manager"))


def _ensure_eligible(setting, employee_id):
	"""HR may edit ANY employee; employees themselves only those in the setting."""
	if _is_hr():
		if not frappe.db.exists("Employee", employee_id):
			frappe.throw(_("Employee not found"))
		return
	if employee_id not in _eligible_ids(setting):
		frappe.throw(_("Employee not eligible for self update"), frappe.PermissionError)


def _gate(setting, employee_id, code):
	"""Throw unless verification passes. When validate_by_dob is on, EVERYONE
	(including HR) must verify — HR uses the admin bypass_code to edit any
	employee. No-op only when validate_by_dob is off."""
	if not setting.validate_by_dob:
		return
	if not _code_ok(setting, employee_id, code):
		frappe.throw(_("Verification failed. Please check the code."), frappe.ValidationError)


def _already_submitted(employee_id):
	"""True once the employee has submitted the form at least once."""
	return bool(frappe.db.get_value(INFO_DT, employee_id, "submitted_on"))


def _unlock_ok(setting, unlock_code):
	"""True if the supplied unlock code matches bypass_code_for_unlock."""
	unlock_code = (str(unlock_code or "")).strip()
	if not unlock_code:
		return False
	return _num_eq(unlock_code, setting.bypass_code_for_unlock)


def _is_locked(setting, employee_id):
	"""True if the form is locked for this employee (submitted once + lock on)."""
	return bool(setting.get("lock_after_submit")) and _already_submitted(employee_id)


def _gate_edit(setting, employee_id, code, unlock_code=None):
	"""Gate for loading/saving the form. DOB check (as _gate) plus, when the
	form is locked after a first submission, BOTH the DOB digits AND the unlock
	code are required (employee must contact HR for the unlock code)."""
	_gate(setting, employee_id, code)
	if _is_locked(setting, employee_id):
		if not (_code_ok(setting, employee_id, code) and _unlock_ok(setting, unlock_code)):
			frappe.throw(
				_("This form is locked. Enter your date-of-birth digits and the unlock code from HR."),
				frappe.PermissionError,
			)


# --- Short-lived download token: lets the just-submitted session download the
# receipt (PDF/PNG) without the unlock code, while a cold visit stays locked. ---

def _dl_secret():
	return (frappe.local.conf.get("encryption_key") or frappe.local.conf.get("secret") or "csi").encode()


def _dl_windows():
	"""Current and previous 15-minute windows (token validity ~15–30 min)."""
	w = int(now_datetime().timestamp() // 900)
	return (w, w - 1)


def _make_download_token(employee_id):
	import hashlib
	import hmac

	msg = f"{employee_id}:{_dl_windows()[0]}".encode()
	return hmac.new(_dl_secret(), msg, hashlib.sha256).hexdigest()[:32]


def _download_token_ok(employee_id, token):
	import hashlib
	import hmac

	token = (str(token or "")).strip()
	if not token:
		return False
	for w in _dl_windows():
		good = hmac.new(_dl_secret(), f"{employee_id}:{w}".encode(), hashlib.sha256).hexdigest()[:32]
		if hmac.compare_digest(good, token):
			return True
	return False


def _gate_receipt(setting, employee_id, code, unlock_code=None, token=None):
	"""Gate for the PDF/PNG receipt. A valid fresh-submit token allows the
	download (same session that just submitted); otherwise the full edit gate
	applies so a locked form does not leak personal data on a later visit."""
	if _download_token_ok(employee_id, token):
		return
	_gate_edit(setting, employee_id, code, unlock_code)


# ---------------------------------------------------------------------------
# Public APIs
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_field_config():
	"""Return the dynamic field configuration for the web form."""
	setting = _get_setting()
	config = _build_config()
	config["require_dob"] = bool(setting.validate_by_dob)
	# Whether the page may keep a local draft (localStorage).
	config["allow_local_draft"] = bool(setting.allow_browser_local_storage)
	# In Zalo's in-app browser, force the user to open in the device browser
	# (PDF download is blocked inside the Zalo webview).
	config["force_device_browser"] = bool(setting.get("force_open_devices_browser"))
	# Receipt file type offered on the success screen: "PDF" (default) or "PNG".
	# PNG renders inline so it can be long-pressed to save inside the Zalo webview.
	config["save_file_type"] = setting.get("save_file_type") or "PDF"
	# Lock the form (and receipts) after the first submission. The secret
	# unlock code (bypass_code_for_unlock) is NEVER sent to the client.
	config["lock_after_submit"] = bool(setting.get("lock_after_submit"))
	config["commitment_text"] = COMMITMENT_TEXT
	return config


@frappe.whitelist(allow_guest=True)
def verify_employee(employee_id, code):
	"""Verify the DOB digits / bypass code before showing the form.

	Returns {valid: bool}. Always valid when validate_by_dob is off.
	"""
	if not employee_id:
		frappe.throw(_("Missing employee"))
	setting = _get_setting()
	_ensure_eligible(setting, employee_id)
	if not setting.validate_by_dob:
		return {"valid": True}
	return {"valid": _code_ok(setting, employee_id, code)}


@frappe.whitelist(allow_guest=True)
def get_access_info(employee_id):
	"""Report whether this employee's form is locked after a first submission.

	Returns {submitted, submitted_on (display), locked}. The unlock code is
	never exposed. Low sensitivity: same as the `submitted` flag already
	returned by get_eligible_employees.
	"""
	if not employee_id:
		frappe.throw(_("Missing employee"))
	setting = _get_setting()
	_ensure_eligible(setting, employee_id)
	submitted_on = frappe.db.get_value(INFO_DT, employee_id, "submitted_on")
	return {
		"submitted": bool(submitted_on),
		"submitted_on": frappe.utils.format_datetime(submitted_on, "dd/MM/yyyy HH:mm") if submitted_on else "",
		"locked": bool(setting.get("lock_after_submit")) and bool(submitted_on),
	}


@frappe.whitelist(allow_guest=True)
def unlock_access(employee_id, code, unlock_code):
	"""Pre-check the unlock: needs BOTH the DOB digits and the unlock code.

	Returns {valid}. Server-side enforcement still happens in get_form_data /
	save_form_data, so bypassing this cannot unlock the form.
	"""
	if not employee_id:
		frappe.throw(_("Missing employee"))
	setting = _get_setting()
	_ensure_eligible(setting, employee_id)
	valid = _code_ok(setting, employee_id, code) and _unlock_ok(setting, unlock_code)
	return {"valid": valid}


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
def get_form_data(employee_id, code=None, unlock_code=None):
	"""Return current Employee values overlaid with any saved draft/submission.

	`code` = DOB digits / bypass code, required only when validate_by_dob is on.
	`unlock_code` = required together with `code` when the form is locked after
	a first submission (lock_after_submit).

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
	_ensure_eligible(setting, employee_id)
	_gate_edit(setting, employee_id, code, unlock_code)

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

	# Fields with auto_fill = 0 must be re-entered every visit: never prefill
	# them from Employee or from a previous submission.
	no_fill = {
		f["fieldname"]
		for sec in config["sections"]
		for f in sec["fields"]
		if not f.get("auto_fill")
	}
	for fn in no_fill:
		values[fn] = None

	return {
		"original": original,
		"values": values,
		"has_existing": has_existing,
		"status": status,
		"employee_name": employee_name,
		"remarks": remarks,
		# HR sửa qua ?emp= → trang không bắt buộc cam kết + chữ ký.
		"is_hr": _is_hr(),
	}


@frappe.whitelist(allow_guest=True)
def save_form_data(employee_id, data, code=None, unlock_code=None, commitment=None, signature=None):
	"""Store submitted values as JSON. Does NOT write back to Employee.

	`commitment` (1/0) + `signature` (data URL PNG từ ô vẽ chữ ký): bắt buộc với NV;
	HR sửa qua ?emp= thì không bắt buộc — không gửi chữ ký thì giữ chữ ký cũ.
	"""
	if not employee_id:
		frappe.throw(_("Missing employee"))

	is_hr = _is_hr()
	committed = frappe.utils.cint(commitment) == 1
	signature = (signature or "").strip()
	if signature:
		if not signature.startswith(_SIGNATURE_PREFIX) or len(signature) > _SIGNATURE_MAX_LEN:
			frappe.throw(_("Invalid signature image"))
	if not is_hr:
		if not committed:
			frappe.throw("Vui lòng tick ô cam kết thông tin khai đúng sự thật.")
		if not signature:
			frappe.throw("Vui lòng ký tên vào ô chữ ký.")

	setting = _get_setting()
	_ensure_eligible(setting, employee_id)
	_gate_edit(setting, employee_id, code, unlock_code)

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
	# Ô "Ghi chú thêm" gắn cứng (__remarks) đã bỏ 16/10/2026 — cần ghi chú thì thêm custom field trong Setting.

	# Tự chuẩn hoá chữ (NFC, khoảng trắng, chữ–số, viết hoa ký tự đầu / Person Name).
	fields_by_name = {f["fieldname"]: f for sec in config["sections"] for f in sec["fields"]}
	for k in list(clean):
		if k in fields_by_name:
			clean[k] = _normalize_text(fields_by_name[k], clean[k])

	# Ngày hết hạn CCCD: không nhận giá trị gửi lên, luôn tự tính.
	_apply_cccd_expiry(config, clean, employee_id)

	# Validate required fields.
	missing = []
	for sec in config["sections"]:
		for f in sec["fields"]:
			if f["required"] and not f["read_only"] and f["fieldname"] != CCCD_EXPIRY_FIELD:
				val = clean.get(f["fieldname"])
				if val is None or str(val).strip() == "":
					missing.append(f["label"])
	if missing:
		frappe.throw(_("Please fill required fields: {0}").format(", ".join(missing)))

	# Format validation (mirrors the client; server is the source of truth).
	errors = []
	for sec in config["sections"]:
		for f in sec["fields"]:
			if f["read_only"] or f["fieldname"] == CCCD_EXPIRY_FIELD:
				continue  # ngày hết hạn tự tính: thẻ đã quá hạn thì vẫn ghi đúng, không chặn "Future"
			err = _validate_value(f, clean.get(f["fieldname"]))
			if err:
				errors.append(err)
	errors += _portal_address_errors(config, clean, employee_id)
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
	# Append device info each submit (keep history) instead of replacing.
	info = _submit_device_info()
	if info:
		stamp = frappe.utils.format_datetime(now_datetime(), "yyyy-MM-dd HH:mm")
		entry = f"[{stamp}]\n{info}"
		prev = (doc.device_info or "").strip()
		doc.device_info = (prev + "\n\n" + entry) if prev else entry
	if signature:
		doc.signature = signature
		doc.commitment_confirmed = 1 if committed else 0
		doc.signed_on = now_datetime()
	doc.flags.from_portal = True
	doc.save(ignore_permissions=True)
	frappe.db.commit()

	# Short-lived token so THIS session can download the receipt right away,
	# even though the form is now locked for later (cold) visits.
	return {
		"status": "success",
		"message": _("Your information has been submitted."),
		"download_token": _make_download_token(employee_id),
	}


@frappe.whitelist(allow_guest=True)
def download_submission_pdf(employee_id, code=None, unlock_code=None, token=None):
	"""Return a PDF receipt of the employee's submitted information."""
	html, base = _load_submission_receipt(employee_id, code, unlock_code, token)
	from frappe.utils.pdf import get_pdf

	frappe.response["filename"] = f"{base}.pdf"
	frappe.response["filecontent"] = get_pdf(html)
	frappe.response["type"] = "pdf"


@frappe.whitelist()
def download_pdf_for_hr(name):
	"""Nút "Generate PDF" trên form Desk: cùng phiếu PDF như trang www, cho HR (không cần mã)."""
	_require_hr()
	doc = frappe.get_doc(INFO_DT, name)
	doc.check_permission("read")
	html = _build_submission_html(doc, json.loads(doc.data_json or "{}"), _build_config())
	from frappe.utils.pdf import get_pdf

	frappe.response["filename"] = f"{_receipt_base(doc)}.pdf"
	frappe.response["filecontent"] = get_pdf(html)
	frappe.response["type"] = "download"   # attachment → tải về ngay; không lưu gì trên server
	frappe.response["content_type"] = "application/pdf"


def _receipt_base(doc):
	"""Tên file phiếu: "<mã NV> <họ tên> <yyyyMMdd_HHmm>"."""
	stamp = frappe.utils.format_datetime(now_datetime(), "yyyyMMdd_HHmm")
	return f"{doc.employee} {(doc.employee_name or '').strip()} {stamp}".strip()


@frappe.whitelist(allow_guest=True)
def download_submission_image(employee_id, code=None, unlock_code=None, token=None):
	"""Return a PNG image of the employee's submitted information as a file download."""
	html, base = _load_submission_receipt(employee_id, code, unlock_code, token)
	frappe.response["filename"] = f"{base}.png"
	frappe.response["filecontent"] = _html_to_png(html)
	frappe.response["type"] = "download"
	frappe.response["content_type"] = "image/png"


def _load_submission_receipt(employee_id, code, unlock_code=None, token=None):
	"""Shared gate + HTML build for the PDF/PNG receipt. Returns (html, base_filename)."""
	if not employee_id:
		frappe.throw(_("Missing employee"))
	setting = _get_setting()
	_ensure_eligible(setting, employee_id)
	_gate_receipt(setting, employee_id, code, unlock_code, token)

	if not frappe.db.exists(INFO_DT, employee_id):
		frappe.throw(_("No submission found for this employee."))

	doc = frappe.get_doc(INFO_DT, employee_id)
	saved = json.loads(doc.data_json or "{}")
	config = _build_config()
	html = _build_submission_html(doc, saved, config)
	return html, _receipt_base(doc)


def _html_to_png(html):
	"""Render HTML to a PNG (bytes) via wkhtmltoimage (stdin → stdout)."""
	import subprocess

	cmd = [
		"wkhtmltoimage",
		"--format", "png",
		"--encoding", "utf-8",
		"--quality", "94",
		"--width", "820",
		"--enable-local-file-access",
		"--quiet",
		"-", "-",
	]
	try:
		proc = subprocess.run(
			cmd, input=html.encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE
		)
	except FileNotFoundError:
		frappe.throw(_("wkhtmltoimage is not installed on the server."))
	if not proc.stdout:
		frappe.log_error(proc.stderr.decode("utf-8", "ignore"), "wkhtmltoimage failed")
		frappe.throw(_("Could not render the image."))

	# wkhtmltoimage emits a large RGBA PNG. Flatten onto white + optimize to
	# keep the file small enough to save comfortably on a phone.
	try:
		import io

		from PIL import Image

		img = Image.open(io.BytesIO(proc.stdout))
		if img.mode in ("RGBA", "LA", "P"):
			bg = Image.new("RGB", img.size, "#FFFFFF")
			img = img.convert("RGBA")
			bg.paste(img, mask=img.split()[-1])
			img = bg
		else:
			img = img.convert("RGB")
		out = io.BytesIO()
		img.save(out, format="PNG", optimize=True)
		return out.getvalue()
	except Exception:
		return proc.stdout


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


def _strip_section_no(label):
	"""Drop a leading ordinal prefix from a section name for the receipt.

	e.g. "1. Thông tin chung" / "2) Trình độ" / "3 - CCCD" -> "Thông tin chung"…
	so the PDF/PNG shows the plain Section name without the numbering HR typed.
	"""
	import re

	cleaned = re.sub(r"^\s*\d+\s*[.)\-–—]\s*", "", label or "").strip()
	return cleaned or (label or "")


def _fmt_date_vn(value):
	"""'2001-07-29' → '29/07/2001'; giá trị không phải ngày → giữ nguyên."""
	try:
		return frappe.utils.getdate(value).strftime("%d/%m/%Y")
	except Exception:
		return str(value)


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
			if f.get("fieldtype") == "Date" and val:
				val = _fmt_date_vn(val)  # ngày trên phiếu: dd/mm/yyyy
			sec_rows.append(
				"<tr><td class='lbl'>{0}</td><td class='val'>{1}</td></tr>".format(
					frappe.utils.escape_html(f["label"]),
					frappe.utils.escape_html(val) or "&mdash;",
				)
			)
		if not sec_rows:
			continue  # drop a section that became empty
		rows.append(
			f'<tr><td colspan="2" class="sec">{frappe.utils.escape_html(_strip_section_no(sec["label"]))}</td></tr>'
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
	# Đã ký → "Ký lúc" ở khung chữ ký là mốc thời gian; chỉ phiếu cũ chưa ký mới hiện giờ gửi.
	submitted_line = "" if doc.get("signed_on") else f"<div><b>Thời điểm gửi:</b> {submitted}</div>"

	# Cam kết + chữ ký (vẽ trên trang www). Chỉ nhận đúng data URL PNG đã kiểm ở save_form_data.
	sign_block = ""
	sig = doc.get("signature") or ""
	if doc.get("commitment_confirmed") or sig:
		signed = frappe.utils.format_datetime(doc.signed_on, "dd/MM/yyyy HH:mm") if doc.get("signed_on") else ""
		sig_img = f"<img src='{sig}' class='sig'/>" if sig.startswith(_SIGNATURE_PREFIX) else ""
		sign_block = (
			"<div class='commit'>"
			+ ("<b>Cam kết:</b> " if doc.get("commitment_confirmed") else "")
			+ frappe.utils.escape_html(COMMITMENT_TEXT)
			+ "</div><div class='signbox'><div class='slabel'>Người khai ký tên</div>"
			+ sig_img
			+ f"<div class='sname'>{frappe.utils.escape_html(doc.employee_name or '')}</div>"
			+ (f"<div class='sdate'>Ký lúc: {signed}</div>" if signed else "")
			+ "</div>"
		)

	return f"""
<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  /* Lề trang PDF: get_pdf đọc từ rule .print-format (khai ở options của get_pdf sẽ bị ghi đè).
     Lề 15mm cả 4 phía (user chọn 15/10/2026); phần còn lại thu gọn để phiếu + chữ ký vừa 1 trang A4. */
  .print-format{{margin-top:15mm;margin-bottom:15mm;margin-left:15mm;margin-right:15mm}}
  body{{font-family:'Helvetica Neue',Arial,sans-serif;color:#1f2733;font-size:11px;line-height:1.3;margin:0}}
  .head{{text-align:left;border-bottom:2px solid #1e3a8a;padding-bottom:6px;margin-bottom:8px;overflow:hidden}}
  .logo{{height:30px;float:left;margin:1px 10px 0 0}}
  .company{{font-size:11px;font-weight:bold;color:#1e3a8a;text-transform:uppercase}}
  .title{{font-size:17px;font-weight:bold;color:#1e3a8a;margin-top:1px}}
  .meta{{margin:6px 0;font-size:11px}}
  .meta b{{display:inline-block;min-width:110px}}
  table{{width:100%;border-collapse:collapse;margin-top:4px}}
  tr{{page-break-inside:avoid}}
  td{{border:1px solid #d5dbe3;padding:3px 7px;vertical-align:top}}
  td.sec{{background:#eef2ff;font-weight:bold;color:#1e3a8a;padding:3px 7px}}
  td.lbl{{width:40%;color:#475569}}  /* chỉ dòng tiêu đề Section (td.sec) có nền */
  td.val{{width:60%}}
  .remarks{{margin-top:8px;border:1px solid #d5dbe3;border-radius:5px;padding:6px 8px}}
  .rlabel{{font-weight:bold;color:#1e3a8a;margin-bottom:2px}}
  .signoff{{page-break-inside:avoid}}
  .commit{{margin-top:8px;font-style:italic}}
  .signbox{{margin:4px 0 0 auto;width:240px;text-align:center}}
  .slabel{{font-weight:bold}}
  .sig{{max-width:220px;max-height:60px;margin:3px 0}}
  .sname{{font-weight:bold}}
  .sdate{{font-size:10px;color:#64748b}}
</style></head><body>
  <div class="head">
    {logo_img}
    <div class="company">{frappe.utils.escape_html(company)}</div>
    <div class="title">PHIẾU CẬP NHẬT THÔNG TIN NHÂN VIÊN</div>
  </div>
  <div class="meta">
    <div><b>Mã nhân viên:</b> {frappe.utils.escape_html(doc.employee)}</div>
    <div><b>Họ và tên:</b> {frappe.utils.escape_html(doc.employee_name or "")}</div>
    {submitted_line}
  </div>
  <table>{''.join(rows)}</table>
  {remarks_block}
  <div class="signoff">{sign_block}</div>
</body></html>
"""


# ---------------------------------------------------------------------------
# HR APIs
# ---------------------------------------------------------------------------

@frappe.whitelist()
def download_excel(names=None, export_type="All Info", file_format="Excel"):
	"""Export submissions to xlsx with two sheets — "New Data" (values submitted
	by employees) and "Old Data" (current Employee values).

	The file is designed to be re-imported into Employee via Data Import, so:
	  - the first column is "ID" (= Employee name → maps to the record on update),
	  - field column headers are the Employee field's own label (NOT label_vi),
	  - no Status / Submitted On columns (they would collide with Employee fields).

	"New Data" is the first sheet (the importable one); changed cells are
	highlighted. `names` = JSON list of Employee Self Update Info names, or None
	for all.

	`export_type="Info for Sign"` → file riêng, xem _download_info_for_sign;
	`file_format="PDF"` (chỉ Info for Sign) → _download_info_for_sign_pdf.
	"""
	_require_hr()
	if export_type == "Info for Sign":
		if file_format == "PDF":
			return _download_info_for_sign_pdf(names)
		return _download_info_for_sign(names)
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


# ---------------------------------------------------------------------------
# Excel "Info for Sign" — danh sách in ra cho NV ký xác nhận
# ---------------------------------------------------------------------------

def _info_for_sign_wanted(config):
	"""Fieldname được tick "Info for Sign" trong Setting (selected_fields)."""
	return {f["fieldname"] for sec in config["sections"] for f in sec["fields"] if f.get("info_for_sign")}


@frappe.whitelist()
def get_info_for_sign_fields():
	"""Các dòng sẽ có trong Info for Sign (để dialog Excel hiện cho HR biết): [nhãn].

	Theo cờ "Info for Sign" của từng field trong Setting; địa chỉ / liên hệ khẩn cấp đã gộp.
	"""
	_require_hr()
	config = _build_config()
	wanted = _info_for_sign_wanted(config)
	return [label for label, _fs, _k in _sign_items(config, wanted)] if wanted else []


def _sign_labels(config):
	"""{fieldname: nhãn tiếng Việt} cho Info for Sign.

	Nhãn trùng giữa các Section (Tỉnh / Xã / Chi tiết… của "Địa chỉ thường trú" và
	"Địa chỉ hiện tại") → ghép tên Section: "Địa chỉ thường trú - Tỉnh".
	"""
	from collections import Counter

	items = [
		(sec["label"], f["fieldname"], _(f["label"], lang="vi"))
		for sec in config["sections"]
		for f in sec["fields"]
		if f["fieldname"] not in ("employee", "name")
	]
	dup = Counter(label for _sec, _fn, label in items)
	return {
		fn: (f"{_strip_section_no(sec)} - {label}" if dup[label] > 1 else label)
		for sec, fn, label in items
	}


# Thông tin liên hệ khẩn cấp (field chuẩn Employee) — Info for Sign ghép thành 1 dòng.
_EMERGENCY_FIELDS = ("person_to_be_contacted", "relation", "emergency_phone_number")
# Số CCCD + ngày cấp → 1 dòng "CCCD": "<số>, cấp ngày dd/mm/yyyy" (ngày hết hạn vẫn dòng riêng).
_CCCD_FIELDS = ("custom_id_card_no", CCCD_ISSUE_FIELD)
# Nhóm field gộp thành 1 dòng: kind → (fieldnames, nhãn dòng). Dòng đặt ở chỗ field đầu tiên của nhóm.
_SIGN_GROUPS = {
	"emergency": (_EMERGENCY_FIELDS, "Liên hệ khẩn cấp"),
	"cccd": (_CCCD_FIELDS, "CCCD"),
}


def _sign_items(config, wanted):
	"""Các dòng của Info for Sign theo thứ tự config: [(nhãn, [field], kiểu)].

	- Section có ô tỉnh (widget Address Province) → 1 dòng "address" mang tên Section,
	  gồm mọi field đã chọn của Section đó;
	- nhóm trong _SIGN_GROUPS (liên hệ khẩn cấp, số CCCD + ngày cấp) → 1 dòng, đặt ở chỗ field đầu tiên;
	- còn lại mỗi field 1 dòng.
	`wanted` = set fieldname được chọn, None = tất cả.
	"""
	labels = _sign_labels(config)
	pick = lambda f: f["fieldname"] not in ("employee", "name") and (wanted is None or f["fieldname"] in wanted)
	group_of = {fn: kind for kind, (fns, _l) in _SIGN_GROUPS.items() for fn in fns}
	members = {
		kind: [f for sec in config["sections"] for f in sec["fields"] if pick(f) and f["fieldname"] in fns]
		for kind, (fns, _l) in _SIGN_GROUPS.items()
	}
	items = []
	for sec in config["sections"]:
		fs = [f for f in sec["fields"] if pick(f)]
		if not fs:
			continue
		if any(f.get("widget") == "Address Province" for f in sec["fields"]):
			items.append((_strip_section_no(sec["label"]), fs, "address"))
			continue
		for f in fs:
			kind = group_of.get(f["fieldname"])
			if kind:
				if f is members[kind][0]:
					items.append((_SIGN_GROUPS[kind][1], members[kind], kind))
				continue
			items.append((labels[f["fieldname"]], [f], "field"))
	return items


def _sign_join(kind, parts):
	"""Ghép giá trị của 1 dòng. parts = [(field, giá trị đã định dạng)] theo thứ tự config."""
	if kind == "address":
		# Như custom_*_address_full: chi tiết (thôn/số nhà) → xã → tỉnh.
		rank = {"Address Ward": 1, "Address Province": 2}
		ordered = sorted(parts, key=lambda p: rank.get(p[0].get("widget"), 0))
		return ", ".join(v for _f, v in ordered if v)
	if kind == "emergency":
		by = {f["fieldname"]: v for f, v in parts}
		name, rel, phone = by.get("person_to_be_contacted"), by.get("relation"), by.get("emergency_phone_number")
		head = " ".join(x for x in (name, f"({rel})" if rel else "") if x)
		return " - ".join(x for x in (head, phone) if x)
	if kind == "cccd":
		by = {f["fieldname"]: v for f, v in parts}
		no, issued = by.get("custom_id_card_no"), by.get(CCCD_ISSUE_FIELD)  # ngày đã dd/mm/yyyy (_sign_value_vi)
		return ", ".join(x for x in (no, f"cấp ngày {issued}" if issued else "") if x)
	return parts[0][1] if parts else ""


def _sign_value_vi(f, value):
	"""Giá trị hiển thị tiếng Việt: Select dịch theo bảng vi, Date dd/mm/yyyy, Check Có/Không."""
	if value in (None, ""):
		return ""
	ft = f.get("fieldtype")
	if ft == "Select":
		return _(str(value), lang="vi")
	if ft == "Date":
		try:
			return frappe.utils.getdate(value).strftime("%d/%m/%Y")
		except Exception:
			return str(value)
	if ft == "Check":
		return "Có" if frappe.utils.cint(value) else "Không"
	return str(value).strip()


INFO_FOR_SIGN_HEADER = ("STT", "Nhân viên", "Thông tin", "Nội dung", "Ghi chú", "Chữ ký")
INFO_FOR_SIGN_TITLE = "DANH SÁCH XÁC NHẬN THÔNG TIN NHÂN VIÊN"


def _info_for_sign_people(names):
	"""Dữ liệu chung cho Info for Sign (Excel + PDF): ([(mã NV, họ tên, [(nhãn, nội dung)])], tên công ty).

	Nội dung = thông tin mới (NV khai), mới trống → Employee; cả hai trống → vẫn có dòng, nội dung "".
	"""
	if isinstance(names, str):
		names = json.loads(names or "null")
	config = _build_config()
	wanted = _info_for_sign_wanted(config)
	if not wanted:
		frappe.throw(
			_("No field is ticked \"Info for Sign\" in Employee Self Update Info Setting."),
			title=_("Info for Sign"),
		)
	items = _sign_items(config, wanted)
	real = [f["fieldname"] for _l, fs, _k in items for f in fs if not f.get("custom")]

	filters = {"name": ["in", names]} if names else {}
	records = frappe.get_all(
		INFO_DT, filters=filters, fields=["name", "employee", "employee_name", "data_json"], order_by="employee asc"
	)
	people = []
	for rec in records:
		saved = json.loads(rec.data_json or "{}")
		old = (frappe.db.get_value("Employee", rec.employee, real, as_dict=True) or {}) if real else {}
		lines = []
		for label, fs, kind in items:
			parts = []
			for f in fs:
				fn = f["fieldname"]
				new_s = _fmt(saved.get(fn)).strip()
				old_s = "" if f.get("custom") else _fmt(old.get(fn)).strip()
				parts.append((f, _sign_value_vi(f, new_s or old_s)))
			# Chưa có dữ liệu → VẪN in dòng, Nội dung để trống cho NV tự ghi tay bổ sung.
			lines.append((label, _sign_join(kind, parts)))
		people.append((rec.employee, rec.employee_name or "", lines))
	company = (
		frappe.defaults.get_global_default("company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or ""
	)
	return people, company


# PDF Info for Sign: A4 ngang, lề trên/dưới 10mm; trang 1 = tiêu đề + 4 NV, các trang sau 5 NV;
# mỗi trang là 1 bảng riêng → tên cột lặp lại; chân trang "Trang x/y". Cỡ chữ chung = lớn nhất mà
# không trang nào tràn (tìm nhị phân, dựng thử + đếm trang).
INFO_FOR_SIGN_PDF_FIRST = 4
INFO_FOR_SIGN_PDF_PER_PAGE = 5
# Tick quá nhiều mục (vd 17 dòng/NV) thì 4/5 NV không vừa ở cỡ chữ đọc được → lùi bố cục.
_SIGN_PDF_FALLBACK = ((3, 4), (2, 3), (1, 2), (1, 1))
_SIGN_PDF_MIN_FONT = 6.0   # px — dưới mức này coi như không đọc được, lùi bố cục
_SIGN_PDF_MAX_FONT = 16.0  # px — trần cỡ chữ; trang còn trống thì chữ lớn dần tới khi lấp đầy
_SIGN_PDF_COL_WIDTHS = (3.5, 13, 15.5, 38, 15.5, 14.5)   # % — cùng tỉ lệ cột Excel
_SIGN_PDF_SAMPLE_PAGES = 6   # số trang "nặng" nhất (+ trang 1) dùng để dò cỡ chữ
INFO_FOR_SIGN_PDF_MAX_RECORDS = 100   # PDF tối đa 100 phiếu/lần (user 16/10/2026); Excel không giới hạn


def _info_for_sign_pdf_pages(people, first=INFO_FOR_SIGN_PDF_FIRST, per=INFO_FOR_SIGN_PDF_PER_PAGE):
	rest = people[first:]
	return [people[:first]] + [rest[i:i + per] for i in range(0, len(rest), per)]


def _info_for_sign_pdf_html(pages, company, font_px):
	esc = frappe.utils.escape_html
	head = "".join(f"<th style='width:{w}%'>{esc(h)}</th>" for h, w in zip(INFO_FOR_SIGN_HEADER, _SIGN_PDF_COL_WIDTHS))
	today = frappe.utils.now_datetime().strftime("%d/%m/%Y")
	stt = 0
	blocks = []
	for i, page in enumerate(pages):
		body = []
		for emp, emp_name, lines in page:
			stt += 1
			n = len(lines) or 1
			who = esc(emp) + (f"<br>{esc(emp_name)}" if emp_name else "")
			for j, (label, value) in enumerate(lines or [("", "")]):
				cells = ""
				if j == 0:
					cells += f"<td class='c' rowspan='{n}'>{stt}</td><td class='c' rowspan='{n}'>{who}</td>"
				cells += f"<td>{esc(label)}</td><td>{esc(value)}</td>"
				if j == 0:
					cells += f"<td rowspan='{n}'></td><td rowspan='{n}'></td>"
				body.append(f"<tr class='{'first' if j == 0 else ''}'>{cells}</tr>")
		title = ""
		if i == 0:
			title = (
				f"<div class='co'>{esc(company.upper())}</div><div class='ti'>{esc(INFO_FOR_SIGN_TITLE)}</div>"
				f"<div class='dt'>Ngày: {today}</div>"
			)
		brk = " style='page-break-after:always'" if i < len(pages) - 1 else ""
		blocks.append(f"<div class='pg'{brk}>{title}<table><thead><tr>{head}</tr></thead><tbody>{''.join(body)}</tbody></table></div>")
	f = font_px
	return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
  .print-format{{margin-top:10mm;margin-bottom:10mm;margin-left:15mm;margin-right:15mm}}
  body{{font-family:Arial,'Helvetica Neue',sans-serif;color:#111;margin:0;font-size:{f}px}}
  .co{{text-align:center;font-weight:bold;font-size:{f + 1}px}}
  .ti{{text-align:center;font-weight:bold;font-size:{f + 5}px;margin:2px 0}}
  .dt{{text-align:center;font-style:italic;font-size:{f}px;margin-bottom:6px}}
  table{{width:100%;border-collapse:collapse;table-layout:fixed}}
  /* line-height 1.1 + đệm 1px: dòng thấp nhất có thể → cùng số dòng/trang nhưng chữ lớn hơn. */
  th,td{{border:1px solid #808080;padding:1px 4px;line-height:1.1;vertical-align:middle;word-wrap:break-word}}
  th{{background:#DCE6F1;font-weight:bold;text-align:center}}
  td.c{{text-align:center}}
  tr.first td{{border-top:1.5px solid #333}}
  tr{{page-break-inside:avoid}}
</style></head><body>{''.join(blocks)}</body></html>"""


def _download_info_for_sign_pdf(names):
	"""PDF Info for Sign (cùng dữ liệu với Excel): A4 ngang, lề trên/dưới 10mm, chân trang "Trang x/y".

	Trang 1: tiêu đề + 4 NV; các trang sau: 5 NV; mỗi trang lặp lại tên cột. Cỡ chữ: tìm nhị phân
	(bước 0,5px, 5–16px) cỡ LỚN NHẤT mà số trang = số trang dự kiến (không trang nào tràn).
	Cỡ tốt nhất < 6px (tick quá nhiều mục) → lùi bố cục 3/4, 2/3, … (_SIGN_PDF_FALLBACK).
	get_pdf tắt JavaScript nên không tự co theo trang được.
	"""
	import io

	from frappe.utils.pdf import get_pdf
	from pypdf import PdfReader

	people, company = _info_for_sign_people(names)
	if not people:
		frappe.throw(_("No record to export."))
	if len(people) > INFO_FOR_SIGN_PDF_MAX_RECORDS:
		frappe.throw(
			_("PDF can export at most {0} records at a time ({1} selected). Select fewer records or use Excel.").format(
				INFO_FOR_SIGN_PDF_MAX_RECORDS, len(people)
			),
			title=_("Info for Sign"),
		)
	options = {
		"orientation": "Landscape",
		"page-size": "A4",
		# Số trang do wkhtmltopdf tự thay [page]/[topage] — không cần JavaScript.
		"footer-center": "Trang [page]/[topage]",
		"footer-font-size": "8",
		"footer-spacing": "2",
	}

	def count(html):
		pdf = get_pdf(html, options=dict(options))
		return pdf, len(PdfReader(io.BytesIO(pdf)).pages)

	def weight(page):
		# Ước lượng độ "nặng": số dòng + dòng xuống hàng của nội dung dài.
		return sum(1 + len(v) // 45 for _e, _n, lines in page for _l, v in lines)

	def best_font(pages):
		"""(cỡ chữ lớn nhất vừa trang theo bước 0,5px trong 5px…_SIGN_PDF_MAX_FONT, pdf) — None nếu 5px vẫn tràn.

		Tìm cỡ chữ trên MẪU nhỏ (trang 1 có tiêu đề + các trang nặng nhất) cho nhanh — dựng cả
		file mỗi lần tốn ~6s/915 phiếu, tìm nhị phân trên cả file sẽ vượt timeout 120s của gunicorn.
		Sau đó dựng cả file 1 lần để kiểm; vẫn tràn thì giảm 0,5px.
		"""
		heavy = sorted(range(1, len(pages)), key=lambda i: weight(pages[i]), reverse=True)[:_SIGN_PDF_SAMPLE_PAGES]
		sample = [pages[0]] + [pages[i] for i in sorted(heavy)]
		cache = {}

		def fits(half):
			if half not in cache:
				cache[half] = count(_info_for_sign_pdf_html(sample, company, half / 2))[1] <= len(sample)
			return cache[half]

		top = int(_SIGN_PDF_MAX_FONT * 2)
		if fits(top):
			lo = top
		elif not fits(10):
			return None
		else:
			lo, hi = 10, top   # fits(lo) đúng, fits(hi) sai
			while hi - lo > 1:
				mid = (lo + hi) // 2
				if fits(mid):
					lo = mid
				else:
					hi = mid
		while True:   # kiểm trên cả file
			pdf, n = count(_info_for_sign_pdf_html(pages, company, lo / 2))
			if n <= len(pages):
				return lo / 2, pdf
			if lo <= 10:
				return None
			lo -= 1

	layouts = ((INFO_FOR_SIGN_PDF_FIRST, INFO_FOR_SIGN_PDF_PER_PAGE),) + _SIGN_PDF_FALLBACK
	pdf = None
	for first, per in layouts:
		got = best_font(_info_for_sign_pdf_pages(people, first, per))
		if got and (got[0] >= _SIGN_PDF_MIN_FONT or (first, per) == layouts[-1]):
			pdf = got[1]
			break
	if pdf is None:   # cả bố cục 1 NV/trang ở 5px vẫn tràn — vẫn xuất (có thể tràn trang)
		pdf = count(_info_for_sign_pdf_html(_info_for_sign_pdf_pages(people, 1, 1), company, 5.0))[0]
	# Tên file theo ngày xuất, không khoảng trắng: employee_info_for_sign_ddmmyyyy.pdf
	frappe.response["filename"] = f"employee_info_for_sign_{frappe.utils.now_datetime().strftime('%d%m%Y')}.pdf"
	frappe.response["filecontent"] = pdf
	# "download" = Content-Disposition: attachment → trình duyệt TẢI VỀ ngay (type "pdf" là inline = mở xem).
	# File chỉ nằm trong bộ nhớ của request, không lưu gì trên server.
	frappe.response["type"] = "download"
	frappe.response["content_type"] = "application/pdf"


def _download_info_for_sign(names):
	"""1 sheet "Info for Sign", A4 ngang: STT | Nhân viên (Mã NV xuống dòng Họ tên) | Thông tin | Nội dung | Ghi chú | Chữ ký.

	- STT đánh theo NHÂN VIÊN; STT / Nhân viên / Chữ ký gộp ô theo nhân viên.
	- Địa chỉ mỗi Section 1 dòng dạng đầy đủ; liên hệ khẩn cấp 1 dòng (xem _sign_items).

	- Nội dung LUÔN là thông tin mới (NV khai); mới trống → lấy giá trị Employee hiện tại;
	  cả hai trống → VẪN in dòng, ô Nội dung trống để NV mới tự ghi tay bổ sung.
	- Chỉ các field được tick "Info for Sign" trong Setting (NV chỉ ký xác nhận một số thông tin),
	  LUÔN đủ các field đó (không lọc "chỉ thay đổi"). Ghi chú NV không xuất.
	- Mã NV / Họ tên / Chữ ký gộp ô theo nhân viên; cột Chữ ký để trống để ký tay khi in.
	"""
	import io

	from openpyxl import Workbook
	from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

	people, company = _info_for_sign_people(names)

	wb = Workbook()
	ws = wb.active
	ws.title = "Info for Sign"

	header = list(INFO_FOR_SIGN_HEADER)
	ncol = len(header)
	thin = Side(style="thin", color="808080")
	border = Border(left=thin, right=thin, top=thin, bottom=thin)
	center = Alignment(horizontal="center", vertical="center", wrap_text=True)
	left = Alignment(horizontal="left", vertical="center", wrap_text=True)

	ws.append([company.upper()])
	ws.append([INFO_FOR_SIGN_TITLE])
	ws.append([f"Ngày: {frappe.utils.now_datetime().strftime('%d/%m/%Y')}"])
	for r in (1, 2, 3):
		ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
		ws.cell(row=r, column=1).alignment = Alignment(horizontal="center")
	ws.cell(row=1, column=1).font = Font(bold=True, size=11)
	ws.cell(row=2, column=1).font = Font(bold=True, size=14)
	ws.cell(row=3, column=1).font = Font(italic=True, size=10)

	head_row = 5
	for c, h in enumerate(header, 1):
		cell = ws.cell(row=head_row, column=c, value=h)
		cell.font = Font(bold=True)
		cell.alignment = center
		cell.border = border
		cell.fill = PatternFill(start_color="DCE6F1", end_color="DCE6F1", fill_type="solid")

	row = head_row + 1
	for stt, (emp, emp_name, lines) in enumerate(people, 1):
		first = row
		for label, value in lines:
			head = row == first
			who = f"{emp}\n{emp_name}" if emp_name else emp  # Mã NV xuống dòng Họ tên, chung 1 ô
			# Ghi chú (cột 5) + Chữ ký (cột 6) để trống cho ghi tay / ký tay, gộp theo nhân viên.
			vals = [stt if head else None, who if head else None, label, value, None, None]
			for c, v in enumerate(vals, 1):
				cell = ws.cell(row=row, column=c, value=v)
				cell.border = border
				cell.alignment = left if c in (3, 4, 5) else center
			row += 1
		last = row - 1
		for c in (1, 2, 5, 6):  # STT, Nhân viên, Ghi chú, Chữ ký gộp theo nhân viên
			if last > first:
				ws.merge_cells(start_row=first, start_column=c, end_row=last, end_column=c)
		if last == first:
			ws.row_dimensions[first].height = 42  # đủ chỗ ký + 2 dòng Mã NV/Họ tên khi NV chỉ có 1 dòng

	# A4 ngang: tổng ~140 ký tự để vừa 1 trang khi fitToWidth; cột Nội dung rộng cho địa chỉ đầy đủ.
	for col, width in zip("ABCDEF", (5, 20, 24, 56, 24, 22)):
		ws.column_dimensions[col].width = width
	ws.print_title_rows = f"{head_row}:{head_row}"
	ws.page_setup.orientation = "landscape"
	ws.page_setup.paperSize = ws.PAPERSIZE_A4
	ws.page_setup.fitToWidth = 1
	ws.page_setup.fitToHeight = 0
	ws.sheet_properties.pageSetUpPr.fitToPage = True
	ws.print_options.horizontalCentered = True

	buf = io.BytesIO()
	wb.save(buf)
	frappe.response["filename"] = "employee_info_for_sign.xlsx"
	frappe.response["filecontent"] = buf.getvalue()
	frappe.response["type"] = "binary"


# HR sửa trực tiếp giá trị đã khai ngay trên bảng của form Desk (data_view), rồi lưu bằng
# nút Save chuẩn: JS ghép vào data_json, controller validate gọi validate_desk_edit().
_TEXT_EDITABLE_TYPES = {"Data", "Small Text", "Text", "Long Text", "Int", "Float", "Currency", "Phone"}
_MULTILINE_TYPES = {"Small Text", "Text", "Long Text"}


def _hr_editor(f):
	"""Loại ô HR được sửa trên Desk: text | textarea | select | date | province | ward — hoặc None.

	Field read_only trên trang (NV không được sửa) thì HR cũng không sửa ở đây.
	Check/Datetime/Time/Link chưa hỗ trợ.
	"""
	if f.get("read_only") or f.get("fieldname") == CCCD_EXPIRY_FIELD:
		return None  # ngày hết hạn CCCD tự tính (validate_desk_edit) — không cho sửa tay
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


def _address_pairs(config):
	"""[(province_fieldname, ward_fieldname)] — ghép theo section, giống trang www
	(mỗi section có 1 field widget Address Province dẫn các field Address Ward)."""
	pairs = []
	for sec in config["sections"]:
		prov = None
		for f in sec["fields"]:
			if f.get("widget") == "Address Province":
				prov = f["fieldname"]
			elif f.get("widget") == "Address Ward":
				pairs.append((prov, f["fieldname"]))
	return pairs


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
	if before.status == "Synced":
		frappe.throw(_("Already synced to Employee — submitted data can no longer be edited."))

	old = json.loads(before.data_json or "{}")
	new = json.loads(doc.data_json or "{}")
	config = _build_config()
	fields = {f["fieldname"]: f for sec in config["sections"] for f in sec["fields"]}

	changed = set()
	errors = []
	for k in set(old) | set(new):
		ov, nv = old.get(k), new.get(k)
		if ov == nv:
			continue
		f = fields.get(k)
		if not f or not _hr_editor(f):
			frappe.throw(_("Field {0} cannot be edited here.").format(f["label"] if f else k))
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

	real = [f["fieldname"] for sec in config["sections"] for f in sec["fields"] if not f.get("custom")]
	emp_vals = frappe.db.get_value("Employee", doc.employee, real, as_dict=True) or {} if real else {}

	prov_of = {ward: prov for prov, ward in _address_pairs(config)}
	sections = []
	for sec in config["sections"]:
		rows = []
		for f in sec["fields"]:
			fn = f["fieldname"]
			if fn in ("employee", "name"):
				continue  # identity — already shown on the record header
			new_v = saved.get(fn)
			new_s = "" if new_v is None else str(new_v)
			old_s = "" if f.get("custom") else _fmt(emp_vals.get(fn))
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
				"custom": bool(f.get("custom")),
				"editor": _hr_editor(f),
				"options": f.get("options") if _hr_editor(f) == "select" else None,
				"province_field": prov_of.get(fn),
			})
		if rows:
			sections.append({"label": sec["label"], "rows": rows})

	return {"sections": sections, "remarks": saved.get(REMARKS_KEY) or ""}


# ---------------------------------------------------------------------------
# Review + Sync to Employee
# ---------------------------------------------------------------------------

# Address groups on Employee whose "_full" is rebuilt = village, commune, province.
_ADDRESS_GROUPS = [
	{
		"province": "custom_current_address_province",
		"commune": "custom_current_address_commune",
		"village": "custom_current_address_village",
		"full": "custom_current_address_full",
	},
	{
		"province": "custom_permanent_address_province",
		"commune": "custom_permanent_address_commune",
		"village": "custom_permanent_address_village",
		"full": "custom_permanent_address_full",
	},
	# 🚧 TẠM TẮT 21/08/2026 — field custom_place_of_origin_address_* đã bị gỡ khỏi Employee.
	#    Giữ nguyên để khai lại sau; bỏ comment cả khối là chạy như cũ.
	# {
	# "province": "custom_place_of_origin_address_province",
	# "commune": "custom_place_of_origin_address_commune",
	# "village": "custom_place_of_origin_address_village",
	# "full": "custom_place_of_origin_address_full",
	# },
]


def _coerce_for_employee(value, fieldtype):
	"""Convert a submitted (string) value to something safe for emp.set()."""
	if value is None:
		return None
	sval = str(value).strip()
	if sval == "":
		# Empty → clear numeric/date/link fields; keep "" for text.
		if fieldtype in ("Int", "Float", "Currency", "Date", "Datetime", "Time", "Link"):
			return None
		return ""
	if fieldtype == "Check":
		return 1 if sval in ("1", "true", "True", "on", "yes", "Có") else 0
	if fieldtype == "Int":
		return int(float(sval))
	if fieldtype in ("Float", "Currency"):
		return float(sval)
	return sval


def _rebuild_address_full(emp, changed_fieldnames):
	"""Recompute custom_*_address_full = village + commune + province (like the
	Employee form) for any address group whose parts were touched."""
	for g in _ADDRESS_GROUPS:
		if not any(g[k] in changed_fieldnames for k in ("province", "commune", "village")):
			continue
		parts = [emp.get(g["village"]), emp.get(g["commune"]), emp.get(g["province"])]
		emp.set(g["full"], ", ".join([p for p in parts if p]))


@frappe.whitelist()
def review_forms(names):
	"""Mark Submitted forms as Reviewed (required before syncing).

	`names` = JSON list of Employee Self Update Info names.
	Returns {reviewed, skipped, results:[{employee, ok, message}]}.
	"""
	_require_hr()
	if isinstance(names, str):
		names = json.loads(names or "[]")
	if not names:
		frappe.throw(_("No records selected."))

	reviewed, skipped, results = 0, 0, []
	for name in names:
		doc = frappe.get_doc(INFO_DT, name)
		if doc.status != "Submitted":
			skipped += 1
			results.append({"employee": doc.employee, "ok": False,
				"message": _("Bỏ qua — trạng thái {0} (chỉ review được bản Submitted)").format(doc.status)})
			continue
		doc.status = "Reviewed"
		doc.reviewed_on = now_datetime()
		doc.reviewed_by = frappe.session.user
		doc.save(ignore_permissions=True)
		reviewed += 1
		results.append({"employee": doc.employee, "ok": True, "message": _("Đã review")})
	frappe.db.commit()
	return {"reviewed": reviewed, "skipped": skipped, "results": results}


@frappe.whitelist()
def get_syncable_fields():
	"""Return the real Employee fields (non-custom) that Sync can write, for the
	HR field-picker dialog. `[{fieldname, label}]`."""
	_require_hr()
	config = _build_config()
	return [
		{"fieldname": f["fieldname"], "label": f["label"]}
		for sec in config["sections"]
		for f in sec["fields"]
		if not f.get("custom") and f["fieldname"] not in ("employee", "name")
	]


@frappe.whitelist()
def sync_to_employee(names, fields=None):
	"""Write submissions into the Employee record.

	Only fields that exist on Employee (incl. custom_ fields) are written; custom
	free-form fields and remarks are ignored. `fields` (optional JSON list of
	fieldnames) limits Sync to the HR-selected fields; omitted → all configured
	fields. When Disable Review is on, records are synced straight from Submitted;
	otherwise only Reviewed records are synced. Each record is saved independently
	so one failure does not block the rest. Returns {synced, failed, skipped, results}.
	"""
	_require_hr()
	if isinstance(names, str):
		names = json.loads(names or "[]")
	if not names:
		frappe.throw(_("No records selected."))
	if isinstance(fields, str):
		fields = json.loads(fields or "null")
	if fields is not None and not fields:
		frappe.throw(_("Select at least one field to sync."))

	setting = _get_setting()
	# Disable Review → sync from Submitted; else require Reviewed. Reviewed is
	# always accepted so legacy already-reviewed records still sync.
	allowed = {"Submitted", "Reviewed"} if setting.get("disable_review") else {"Reviewed"}

	config = _build_config()
	# Real Employee fields only (non-custom, excluding identity fields).
	emp_fields = {
		f["fieldname"]: f
		for sec in config["sections"]
		for f in sec["fields"]
		if not f.get("custom") and f["fieldname"] not in ("employee", "name")
	}
	# Limit to the HR-selected fields when provided.
	if fields is not None:
		sel = set(fields)
		emp_fields = {fn: f for fn, f in emp_fields.items() if fn in sel}

	synced, failed, skipped, results = 0, 0, 0, []
	for name in names:
		doc = frappe.get_doc(INFO_DT, name)
		if doc.status not in allowed:
			skipped += 1
			need = _("Submitted") if setting.get("disable_review") else _("Reviewed")
			results.append({"employee": doc.employee, "employee_name": doc.employee_name, "ok": False,
				"message": _("Bỏ qua — cần trạng thái {0} để Sync (hiện tại: {1})").format(need, doc.status)})
			continue

		saved = json.loads(doc.data_json or "{}")
		try:
			emp = frappe.get_doc("Employee", doc.employee)
			meta = emp.meta
			changed = []
			for fn, f in emp_fields.items():
				if fn not in saved:
					continue
				if not meta.has_field(fn):
					continue  # field no longer on Employee
				emp.set(fn, _coerce_for_employee(saved.get(fn), f["fieldtype"]))
				changed.append(fn)
			_rebuild_address_full(emp, set(changed))
			emp.save(ignore_permissions=True)

			doc.status = "Synced"
			doc.synced_on = now_datetime()
			doc.synced_by = frappe.session.user
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			synced += 1
			results.append({"employee": doc.employee, "employee_name": doc.employee_name, "ok": True,
				"message": _("Đã đồng bộ {0} trường").format(len(changed))})
		except Exception as e:
			frappe.db.rollback()
			failed += 1
			results.append({"employee": doc.employee, "employee_name": doc.employee_name, "ok": False,
				"message": str(e)})
	return {"synced": synced, "failed": failed, "skipped": skipped, "results": results}
