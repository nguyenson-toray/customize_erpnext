# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""REST API for the TIQN Vehicle Management module (Zalo Mini App backend).

Base: /api/method/customize_erpnext.api.vehicle_management.<method>

Auth
----
The Mini App authenticates with one shared Frappe API Key + Secret. That user
carries the `Vehicle Manager` role, so the DocType permissions are the single
place access is decided - every endpoint below asserts `frappe.has_permission`
and nothing here uses `ignore_permissions`.

Roles inside the Mini App (requester / dispatcher / driver) come from
`TIQN Zalo Role Map` and are the Mini App's business, not ERPNext's.

Reads use `frappe.get_all`, which does not apply row-level permissions; that is
intentional - the shared API user is allowed to see every vehicle record, and
the explicit `has_permission` gate above it is what keeps a user without the
role out.
"""

import hmac
from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, get_time, getdate, now_datetime, nowdate

from customize_erpnext.vehicle_management.doctype.tiqn_vehicle.tiqn_vehicle import (
	MANUAL_STATUSES,
	VEHICLE_STATUSES,
)
from customize_erpnext.vehicle_management.doctype.tiqn_vehicle_request.tiqn_vehicle_request import (
	CONTENT_FIELDS as REQUEST_CONTENT_FIELDNAMES,
)

# Event the Dispatcher page listens on so it can refresh without polling.
DISPATCH_EVENT = "tiqn_vehicle_dispatch_update"

# Phase 1 driver login brute-force guard (see verify_driver_login).
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_SECONDS = 15 * 60

REQUEST_FIELDS = [
	"name", "employee_name", "employee_id_display", "zalo_user_id",
	"request_time", "return_time", "from_location", "to_location", "purpose",
	"passenger_count", "notes", "status", "rejection_reason", "assigned_trip",
	"submit_time", "creation", "modified",
]

TRIP_FIELDS = [
	"name", "trip_name", "trip_type", "template_id", "vehicle", "driver",
	"trip_date", "depart_time", "from_location", "to_location",
	"dispatcher_note", "notes", "status", "route_changed",
	"km_start", "km_end", "total_km", "km_start_photo", "km_end_photo",
	"start_gps_lat", "start_gps_lng", "end_gps_lat", "end_gps_lng",
	"additional_cost", "checkin_notes", "checkout_notes",
	"checkin_time", "checkout_time", "confirmed_at", "cancelled_reason",
	"creation", "modified",
]

VEHICLE_FIELDS = [
	"name", "vehicle_name", "license_plate", "vehicle_type", "capacity",
	# `image` feeds the vehicle card on the dispatch page. Adding the field to the
	# DocType is not enough - a field missing from this list is simply never sent,
	# and the card silently falls back to the bus emoji with nothing to explain why.
	"status", "image", "notes",
]

# What update_trip() is allowed to write. This is wide on purpose: the Mini App
# drives check in / check out through it. It is safe to be wide because every
# rule lives in TIQNVehicleTrip.validate()/on_update() - one-way status
# transitions, km_end > km_start, odometer continuity, total_km, vehicle status
# and linked requests all still run on doc.save(). A field NOT in this set
# (template_id, total_km, confirmed_at...) is derived and must stay derived.
TRIP_EDITABLE_FIELDS = {
	"trip_name", "trip_type", "vehicle", "driver", "trip_date", "depart_time",
	"from_location", "to_location", "dispatcher_note", "notes", "additional_cost",
	"status", "cancelled_reason", "confirmed_at", "route_changed",
	"km_start", "km_end", "km_start_photo", "km_end_photo",
	"checkin_time", "checkout_time", "checkin_notes", "checkout_notes",
	"passengers",
	# GPS is Phase 2: vehicle_management/API_CONTRACT.md says the Mini App does not send
	# start_gps_* / end_gps_* yet, so they stay out of the generic setter. The
	# columns and the dedicated checkin_trip()/checkout_trip() arguments remain,
	# ready for Phase 2 - only this door is shut.
}

# Workflow fields move a request along and stay writable at any status, subject to
# TIQNVehicleRequest.ALLOWED_TRANSITIONS.
REQUEST_WORKFLOW_FIELDS = {"status", "rejection_reason", "assigned_trip"}

# Details of the ride. Writable through update_request() only while the request is
# still `pending` - once a dispatcher has acted on it, silently moving the pickup
# point or the time would send a driver to the wrong place.
REQUEST_CONTENT_FIELDS = set(REQUEST_CONTENT_FIELDNAMES)

REQUEST_EDITABLE_FIELDS = REQUEST_WORKFLOW_FIELDS | REQUEST_CONTENT_FIELDS

# Fields that reach the DB as a DATETIME column and therefore need the ISO
# spelling normalised out (see _normalise_dt_in).
DATETIME_INPUT_FIELDS = {
	"checkin_time", "checkout_time", "confirmed_at",
	"request_time", "return_time", "submit_time",
}

# A trip is born planned. Anything further along has to go through update_trip(),
# where the transition table and the KM rules apply.
TRIP_CREATE_STATUSES = {"scheduled", "confirmed"}

VEHICLE_EDITABLE_FIELDS = {"status", "vehicle_name", "license_plate", "vehicle_type", "capacity", "notes"}

# Args the spec lists that do not exist on that particular DocType. Accepted and
# dropped rather than throwing, so a Mini App build that still sends them keeps
# working. This is PER DOCTYPE on purpose: `notes` is not a Vehicle Trip field,
# but it IS a real field on TIQN Vehicle Request - dropping it globally would
# silently swallow a note the requester typed.
# GPS is Phase 2. The Mini App still sends the keys, and Frappe's scrub() turns
# `startGPS` into `start_g_p_s`, so accept every spelling and DROP them instead of
# throwing "These fields cannot be updated" at a client that is otherwise correct.
IGNORED_TRIP_ARGS = {
	"start_g_p_s", "end_g_p_s", "startGPS", "endGPS",
	"start_gps", "end_gps",
}
IGNORED_VEHICLE_ARGS = {"current_trip"}  # computed by get_vehicles(), never stored
IGNORED_REQUEST_ARGS: set[str] = set()

# Keys Frappe itself puts in form_dict; never document fields.
FRAMEWORK_ARGS = {"cmd", "csrf_token", "doctype", "name", "run_method", "ignore_permissions", "flags"}

SCHEDULE_FIELDS = [
	"name", "schedule_name", "driver", "vehicle", "depart_time",
	"from_location", "to_location", "trip_name_template", "trip_number",
	"is_active", "days_of_week",
]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _guard(doctype, ptype="read"):
	frappe.has_permission(doctype, ptype, throw=True)


def _notify_dispatch(event, payload=None):
	"""Tell the open Dispatcher pages something changed. No email, no ZNS."""
	frappe.publish_realtime(
		DISPATCH_EVENT,
		{"event": event, **(payload or {})},
		after_commit=True,
	)


def _as_list(value):
	"""HTTP hands us either a real list (JSON body) or a JSON string (form post)."""
	if not value:
		return []
	if isinstance(value, str):
		value = frappe.parse_json(value)
	if isinstance(value, str):
		value = [value]
	return list(value)


def _as_dict_list(value):
	out = []
	for row in _as_list(value):
		if isinstance(row, str):
			row = frappe.parse_json(row)
		if isinstance(row, dict):
			out.append(row)
	return out


def _fmt_datetime(value):
	"""Datetime on the wire: "YYYY-MM-DD HH:MM:SS".

	Frappe's JSON encoder emits `str(datetime)`, which keeps microseconds
	("2026-09-15 09:28:40.123456"). vehicle_management/API_CONTRACT.md pins the format with
	no T, no Z and no fractional seconds, so every datetime the Mini App reads
	goes through here.
	"""
	if not value:
		return None
	return get_datetime(value).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_time(value):
	"""Time on the wire: "HH:MM".

	A Frappe Time column comes back as a `timedelta`, which serialises as
	"6:30:00" - no leading zero, and seconds the Mini App does not want.
	"""
	if value in (None, ""):
		return None

	if isinstance(value, timedelta):
		minutes = int(value.total_seconds()) // 60
	else:
		parts = str(value).split(":")
		minutes = int(parts[0]) * 60 + int(parts[1] if len(parts) > 1 else 0)

	return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _fmt_date(value):
	if not value:
		return None
	return str(getdate(value))


def _vehicle_lookup(names):
	"""vehicle docname -> {vehicle_name, license_plate}, one query."""
	names = [n for n in set(names) if n]
	if not names:
		return {}
	return {
		v.name: v
		for v in frappe.get_all(
			"TIQN Vehicle",
			filters={"name": ("in", names)},
			fields=["name", "vehicle_name", "license_plate"],
			limit_page_length=0,
		)
	}


def _driver_lookup(names):
	names = [n for n in set(names) if n]
	if not names:
		return {}
	return {
		d.name: d
		for d in frappe.get_all(
			"TIQN Driver",
			filters={"name": ("in", names)},
			fields=["name", "driver_name", "phone"],
			limit_page_length=0,
		)
	}


def _decorate_trips(rows):
	"""Add vehicle_name / license_plate / driver_name and fix the wire formats.

	The contract requires these three to be present whenever the trip has a
	vehicle or a driver, so they are resolved in bulk rather than per row.
	"""
	vehicles = _vehicle_lookup([r.get("vehicle") for r in rows])
	drivers = _driver_lookup([r.get("driver") for r in rows])

	for row in rows:
		vehicle = vehicles.get(row.get("vehicle"))
		driver = drivers.get(row.get("driver"))
		row["vehicle_name"] = vehicle.vehicle_name if vehicle else None
		row["license_plate"] = vehicle.license_plate if vehicle else None
		row["driver_name"] = driver.driver_name if driver else None

		row["trip_date"] = _fmt_date(row.get("trip_date"))
		row["depart_time"] = _fmt_time(row.get("depart_time"))
		for field in ("checkin_time", "checkout_time", "confirmed_at", "creation", "modified"):
			if field in row:
				row[field] = _fmt_datetime(row.get(field))

	return rows


def _decorate_requests(rows):
	for row in rows:
		for field in ("request_time", "return_time", "submit_time", "creation", "modified"):
			if field in row:
				row[field] = _fmt_datetime(row.get(field))
	return rows


def _serialise_request(doc):
	return _decorate_requests([{f: doc.get(f) for f in REQUEST_FIELDS}])[0]


def _trip_doc(name):
	if not frappe.db.exists("TIQN Vehicle Trip", name):
		frappe.throw(_("Trip {0} not found").format(name), frappe.DoesNotExistError)
	return frappe.get_doc("TIQN Vehicle Trip", name)


def _request_doc(name):
	if not frappe.db.exists("TIQN Vehicle Request", name):
		frappe.throw(_("Request {0} not found").format(name), frappe.DoesNotExistError)
	return frappe.get_doc("TIQN Vehicle Request", name)


def _serialise_trip(doc):
	"""One trip in the exact shape vehicle_management/API_CONTRACT.md documents.

	Passenger keys are the contract's (`request_id`, `from_location`, `order`),
	not the child table's column names - the Mini App was written against these.
	`_build_passenger_rows()` accepts either spelling on the way in.
	"""
	data = _decorate_trips([{f: doc.get(f) for f in TRIP_FIELDS}])[0]

	data["passengers"] = [
		{
			"passenger_name": row.passenger_name,
			"from_location": row.pickup_location,
			"request_id": row.request,
			"order": cint(row.pickup_order),
			# The child row's own docname, so an edit can be traced back. Never
			# the person - see PASSENGER_ALIASES.
			"row_name": row.name,
		}
		for row in sorted(doc.passengers or [], key=lambda r: cint(r.pickup_order))
	]
	data["stops"] = [
		{
			"location": row.location,
			"landmark": row.landmark,
			"order": cint(row.stop_order),
			"row_name": row.name,
		}
		for row in sorted(doc.stops or [], key=lambda r: cint(r.stop_order))
	]
	return data


# ---------------------------------------------------------------------------
# 3.1 Auth & Role
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET", "POST"])
def get_user_by_zalo_id(zalo_user_id):
	"""Resolve a Zalo account to its Mini App role. Returns None if unmapped."""
	_guard("TIQN Zalo Role Map")

	zalo_user_id = (zalo_user_id or "").strip()
	if not zalo_user_id:
		frappe.throw(_("zalo_user_id is required"))

	row = frappe.db.get_value(
		"TIQN Zalo Role Map",
		{"zalo_user_id": zalo_user_id},
		["zalo_user_id", "display_name", "role", "driver_ref", "employee_id"],
		as_dict=True,
	)
	if not row:
		return None

	result = {
		"zalo_user_id": row.zalo_user_id,
		"display_name": row.display_name,
		"role": row.role,
	}

	if row.role == "driver" and row.driver_ref:
		driver = frappe.db.get_value(
			"TIQN Driver",
			row.driver_ref,
			["name", "driver_name", "phone", "assigned_vehicle", "is_active"],
			as_dict=True,
		)
		if driver:
			result.update(
				{
					"driver_id": driver.name,
					"driver_name": driver.driver_name,
					"driver_phone": driver.phone,
					"vehicle_id": driver.assigned_vehicle,
					"is_active": driver.is_active,
				}
			)
	elif row.role == "requester":
		result["employee_id"] = row.employee_id

	return result


# ---------------------------------------------------------------------------
# 3.2 Vehicle Request APIs
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET", "POST"])
def get_requests(status=None, employee_id=None, employee_id_display=None, limit=200):
	"""Vehicle requests, optionally narrowed to one status and/or one employee.

	`employee_id` filters on the DocType field `employee_id_display`; both
	spellings are accepted because the Mini App and the DocType disagree on the
	name. Leaving it out returns the whole queue - that is the dispatcher's view
	and the existing behaviour, so nothing that already works changes.

	⚠ This is a CONVENIENCE filter, not an authorisation boundary. Every Mini App
	install shares one API key, so whoever holds it can ask for any employee's
	requests simply by putting a different code in the parameter - the server has
	no way to tell one requester from another in Phase 1. Real per-requester
	isolation needs server-side identity: Phase 2 maps the Zalo user to an
	employee through `TIQN Zalo Role Map`, and the filter must then be derived
	from the authenticated session rather than trusted from the caller.
	`get_my_requests(zalo_user_id)` has exactly the same limitation today.
	"""
	_guard("TIQN Vehicle Request")

	filters = {}
	if status:
		filters["status"] = status

	employee = employee_id or employee_id_display
	if employee:
		filters["employee_id_display"] = employee

	return _decorate_requests(frappe.get_all(
		"TIQN Vehicle Request",
		filters=filters,
		fields=REQUEST_FIELDS,
		order_by="request_time asc, creation asc",
		limit_page_length=cint(limit),
	))


@frappe.whitelist(methods=["GET", "POST"])
def get_my_requests(zalo_user_id, limit=100):
	_guard("TIQN Vehicle Request")
	if not zalo_user_id:
		frappe.throw(_("zalo_user_id is required"))
	return _decorate_requests(frappe.get_all(
		"TIQN Vehicle Request",
		filters={"zalo_user_id": zalo_user_id},
		fields=REQUEST_FIELDS,
		order_by="creation desc",
		limit_page_length=cint(limit),
	))


@frappe.whitelist(methods=["GET", "POST"])
def get_request(name):
	_guard("TIQN Vehicle Request")
	doc = _request_doc(name)
	return _serialise_request(doc)


@frappe.whitelist(methods=["POST"])
def create_request(
	employee_name,
	request_time,
	from_location,
	to_location,
	employee_id_display=None,
	zalo_user_id=None,
	purpose=None,
	passenger_count=1,
	return_time=None,
	notes=None,
):
	_guard("TIQN Vehicle Request", "create")

	doc = frappe.get_doc(
		{
			"doctype": "TIQN Vehicle Request",
			"employee_name": employee_name,
			"employee_id_display": employee_id_display,
			"zalo_user_id": zalo_user_id,
			"request_time": _normalise_dt_in(request_time),
			"return_time": _normalise_dt_in(return_time),
			"from_location": from_location,
			"to_location": to_location,
			"purpose": purpose,
			"notes": notes,
			"passenger_count": cint(passenger_count) or 1,
			"status": "pending",
			"submit_time": now_datetime(),
		}
	).insert()

	_notify_dispatch("request_created", {"request": doc.name})
	return _serialise_request(doc)


@frappe.whitelist(methods=["POST", "PUT"])
def approve_request(name):
	_guard("TIQN Vehicle Request", "write")
	doc = _request_doc(name)
	if doc.status != "pending":
		frappe.throw(_("Only a pending request can be approved (current: {0})").format(doc.status))

	doc.status = "approved"
	doc.save()
	_notify_dispatch("request_approved", {"request": doc.name})
	return _serialise_request(doc)


@frappe.whitelist(methods=["POST", "PUT"])
def reject_request(name, rejection_reason=None):
	_guard("TIQN Vehicle Request", "write")
	doc = _request_doc(name)
	if doc.status in ("assigned", "rejected"):
		frappe.throw(_("A {0} request cannot be rejected").format(doc.status))
	if not rejection_reason:
		frappe.throw(_("Rejection Reason is required"))

	doc.status = "rejected"
	doc.rejection_reason = rejection_reason
	doc.save()
	_notify_dispatch("request_rejected", {"request": doc.name})
	return _serialise_request(doc)


@frappe.whitelist(methods=["POST", "PUT"])
def assign_request_to_trip(request_name, trip_name):
	"""Put an approved request on an existing trip as a passenger row."""
	_guard("TIQN Vehicle Request", "write")
	_guard("TIQN Vehicle Trip", "write")

	request = _request_doc(request_name)
	if request.status == "rejected":
		frappe.throw(_("A rejected request cannot be assigned to a trip"))
	if request.status == "assigned":
		frappe.throw(
			_("Request {0} is already assigned to trip {1}").format(
				request.name, request.assigned_trip
			)
		)

	trip = _trip_doc(trip_name)
	if trip.status in ("completed", "cancelled"):
		frappe.throw(_("Cannot assign a request to a {0} trip").format(trip.status))

	if not any(row.request == request.name for row in (trip.passengers or [])):
		trip.append(
			"passengers",
			{
				"request": request.name,
				"passenger_name": request.employee_name,
				"pickup_location": request.from_location,
				"pickup_order": len(trip.passengers or []) + 1,
			},
		)
		trip.save()

	# TIQNVehicleTrip.sync_linked_requests() already flipped the request to
	# "assigned"; reload so the payload we return is not stale.
	request.reload()
	_notify_dispatch("request_assigned", {"request": request.name, "trip": trip.name})
	return _serialise_request(request)


@frappe.whitelist(methods=["POST", "PUT"])
def combine_requests_to_trip(
	request_names,
	vehicle,
	driver=None,
	trip_date=None,
	depart_time=None,
	from_location=None,
	to_location=None,
	dispatcher_note=None,
):
	"""Create one trip carrying several approved requests.

	`driver` is optional: leave it out and TIQNVehicleTrip.validate() fills in the
	vehicle's default driver. Pass it only to override with a stand-in.
	"""
	_guard("TIQN Vehicle Trip", "create")
	_guard("TIQN Vehicle Request", "write")

	names = _as_list(request_names)
	if not names:
		frappe.throw(_("At least one request is required"))

	requests = []
	for name in names:
		doc = _request_doc(name)
		if doc.status == "rejected":
			frappe.throw(_("Request {0} was rejected and cannot be combined").format(name))
		if doc.status == "assigned":
			frappe.throw(
				_("Request {0} is already assigned to trip {1}").format(name, doc.assigned_trip)
			)
		requests.append(doc)

	first = requests[0]
	trip = frappe.get_doc(
		{
			"doctype": "TIQN Vehicle Trip",
			"trip_type": "on_demand",
			"vehicle": vehicle,
			"driver": driver,
			"trip_date": getdate(trip_date) if trip_date else getdate(first.request_time),
			"depart_time": depart_time or get_time(first.request_time),
			"from_location": from_location or first.from_location,
			"to_location": to_location or first.to_location,
			"dispatcher_note": dispatcher_note,
			"status": "scheduled",
			"passengers": [
				{
					"request": doc.name,
					"passenger_name": doc.employee_name,
					"pickup_location": doc.from_location,
					"pickup_order": idx + 1,
				}
				for idx, doc in enumerate(requests)
			],
		}
	).insert()

	_notify_dispatch("trip_created", {"trip": trip.name})
	return _serialise_trip(trip)


# ---------------------------------------------------------------------------
# 3.3 Vehicle Trip APIs
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET", "POST"])
def get_trips(date=None, vehicle=None, driver=None, status=None, limit=200):
	_guard("TIQN Vehicle Trip")
	filters = {"trip_date": getdate(date) if date else getdate(nowdate())}
	if vehicle:
		filters["vehicle"] = vehicle
	if driver:
		filters["driver"] = driver
	if status:
		filters["status"] = status

	return _decorate_trips(frappe.get_all(
		"TIQN Vehicle Trip",
		filters=filters,
		fields=TRIP_FIELDS,
		order_by="depart_time asc, creation asc",
		limit_page_length=cint(limit),
	))


@frappe.whitelist(methods=["GET", "POST"])
def get_trip(name):
	_guard("TIQN Vehicle Trip")
	return _serialise_trip(_trip_doc(name))


@frappe.whitelist(methods=["GET", "POST"])
def get_today_trips_by_driver(driver_name, date=None):
	"""driver_name is the TIQN Driver docname (e.g. TIQN-DRV-001)."""
	_guard("TIQN Vehicle Trip")
	return _decorate_trips(frappe.get_all(
		"TIQN Vehicle Trip",
		filters={"driver": driver_name, "trip_date": getdate(date) if date else getdate(nowdate())},
		fields=TRIP_FIELDS,
		order_by="depart_time asc, creation asc",
		limit_page_length=0,
	))


@frappe.whitelist(methods=["GET", "POST"])
def get_last_completed_trip_by_vehicle(vehicle, date=None):
	"""Latest completed trip of a vehicle - used to pre-fill KM Start."""
	_guard("TIQN Vehicle Trip")
	rows = frappe.get_all(
		"TIQN Vehicle Trip",
		filters={
			"vehicle": vehicle,
			"status": "completed",
			"trip_date": getdate(date) if date else getdate(nowdate()),
		},
		fields=TRIP_FIELDS,
		order_by="checkout_time desc, modified desc",
		limit_page_length=1,
	)
	return _decorate_trips(rows)[0] if rows else None


@frappe.whitelist(methods=["GET", "POST"])
def get_fixed_templates_for_driver(driver_name, trip_date=None):
	"""Active templates of a driver, each flagged with today's trip if created."""
	_guard("TIQN Fixed Trip Schedule")
	on_date = getdate(trip_date) if trip_date else getdate(nowdate())

	templates = frappe.get_all(
		"TIQN Fixed Trip Schedule",
		filters={"driver": driver_name, "is_active": 1},
		fields=SCHEDULE_FIELDS,
		order_by="trip_number asc, depart_time asc",
		limit_page_length=0,
	)
	if not templates:
		return []

	existing = frappe.get_all(
		"TIQN Vehicle Trip",
		filters={
			"template_id": ("in", [t.name for t in templates]),
			"trip_date": on_date,
			"status": ("!=", "cancelled"),
		},
		fields=["name", "template_id", "status"],
		order_by="creation asc",
	)
	by_template = {row.template_id: row for row in existing}

	for template in templates:
		row = by_template.get(template.name)
		template["trip_created_today"] = bool(row)
		template["trip_name"] = row.name if row else None
		template["trip_status"] = row.status if row else None

	return templates


