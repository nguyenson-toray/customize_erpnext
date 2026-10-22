# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Labor Contract v3 — one record per paper document (user decision 22/10/2026).

A record is either a Contract (one stage of the fixed chain) or an Appendix (phụ lục)
attached to the contract in force on its effective date. The record name IS the
document number HR prints:

    {employee}-HD    probation (30/60 days)     PL-{employee}-{YYMM}   appendix
    {employee}-HD1   1-year contract                                   (YYMM of the
    {employee}-HD2   3-year contract                                    effective date)
    {employee}-HD3   indefinite-term contract

The DocType only holds what belongs to the document. Employee details (designation,
department, ID card, address…) are pulled by the report / export, and the position on a
given date comes from Internal Work History — see positions_at().

Contracts from before 22/10/2026 were copied in from the old model (labor_contract.md).
"""

import json
import os
from collections import defaultdict
from datetime import date

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_years, cint, formatdate, get_link_to_form, getdate


# =============================================================================
# Contract Sequence
# =============================================================================
# Chuỗi hợp đồng cố định, không nhảy cóc, không có khoảng trống:
#   [30 hoặc 60 ngày thử việc] -> 1 năm -> 3 năm -> không xác định thời hạn
# Tên phải khớp CHÍNH XÁC với record Employment Type thật trong DB.
PROBATION_30 = "30 Days Probationary Contract"
PROBATION_60 = "60 Days Probationary Contract"
CONTRACT_1_YEAR = "1 Year Employment Contract"
CONTRACT_3_YEAR = "3 Year Employment Contract"
CONTRACT_INDEFINITE = "Indefinite-term Employment Contract"

# Từ 1 loại thử việc, giai đoạn kế tiếp luôn là hợp đồng 1 năm (2 loại thử
# việc không nối tiếp nhau nên không thể suy ra bằng SEQUENCE[index + 1]).
NEXT_CONTRACT_TYPE = {
	PROBATION_30: CONTRACT_1_YEAR,
	PROBATION_60: CONTRACT_1_YEAR,
	CONTRACT_1_YEAR: CONTRACT_3_YEAR,
	CONTRACT_3_YEAR: CONTRACT_INDEFINITE,
	CONTRACT_INDEFINITE: None,
}

# Document number suffix per stage (HR's numbering)
CONTRACT_SUFFIX = {
	PROBATION_30: "HD",
	PROBATION_60: "HD",
	CONTRACT_1_YEAR: "HD1",
	CONTRACT_3_YEAR: "HD2",
	CONTRACT_INDEFINITE: "HD3",
}

# Fixed-term contracts run by calendar year: same date N years later, minus one day
# (31/12/2022 -> 30/12/2025). Probation runs by days (Employment Type.custom_period).
CONTRACT_YEARS = {
	CONTRACT_1_YEAR: 1,
	CONTRACT_3_YEAR: 3,
}

CONTRACT = "Contract"
APPENDIX = "Appendix"

# Employee.custom_probation_days (fetch_from Designation) -> loại hợp đồng thử việc
PROBATION_DAYS_TO_CONTRACT_TYPE = {
	"30": PROBATION_30,
	"60": PROBATION_60,
}

# Trường hợp đặc biệt, hiếm: tuyển vào không qua thử việc. Giai đoạn đầu là gì
# (1 năm? 3 năm?) là quyết định nghiệp vụ nên hệ thống KHÔNG đoán — HR tự tạo tay.
NO_PROBATION = "0"

# Lý do bỏ qua, hiển thị cho HR trong bảng kết quả bulk.
# Probation Days TRỐNG = chức danh đặc biệt (giám đốc, trưởng chi nhánh…) không thử
# việc và KHÔNG theo dõi hợp đồng — bỏ qua hẳn, không phải thiếu dữ liệu (user chốt
# 21/10/2026).
SKIP_NO_PROBATION = "no_probation_period"
SKIP_MISSING_PROBATION_DAYS = "missing_probation_days"


def get_next_contract_type(current_type):
	return NEXT_CONTRACT_TYPE.get(current_type)


def classify_probation_days(probation_days):
	"""(contract_type, skip_reason) — đúng một trong hai khác None.
	Tách 0 (cố ý không thử việc) khỏi rỗng (chưa khai báo) để HR nhìn danh sách
	bỏ qua là biết ngay phải sửa dữ liệu hay phải tạo hợp đồng tay."""
	value = (probation_days or "").strip()
	if value == NO_PROBATION:
		return None, SKIP_NO_PROBATION
	contract_type = PROBATION_DAYS_TO_CONTRACT_TYPE.get(value)
	if not contract_type:
		return None, SKIP_MISSING_PROBATION_DAYS
	return contract_type, None


def _probation_skip_message(skip_reason):
	if skip_reason == SKIP_NO_PROBATION:
		return _("No probation period (0) — create the contract manually")
	return _("No Probation Days — no contract needed")


def compute_end_date(contract_type, start_date, period=None):
	"""Last day of a contract stage, None for indefinite-term.

	Probation: start + period − 1 (30/60 days). 1-year / 3-year: the same date
	N years later − 1. A 29/02 start counts as 01/03, so its 1-year contract ends
	on 28/02 (plain add_years would land on 28/02 and give 27/02).
	`period` (Employment Type.custom_period) can be passed in to skip the lookup.
	"""
	if not (contract_type and start_date):
		return None
	start = getdate(start_date)

	years = CONTRACT_YEARS.get(contract_type)
	if years:
		base = date(start.year, 3, 1) if (start.month, start.day) == (2, 29) else start
		return add_days(add_years(base, years), -1)

	if period is None:
		period = cint(frappe.db.get_value("Employment Type", contract_type, "custom_period"))
	return add_days(start, period - 1) if period else None


def document_number(document_type, employee, contract_type=None, start_date=None):
	"""Base document number (without the -2/-3 duplicate suffix)."""
	if document_type == APPENDIX:
		return f"PL-{employee}-{getdate(start_date):%y%m}"
	return f"{employee}-{CONTRACT_SUFFIX[contract_type]}"


class LaborContract(Document):
	def autoname(self):
		"""Name = document number. A second document with the same number (re-signed
		stage, two appendices in one month) gets -2, -3… (user decision 22/10/2026)."""
		# autoname runs before validate (and before field defaults on get_doc(dict)),
		# so check what the number is built from here
		self.document_type = self.document_type or CONTRACT
		if self.document_type == APPENDIX:
			if not (self.employee and self.start_date):
				frappe.throw(_("Employee and Effective Date are required"))
		elif self.contract_type not in CONTRACT_SUFFIX:
			frappe.throw(
				_("Contract Type must be one of: {0}").format(", ".join(CONTRACT_SUFFIX))
			)
		base = document_number(self.document_type, self.employee, self.contract_type, self.start_date)
		name, n = base, 2
		while frappe.db.exists("Labor Contract", name):
			name = f"{base}-{n}"
			n += 1
		self.name = name

	def validate(self):
		if self.document_type == APPENDIX:
			self.validate_appendix()
		else:
			self.validate_contract()
		self.set_signed_on()
		self.validate_scan()

	def validate_contract(self):
		if self.contract_type not in CONTRACT_SUFFIX:
			frappe.throw(
				_("Contract Type must be one of: {0}").format(", ".join(CONTRACT_SUFFIX))
			)
		self.calculate_dates()
		self.parent_contract = None
		self.change_type = None

	def calculate_dates(self):
		"""end_date / next_contract_type / next_sign_date là derived field, luôn
		tính lại từ contract_type + start_date mỗi lần save (kể cả khi HR sửa
		tay) để không bao giờ lệch công thức."""
		if not (self.contract_type and self.start_date):
			return
		self.end_date = compute_end_date(self.contract_type, self.start_date)
		self.next_contract_type = get_next_contract_type(self.contract_type)
		self.next_sign_date = (
			add_days(self.end_date, 1) if (self.end_date and self.next_contract_type) else None
		)

	def validate_appendix(self):
		# The YYMM in the number is printed on paper; moving the effective date to
		# another month would leave a number that no longer matches it.
		if not self.is_new() and not self.name.startswith(
			document_number(APPENDIX, self.employee, start_date=self.start_date)
		):
			frappe.throw(
				_("The Effective Date month is part of the appendix number {0}. Delete this appendix and create a new one instead.").format(
					self.name
				)
			)

		self.parent_contract = contract_in_force(self.employee, self.start_date)
		if not self.parent_contract:
			frappe.throw(
				_("Employee {0} has no contract in force on {1} — create the contract first.").format(
					self.employee, formatdate(self.start_date)
				)
			)
		self.contract_type = None
		self.end_date = None
		self.next_contract_type = None
		self.next_sign_date = None
		self.next_stage_created = 0

	def set_signed_on(self):
		if self.status != "Signed":
			# taken back to Upcoming: the old date would still claim it was signed
			self.signed_on = None
			return
		# Only when someone flips an existing document to Signed: a record inserted
		# as Signed is history whose real signing date nobody knows — don't make one up.
		if (
			self.status == "Signed"
			and not self.signed_on
			and not self.is_new()
			and self.has_value_changed("status")
		):
			self.signed_on = business_today()

	def validate_scan(self):
		"""Any path that sets `scan` (form, Data Import, API): the file name must start
		with this document's number and the file must be private (ID card, salary)."""
		if not self.scan or self.flags.scan_checked or not self.has_value_changed("scan"):
			return
		if not self.scan.startswith("/private/"):
			frappe.throw(_("The scan holds personal data — it must be a private file."))
		file = frappe.db.get_value(
			"File",
			{"file_url": self.scan, "attached_to_doctype": self.doctype, "attached_to_name": self.name},
			["file_name", "content_hash"],
			as_dict=True,
		)
		file_name = (file and file.file_name) or self.scan.rsplit("/", 1)[-1]
		if not scan_name_matches(self.name, file_name, file and file.content_hash):
			frappe.throw(_scan_name_message(file_name, self.name))

	def after_insert(self):
		if self.document_type == CONTRACT:
			self.claim_predecessor()

	def claim_predecessor(self):
		"""Flag the contract this one follows (ends the day before it starts) as having
		its next stage, so the daily job doesn't draft a duplicate -2 when HR created the
		next stage by hand. Counterpart of release_predecessor."""
		if not self.start_date:
			return
		frappe.db.sql(
			"""
			UPDATE `tabLabor Contract` SET next_stage_created = 1
			WHERE employee = %(employee)s
			  AND document_type = 'Contract'
			  AND end_date = %(previous_day)s
			  AND next_stage_created = 0
			""",
			{"employee": self.employee, "previous_day": add_days(self.start_date, -1)},
		)

	def on_update(self):
		if self.document_type == CONTRACT:
			sync_employee_employment_type(self.employee)

	def after_delete(self):
		# Must be after_delete, not on_trash: on_trash still runs while the row
		# is in the table, so both helpers below would still see this contract.
		if self.document_type == CONTRACT:
			self.release_predecessor()
			sync_employee_employment_type(self.employee)

	def release_predecessor(self):
		"""Clear next_stage_created on the contract this one followed.

		Without this, deleting a wrongly-created follow-up leaves the previous
		contract flagged forever: the daily job and the review tool both skip
		it, so the stage can never be regenerated and HR is stuck editing a
		hidden field. The predecessor is the contract ending the day before
		this one starts.
		"""
		if not (self.employee and self.start_date):
			return

		predecessors = frappe.db.sql(
			"""
			SELECT name FROM `tabLabor Contract`
			WHERE employee = %(employee)s
			  AND document_type = 'Contract'
			  AND end_date = %(previous_day)s
			  AND next_stage_created = 1
			""",
			{"employee": self.employee, "previous_day": add_days(self.start_date, -1)},
			pluck=True,
		)
		for name in predecessors:
			frappe.db.set_value(
				"Labor Contract", name, "next_stage_created", 0, update_modified=False
			)


