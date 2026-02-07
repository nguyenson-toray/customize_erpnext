# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import getdate, add_days, today, date_diff
from frappe.model.document import Document
from datetime import date
from dateutil.relativedelta import relativedelta
import json


class EmployeeMaternity(Document):
	@property
	def seniority(self):
		"""Seniority in months from date_of_joining to today"""
		if self.type != "Pregnant" or not self.date_of_joining:
			return 0
		doj = getdate(self.date_of_joining)
		today_date = date.today()
		rd = relativedelta(today_date, doj)
		return rd.years * 12 + rd.months

	@property
	def gestational_age(self):
		"""Gestational age in months. Formula: 9.5 - (DATEDIF(TODAY, estimated_due_date, "m") + 1)
		DATEDIF with "m" counts complete months between two dates."""
		if self.type != "Pregnant" or not self.estimated_due_date:
			return 0
		today_date = date.today()
		edd = getdate(self.estimated_due_date)
		if edd <= today_date:
			return 9.5
		# DATEDIF(TODAY(), due_date, "m") = complete months from today to due date
		rd = relativedelta(edd, today_date)
		months_diff = rd.years * 12 + rd.months
		return round(9.5 - (months_diff + 1), 1)

	def validate(self):
		self.validate_dates()
		self.validate_maternity_leave_readonly()
		self.validate_date_overlap()

	def validate_dates(self):
		"""Validate from_date < to_date"""
		if self.from_date and self.to_date:
			if getdate(self.from_date) >= getdate(self.to_date):
				frappe.throw(_("From Date must be earlier than To Date"))

	def validate_maternity_leave_readonly(self):
		"""Prevent manual creation/modification of Maternity Leave type records"""
		if self.type == "Maternity Leave" and not self.flags.from_leave_application:
			if self.is_new():
				frappe.throw(
					_("Maternity Leave records are automatically created from Leave Application. "
					  "Please submit a Leave Application instead.")
				)
			else:
				# Check if key fields changed (only allow if triggered from LA sync)
				old_doc = self.get_doc_before_save()
				if old_doc and old_doc.type == "Maternity Leave":
					for field in ['employee', 'from_date', 'to_date', 'type']:
						if str(getattr(old_doc, field, '')) != str(getattr(self, field, '')):
							frappe.throw(
								_("Maternity Leave records cannot be manually modified. "
								  "Please update the linked Leave Application instead.")
							)

	def validate_date_overlap(self):
		"""Validate no date overlap between records of the same employee"""
		if not self.employee or not self.from_date or not self.to_date:
			return

		filters = {
			"employee": self.employee,
			"from_date": ["<=", self.to_date],
			"to_date": [">=", self.from_date],
		}
		if not self.is_new():
			filters["name"] = ["!=", self.name]

		overlapping = frappe.get_all("Employee Maternity", filters=filters, fields=["name", "type", "from_date", "to_date"])

		if overlapping:
			rec = overlapping[0]
			frappe.throw(
				_("Date period overlaps with {0} ({1}: {2} - {3})").format(
					rec.name, rec.type, rec.from_date, rec.to_date
				)
			)

	def before_save(self):
		"""Collect affected dates before save for attendance recalculation"""
		self._collect_affected_dates()

	def _collect_affected_dates(self):
		"""Compare old vs new to find affected dates"""
		affected_dates = set()

		if not self.is_new():
			old_doc = self.get_doc_before_save()
			if old_doc:
				# Collect old date range
				if old_doc.from_date and old_doc.to_date:
					self._add_date_range(affected_dates, old_doc.from_date, old_doc.to_date, self.employee)

				# Check if anything relevant changed
				changed = False
				for field in ['from_date', 'to_date', 'type', 'apply_benefit']:
					if str(getattr(old_doc, field, '')) != str(getattr(self, field, '')):
						changed = True
						break

				if not changed:
					return

		# Collect new date range
		if self.from_date and self.to_date:
			self._add_date_range(affected_dates, self.from_date, self.to_date, self.employee)

		if affected_dates:
			self._maternity_affected_dates = list(affected_dates)
			self._maternity_employee = self.employee

	def _add_date_range(self, date_set, from_date, to_date, employee):
		"""Add date range to set, limited to today and relieving date"""
		current_date = getdate(from_date)
		end_date = getdate(to_date)

		today_date = getdate(today())
		if end_date > today_date:
			end_date = today_date

		# Limit to relieving date
		relieving_date = frappe.db.get_value("Employee", employee, "relieving_date")
		if relieving_date:
			last_working_day = add_days(getdate(relieving_date), -1)
			if end_date > last_working_day:
				end_date = last_working_day

		while current_date <= end_date:
			date_set.add(str(current_date))
			current_date = add_days(current_date, 1)