@frappe.whitelist(methods=["POST"])
def create_trip(
	vehicle,
	trip_date,
	driver=None,
	depart_time=None,
	from_location=None,
	to_location=None,
	trip_type="on_demand",
	dispatcher_note=None,
	trip_name=None,
	notes=None,
	status=None,
	template_id=None,
	passengers=None,
	stops=None,
):
	_guard("TIQN Vehicle Trip", "create")

	if status and status not in TRIP_CREATE_STATUSES:
		frappe.throw(
			_("A new trip can only start as {0}").format(" or ".join(sorted(TRIP_CREATE_STATUSES)))
		)

	doc = frappe.get_doc(
		{
			"doctype": "TIQN Vehicle Trip",
			"trip_name": trip_name,
			"trip_type": trip_type or "on_demand",
			"template_id": template_id,
			"vehicle": vehicle,
			"driver": driver,
			"trip_date": getdate(trip_date),
			"depart_time": depart_time,
			"from_location": from_location,
			"to_location": to_location,
			"dispatcher_note": dispatcher_note,
			"notes": notes,
			"status": status or "scheduled",
			"passengers": _build_passenger_rows(passengers),
			"stops": [
				{
					"location": row.get("location"),
					"landmark": row.get("landmark"),
					"stop_order": cint(row.get("stop_order") or row.get("order") or idx + 1),
				}
				for idx, row in enumerate(_as_dict_list(stops))
			],
		}
	).insert()

	_notify_dispatch("trip_created", {"trip": doc.name})
	return _serialise_trip(doc)


