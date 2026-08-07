"""
Keep a durable index on Employee Checkin.attendance.

The attendance recalculation unlinks checkins with
``UPDATE `tabEmployee Checkin` SET attendance = NULL WHERE attendance = %s``.
Without an index that is a full scan of the whole checkin table (~860k rows,
measured at ~2s per statement), which is what pushed Bulk Update Attendance past
the 120s gunicorn request timeout and got the worker killed mid-write.

add_attendance_performance_indexes already created this index as
``idx_checkin_attendance_fk`` with a raw CREATE INDEX — but the field is
``search_index = 0`` in the DocType, and frappe's schema sync drops any
single-column index on a column whose field says it should not have one
(frappe/database/schema.py: "index should be applied or dropped irrespective of
type change"). So every ``bench migrate`` silently removed it again.

Setting ``search_index = 1`` through a Property Setter hands ownership of the
index to frappe, which then keeps it across migrations. frappe.db.add_index()
does both, but it skips the Property Setter while ``in_migrate`` is set — and
patches run during migrate — so the Property Setter is written explicitly here.
"""

import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
	# 1) Tell frappe the column is indexed, so schema sync stops dropping it
	make_property_setter(
		"Employee Checkin",
		"attendance",
		"search_index",
		"1",
		"Check",
		for_doctype=False,
		validate_fields_for_doctype=False,
	)
	frappe.clear_cache(doctype="Employee Checkin")

	# 2) Create the index itself if it is not already there. Uses frappe's
	#    naming convention (attendance_index) so schema sync recognises it.
	table = "tabEmployee Checkin"
	index_name = frappe.db.get_index_name(["attendance"])

	if frappe.db.has_index(table, index_name):
		print(f"   ⏭  Index already exists: {index_name} on {table}")
	else:
		frappe.db.commit()
		frappe.db.sql(f"ALTER TABLE `{table}` ADD INDEX IF NOT EXISTS `{index_name}` (`attendance`)")
		print(f"   ✅ Created index: {index_name} on {table} (checkin unlink during recalc)")

	# 3) Drop the older hand-rolled index — same column, so it would only be
	#    duplicate write cost. Safe to skip if a previous migrate already ate it.
	if frappe.db.has_index(table, "idx_checkin_attendance_fk"):
		frappe.db.sql(f"ALTER TABLE `{table}` DROP INDEX `idx_checkin_attendance_fk`")
		print(f"   🧹 Dropped superseded index: idx_checkin_attendance_fk on {table}")

	frappe.db.commit()
