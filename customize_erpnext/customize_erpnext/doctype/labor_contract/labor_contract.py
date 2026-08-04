# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, getdate
from frappe.model.document import Document


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

# Employee.custom_probation_days (fetch_from Designation) -> loại hợp đồng thử việc
PROBATION_DAYS_TO_CONTRACT_TYPE = {
	"30": PROBATION_30,
	"60": PROBATION_60,
}

# Trường hợp đặc biệt, hiếm: tuyển vào không qua thử việc. Giai đoạn đầu là gì
# (1 năm? 3 năm?) là quyết định nghiệp vụ nên hệ thống KHÔNG đoán — HR tự tạo tay.
NO_PROBATION = "0"

# Lý do bỏ qua, hiển thị cho HR trong bảng kết quả bulk/seed
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
	return _("Probation Days is not set")


class LaborContract(Document):
	def validate(self):
		self.calculate_dates()
		self.set_manager_email()

	def calculate_dates(self):
		"""end_date / next_contract_type / next_sign_date là derived field, luôn
		tính lại từ contract_type + start_date mỗi lần save (kể cả khi HR sửa
		tay) để không bao giờ lệch công thức so với Employment Type hiện tại."""
		if not (self.contract_type and self.start_date):
			return

		et = frappe.db.get_value(
			"Employment Type", self.contract_type,
			["custom_period"], as_dict=True,
		)
		period = cint(et.custom_period) if et else 0

		self.end_date = add_days(self.start_date, period - 1) if period else None
		self.next_contract_type = get_next_contract_type(self.contract_type)
		self.next_sign_date = (
			add_days(self.end_date, 1) if (self.end_date and self.next_contract_type) else None
		)

	def set_manager_email(self):
		"""Hidden helper field dùng làm Notification Recipient (Receiver By
		Document Field chỉ đọc được field phẳng trên chính doctype này, không
		theo được dotted path employee.reports_to.user_id qua 2 lớp Link)."""
		manager_email = None
		if self.employee:
			reports_to = frappe.db.get_value("Employee", self.employee, "reports_to")
			if reports_to:
				manager_email = frappe.db.get_value("Employee", reports_to, "user_id")
		self.manager_email = manager_email

	def on_update(self):
		sync_employee_employment_type(self.employee)

	def after_delete(self):
		# Must be after_delete, not on_trash: on_trash still runs while the row
		# is in the table, so both helpers below would still see this contract.
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
# Employee.employment_type mirror
# =============================================================================

def sync_employee_employment_type(employee):
	"""Mirror the employee's CURRENT contract type onto Employee.employment_type.

	Deliberately recomputed from the whole chain rather than copied from
	whichever record was just saved: every stage of a seeded history is Signed,
	so re-saving an old stage must not drag the employee back to "probation".
	The current contract is the latest Signed one that has already started.
	"""
	if not employee:
		return

	current = frappe.db.sql(
		"""
		SELECT contract_type
		FROM `tabLabor Contract`
		WHERE employee = %(employee)s
		  AND status = 'Signed'
		  AND start_date <= %(today)s
		ORDER BY start_date DESC, creation DESC
		LIMIT 1
		""",
		{"employee": employee, "today": business_today()}, pluck=True,
	)
	new_value = current[0] if current else None

	if frappe.db.get_value("Employee", employee, "employment_type") != new_value:
		frappe.db.set_value(
			"Employee", employee, "employment_type", new_value, update_modified=False
		)


# =============================================================================
# Shared creation logic — used by Trigger A (single, on Employee insert) and by
# the "Create Probation Contracts" bulk backfill tool (List View button, for
# employees that predate this feature or were skipped via Data Import).
# =============================================================================