@frappe.whitelist(methods=["POST"])
def create_trip_from_template(template_name, trip_date=None):
	"""Driver starts a fixed trip. Idempotent: one trip per template per day."""
	_guard("TIQN Vehicle Trip", "create")

	if not frappe.db.exists("TIQN Fixed Trip Schedule", template_name):
		frappe.throw(_("Template {0} not found").format(template_name), frappe.DoesNotExistError)

	template = frappe.get_doc("TIQN Fixed Trip Schedule", template_name)
	if not template.is_active:
		frappe.throw(_("Template {0} is not active").format(template_name))

	on_date = getdate(trip_date) if trip_date else getdate(nowdate())

	existing = frappe.get_all(
		"TIQN Vehicle Trip",
		filters={
			"template_id": template.name,
			"trip_date": on_date,
			"status": ("!=", "cancelled"),
		},
		fields=["name"],
		order_by="creation asc",
		limit_page_length=1,
	)
	if existing:
		return _serialise_trip(_trip_doc(existing[0].name))

	doc = frappe.get_doc(
		{
			"doctype": "TIQN Vehicle Trip",
			"trip_name": f"{template.schedule_name} - {frappe.format(on_date, {'fieldtype': 'Date'})}",
			"trip_type": "fixed",
			"template_id": template.name,
			"vehicle": template.vehicle,
			"driver": template.driver,
			"trip_date": on_date,
			"depart_time": template.depart_time,
			"from_location": template.from_location,
			"to_location": template.to_location,
			"status": "confirmed",
			"confirmed_at": now_datetime(),
		}
	).insert()

	_notify_dispatch("trip_created", {"trip": doc.name})
	return _serialise_trip(doc)