def contract_in_force(employee, on_date):
	"""Name of the employee's contract covering `on_date` (None if there is none)."""
	if not (employee and on_date):
		return None
	found = frappe.db.sql(
		"""
		SELECT name FROM `tabLabor Contract`
		WHERE employee = %(employee)s
		  AND document_type = 'Contract'
		  AND start_date <= %(on_date)s
		  AND (end_date IS NULL OR end_date >= %(on_date)s)
		ORDER BY start_date DESC, creation DESC
		LIMIT 1
		""",
		{"employee": employee, "on_date": getdate(on_date)},
		pluck=True,
	)
	return found[0] if found else None


# =============================================================================
# "Today" — single source of truth
# =============================================================================

def business_today():
	"""Today's date, read from the database.

	Every date comparison in this module — SQL and Python alike — goes through
	this so they can never disagree. System Settings.time_zone on this site
	intermittently reverts to Asia/Kolkata (UTC+5:30) while the database server
	runs on local time (UTC+7); frappe.utils.today() would then be a day behind
	SQL CURDATE() between 00:00 and 01:30 local — exactly when the daily job runs.
	"""
	return frappe.db.sql("SELECT CURDATE()")[0][0]


# =============================================================================
# Position on a date — Internal Work History
# =============================================================================

POSITION_FIELDS = ("designation", "department", "custom_section", "custom_group")


