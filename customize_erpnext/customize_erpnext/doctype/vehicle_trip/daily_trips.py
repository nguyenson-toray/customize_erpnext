# -*- coding: utf-8 -*-
# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import now_datetime, today, get_datetime
from datetime import datetime, time


@frappe.whitelist()
def create_daily_trips_pickup():
	"""
	Scheduled task to create daily trips for all vehicles
	Creates pickup per vehicle:
	- 05:30 - Daily pickup (fixed_location_1 -> fixed_location_2) 
	"""
	try:
		# Get all active vehicles
		vehicles = frappe.get_all(
			"Vehicle List",
			filters={
				"fixed_location_1": ["is", "set"],
				"fixed_location_2": ["is", "set"]
			},
			fields=["name", "vehicle_name", "fixed_location_1", "fixed_location_2", "default_driver"]
		)

		if not vehicles:
			frappe.logger().info(_("No vehicles with fixed locations found"))
			return

		today_date = today()
		created_count = 0

		for vehicle in vehicles:
			# Create morning pickup trip at 05:30
			pickup_created = create_trip_if_not_exists(
				vehicle=vehicle,
				trip_type="pickup",
				start_location=vehicle.fixed_location_1,
				destination_location=vehicle.fixed_location_2,
				scheduled_time="05:30:00"
			)
			if pickup_created:
				created_count += 1 

		if created_count > 0:
			frappe.logger().info(_("Created {0} daily pickup").format(created_count))
		else:
			frappe.logger().info(_("No new daily pickup created (pickup already exist for today)"))

	except Exception as e:
		frappe.log_error(_("Error creating daily pickup: {0}").format(str(e)), _("Daily pickup Creation Error"))

@frappe.whitelist()
def create_daily_trips_dropoff():
	"""
	Scheduled task to create daily trips for all vehicles
	Creates dropoff per vehicle: 
	- 17:00 - Daily dropoff (fixed_location_2 -> fixed_location_1)
	"""
	try:
		# Get all active vehicles
		vehicles = frappe.get_all(
			"Vehicle List",
			filters={
				"fixed_location_1": ["is", "set"],
				"fixed_location_2": ["is", "set"]
			},
			fields=["name", "vehicle_name", "fixed_location_1", "fixed_location_2", "default_driver"]
		)

		if not vehicles:
			frappe.logger().info(_("No vehicles with fixed locations found"))
			return

		today_date = today()
		created_count = 0

		for vehicle in vehicles:
			# Create evening dropoff trip at 17:00
			dropoff_created = create_trip_if_not_exists(
				vehicle=vehicle,
				trip_type="dropoff",
				start_location=vehicle.fixed_location_2,
				destination_location=vehicle.fixed_location_1,
				scheduled_time="17:00:00"
			)
			if dropoff_created:
				created_count += 1

		if created_count > 0:
			frappe.logger().info(_("Created {0} daily dropoff").format(created_count))
		else:
			frappe.logger().info(_("No new daily dropoff created (dropoff already exist for today)"))

	except Exception as e:
		frappe.log_error(_("Error creating daily dropoff: {0}").format(str(e)), _("Daily dropoff Creation Error"))


def create_trip_if_not_exists(vehicle, trip_type, start_location, destination_location, scheduled_time):
	"""
	Create a trip if it doesn't already exist for today

	Args:
		vehicle: Vehicle document
		trip_type: 'pickup' or 'dropoff'
		start_location: Starting location
		destination_location: Destination location
		scheduled_time: Scheduled time for the trip (HH:MM:SS format)

	Returns:
		bool: True if trip was created, False if it already exists
	"""
	# Check if trip already exists for this vehicle, date and type
	today_date = today()
	existing_trip = frappe.db.exists(
		"Vehicle Trip",
		{
			"vehicle_name": vehicle.name,
			"request_date": today_date,
			"daily_pickup" if trip_type == "pickup" else "daily_dropoff": 1
		}
	)

	if existing_trip:
		return False

	# Create new trip with scheduled time
	try:
		trip = frappe.get_doc({
			"doctype": "Vehicle Trip",
			"vehicle_name": vehicle.name,
			"request_date": today_date,
			"request_time": scheduled_time,
			"start_location": start_location,
			"destination_location": destination_location,
			"purpose": _("Đón CNV hàng ngày") if trip_type == "pickup" else _("Trả CNV hàng ngày"),
			"daily_pickup": 1 if trip_type == "pickup" else 0,
			"daily_dropoff": 1 if trip_type == "dropoff" else 0
		})

		trip.insert(ignore_permissions=True)

		# Assign default driver to the trip if available
		vehicle_doc = frappe.get_doc("Vehicle List", vehicle.name)
		if vehicle_doc.default_driver:
			try:
				from frappe.desk.form.assign_to import add as add_assignment
				add_assignment({
					"doctype": "Vehicle Trip",
					"name": trip.name,
					"assign_to": [vehicle_doc.default_driver],
					"description": _("Auto-assigned from vehicle's default driver")
				})
				frappe.logger().info(
					_("Assigned trip {0} to default driver {1}").format(trip.name, vehicle_doc.default_driver)
				)
			except Exception as assign_error:
				frappe.log_error(
					_("Error assigning driver to trip {0}: {1}").format(trip.name, str(assign_error)),
					_("Driver Assignment Error")
				)

		frappe.db.commit()

		frappe.logger().info(
			_("Created daily {0} trip for vehicle {1} at {2}").format(trip_type, vehicle.name, scheduled_time)
		)
		return True

	except Exception as e:
		frappe.log_error(
			_("Error creating {0} trip for {1}: {2}").format(trip_type, vehicle.name, str(e)),
			_("Daily Trip Creation Error")
		)
		return False