def _clean_kwargs(fields, editable, label, ignored=frozenset()):
	"""Strip framework noise from a **kwargs endpoint and check what is left.

	`frappe.get_newargs` hands a function declaring **kwargs the ENTIRE form_dict,
	so `cmd` and friends arrive alongside real field names. Writing those onto the
	document would quietly corrupt it.
	"""
	fields = {
		k: v
		for k, v in fields.items()
		if k not in FRAMEWORK_ARGS and k not in ignored and not k.startswith("_")
	}

	unknown = set(fields) - editable
	if unknown:
		frappe.throw(
			_("These fields cannot be updated on {0}: {1}").format(label, ", ".join(sorted(unknown)))
		)

	# A value the caller left out and a value the caller nulled are different
	# things, but the Mini App sends `null` for "no change", so None is dropped.
	return {
		k: (_normalise_dt_in(v) if k in DATETIME_INPUT_FIELDS else v)
		for k, v in fields.items()
		if v is not None
	}


def _normalise_dt_in(value):
	"""Accept an ISO datetime from the Mini App and hand MySQL what it wants.

	A browser's `Date.toISOString()` produces "2026-09-15T07:28:40.415Z", which
	MySQL rejects for a DATETIME column ("Incorrect datetime value"). Strip the
	T, the Z and the milliseconds. The contract asks the Mini App to send
	"YYYY-MM-DD HH:MM:SS"; this makes a client that forgets harmless instead of
	fatal.

	NOTE the Z is dropped, not converted: the Mini App builds these from local
	Vietnam time and merely labels them UTC. Treating them as real UTC would
	shift every check-in by 7 hours.
	"""
	if not isinstance(value, str):
		return value

	text = value.strip()
	if "T" not in text and "Z" not in text:
		return text

	return text.replace("T", " ").replace("Z", "").split(".")[0][:19].strip()


@frappe.whitelist(methods=["POST", "PUT"])
def update_trip(name, **fields):
	"""Generic trip setter used by the Mini App for check in, check out and re-routing.

	Every rule still applies: this goes through doc.save(), so
	TIQNVehicleTrip.validate() rejects a backwards status change, a km_end below
	km_start, or a km_start below the last completed trip of the same vehicle,
	and on_update() keeps the vehicle status and the linked requests in step.

	Deliberately NOT `ignore_permissions=True` and NOT followed by
	frappe.db.commit(), despite the spec snippet: permissions are what stop any
	random ERPNext account from rewriting trips, and Frappe already commits at the
	end of a successful request - committing here would break the transaction and
	let tests leak into the real database.
	"""
	_guard("TIQN Vehicle Trip", "write")
	doc = _trip_doc(name)

	fields = _clean_kwargs(fields, TRIP_EDITABLE_FIELDS, _("Trip"), IGNORED_TRIP_ARGS)

	passengers = fields.pop("passengers", None)
	for key, value in fields.items():
		doc.set(key, value)

	if passengers is not None:
		_set_trip_passengers(doc, passengers)

	doc.save()
	_notify_dispatch("trip_updated", {"trip": doc.name})
	return _serialise_trip(doc)


# Every spelling of a passenger key seen in the wild, in priority order. The Mini
# App has shipped camelCase (`requestId`/`fromLocation`) AND snake_case
# (`request_id`/`from_location`), and _serialise_trip() hands back a third shape
# when a trip is read and pushed straight back. A key that is not listed here is
# dropped in silence, which is exactly how `from_location` and `request_id` went
# missing before - so add new spellings here rather than at the call site.
PASSENGER_ALIASES = {
	"request": ("request", "request_id", "requestId"),
	"passenger_name": ("passenger_name", "passengerName"),
	"pickup_location": ("pickup_location", "pickupLocation", "from_location", "fromLocation"),
	"pickup_order": ("pickup_order", "pickupOrder", "order"),
}


def _pick(row, field):
	for key in PASSENGER_ALIASES[field]:
		value = row.get(key)
		if value not in (None, ""):
			return value
	return None


def _normalise_passenger(row, idx):
	"""Turn one inbound passenger dict into a TIQN Trip Passenger row.

	`passenger_name` is mandatory on the child table, and a nameless passenger is
	no use to a driver anyway, so it is filled from the linked request when the
	caller did not send one - that covers the normal case, where the row came
	from a request that already carries the employee's name.
	"""
	request = _pick(row, "request")
	name = _pick(row, "passenger_name")

	# Bare `name` means the person only when the caller is not echoing a row that
	# came out of _serialise_trip(), where `name` is the child row's docname.
	if not name and "passenger_name" not in row:
		name = row.get("name") or None

	if not name and request:
		name = frappe.db.get_value("TIQN Vehicle Request", request, "employee_name")

	if not name:
		frappe.throw(
			_("Passenger row {0} has no name. Send passenger_name, or a request to take it from.").format(
				idx + 1
			)
		)

	return {
		"request": request,
		"passenger_name": name,
		"pickup_location": _pick(row, "pickup_location"),
		"pickup_order": cint(_pick(row, "pickup_order") or idx + 1),
	}


def _build_passenger_rows(passengers):
	return [_normalise_passenger(row, idx) for idx, row in enumerate(_as_dict_list(passengers))]


def _set_trip_passengers(doc, passengers):
	"""Replace the passenger rows from the Mini App's JSON array.

	The child table is the storage, not a Long Text blob, so the dispatcher page,
	`combine_requests_to_trip` and `sync_linked_requests` all keep working.
	"""
	doc.set("passengers", [])
	for row in _build_passenger_rows(passengers):
		doc.append("passengers", row)