def positions_at(pairs):
	"""Designation / department / section / group of each (employee, date), in order.

	Internal Work History is rebuilt from Promotion/Transfer and starts on the joining
	date (overrides/employee_property/work_history.py), so the row whose from_date is
	the latest one on/before the date is the position then. Employees who never moved
	have no rows — their current Employee values are the answer.
	"""
	employees = list({employee for employee, _d in pairs if employee})
	if not employees:
		return [frappe._dict() for _p in pairs]

	fields = ", ".join(POSITION_FIELDS)
	history = defaultdict(list)
	for row in frappe.db.sql(
		f"""
		SELECT parent, from_date, {fields}
		FROM `tabEmployee Internal Work History`
		WHERE parenttype = 'Employee' AND parent IN %(employees)s
		ORDER BY from_date
		""",
		{"employees": employees}, as_dict=True,
	):
		history[row.parent].append(row)

	current = {
		row.name: row
		for row in frappe.db.sql(
			f"SELECT name, {fields} FROM `tabEmployee` WHERE name IN %(employees)s",
			{"employees": employees}, as_dict=True,
		)
	}

	out = []
	for employee, on_date in pairs:
		rows = history.get(employee)
		source = current.get(employee) or {}
		if rows and on_date:
			on_date = getdate(on_date)
			started = [r for r in rows if r.from_date and r.from_date <= on_date]
			source = started[-1] if started else rows[0]
		out.append(frappe._dict({f: source.get(f) for f in POSITION_FIELDS}))
	return out


# =============================================================================
# Employee.employment_type mirror
# =============================================================================

def leaves_before(relieving_date, contract_start):
	"""True when the employee is gone by the day a contract would start.

	relieving_date is the FIRST day off at TIQN (last working day = relieving_date
	- 1), so leaving ON the start day already means the contract is never needed.
	"""
	return bool(relieving_date and contract_start) and getdate(relieving_date) <= getdate(contract_start)


def sync_employee_employment_type(employee):
	"""Mirror the employee's CURRENT contract type onto Employee.employment_type.

	Deliberately recomputed from the whole chain rather than copied from
	whichever record was just saved: every stage of a seeded history is Signed,
	so re-saving an old stage must not drag the employee back to "probation".
	The current contract is the latest Signed one that has already started.
	Appendices never change the contract type.

	No such contract → leave the field as it is. A new hire's probation contract
	is created Upcoming (unsigned) by the Employee.after_insert hook, and
	clearing the employment_type their Data Import row set would make payroll
	stop treating them as probationary until HR marks the contract signed.
	"""
	if not employee:
		return

	current = frappe.db.sql(
		"""
		SELECT contract_type
		FROM `tabLabor Contract`
		WHERE employee = %(employee)s
		  AND document_type = 'Contract'
		  AND status = 'Signed'
		  AND start_date <= %(today)s
		ORDER BY start_date DESC, creation DESC
		LIMIT 1
		""",
		{"employee": employee, "today": business_today()}, pluck=True,
	)
	if not current:
		return
	new_value = current[0]

	if frappe.db.get_value("Employee", employee, "employment_type") != new_value:
		frappe.db.set_value(
			"Employee", employee, "employment_type", new_value, update_modified=False
		)


# =============================================================================
# Shared creation logic — used by Trigger A (single, on Employee insert) and by
# the "Create Probation Contracts" bulk backfill tool (List View button, for
# employees that predate this feature or were skipped via Data Import).
# =============================================================================

def _has_contract(employee):
	return frappe.db.exists("Labor Contract", {"employee": employee, "document_type": CONTRACT})


def _create_initial_labor_contract(employee):
	"""Create the first probationary Labor Contract for `employee`, using their
	Date of Joining as start_date and Probation Days (30/60) to pick the
	contract type. Raises ValueError with a human-readable reason when it
	can't (caller decides whether that's a msgprint, a skip row, etc.)."""
	if _has_contract(employee):
		raise ValueError(_("Already has a Labor Contract"))

	emp = frappe.db.get_value(
		"Employee", employee,
		["custom_probation_days", "date_of_joining", "status"], as_dict=True,
	)
	if not emp:
		raise ValueError(_("Employee not found"))
	if emp.status != "Active":
		raise ValueError(_("Employee is not Active"))

	contract_type, skip_reason = classify_probation_days(emp.custom_probation_days)
	if skip_reason:
		raise ValueError(_probation_skip_message(skip_reason))

	doc = frappe.get_doc({
		"doctype": "Labor Contract",
		"employee": employee,
		"document_type": CONTRACT,
		"contract_type": contract_type,
		"start_date": emp.date_of_joining,
		"status": "Upcoming",
	})
	doc.insert(ignore_permissions=True)
	return doc.name


# =============================================================================
# Trigger A — Employee mới -> tự tạo Labor Contract thử việc đầu tiên
# =============================================================================

