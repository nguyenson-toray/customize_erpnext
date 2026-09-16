# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""post_model_sync: finish the Fixed Trip Schedule rename.

Runs after the model sync, which has already created the `schedule_name` column
from the new JSON. What is left is to move the data over from `template_name`
and drop that orphan column - removing a field from a DocType JSON never drops
its column.

Also renumbers the docnames TIQN-FTT-00x -> TIQN-FST-00x and back-fills the two
new fields. `TIQN Vehicle Trip.template_id` is a Data field holding the schedule
docname, so any existing trip is repointed by hand here.

Idempotent.
"""

import frappe
from frappe.model.rename_doc import rename_doc

DOCTYPE = "TIQN Fixed Trip Schedule"
SERIES_PREFIX = "TIQN-FST-"
DEFAULT_DAYS = "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday"


def execute():
	if not frappe.db.exists("DocType", DOCTYPE):
		return

	_move_template_name_across()

	for row in frappe.get_all(DOCTYPE, fields=["name", "schedule_name"], order_by="name asc"):
		_backfill(row)
		_renumber(row)

	_advance_series()


def _advance_series():
	"""Push `tabSeries` past the highest TIQN-FST-xxx we just created.

	Renaming a document does NOT move the naming-series counter. The new prefix
	starts at 0, so the very next schedule anyone creates would be named
	TIQN-FST-001 again and die on a duplicate primary key. Note this only ever
	raises the counter - never delete or lower a `tabSeries` row, that is what
	stopped HR from saving new Leave Applications in August 2026.
	"""
	highest = 0
	for name in frappe.get_all(DOCTYPE, pluck="name"):
		suffix = name.rsplit("-", 1)[-1]
		if suffix.isdigit():
			highest = max(highest, int(suffix))

	if not highest:
		return

	frappe.db.sql(
		"""INSERT INTO `tabSeries` (name, current) VALUES (%s, %s)
			ON DUPLICATE KEY UPDATE current = GREATEST(current, VALUES(current))""",
		(SERIES_PREFIX, highest),
	)


def _move_template_name_across():
	"""Copy template_name -> schedule_name, then drop the orphan column.

	Deliberately NOT frappe.model.utils.rename_field: the model sync has already
	created `schedule_name` from the new JSON, so there is no column to rename -
	only data to move. Dropping the old column by hand matters too, because
	removing a field from the JSON never drops its column; it would sit there
	forever holding a stale copy of every schedule name.
	"""
	if not frappe.db.has_column(DOCTYPE, "template_name"):
		return

	frappe.db.sql(
		f"""UPDATE `tab{DOCTYPE}`
			SET schedule_name = template_name
			WHERE (schedule_name IS NULL OR schedule_name = '')
			  AND template_name IS NOT NULL AND template_name != ''"""
	)
	frappe.db.sql_ddl(f"ALTER TABLE `tab{DOCTYPE}` DROP COLUMN `template_name`")


def _backfill(row):
	values = {}
	if not frappe.db.get_value(DOCTYPE, row.name, "days_of_week"):
		values["days_of_week"] = DEFAULT_DAYS
	if not frappe.db.get_value(DOCTYPE, row.name, "trip_name_template"):
		values["trip_name_template"] = row.schedule_name
	if values:
		frappe.db.set_value(DOCTYPE, row.name, values, update_modified=False)


def _renumber(row):
	"""TIQN-FTT-001 -> TIQN-FST-001, keeping the number."""
	if not row.name.startswith("TIQN-FTT-"):
		return

	new_name = row.name.replace("TIQN-FTT-", "TIQN-FST-", 1)
	if frappe.db.exists(DOCTYPE, new_name):
		return

	rename_doc(DOCTYPE, row.name, new_name, force=True, ignore_permissions=True)

	# template_id is Data, not a Link, so nothing repoints it automatically.
	frappe.db.sql(
		"UPDATE `tabTIQN Vehicle Trip` SET template_id = %s WHERE template_id = %s",
		(new_name, row.name),
	)