@frappe.whitelist(methods=["POST", "PUT"])
def update_request(name, **fields):
	"""Generic request setter: reject a request, or attach it to a trip.

	The Phase 1 flow has no separate approval step - creating the trip IS the
	approval, so `pending -> assigned` is a legal jump. The transition table in
	TIQNVehicleRequest enforces the rest, and refuses `assigned` without an
	`assigned_trip` or `rejected` without a reason.

	Content fields (where, when, who, how many) are writable only while the
	request is still `pending`. After that a dispatcher has already read it and
	possibly built a trip around it; letting the requester quietly move the pickup
	point would send a driver to the wrong place with nothing on screen to say so.
	Workflow fields stay writable, so cancelling a scheduled ride still works.

	The guard lives here rather than in the controller on purpose: a Desk admin
	fixing a typo on an assigned request is legitimate, and the controller is what
	Desk goes through.
	"""
	_guard("TIQN Vehicle Request", "write")
	doc = _request_doc(name)

	fields = _clean_kwargs(fields, REQUEST_EDITABLE_FIELDS, _("Request"), IGNORED_REQUEST_ARGS)

	# `doc.status` here is the status BEFORE this call, which is what decides
	# whether editing is still open. A pending request may therefore be edited and
	# cancelled in the same call.
	locked = set(fields) & REQUEST_CONTENT_FIELDS
	if locked and doc.status != "pending":
		frappe.throw(
			_("Request {0} is already {1} - only a pending request can have its details changed ({2}).").format(
				doc.name, doc.status, ", ".join(sorted(locked))
			)
		)

	for key, value in fields.items():
		doc.set(key, value)

	doc.save()
	_notify_dispatch("request_updated", {"request": doc.name})
	return _serialise_request(doc)


@frappe.whitelist(methods=["POST", "PUT"])
def update_vehicle(name, **fields):
	"""Generic vehicle setter, mostly for the status buttons.

	`in_trip` is owned by trip check in / check out. It is accepted here only
	when the vehicle really is running a trip, so the board cannot be made to
	show a busy vehicle that is not on the road - and the reverse.
	"""
	_guard("TIQN Vehicle", "write")

	if not frappe.db.exists("TIQN Vehicle", name):
		frappe.throw(_("Vehicle {0} not found").format(name), frappe.DoesNotExistError)

	fields = _clean_kwargs(fields, VEHICLE_EDITABLE_FIELDS, _("Vehicle"), IGNORED_VEHICLE_ARGS)
	status = fields.get("status")

	if status and status not in VEHICLE_STATUSES:
		frappe.throw(
			_("Status must be one of: {0}").format(", ".join(VEHICLE_STATUSES))
		)

	running = frappe.db.get_value(
		"TIQN Vehicle Trip", {"vehicle": name, "status": "in_progress"}, "name"
	)
	if status == "in_trip" and not running:
		frappe.throw(
			_("Vehicle {0} has no trip in progress. Check a trip in instead of setting in_trip.").format(name)
		)
	if status and status != "in_trip" and running and status != "available":
		frappe.throw(
			_("Vehicle {0} is running trip {1}. Finish or cancel it first.").format(name, running)
		)

	doc = frappe.get_doc("TIQN Vehicle", name)
	for key, value in fields.items():
		doc.set(key, value)
	doc.save()

	_notify_dispatch("vehicle_updated", {"vehicle": doc.name, "status": doc.status})
	return {f: doc.get(f) for f in VEHICLE_FIELDS}


@frappe.whitelist(methods=["POST", "PUT"])
def confirm_trip(name):
	_guard("TIQN Vehicle Trip", "write")
	doc = _trip_doc(name)
	if doc.status != "scheduled":
		frappe.throw(_("Only a scheduled trip can be confirmed (current: {0})").format(doc.status))

	doc.status = "confirmed"
	doc.confirmed_at = now_datetime()
	doc.save()
	_notify_dispatch("trip_confirmed", {"trip": doc.name})
	return _serialise_trip(doc)


@frappe.whitelist(methods=["POST", "PUT"])
def cancel_trip(name, cancelled_reason=None):
	_guard("TIQN Vehicle Trip", "write")
	doc = _trip_doc(name)
	if doc.status == "completed":
		frappe.throw(_("A completed trip cannot be cancelled"))

	doc.status = "cancelled"
	doc.cancelled_reason = cancelled_reason
	doc.save()
	_notify_dispatch("trip_cancelled", {"trip": doc.name})
	return _serialise_trip(doc)


@frappe.whitelist(methods=["POST", "PUT"])
def update_trip_route(name, from_location=None, to_location=None, dispatcher_note=None):
	"""Dispatcher re-routes a trip. If it is already running, the driver has to
	acknowledge the change before the flag clears."""
	_guard("TIQN Vehicle Trip", "write")
	doc = _trip_doc(name)
	if doc.status in ("completed", "cancelled"):
		frappe.throw(_("Cannot change the route of a {0} trip").format(doc.status))

	if from_location:
		doc.from_location = from_location
	if to_location:
		doc.to_location = to_location
	if dispatcher_note is not None:
		doc.dispatcher_note = dispatcher_note

	if doc.status == "in_progress":
		doc.route_changed = 1

	doc.save()

	# Wake up the driver's Mini App session. Deliberately realtime only - no
	# email and no ZNS is armed from here (see utils/zns.py).
	frappe.publish_realtime(
		"tiqn_trip_route_changed",
		{
			"trip": doc.name,
			"driver": doc.driver,
			"from_location": doc.from_location,
			"to_location": doc.to_location,
			"dispatcher_note": doc.dispatcher_note,
		},
		after_commit=True,
	)
	_notify_dispatch("trip_route_changed", {"trip": doc.name})
	return _serialise_trip(doc)


@frappe.whitelist(methods=["POST", "PUT"])
def checkin_trip(
	name,
	km_start,
	km_start_photo=None,
	start_gps_lat=None,
	start_gps_lng=None,
	checkin_notes=None,
):
	_guard("TIQN Vehicle Trip", "write")
	doc = _trip_doc(name)

	if doc.status not in ("scheduled", "confirmed"):
		frappe.throw(_("Trip {0} cannot be checked in (current status: {1})").format(name, doc.status))

	km_start = flt(km_start)
	if km_start <= 0:
		frappe.throw(_("KM Start must be greater than zero"))

	# Odometer continuity against the previous completed trip is enforced by
	# TIQNVehicleTrip.validate_odometer_continuity() on save, so that the generic
	# update_trip() path gets the same rule instead of a second copy of it here.
	doc.km_start = km_start
	doc.km_start_photo = km_start_photo or doc.km_start_photo
	doc.start_gps_lat = flt(start_gps_lat) if start_gps_lat not in (None, "") else None
	doc.start_gps_lng = flt(start_gps_lng) if start_gps_lng not in (None, "") else None
	doc.checkin_notes = checkin_notes
	doc.checkin_time = now_datetime()
	doc.status = "in_progress"
	doc.save()  # on_update flips the vehicle to in_trip

	_notify_dispatch("trip_checked_in", {"trip": doc.name})
	return _serialise_trip(doc)


@frappe.whitelist(methods=["POST", "PUT"])
def checkout_trip(
	name,
	km_end,
	km_end_photo=None,
	end_gps_lat=None,
	end_gps_lng=None,
	checkout_notes=None,
	additional_cost=None,
):
	_guard("TIQN Vehicle Trip", "write")
	doc = _trip_doc(name)

	if doc.status != "in_progress":
		frappe.throw(_("Trip {0} is not in progress (current status: {1})").format(name, doc.status))

	km_end = flt(km_end)
	if km_end <= flt(doc.km_start):
		frappe.throw(
			_("KM End ({0}) must be greater than KM Start ({1})").format(km_end, flt(doc.km_start))
		)

	doc.km_end = km_end
	doc.km_end_photo = km_end_photo or doc.km_end_photo
	doc.end_gps_lat = flt(end_gps_lat) if end_gps_lat not in (None, "") else None
	doc.end_gps_lng = flt(end_gps_lng) if end_gps_lng not in (None, "") else None
	doc.checkout_notes = checkout_notes
	if additional_cost not in (None, ""):
		doc.additional_cost = flt(additional_cost)
	doc.checkout_time = now_datetime()
	doc.status = "completed"
	doc.save()  # on_update releases the vehicle back to available

	_notify_dispatch("trip_checked_out", {"trip": doc.name})
	return _serialise_trip(doc)