def create_initial_contract_on_employee_insert(doc, method=None):
	"""hooks.py doc_events["Employee"]["after_insert"]

	Chạy cả khi tạo NV bằng Data Import — đó là đường nhận việc thực tế ở TIQN
	(user cho phép 21/10/2026).
	Probation Days trống = chức danh đặc biệt, không theo dõi hợp đồng → bỏ qua im lặng.
	"""
	_contract_type, skip_reason = classify_probation_days(doc.custom_probation_days)
	if skip_reason == SKIP_MISSING_PROBATION_DAYS:
		return

	try:
		_create_initial_labor_contract(doc.name)
	except ValueError as e:
		# Data Import has no one watching for alerts; the row shows up in
		# "Create Probation Contracts" instead.
		if not frappe.flags.in_import:
			frappe.msgprint(
				_("Employee {0}: {1} — please create the Labor Contract manually.").format(doc.name, str(e)),
				alert=True,
				indicator="orange",
			)
	except Exception:
		frappe.log_error(
			frappe.get_traceback(),
			f"Labor Contract auto-create failed for Employee {doc.name}",
		)


# =============================================================================
# Bulk backfill tool — Labor Contract List View "Create Probation Contracts"
# =============================================================================

# Small selections run inline (fast UX, no polling needed); larger ones are
# enqueued to avoid tying up a web worker / risking an HTTP timeout.
BULK_SYNC_THRESHOLD = 20


MISSING_CONTRACT = "Missing Contract"


def _resolve_target_employees(filter_by, employees=None):
	"""Active employees to attempt a first contract for.

	Default: every Active employee with no contract at all, so HR doesn't
	have to know which intake dates still need contracts. Employees with empty
	Probation Days hold special designations that don't get contracts, so they
	aren't "missing" one and are left out. The explicit employee list is the
	fallback for odd one-off cases.
	"""
	if filter_by == "Employees":
		if isinstance(employees, str):
			employees = frappe.parse_json(employees) if employees.strip() else None
		if not employees:
			frappe.throw(_("Please select at least one Employee"))
		return employees

	return frappe.db.sql(
		"""
		SELECT emp.name FROM `tabEmployee` emp
		WHERE emp.status = 'Active'
			AND IFNULL(emp.custom_probation_days, '') != ''
			AND NOT EXISTS (
				SELECT 1 FROM `tabLabor Contract` lc
				WHERE lc.employee = emp.name AND lc.document_type = 'Contract'
			)
		ORDER BY emp.date_of_joining, emp.name
		""",
		pluck=True,
	)


@frappe.whitelist()
def get_probation_contract_candidates(
	filter_by=MISSING_CONTRACT, employees=None
):
	"""The employees still missing a contract (or the hand-picked ones), one row
	each, so HR can eyeball the actual names before creating anything. Rows that won't get a contract carry
	the reason instead of a contract type."""
	frappe.has_permission("Labor Contract", "create", throw=True)

	targets = _resolve_target_employees(filter_by, employees)
	if not targets:
		return []

	rows = frappe.db.sql(
		"""
		SELECT
			emp.name AS employee, emp.employee_name, emp.designation,
			emp.date_of_joining, emp.custom_probation_days AS probation_days,
			EXISTS(
				SELECT 1 FROM `tabLabor Contract` lc
				WHERE lc.employee = emp.name AND lc.document_type = 'Contract'
			) AS has_contract
		FROM `tabEmployee` emp
		WHERE emp.name IN %(names)s
		ORDER BY emp.date_of_joining, emp.name
		""",
		{"names": targets}, as_dict=True,
	)

	out = []
	for row in rows:
		contract_type = None
		reason = None
		if row.has_contract:
			reason = _("Already has a Labor Contract")
		else:
			contract_type, skip_reason = classify_probation_days(row.probation_days)
			if skip_reason:
				reason = _probation_skip_message(skip_reason)

		out.append({
			"employee": row.employee,
			"employee_name": row.employee_name,
			"designation": row.designation,
			"date_of_joining": row.date_of_joining,
			"probation_days": row.probation_days,
			"contract_type": contract_type,
			"will_create": bool(contract_type),
			"reason": reason,
		})

	return out


@frappe.whitelist()
def bulk_create_probation_contracts(
	filter_by=MISSING_CONTRACT, employees=None
):
	"""hooks.py-free entry point for the Labor Contract List View button.
	Returns either the finished result (small selections) or {queued: True, total}
	when the work was hand off to a background job (large selections)."""
	frappe.has_permission("Labor Contract", "create", throw=True)

	targets = _resolve_target_employees(filter_by, employees)
	if not targets:
		return {"created": 0, "skipped": 0, "errors": [], "queued": False}

	if len(targets) <= BULK_SYNC_THRESHOLD:
		result = _run_bulk_create(targets)
		result["queued"] = False
		return result

	frappe.enqueue(
		"customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.background_bulk_create_probation_contracts",
		queue="long",
		timeout=1800,
		employees_json=json.dumps(targets),
		user=frappe.session.user,
		enqueue_after_commit=True,
	)
	return {"queued": True, "total": len(targets)}


def _run_bulk_create(employee_names):
	created = 0
	errors = []
	for i, name in enumerate(employee_names):
		try:
			_create_initial_labor_contract(name)
			created += 1
		except ValueError as e:
			errors.append({"employee": name, "error": str(e)})
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Bulk Labor Contract create failed for {name}")
			errors.append({"employee": name, "error": _("Unexpected error — see Error Log")})
		if (i + 1) % 100 == 0:
			frappe.db.commit()
	return {"created": created, "skipped": len(errors), "errors": errors}


def background_bulk_create_probation_contracts(employees_json, user):
	employees = json.loads(employees_json)
	result = _run_bulk_create(employees)
	frappe.db.commit()
	frappe.publish_realtime(
		event="labor_contract_bulk_create_complete",
		message=result,
		user=user,
	)


def _get_employment_type_periods():
	rows = frappe.get_all(
		"Employment Type", fields=["name", "custom_period"], order_by="creation desc"
	)
	return {r.name: cint(r.custom_period) for r in rows}


