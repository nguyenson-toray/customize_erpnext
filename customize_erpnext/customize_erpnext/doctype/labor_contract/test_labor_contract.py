# Copyright (c) 2026, IT Team - TIQN and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from .labor_contract import (
	NEXT_CONTRACT_TYPE as NEXT_STAGES,
	CONTRACT_1_YEAR,
	CONTRACT_3_YEAR,
	CONTRACT_INDEFINITE,
	MISSING_CONTRACT,
	PROBATION_30,
	PROBATION_60,
	SKIP_MISSING_PROBATION_DAYS,
	SKIP_NO_PROBATION,
	bulk_mark_signed,
	business_today,
	compute_end_date,
	contract_in_force,
	positions_at,
	remove_appendix_on_cancel,
	classify_probation_days,
	draft_expiring_contracts,
	get_next_contract_type,
	sync_employee_employment_type,
	get_expiring_contracts,
	get_probation_contract_candidates,
	leaves_before,
	_create_initial_labor_contract,
	_mark_overdue,
	_materialize_next_stage,
	_resolve_target_employees,
)

# On IntegrationTestCase, the doctype test records and all
# link-field test record dependencies are recursively loaded
# Use these module variables to add/remove to/from that list
EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
# Employee's (and its own link fields') test modules transitively bootstrap the
# whole standard ERPNext test dataset (price lists etc.), which conflicts with
# this production site's existing data. Tests use real/throwaway records via
# _make_test_employee() and the site's existing Employment Type/Designation
# instead of Frappe-generated test fixtures.
IGNORE_TEST_RECORD_DEPENDENCIES = [
	"Employee", "Employment Type", "Designation", "Department", "Section", "Group",
]


def _make_test_employee(designation=None, date_of_joining=None):
	"""Insert a minimal but valid Employee for integration tests.
	Reuses an existing Company/Department already present on the site instead
	of creating new master data."""
	company = frappe.db.get_value("Company", {}, "name")
	department = frappe.db.get_value("Department", {"company": company}, "name")

	doc = frappe.get_doc({
		"doctype": "Employee",
		"first_name": "LCTest",
		"last_name": frappe.generate_hash(length=6),
		"status": "Active",
		"gender": frappe.db.get_value("Gender", {}, "name"),
		"date_of_birth": "1995-01-01",
		"date_of_joining": date_of_joining or nowdate(),
		"company": company,
		"department": department,
	})
	if designation:
		doc.designation = designation
	doc.insert(ignore_permissions=True)
	return doc