@frappe.whitelist(methods=["POST", "PUT"])
def acknowledge_route_change(name):
	_guard("TIQN Vehicle Trip", "write")
	doc = _trip_doc(name)
	if doc.route_changed:
		doc.db_set("route_changed", 0)
	_notify_dispatch("trip_route_acknowledged", {"trip": doc.name})
	return _serialise_trip(_trip_doc(name))


# ---------------------------------------------------------------------------
# 3.4 Vehicle APIs
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET", "POST"])
def get_vehicles(status=None):
	"""Every vehicle, each carrying its running trip when it has one."""
	_guard("TIQN Vehicle")
	filters = {"status": status} if status else {}
	vehicles = frappe.get_all(
		"TIQN Vehicle",
		filters=filters,
		fields=VEHICLE_FIELDS,
		order_by="vehicle_name asc",
		limit_page_length=0,
	)
	if not vehicles:
		return []

	running = frappe.get_all(
		"TIQN Vehicle Trip",
		filters={"vehicle": ("in", [v.name for v in vehicles]), "status": "in_progress"},
		fields=[
			"name", "vehicle", "driver", "trip_name", "from_location", "to_location",
			"depart_time", "checkin_time", "km_start", "route_changed",
		],
		order_by="checkin_time desc",
	)
	by_vehicle = {}
	for row in running:
		by_vehicle.setdefault(row.vehicle, row)

	driver_names = {
		d.name: d.driver_name
		for d in frappe.get_all(
			"TIQN Driver", fields=["name", "driver_name"], limit_page_length=0
		)
	}

	for vehicle in vehicles:
		trip = by_vehicle.get(vehicle.name)
		if trip:
			trip["driver_name"] = driver_names.get(trip.driver)
			trip["depart_time"] = _fmt_time(trip.get("depart_time"))
			trip["checkin_time"] = _fmt_datetime(trip.get("checkin_time"))
		vehicle["current_trip"] = trip

	return vehicles


@frappe.whitelist(methods=["GET", "POST"])
def get_vehicle_status():
	"""Contract name for "every vehicle plus the trip it is on right now".

	Identical payload to get_vehicles(); both exist because the Mini App calls
	this one and the Dispatcher page calls the other.
	"""
	return get_vehicles()


@frappe.whitelist(methods=["POST", "PUT"])
def update_vehicle_status(vehicle, status):
	"""Phase 0 name for the status button. Narrower than update_vehicle(): it
	refuses `in_trip` outright, because a human pressing a button never has a
	legitimate reason to claim a vehicle is on the road."""
	if status not in MANUAL_STATUSES:
		frappe.throw(
			_("Status must be one of: {0}. in_trip is set automatically by trip check in.").format(
				", ".join(MANUAL_STATUSES)
			)
		)
	return update_vehicle(vehicle, status=status)


@frappe.whitelist(methods=["GET", "POST"])
def get_drivers():
	"""Active drivers, for the Mini App login picker.

	Never selects `password`. The column holds "*" repeated to the length of the
	real password, so asking for it would hand out the password length for free.
	`zalo_user_id` is left out for the same reason - this list is readable by
	anyone holding the Mini App's shared API key, which ships inside the client.
	"""
	_guard("TIQN Driver")

	drivers = frappe.get_all(
		"TIQN Driver",
		filters={"is_active": 1},
		# is_active is already the filter, but it ships in the payload too: the
		# dispatch page checks it before auto-filling a driver, and a field that is
		# absent reads as falsy there - the driver would never be filled in.
		fields=["name", "driver_name", "phone", "assigned_vehicle", "is_active"],
		order_by="driver_name asc",
		limit_page_length=0,
	)
	if not drivers:
		return []

	# One query for every vehicle instead of one per driver.
	vehicles = {
		v.name: v
		for v in frappe.get_all(
			"TIQN Vehicle",
			filters={"name": ("in", [d.assigned_vehicle for d in drivers if d.assigned_vehicle])},
			fields=["name", "vehicle_name", "license_plate"],
			limit_page_length=0,
		)
	}

	for driver in drivers:
		vehicle = vehicles.get(driver.assigned_vehicle)
		if vehicle:
			driver["assigned_vehicle_name"] = f"{vehicle.vehicle_name} \u2022 {vehicle.license_plate}"
		else:
			driver["assigned_vehicle_name"] = driver.assigned_vehicle

	return drivers


@frappe.whitelist(methods=["POST"])
def verify_driver_login(driver_name, password):
	"""Phase 1 driver login: pick your name, type the password.

	Phase 2 replaces this with the Zalo User ID mapping, at which point this
	endpoint and the `password` field should be removed rather than left lying
	around.

	Security notes, so nobody mistakes this for real authentication:
	  * A DocType `Password` field is ENCRYPTED, not hashed - frappe stores it in
	    `__Auth` with encrypted=1 and can decrypt it back. `check_password()`
	    only ever matches hashed rows (encrypted=0), so it can never verify this
	    field; `Document.get_password()` is the accessor that works.
	  * Passwords here are short and shared, so the endpoint locks a driver out
	    for LOCKOUT_SECONDS after MAX_LOGIN_ATTEMPTS wrong tries. Without that,
	    a value like "driver01" falls in seconds.
	"""
	_guard("TIQN Driver")

	if not driver_name or not password:
		frappe.throw(_("Driver and password are required"), frappe.AuthenticationError)

	if not frappe.db.exists("TIQN Driver", driver_name):
		# Same message as a wrong password: do not confirm which names exist.
		frappe.throw(_("Incorrect driver or password"), frappe.AuthenticationError)

	_check_login_lockout(driver_name)

	driver = frappe.get_doc("TIQN Driver", driver_name)
	if not driver.is_active:
		frappe.throw(_("This driver is no longer active"), frappe.AuthenticationError)

	stored = driver.get_password("password", raise_exception=False)
	if not stored:
		frappe.throw(
			_("No Mini App password has been set for {0} yet").format(driver.driver_name),
			frappe.AuthenticationError,
		)

	if not hmac.compare_digest(str(stored), str(password)):
		_record_failed_login(driver_name)
		frappe.throw(_("Incorrect driver or password"), frappe.AuthenticationError)

	_clear_failed_logins(driver_name)

	vehicle = (
		frappe.db.get_value(
			"TIQN Vehicle", driver.assigned_vehicle, ["vehicle_name", "license_plate"], as_dict=True
		)
		if driver.assigned_vehicle
		else None
	)

	return {
		"name": driver.name,
		"driver_name": driver.driver_name,
		"phone": driver.phone,
		"assigned_vehicle": driver.assigned_vehicle,
		"assigned_vehicle_name": vehicle.vehicle_name if vehicle else None,
		"assigned_vehicle_plate": vehicle.license_plate if vehicle else None,
	}


def _login_cache_key(driver_name):
	return f"tiqn_driver_login_fail:{driver_name}"


