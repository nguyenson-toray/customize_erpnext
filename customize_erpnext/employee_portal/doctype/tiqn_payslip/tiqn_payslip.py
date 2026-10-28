# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate

from customize_erpnext.employee_portal import payslip_structure as pss
from customize_erpnext.employee_portal.utils import (
	expected_pay_date,
	period_bounds,
	validate_period,
)

FINAL_SETTLEMENT_PAY_DAYS = 14  # paid within 14 days of leaving, not on the monthly pay day


class TIQNPayslip(Document):
	"""One employee x one pay period, numbers exactly as HR computed them in Excel.

	Deliberately NOT HRMS Salary Slip: that one recalculates from Salary Structure and
	attendance and would overwrite HR's figures. Nothing here is computed except the
	period dates and the report columns (`net_pay`, `gross_pay`...), copied from the lines
	that carry a Report Column.

	Lines (28/10/2026): the payslip keeps its own copy of the lines of its period's
	TIQN Payslip Structure + HR's numbers in `lines_json` (employee_portal/
	payslip_structure.py), written by Payslip Upload. A later structure never changes it.

	Status is changed only through `employee_portal.payslip_admin` (Publish /
	Withdraw), never by editing the field or by Data Import - publishing also creates
	the employee's notification.
	"""

	def validate(self):
		self.period = validate_period(self.period)
		self.set_dates()
		self.set_lines()
		self.block_status_change()
		self.block_published_edits()

	def set_dates(self):
		"""Period From / To = the period (26th -> 25th), cut to the days the employee was
		on the payroll: joined during it -> date of joining; left during it -> the day
		before relieving_date (🔴 relieving_date = first day OFF). Left during it also
		= final settlement: paid separately, within 14 days, no notification."""
		start, end = period_bounds(self.period)
		joined, relieving = frappe.db.get_value("Employee", self.employee, ["date_of_joining", "relieving_date"]) or (None, None)
		self.final_settlement = int(bool(relieving) and start < getdate(relieving) <= end)
		first = max(start, getdate(joined)) if joined else start
		last = add_days(relieving, -1) if self.final_settlement else end
		self.period_from = getdate(self.period_from) if self.period_from else first
		self.period_to = getdate(self.period_to) if self.period_to else last
		if not start <= self.period_from <= self.period_to <= end:
			frappe.throw(
				_("Period From / To must be inside the period {0} - {1}.").format(
					frappe.format(start, "Date"), frappe.format(end, "Date")
				)
			)
		if not self.pay_date:
			self.pay_date = (
				add_days(relieving, FINAL_SETTLEMENT_PAY_DAYS) if self.final_settlement else expected_pay_date(self.period)
			)

	def set_lines(self):
		"""Snapshot of the period's structure: kept as imported, layout re-derived (level,
		header) and numbers checked for the impossible only. A payslip made by hand starts
		with the structure's lines at 0."""
		expected = pss.structure_for_period(self.period)
		if self.is_new() or self.has_value_changed("period") or not self.structure:
			if not expected:
				frappe.throw(_("No Payslip Structure covers period {0}.").format(self.period))
			if self.structure and self.structure != expected and self.lines_json:
				frappe.throw(
					_("These lines belong to {0}, period {1} uses {2}. Upload the payslip again.").format(
						self.structure, self.period, expected
					)
				)
			self.structure = expected
		snapshot = pss.snapshot_of(self)
		lines = snapshot or pss.structure_lines(self.structure)
		snapshot = pss.make_snapshot(lines, pss.snapshot_values(snapshot))
		errors = pss.absurd_errors(snapshot, self.period)
		if errors:
			frappe.throw("<br>".join(errors), title=_("Impossible numbers"))
		self.lines_json = pss.dump_snapshot(snapshot)
		self.content_version = pss.content_version(snapshot)
		self.update(pss.key_values(snapshot))

	def block_status_change(self):
		"""Publishing notifies the employee and stamps published_on/by: only
		payslip_admin (which sets `flags.portal_status_change`) may do it. A Data Import
		with a "Status = Published" column must not slip a payslip out silently."""
		if self.flags.portal_status_change:
			return
		before = None if self.is_new() else self.get_doc_before_save()
		old = before.status if before else "Draft"
		if (self.status or "Draft") != old:
			frappe.throw(_("Change the status on the Payslip Upload page (Publish / Withdraw), not here."))

	def block_published_edits(self):
		"""An employee may already have read a published payslip. Changing numbers under
		them silently is exactly the dispute this module must avoid - withdraw first."""
		if self.is_new() or self.flags.allow_published_edit:
			return
		before = self.get_doc_before_save()
		if not before or before.status != "Published" or self.status != "Published":
			return

		def numbers(doc):
			return [(r.code, flt(r.amount, 2), flt(r.quantity, 2)) for r in pss.snapshot_of(doc)]

		if (
			numbers(before) != numbers(self)
			or before.employee != self.employee
			or before.period != self.period
			or (before.get("note") or "") != (self.get("note") or "")
		):
			frappe.throw(_("This payslip is published. Withdraw it on the Payslip Upload page before changing it."))