def _create_initial_labor_contract(employee):
	"""Create the first probationary Labor Contract for `employee`, using their
	Date of Joining as start_date and Probation Days (30/60) to pick the
	contract type. Raises ValueError with a human-readable reason when it
	can't (caller decides whether that's a msgprint, a skip row, etc.)."""
	if frappe.db.exists("Labor Contract", {"employee": employee}):
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

	Bỏ qua hoàn toàn khi import hàng loạt (frappe.flags.in_import) để tránh tự
	tạo sai khi migrate/import nhân viên cũ. HR tự tạo Labor Contract tay (hoặc
	dùng nút "Create Probation Contracts" trên List View) cho các case đó.
	"""
	if frappe.flags.in_import:
		return

	try:
		_create_initial_labor_contract(doc.name)
	except ValueError as e:
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


def _resolve_target_employees(filter_by, employees=None, date_of_joining=None):
	"""Active employees to attempt a first contract for.

	New hires arrive in batches that all start on the same day, so the normal
	flow is "one intake date"; the explicit employee list is the fallback for
	odd one-off cases.
	"""
	filter_by = filter_by or "Date of Joining"

	if filter_by == "Employees":
		if isinstance(employees, str):
			employees = frappe.parse_json(employees)
		if not employees:
			frappe.throw(_("Please select at least one Employee"))
		return employees

	if not date_of_joining:
		frappe.throw(_("Please pick a Date of Joining"))

	return frappe.db.sql(
		"""
		SELECT emp.name FROM `tabEmployee` emp
		WHERE emp.status = 'Active' AND emp.date_of_joining = %(doj)s
		ORDER BY emp.name
		""",
		{"doj": date_of_joining}, pluck=True,
	)


@frappe.whitelist()
def get_probation_contract_candidates(
	filter_by="Date of Joining", employees=None, date_of_joining=None
):
	"""The employees in this intake batch, one row each, so HR can eyeball the
	actual names before creating anything. Rows that won't get a contract carry
	the reason instead of a contract type."""
	frappe.has_permission("Labor Contract", "create", throw=True)

	targets = _resolve_target_employees(filter_by, employees, date_of_joining)
	if not targets:
		return []

	rows = frappe.db.sql(
		"""
		SELECT
			emp.name AS employee, emp.employee_name, emp.designation,
			emp.date_of_joining, emp.custom_probation_days AS probation_days,
			EXISTS(SELECT 1 FROM `tabLabor Contract` lc WHERE lc.employee = emp.name) AS has_contract
		FROM `tabEmployee` emp
		WHERE emp.name IN %(names)s
		ORDER BY emp.name
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
	filter_by="Date of Joining", employees=None, date_of_joining=None
):
	"""hooks.py-free entry point for the Labor Contract List View button.
	Returns either the finished result (small selections) or {queued: True, total}
	when the work was hand off to a background job (large selections)."""
	frappe.has_permission("Labor Contract", "create", throw=True)

	targets = _resolve_target_employees(filter_by, employees, date_of_joining)
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


# =============================================================================
# Seeding tool — one-off backfill of the FULL contract history
# =============================================================================
# Unlike "Create Probation Contracts" (which only creates the first stage for
# new hires), seeding walks the whole chain forward from Date of Joining so that
# employees who predate this feature land on the contract stage they are
# actually on today, with their past stages recorded as Signed.
#
# Administrator-only: it writes thousands of records and is meant to be run once
# on go-live.

def _get_employment_type_periods():
	rows = frappe.get_all(
		"Employment Type", fields=["name", "custom_period"], order_by="creation desc"
	)
	return {r.name: cint(r.custom_period) for r in rows}


def _plan_contract_chain(date_of_joining, probation_days, period_map, as_of):
	"""Pure date math (no DB writes): the sequence of (contract_type, start, end)
	an employee has gone through, from Date of Joining up to and including the
	stage that covers `as_of`. Stops at the Indefinite-term stage, which has no
	end date and no successor."""
	contract_type, _skip_reason = classify_probation_days(probation_days)
	if not (contract_type and date_of_joining):
		return []

	plan = []
	start = getdate(date_of_joining)

	# The sequence is finite; the bound is just a guard against a mis-configured
	# Employment Type (e.g. period 0 on a non-terminal stage) looping forever.
	for _i in range(len(NEXT_CONTRACT_TYPE) + 1):
		period = period_map.get(contract_type, 0)
		end = add_days(start, period - 1) if period else None
		plan.append((contract_type, start, end))

		if end is None or getdate(end) >= as_of:
			break  # current (or open-ended) stage — chain stops here

		next_type = get_next_contract_type(contract_type)
		if not next_type:
			break
		contract_type = next_type
		start = add_days(end, 1)

	return plan


def _seed_employee_contract_chain(employee, period_map, as_of):
	"""Create the full contract chain for one employee. Every stage is inserted
	as Signed (these are historical facts on paper); only the last one keeps
	next_stage_created = 0 so the daily job takes over from there.
	Raises ValueError with a human-readable reason when the employee is skipped."""
	if frappe.db.exists("Labor Contract", {"employee": employee}):
		raise ValueError(_("Already has a Labor Contract"))

	emp = frappe.db.get_value(
		"Employee", employee,
		["custom_probation_days", "date_of_joining", "status"], as_dict=True,
	)
	if not emp:
		raise ValueError(_("Employee not found"))
	if emp.status != "Active":
		raise ValueError(_("Employee is not Active"))
	if not emp.date_of_joining:
		raise ValueError(_("Date of Joining is not set"))

	_contract_type, skip_reason = classify_probation_days(emp.custom_probation_days)
	if skip_reason:
		raise ValueError(_probation_skip_message(skip_reason))

	plan = _plan_contract_chain(emp.date_of_joining, emp.custom_probation_days, period_map, as_of)
	if not plan:
		raise ValueError(_("Could not build a contract chain"))

	last_index = len(plan) - 1
	for i, (contract_type, start, _end) in enumerate(plan):
		doc = frappe.get_doc({
			"doctype": "Labor Contract",
			"employee": employee,
			"contract_type": contract_type,
			"start_date": start,
			# A stage that hasn't begun yet (future-dated joiner) is not signed yet
			"status": "Upcoming" if getdate(start) > as_of else "Signed",
		}).insert(ignore_permissions=True)

		if i < last_index:
			frappe.db.set_value(
				"Labor Contract", doc.name, "next_stage_created", 1, update_modified=False
			)

	return len(plan)


