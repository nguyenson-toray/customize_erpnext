"""Quyền vào trang www: danh sách NV, mã ngày sinh / bypass, khoá sau khi gửi, token tải phiếu.

Tách nguyên văn từ self_update_info_api.py (27/10/2026) — mặt tiền đó re-export mọi tên."""

import frappe
from frappe import _
from frappe.utils import now_datetime

from .rules import (
	INFO_DT,
)


def _require_hr():
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required"), frappe.AuthenticationError)
	roles = frappe.get_roles()
	if not any(r in roles for r in ("HR Manager", "HR User", "System Manager")):
		frappe.throw(_("Not permitted"), frappe.PermissionError)


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
