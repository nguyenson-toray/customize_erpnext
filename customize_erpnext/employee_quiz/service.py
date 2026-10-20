# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Attempt lifecycle for TIQN Quiz: start -> save progress -> submit/expire.
To let someone redo a quiz, HR deletes the attempt (or raises Max Attempts).

Called by the guest API (api/employee_quiz/quiz_api.py) and the Desk API.
Everything here runs with ignore_permissions: the caller decides who may act.
Messages for employees are hard-coded Vietnamese (the quiz page is Vietnamese only).
"""

import json
import random
from datetime import timedelta

import frappe
from frappe.utils import cint, flt, get_datetime, now_datetime

from customize_erpnext.employee_quiz import grading
from customize_erpnext.employee_quiz.doctype.tiqn_quiz.tiqn_quiz import COUNTED_STATUSES

RESPONSE_DT = "TIQN Quiz Response"
# A client that auto-submits at 00:00 still needs a moment to reach the server.
GRACE_SECONDS = 60
# Signature pad on the quiz page (same format as /employee-self-update-info).
SIGNATURE_PREFIX = "data:image/png;base64,"
SIGNATURE_MAX_LEN = 400_000
MAX_ANSWER_LENGTH = 2000


# ------------------------------------------------------------------ helpers


def parse_answers(answers):
	"""JSON string / dict from the page -> {q_key: str}."""
	if not answers:
		return {}
	if isinstance(answers, str):
		try:
			answers = json.loads(answers)
		except ValueError:
			frappe.throw("Bài làm không hợp lệ.")
	if not isinstance(answers, dict):
		frappe.throw("Bài làm không hợp lệ.")
	out = {}
	for key, value in answers.items():
		if isinstance(value, (list, tuple)):
			value = ",".join(str(v) for v in value)
		out[str(key)] = str(value if value is not None else "")[:MAX_ANSWER_LENGTH]
	return out


def is_open(quiz):
	"""-> (True, "") or (False, message for the employee). HR opens/closes by hand."""
	if quiz.status == "Draft":
		return False, "Bài kiểm tra chưa mở."
	if quiz.status == "Closed":
		return False, "Bài kiểm tra đã đóng."
	return True, ""


def is_allowed(quiz, employee):
	if frappe.db.get_value("Employee", employee, "status") != "Active":
		return False
	if quiz.all_employees:
		return True
	return any(r.employee == employee for r in quiz.employees)


def code_ok(quiz, employee, code):
	"""Code = the 2 digits of the birth day, or the quiz bypass code.
	Always passes when the quiz has Verify by Birth Day unticked."""
	if not cint(quiz.verify_by_dob):
		return True
	code = "".join(ch for ch in str(code or "") if ch.isdigit())
	if not code:
		return False
	# bypass_code is optional — an empty one must not turn into "00".
	if quiz.bypass_code and code.zfill(2) == str(quiz.bypass_code).zfill(2):
		return True
	dob = frappe.db.get_value("Employee", employee, "date_of_birth")
	return bool(dob) and int(code) == get_datetime(dob).day


def attempts_used(quiz_name, employee):
	return frappe.db.count(RESPONSE_DT, {"quiz": quiz_name, "employee": employee, "status": ["in", COUNTED_STATUSES]})


def attempts_left(quiz, employee):
	"""None = unlimited."""
	if not cint(quiz.max_attempts):
		return None
	return max(0, cint(quiz.max_attempts) - attempts_used(quiz.name, employee))


def in_progress(quiz_name, employee):
	name = frappe.db.get_value(
		RESPONSE_DT, {"quiz": quiz_name, "employee": employee, "status": "In Progress"}, "name", order_by="creation desc"
	)
	return frappe.get_doc(RESPONSE_DT, name) if name else None


def past_deadline(resp, grace=GRACE_SECONDS):
	return bool(resp.deadline) and now_datetime() > get_datetime(resp.deadline) + timedelta(seconds=grace)


def time_is_up(resp, slack=5):
	"""The clock reached 0 (the page auto-submits then) — a few seconds of clock drift allowed."""
	return bool(resp.deadline) and now_datetime() >= get_datetime(resp.deadline) - timedelta(seconds=slack)


def signature_payload(quiz):
	"""What the page shows before Submit: None, or the commitment line + signature pad."""
	if not cint(quiz.require_signature):
		return None
	return {"commitment": (quiz.commitment_text or "").strip()}


def seconds_left(resp):
	if not resp.deadline:
		return None
	return max(0, int((get_datetime(resp.deadline) - now_datetime()).total_seconds()))


def question_map(quiz):
	return {q.q_key: q for q in quiz.questions}


# ----------------------------------------------------------- payload builders


def build_order(quiz):
	"""[{q, o}] — question keys in display order, option letters per question."""
	questions = list(quiz.questions)
	if quiz.shuffle_questions:
		random.shuffle(questions)
	order = []
	for q in questions:
		letters = [letter for letter, _text in grading.options(q)]
		if quiz.shuffle_options:
			random.shuffle(letters)
		order.append({"q": q.q_key, "o": letters})
	return order


def questions_payload(quiz, order):
	"""Questions as the page shows them — never the correct answers."""
	qmap = question_map(quiz)
	out = []
	for item in order:
		q = qmap.get(item["q"])
		if not q:
			continue
		labels = dict(grading.options(q))
		out.append(
			{
				"key": q.q_key,
				"question": grading.question_html(q.question),
				"type": q.question_type,
				"required": cint(q.required),
				"points": flt(grading.max_points(q)),
				"image": q.image or "",
				"options": [{"key": letter, "text": labels[letter]} for letter in item["o"] if letter in labels],
			}
		)
	return out


def attempt_payload(quiz, resp):
	order = json.loads(resp.question_order or "[]")
	return {
		"response": resp.name,
		"employee_name": resp.employee_name,
		"attempt_no": resp.attempt_no,
		"seconds_left": seconds_left(resp),
		"questions": questions_payload(quiz, order),
		"answers": parse_answers(resp.draft_answers),
		"signature": signature_payload(quiz),
	}


def result_payload(quiz, resp):
	mode = quiz.show_result or "Score only"
	out = {
		"response": resp.name,
		"status": resp.status,
		"show_result": mode,
		"attempts_left": attempts_left(quiz, resp.employee),
	}
	if mode == "Nothing":
		return out
	out.update(
		{
			"score": flt(resp.score),
			"max_score": flt(resp.max_score),
			"percentage": flt(resp.percentage),
			"passed": cint(resp.passed),
			"pass_percentage": flt(quiz.pass_percentage),
		}
	)
	if mode == "Score + correct answers":
		qmap = question_map(quiz)
		out["details"] = [
			{
				"question": grading.question_html(a.question),
				"answer_text": a.answer_text,
				"correct_text": a.correct_text,
				"is_correct": cint(a.is_correct),
				"points_awarded": flt(a.points_awarded),
				"points_max": flt(a.points_max),
				"explanation": (qmap[a.q_key].explanation or "") if a.q_key in qmap else "",
			}
			for a in resp.answers
		]
	return out


def preview_result(quiz, answers):
	"""Grade without saving — Desk preview always shows the correct answers."""
	result = grading.grade(quiz.questions, answers, quiz.pass_percentage)
	qmap = question_map(quiz)
	return {
		"status": "Preview",
		"show_result": "Score + correct answers",
		"attempts_left": None,
		"score": result["score"],
		"max_score": result["max_score"],
		"percentage": result["percentage"],
		"passed": result["passed"],
		"pass_percentage": flt(quiz.pass_percentage),
		"details": [dict(r, explanation=qmap[r["q_key"]].explanation or "") for r in result["rows"]],
	}


# ---------------------------------------------------------------- lifecycle


def start(quiz, employee):
	"""Resume the open attempt or create a new one. Caller has checked code/open/allowed."""
	# Serialise double-taps on "Start" for the same employee.
	frappe.db.sql("select name from `tabEmployee` where name = %s for update", employee)

	resp = in_progress(quiz.name, employee)
	if resp and past_deadline(resp):
		finalize(quiz, resp, parse_answers(resp.draft_answers), expired=True)
		resp = None
	if resp:
		return resp

	left = attempts_left(quiz, employee)
	if left is not None and left <= 0:
		frappe.throw("Bạn đã dùng hết {0} lượt làm bài này.".format(cint(quiz.max_attempts)))

	emp = frappe.db.get_value("Employee", employee, ["employee_name", "custom_section", "custom_group"], as_dict=True)
	last_no = frappe.db.sql(
		"select max(attempt_no) from `tabTIQN Quiz Response` where quiz = %s and employee = %s", (quiz.name, employee)
	)[0][0]
	started = now_datetime()
	minutes = cint(quiz.time_limit_minutes)
	resp = frappe.get_doc(
		{
			"doctype": RESPONSE_DT,
			"quiz": quiz.name,
			"employee": employee,
			"employee_name": emp.employee_name,
			"custom_section": emp.custom_section,
			"custom_group": emp.custom_group,
			"status": "In Progress",
			"attempt_no": cint(last_no) + 1,  # max + 1: stays unique after HR deletes an attempt
			"started_at": started,
			"deadline": started + timedelta(minutes=minutes) if minutes else None,
			"question_order": json.dumps(build_order(quiz)),
		}
	)
	resp.insert(ignore_permissions=True)
	return resp


def save_progress(resp, answers):
	if resp.status != "In Progress" or past_deadline(resp):
		return False
	resp.db_set("draft_answers", json.dumps(answers, ensure_ascii=False), update_modified=False)
	return True


def finalize(quiz, resp, answers, expired=False, signature=None, committed=0):
	qmap = question_map(quiz)
	order = json.loads(resp.question_order or "[]")
	questions = [qmap[item["q"]] for item in order if item["q"] in qmap]
	result = grading.grade(questions, answers, quiz.pass_percentage)

	now = now_datetime()
	resp.set("answers", [])
	for row in result["rows"]:
		resp.append("answers", row)
	resp.update(
		{
			"status": "Expired" if expired else "Submitted",
			"score": result["score"],
			"max_score": result["max_score"],
			"percentage": result["percentage"],
			"passed": result["passed"],
			"submitted_at": now,
			"duration_sec": int((now - get_datetime(resp.started_at)).total_seconds()),
			"draft_answers": json.dumps(answers, ensure_ascii=False),
		}
	)
	if signature:
		resp.update({"signature": signature, "commitment_confirmed": cint(committed)})
	resp.save(ignore_permissions=True)
	return resp


# ------------------------------------------------------------------ results


def eligible_employees(quiz, section=None, group=None, employee=None):
	"""Who may take the quiz: the Employees table, or every active employee."""
	fields = ["employee", "employee_name", "custom_section", "custom_group", "date_of_joining"]
	if quiz.all_employees:
		filters = {"status": "Active"}
		if section:
			filters["custom_section"] = section
		if group:
			filters["custom_group"] = group
		if employee:
			filters["name"] = employee
		return frappe.get_all(
			"Employee", filters=filters, fields=["name as employee", *fields[1:]], order_by="name asc"
		)
	return [
		frappe._dict({f: r.get(f) for f in fields})
		for r in quiz.employees
		if (not section or r.custom_section == section)
		and (not group or r.custom_group == group)
		and (not employee or r.employee == employee)
	]


def latest_results(quiz_name):
	"""{employee: latest Submitted/Expired attempt} — the attempt that counts."""
	out = {}
	for r in frappe.get_all(
		RESPONSE_DT,
		filters={"quiz": quiz_name, "status": ["in", COUNTED_STATUSES]},
		fields=["name", "employee", "percentage", "passed"],
		order_by="creation asc",
	):
		out[r.employee] = r
	return out