class IntegrationTestLaborContract(IntegrationTestCase):
	"""
	Integration tests for LaborContract.
	Use this class for testing interactions between multiple components.
	"""

	# ---- get_next_contract_type (pure sequence logic) ----

	def test_sequence_from_probation_30(self):
		self.assertEqual(get_next_contract_type(PROBATION_30), CONTRACT_1_YEAR)

	def test_sequence_from_probation_60(self):
		self.assertEqual(get_next_contract_type(PROBATION_60), CONTRACT_1_YEAR)

	def test_sequence_from_1_year(self):
		self.assertEqual(get_next_contract_type(CONTRACT_1_YEAR), CONTRACT_3_YEAR)

	def test_sequence_from_3_year(self):
		self.assertEqual(get_next_contract_type(CONTRACT_3_YEAR), CONTRACT_INDEFINITE)

	def test_sequence_from_indefinite_is_terminal(self):
		self.assertIsNone(get_next_contract_type(CONTRACT_INDEFINITE))

	# ---- calculate_dates() ----

	def test_calculate_dates_probation_30(self):
		doc = frappe.new_doc("Labor Contract")
		doc.contract_type = PROBATION_30
		doc.start_date = "2026-01-01"
		doc.calculate_dates()
		self.assertEqual(str(doc.end_date), "2026-01-30")  # 30 days inclusive
		self.assertEqual(doc.next_contract_type, CONTRACT_1_YEAR)
		self.assertEqual(str(doc.next_sign_date), "2026-01-31")

	def test_calculate_dates_indefinite_has_no_end_or_next(self):
		doc = frappe.new_doc("Labor Contract")
		doc.contract_type = CONTRACT_INDEFINITE
		doc.start_date = "2026-01-01"
		doc.calculate_dates()
		self.assertIsNone(doc.end_date)
		self.assertIsNone(doc.next_contract_type)
		self.assertIsNone(doc.next_sign_date)

	def test_calculate_dates_noop_without_start_date(self):
		doc = frappe.new_doc("Labor Contract")
		doc.contract_type = PROBATION_30
		doc.calculate_dates()
		self.assertIsNone(doc.end_date)

	# ---- Trigger A: create_initial_contract_on_employee_insert ----

	def test_after_insert_creates_probation_contract(self):
		"""The hooks.py Employee.after_insert wiring fires create_initial_contract_on_employee_insert
		for real during .insert() — no need to call it manually here."""
		designation = frappe.db.get_value("Designation", {"custom_probation_days": "30"}, "name")
		if not designation:
			self.skipTest("No Designation with custom_probation_days=30 on this site")

		emp = _make_test_employee(designation=designation, date_of_joining="2026-02-01")

		lc = frappe.get_all(
			"Labor Contract",
			filters={"employee": emp.name},
			fields=["contract_type", "start_date", "status"],
		)
		self.assertEqual(len(lc), 1)
		self.assertEqual(lc[0].contract_type, PROBATION_30)
		self.assertEqual(str(lc[0].start_date), "2026-02-01")
		self.assertEqual(lc[0].status, "Upcoming")

	def test_after_insert_skips_when_probation_days_unset(self):
		emp = _make_test_employee(designation=None)
		lc = frappe.get_all("Labor Contract", filters={"employee": emp.name})
		self.assertEqual(len(lc), 0)

	def test_after_insert_also_runs_during_data_import(self):
		# Data Import is how new hires actually arrive, so it must create the contract too
		designation = frappe.db.get_value("Designation", {"custom_probation_days": "30"}, "name")
		if not designation:
			self.skipTest("No Designation with custom_probation_days=30 on this site")

		frappe.flags.in_import = True
		try:
			emp = _make_test_employee(designation=designation)
		finally:
			frappe.flags.in_import = False
		lc = frappe.get_all("Labor Contract", filters={"employee": emp.name}, pluck="contract_type")
		self.assertEqual(lc, [PROBATION_30])

	# ---- Trigger B: daily scheduler ----

	def test_materialize_next_stage_within_warning_window(self):
		emp = _make_test_employee(date_of_joining="2025-01-01")
		# Probation 30 warning_before = 7. Signed contract ending in 5 days -> due.
		start = add_days(nowdate(), -25)
		lc = frappe.get_doc({
			"doctype": "Labor Contract",
			"employee": emp.name,
			"contract_type": PROBATION_30,
			"start_date": start,
			"status": "Signed",
		}).insert(ignore_permissions=True)

		created = _materialize_next_stage()
		self.assertGreaterEqual(created, 1)

		next_lc = frappe.get_all(
			"Labor Contract",
			filters={"employee": emp.name, "contract_type": CONTRACT_1_YEAR},
			fields=["start_date"],
		)
		self.assertEqual(len(next_lc), 1)
		self.assertEqual(str(next_lc[0].start_date), str(add_days(lc.end_date, 1)))
		self.assertEqual(frappe.db.get_value("Labor Contract", lc.name, "next_stage_created"), 1)

	def test_materialize_skips_outside_warning_window(self):
		emp = _make_test_employee(date_of_joining=nowdate())
		# Just started today -> end_date far in the future, not due yet.
		lc = frappe.get_doc({
			"doctype": "Labor Contract",
			"employee": emp.name,
			"contract_type": PROBATION_30,
			"start_date": nowdate(),
			"status": "Signed",
		}).insert(ignore_permissions=True)

		_materialize_next_stage()

		self.assertEqual(frappe.db.get_value("Labor Contract", lc.name, "next_stage_created"), 0)
		next_lc = frappe.get_all(
			"Labor Contract",
			filters={"employee": emp.name, "contract_type": CONTRACT_1_YEAR},
		)
		self.assertEqual(len(next_lc), 0)

	def test_materialize_skips_inactive_employee(self):
		emp = _make_test_employee(date_of_joining="2025-01-01")
		start = add_days(nowdate(), -25)
		lc = frappe.get_doc({
			"doctype": "Labor Contract",
			"employee": emp.name,
			"contract_type": PROBATION_30,
			"start_date": start,
			"status": "Signed",
		}).insert(ignore_permissions=True)
		frappe.db.set_value("Employee", emp.name, "status", "Left", update_modified=False)

		_materialize_next_stage()

		self.assertEqual(frappe.db.get_value("Labor Contract", lc.name, "next_stage_created"), 0)

	def test_mark_overdue_transitions_past_start_date(self):
		emp = _make_test_employee()
		lc = frappe.get_doc({
			"doctype": "Labor Contract",
			"employee": emp.name,
			"contract_type": CONTRACT_1_YEAR,
			"start_date": add_days(nowdate(), -1),
			"status": "Upcoming",
		}).insert(ignore_permissions=True)

		_mark_overdue()

		self.assertEqual(frappe.db.get_value("Labor Contract", lc.name, "status"), "Overdue")

	def test_mark_overdue_leaves_future_upcoming_alone(self):
		emp = _make_test_employee()
		lc = frappe.get_doc({
			"doctype": "Labor Contract",
			"employee": emp.name,
			"contract_type": CONTRACT_1_YEAR,
			"start_date": add_days(nowdate(), 5),
			"status": "Upcoming",
		}).insert(ignore_permissions=True)

		_mark_overdue()

		self.assertEqual(frappe.db.get_value("Labor Contract", lc.name, "status"), "Upcoming")

	# ---- Leaving before the next contract starts ----

	def test_leaves_before_uses_relieving_date_as_first_day_off(self):
		# relieving_date is the first day off: leaving ON the start day = not needed
		self.assertTrue(leaves_before("2027-04-19", "2027-04-19"))
		self.assertTrue(leaves_before("2026-10-22", "2027-04-19"))
		self.assertFalse(leaves_before("2027-04-20", "2027-04-19"))
		self.assertFalse(leaves_before(None, "2027-04-19"))
		self.assertFalse(leaves_before("2026-10-22", None))

	# ---- Bulk backfill target resolution ----

	def test_resolve_targets_lists_active_employees_without_contract(self):
		designation = frappe.db.get_value("Designation", {"custom_probation_days": "30"}, "name")
		if not designation:
			self.skipTest("No Designation with custom_probation_days=30 on this site")

		missing = _make_test_employee(designation=designation, date_of_joining="2026-05-10")
		# the after_insert hook gave it a contract; take it away to make it "missing"
		frappe.db.delete("Labor Contract", {"employee": missing.name})
		# no designation -> empty Probation Days = special role, no contract needed
		no_probation = _make_test_employee(date_of_joining="2026-05-10")
		covered = _make_test_employee(designation=designation, date_of_joining="2026-05-10")

		targets = _resolve_target_employees(MISSING_CONTRACT)
		self.assertIn(missing.name, targets)
		self.assertNotIn(no_probation.name, targets)
		self.assertNotIn(covered.name, targets)

	# ---- Batch listing shown in the dialog ----

	def test_candidates_list_flags_who_gets_a_contract(self):
		designation = frappe.db.get_value("Designation", {"custom_probation_days": "30"}, "name")
		if not designation:
			self.skipTest("No Designation with custom_probation_days=30 on this site")

		doj = "2026-04-17"
		ok = _make_test_employee(designation=designation, date_of_joining=doj)
		# drop the hook's contract: a contract-less employee is the row the dialog
		# should offer to create
		frappe.db.delete("Labor Contract", {"employee": ok.name})
		blank = _make_test_employee(date_of_joining=doj)  # no designation -> no probation days

		rows = get_probation_contract_candidates("Employees", employees=[ok.name, blank.name])
		by_employee = {r["employee"]: r for r in rows}

		self.assertIn(ok.name, by_employee)
		self.assertTrue(by_employee[ok.name]["will_create"])
		self.assertEqual(by_employee[ok.name]["contract_type"], PROBATION_30)
		self.assertTrue(by_employee[ok.name]["employee_name"])

		self.assertIn(blank.name, by_employee)
		self.assertFalse(by_employee[blank.name]["will_create"])
		self.assertTrue(by_employee[blank.name]["reason"])

	def test_candidates_list_marks_existing_contract(self):
		designation = frappe.db.get_value("Designation", {"custom_probation_days": "30"}, "name")
		if not designation:
			self.skipTest("No Designation with custom_probation_days=30 on this site")

		doj = "2026-04-18"
		emp = _make_test_employee(designation=designation, date_of_joining=doj)
		# after_insert already created one, so this employee must show as skipped
		rows = get_probation_contract_candidates("Employees", employees=[emp.name])
		row = next(r for r in rows if r["employee"] == emp.name)

		self.assertFalse(row["will_create"])
		self.assertIn("Already", row["reason"])


	# ---- Review Expiring Contracts (date-range renewal tool) ----

	def _expiring_contract(self, status="Signed", start_date="2026-09-01"):
		"""A 30-day probation contract, so end_date = start_date + 29."""
		emp = _make_test_employee(date_of_joining=start_date)
		return frappe.get_doc({
			"doctype": "Labor Contract",
			"employee": emp.name,
			"contract_type": PROBATION_30,
			"start_date": start_date,
			"status": status,
		}).insert(ignore_permissions=True)

	def test_expiring_list_finds_contracts_ending_in_range(self):
		lc = self._expiring_contract()  # ends 2026-09-30
		self.assertEqual(str(lc.end_date), "2026-09-30")

		rows = get_expiring_contracts("2026-09-01", "2026-09-30")
		row = next(r for r in rows if r["name"] == lc.name)
		self.assertTrue(row["can_draft"])
		self.assertEqual(row["next_contract_type"], CONTRACT_1_YEAR)

		# A range that doesn't cover the end date must not list it
		outside = get_expiring_contracts("2026-10-01", "2026-10-31")
		self.assertNotIn(lc.name, [r["name"] for r in outside])

	def test_expiring_list_blocks_unsigned_contract(self):
		lc = self._expiring_contract(status="Upcoming")
		row = next(r for r in get_expiring_contracts("2026-09-01", "2026-09-30") if r["name"] == lc.name)
		self.assertFalse(row["can_draft"])
		self.assertIn("Signed", row["reason"])

	def test_expiring_list_blocks_indefinite_term(self):
		emp = _make_test_employee()
		lc = frappe.get_doc({
			"doctype": "Labor Contract",
			"employee": emp.name,
			"contract_type": CONTRACT_INDEFINITE,
			"start_date": "2026-09-01",
			"status": "Signed",
		}).insert(ignore_permissions=True)
		# No end_date at all, so it can never show up in an end-date range
		self.assertIsNone(lc.end_date)
		self.assertNotIn(
			lc.name, [r["name"] for r in get_expiring_contracts("2026-01-01", "2030-12-31")]
		)

	def test_drafting_creates_next_stage_and_is_idempotent(self):
		lc = self._expiring_contract()

		result = draft_expiring_contracts("2026-09-01", "2026-09-30")
		self.assertGreaterEqual(result["created"], 1)

		nxt = frappe.get_all(
			"Labor Contract",
			filters={"employee": lc.employee, "contract_type": CONTRACT_1_YEAR},
			fields=["start_date", "status"],
		)
		self.assertEqual(len(nxt), 1)
		# Starts the day after the old one ends, as an unsigned draft
		self.assertEqual(str(nxt[0].start_date), "2026-10-01")
		self.assertEqual(nxt[0].status, "Upcoming")
		self.assertEqual(frappe.db.get_value("Labor Contract", lc.name, "next_stage_created"), 1)

		# Running it again must not duplicate
		draft_expiring_contracts("2026-09-01", "2026-09-30")
		self.assertEqual(
			frappe.db.count("Labor Contract", {"employee": lc.employee, "contract_type": CONTRACT_1_YEAR}), 1
		)

	def test_expiring_requires_a_valid_range(self):
		self.assertRaises(frappe.ValidationError, get_expiring_contracts, None, "2026-09-30")
		self.assertRaises(frappe.ValidationError, get_expiring_contracts, "2026-09-30", "2026-09-01")

	# ---- Bulk mark as Signed + Employee.employment_type mirror ----

	def _contract(self, employee, contract_type, start_date, status="Upcoming"):
		return frappe.get_doc({
			"doctype": "Labor Contract",
			"employee": employee,
			"contract_type": contract_type,
			"start_date": start_date,
			"status": status,
		}).insert(ignore_permissions=True)

	def test_signing_mirrors_contract_type_onto_employee(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		lc = self._contract(emp.name, CONTRACT_1_YEAR, "2026-01-01")

		# Not signed yet -> employee keeps whatever it had (nothing)
		self.assertIsNone(frappe.db.get_value("Employee", emp.name, "employment_type"))

		result = bulk_mark_signed([lc.name])
		self.assertEqual(result["signed"], 1)
		self.assertEqual(frappe.db.get_value("Labor Contract", lc.name, "status"), "Signed")
		self.assertEqual(
			frappe.db.get_value("Employee", emp.name, "employment_type"), CONTRACT_1_YEAR
		)

	def test_employment_type_follows_the_current_stage_not_the_saved_one(self):
		"""Re-saving an old stage must not drag the employee back to probation."""
		emp = _make_test_employee(date_of_joining="2020-01-01")
		old = self._contract(emp.name, PROBATION_30, "2020-01-01", status="Signed")
		self._contract(emp.name, CONTRACT_3_YEAR, "2025-01-01", status="Signed")

		self.assertEqual(
			frappe.db.get_value("Employee", emp.name, "employment_type"), CONTRACT_3_YEAR
		)

		# Touching the 2020 probation record leaves the mirror on the current stage
		old.reload()
		old.save(ignore_permissions=True)
		self.assertEqual(
			frappe.db.get_value("Employee", emp.name, "employment_type"), CONTRACT_3_YEAR
		)

	def test_future_signed_contract_does_not_take_effect_yet(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		self._contract(emp.name, CONTRACT_1_YEAR, "2026-01-01", status="Signed")
		# Already signed but starts next year — not in effect today
		self._contract(emp.name, CONTRACT_3_YEAR, add_days(nowdate(), 30), status="Signed")

		self.assertEqual(
			frappe.db.get_value("Employee", emp.name, "employment_type"), CONTRACT_1_YEAR
		)

	def test_bulk_sign_skips_already_signed(self):
		emp = _make_test_employee()
		lc = self._contract(emp.name, CONTRACT_1_YEAR, "2026-01-01", status="Signed")

		result = bulk_mark_signed([lc.name])
		self.assertEqual(result["signed"], 0)
		self.assertEqual(result["skipped"], 1)

	def test_bulk_sign_rejects_empty_selection(self):
		self.assertRaises(frappe.ValidationError, bulk_mark_signed, [])

	def test_deleting_current_contract_rolls_employment_type_back(self):
		emp = _make_test_employee(date_of_joining="2020-01-01")
		self._contract(emp.name, PROBATION_30, "2020-01-01", status="Signed")
		current = self._contract(emp.name, CONTRACT_3_YEAR, "2025-01-01", status="Signed")
		self.assertEqual(
			frappe.db.get_value("Employee", emp.name, "employment_type"), CONTRACT_3_YEAR
		)

		current.delete()
		self.assertEqual(
			frappe.db.get_value("Employee", emp.name, "employment_type"), PROBATION_30
		)

	def test_sync_is_a_noop_without_signed_contracts(self):
		emp = _make_test_employee()
		self._contract(emp.name, CONTRACT_1_YEAR, "2026-01-01", status="Upcoming")
		sync_employee_employment_type(emp.name)
		self.assertIsNone(frappe.db.get_value("Employee", emp.name, "employment_type"))

	def test_sync_keeps_imported_employment_type_until_a_contract_is_signed(self):
		# New hire imported as probationary; the hook's contract is still Upcoming
		emp = _make_test_employee()
		frappe.db.set_value("Employee", emp.name, "employment_type", PROBATION_30)
		self._contract(emp.name, CONTRACT_1_YEAR, "2026-01-01", status="Upcoming")
		sync_employee_employment_type(emp.name)
		self.assertEqual(frappe.db.get_value("Employee", emp.name, "employment_type"), PROBATION_30)

	# ---- Deleting a follow-up must free the predecessor to be redrafted ----

	def test_deleting_next_stage_clears_the_predecessor_flag(self):
		lc = self._expiring_contract()  # 30-day probation, ends 2026-09-30
		draft_expiring_contracts("2026-09-01", "2026-09-30")
		self.assertEqual(frappe.db.get_value("Labor Contract", lc.name, "next_stage_created"), 1)

		follow_up = frappe.get_all(
			"Labor Contract",
			filters={"employee": lc.employee, "contract_type": CONTRACT_1_YEAR},
			pluck="name",
		)
		self.assertEqual(len(follow_up), 1)

		# HR realises it was wrong and deletes it
		frappe.delete_doc("Labor Contract", follow_up[0], ignore_permissions=True)

		# The predecessor must be redraftable again, not stuck forever
		self.assertEqual(frappe.db.get_value("Labor Contract", lc.name, "next_stage_created"), 0)
		row = next(r for r in get_expiring_contracts("2026-09-01", "2026-09-30") if r["name"] == lc.name)
		self.assertTrue(row["can_draft"])

		result = draft_expiring_contracts("2026-09-01", "2026-09-30")
		self.assertGreaterEqual(result["created"], 1)

	def test_deleting_an_unrelated_contract_leaves_flags_alone(self):
		emp = _make_test_employee(date_of_joining="2020-01-01")
		first = self._contract(emp.name, PROBATION_30, "2020-01-01", status="Signed")
		frappe.db.set_value("Labor Contract", first.name, "next_stage_created", 1, update_modified=False)
		# Not the day after `first` ends -> not its successor
		unrelated = self._contract(emp.name, CONTRACT_1_YEAR, "2024-06-01", status="Signed")

		unrelated.delete()

		self.assertEqual(frappe.db.get_value("Labor Contract", first.name, "next_stage_created"), 1)

	# ---- One source of truth for "today" ----

	def test_business_today_matches_the_database(self):
		self.assertEqual(
			str(business_today()), str(frappe.db.sql("SELECT CURDATE()")[0][0])
		)

	def test_resolve_targets_excludes_left_employees(self):
		emp = _make_test_employee(date_of_joining="2026-05-10")
		frappe.db.set_value("Employee", emp.name, "status", "Left", update_modified=False)

		targets = _resolve_target_employees(MISSING_CONTRACT)
		self.assertNotIn(emp.name, targets)

	def test_resolve_targets_by_explicit_employee_list(self):
		emp = _make_test_employee()
		self.assertEqual(_resolve_target_employees("Employees", employees=[emp.name]), [emp.name])

	def test_resolve_targets_rejects_empty_employee_list(self):
		self.assertRaises(frappe.ValidationError, _resolve_target_employees, "Employees", employees=[])

	# ---- Probation Days = 0 (special case: hired without probation) ----

	def test_classify_probation_days(self):
		self.assertEqual(classify_probation_days("30"), (PROBATION_30, None))
		self.assertEqual(classify_probation_days("60"), (PROBATION_60, None))
		# 0 is a deliberate "no probation" flag, NOT the same as unset
		self.assertEqual(classify_probation_days("0"), (None, SKIP_NO_PROBATION))
		self.assertEqual(classify_probation_days(""), (None, SKIP_MISSING_PROBATION_DAYS))
		self.assertEqual(classify_probation_days(None), (None, SKIP_MISSING_PROBATION_DAYS))

	def test_zero_probation_days_is_skipped_with_its_own_reason(self):
		emp = _make_test_employee()
		frappe.db.set_value("Employee", emp.name, "custom_probation_days", "0", update_modified=False)

		with self.assertRaises(ValueError) as ctx:
			_create_initial_labor_contract(emp.name)
		self.assertIn("manually", str(ctx.exception))

		# Nothing auto-created — HR decides the first stage by hand
		self.assertEqual(frappe.db.count("Labor Contract", {"employee": emp.name}), 0)

	# ---- v3: end dates (probation by days, 1Y/3Y by calendar year) ----

	def test_end_date_probation_by_days(self):
		self.assertEqual(str(compute_end_date(PROBATION_30, "2026-01-01")), "2026-01-30")
		self.assertEqual(str(compute_end_date(PROBATION_60, "2026-01-01")), "2026-03-01")

	def test_end_date_fixed_term_by_calendar_year(self):
		self.assertEqual(str(compute_end_date(CONTRACT_1_YEAR, "2024-03-29")), "2025-03-28")
		self.assertEqual(str(compute_end_date(CONTRACT_3_YEAR, "2022-12-31")), "2025-12-30")
		# a leap year inside the term: still the same date minus one, not 365 days
		self.assertEqual(str(compute_end_date(CONTRACT_1_YEAR, "2023-06-01")), "2024-05-31")

	def test_end_date_29_february_counts_as_1_march(self):
		self.assertEqual(str(compute_end_date(CONTRACT_1_YEAR, "2024-02-29")), "2025-02-28")
		self.assertEqual(str(compute_end_date(CONTRACT_3_YEAR, "2024-02-29")), "2027-02-28")

	def test_end_date_indefinite_is_open(self):
		self.assertIsNone(compute_end_date(CONTRACT_INDEFINITE, "2026-01-01"))

	# ---- v3: names = document numbers ----

	def test_contract_names_follow_the_stage(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		self.assertEqual(self._contract(emp.name, PROBATION_30, "2026-01-01").name, f"{emp.name}-HD")
		self.assertEqual(self._contract(emp.name, CONTRACT_1_YEAR, "2026-01-31").name, f"{emp.name}-HD1")
		self.assertEqual(self._contract(emp.name, CONTRACT_3_YEAR, "2027-01-31").name, f"{emp.name}-HD2")
		self.assertEqual(self._contract(emp.name, CONTRACT_INDEFINITE, "2030-01-31").name, f"{emp.name}-HD3")

	def test_duplicate_stage_gets_a_suffix(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		self._contract(emp.name, CONTRACT_1_YEAR, "2026-01-01")
		self.assertEqual(self._contract(emp.name, CONTRACT_1_YEAR, "2027-01-01").name, f"{emp.name}-HD1-2")
		self.assertEqual(self._contract(emp.name, CONTRACT_1_YEAR, "2028-01-01").name, f"{emp.name}-HD1-3")

	def test_contract_type_outside_the_chain_is_rejected(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		other = frappe.db.get_value("Employment Type", {"name": ["not in", list(NEXT_STAGES)]}, "name")
		if not other:
			self.skipTest("Only chain Employment Types exist on this site")
		self.assertRaises(frappe.ValidationError, self._contract, emp.name, other, "2026-01-01")

	# ---- v3: appendices ----

	def _appendix(self, employee, effective, **extra):
		return frappe.get_doc({
			"doctype": "Labor Contract",
			"employee": employee,
			"document_type": "Appendix",
			"start_date": effective,
			**extra,
		}).insert(ignore_permissions=True)

	def test_appendix_name_and_parent_contract(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		self._contract(emp.name, PROBATION_30, "2026-01-01", status="Signed")
		year = self._contract(emp.name, CONTRACT_1_YEAR, "2026-01-31", status="Signed")

		pl = self._appendix(emp.name, "2026-05-26")
		self.assertEqual(pl.name, f"PL-{emp.name}-2605")
		self.assertEqual(pl.parent_contract, year.name)
		self.assertIsNone(pl.end_date)
		self.assertEqual(contract_in_force(emp.name, "2026-01-15"), f"{emp.name}-HD")

		second = self._appendix(emp.name, "2026-05-30")
		self.assertEqual(second.name, f"PL-{emp.name}-2605-2")

	def test_appendix_without_contract_in_force_is_rejected(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		self.assertRaises(frappe.ValidationError, self._appendix, emp.name, "2026-05-26")

	def test_appendix_month_cannot_move(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		self._contract(emp.name, CONTRACT_1_YEAR, "2026-01-01", status="Signed")
		pl = self._appendix(emp.name, "2026-05-26")
		pl.start_date = "2026-05-02"
		pl.save(ignore_permissions=True)  # same month: fine
		pl.start_date = "2026-06-02"
		self.assertRaises(frappe.ValidationError, pl.save, ignore_permissions=True)

	def test_signed_appendix_does_not_change_employment_type(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		self._contract(emp.name, CONTRACT_1_YEAR, "2026-01-01", status="Signed")
		self.assertEqual(frappe.db.get_value("Employee", emp.name, "employment_type"), CONTRACT_1_YEAR)
		pl = self._appendix(emp.name, "2026-02-26")
		bulk_mark_signed([pl.name])
		self.assertEqual(frappe.db.get_value("Employee", emp.name, "employment_type"), CONTRACT_1_YEAR)

	def test_overdue_also_applies_to_appendices(self):
		emp = _make_test_employee(date_of_joining="2025-01-01")
		self._contract(emp.name, CONTRACT_1_YEAR, add_days(nowdate(), -30), status="Signed")
		pl = self._appendix(emp.name, add_days(nowdate(), -2))
		_mark_overdue()
		self.assertEqual(frappe.db.get_value("Labor Contract", pl.name, "status"), "Overdue")

	def test_appendix_removed_or_kept_on_cancel(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		self._contract(emp.name, CONTRACT_1_YEAR, "2026-01-01", status="Signed")
		source = frappe._dict(doctype="Employee Promotion", name="HR-EMP-PRO-TEST-LC")
		pl = self._appendix(
			emp.name, "2026-03-01",
			reference_doctype=source.doctype, reference_name=source.name,
		)
		frappe.db.set_value("Labor Contract", pl.name, "status", "Signed")
		self.assertRaises(frappe.ValidationError, remove_appendix_on_cancel, source)

		frappe.db.set_value("Labor Contract", pl.name, "status", "Upcoming")
		remove_appendix_on_cancel(source)
		self.assertFalse(frappe.db.exists("Labor Contract", pl.name))

	# ---- v3: signing date ----

	def test_bulk_sign_records_the_signing_date(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		lc = self._contract(emp.name, PROBATION_30, "2026-01-01")
		bulk_mark_signed([lc.name], signed_on="2026-01-03")
		self.assertEqual(str(frappe.db.get_value("Labor Contract", lc.name, "signed_on")), "2026-01-03")

	def test_form_sign_defaults_signed_on_to_today(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		lc = self._contract(emp.name, PROBATION_30, "2026-01-01")
		lc.status = "Signed"
		lc.save(ignore_permissions=True)
		self.assertEqual(getdate(lc.signed_on), getdate(business_today()))

	def test_inserting_a_signed_record_leaves_signed_on_empty(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		lc = self._contract(emp.name, PROBATION_30, "2026-01-01", status="Signed")
		self.assertIsNone(lc.signed_on)

	# ---- v3: position on a date (Internal Work History) ----

	def test_positions_fall_back_to_the_employee_without_history(self):
		emp = _make_test_employee(date_of_joining="2026-01-01")
		[position] = positions_at([(emp.name, "2026-02-01")])
		self.assertEqual(position.department, emp.department)
