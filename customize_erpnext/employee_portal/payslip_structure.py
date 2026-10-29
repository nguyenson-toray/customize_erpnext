# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Payslip lines per pay period (28/10/2026) - TIQN Payslip Structure.

C&B may add, remove, rename lines and change the formula text from one month to the
next without IT. A structure applies from its `valid_from` period until the next one.

Each TIQN Payslip keeps its OWN copy of the lines (`lines_json`, the "snapshot"): code,
labels, layout and the numbers HR imported. The Mini App (`rows`, `sections`), the
printout and the reports read the snapshot only, so a later structure never changes a
payslip already imported. Labels of imported payslips change only through
`apply_labels` (numbers never).

Numbers are 100% HR's: nothing here checks or computes a formula (user, 28/10/2026).
`absurd_errors` only refuses numbers that cannot be right (negative days / hours, more
working days than the period has, an amount mistyped by several digits).
"""

import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import date_diff, flt

from customize_erpnext.employee_portal.utils import code_key, period_bounds, shift_period

STRUCTURE_DT = "TIQN Payslip Structure"
PAYSLIP_DT = "TIQN Payslip"
CODE_FORMAT = re.compile(r"^\d+(?:\.\d+)*$")
UNITS = {"VND": "VND", "Day": "DAY", "Hour": "HOUR"}
# `section` of a line -> (key, label, sign) of the deprecated `sections` payload (Mini
# App builds before 1.3.0 still read it). "Net Pay" is in no block.
SECTIONS = [
	("Earnings", "EARNINGS", "Earnings", 1),
	("Deductions", "DEDUCTIONS", "Deductions", -1),
	("Others", "OTHERS", "Other Items", 1),
	("Adjustment", "ADJUSTMENT", "Adjustment for Previous Month", 1),
	("Attendance", "ATTENDANCE", "Attendance & Overtime", 0),
]
# Line fields that shape the payslip. Locked once payslips use the structure; the
# label fields may still change (then apply_labels).
STRUCTURAL = ("code", "unit", "quantity_unit", "parent_code", "row_type", "section", "report_key")
LABELS = ("label_en", "label_vi", "formula_display")
# report_key -> TIQN Payslip column. Money keys take the amount, the others the days /
# hours; OT Hours adds up every line that carries it.
MONEY_KEYS = {
	"Basic": "basic_pay",
	"Overtime": "overtime_pay",
	"Gross": "gross_pay",
	"Deductions": "total_deductions",
	"Net": "net_pay",
}
QUANTITY_KEYS = {"Standard Days": "standard_days", "Actual Days": "actual_days", "OT Hours": "ot_hours"}
KEY_FIELDS = {**MONEY_KEYS, **QUANTITY_KEYS}
SUMMED_KEYS = ("OT Hours",)
MAX_AMOUNT = 10**11  # 100 billion VND on one line = digits typed twice


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------
def structure_for_period(period):
	"""Name of the structure that applies to `period` (YYYY-MM), None when none does."""
	if not period:
		return None
	return frappe.db.get_value(
		STRUCTURE_DT, {"valid_from": ("<=", period)}, "name", order_by="valid_from desc"
	)


def refresh_valid_to():
	"""Valid To Period of every structure = the period before the next one's Valid From
	(empty for the last). Derived, so recomputed after any insert / change / delete."""
	rows = frappe.get_all(STRUCTURE_DT, fields=["name", "valid_from", "valid_to"], order_by="valid_from asc")
	for row, nxt in zip(rows, rows[1:] + [None]):
		valid_to = shift_period(nxt.valid_from, -1) if nxt else ""
		if (row.valid_to or "") != valid_to:
			frappe.db.set_value(STRUCTURE_DT, row.name, "valid_to", valid_to, update_modified=False)


def structure_lines(name):
	"""Lines of a structure, in code order, as plain dicts."""
	doc = frappe.get_doc(STRUCTURE_DT, name)
	return sorted(
		(frappe._dict({f: row.get(f) or None for f in STRUCTURAL + LABELS}) for row in doc.lines),
		key=lambda r: code_key(r.code),
	)


def period_structure_lines(period):
	"""(structure name, lines) for `period`; throws when no structure covers it."""
	name = structure_for_period(period)
	if not name:
		frappe.throw(
			_("No Payslip Structure covers period {0}. Create one (Valid From Period on or before it) first.").format(period)
		)
	return name, structure_lines(name)


def clean_line(row):
	"""Trim what C&B typed; formula text without its brackets ("(c=a+b)" -> "c=a+b")."""
	row.code = (row.code or "").strip()
	row.parent_code = (row.parent_code or "").strip() or None
	for f in ("label_en", "label_vi"):
		row.set(f, " ".join((row.get(f) or "").split()))
	formula = " ".join((row.formula_display or "").split())
	# Only one pair around everything: "(a) + (b)" keeps its brackets.
	if formula.startswith("(") and formula.endswith(")") and "(" not in formula[1:-1] and ")" not in formula[1:-1]:
		formula = formula[1:-1].strip()
	row.formula_display = formula or None
	row.quantity_unit = row.quantity_unit or None
	row.report_key = row.report_key or None


def validate_lines(lines):
	"""Only what cannot be right - never the formulas (HR's numbers, HR's rules)."""
	if not lines:
		frappe.throw(_("A Payslip Structure needs at least one line."))
	codes = {}
	for row in lines:
		label = _("Row {0}").format(row.get("idx") or len(codes) + 1)
		if not CODE_FORMAT.match(row.code or ""):
			frappe.throw(_("{0}: No. \"{1}\" must be numbers separated by dots, e.g. 1, 1.2, 7.4.").format(label, row.code or ""))
		if row.code in codes:
			frappe.throw(_("No. {0} is used twice.").format(row.code))
		codes[row.code] = row
		if not row.label_en or not row.label_vi:
			frappe.throw(_("Line {0}: English Label and Vietnamese Label are required.").format(row.code))
		if row.unit != "VND" and row.quantity_unit:
			frappe.throw(
				_("Line {0}: a {1} line has no Unit/ĐVT Column - its number already is the days / hours.").format(row.code, _(row.unit))
			)
	for row in lines:
		parent, seen = row.parent_code, {row.code}
		if parent and parent not in codes:
			frappe.throw(_("Line {0}: Under Line {1} does not exist.").format(row.code, parent))
		while parent:
			if parent in seen:
				frappe.throw(_("Line {0}: Under Line goes round in a loop.").format(row.code))
			seen.add(parent)
			parent = codes[parent].parent_code
	keys = {}
	for row in lines:
		if not row.report_key:
			continue
		if row.report_key in keys and row.report_key not in SUMMED_KEYS:
			frappe.throw(_("Report Column {0} is set on lines {1} and {2}.").format(_(row.report_key), keys[row.report_key], row.code))
		keys.setdefault(row.report_key, row.code)
		if row.report_key in MONEY_KEYS and row.unit != "VND":
			frappe.throw(_("Line {0}: Report Column {1} needs a VND line.").format(row.code, _(row.report_key)))
		if row.report_key in QUANTITY_KEYS and row.unit == "VND" and not row.quantity_unit:
			frappe.throw(_("Line {0}: Report Column {1} needs days / hours.").format(row.code, _(row.report_key)))
	if "Net" not in keys:
		frappe.throw(_("Set Report Column = Net on the net salary line."))
	totals = {}
	for row in lines:
		if row.row_type == "Section Total":
			if row.section in totals:
				frappe.throw(
					_("Block {0} has two Section Total lines: {1} and {2}.").format(_(row.section), totals[row.section], row.code)
				)
			totals[row.section] = row.code


def structural_signature(lines):
	return [tuple(str(r.get(f) or "") for f in STRUCTURAL) for r in sorted(lines, key=lambda r: code_key(r.code))]


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------
def make_snapshot(lines, values=None):
	"""The payslip's own copy of `lines` + numbers. `values` = {code: {"amount", "quantity"}}
	(a missing code = 0). Amounts / days are kept as HR typed them, rounded only on output."""
	values = values or {}
	by_code = {r["code"]: r for r in lines}
	has_children = {r.get("parent_code") for r in lines if r.get("parent_code") in by_code}

	def level(r):
		depth, seen, p = 0, {r["code"]}, r.get("parent_code")
		while p in by_code and p not in seen:
			depth += 1
			seen.add(p)
			p = by_code[p].get("parent_code")
		return depth

	out = []
	for r in sorted(lines, key=lambda r: code_key(r["code"])):
		v = values.get(r["code"]) or {}
		vnd = (r.get("unit") or "VND") == "VND"
		has_quantity = not vnd or bool(r.get("quantity_unit"))
		line = {f: r.get(f) or None for f in STRUCTURAL + LABELS}
		line["unit"] = r.get("unit") or "VND"
		line["row_type"] = r.get("row_type") or "Line"
		line.update(
			{
				"level": level(r),
				"is_header": line["row_type"] != "Line" or r["code"] in has_children,
				"amount": flt(v.get("amount")) if vnd else None,
				"quantity": flt(v.get("quantity")) if has_quantity else None,
			}
		)
		out.append(line)
	return out


def snapshot_of(doc):
	return [frappe._dict(r) for r in json.loads(doc.get("lines_json") or "[]")]


def snapshot_values(snapshot):
	return {r["code"]: {"amount": r.get("amount"), "quantity": r.get("quantity")} for r in snapshot}


def dump_snapshot(snapshot):
	return json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))


def content_version(snapshot):
	"""Changes whenever anything shown changes (labels included) - with published_on, the
	Mini App's cache key from contract 1.9.0."""
	return hashlib.sha1(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def key_values(snapshot):
	"""{TIQN Payslip column: value} of the lines that carry a Report Column."""
	out = {f: 0.0 for f in KEY_FIELDS.values()}
	for r in snapshot:
		key = r.get("report_key")
		if key in MONEY_KEYS:
			out[MONEY_KEYS[key]] = flt(r.get("amount"))
		elif key in QUANTITY_KEYS:
			out[QUANTITY_KEYS[key]] += flt(r.get("quantity"))
	return out


def quantity_unit_of(r):
	return r.get("unit") if (r.get("unit") or "VND") != "VND" else r.get("quantity_unit")


def absurd_errors(snapshot, period):
	"""Numbers that cannot be right, whatever HR's rules: negative days / hours on any line;
	on an Attendance line (working days, overtime hours) more days - or 24 h x days - than
	the period has; an amount of 100 billion or more. Days paid out elsewhere (e.g. unused
	annual leave in a final settlement) may exceed the period, so only Attendance is bounded."""
	errors = []
	start, end = period_bounds(period)
	days = date_diff(end, start) + 1
	for r in snapshot:
		q, unit = r.get("quantity"), quantity_unit_of(r)
		if q is not None and unit:
			if flt(q) < 0:
				errors.append(_("{0}: {1} {2} cannot be negative.").format(r["code"], q, _(unit + "s")))
			elif r.get("section") != "Attendance":
				pass
			elif unit == "Day" and flt(q) > days:
				errors.append(_("{0}: {1} days is more than the {2} days of the period.").format(r["code"], q, days))
			elif unit == "Hour" and flt(q) > 24 * days:
				errors.append(_("{0}: {1} hours is more than 24 hours x {2} days of the period.").format(r["code"], q, days))
		if r.get("amount") is not None and abs(flt(r["amount"])) >= MAX_AMOUNT:
			errors.append(_("{0}: {1:,.0f} VND looks mistyped.").format(r["code"], flt(r["amount"])))
	return errors


# ---------------------------------------------------------------------------
# Output (Mini App rows / sections, printout)
# ---------------------------------------------------------------------------
def output_amount(value, unit):
	if unit == "VND":
		return int(round(flt(value)))
	value = round(flt(value), 2)
	return int(value) if value == int(value) else value


def display_label(r):
	"""Mini App text as shown: "9 Thực lĩnh (j=f-g+h+i)"."""
	text = f"{r['code']} {r.get('label_vi') or ''}".strip()
	return f"{text} ({r['formula_display']})" if r.get("formula_display") else text


def rows_from_snapshot(snapshot, include_zero=True):
	"""`rows` (contract 1.3.0): the paper payslip line by line, amounts positive as printed."""
	rows = []
	for r in snapshot:
		unit = UNITS.get(r.get("unit") or "VND", "VND")
		if unit == "VND":
			amount = output_amount(r.get("amount"), unit)
			quantity_unit = UNITS.get(r["quantity_unit"]) if r.get("quantity_unit") else None
			quantity = output_amount(r.get("quantity"), quantity_unit) if quantity_unit else None
		else:  # days / hours only (1.1): nothing in the Amount column
			amount, quantity, quantity_unit = None, output_amount(r.get("quantity"), unit), unit
		if not include_zero and not r.get("is_header") and not amount and not quantity:
			continue
		rows.append(
			{
				"no": r["code"],
				"display_label": display_label(r),
				"label": r.get("label_vi") or r.get("label_en") or r["code"],
				"formula": re.sub(r"\s+", "", r.get("formula_display") or "") or None,
				"quantity": quantity,
				"quantity_unit": quantity_unit,
				"amount": amount,
				"level": r.get("level") or 0,
				"is_header": bool(r.get("is_header")),
			}
		)
	return rows


def sections_from_snapshot(snapshot, include_zero=True):
	"""Deprecated `sections` (Mini App builds before 1.3.0 still read it), same blocks and
	rules as before the structures: the details of the Attendance block show their days /
	hours, a Section Total line is the block total, Net Pay is in no block."""
	amounts, units = {}, {}
	for r in snapshot:
		if r.get("section") == "Attendance" and r.get("quantity_unit"):
			amounts[r["code"]], units[r["code"]] = flt(r.get("quantity")), r["quantity_unit"]
		elif (r.get("unit") or "VND") == "VND":
			amounts[r["code"]], units[r["code"]] = flt(r.get("amount")), "VND"
		else:
			amounts[r["code"]], units[r["code"]] = flt(r.get("quantity")), r["unit"]

	def line(r, children):
		unit = UNITS.get(units[r["code"]], "VND")
		return {
			"code": r["code"],
			"label": r.get("label_vi") or r.get("label_en") or r["code"],
			"amount": output_amount(amounts[r["code"]], unit),
			"unit": unit,
			"is_total": r.get("row_type") == "Subtotal",
			"children": children,
		}

	sections = []
	for section_value, key, label, sign in SECTIONS:
		members = [r for r in snapshot if r.get("section") == section_value]
		total_line = next((m for m in members if m.get("row_type") == "Section Total"), None)
		body = [m for m in members if m.get("row_type") != "Section Total"]
		codes_in_body = {m["code"] for m in body}

		def build(parent_code):
			out = []
			for m in body:
				parent = m.get("parent_code")
				parent = parent if parent in codes_in_body and parent != m["code"] else None
				if parent != parent_code:
					continue
				children = build(m["code"])
				if m.get("row_type") == "Subtotal" or include_zero or amounts[m["code"]] != 0:
					out.append(line(m, children))
			return out

		lines = build(None)
		unit = None if sign == 0 else "VND"
		total = None
		if total_line:
			total = output_amount(amounts[total_line["code"]], UNITS.get(units[total_line["code"]], "VND"))
		elif sign != 0:
			total = 0
		if not lines and total in (None, 0) and not total_line:
			continue
		sections.append(
			{"key": key, "label": _(label, context="Payslip"), "sign": sign, "total": total, "unit": unit, "lines": lines}
		)
	return sections


# ---------------------------------------------------------------------------
# Apply Labels to Payslips (labels only - never a number)
# ---------------------------------------------------------------------------
def label_changes(name):
	"""[(code, field, old, new, payslips)] between the structure and its payslips."""
	labels = {r.code: r for r in structure_lines(name)}
	changes = {}
	for ps in frappe.get_all(PAYSLIP_DT, {"structure": name}, ["name", "lines_json"]):
		for r in json.loads(ps.lines_json or "[]"):
			new = labels.get(r["code"])
			if not new:
				continue
			for f in LABELS:
				if (r.get(f) or None) != (new.get(f) or None):
					key = (r["code"], f, r.get(f) or "", new.get(f) or "")
					changes.setdefault(key, set()).add(ps.name)
	return [(*k, len(v)) for k, v in sorted(changes.items(), key=lambda kv: (code_key(kv[0][0]), kv[0][1]))]


def apply_labels(name):
	"""Copy the structure's labels into its payslips' snapshots. Numbers, published_on and
	modified stay; no notification. Returns the number of payslips changed."""
	labels = {r.code: r for r in structure_lines(name)}
	changed = 0
	for ps in frappe.get_all(PAYSLIP_DT, {"structure": name}, ["name", "lines_json"]):
		snapshot = json.loads(ps.lines_json or "[]")
		dirty = False
		for r in snapshot:
			new = labels.get(r["code"])
			for f in LABELS if new else ():
				if (r.get(f) or None) != (new.get(f) or None):
					r[f] = new.get(f) or None
					dirty = True
		if dirty:
			frappe.db.set_value(
				PAYSLIP_DT,
				ps.name,
				{"lines_json": dump_snapshot(snapshot), "content_version": content_version(snapshot)},
				update_modified=False,
			)
			changed += 1
	return changed
