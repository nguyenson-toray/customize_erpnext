# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Guest API for the quiz page /quiz?f=<slug> (no login).

Employees pick themselves and type the 2 digits of their birth day or the
quiz bypass code. Messages raised here are shown on the quiz page, which is Vietnamese only
(user decision 20/10/2026) — so they are hard-coded Vietnamese, not _().

Public (allow_guest=True):
	get_quiz(slug)                      -> intro screen
	get_employees(slug)                 -> who may take it (picker list)
	verify(slug, employee, code)        -> {valid, attempts...}
	start(slug, employee, code)         -> attempt payload (new or resumed)
	save_progress(response, answers)    -> autosave
	submit(response, answers)           -> result per quiz.show_result
Desk users with a quiz role (preview, nothing saved):
	preview_start(slug), preview_submit(slug, answers)
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from customize_erpnext.employee_quiz import service

MANAGER_ROLES = ("Quiz Manager", "System Manager")


def _quiz(slug):
	name = frappe.db.get_value("TIQN Quiz", {"slug": str(slug or "").strip()}) if slug else None
	if not name:
		frappe.throw("Link bài kiểm tra không đúng.")
	return frappe.get_doc("TIQN Quiz", name)


def _is_manager():
	return frappe.session.user != "Guest" and bool(set(frappe.get_roles()) & set(MANAGER_ROLES))


def _require_manager():
	if not _is_manager():
		frappe.throw(_("Not permitted"), frappe.PermissionError)


def _require_open(quiz):
	ok, message = service.is_open(quiz)
	if not ok:
		frappe.throw(message)


def _require_employee(quiz, employee, code):
	_require_open(quiz)
	if not employee or not service.is_allowed(quiz, employee):
		frappe.throw("Bạn không có trong danh sách làm bài này. Vui lòng liên hệ HR.")
	if not service.code_ok(quiz, employee, code):
		frappe.throw("Sai mã. Nhập 2 số ngày sinh của bạn hoặc mã do HR cung cấp.")


def _response(name):
	if not name or not frappe.db.exists(service.RESPONSE_DT, name):
		frappe.throw("Không tìm thấy lượt làm bài. Vui lòng bắt đầu lại.")
	resp = frappe.get_doc(service.RESPONSE_DT, name)
	return frappe.get_doc("TIQN Quiz", resp.quiz), resp


def _department_labels():
	return dict(frappe.get_all("Department", fields=["name", "department_name"], as_list=True))


@frappe.whitelist(allow_guest=True)
def get_quiz(slug):
	quiz = _quiz(slug)
	ok, message = service.is_open(quiz)
	return {
		"title": quiz.title,
		"description": quiz.description or "",
		"question_count": cint(quiz.question_count),
		"total_points": flt(quiz.total_points),
		"time_limit_minutes": cint(quiz.time_limit_minutes),
		"max_attempts": cint(quiz.max_attempts),
		"pass_percentage": flt(quiz.pass_percentage),
		"is_open": ok,
		"message": message,
		"require_code": bool(cint(quiz.verify_by_dob)),
		"can_preview": _is_manager(),
	}


@frappe.whitelist(allow_guest=True)
def get_employees(slug):
	"""[{id, name, dept}] — the page filters this list locally (accent-insensitive)."""
	quiz = _quiz(slug)
	_require_open(quiz)
	filters = {"status": "Active"}
	if not quiz.all_employees:
		filters["name"] = ["in", [r.employee for r in quiz.employees] or [""]]
	rows = frappe.get_all(
		"Employee", filters=filters, fields=["name", "employee_name", "department"], order_by="name asc"
	)
	depts = _department_labels()
	return [
		{"id": r.name, "name": r.employee_name, "dept": depts.get(r.department) or r.department or ""}
		for r in rows
	]


@frappe.whitelist(allow_guest=True)
def verify(slug, employee, code):
	quiz = _quiz(slug)
	_require_open(quiz)
	if not service.is_allowed(quiz, employee):
		frappe.throw("Bạn không có trong danh sách làm bài này. Vui lòng liên hệ HR.")
	if not service.code_ok(quiz, employee, code):
		return {"valid": False}
	return {
		"valid": True,
		"employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
		"attempts_used": service.attempts_used(quiz.name, employee),
		"attempts_left": service.attempts_left(quiz, employee),
		"in_progress": bool(service.in_progress(quiz.name, employee)),
	}


@frappe.whitelist(allow_guest=True)
def start(slug, employee, code):
	quiz = _quiz(slug)
	_require_employee(quiz, employee, code)
	resp = service.start(quiz, employee)
	return service.attempt_payload(quiz, resp)


@frappe.whitelist(allow_guest=True)
def save_progress(response, answers):
	quiz, resp = _response(response)
	saved = service.save_progress(resp, service.parse_answers(answers))
	return {"saved": saved, "status": resp.status, "seconds_left": service.seconds_left(resp)}


@frappe.whitelist(allow_guest=True)
def submit(response, answers=None):
	quiz, resp = _response(response)
	if resp.status == "In Progress":
		if service.past_deadline(resp):
			# Too late: grade what was autosaved before the deadline.
			service.finalize(quiz, resp, service.parse_answers(resp.draft_answers), expired=True)
		else:
			service.finalize(quiz, resp, service.parse_answers(answers))
	# Already submitted (double tap / retry after a lost response): same result again.
	return service.result_payload(quiz, resp)


@frappe.whitelist()
def preview_start(slug):
	_require_manager()
	quiz = _quiz(slug)
	return {
		"response": None,
		"employee_name": "Xem thử",
		"attempt_no": 0,
		"seconds_left": cint(quiz.time_limit_minutes) * 60 or None,
		"questions": service.questions_payload(quiz, service.build_order(quiz)),
		"answers": {},
	}


@frappe.whitelist()
def preview_submit(slug, answers=None):
	_require_manager()
	quiz = _quiz(slug)
	return service.preview_result(quiz, service.parse_answers(answers))