# =============================================================================
# Trigger B — Scheduled job hàng ngày (00:00)
# =============================================================================

def process_labor_contracts_daily():
	"""hooks.py scheduler_events["cron"]["0 0 * * *"]

	Bước 1 (materialize) PHẢI chạy trước Bước 2 (overdue): tránh 1 record vừa
	được tạo hôm nay (start_date = hôm nay) bị chính lần chạy này đánh Overdue
	oan nếu chạy theo thứ tự ngược lại.
	"""
	try:
		created = _materialize_next_stage()
		overdue = _mark_overdue()
		frappe.db.commit()
		frappe.logger().info(
			f"[Labor Contract] Daily job done — materialized {created}, marked overdue {overdue}"
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Labor Contract Daily Job Failed")
		frappe.db.rollback()


def _draft_next_stage(contract_name, employee, next_contract_type, end_date):
	"""Insert the next stage as an Upcoming (unsigned) contract and flag the
	current one so nothing creates it twice. Shared by the daily job and the
	manual "Review Expiring Contracts" tool."""
	doc = frappe.get_doc({
		"doctype": "Labor Contract",
		"employee": employee,
		"document_type": CONTRACT,
		"contract_type": next_contract_type,
		"start_date": add_days(end_date, 1),
		"status": "Upcoming",
	}).insert(ignore_permissions=True)

	frappe.db.set_value(
		"Labor Contract", contract_name, "next_stage_created", 1, update_modified=False
	)
	return doc.name


def _materialize_next_stage():
	"""Tạo Labor Contract cho giai đoạn kế tiếp khi hợp đồng hiện tại đã Signed
	và sắp hết hạn (trong vòng custom_warning_before ngày của chính contract_type
	hiện tại), với điều kiện nhân viên vẫn đang Active."""
	rows = frappe.db.sql(
		"""
		SELECT lc.name, lc.employee, lc.next_contract_type, lc.end_date
		FROM `tabLabor Contract` lc
		INNER JOIN `tabEmployee` emp ON emp.name = lc.employee
		INNER JOIN `tabEmployment Type` et ON et.name = lc.contract_type
		WHERE lc.document_type = 'Contract'
		  AND lc.status = 'Signed'
		  AND lc.next_stage_created = 0
		  AND lc.next_contract_type IS NOT NULL AND lc.next_contract_type != ''
		  AND emp.status = 'Active'
		  -- leaving on/before the next stage would start -> no next contract
		  AND (emp.relieving_date IS NULL OR emp.relieving_date > lc.next_sign_date)
		  AND DATEDIFF(lc.end_date, %(today)s) <= et.custom_warning_before
		  -- a later contract exists (created by hand, or with a corrected date)
		  AND NOT EXISTS (
			SELECT 1 FROM `tabLabor Contract` later
			WHERE later.employee = lc.employee AND later.document_type = 'Contract'
			  AND later.start_date > lc.start_date
		  )
		LIMIT 500
		""",
		{"today": business_today()},
		as_dict=True,
	)

	for row in rows:
		_draft_next_stage(row.name, row.employee, row.next_contract_type, row.end_date)

	return len(rows)


# =============================================================================
# Review Expiring Contracts — manual, date-range version of the daily job
# =============================================================================
# The daily job only looks at its own warning window (custom_warning_before).
# HR also wants to work a month at a time: "show me everything expiring between
# these dates, then draft the follow-up contracts for the ones that are ready".

MAX_INLINE_DRAFTS = 500

def _expiring_contract_rows(from_date, to_date):
	return frappe.db.sql(
		"""
		SELECT
			lc.name, lc.employee, lc.employee_name, emp.designation,
			lc.contract_type, lc.end_date, lc.status,
			lc.next_contract_type, lc.next_sign_date, lc.next_stage_created,
			emp.status AS employee_status, emp.relieving_date,
			EXISTS (
				SELECT 1 FROM `tabLabor Contract` later
				WHERE later.employee = lc.employee AND later.document_type = 'Contract'
				  AND later.start_date > lc.start_date
			) AS has_later_contract
		FROM `tabLabor Contract` lc
		INNER JOIN `tabEmployee` emp ON emp.name = lc.employee
		WHERE lc.document_type = 'Contract'
		  AND lc.end_date BETWEEN %(from_date)s AND %(to_date)s
		ORDER BY lc.end_date, lc.employee
		""",
		{"from_date": from_date, "to_date": to_date}, as_dict=True,
	)


def _blocking_reason(row):
	"""Why this contract can't have its next stage drafted — None when it can."""
	if not row.next_contract_type:
		return _("Indefinite-term — no next stage")
	if row.next_stage_created or row.has_later_contract:
		return _("Next contract already created")
	if row.employee_status != "Active":
		return _("Employee is not Active")
	if leaves_before(row.relieving_date, row.next_sign_date):
		return _("Leaves on {0} — no next contract").format(formatdate(row.relieving_date))
	if row.status != "Signed":
		return _("Current contract is not Signed yet")
	return None


@frappe.whitelist()
def get_expiring_contracts(from_date, to_date):
	"""List every contract ending in the range, flagging which ones are ready to
	have their follow-up contract drafted."""
	frappe.has_permission("Labor Contract", "create", throw=True)

	if not (from_date and to_date):
		frappe.throw(_("Please pick both dates"))
	if getdate(from_date) > getdate(to_date):
		frappe.throw(_("From Date cannot be after To Date"))

	out = []
	for row in _expiring_contract_rows(from_date, to_date):
		reason = _blocking_reason(row)
		out.append({
			"name": row.name,
			"employee": row.employee,
			"employee_name": row.employee_name,
			"designation": row.designation,
			"contract_type": row.contract_type,
			"end_date": row.end_date,
			"status": row.status,
			"next_contract_type": row.next_contract_type,
			"next_sign_date": row.next_sign_date,
			"relieving_date": row.relieving_date,
			"can_draft": reason is None,
			"reason": reason,
		})
	return out


@frappe.whitelist()
def draft_expiring_contracts(from_date, to_date):
	"""Create the follow-up (Upcoming) contract for every ready row in the range."""
	frappe.has_permission("Labor Contract", "create", throw=True)

	if not (from_date and to_date):
		frappe.throw(_("Please pick both dates"))

	ready = [row for row in _expiring_contract_rows(from_date, to_date) if not _blocking_reason(row)]

	# This runs inline in the web request. The tool is meant for one month at a
	# time (~120 contracts); a multi-year range would otherwise time out midway
	# and leave a half-finished batch behind.
	if len(ready) > MAX_INLINE_DRAFTS:
		frappe.throw(
			_("{0} contracts are ready in this range — too many for one run. Please narrow the date range to about a month.").format(
				len(ready)
			)
		)

	created = 0
	errors = []
	for row in ready:
		try:
			_draft_next_stage(row.name, row.employee, row.next_contract_type, row.end_date)
			created += 1
		except Exception:
			frappe.log_error(
				frappe.get_traceback(), f"Drafting next contract failed for {row.name}"
			)
			errors.append({
				"employee": row.employee,
				"error": _("Unexpected error — see Error Log"),
			})

	# No explicit commit: Frappe commits at the end of a successful request.
	# Committing here would also break test isolation — tests call this
	# directly, and a commit escapes their rollback into the real database.
	return {"created": created, "skipped": len(errors), "errors": errors}


def _mark_overdue():
	"""Upcoming (contract or appendix) đã quá ngày bắt đầu mà chưa Signed -> Overdue."""
	frappe.db.sql(
		"""
		UPDATE `tabLabor Contract` lc
		SET lc.status = 'Overdue'
		WHERE lc.status = 'Upcoming' AND lc.start_date < %(today)s
		  -- starts on/after the employee's first day off: never going to be signed
		  AND NOT EXISTS (
			SELECT 1 FROM `tabEmployee` emp
			WHERE emp.name = lc.employee
			  AND emp.relieving_date IS NOT NULL AND emp.relieving_date <= lc.start_date
		  )
		""",
		{"today": business_today()},
	)
	return frappe.db.sql("SELECT ROW_COUNT()")[0][0]


# =============================================================================
# Bulk "mark as Signed"
# =============================================================================

@frappe.whitelist()
def get_unsigned_contracts(employees=None, limit=500):
	"""Contracts and appendices still waiting to be signed — the picker list for
	the bulk tool when the user hasn't ticked any rows in the list view.

	No contract-type filter on purpose: this tool only confirms that an existing
	Upcoming/Overdue document has been signed, it never chooses the type.
	"""
	frappe.has_permission("Labor Contract", "write", throw=True)

	# null from the browser arrives as "" — parse_json("") raises
	if isinstance(employees, str):
		employees = frappe.parse_json(employees) if employees.strip() else None

	conditions = [
		"lc.status IN ('Upcoming', 'Overdue')",
		# a document starting on/after the first day off will never be signed
		"(emp.relieving_date IS NULL OR emp.relieving_date > lc.start_date)",
	]
	values = {"limit": cint(limit) or 500}
	if employees:
		conditions.append("lc.employee IN %(employees)s")
		values["employees"] = employees

	return frappe.db.sql(
		f"""
		SELECT
			lc.name, lc.employee, lc.employee_name, emp.designation, lc.document_type,
			lc.contract_type, lc.start_date, lc.end_date, lc.status
		FROM `tabLabor Contract` lc
		INNER JOIN `tabEmployee` emp ON emp.name = lc.employee
		WHERE {" AND ".join(conditions)}
		ORDER BY lc.start_date, lc.employee
		LIMIT %(limit)s
		""",
		values, as_dict=True,
	)


def _sign(doc, signed_on):
	"""Set one document to Signed (not saved). Returns why it can't be, or None."""
	if doc.status == "Signed":
		return _("Already Signed")
	relieving_date = frappe.db.get_value("Employee", doc.employee, "relieving_date")
	if leaves_before(relieving_date, doc.start_date):
		return _("Employee leaves on {0}, before this contract starts").format(
			formatdate(relieving_date)
		)
	doc.status = "Signed"
	doc.signed_on = doc.signed_on or signed_on
	return None


@frappe.whitelist()
def bulk_mark_signed(contracts, signed_on=None):
	"""Flip the given documents to Signed (actual signing date `signed_on`, default
	today) and mirror each employee's current contract type onto
	Employee.employment_type.

	Goes through the full document save (not db_set) so the controller keeps
	derived dates consistent and on_update fires the employment-type sync.
	"""
	frappe.has_permission("Labor Contract", "write", throw=True)

	if isinstance(contracts, str):
		contracts = frappe.parse_json(contracts) if contracts.strip() else None
	if not contracts:
		frappe.throw(_("Please select at least one contract"))
	signed_on = getdate(signed_on) if signed_on else business_today()

	signed = 0
	errors = []
	for name in contracts:
		# a document that fails halfway must not leave part of its writes behind
		frappe.db.savepoint("lc_sign")
		try:
			doc = frappe.get_doc("Labor Contract", name)
			error = _sign(doc, signed_on)
			if error:
				errors.append({"contract": name, "error": error})
				continue
			doc.save(ignore_permissions=True)
			signed += 1
		except Exception:
			frappe.db.rollback(save_point="lc_sign")
			frappe.log_error(frappe.get_traceback(), f"Bulk sign failed for {name}")
			errors.append({"contract": name, "error": _("Unexpected error — see Error Log")})

	# No explicit commit: Frappe commits at the end of a successful request.
	# Committing here would also break test isolation — tests call this
	# directly, and a commit escapes their rollback into the real database.
	return {"signed": signed, "skipped": len(errors), "errors": errors}


def _only_administrator():
	if frappe.session.user != "Administrator":
		frappe.throw(_("Only Administrator can do this."), frappe.PermissionError)


@frappe.whitelist()
def resync_all_employment_types():
	"""Backfill Employee.employment_type from existing contracts (one-off, after
	contracts were bulk-imported or migrated).

	Administrator-only: it rewrites a field on every employee that has a
	signed, already started contract (others keep their current value).
	"""
	_only_administrator()

	employees = frappe.db.sql(
		"SELECT DISTINCT employee FROM `tabLabor Contract` WHERE document_type = 'Contract'",
		pluck=True,
	)
	for name in employees:
		sync_employee_employment_type(name)
	# No explicit commit: Frappe commits at the end of a successful request.
	# Committing here would also break test isolation — tests call this
	# directly, and a commit escapes their rollback into the real database.
	return {"employees": len(employees)}


# =============================================================================
# Contract appendix from Employee Promotion / Employee Transfer
# =============================================================================
# Ticking `custom_create_contract_appendix` on the form creates the appendix when the
# document is submitted (overrides/employee_property/*.py). Forgot to tick → button
# "Create Contract Appendix" on the submitted document. Salary changes: pending.

PROPERTY_UPDATE_DATE_FIELD = {
	"Employee Promotion": "promotion_date",
	"Employee Transfer": "transfer_date",
}


def _appendix_of(doctype, name):
	return frappe.db.get_value(
		"Labor Contract",
		{"document_type": APPENDIX, "reference_doctype": doctype, "reference_name": name},
		"name",
	)


def _make_appendix(doc):
	existing = _appendix_of(doc.doctype, doc.name)
	if existing:
		return existing

	appendix = frappe.get_doc({
		"doctype": "Labor Contract",
		"employee": doc.employee,
		"document_type": APPENDIX,
		"start_date": doc.get(PROPERTY_UPDATE_DATE_FIELD[doc.doctype]),
		"change_type": "C",
		"status": "Upcoming",
		"reference_doctype": doc.doctype,
		"reference_name": doc.name,
	}).insert(ignore_permissions=True)

	frappe.msgprint(
		_("Contract Appendix {0} created.").format(get_link_to_form("Labor Contract", appendix.name)),
		alert=True,
		indicator="green",
	)
	return appendix.name


def create_appendix_on_submit(doc):
	"""Employee Promotion / Transfer on_submit. Throws (blocks the submit) when the
	employee has no contract in force on the effective date."""
	if doc.get("custom_create_contract_appendix"):
		_make_appendix(doc)


def remove_appendix_on_cancel(doc):
	"""Employee Promotion / Transfer on_cancel: an unsigned appendix goes with the
	document; a signed one is a signed paper and blocks the cancel."""
	name = _appendix_of(doc.doctype, doc.name)
	if not name:
		return
	if frappe.db.get_value("Labor Contract", name, "status") == "Signed":
		frappe.throw(
			_("Contract Appendix {0} is already signed. Delete it first if this {1} really has to be cancelled.").format(
				get_link_to_form("Labor Contract", name), _(doc.doctype)
			)
		)
	frappe.delete_doc("Labor Contract", name, ignore_permissions=True)


@frappe.whitelist()
def get_contract_appendix(doctype, name):
	if doctype not in PROPERTY_UPDATE_DATE_FIELD:
		frappe.throw(_("Not supported"))
	frappe.has_permission(doctype, "read", doc=name, throw=True)
	if not frappe.has_permission("Labor Contract", "read"):
		return {"allowed": False}
	return {
		"allowed": True,
		"can_create": bool(frappe.has_permission("Labor Contract", "create")),
		"appendix": _appendix_of(doctype, name),
	}


@frappe.whitelist()
def create_contract_appendix(doctype, name):
	if doctype not in PROPERTY_UPDATE_DATE_FIELD:
		frappe.throw(_("Not supported"))
	frappe.has_permission("Labor Contract", "create", throw=True)
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus != 1:
		frappe.throw(_("Submit the {0} first.").format(_(doctype)))
	return _make_appendix(doc)


# =============================================================================
# Signed copy (scan)
# =============================================================================
# HR scans the signed paper and names the file after the document number
# (TIQN-2548-HD1.pdf, "PL-TIQN-2548-2610 signed.pdf"): the name is how a pile of scans
# finds its records (List View "Upload Signed Scans"), and it is required on the form
# too, so a scan can never sit on the wrong record (user request 22/10/2026).

SCAN_FILE_TYPES = (".pdf", ".jpg", ".jpeg", ".png")


def match_scan_file(file_name):
	"""The Labor Contract a scan belongs to, or None.

	The longest document number the file name starts with, ending where a word ends:
	TIQN-2548-HD1.pdf is HD1 (not HD), TIQN-2548-HD1-2.pdf is HD1-2 when that record
	exists. Case-insensitive (the table collation).
	"""
	stem = os.path.splitext(os.path.basename(file_name or ""))[0].strip()
	prefixes = [
		stem[:i] for i in range(1, len(stem) + 1) if i == len(stem) or not stem[i].isalnum()
	]
	if not prefixes:
		return None
	found = frappe.get_all("Labor Contract", filters={"name": ("in", prefixes)}, pluck="name")
	return max(found, key=len) if found else None


def scan_name_matches(name, file_name, content_hash=None):
	if match_scan_file(file_name) == name:
		return True
	# Frappe appends the last 6 characters of the content hash when the name is
	# already taken on disk (TIQN-2548-HD1a3f9c2.pdf)
	stem, ext = os.path.splitext(file_name)
	if content_hash and stem.endswith(content_hash[-6:]):
		return match_scan_file(stem[:-6] + ext) == name
	return False


def _scan_name_message(file_name, name):
	return _("File name {0} must start with the document number {1}, e.g. {1}.pdf").format(
		file_name, name
	)


def _scan_problem(file_name, target=None):
	"""(contract, error) for one file — error is None when it can be attached.
	`target`: the record whose form the file was uploaded from."""
	if not file_name.lower().endswith(SCAN_FILE_TYPES):
		return None, _("Only PDF, JPG or PNG files are accepted")
	name = match_scan_file(file_name)
	if target and name != target:
		if name:
			return name, _("This is the scan of {0}, not {1}").format(name, target)
		return None, _scan_name_message(file_name, target)
	if not name:
		return None, _("The file name does not start with a document number (e.g. TIQN-2548-HD1.pdf)")
	scan = frappe.db.get_value("Labor Contract", name, "scan")
	if scan:
		return name, _("{0} already has a scan — clear it on the form first to replace it").format(name)
	return name, None


@frappe.whitelist()
def match_scan_files(file_names):
	"""Preview for "Upload Signed Scans": which record each file goes to, before uploading."""
	frappe.has_permission("Labor Contract", "write", throw=True)
	if isinstance(file_names, str):
		file_names = frappe.parse_json(file_names)

	out = []
	for file_name in file_names or []:
		name, error = _scan_problem(file_name)
		row = {"file_name": file_name, "contract": name, "error": error}
		if name:
			row.update(frappe.db.get_value(
				"Labor Contract", name, ["employee_name", "status", "document_type"], as_dict=True
			))
		out.append(row)
	return out


@frappe.whitelist(methods=["POST"])
def upload_scan():
	"""`method` of /api/method/upload_file for scans — from the form's Scan field (the
	record is form_dict.docname) or the List View bulk upload (the file name picks it).

	The name is checked here, BEFORE a File exists: a wrongly named upload would otherwise
	stay behind as an attachment, and Frappe renames a file whose name is taken on disk.
	Bulk upload may also send mark_signed + signed_on.
	"""
	from frappe.core.doctype.file.utils import get_content_hash

	content = getattr(frappe.local, "uploaded_file", None)
	file_name = getattr(frappe.local, "uploaded_filename", None)
	if content is None or not file_name:
		frappe.throw(_("Choose the scanned file from your computer."))

	form = frappe.form_dict
	target = form.docname if form.doctype == "Labor Contract" else None
	if target and not frappe.db.exists("Labor Contract", target):
		frappe.throw(_("Save the document before attaching its scan."))

	name, error = _scan_problem(file_name, target)
	if error:
		frappe.throw(f"{file_name}: {error}")

	doc = frappe.get_doc("Labor Contract", name)
	doc.check_permission("write")

	# The same file on two records = one of them got the wrong paper
	other = frappe.db.get_value(
		"File",
		{
			"content_hash": get_content_hash(content),
			"attached_to_doctype": "Labor Contract",
			"attached_to_field": "scan",
			"attached_to_name": ("!=", name),
		},
		"attached_to_name",
	)
	if other:
		frappe.throw(_("{0}: the same file is already the scan of {1}").format(file_name, other))

	note = None
	if cint(form.mark_signed) and doc.status != "Signed":
		note = _sign(doc, getdate(form.signed_on) if form.signed_on else business_today())

	file = frappe.get_doc({
		"doctype": "File",
		"file_name": file_name,
		"content": content,
		"is_private": 1,
		"attached_to_doctype": "Labor Contract",
		"attached_to_name": name,
		"attached_to_field": "scan",
	}).insert(ignore_permissions=True)

	doc.scan = file.file_url
	doc.flags.scan_checked = True
	doc.save()
	return {
		"name": file.name,
		"file_name": file.file_name,
		"file_url": file.file_url,
		"is_private": 1,
		"contract": name,
		"status": doc.status,
		"note": note,
	}


# Download Signed Scans — List View, one ZIP. Same two steps as the employee photo
# ZIP (api/employee/employee_photo_download.py): preview with frappe.call first,
# because open_url_post replaces the page with a JSON error if the download throws.

MAX_SCAN_DOWNLOAD = 3000


def _scan_entries(contracts=None, filters=None):
	"""(entries, missing) for the ticked records, or every record matching the list
	filters when nothing is ticked. Read permission applies (frappe.get_list)."""
	from customize_erpnext.api.employee.employee_photo_download import _resolve_photo_path

	if isinstance(contracts, str):
		contracts = frappe.parse_json(contracts) if contracts.strip() else None
	if isinstance(filters, str):
		filters = frappe.parse_json(filters) if filters.strip() else None
	if contracts:
		filters = [["Labor Contract", "name", "in", contracts]]

	rows = frappe.get_list(
		"Labor Contract",
		filters=filters or [],
		fields=["name", "employee_name", "scan"],
		order_by="name asc",
		limit_page_length=MAX_SCAN_DOWNLOAD + 1,
	)
	if len(rows) > MAX_SCAN_DOWNLOAD:
		frappe.throw(_("Too many documents ({0}+) — narrow the filters to at most {1}.").format(
			MAX_SCAN_DOWNLOAD, MAX_SCAN_DOWNLOAD
		))

	entries, missing = [], []
	for row in rows:
		path = _resolve_photo_path(row.scan) if row.scan else None
		if path:
			entries.append({"name": row.name, "path": path})
		else:
			missing.append({
				"name": row.name,
				"employee_name": row.employee_name or "",
				"reason": _("Scan file not found on server") if row.scan else _("No scan"),
			})
	return entries, missing


@frappe.whitelist()
def preview_scan_download(contracts=None, filters=None):
	entries, missing = _scan_entries(contracts, filters)
	return {
		"count": len(entries),
		"total_size": sum(os.path.getsize(e["path"]) for e in entries),
		"missing": missing,
	}


@frappe.whitelist(methods=["POST"])
def download_scans(contracts=None, filters=None):
	import io
	import zipfile

	entries, missing = _scan_entries(contracts, filters)
	if not entries:
		frappe.throw(_("None of these documents has a scan"))

	buf = io.BytesIO()
	# PDF / JPEG are already compressed — deflate costs CPU for almost nothing
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
		for entry in entries:
			# the document number, whatever the uploaded file was called
			zf.write(entry["path"], entry["name"] + os.path.splitext(entry["path"])[1].lower())
		if missing:
			lines = [_("Documents without a scan") + f" ({len(missing)})", ""]
			lines += ["\t".join((m["name"], m["employee_name"], m["reason"])) for m in missing]
			# BOM so old Notepad shows Vietnamese correctly
			zf.writestr("_missing_scans.txt", "﻿" + "\r\n".join(lines) + "\r\n")

	frappe.response.filename = f"labor_contract_scans_{frappe.utils.now_datetime():%Y%m%d_%H%M%S}.zip"
	frappe.response.filecontent = buf.getvalue()
	frappe.response.type = "download"
	frappe.response.content_type = "application/zip"
