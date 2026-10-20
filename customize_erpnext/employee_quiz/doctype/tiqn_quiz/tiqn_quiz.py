# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_url

from customize_erpnext.employee_quiz import grading

COUNTED_STATUSES = ("Submitted", "Expired")


def quiz_url(slug):
	return get_url(f"/quiz?f={slug}")


def question_signature(q):
	"""What a question asks and how it is graded — frozen once attempts exist.

	Values are normalised: the form sends 1 where the DB holds 1.0, and the Text
	Editor re-wraps old plain-text questions in HTML without changing a word.
	Explanation and image are not part of it (they do not change any score).
	"""
	return (
		grading.question_text(q.get("question")),
		q.get("question_type") or "",
		flt(q.get("points")),
		tuple((q.get(f) or "").strip() for f in grading.OPTION_FIELDS),
		tuple(grading.parse_letters(q.get("correct_options"))),
	)


def has_counted_responses(quiz):
	return bool(frappe.db.exists("TIQN Quiz Response", {"quiz": quiz, "status": ["in", COUNTED_STATUSES]}))


class TIQNQuiz(Document):
	def before_validate(self):
		if not self.slug:
			self.slug = frappe.generate_hash(length=10)
		self.bypass_code = (self.bypass_code or "").strip() or None
		self.quiz_link = quiz_url(self.slug)

	def validate(self):
		# Optional: empty = birth day only.
		if self.bypass_code and not re.fullmatch(r"\d{2}", self.bypass_code):
			frappe.throw(_("Bypass Code must be exactly 2 digits, or empty."))
		if (self.time_limit_minutes or 0) < 0 or (self.max_attempts or 0) < 0:
			frappe.throw(_("Time Limit and Max Attempts cannot be negative."))

		self._validate_questions()
		self._validate_employees()
		self._check_locked_questions()

		self.question_count = len(self.questions)
		self.total_points = sum(grading.max_points(q) for q in self.questions)

		if self.status == "Open":
			if not self.questions:
				frappe.throw(_("Add at least one question before opening the quiz."))
			# An empty Employees list is allowed (user 21/10/2026): nobody can take the
			# quiz until employees are added or All Active Employees is ticked.

	def _validate_questions(self):
		seen = set()
		no_answer = []
		for q in self.questions:
			if not q.q_key or q.q_key in seen:
				q.q_key = frappe.generate_hash(length=8)
			seen.add(q.q_key)

			row = _("Question {0}").format(q.idx)
			if not grading.question_text(q.question) and "<img" not in (q.question or ""):
				frappe.throw(_("{0}: enter the question.").format(row))
			if (q.points or 0) < 0:
				frappe.throw(_("{0}: Points cannot be negative.").format(row))

			# Type and answer key come from the options and their Correct ticks.
			filled = grading.filled_letters(q)
			empty_ticked = [letter for letter in grading.ticked_letters(q) if letter not in filled]
			if empty_ticked:
				frappe.throw(
					_("{0}: option {1} is ticked as correct but has no text.").format(row, ", ".join(empty_ticked))
				)
			q.question_type, correct = grading.derive_type(q)
			q.correct_options = ",".join(correct)

			# Every question is multiple choice: free text cannot be graded automatically.
			if len(filled) < 2:
				frappe.throw(_("{0}: enter at least 2 options.").format(row))
			if not correct:
				# A Draft may wait for its answer key (e.g. questions imported first).
				if self.status != "Draft":
					frappe.throw(_("{0}: tick Correct under the right option(s).").format(row))
				no_answer.append(str(q.idx))

		if no_answer and not frappe.flags.in_test:
			frappe.msgprint(
				_("Questions without a correct answer yet: {0}. The quiz cannot be opened until they have one.").format(
					", ".join(no_answer)
				),
				indicator="orange",
				alert=True,
			)

	def _validate_employees(self):
		seen = set()
		for row in self.employees:
			if row.employee in seen:
				frappe.throw(_("Employee {0} is listed twice.").format(row.employee))
			seen.add(row.employee)

	def _check_locked_questions(self):
		if self.is_new() or not has_counted_responses(self.name):
			return
		before = self.get_doc_before_save()
		if not before:
			return

		def signature(doc):
			return {q.q_key: question_signature(q) for q in doc.questions}

		if signature(before) != signature(self):
			frappe.throw(
				_(
					"This quiz already has submitted attempts, so its questions and answers cannot change "
					"(other settings and the employee list still can). Use Duplicate to make a new version."
				)
			)