# =============================================================================
# MANUAL TRIP CREATION FUNCTIONS (for Console Usage)
# =============================================================================

@frappe.whitelist()
def manual_create_daily_trips():
	"""
	Manual function to create daily trips for all vehicles (for today)

	Usage in bench console:
		bench --site [site-name] console
		>>> from customize_erpnext.customize_erpnext.doctype.vehicle_trip.daily_trips import manual_create_daily_trips
		>>> manual_create_daily_trips()

	Usage in web console:
		frappe.call('customize_erpnext.customize_erpnext.doctype.vehicle_trip.daily_trips.create_daily_trips_pickup')
		frappe.call('customize_erpnext.customize_erpnext.doctype.vehicle_trip.daily_trips.create_daily_trips_dropoff')
	"""
	print("="*60)
	print(_("CREATING DAILY TRIPS FOR ALL VEHICLES"))
	print("="*60)

	create_daily_trips_pickup()
	create_daily_trips_dropoff()

	print("\n" + _("Done! Check the logs above for details."))
	return _("Daily trips creation completed")


@frappe.whitelist()
def manual_create_trips_for_date(date_str):
	"""
	Create daily trips for all vehicles for a specific date

	Args:
		date_str: Date in YYYY-MM-DD format (e.g., "2025-11-14")

	Usage in bench console:
		>>> from customize_erpnext.customize_erpnext.doctype.vehicle_trip.daily_trips import manual_create_trips_for_date
		>>> manual_create_trips_for_date("2025-11-14")

	Usage in web console:
		frappe.call('customize_erpnext.customize_erpnext.doctype.vehicle_trip.daily_trips.manual_create_trips_for_date', {'date_str': '2025-11-14'})
	"""
	print("="*60)
	print(_("CREATING DAILY TRIPS FOR DATE: {0}").format(date_str))
	print("="*60)

	try:
		# Get all active vehicles
		vehicles = frappe.get_all(
			"Vehicle List",
			filters={
				"fixed_location_1": ["is", "set"],
				"fixed_location_2": ["is", "set"]
			},
			fields=["name", "vehicle_name", "fixed_location_1", "fixed_location_2", "default_driver"]
		)

		if not vehicles:
			print(_("No vehicles with fixed locations found"))
			return _("No vehicles found")

		created_count = 0

		for vehicle in vehicles:
			# Create morning pickup trip at 05:30
			pickup_created = create_trip_for_date(
				vehicle=vehicle,
				trip_type="pickup",
				start_location=vehicle.fixed_location_1,
				destination_location=vehicle.fixed_location_2,
				scheduled_time="05:30:00",
				date_str=date_str
			)
			if pickup_created:
				created_count += 1
				print("✓ " + _("Created pickup trip for {0}").format(vehicle.vehicle_name or vehicle.name))

			# Create evening dropoff trip at 17:00
			dropoff_created = create_trip_for_date(
				vehicle=vehicle,
				trip_type="dropoff",
				start_location=vehicle.fixed_location_2,
				destination_location=vehicle.fixed_location_1,
				scheduled_time="17:00:00",
				date_str=date_str
			)
			if dropoff_created:
				created_count += 1
				print("✓ " + _("Created dropoff trip for {0}").format(vehicle.vehicle_name or vehicle.name))

		print(f"\n{'='*60}")
		print(_("SUMMARY: Created {0} trips for {1} vehicles").format(created_count, len(vehicles)))
		print(f"{'='*60}")

		return _("Created {0} trips").format(created_count)

	except Exception as e:
		error_msg = _("Error creating trips for date {0}: {1}").format(date_str, str(e))
		print("\n✗ " + error_msg)
		frappe.log_error(error_msg, _("Manual Trips Creation Error"))
		return error_msg