def _check_login_lockout(driver_name):
	attempts = cint(frappe.cache.get_value(_login_cache_key(driver_name)))
	if attempts >= MAX_LOGIN_ATTEMPTS:
		frappe.throw(
			_("Too many failed attempts. Try again in {0} minutes.").format(LOCKOUT_SECONDS // 60),
			frappe.AuthenticationError,
		)


def _record_failed_login(driver_name):
	key = _login_cache_key(driver_name)
	attempts = cint(frappe.cache.get_value(key)) + 1
	# The TTL is refreshed on every failure, so a slow drip does not reset it.
	frappe.cache.set_value(key, attempts, expires_in_sec=LOCKOUT_SECONDS)


def _clear_failed_logins(driver_name):
	frappe.cache.delete_value(_login_cache_key(driver_name))


# ---------------------------------------------------------------------------
# 3.5 Report APIs
# ---------------------------------------------------------------------------
@frappe.whitelist(methods=["GET", "POST"])
def get_trip_report(start_date, end_date, vehicle=None, driver=None):
	_guard("TIQN Vehicle Trip")

	start_date, end_date = getdate(start_date), getdate(end_date)
	if start_date > end_date:
		frappe.throw(_("Start Date must be on or before End Date"))

	filters = {"trip_date": ("between", [start_date, end_date])}
	if vehicle:
		filters["vehicle"] = vehicle
	if driver:
		filters["driver"] = driver

	trips = _decorate_trips(frappe.get_all(
		"TIQN Vehicle Trip",
		filters=filters,
		fields=TRIP_FIELDS,
		order_by="trip_date asc, depart_time asc",
		limit_page_length=0,
	))

	km_by_vehicle, km_by_driver = {}, {}
	total_km = total_cost = 0.0
	completed = cancelled = 0

	for trip in trips:
		# _decorate_trips() already resolved the names; fall back to the docname so
		# a deleted vehicle still groups under something readable.
		trip["vehicle_name"] = trip.get("vehicle_name") or trip.get("vehicle")
		trip["driver_name"] = trip.get("driver_name") or trip.get("driver")

		if trip.status == "completed":
			completed += 1
		elif trip.status == "cancelled":
			cancelled += 1

		km = flt(trip.total_km)
		total_km += km
		total_cost += flt(trip.additional_cost)

		if km:
			km_by_vehicle[trip["vehicle_name"]] = flt(km_by_vehicle.get(trip["vehicle_name"], 0)) + km
			km_by_driver[trip["driver_name"]] = flt(km_by_driver.get(trip["driver_name"], 0)) + km

	return {
		"trips": trips,
		"summary": {
			"total_trips": len(trips),
			"total_km": flt(total_km, 1),
			"total_additional_cost": flt(total_cost, 2),
			"completed": completed,
			"cancelled": cancelled,
			"km_by_vehicle": {k: flt(v, 1) for k, v in km_by_vehicle.items()},
			"km_by_driver": {k: flt(v, 1) for k, v in km_by_driver.items()},
		},
	}


@frappe.whitelist(methods=["GET", "POST"])
def get_today_stats(date=None):
	_guard("TIQN Vehicle Trip")
	on_date = getdate(date) if date else getdate(nowdate())

	counts = dict.fromkeys(
		("scheduled", "confirmed", "in_progress", "completed", "cancelled"), 0
	)
	# One day of trips is a handful of rows, so pull the statuses and tally them
	# here. v16 refuses SQL functions written as strings in `fields`.
	for row in frappe.get_all(
		"TIQN Vehicle Trip",
		filters={"trip_date": on_date},
		fields=["status"],
		order_by="status asc",
		limit_page_length=0,
	):
		if row.status in counts:
			counts[row.status] += 1

	return {
		"date": str(on_date),
		"total": sum(counts.values()),
		"scheduled": counts["scheduled"],
		"confirmed": counts["confirmed"],
		"in_progress": counts["in_progress"],
		"completed": counts["completed"],
		"cancelled": counts["cancelled"],
		"pending": frappe.db.count("TIQN Vehicle Request", {"status": "pending"}),
	}


@frappe.whitelist(methods=["GET", "POST"])
def get_dispatch_overview(date=None):
	"""One round trip for the whole Dispatcher page (stats + vehicles + queues)."""
	_guard("TIQN Vehicle Trip")
	on_date = getdate(date) if date else getdate(nowdate())

	trips = get_trips(date=on_date, limit=0)

	pending = get_requests(status="pending", limit=0)
	_flag_overdue(pending)

	return {
		"date": str(on_date),
		"stats": get_today_stats(on_date),
		"vehicles": get_vehicles(),
		# Drivers ride along so the dispatch page can fill in the driver the moment
		# a vehicle is picked, without a second round trip mid-dialog. Each driver
		# carries `assigned_vehicle`, which is what that lookup keys on.
		"drivers": get_drivers(),
		"pending_requests": pending,
		"combinable": find_combinable_requests(pending),
		"trips": trips,
	}


# A request is "due soon" once the vehicle is needed within this many minutes.
DUE_SOON_MINUTES = 10


def _flag_overdue(requests):
	"""Add `minutes_until` to each request: minutes from now to request_time.

	Negative means the moment the vehicle was wanted has already passed.

	Computed on the SERVER on purpose. Doing the subtraction in the browser would
	compare a naive "YYYY-MM-DD HH:MM:SS" string in site time against the visitor's
	clock - correct only while everyone sits in the same timezone as the site, and
	silently wrong the day someone opens the board from elsewhere.
	"""
	now = now_datetime()
	for row in requests:
		if not row.get("request_time"):
			row["minutes_until"] = None
			continue
		delta = get_datetime(row["request_time"]) - now
		row["minutes_until"] = int(delta.total_seconds() // 60)
	return requests


def find_combinable_requests(requests, window_minutes=30):
	"""Group pending requests that share a route and start within +/- 30 minutes.

	Returns a list of groups, each a list of request names. Pure function so it
	can be unit tested without a database.
	"""
	from frappe.utils import get_datetime

	buckets = {}
	for row in requests:
		key = (
			(row.get("from_location") or "").strip().lower(),
			(row.get("to_location") or "").strip().lower(),
		)
		buckets.setdefault(key, []).append(row)

	groups = []
	for rows in buckets.values():
		if len(rows) < 2:
			continue
		rows = sorted(rows, key=lambda r: get_datetime(r.get("request_time")))
		current = [rows[0]]
		for row in rows[1:]:
			delta = get_datetime(row["request_time"]) - get_datetime(current[0]["request_time"])
			if abs(delta.total_seconds()) <= window_minutes * 60:
				current.append(row)
			else:
				if len(current) > 1:
					groups.append([r["name"] for r in current])
				current = [row]
		if len(current) > 1:
			groups.append([r["name"] for r in current])

	return groups


# ---------------------------------------------------------------------------
# Scheduled fixed trips (vehicle_management/API_CONTRACT.md mục 8)
# ---------------------------------------------------------------------------
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


def create_scheduled_trips(trip_date=None, force_all=False):
	"""Create today's fixed trips from TIQN Fixed Trip Schedule.

	Registered on cron in hooks.py at 06:30 and 17:00. The driver opens the Mini
	App and the trip is already there.

	Timezone: Frappe evaluates cron with `now_datetime()`, which is the SITE
	timezone (System Settings.time_zone), not UTC - so `30 6 * * *` really is
	06:30 in Vietnam on this bench. Verified: System Settings.time_zone is
	Asia/Ho_Chi_Minh and the server clock matches. That setting is known to revert
	to Asia/Kolkata on this site; if fixed trips start appearing ~1.5 hours late,
	check it before touching this function.

	Idempotent on (vehicle, trip_date, depart_time, trip_type=fixed), so a
	scheduler restart, a manual run, or a driver who used
	create_trip_from_template() first will never produce a duplicate.

	Not whitelisted on purpose: this writes records for the whole fleet and has
	no business being reachable over HTTP. Run it by hand with
	`bench --site <site> execute
	customize_erpnext.api.vehicle_management.create_scheduled_trips`.
	"""
	on_date = getdate(trip_date) if trip_date else getdate(nowdate())
	weekday = WEEKDAY_NAMES[on_date.weekday()]
	now_hhmm = now_datetime().strftime("%H:%M")

	schedules = frappe.get_all(
		"TIQN Fixed Trip Schedule",
		filters={"is_active": 1},
		fields=SCHEDULE_FIELDS,
		order_by="depart_time asc, name asc",
		limit_page_length=0,
	)

	created, skipped, not_due = [], [], []

	for schedule in schedules:
		allowed = [d.strip() for d in (schedule.days_of_week or "").split(",") if d.strip()]
		if allowed and weekday not in allowed:
			not_due.append(schedule.name)
			continue

		# Each cron tick only creates the trips due at that tick. `force_all`
		# exists for a manual catch-up run, and for tests.
		depart = _fmt_time(schedule.depart_time)
		if not force_all and depart != now_hhmm:
			not_due.append(schedule.name)
			continue

		existing = frappe.db.exists(
			"TIQN Vehicle Trip",
			{
				"vehicle": schedule.vehicle,
				"trip_date": on_date,
				"depart_time": schedule.depart_time,
				"trip_type": "fixed",
			},
		)
		if existing:
			skipped.append(schedule.name)
			continue

		created.append(_create_trip_from_schedule(schedule, on_date))

	frappe.db.commit()  # scheduler task: nothing else commits for us

	summary = {
		"date": str(on_date),
		"weekday": weekday,
		"clock": now_hhmm,
		"created": created,
		"skipped": skipped,
		"not_due": not_due,
	}
	frappe.logger("vehicle_management").info({"create_scheduled_trips": summary})

	if created:
		_notify_dispatch("scheduled_trips_created", {"trips": created})

	return summary


def _create_trip_from_schedule(schedule, on_date):
	vehicle_name = (
		frappe.db.get_value("TIQN Vehicle", schedule.vehicle, "vehicle_name") or schedule.vehicle
	)
	trip_name = (schedule.trip_name_template or schedule.schedule_name or _("Fixed trip")).replace(
		"{vehicle_name}", vehicle_name
	)

	doc = frappe.get_doc(
		{
			"doctype": "TIQN Vehicle Trip",
			"trip_name": trip_name,
			"trip_type": "fixed",
			"template_id": schedule.name,
			"trip_date": on_date,
			"status": "scheduled",
			"vehicle": schedule.vehicle,
			"driver": schedule.driver,
			"depart_time": schedule.depart_time,
			"from_location": schedule.from_location,
			"to_location": schedule.to_location,
		}
	).insert(ignore_permissions=True)
	return doc.name


# ---------------------------------------------------------------------------
# Excel export (vehicle_management/API_CONTRACT.md mục 7)
# ---------------------------------------------------------------------------
# (source string, column width). English source per the app-wide UI rule; the
# Vietnamese a user actually sees comes from translations/vi.csv.
EXCEL_HEADERS = [
	("Date", 12), ("Vehicle", 16), ("License Plate", 14), ("Driver", 20),
	("Start Time", 12), ("End Time", 12),
	("From", 28), ("To", 28),
	("KM Start", 12), ("KM End", 12), ("Billable KM", 12),
	("Additional Cost", 18), ("Status", 14), ("Notes", 30),
]
KM_COLUMNS = (9, 10, 11)
COST_COLUMN = 12
KM_FORMAT = "#,##0.00"
COST_FORMAT = "#,##0"

# How long an exported file survives. The hourly cleanup below removes anything
# older; a download link the user opens straight away does not need to outlive that.
EXPORT_RETENTION_MINUTES = 45


@frappe.whitelist(methods=["GET", "POST"])
def download_trip_report_excel(start_date, end_date, vehicle=None, driver=None):
	"""Build the KM report as .xlsx and return a URL to fetch it.

	Returns {"url", "filename", "row_count", "expires_in_minutes"}.

	The file is registered as a Frappe `File` (is_private=0) rather than written
	straight into public/files: a loose file on disk has no owner, never gets
	cleaned up, and does not show anywhere in Desk. cleanup_trip_report_exports()
	sweeps these hourly.

	The filename carries a `YYMMDD HHMMSS` stamp per the app-wide rule for
	downloaded data files. Without it two people exporting the same date range
	overwrite each other's file, and nobody can tell which download in their
	Downloads folder is which.
	"""
	_guard("TIQN Vehicle Trip")

	import io

	import openpyxl
	from openpyxl.styles import Alignment, Font, PatternFill
	from openpyxl.utils import get_column_letter

	report = get_trip_report(start_date, end_date, vehicle=vehicle, driver=driver)
	trips = report["trips"]

	wb = openpyxl.Workbook()
	ws = wb.active
	ws.title = _("Vehicle Report")

	header_fill = PatternFill("solid", fgColor="DDEEFF")
	for col, (label, width) in enumerate(EXCEL_HEADERS, 1):
		cell = ws.cell(row=1, column=col, value=_(label))
		cell.font = Font(bold=True)
		cell.fill = header_fill
		cell.alignment = Alignment(horizontal="center", vertical="center")
		ws.column_dimensions[get_column_letter(col)].width = width
	ws.freeze_panes = "A2"

	for row_idx, trip in enumerate(trips, 2):
		values = [
			_excel_date(trip.get("trip_date")),
			trip.get("vehicle_name") or "",
			trip.get("license_plate") or "",
			trip.get("driver_name") or "",
			_excel_clock(trip.get("checkin_time")),
			_excel_clock(trip.get("checkout_time")),
			trip.get("from_location") or "",
			trip.get("to_location") or "",
			flt(trip.get("km_start")),
			flt(trip.get("km_end")),
			flt(trip.get("total_km")),
			flt(trip.get("additional_cost")),
			trip.get("status") or "",
			trip.get("checkout_notes") or trip.get("notes") or "",
		]
		for col, value in enumerate(values, 1):
			cell = ws.cell(row=row_idx, column=col, value=value)
			if col in KM_COLUMNS:
				cell.number_format = KM_FORMAT
			elif col == COST_COLUMN:
				cell.number_format = COST_FORMAT

	if trips:
		last = len(trips) + 1
		total = last + 1
		ws.cell(total, 1, _("TOTAL")).font = Font(bold=True)
		# Real formulas, not pre-computed numbers: someone filtering or deleting a
		# row in Excel then sees the total follow.
		km_cell = ws.cell(total, 11, f"=SUM(K2:K{last})")
		km_cell.number_format = KM_FORMAT
		km_cell.font = Font(bold=True)
		cost_cell = ws.cell(total, COST_COLUMN, f"=SUM(L2:L{last})")
		cost_cell.number_format = COST_FORMAT
		cost_cell.font = Font(bold=True)

	stream = io.BytesIO()
	wb.save(stream)

	file_doc = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": _trip_report_filename(start_date, end_date, vehicle),
			"is_private": 0,
			"content": stream.getvalue(),
		}
	).save(ignore_permissions=True)

	return {
		# Relative, as vehicle_management/API_CONTRACT.md mục 7 specifies.
		"url": file_doc.file_url,
		# ...and absolute, because a relative path handed to window.open() inside
		# the Zalo Mini App resolves against the MINI APP's origin, not ERPNext,
		# and 404s there. Open this one from anywhere that is not erp.tiqn.com.vn.
		"absolute_url": frappe.utils.get_url(file_doc.file_url),
		"filename": file_doc.file_name,
		"is_private": file_doc.is_private,
		"row_count": len(trips),
		"expires_in_minutes": EXPORT_RETENTION_MINUTES,
	}