def validate_maternity(doc, method):
	"""Hook: validate Employee Maternity"""
	doc.validate()


def on_maternity_update(doc, method):
	"""Hook: on_update - queue attendance recalculation"""
	_queue_attendance_recalculation(doc, "on_update")


def on_maternity_insert(doc, method):
	"""Hook: after_insert - queue attendance recalculation"""
	# For new records, collect dates since before_save may not have run for hooks
	if not hasattr(doc, '_maternity_affected_dates'):
		affected_dates = set()
		if doc.from_date and doc.to_date:
			doc._add_date_range(affected_dates, doc.from_date, doc.to_date, doc.employee)
		if affected_dates:
			doc._maternity_affected_dates = list(affected_dates)
			doc._maternity_employee = doc.employee

	_queue_attendance_recalculation(doc, "after_insert")


def on_maternity_delete(doc, method):
	"""Hook: on_trash - queue attendance recalculation for deleted dates"""
	affected_dates = set()
	if doc.from_date and doc.to_date:
		doc._add_date_range(affected_dates, doc.from_date, doc.to_date, doc.employee)

	if affected_dates:
		doc._maternity_affected_dates = list(affected_dates)
		doc._maternity_employee = doc.employee
		_queue_attendance_recalculation(doc, "on_trash")


def _queue_attendance_recalculation(doc, trigger):
	"""Queue background job to recalculate attendance for affected dates"""
	try:
		if not hasattr(doc, '_maternity_affected_dates') or not doc._maternity_affected_dates:
			return

		affected_dates = doc._maternity_affected_dates
		employee = getattr(doc, '_maternity_employee', doc.employee)

		affected_dates_sorted = sorted([getdate(d) for d in affected_dates])
		from_date = str(affected_dates_sorted[0])
		to_date = str(affected_dates_sorted[-1])
		total_days = len(affected_dates)

		job_id = f"maternity_attendance_{employee}_{int(frappe.utils.now_datetime().timestamp())}"

		frappe.enqueue(
			'customize_erpnext.customize_erpnext.doctype.employee_maternity.employee_maternity.background_update_attendance_for_maternity',
			queue='long',
			timeout=1800,
			job_id=job_id,
			employee=employee,
			from_date=from_date,
			to_date=to_date,
			total_days=total_days
		)

		frappe.msgprint(
			msg=_('Maternity period changed. Updating attendance for {0} days ({1} to {2})...').format(
				total_days, from_date, to_date
			),
			title=_('Attendance Update'),
			indicator='blue'
		)

		frappe.logger().info(
			f"Employee Maternity {trigger} for {employee}. "
			f"Queued attendance update for {total_days} days ({from_date} to {to_date}). Job: {job_id}"
		)

	except Exception as e:
		frappe.log_error(
			f"Error in _queue_attendance_recalculation for {doc.name}: {str(e)}",
			"Employee Maternity Attendance Update Error"
		)


def background_update_attendance_for_maternity(employee, from_date, to_date, total_days):
	"""Background job for updating attendance when maternity tracking changes"""
	import time
	start_time = time.time()

	try:
		frappe.logger().info(
			f"Background attendance update started for employee {employee} "
			f"from {from_date} to {to_date} ({total_days} days)"
		)

		from customize_erpnext.overrides.shift_type.shift_type_optimized import bulk_update_attendance_optimized

		result = bulk_update_attendance_optimized(
			from_date=from_date,
			to_date=to_date,
			employees=json.dumps([employee]),
			force_sync=1
		)

		end_time = time.time()
		processing_time = round(end_time - start_time, 2)

		if result and result.get('status') == 'success':
			stats = result.get('stats', {})
			frappe.logger().info(
				f"Background attendance update completed for {employee}. "
				f"Created: {stats.get('new_attendance', 0)}, "
				f"Updated: {stats.get('updated_attendance', 0)} in {processing_time}s"
			)
		else:
			error_message = result.get('message', 'Unknown error') if result else 'No response'
			frappe.logger().error(
				f"Background attendance update failed for {employee}: {error_message}"
			)

		return result

	except Exception as e:
		frappe.log_error(
			f"Background attendance update failed for {employee}: {str(e)}",
			"Maternity Attendance Update Background Job Error"
		)
		raise e
