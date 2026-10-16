# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from customize_erpnext.employee_portal.utils import expected_pay_date, period_bounds, validate_period

NET_PAY_ABBR = "9"


class TIQNPayslip(Document):
	"""One employee x one pay period, numbers exactly as HR computed them in Excel.

	Deliberately NOT HRMS Salary Slip: that one recalculates from Salary Structure and
	attendance and would overwrite HR's figures. Nothing here is computed except the
	period dates and `net_pay`, which is copied from component 9.

	Status is changed only through `employee_portal.payslip_admin` (Publish /
	Withdraw), never by editing the field - publishing also creates the employee's
	notification.
	"""

	def validate(self):
		self.period = validate_period(self.period)
		self.period_from, self.period_to = period_bounds(self.period)
		if not self.pay_date:
			self.pay_date = expected_pay_date(self.period)

		self.fill_abbr()
		self.check_duplicate_components()
		self.net_pay = flt(next((d.amount for d in self.details if d.abbr == NET_PAY_ABBR), 0))
		self.block_published_edits()

	def fill_abbr(self):
		missing = {d.salary_component for d in self.details if not d.abbr}
		if not missing:
			return
		abbr = dict(
			frappe.get_all(
				"Salary Component",
				filters={"name": ["in", list(missing)]},
				fields=["name", "salary_component_abbr"],
				as_list=True,
			)
		)
		for d in self.details:
			if not d.abbr:
				d.abbr = abbr.get(d.salary_component)

	def check_duplicate_components(self):
		seen = set()
		for d in self.details:
			if d.salary_component in seen:
				frappe.throw(_("Row {0}: Salary Component {1} appears twice").format(d.idx, d.salary_component))
			seen.add(d.salary_component)

	def block_published_edits(self):
		"""An employee may already have read a published payslip. Changing numbers under
		them silently is exactly the dispute this module must avoid - withdraw first."""
		if self.is_new() or self.flags.allow_published_edit:
			return
		before = self.get_doc_before_save()
		if not before or before.status != "Published" or self.status != "Published":
			return

		def snapshot(doc):
			return sorted((d.salary_component, flt(d.amount, 2)) for d in doc.details)

		if snapshot(before) != snapshot(self) or before.employee != self.employee or before.period != self.period:
			frappe.throw(_("This payslip is published. Withdraw it on the Payslip Upload page before changing it."))