def _only_administrator():
	if frappe.session.user != "Administrator":
		frappe.throw(
			_("Only Administrator can seed contract history."), frappe.PermissionError
		)


def _seeding_candidates():
	"""Active employees that have no Labor Contract at all yet."""
	return frappe.db.sql(
		"""
		SELECT emp.name, emp.custom_probation_days, emp.date_of_joining
		FROM `tabEmployee` emp
		WHERE emp.status = 'Active'
		  AND NOT EXISTS (SELECT 1 FROM `tabLabor Contract` lc WHERE lc.employee = emp.name)
		ORDER BY emp.date_of_joining
		""",
		as_dict=True,
	)


@frappe.whitelist()
def get_contract_seeding_summary():
	"""Dry-run preview: how many employees/contracts seeding would create, and
	which stage each employee would end up on."""
	_only_administrator()

	period_map = _get_employment_type_periods()
	as_of = getdate(business_today())
	candidates = _seeding_candidates()

	total_contracts = 0
	eligible = 0
	skipped = {SKIP_NO_PROBATION: 0, SKIP_MISSING_PROBATION_DAYS: 0}
	missing_doj = 0
	by_current_stage = {}

	for emp in candidates:
		if not emp.date_of_joining:
			missing_doj += 1
			continue

		_contract_type, skip_reason = classify_probation_days(emp.custom_probation_days)
		if skip_reason:
			skipped[skip_reason] += 1
			continue

		plan = _plan_contract_chain(
			emp.date_of_joining, emp.custom_probation_days, period_map, as_of
		)
		if not plan:
			continue

		eligible += 1
		total_contracts += len(plan)
		current_stage = plan[-1][0]
		by_current_stage[current_stage] = by_current_stage.get(current_stage, 0) + 1

	return {
		"candidates": len(candidates),
		"eligible": eligible,
		"total_contracts": total_contracts,
		"no_probation_period": skipped[SKIP_NO_PROBATION],
		"missing_probation_days": skipped[SKIP_MISSING_PROBATION_DAYS],
		"missing_date_of_joining": missing_doj,
		"by_current_stage": by_current_stage,
	}


@frappe.whitelist()
def seed_all_contract_history():
	"""Queue the one-off full-history seeding for every Active employee that has
	no Labor Contract yet. Always runs in the background — this touches every
	employee on site."""
	_only_administrator()

	candidates = [e.name for e in _seeding_candidates()]
	if not candidates:
		return {"queued": False, "total": 0}

	frappe.enqueue(
		"customize_erpnext.customize_erpnext.doctype.labor_contract.labor_contract.background_seed_contract_history",
		queue="long",
		timeout=3600,
		employees_json=json.dumps(candidates),
		user=frappe.session.user,
		enqueue_after_commit=True,
	)
	return {"queued": True, "total": len(candidates)}


