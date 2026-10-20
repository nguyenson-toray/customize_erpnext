# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Grading for TIQN Quiz — pure functions, no DB access.

A question is a TIQN Quiz Question row or a plain dict with the same keys.
Every question is multiple choice (single or multiple correct options) — free
text was dropped on purpose: it cannot be graded automatically (user, 20/10/2026).
An answer is what the quiz page sends per q_key: "A" or "A,C".
"""

import html
import re

from frappe.utils import flt, strip_html

LETTERS = "ABCDEF"
OPTION_FIELDS = [f"option_{c.lower()}" for c in LETTERS]
CORRECT_FIELDS = [f"is_correct_{c.lower()}" for c in LETTERS]


def parse_letters(value):
	"""'c, a' / 'AC' / ['a'] -> ['A', 'C'] (sorted, unique, only A-F)."""
	if isinstance(value, (list, tuple)):
		value = ",".join(str(v) for v in value)
	return sorted(set(re.findall(f"[{LETTERS}]", str(value or "").upper())))


def question_html(value):
	"""Question is a Text Editor field; questions typed before that are plain text."""
	value = value or ""
	if re.search(r"<[a-zA-Z][^>]*>", value):
		return value
	return html.escape(value).replace("\n", "<br>")


def question_text(value):
	"""Plain one-line text of a question — report column labels, Desk tables."""
	return " ".join(html.unescape(strip_html(value or "")).split())


def filled_letters(q):
	return [letter for letter, field in zip(LETTERS, OPTION_FIELDS) if (q.get(field) or "").strip()]


def ticked_letters(q):
	return [letter for letter, field in zip(LETTERS, CORRECT_FIELDS) if q.get(field)]


def derive_type(q):
	"""Question type and correct letters from the Correct ticks:
	2+ ticked -> Multiple choice, otherwise Single choice."""
	filled = filled_letters(q)
	correct = [letter for letter in ticked_letters(q) if letter in filled]
	return ("Multiple choice" if len(correct) > 1 else "Single choice"), correct


def options(q):
	"""[(letter, text)] the employee can pick from, in A-F order."""
	out = []
	for letter, field in zip(LETTERS, OPTION_FIELDS):
		text = (q.get(field) or "").strip()
		if text:
			out.append((letter, text))
	return out


def max_points(q):
	return flt(q.get("points"))


def _texts(q, letters):
	labels = dict(options(q))
	return "; ".join(labels.get(letter, letter) for letter in letters)


def answer_text(q, answer):
	return _texts(q, parse_letters(answer))


def correct_text(q):
	return _texts(q, parse_letters(q.get("correct_options")))


def grade_question(q, answer):
	"""All or nothing (like MS Forms): exactly the correct options, or 0.
	-> {is_correct, points_awarded, points_max}"""
	points = flt(q.get("points"))
	correct = parse_letters(q.get("correct_options"))
	ok = bool(correct) and parse_letters(answer) == correct
	return {"is_correct": int(ok), "points_awarded": points if ok else 0.0, "points_max": points}


def grade(questions, answers, pass_percentage=0):
	"""Grade every question (in the given order) against answers {q_key: value}.

	-> {rows: [...], score, max_score, percentage, passed}
	"""
	answers = answers or {}
	rows = []
	for q in questions:
		answer = answers.get(q.get("q_key"))
		res = grade_question(q, answer)
		rows.append(
			{
				"q_key": q.get("q_key"),
				"question": question_html(q.get("question")),
				"selected": ",".join(parse_letters(answer)),
				"answer_text": answer_text(q, answer),
				"correct_text": correct_text(q),
				**res,
			}
		)

	score = round(sum(r["points_awarded"] for r in rows), 2)
	max_score = round(sum(r["points_max"] for r in rows), 2)
	percentage = round(score / max_score * 100, 2) if max_score else 0.0
	# Every question worth 0 points: nothing to fail.
	passed = percentage >= flt(pass_percentage) if max_score else True
	return {"rows": rows, "score": score, "max_score": max_score, "percentage": percentage, "passed": int(passed)}
