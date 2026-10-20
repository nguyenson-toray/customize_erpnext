# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Employee Quiz — grading, quiz validation, guest flow, Desk actions.

Everything runs in one transaction and is rolled back at the end (nothing is
committed, series counters included):

    bench --site erp.tiqn.local execute customize_erpnext.employee_quiz.test_employee_quiz.run
"""

import json

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from customize_erpnext.api.employee_quiz import employee_picker as picker
from customize_erpnext.api.employee_quiz import quiz_admin_api as admin
from customize_erpnext.api.employee_quiz import quiz_api as api
from customize_erpnext.employee_quiz import grading, service
from customize_erpnext.employee_quiz.report.tiqn_quiz_result import tiqn_quiz_result as result_report

RESULTS = []


def check(name, cond):
	RESULTS.append((name, bool(cond)))


def throws(fn, exc=frappe.ValidationError):
	try:
		fn()
	except exc:
		frappe.clear_messages()
		return True
	return False


# ---------------------------------------------------------------- fixtures


def _employees(n):
	rows = frappe.get_all(
		"Employee",
		filters={"status": "Active", "date_of_birth": ["is", "set"]},
		fields=["name", "date_of_birth"],
		order_by="name asc",
		limit=n,
	)
	assert len(rows) == n, "not enough active employees with a date of birth"
	return rows


def _day(emp):
	return f"{get_datetime(emp.date_of_birth).day:02d}"


def _wrong_day(emp):
	return f"{(get_datetime(emp.date_of_birth).day % 28) + 1:02d}"


QUESTIONS = [
	# question_type / correct_options are what the quiz derives from the ticks;
	# they are spelled out here for the pure grading tests.
	{"question": "Single", "question_type": "Single choice", "points": 2, "option_a": "x", "option_b": "y",
		"option_c": "z", "is_correct_b": 1, "correct_options": "B"},
	{"question": "Multi", "question_type": "Multiple choice", "points": 2, "option_a": "x", "option_b": "y",
		"option_c": "z", "is_correct_c": 1, "is_correct_a": 1, "correct_options": "c, a"},
	{"question": "TF", "question_type": "Single choice", "points": 1, "option_a": "Đúng", "option_b": "Sai",
		"is_correct_a": 1, "correct_options": "A"},
	{"question": "Text", "question_type": "Single choice", "points": 1, "option_a": "kéo", "option_b": "dao",
		"is_correct_a": 1, "correct_options": "A"},
	# 0 points + optional: counts for nothing, like a feedback question.
	{"question": "Survey", "question_type": "Single choice", "points": 0, "required": 0, "option_a": "tốt",
		"option_b": "chưa tốt", "is_correct_a": 1, "correct_options": "A"},
]


def _quiz(employees, **kw):
	doc = frappe.get_doc(
		{
			"doctype": "TIQN Quiz",
			"title": "Test quiz",
			"status": "Open",
			"bypass_code": "77",
			"time_limit_minutes": 10,
			"max_attempts": 1,
			"pass_percentage": 80,
			"show_result": "Score only",  # explicit: the DocType default may change
			"questions": [dict(q) for q in QUESTIONS],
			"employees": [{"employee": e.name} for e in employees],
			**kw,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _keys(quiz):
	return {q.question: q.q_key for q in quiz.questions}


# ------------------------------------------------------------------ tests


def test_grading():
	q = frappe._dict(QUESTIONS[1], q_key="m")
	check("multi exact = full", grading.grade_question(q, "A,C")["points_awarded"] == 2)
	check("multi order-free", grading.grade_question(q, "c,a")["is_correct"] == 1)
	check("multi: half right = 0 (all or nothing)", grading.grade_question(q, "A")["points_awarded"] == 0)
	check("multi: extra wrong pick = 0", grading.grade_question(q, "A,B,C")["points_awarded"] == 0)
	t = frappe._dict(QUESTIONS[3])
	check("single right", grading.grade_question(t, "a")["points_awarded"] == 1)
	check("single wrong", grading.grade_question(t, "B")["is_correct"] == 0)
	check("single two picks = wrong", grading.grade_question(t, "A,B")["is_correct"] == 0)
	check("unanswered = 0", grading.grade_question(t, None)["points_awarded"] == 0)
	s = frappe._dict(QUESTIONS[4])
	check("0-point question max 0", grading.max_points(s) == 0)
	r = grading.grade([frappe._dict(QUESTIONS[0], q_key="a"), s], {"a": "B"}, pass_percentage=80)
	check("grade total", r["max_score"] == 2 and r["percentage"] == 100 and r["passed"] == 1)
	check("all-zero quiz passes", grading.grade([s], {})["passed"] == 1)
	check("parse letters", grading.parse_letters("c ,a, A, x") == ["A", "C"])


def test_validation(emps):
	check("bypass must be 2 digits", throws(lambda: _quiz(emps, bypass_code="123")))
	bad = [dict(QUESTIONS[0], is_correct_d=1)]
	check("tick on an empty option rejected", throws(lambda: _quiz(emps, questions=bad)))
	auto = _quiz(emps, status="Draft", questions=[
		dict(QUESTIONS[0], question_type="Multiple choice", correct_options="Z"),  # typed values are ignored
		dict(QUESTIONS[0], is_correct_c=1),
	])
	check("auto: 1 tick = single", (auto.questions[0].question_type, auto.questions[0].correct_options) == ("Single choice", "B"))
	check("auto: 2 ticks = multiple", (auto.questions[1].question_type, auto.questions[1].correct_options) == ("Multiple choice", "B,C"))
	free = [{"question": "Free", "question_type": "Single choice"}]
	check("no options rejected (no free text)", throws(lambda: _quiz(emps, status="Draft", questions=free)))
	bad = [dict(QUESTIONS[0], option_b="", option_c="")]
	check("needs 2 options", throws(lambda: _quiz(emps, questions=bad, status="Draft")))
	check("open needs employees", throws(lambda: _quiz([], status="Open")))
	no_key = [dict(QUESTIONS[0], is_correct_b=0)]
	check("draft without answer key saves", _quiz(emps, questions=no_key, status="Draft").question_count == 1)
	check("open without answer key blocked", throws(lambda: _quiz(emps, questions=no_key, status="Open")))
	draft = _quiz([], status="Draft", bypass_code="")
	check("bypass optional (stays empty)", draft.bypass_code is None)
	check("slug + link", draft.slug and draft.quiz_link.endswith("/quiz?f=" + draft.slug))
	check("totals", draft.question_count == 5 and draft.total_points == 6)
	check("correct letters from ticks", draft.questions[1].correct_options == "A,C")
	check("q_keys unique", len({q.q_key for q in draft.questions}) == 5)
	check("draft: get_employees blocked", throws(lambda: api.get_employees(draft.slug)))


def test_guest_flow(emps):
	e1, e2, e3 = emps
	quiz = _quiz([e1, e2])
	keys = _keys(quiz)

	info = api.get_quiz(quiz.slug)
	check("get_quiz open", info["is_open"] and info["question_count"] == 5)
	check("bad slug", throws(lambda: api.get_quiz("nope")))
	listed = {r["id"] for r in api.get_employees(quiz.slug)}
	check("only listed employees", listed == {e1.name, e2.name})

	check("verify wrong day", api.verify(quiz.slug, e1.name, _wrong_day(e1))["valid"] is False)
	check("verify dob day", api.verify(quiz.slug, e1.name, _day(e1))["valid"])
	check("verify dob day without zero", api.verify(quiz.slug, e1.name, str(int(_day(e1))))["valid"])
	check("verify bypass", api.verify(quiz.slug, e2.name, "77")["valid"])
	nob = _quiz([e1], bypass_code="")
	check("empty bypass: 00 refused", api.verify(nob.slug, e1.name, "00")["valid"] is (_day(e1) == "00"))
	check("empty bypass: dob still works", api.verify(nob.slug, e1.name, _day(e1))["valid"])
	check("not listed -> throw", throws(lambda: api.verify(quiz.slug, e3.name, "77")))
	check("start with wrong code -> throw", throws(lambda: api.start(quiz.slug, e1.name, _wrong_day(e1))))

	a = api.start(quiz.slug, e1.name, _day(e1))
	blob = json.dumps(a)
	check("payload hides answers", "correct_options" not in blob and "is_correct" not in blob and "bypass" not in blob)
	check("payload has 5 questions", len(a["questions"]) == 5)
	check("yes/no question has its 2 options", [o["text"] for o in a["questions"][2]["options"]] == ["Đúng", "Sai"])
	check("seconds left ~600", 590 <= a["seconds_left"] <= 600)

	again = api.start(quiz.slug, e1.name, _day(e1))
	check("start again resumes", again["response"] == a["response"])

	answers = {keys["Single"]: "B", keys["Multi"]: "A", keys["TF"]: "A", keys["Text"]: "A"}
	check("save progress", api.save_progress(a["response"], json.dumps(answers))["saved"])
	check("resume returns saved answers", api.start(quiz.slug, e1.name, _day(e1))["answers"] == answers)

	r = api.submit(a["response"], json.dumps(answers))
	check("score 4/6", r["score"] == 4 and r["max_score"] == 6 and r["passed"] == 0)
	check("score only: no details", "details" not in r)
	check("double submit returns same", api.submit(a["response"], "{}")["score"] == 4)
	check("no attempts left", throws(lambda: api.start(quiz.slug, e1.name, _day(e1))))
	check("verify shows used", api.verify(quiz.slug, e1.name, _day(e1))["attempts_left"] == 0)

	s1 = admin.get_results_summary(quiz.name)
	check("results tab counts", (s1["eligible"], s1["submitted"], s1["not_started"], s1["average"]) == (2, 1, 1, 66.7))

	# Lock after a submission
	quiz.reload()
	quiz.questions[0].is_correct_b = 0
	quiz.questions[0].is_correct_c = 1
	check("locked: correct answer", throws(quiz.save))
	quiz.reload()
	quiz.append("questions", dict(QUESTIONS[2]))
	check("locked: add question", throws(quiz.save))
	quiz.reload()
	quiz.questions[0].question = "Single (changed)"
	check("locked: question text", throws(quiz.save))
	quiz.reload()
	quiz.questions[0].option_a = "x2"
	check("locked: option text", throws(quiz.save))

	# Settings, employee list, formatting-only edits stay open
	quiz.reload()
	for q in quiz.questions:
		q.points = int(q.points)  # what the browser sends back: 1, not 1.0
	quiz.questions[0].question = '<div class="ql-editor read-mode"><p>Single</p></div>'
	quiz.questions[0].explanation = "why"
	quiz.title = "Renamed"
	quiz.bypass_code = "55"
	quiz.time_limit_minutes = 15
	quiz.append("employees", {"employee": e3.name})
	quiz.save()
	check("unlocked: settings, list, formatting", frappe.db.get_value("TIQN Quiz", quiz.name, "bypass_code") == "55")
	quiz.reload()
	quiz.employees = [r for r in quiz.employees if r.employee != e1.name]
	quiz.save()
	check("employee with results can be removed", e1.name not in {r.employee for r in quiz.employees})
	check("removed employee cannot start", throws(lambda: api.start(quiz.slug, e1.name, _day(e1))))
	quiz.append("employees", {"employee": e1.name})
	quiz.save()
	frappe.db.set_value("TIQN Quiz", quiz.name, "bypass_code", "77")

	# Deleting the attempt lets the employee redo the quiz
	frappe.delete_doc(service.RESPONSE_DT, a["response"], ignore_permissions=True)
	check("delete gives the attempt back", api.verify(quiz.slug, e1.name, _day(e1))["attempts_left"] == 1)
	check("delete: can start again as attempt 1", api.start(quiz.slug, e1.name, _day(e1))["attempt_no"] == 1)

	# Expiry: autosaved answers graded, late answers ignored
	b = api.start(quiz.slug, e2.name, "77")
	api.save_progress(b["response"], json.dumps({keys["Single"]: "B"}))
	frappe.db.set_value(service.RESPONSE_DT, b["response"], "deadline", add_to_date(now_datetime(), minutes=-5))
	check("late save refused", api.save_progress(b["response"], json.dumps({keys["TF"]: "A"}))["saved"] is False)
	late = api.submit(b["response"], json.dumps({keys["Single"]: "B", keys["TF"]: "A", keys["Multi"]: "A,C"}))
	check("expired graded from autosave", late["status"] == "Expired" and late["score"] == 2)

	# Closed quiz
	frappe.db.set_value("TIQN Quiz", quiz.name, "status", "Closed")
	check("closed: start blocked", throws(lambda: api.start(quiz.slug, e2.name, "77")))
	check("closed: page told", api.get_quiz(quiz.slug)["is_open"] is False)


def test_all_employees_latest(emps):
	e1, e2, e3 = emps
	quiz = _quiz([], all_employees=1, max_attempts=0, show_result="Score + correct answers")
	keys = _keys(quiz)
	active = frappe.db.count("Employee", {"status": "Active"})
	check("all employees listed", len(api.get_employees(quiz.slug)) == active)

	a = api.start(quiz.slug, e3.name, "77")
	quiz.reload()
	check("no row added to the list", not quiz.employees)
	full = {keys["Single"]: "B", keys["Multi"]: "A,C", keys["TF"]: "A", keys["Text"]: "A"}
	r = api.submit(a["response"], json.dumps(full))
	check("100% passed", r["percentage"] == 100 and r["passed"] == 1)
	check("details shown", len(r["details"]) == 5 and r["attempts_left"] is None)

	b = api.start(quiz.slug, e3.name, "77")
	check("attempt numbers go up", b["attempt_no"] == 2)
	api.submit(b["response"], json.dumps({keys["Single"]: "B"}))
	check("latest attempt counts", float(service.latest_results(quiz.name)[e3.name].percentage) == 33.33)

	summary = admin.get_results_summary(quiz.name)
	check("summary: latest counts", summary["submitted"] == 1 and summary["passed"] == 0)
	check("summary: eligible = all active", summary["eligible"] == active and summary["not_started"] == active - 1)
	single = [q for q in summary["questions"] if q["question"] == "Single"][0]
	check("per-question stats", single["total"] == 2 and single["correct_pct"] == 100)


def test_admin(emps):
	e1, e2, e3 = emps
	quiz = _quiz([e1], status="Draft")
	digits = e2.name.split("-")[-1].lstrip("0")
	r = picker.resolve_codes(f"{e1.name}\n{digits}\nNOPE-1, {e3.name.lower()}, {e1.name}")
	check(
		"paste codes resolved",
		[x.employee for x in r["rows"]] == [e1.name, e2.name, e3.name] and r["not_found"] == ["NOPE-1"],
	)
	check("paste codes rows carry name", r["rows"][0].employee_name and "status" not in r["rows"][0])
	left = frappe.db.get_value("Employee", {"status": "Left"})
	if left:
		check("paste codes flags not active", picker.resolve_codes(left)["not_active"] == [left])
	rows = picker.find_employees(date_from="2000-01-01")
	check("find employees", len(rows) >= 3 and rows[0].employee and "employee_name" in rows[0])
	recent = picker.find_employees(date_from=frappe.utils.add_days(frappe.utils.today(), -14))
	check("find employees by joining date", len(recent) <= len(rows))
	old = quiz.slug
	check("qr svg", admin.get_qr_svg(quiz.name).lstrip().startswith("<"))
	check("preview works in draft", len(api.preview_start(quiz.slug)["questions"]) == 5)
	frappe.set_user("Guest")
	try:
		check("preview needs a role", throws(lambda: api.preview_start(old), frappe.PermissionError))
		check("picker needs a role", throws(lambda: picker.find_employees(), frappe.PermissionError))
	finally:
		frappe.set_user("Administrator")


def test_rich_question(emps):
	html_q = '<div class="ql-editor read-mode"><p><strong>Chọn</strong> đáp án <em>đúng</em> &amp; nhanh</p></div>'
	check("html kept", grading.question_html(html_q) == html_q)
	check("plain escaped", grading.question_html("a < b\nc") == "a &lt; b<br>c")
	check("plain text for labels", grading.question_text(html_q) == "Chọn đáp án đúng & nhanh")
	quiz = _quiz(emps[:1], questions=[dict(QUESTIONS[0], question=html_q)])
	a = api.start(quiz.slug, emps[0].name, "77")
	check("page gets html", a["questions"][0]["question"] == html_q)
	r = frappe.get_doc(service.RESPONSE_DT, a["response"])
	service.finalize(quiz, r, {quiz.questions[0].q_key: "B"})
	check("snapshot keeps html", "<strong>" in r.answers[0].question)
	cols = _detail({"quiz": quiz.name})[0]
	check("report label is plain", any(c["label"] == "1. Chọn đáp án đúng & nhanh" for c in cols))
	long_q = "Trong trường hợp xảy ra tranh chấp, bất đồng với đồng nghiệp, cách xử lý phù hợp nhất là gì?"
	lq = _quiz(emps[:1], status="Draft", questions=[dict(QUESTIONS[0], question=long_q)])
	check("report label not truncated", any(c["label"] == "1. " + long_q for c in _detail({"quiz": lq.name})[0]))
	empty = [dict(QUESTIONS[0], question="<p><br></p>")]
	check("empty rich question rejected", throws(lambda: _quiz(emps[:1], questions=empty)))


def test_no_verification(emps):
	e1 = emps[0]
	check("verify on by default", _quiz(emps[:1], status="Draft").verify_by_dob == 1)
	quiz = _quiz(emps[:1], verify_by_dob=0, bypass_code="")
	check("page told no code", api.get_quiz(quiz.slug)["require_code"] is False)
	check("no code: verify passes", api.verify(quiz.slug, e1.name, "")["valid"])
	check("no code: any input passes", api.verify(quiz.slug, e1.name, _wrong_day(e1))["valid"])
	check("no code: start", bool(api.start(quiz.slug, e1.name, "")["response"]))
	check("no code: list still enforced", throws(lambda: api.start(quiz.slug, emps[1].name, "")))
	check("with code: page told", api.get_quiz(_quiz(emps[:1]).slug)["require_code"] is True)


def _detail(filters):
	return result_report.execute(dict(filters, detail=1))


def test_reports(emps):
	e1, e2, e3 = emps
	quiz = _quiz([e1, e2], max_attempts=0)
	keys = _keys(quiz)
	for answers in ({keys["Single"]: "B", keys["Text"]: "A"}, {keys["Single"]: "C"}):
		a = api.start(quiz.slug, e1.name, "77")
		api.submit(a["response"], json.dumps(answers))

	cols, rows, _m, _c, cards = _detail({"quiz": quiz.name})
	check("detail: 1 row per attempt", len(rows) == 2 and rows[0].attempt_no == 1)
	check("detail: answer + points per question", len([c for c in cols if c["fieldname"].startswith(("a_", "p_"))]) == 10)
	check("detail: compact info columns first", [c["fieldname"] for c in cols][:2] == ["employee", "employee_name"]
		and len([c for c in cols if not c["fieldname"].startswith(("a_", "p_"))]) == 9)
	check("quiz picked: no quiz/title columns", not any(c["fieldname"] in ("quiz", "quiz_title") for c in cols))
	check("detail: answer text", rows[0][f"a_{keys['Single']}"] == "y" and rows[0][f"p_{keys['Single']}"] == 2)
	check("detail: unanswered 0-point question", rows[0][f"p_{keys['Survey']}"] == 0)
	check("detail: correctness flag", rows[1][f"ok_{keys['Single']}"] == 0)
	check("detail: duration text", rows[0].duration.count(":") == 1)
	cols_nq, _d, msg, _c, _cards = _detail({})
	check("detail without quiz: message, no question columns", msg and not any(c["fieldname"].startswith("a_") for c in cols_nq))
	plain_cols = result_report.execute({"quiz": quiz.name})[0]
	check("no detail: no question columns", not any(c["fieldname"].startswith(("a_", "p_")) for c in plain_cols))
	counted = _detail({"quiz": quiz.name, "counted_only": 1})[1]
	check("detail: counted attempt = latest", len(counted) == 1 and counted[0].attempt_no == 2)
	check("detail: cards", cards[0]["value"] == 2)

	rows = result_report.execute({"quiz": quiz.name, "include_not_started": 1})[1]
	check("summary: + not started", [r.status for r in rows] == ["Submitted", "Submitted", "Not Started"])
	check("summary: result text", rows[0].result and rows[1].result)
	check("summary: passed filter", result_report.execute({"quiz": quiz.name, "result": "Not Passed"})[1].__len__() == 2)
	check("summary: no not-started without flag", len(result_report.execute({"quiz": quiz.name})[1]) == 2)
	d_rows = _detail({"quiz": quiz.name, "include_not_started": 1})[1]
	check("detail: + not started", [r.status for r in d_rows] == ["Submitted", "Submitted", "Not Started"])
	check("detail: not started has no answers", not any(k.startswith("a_") for k in d_rows[-1]))
	check("detail: result filter", len(_detail({"quiz": quiz.name, "result": "Not Passed"})[1]) == 2)
	check("detail: result filter hides not started",
		all(r.status != "Not Started" for r in _detail({"quiz": quiz.name, "result": "Passed", "include_not_started": 1})[1]))
	section = frappe.db.get_value("Employee", e1.name, "custom_section")
	check("attempt stamped with section", rows[0].custom_section == section)
	if section:
		check("summary: section filter", len(result_report.execute({"quiz": quiz.name, "section": section})[1]) == 2)
		check("detail: section filter", len(_detail({"quiz": quiz.name, "section": section})[1]) == 2)
		check("picker: section filter", all(r.custom_section == section for r in picker.find_employees(section=section)))
	check("summary: other section empty", result_report.execute({"quiz": quiz.name, "section": "__none__"})[1] == [])


def run():
	RESULTS.clear()
	frappe.set_user("Administrator")
	try:
		emps = _employees(3)
		test_grading()
		test_validation(emps)
		test_guest_flow(emps)
		test_all_employees_latest(emps)
		test_admin(emps)
		test_reports(emps)
		test_no_verification(emps)
		test_rich_question(emps)
	finally:
		frappe.db.rollback()
	failed = [n for n, ok in RESULTS if not ok]
	for n, ok in RESULTS:
		print(("PASS " if ok else "FAIL ") + n)
	print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} passed")
	return {"passed": len(RESULTS) - len(failed), "failed": failed}
