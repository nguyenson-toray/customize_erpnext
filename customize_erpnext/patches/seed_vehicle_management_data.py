# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""post_model_sync: seed vehicles and fixed trip templates.

Numbers below are the real fleet, copied from the legacy `Vehicle List` records
(plates and odometers were verified against the live site). Driver phone numbers
and Zalo User IDs are NOT seeded - nobody has given us those yet, and a fake
phone number in a dispatch system is worse than an empty one. An admin fills
them in, plus the `TIQN Zalo Role Map` rows, before the Mini App goes live.

Depart times 06:30 / 17:15 come from vehicle_management/README.md. The legacy
scheduler used 05:30 / 17:00 - if the spec times are wrong, fix the six
`TIQN Fixed Trip Schedule` records, not this patch.

Idempotent, and stable under admin edits: records are keyed on the vehicle
(license plate / assigned vehicle / shift number), never on the editable
display names, so renaming a driver or a template does not produce duplicates
if this patch is ever re-run.
"""

import frappe

VEHICLES = [
	{
		"vehicle_name": "Bus 1",
		"license_plate": "43B-043.95",
		"vehicle_type": "Bus",
		"capacity": 16,
		"notes": "Ford Transit. Migrated from legacy Vehicle List 'Bus 1'.",
		"_from": "Vincom",
		"_to": "Công ty Toray",
	},
	{
		"vehicle_name": "Bus 2",
		"license_plate": "76F-000.52",
		"vehicle_type": "Bus",
		"capacity": 16,
		"notes": "Ford Transit. Migrated from legacy Vehicle List 'Bus 2'.",
		"_from": "Dốc Sỏi",
		"_to": "Công ty Toray",
	},
	{
		"vehicle_name": "Kia",
		"license_plate": "76H-058.34",
		"vehicle_type": "MPV",
		"capacity": 7,
		"notes": "Kia Carnival. Migrated from legacy Vehicle List 'Kia'.",
		"_from": "Vincom",
		"_to": "Công ty Toray",
	},
]

MORNING_DEPART = "06:30:00"
AFTERNOON_DEPART = "17:15:00"


def execute():
	for spec in VEHICLES:
		vehicle = _ensure_vehicle(spec)
		_ensure_schedule(
			f"{spec['_from']} - {spec['_to']} ({spec['vehicle_name']} morning)",
			vehicle, MORNING_DEPART, spec["_from"], spec["_to"], 1,
		)
		_ensure_schedule(
			f"{spec['_to']} - {spec['_from']} ({spec['vehicle_name']} afternoon)",
			vehicle, AFTERNOON_DEPART, spec["_to"], spec["_from"], 2,
		)


def _ensure_vehicle(spec):
	existing = frappe.db.get_value("TIQN Vehicle", {"license_plate": spec["license_plate"]}, "name")
	if existing:
		return existing

	doc = frappe.get_doc(
		{
			"doctype": "TIQN Vehicle",
			"vehicle_name": spec["vehicle_name"],
			"license_plate": spec["license_plate"],
			"vehicle_type": spec["vehicle_type"],
			"capacity": spec["capacity"],
			"status": "available",
			"notes": spec["notes"],
		}
	).insert(ignore_permissions=True)
	return doc.name


def _ensure_schedule(template_name, vehicle, depart_time, from_location, to_location, trip_number):
	# One template per vehicle per shift: the template_name is editable, the
	# (vehicle, trip_number) pair is what identifies it.
	#
	# 🔴 KHÔNG gán driver ở đây. Tài xế giờ là một tài khoản Zalo được quản lý nâng vai
	# trò (DocType `TIQN Driver` đã bỏ 23/09/2026), nên một patch khởi tạo không thể
	# biết trước ai. Để trống thì TIQNVehicleTrip.set_default_driver() suy từ xe lúc
	# tạo chuyến - đó cũng là nguồn sự thật duy nhất, thay vì một bản sao trên lịch có
	# thể mục nát (đã mục nát thật khi đổi tên tài xế ngày 22/09).
	if frappe.db.exists(
		"TIQN Fixed Trip Schedule", {"vehicle": vehicle, "trip_number": trip_number}
	):
		return

	frappe.get_doc(
		{
			"doctype": "TIQN Fixed Trip Schedule",
			"schedule_name": template_name,
			"trip_name_template": template_name,
			"vehicle": vehicle,
			"depart_time": depart_time,
			"from_location": from_location,
			"to_location": to_location,
			"trip_number": trip_number,
			"is_active": 1,
		}
	).insert(ignore_permissions=True)
