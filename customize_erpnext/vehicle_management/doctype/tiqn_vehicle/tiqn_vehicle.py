# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

# Statuses a human is allowed to set. "in_trip" is owned by the trip check in /
# check out flow — see TIQNVehicleTrip.sync_vehicle_status().
MANUAL_STATUSES = ("available", "not_available")

# Every legal value of TIQN Vehicle.status, in the order the Select field lists them.
VEHICLE_STATUSES = ("available", "in_trip", "not_available")


class TIQNVehicle(Document):
	def validate(self):
		self.license_plate = (self.license_plate or "").strip().upper()
		if self.capacity and self.capacity < 0:
			frappe.throw(_("Capacity cannot be negative"))