def background_seed_contract_history(employees_json, user):
	employees = json.loads(employees_json)
	period_map = _get_employment_type_periods()
	as_of = getdate(business_today())

	employees_seeded = 0
	contracts_created = 0
	errors = []

	for i, name in enumerate(employees):
		try:
			contracts_created += _seed_employee_contract_chain(name, period_map, as_of)
			employees_seeded += 1
		except ValueError as e:
			errors.append({"employee": name, "error": str(e)})
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Labor Contract seeding failed for {name}")
			errors.append({"employee": name, "error": _("Unexpected error — see Error Log")})

		if (i + 1) % 50 == 0:
			frappe.db.commit()
			frappe.publish_progress(
				(i + 1) * 100 / len(employees),
				title=_("Seeding Contract History"),
				description=_("{0} of {1} employees").format(i + 1, len(employees)),
			)

	frappe.db.commit()
	frappe.publish_realtime(
		event="labor_contract_seeding_complete",
		message={
			"employees_seeded": employees_seeded,
			"contracts_created": contracts_created,
			"skipped": len(errors),
			"errors": errors,
		},
		user=user,
	)


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
		WHERE lc.status = 'Signed'
		  AND lc.next_stage_created = 0
		  AND lc.next_contract_type IS NOT NULL AND lc.next_contract_type != ''
		  AND emp.status = 'Active'
		  AND DATEDIFF(lc.end_date, %(today)s) <= et.custom_warning_before
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
			lc.name, lc.employee, lc.employee_name, lc.designation,
			lc.contract_type, lc.end_date, lc.status,
			lc.next_contract_type, lc.next_sign_date, lc.next_stage_created,
			emp.status AS employee_status
		FROM `tabLabor Contract` lc
		INNER JOIN `tabEmployee` emp ON emp.name = lc.employee
		WHERE lc.end_date BETWEEN %(from_date)s AND %(to_date)s
		ORDER BY lc.end_date, lc.employee
		""",
		{"from_date": from_date, "to_date": to_date}, as_dict=True,
	)


def _blocking_reason(row):
	"""Why this contract can't have its next stage drafted — None when it can."""
	if not row.next_contract_type:
		return _("Indefinite-term — no next stage")
	if row.next_stage_created:
		return _("Next contract already created")
	if row.employee_status != "Active":
		return _("Employee is not Active")
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
	"""Upcoming đã quá ngày bắt đầu ký mà chưa Signed -> Overdue."""
	frappe.db.sql(
		"""
		UPDATE `tabLabor Contract`
		SET status = 'Overdue'
		WHERE status = 'Upcoming' AND start_date < %(today)s
		""",
		{"today": business_today()},
	)
	return frappe.db.sql("SELECT ROW_COUNT()")[0][0]


# =============================================================================
# Bulk "mark as Signed"
# =============================================================================

@frappe.whitelist()
def get_unsigned_contracts(employees=None, limit=500):
	"""Contracts still waiting to be signed — the picker list for the bulk tool
	when the user hasn't ticked any rows in the list view.

	No contract-type filter on purpose: this tool only confirms that an existing
	Upcoming/Overdue contract has been signed, it never chooses the type.
	"""
	frappe.has_permission("Labor Contract", "write", throw=True)

	if isinstance(employees, str):
		employees = frappe.parse_json(employees)

	conditions = ["lc.status IN ('Upcoming', 'Overdue')"]
	values = {"limit": cint(limit) or 500}
	if employees:
		conditions.append("lc.employee IN %(employees)s")
		values["employees"] = employees

	return frappe.db.sql(
		f"""
		SELECT
			lc.name, lc.employee, lc.employee_name, lc.designation,
			lc.contract_type, lc.start_date, lc.end_date, lc.status
		FROM `tabLabor Contract` lc
		WHERE {" AND ".join(conditions)}
		ORDER BY lc.start_date, lc.employee
		LIMIT %(limit)s
		""",
		values, as_dict=True,
	)


@frappe.whitelist()
def bulk_mark_signed(contracts):
	"""Flip the given contracts to Signed and mirror each employee's current
	contract type onto Employee.employment_type.

	Goes through the full document save (not db_set) so the controller keeps
	derived dates consistent and on_update fires the employment-type sync.
	"""
	frappe.has_permission("Labor Contract", "write", throw=True)

	if isinstance(contracts, str):
		contracts = frappe.parse_json(contracts)
	if not contracts:
		frappe.throw(_("Please select at least one contract"))

	signed = 0
	errors = []
	for name in contracts:
		try:
			doc = frappe.get_doc("Labor Contract", name)
			if doc.status == "Signed":
				errors.append({"contract": name, "error": _("Already Signed")})
				continue
			doc.status = "Signed"
			doc.save(ignore_permissions=True)
			signed += 1
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Bulk sign failed for {name}")
			errors.append({"contract": name, "error": _("Unexpected error — see Error Log")})

	# No explicit commit: Frappe commits at the end of a successful request.
	# Committing here would also break test isolation — tests call this
	# directly, and a commit escapes their rollback into the real database.
	return {"signed": signed, "skipped": len(errors), "errors": errors}


@frappe.whitelist()
def resync_all_employment_types():
	"""Backfill Employee.employment_type from existing contracts (one-off, after
	the field was introduced or contracts were bulk-imported).

	Administrator-only: it rewrites a field on every employee that has a
	contract, and it is authoritative — an employee with no signed, already
	started contract gets the field cleared.
	"""
	_only_administrator()

	employees = frappe.db.sql(
		"SELECT DISTINCT employee FROM `tabLabor Contract`", pluck=True
	)
	for name in employees:
		sync_employee_employment_type(name)
	# No explicit commit: Frappe commits at the end of a successful request.
	# Committing here would also break test isolation — tests call this
	# directly, and a commit escapes their rollback into the real database.
	return {"employees": len(employees)}
