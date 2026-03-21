"""
Migrate Employee Onboarding Settings from multi-record to Single doctype.

Picks the most recently modified record, re-parents its child rows to
'Employee Onboarding Settings' (the fixed parent name for Single doctypes),
then removes all old records from the main table.
"""

import frappe


def execute():
	# Find the most recently modified settings record
	rows = frappe.db.sql(
		"SELECT `name` FROM `tabEmployee Onboarding Settings`"
		" ORDER BY `modified` DESC LIMIT 1",
		as_dict=True,
	)
	if not rows:
		return  # nothing to migrate

	old_name = rows[0].name

	if old_name == "Employee Onboarding Settings":
		return  # already migrated

	# Re-parent child rows to the Single parent name
	frappe.db.sql(
		"""UPDATE `tabEmployee Onboarding Employee`
		   SET `parent` = 'Employee Onboarding Settings'
		   WHERE `parenttype` = 'Employee Onboarding Settings'
		     AND `parent` = %s""",
		old_name,
	)

	# Remove child rows belonging to other (older) records
	frappe.db.sql(
		"""DELETE FROM `tabEmployee Onboarding Employee`
		   WHERE `parenttype` = 'Employee Onboarding Settings'
		     AND `parent` != 'Employee Onboarding Settings'""",
	)

	# Drop all records from the main table (Single stores data in tabSingles)
	frappe.db.sql("DELETE FROM `tabEmployee Onboarding Settings`")

	frappe.db.commit()
