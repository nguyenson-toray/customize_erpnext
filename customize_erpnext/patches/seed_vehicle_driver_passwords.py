# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""post_model_sync: set the Phase 1 Mini App password for the three drivers.

Passwords come from vehicle_management/API_CONTRACT.md mục 7 and are deliberately
trivial - they are a temporary stand-in until Phase 2 switches to Zalo User IDs.
Three things follow from that, and all three are intentional:

  * The patch only ever sets a password on a driver that has NONE. It never
    overwrites one, so an admin who picks a better password keeps it across
    every future `bench migrate`.
  * A DocType `Password` field is encrypted, not hashed. Anyone with the DB and
    the site's encryption key can read these back. Do not reuse a password here
    that is used anywhere else.
  * `verify_driver_login` locks a driver out for 15 minutes after 5 wrong
    tries, because "driver01" would otherwise fall to a script instantly.

Mapping follows the fleet order seeded by `seed_vehicle_management_data`:
Bus 1 -> driver01, Bus 2 -> driver02, Kia -> driver03.
"""

import frappe

# license plate of the assigned vehicle -> Phase 1 password
PASSWORD_BY_PLATE = {
	"43B-043.95": "driver01",
	"76F-000.52": "driver02",
	"76H-058.34": "driver03",
}


def execute():
	if not frappe.db.has_column("TIQN Driver", "password"):
		# Schema sync has not reached this column yet; nothing to do this run.
		return

	for plate, password in PASSWORD_BY_PLATE.items():
		vehicle = frappe.db.get_value("TIQN Vehicle", {"license_plate": plate}, "name")
		if not vehicle:
			continue

		driver_name = frappe.db.get_value(
			"TIQN Driver", {"assigned_vehicle": vehicle}, "name", order_by="creation asc"
		)
		if not driver_name:
			continue

		driver = frappe.get_doc("TIQN Driver", driver_name)
		if driver.get_password("password", raise_exception=False):
			continue  # an admin already set one - leave it alone

		driver.password = password
		driver.save(ignore_permissions=True)