@frappe.whitelist()
def manual_create_trips_for_vehicle(vehicle_name, date_str=None):
	"""
	Create daily trips for a specific vehicle

	Args:
		vehicle_name: Name of the vehicle (e.g., "VEH-001")
		date_str: Optional date in YYYY-MM-DD format. If not provided, uses today

	Usage in bench console:
		>>> from customize_erpnext.customize_erpnext.doctype.vehicle_trip.daily_trips import manual_create_trips_for_vehicle
		>>> manual_create_trips_for_vehicle("VEH-001")
		>>> manual_create_trips_for_vehicle("VEH-001", "2025-11-14")

	Usage in web console:
		frappe.call('customize_erpnext.customize_erpnext.doctype.vehicle_trip.daily_trips.manual_create_trips_for_vehicle', {'vehicle_name': 'VEH-001'})
	"""
	if not date_str:
		date_str = today()

	print("="*60)
	print(_("CREATING TRIPS FOR VEHICLE: {0}").format(vehicle_name))
	print(_("DATE: {0}").format(date_str))
	print("="*60)

	try:
		# Get vehicle details
		vehicle = frappe.get_doc("Vehicle List", vehicle_name)

		if not vehicle.fixed_location_1 or not vehicle.fixed_location_2:
			msg = "✗ " + _("Vehicle {0} does not have fixed locations configured").format(vehicle_name)
			print(msg)
			return msg

		created_count = 0

		# Create morning pickup trip at 05:30
		pickup_created = create_trip_for_date(
			vehicle=vehicle,
			trip_type="pickup",
			start_location=vehicle.fixed_location_1,
			destination_location=vehicle.fixed_location_2,
			scheduled_time="05:30:00",
			date_str=date_str
		)
		if pickup_created:
			created_count += 1
			print("✓ " + _("Created pickup trip (05:30) - {0} → {1}").format(vehicle.fixed_location_1, vehicle.fixed_location_2))
		else:
			print("  " + _("Pickup trip already exists"))

		# Create evening dropoff trip at 17:00
		dropoff_created = create_trip_for_date(
			vehicle=vehicle,
			trip_type="dropoff",
			start_location=vehicle.fixed_location_2,
			destination_location=vehicle.fixed_location_1,
			scheduled_time="17:00:00",
			date_str=date_str
		)
		if dropoff_created:
			created_count += 1
			print("✓ " + _("Created dropoff trip (17:00) - {0} → {1}").format(vehicle.fixed_location_2, vehicle.fixed_location_1))
		else:
			print("  " + _("Dropoff trip already exists"))

		print(f"\n{'='*60}")
		print(_("SUMMARY: Created {0} trips for {1}").format(created_count, vehicle_name))
		print(f"{'='*60}")

		return _("Created {0} trips").format(created_count)

	except Exception as e:
		error_msg = _("Error creating trips for vehicle {0}: {1}").format(vehicle_name, str(e))
		print("\n✗ " + error_msg)
		frappe.log_error(error_msg, _("Manual Trips Creation Error"))
		return error_msg


def create_trip_for_date(vehicle, trip_type, start_location, destination_location, scheduled_time, date_str):
	"""
	Helper function to create a trip for a specific date

	Args:
		vehicle: Vehicle document
		trip_type: 'pickup' or 'dropoff'
		start_location: Starting location
		destination_location: Destination location
		scheduled_time: Scheduled time for the trip (HH:MM:SS format)
		date_str: Date in YYYY-MM-DD format

	Returns:
		bool: True if trip was created, False if it already exists
	"""
	# Check if trip already exists for this vehicle, date and type
	existing_trip = frappe.db.exists(
		"Vehicle Trip",
		{
			"vehicle_name": vehicle.name,
			"request_date": date_str,
			"daily_pickup" if trip_type == "pickup" else "daily_dropoff": 1
		}
	)

	if existing_trip:
		return False

	# Create new trip with scheduled time
	try:
		trip = frappe.get_doc({
			"doctype": "Vehicle Trip",
			"vehicle_name": vehicle.name,
			"request_date": date_str,
			"request_time": scheduled_time,
			"start_location": start_location,
			"destination_location": destination_location,
			"purpose": _("Daily employee pickup and dropoff"),
			"daily_pickup": 1 if trip_type == "pickup" else 0,
			"daily_dropoff": 1 if trip_type == "dropoff" else 0
		})

		trip.insert(ignore_permissions=True)

		# Assign default driver to the trip if available
		if hasattr(vehicle, 'default_driver') and vehicle.default_driver:
			try:
				from frappe.desk.form.assign_to import add as add_assignment
				add_assignment({
					"doctype": "Vehicle Trip",
					"name": trip.name,
					"assign_to": [vehicle.default_driver],
					"description": _("Auto-assigned from vehicle's default driver")
				})
				frappe.logger().info(
					_("Assigned trip {0} to default driver {1}").format(trip.name, vehicle.default_driver)
				)
			except Exception as assign_error:
				frappe.log_error(
					_("Error assigning driver to trip {0}: {1}").format(trip.name, str(assign_error)),
					_("Driver Assignment Error")
				)

		frappe.db.commit()

		frappe.logger().info(
			_("Created daily {0} trip for vehicle {1} at {2} for date {3}").format(
				trip_type, vehicle.name, scheduled_time, date_str
			)
		)
		return True

	except Exception as e:
		frappe.log_error(
			_("Error creating {0} trip for {1} on {2}: {3}").format(
				trip_type, vehicle.name, date_str, str(e)
			),
			_("Daily Trip Creation Error")
		)
		return False
