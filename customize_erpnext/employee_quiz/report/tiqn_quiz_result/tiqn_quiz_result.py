# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Quiz results, one row per attempt (optionally + listed employees who have
not started). Tick "Detail" for the MS Forms results-Excel layout: one answer +
points column pair per question — needs a single quiz, its questions are the
columns."""

import frappe
from frappe import _
from frappe.utils import cint

from customize_erpnext.employee_quiz.grading import question_text
from customize_erpnext.employee_quiz.report.quiz_report_utils import (
	base_columns,
	finish_row,
	get_responses,
	not_started_rows,
	summary_cards,
)

# Detail keeps only these info columns (like the MS Forms results Excel) so the
# question columns start on screen instead of after 15 columns.
DETAIL_INFO = (
	"employee", "employee_name", "custom_section", "custom_group",
	"started_at", "submitted_at", "score", "percentage", "result",
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columns = base_columns()
	if not filters.get("quiz"):  # one quiz picked: the same value on every row
		columns = [
			{"fieldname": "quiz", "label": _("Quiz"), "fieldtype": "Link", "options": "TIQN Quiz", "width": 120},
			{"fieldname": "quiz_title", "label": _("Quiz Title"), "fieldtype": "Data", "width": 220},
			*columns,
		]
	data = [finish_row(r) for r in get_responses(filters)]

	message = None
	if cint(filters.get("detail")):
		if filters.get("quiz"):
			columns = [c for c in columns if c["fieldname"] in DETAIL_INFO] + _question_columns(filters.quiz)
			_add_answers(data)
		else:
			message = _("Pick a Quiz to see the answer of every question.")

	data += not_started_rows(filters)  # no answers, so question columns stay empty
	return columns, data, message, None, summary_cards(data)


def _question_columns(quiz):
	columns = []
	for q in frappe.get_doc("TIQN Quiz", quiz).questions:
		# Full question text: the Excel export uses this label as is; on screen
		# the column header is ellipsised to its width anyway.
		label = f"{q.idx}. {question_text(q.question)}"
		columns.append({"fieldname": f"a_{q.q_key}", "label": label, "fieldtype": "Data", "width": 220})
		columns.append(
			{
				"fieldname": f"p_{q.q_key}",
				"label": _("Points - Q{0}").format(q.idx),
				"fieldtype": "Float",
				"precision": 2,
				"width": 95,
			}
		)
	return columns


def _add_answers(rows):
	if not rows:
		return
	by_response = {}
	for a in frappe.get_all(
		"TIQN Quiz Answer",
		filters={"parent": ["in", [r.name for r in rows]], "parenttype": "TIQN Quiz Response"},
		fields=["parent", "q_key", "answer_text", "points_awarded", "is_correct"],
	):
		by_response.setdefault(a.parent, []).append(a)
	for row in rows:
		for a in by_response.get(row.name, ()):
			row[f"a_{a.q_key}"] = a.answer_text
			row[f"p_{a.q_key}"] = a.points_awarded
			# Read by the JS formatter to colour the answer cell; not a column.
			row[f"ok_{a.q_key}"] = cint(a.is_correct)
