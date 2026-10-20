# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Desk actions on TIQN Quiz (tiqn_quiz.js): the QR code and the Results tab."""

import frappe
from frappe.utils import cint, flt

from customize_erpnext.api.qr_svg import make_qr_svg
from customize_erpnext.employee_quiz import grading, service


@frappe.whitelist()
def get_qr_svg(quiz):
	doc = frappe.get_doc("TIQN Quiz", quiz)
	doc.check_permission("read")
	return make_qr_svg(doc.quiz_link)


@frappe.whitelist()
def get_results_summary(quiz):
	"""Results tab. Per employee, the latest submitted attempt counts."""
	doc = frappe.get_doc("TIQN Quiz", quiz)
	doc.check_permission("read")

	eligible = {r.employee for r in service.eligible_employees(doc)}
	latest = service.latest_results(doc.name)
	started = set(frappe.get_all(service.RESPONSE_DT, filters={"quiz": doc.name}, pluck="employee", distinct=True))
	done = list(latest.values())
	summary = {
		"eligible": len(eligible),
		"not_started": len(eligible - started),
		"in_progress": len(started - set(latest)),
		"submitted": len(done),
		"passed": sum(1 for r in done if r.passed),
		"average": round(sum(flt(r.percentage) for r in done) / len(done), 1) if done else 0,
	}

	# % correct per question, over every submitted attempt.
	stats = frappe.db.sql(
		"""
		select a.q_key, count(*) total, sum(a.is_correct) correct
		from `tabTIQN Quiz Answer` a
		join `tabTIQN Quiz Response` r on r.name = a.parent
		where r.quiz = %s and r.status in ('Submitted', 'Expired')
		group by a.q_key
		""",
		quiz,
		as_dict=True,
	)
	by_key = {s.q_key: s for s in stats}
	summary["questions"] = [
		{
			"idx": q.idx,
			"question": grading.question_text(q.question),
			"total": cint(by_key[q.q_key].total) if q.q_key in by_key else 0,
			"correct_pct": round(flt(by_key[q.q_key].correct) / by_key[q.q_key].total * 100)
			if q.q_key in by_key and by_key[q.q_key].total
			else None,
		}
		for q in doc.questions
	]
	return summary