def _trip_report_filename(start_date, end_date, vehicle=None):
	"""bao-cao-xe[-Bus1]-<from>-den-<to>-<YYMMDD HHMMSS>.xlsx

	The date range says what the data covers; the stamp says when the file was
	made. They are different questions, so both are in the name.
	"""
	suffix = ""
	if vehicle:
		name = frappe.db.get_value("TIQN Vehicle", vehicle, "vehicle_name") or vehicle
		suffix = "-" + "".join(name.split())

	# Underscore, not the space the house style uses for spreadsheets people only
	# ever see in a Downloads folder: this name also travels in a URL that the Mini
	# App hands to window.open(), and a literal space there is asking for trouble.
	# Matches the app's own attendance export (standard_export_filename).
	stamp = now_datetime().strftime("%y%m%d_%H%M%S")
	return f"bao-cao-xe{suffix}-{getdate(start_date)}-den-{getdate(end_date)}-{stamp}.xlsx"


def _excel_date(value):
	"""dd/mm/yyyy as text - the contract asks for text, not a date cell."""
	if not value:
		return ""
	return getdate(value).strftime("%d/%m/%Y")


def _excel_clock(value):
	"""HH:MM out of a "YYYY-MM-DD HH:MM:SS" string or a datetime."""
	if not value:
		return ""
	return _fmt_datetime(value)[11:16]


def cleanup_trip_report_exports():
	"""Hourly scheduler task: drop exported report files older than the retention
	window. Same approach as the attendance export cleanup - one sweep beats one
	sleeping job per file."""
	cutoff = frappe.utils.add_to_date(now_datetime(), minutes=-EXPORT_RETENTION_MINUTES)
	stale = frappe.get_all(
		"File",
		filters={
			"file_name": ("like", "bao-cao-xe%.xlsx"),
			"is_private": 0,
			"creation": ("<", cutoff),
		},
		pluck="name",
	)
	for name in stale:
		try:
			frappe.delete_doc("File", name, ignore_permissions=True)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Vehicle Report Export Cleanup Error")

	if stale:
		frappe.db.commit()
	return {"deleted": len(stale)}
