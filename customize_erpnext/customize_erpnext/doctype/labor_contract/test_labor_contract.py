# Copyright (c) 2026, IT Team - TIQN and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, nowdate

from .labor_contract import (
	CONTRACT_1_YEAR,
	CONTRACT_3_YEAR,
	CONTRACT_INDEFINITE,
	PROBATION_30,
	PROBATION_60,
	SKIP_MISSING_PROBATION_DAYS,
	SKIP_NO_PROBATION,
	bulk_mark_signed,
	business_today,
	classify_probation_days,
	draft_expiring_contracts,
	get_next_contract_type,
	sync_employee_employment_type,
	get_expiring_contracts,
	get_probation_contract_candidates,
	_create_initial_labor_contract,
	_get_employment_type_periods,
	_mark_overdue,
	_materialize_next_stage,
	_plan_contract_chain,
	_resolve_target_employees,
	_seed_employee_contract_chain,
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

	def test_after_insert_skips_during_import(self):
		designation = frappe.db.get_value("Designation", {"custom_probation_days": "30"}, "name")
		if not designation:
			self.skipTest("No Designation with custom_probation_days=30 on this site")

		frappe.flags.in_import = True
		try:
			emp = _make_test_employee(designation=designation)
		finally:
			frappe.flags.in_import = False
		lc = frappe.get_all("Labor Contract", filters={"employee": emp.name})
		self.assertEqual(len(lc), 0)

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

	# ---- Bulk backfill target resolution ----

	def test_resolve_targets_matches_exact_intake_date_only(self):
		emp = _make_test_employee(date_of_joining="2026-05-10")

		self.assertIn(emp.name, _resolve_target_employees("Date of Joining", date_of_joining="2026-05-10"))
		# One day either side must NOT be picked up — each intake batch is its own run
		self.assertNotIn(emp.name, _resolve_target_employees("Date of Joining", date_of_joining="2026-05-09"))
		self.assertNotIn(emp.name, _resolve_target_employees("Date of Joining", date_of_joining="2026-05-11"))

	def test_resolve_targets_requires_a_date(self):
		self.assertRaises(frappe.ValidationError, _resolve_target_employees, "Date of Joining")

	# ---- Batch listing shown in the dialog ----

	def test_candidates_list_flags_who_gets_a_contract(self):
		designation = frappe.db.get_value("Designation", {"custom_probation_days": "30"}, "name")
		if not designation:
			self.skipTest("No Designation with custom_probation_days=30 on this site")

		doj = "2026-04-17"
		# in_import skips the after_insert hook, leaving this employee genuinely
		# contract-less — that's the row the dialog should offer to create.
		frappe.flags.in_import = True
		try:
			ok = _make_test_employee(designation=designation, date_of_joining=doj)
		finally:
			frappe.flags.in_import = False
		blank = _make_test_employee(date_of_joining=doj)  # no designation -> no probation days

		rows = get_probation_contract_candidates("Date of Joining", date_of_joining=doj)
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
		rows = get_probation_contract_candidates("Date of Joining", date_of_joining=doj)
		row = next(r for r in rows if r["employee"] == emp.name)

		self.assertFalse(row["will_create"])
		self.assertIn("Already", row["reason"])

	def test_candidates_list_empty_for_a_day_with_no_hires(self):
		self.assertEqual(
			get_probation_contract_candidates("Date of Joining", date_of_joining="1990-01-01"), []
		)

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

		targets = _resolve_target_employees("Date of Joining", date_of_joining="2026-05-10")
		self.assertNotIn(emp.name, targets)

	def test_resolve_targets_by_explicit_employee_list(self):
		emp = _make_test_employee()
		self.assertEqual(_resolve_target_employees("Employees", employees=[emp.name]), [emp.name])

	def test_resolve_targets_rejects_empty_employee_list(self):
		self.assertRaises(frappe.ValidationError, _resolve_target_employees, "Employees", employees=[])

	# ---- Seeding: contract chain planning (pure date math) ----

	def test_chain_for_brand_new_hire_is_probation_only(self):
		periods = _get_employment_type_periods()
		plan = _plan_contract_chain("2026-08-01", "30", periods, getdate("2026-08-04"))

		self.assertEqual(len(plan), 1)
		self.assertEqual(plan[0][0], PROBATION_30)
		self.assertEqual(str(plan[0][1]), "2026-08-01")
		self.assertEqual(str(plan[0][2]), "2026-08-30")

	def test_chain_is_contiguous_with_no_gaps(self):
		periods = _get_employment_type_periods()
		plan = _plan_contract_chain("2020-01-01", "30", periods, getdate("2026-08-04"))

		for previous, nxt in zip(plan, plan[1:]):
			self.assertEqual(
				str(nxt[1]), str(add_days(previous[2], 1)),
				f"gap between {previous[0]} and {nxt[0]}",
			)

	def test_chain_for_long_tenure_ends_on_indefinite(self):
		periods = _get_employment_type_periods()
		# Joined 2020: 30d probation + 1y + 3y is ~4 years, so by 2026 they are
		# on the Indefinite-term contract.
		plan = _plan_contract_chain("2020-01-01", "30", periods, getdate("2026-08-04"))

		self.assertEqual(
			[stage[0] for stage in plan],
			[PROBATION_30, CONTRACT_1_YEAR, CONTRACT_3_YEAR, CONTRACT_INDEFINITE],
		)
		self.assertIsNone(plan[-1][2])  # Indefinite-term has no end date

	def test_chain_stops_at_the_stage_covering_today(self):
		periods = _get_employment_type_periods()
		# 60d probation from 2026-01-01 ends 2026-03-01, then the 1-year contract
		# runs 2026-03-02 -> 2027-03-01, which covers 2026-08-04.
		plan = _plan_contract_chain("2026-01-01", "60", periods, getdate("2026-08-04"))

		self.assertEqual([stage[0] for stage in plan], [PROBATION_60, CONTRACT_1_YEAR])
		self.assertEqual(str(plan[-1][2]), "2027-03-01")

	def test_chain_empty_without_probation_days(self):
		periods = _get_employment_type_periods()
		self.assertEqual(_plan_contract_chain("2020-01-01", "", periods, getdate("2026-08-04")), [])
		self.assertEqual(_plan_contract_chain("2020-01-01", None, periods, getdate("2026-08-04")), [])

	# ---- Probation Days = 0 (special case: hired without probation) ----

	def test_classify_probation_days(self):
		self.assertEqual(classify_probation_days("30"), (PROBATION_30, None))
		self.assertEqual(classify_probation_days("60"), (PROBATION_60, None))
		# 0 is a deliberate "no probation" flag, NOT the same as unset
		self.assertEqual(classify_probation_days("0"), (None, SKIP_NO_PROBATION))
		self.assertEqual(classify_probation_days(""), (None, SKIP_MISSING_PROBATION_DAYS))
		self.assertEqual(classify_probation_days(None), (None, SKIP_MISSING_PROBATION_DAYS))

	def test_zero_probation_days_builds_no_chain(self):
		periods = _get_employment_type_periods()
		self.assertEqual(_plan_contract_chain("2020-01-01", "0", periods, getdate("2026-08-04")), [])

	def test_zero_probation_days_is_skipped_with_its_own_reason(self):
		emp = _make_test_employee()
		frappe.db.set_value("Employee", emp.name, "custom_probation_days", "0", update_modified=False)

		with self.assertRaises(ValueError) as ctx:
			_create_initial_labor_contract(emp.name)
		self.assertIn("manually", str(ctx.exception))

		# Nothing auto-created — HR decides the first stage by hand
		self.assertEqual(frappe.db.count("Labor Contract", {"employee": emp.name}), 0)

	def test_zero_probation_days_is_not_seeded(self):
		emp = _make_test_employee(date_of_joining="2020-01-01")
		periods = _get_employment_type_periods()
		frappe.db.set_value("Employee", emp.name, "custom_probation_days", "0", update_modified=False)

		with self.assertRaises(ValueError):
			_seed_employee_contract_chain(emp.name, periods, getdate("2026-08-04"))
		self.assertEqual(frappe.db.count("Labor Contract", {"employee": emp.name}), 0)

	# ---- Seeding: record creation ----

	def test_seed_creates_whole_chain_with_correct_flags(self):
		emp = _make_test_employee(date_of_joining="2020-01-01")
		periods = _get_employment_type_periods()
		frappe.db.set_value("Employee", emp.name, "custom_probation_days", "30", update_modified=False)

		count = _seed_employee_contract_chain(emp.name, periods, getdate("2026-08-04"))
		self.assertEqual(count, 4)

		contracts = frappe.get_all(
			"Labor Contract",
			filters={"employee": emp.name},
			fields=["contract_type", "status", "next_stage_created", "end_date"],
			order_by="start_date asc",
		)
		self.assertEqual(
			[c.contract_type for c in contracts],
			[PROBATION_30, CONTRACT_1_YEAR, CONTRACT_3_YEAR, CONTRACT_INDEFINITE],
		)
		# All historical/current stages are Signed...
		self.assertTrue(all(c.status == "Signed" for c in contracts))
		# ...and every stage but the last is flagged so the daily job won't
		# create a duplicate successor for it.
		self.assertEqual([c.next_stage_created for c in contracts], [1, 1, 1, 0])

	def test_seed_is_idempotent(self):
		emp = _make_test_employee(date_of_joining="2020-01-01")
		periods = _get_employment_type_periods()
		frappe.db.set_value("Employee", emp.name, "custom_probation_days", "30", update_modified=False)

		_seed_employee_contract_chain(emp.name, periods, getdate("2026-08-04"))
		with self.assertRaises(ValueError):
			_seed_employee_contract_chain(emp.name, periods, getdate("2026-08-04"))

		self.assertEqual(frappe.db.count("Labor Contract", {"employee": emp.name}), 4)

	def test_seeded_current_stage_is_not_picked_up_twice_by_daily_job(self):
		"""The seeded chain must leave the daily job with exactly one open stage."""
		emp = _make_test_employee(date_of_joining="2026-01-01")
		periods = _get_employment_type_periods()
		frappe.db.set_value("Employee", emp.name, "custom_probation_days", "30", update_modified=False)

		_seed_employee_contract_chain(emp.name, periods, getdate(nowdate()))
		before = frappe.db.count("Labor Contract", {"employee": emp.name})

		_materialize_next_stage()

		after = frappe.db.count("Labor Contract", {"employee": emp.name})
		# The 1-year stage seeded today runs well past the 30-day warning window,
		# so nothing new is due yet.
		self.assertEqual(after, before)
