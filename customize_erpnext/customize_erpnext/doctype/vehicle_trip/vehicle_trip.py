# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


@frappe.whitelist()
def get_max_km_for_vehicle(vehicle_name):
	"""
	Get the maximum km recorded for a specific vehicle

	Args:
		vehicle_name: Name of the vehicle

	Returns:
		dict: {
			"max_km": int or None,
			"last_trip": str or None (name of the last trip)
		}
	"""
	if not vehicle_name:
		return {"max_km": None, "last_trip": None}

	# Get max from start_km
	max_start_km = frappe.db.get_value(
		"Vehicle Trip",
		filters={"vehicle_name": vehicle_name},
		fieldname="start_km",
		order_by="start_km desc"
	) or 0

	# Get max from finish_km
	max_finish_km_data = frappe.db.get_value(
		"Vehicle Trip",
		filters={"vehicle_name": vehicle_name, "finish_km": ["is", "set"]},
		fieldname=["finish_km", "name"],
		order_by="finish_km desc",
		as_dict=True
	)

	max_finish_km = max_finish_km_data.get("finish_km") if max_finish_km_data else 0
	last_trip = max_finish_km_data.get("name") if max_finish_km_data else None

	# Return the maximum of both
	max_km = max(max_start_km or 0, max_finish_km or 0)

	return {
		"max_km": max_km if max_km > 0 else None,
		"last_trip": last_trip
	}


class VehicleTrip(Document):
	def autoname(self):
		"""
		Custom naming: {vehicle_name}-{YY}{MM}{DD}{HH}{mm}
		Example: Bus 1-2511141530
		"""
		from frappe.utils import now_datetime

		# Get current datetime
		now = now_datetime()

		# Format: vehicle_name-YYMMDDHHmm
		self.name = "{vehicle}-{year}{month:02d}{day:02d}{hour:02d}{minute:02d}".format(
			vehicle=self.vehicle_name,
			year=now.strftime("%y"),
			month=now.month,
			day=now.day,
			hour=now.hour,
			minute=now.minute
		)

	def validate(self):
		# Auto-populate vehicle info from Vehicle List
		if self.vehicle_name:
			vehicle = frappe.get_doc("Vehicle List", self.vehicle_name)
			vehicle_info = "{0} - {1} - {2} {3}".format(
				vehicle.model or '',
				vehicle.driver or '',
				vehicle.number_of_seats or '',
				_("seats")
			)
			self.vehicle_info = vehicle_info.strip(" - ")

		# Auto-set status based on trip state
		if self.finish_time:
			self.status = "Hoàn Thành"
		elif self.start_time:
			self.status = "Đang Chạy"
		else:
			self.status = "Đang Đỗ"

		# Validate start_km against initial_odometer for first trip
		if self.start_km is not None and self.vehicle_name:
			self.validate_first_trip_odometer()

		# Validate finish_km must be greater than start_km
		# Only validate when trip is finished (has finish_time)
		if self.finish_time and self.start_km is not None and self.finish_km is not None:
			if self.finish_km <= self.start_km:
				frappe.throw(
					_("Finish km ({0}) must be greater than start km ({1})").format(
						self.finish_km, self.start_km
					),
					title=_("Invalid km error")
				)

		# Calculate total_km if both start_km and finish_km are provided
		if self.finish_km and self.start_km:
			self.total_km = self.finish_km - self.start_km

	def validate_first_trip_odometer(self):
		"""
		Validate that first trip start_km must be >= vehicle's initial_odometer
		"""
		# Get vehicle document
		vehicle = frappe.get_doc("Vehicle List", self.vehicle_name)

		# Check if vehicle has initial_odometer set
		if not vehicle.initial_odometer:
			return  # No validation needed if initial_odometer is not set

		# Check if this is the first trip for this vehicle
		# (no previous trips with finish_km)
		existing_trips = frappe.db.count(
			"Vehicle Trip",
			filters={
				"vehicle_name": self.vehicle_name,
				"finish_km": ["is", "set"],
				"name": ["!=", self.name] if not self.is_new() else ""
			}
		)

		# If this is the first trip (no previous finished trips)
		if existing_trips == 0:
			if self.start_km < vehicle.initial_odometer:
				frappe.throw(
					_("This is the first trip for vehicle {0}. Start km ({1}) must be greater than or equal to the vehicle's initial odometer ({2}).").format(
						self.vehicle_name,
						self.start_km,
						vehicle.initial_odometer
					),
					title=_("Invalid Start Km")
				)

	def after_insert(self):
		"""
		Auto-assign the default driver from Vehicle List to this Vehicle Trip
		"""
		if self.vehicle_name:
			vehicle = frappe.get_doc("Vehicle List", self.vehicle_name)
			if vehicle.default_driver:
				# Use frappe's assign_to API to assign the default driver
				from frappe.desk.form.assign_to import add
				try:
					add({
						"assign_to": [vehicle.default_driver],
						"doctype": self.doctype,
						"name": self.name,
						"description": _("Auto-assigned as default driver for {0}").format(self.vehicle_name)
					})
				except Exception as e:
					# Log the error but don't fail the document creation
					frappe.log_error(
						message=str(e),
						title=_("Failed to auto-assign driver to Vehicle Trip {0}").format(self.name)
					)
