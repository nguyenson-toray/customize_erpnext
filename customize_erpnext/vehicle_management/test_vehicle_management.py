"""End-to-end check of the TIQN Vehicle Management API.

Exercises the whole dispatcher + driver flow against the real site and then
rolls the transaction back, so nothing is left behind.

Run:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    exec(open('../apps/customize_erpnext/customize_erpnext/vehicle_management/test_vehicle_management.py').read())"

Teardown is `frappe.db.rollback()` and nothing else. Do NOT add a cleanup that
deletes `tabSeries` rows: dropping a naming series row is what stopped HR from
saving new Leave Applications in August 2026.
"""

import re

import frappe
from frappe.utils import add_days, add_to_date, flt, getdate, now_datetime, nowdate

import customize_erpnext.api.vehicle_management as vm

ok = fail = 0
TODAY = nowdate()

# 🔴 NOTHING in this script may commit. `create_scheduled_trips()` calls
# frappe.db.commit() because it is a scheduler task - correct in production, fatal
# here: one commit flushes the WHOLE open transaction, so the rollback at the end
# has nothing left to undo and every TEST record stays in the real database.
# That happened once (25 trips, 7 requests, 3 drivers and a vehicle had to be
# deleted by hand). The guard is global rather than wrapped around one section so
# that a future test calling another committing function cannot reintroduce it.
_REAL_COMMIT = frappe.db.commit
frappe.db.commit = lambda *a, **k: None


def check(label, got, want):
	global ok, fail
	if got == want:
		ok += 1
		print(f"  ok   {label}")
	else:
		fail += 1
		print(f"  FAIL {label}: got {got!r}, want {want!r}")


def throws(label, fn, *args, **kwargs):
	global ok, fail
	try:
		fn(*args, **kwargs)
	except Exception as e:  # noqa: BLE001 - we only care that it refused
		ok += 1
		print(f"  ok   {label} (refused: {str(e)[:70]})")
		return
	fail += 1
	print(f"  FAIL {label}: expected a refusal, got none")


print("\n=== fixtures ===")
vehicle = frappe.get_doc(
	{
		"doctype": "TIQN Vehicle",
		"vehicle_name": "TEST Vehicle",
		"license_plate": "99Z-999.99",
		"vehicle_type": "MPV",
		"capacity": 7,
		"status": "available",
	}
).insert()

driver = frappe.get_doc(
	{
		"doctype": "TIQN Driver",
		"driver_name": "TEST Driver",
		"phone": "0900000000",
		"assigned_vehicle": vehicle.name,
		"zalo_user_id": "zalo_test_driver",
		"is_active": 1,
	}
).insert()

frappe.get_doc(
	{
		"doctype": "TIQN Zalo Role Map",
		"zalo_user_id": "zalo_test_driver",
		"display_name": "TEST Driver",
		"role": "driver",
		"driver_ref": driver.name,
	}
).insert()

template = frappe.get_doc(
	{
		"doctype": "TIQN Fixed Trip Schedule",
		"schedule_name": "TEST morning run",
		"trip_name_template": "TEST morning run",
		"days_of_week": "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday",
		"driver": driver.name,
		"vehicle": vehicle.name,
		"depart_time": "06:30:00",
		"from_location": "TEST Vincom",
		"to_location": "TEST Toray",
		"trip_number": 1,
		"is_active": 1,
	}
).insert()
print(f"  vehicle={vehicle.name} driver={driver.name} template={template.name}")


print("\n=== 3.1 get_user_by_zalo_id ===")
user = vm.get_user_by_zalo_id("zalo_test_driver")
check("role", user["role"], "driver")
check("driver_id", user["driver_id"], driver.name)
check("vehicle_id", user["vehicle_id"], vehicle.name)
check("unknown id returns None", vm.get_user_by_zalo_id("nobody_at_all"), None)


print("\n=== 3.2 request lifecycle ===")
req = vm.create_request(
	employee_name="TEST Employee",
	employee_id_display="TEST001",
	zalo_user_id="zalo_test_emp",
	request_time=add_to_date(now_datetime(), hours=2),
	from_location="TEST Toray",
	to_location="TEST UBND",
	purpose="Meeting",
	passenger_count=2,
)
check("new request is pending", req["status"], "pending")
check("submit_time filled", bool(req["submit_time"]), True)
check("my requests", [r.name for r in vm.get_my_requests("zalo_test_emp")], [req["name"]])

throws("reject without a reason", vm.reject_request, req["name"])
check("approve", vm.approve_request(req["name"])["status"], "approved")
throws("approve twice", vm.approve_request, req["name"])

rejected = vm.create_request(
	employee_name="TEST Rejected",
	request_time=add_to_date(now_datetime(), hours=3),
	from_location="A",
	to_location="B",
)
out = vm.reject_request(rejected["name"], "No vehicle free")
check("rejected status", out["status"], "rejected")
check("rejection reason kept", out["rejection_reason"], "No vehicle free")
throws("assign a rejected request", vm.assign_request_to_trip, rejected["name"], "x")


print("\n=== 3.3 fixed trip from template (idempotent) ===")
templates = vm.get_fixed_templates_for_driver(driver.name, TODAY)
check("schedule listed", templates[0]["name"], template.name)
check("no trip yet", templates[0]["trip_created_today"], False)

trip = vm.create_trip_from_template(template.name, TODAY)
check("created confirmed", trip["status"], "confirmed")
check("trip_type fixed", trip["trip_type"], "fixed")
check("template_id set", trip["template_id"], template.name)
check("vehicle from template", trip["vehicle"], vehicle.name)

again = vm.create_trip_from_template(template.name, TODAY)
check("second call is idempotent", again["name"], trip["name"])
check(
	"only one trip exists",
	frappe.db.count("TIQN Vehicle Trip", {"template_id": template.name, "trip_date": TODAY}),
	1,
)
check("schedule now flagged", vm.get_fixed_templates_for_driver(driver.name, TODAY)[0]["trip_created_today"], True)


print("\n=== 3.3 check in / check out ===")
throws("check in with km_start = 0", vm.checkin_trip, trip["name"], 0)

checked_in = vm.checkin_trip(
	trip["name"], km_start=14500, start_gps_lat=15.1194, start_gps_lng=108.7922, checkin_notes="OK"
)
check("status in_progress", checked_in["status"], "in_progress")
check("checkin_time set", bool(checked_in["checkin_time"]), True)
check("vehicle now in_trip", frappe.db.get_value("TIQN Vehicle", vehicle.name, "status"), "in_trip")
check("gps stored", checked_in["start_gps_lat"], 15.1194)

throws("check in twice", vm.checkin_trip, trip["name"], 14600)
throws("check out below km_start", vm.checkout_trip, trip["name"], 14400)

done = vm.checkout_trip(trip["name"], km_end=14538, additional_cost=50000, checkout_notes="Done")
check("status completed", done["status"], "completed")
check("total_km computed", done["total_km"], 38.0)
check("vehicle released", frappe.db.get_value("TIQN Vehicle", vehicle.name, "status"), "available")

last = vm.get_last_completed_trip_by_vehicle(vehicle.name, TODAY)
check("last completed trip found", last["name"], trip["name"])


print("\n=== 3.3 odometer continuity across trips ===")
trip2 = vm.create_trip(
	vehicle=vehicle.name, driver=driver.name, trip_date=TODAY,
	depart_time="09:00:00", from_location="TEST Toray", to_location="TEST Port",
)
throws("km_start below previous km_end", vm.checkin_trip, trip2["name"], 14000)
check("km_start at previous km_end is fine", vm.checkin_trip(trip2["name"], 14538)["status"], "in_progress")


print("\n=== 3.3 route change + acknowledge ===")
changed = vm.update_trip_route(trip2["name"], to_location="TEST Airport", dispatcher_note="Pick up guest")
check("to_location updated", changed["to_location"], "TEST Airport")
check("route_changed raised while running", changed["route_changed"], 1)
check("acknowledged clears the flag", vm.acknowledge_route_change(trip2["name"])["route_changed"], 0)

vm.cancel_trip(trip2["name"], "Test cleanup")
check("cancelled", frappe.db.get_value("TIQN Vehicle Trip", trip2["name"], "status"), "cancelled")
throws("check in a cancelled trip", vm.checkin_trip, trip2["name"], 15000)


print("\n=== 3.2 combine requests ===")
combined = vm.combine_requests_to_trip(
	request_names=[req["name"]],
	vehicle=vehicle.name,
	driver=driver.name,
	trip_date=TODAY,
	depart_time="14:00:00",
)
check("one passenger row", len(combined["passengers"]), 1)
check("passenger links the request", combined["passengers"][0]["request_id"], req["name"])
check("request became assigned", frappe.db.get_value("TIQN Vehicle Request", req["name"], "status"), "assigned")
check(
	"assigned_trip back-linked",
	frappe.db.get_value("TIQN Vehicle Request", req["name"], "assigned_trip"),
	combined["name"],
)
throws("assign an already assigned request", vm.assign_request_to_trip, req["name"], combined["name"])

vm.cancel_trip(combined["name"], "Test cleanup")
check(
	"cancelling the trip frees the request",
	frappe.db.get_value("TIQN Vehicle Request", req["name"], "status"),
	"approved",
)


print("\n=== 3.4 vehicle status guard ===")
throws("in_trip cannot be set by hand", vm.update_vehicle_status, vehicle.name, "in_trip")
check("maintenance", vm.update_vehicle_status(vehicle.name, "maintenance")["status"], "maintenance")
check("back to available", vm.update_vehicle_status(vehicle.name, "available")["status"], "available")


print("\n=== combinable detection ===")
base = add_to_date(now_datetime(), days=1)
rows = [
	{"name": "R1", "from_location": "Toray", "to_location": "UBND", "request_time": base},
	{"name": "R2", "from_location": "toray ", "to_location": " UBND", "request_time": add_to_date(base, minutes=20)},
	{"name": "R3", "from_location": "Toray", "to_location": "UBND", "request_time": add_to_date(base, minutes=200)},
	{"name": "R4", "from_location": "Toray", "to_location": "Airport", "request_time": base},
]
groups = vm.find_combinable_requests(rows)
check("one group found", len(groups), 1)
check("group holds the two near-in-time rows", sorted(groups[0]), ["R1", "R2"])


print("\n=== 3.5 reports ===")
# Scoped to the TEST vehicle, never to absolute counts: get_today_stats() sees the
# whole fleet, so the demo dataset (or a real trip someone logs today) would break
# a hard-coded number for reasons that have nothing to do with the code.
from collections import Counter as _Counter

_mine = _Counter(t["status"] for t in vm.get_trips(date=TODAY, vehicle=vehicle.name, limit=0))
check("this vehicle's cancelled trips today", _mine["cancelled"], 2)
check("this vehicle's completed trips today", _mine["completed"], 1)

stats = vm.get_today_stats(TODAY)
check("fleet stats include them", stats["cancelled"] >= 2 and stats["completed"] >= 1, True)
check("stats carry every status key",
      sorted(k for k in stats if k not in ("date", "total", "pending")),
      ["cancelled", "completed", "confirmed", "in_progress", "scheduled"])

report = vm.get_trip_report(add_days(TODAY, -1), TODAY, vehicle=vehicle.name)
check("report totals km of completed trip", report["summary"]["total_km"], 38.0)
check("km_by_vehicle keyed by name", report["summary"]["km_by_vehicle"].get("TEST Vehicle"), 38.0)
check("km_by_driver keyed by name", report["summary"]["km_by_driver"].get("TEST Driver"), 38.0)

overview = vm.get_dispatch_overview(TODAY)
check("overview carries every panel", sorted(overview.keys()),
      ["combinable", "date", "drivers", "pending_requests", "stats", "trips", "vehicles"])
# The dispatch page fills the driver in from the vehicle and filters on is_active;
# a field missing from the payload reads as falsy there and nothing ever fills.
check("drivers payload carries is_active", all("is_active" in d for d in overview["drivers"]), True)
check(
	"driver is reachable from its vehicle",
	[d["name"] for d in overview["drivers"] if d["assigned_vehicle"] == vehicle.name and d["is_active"]],
	[driver.name],
)


print("\n=== update_trip field guard ===")
# km_start / km_end ARE writable here from Phase 1 on: the Mini App checks in and
# out through update_trip(). Derived fields stay off limits.
# GPS is Phase 2 per vehicle_management/API_CONTRACT.md: shut out of the generic setter.
throws("GPS is not writable in Phase 1", vm.update_trip, trip["name"], start_gps_lat=1.0)
check(
	"framework args are ignored",
	vm.update_trip(trip["name"], dispatcher_note="note", cmd="x")["dispatcher_note"],
	"note",
)


print("\n=== Phase 1 driver login ===")
driver.password = "test-secret-1"
driver.save()

listed = vm.get_drivers()
me = [d for d in listed if d["name"] == driver.name]
check("active driver is listed", len(me), 1)
check("no password field in the list", "password" in me[0], False)
check("no zalo id in the list", "zalo_user_id" in me[0], False)
check("vehicle label built", me[0]["assigned_vehicle_name"], "TEST Vehicle \u2022 99Z-999.99")

logged_in = vm.verify_driver_login(driver.name, "test-secret-1")
check("login returns the driver", logged_in["name"], driver.name)
check("login returns the vehicle", logged_in["assigned_vehicle_name"], "TEST Vehicle")
check("login returns the plate", logged_in["assigned_vehicle_plate"], "99Z-999.99")
check("login never returns the password", "password" in logged_in, False)

throws("wrong password", vm.verify_driver_login, driver.name, "wrong")
throws("empty password", vm.verify_driver_login, driver.name, "")
throws("unknown driver", vm.verify_driver_login, "TIQN-DRV-NOPE", "test-secret-1")
vm._clear_failed_logins(driver.name)

# Brute-force guard: the 6th attempt must be refused even with the right password.
for _i in range(vm.MAX_LOGIN_ATTEMPTS):
	try:
		vm.verify_driver_login(driver.name, "wrong")
	except Exception:
		pass
throws("locked out after 5 failures", vm.verify_driver_login, driver.name, "test-secret-1")
vm._clear_failed_logins(driver.name)
check("lockout clears", vm.verify_driver_login(driver.name, "test-secret-1")["name"], driver.name)

# A driver with no password set must not fall through to "any password works".
no_pwd = frappe.get_doc(
	{"doctype": "TIQN Driver", "driver_name": "TEST No Password", "is_active": 1}
).insert()
throws("driver without a password", vm.verify_driver_login, no_pwd.name, "anything")

inactive = frappe.get_doc(
	{"doctype": "TIQN Driver", "driver_name": "TEST Inactive", "is_active": 0}
).insert()
inactive.password = "x"
inactive.save()
throws("inactive driver", vm.verify_driver_login, inactive.name, "x")
check(
	"inactive driver hidden from the picker",
	[d for d in vm.get_drivers() if d["name"] == inactive.name],
	[],
)

check(
	"column stores only asterisks",
	set(frappe.db.get_value("TIQN Driver", driver.name, "password") or ""),
	{"*"},
)


print("\n=== Phase 1 CRUD: update_request ===")
crud_req = vm.create_request(
	employee_name="TEST CRUD",
	request_time=add_to_date(now_datetime(), hours=4),
	from_location="TEST Toray",
	to_location="TEST Port",
)
# employee_name IS editable now (content field); submit_time never is.
throws("non-editable field on a request", vm.update_request, crud_req["name"], submit_time=now_datetime())
throws("vehicle-only arg on a request", vm.update_request, crud_req["name"], current_trip="TIQN-TRIP-X")
throws("assigned without a trip", vm.update_request, crud_req["name"], status="assigned")

crud_trip = vm.create_trip(
	vehicle=vehicle.name, driver=driver.name, trip_date=TODAY,
	depart_time="15:00:00", from_location="TEST Toray", to_location="TEST Port",
)
# The Phase 1 flow has no separate approval: pending jumps straight to assigned.
out = vm.update_request(crud_req["name"], status="assigned", assigned_trip=crud_trip["name"])
check("pending -> assigned in one step", out["status"], "assigned")
check("assigned_trip stored", out["assigned_trip"], crud_trip["name"])
throws("assigned is terminal", vm.update_request, crud_req["name"], status="pending")

reject_me = vm.create_request(
	employee_name="TEST CRUD reject",
	request_time=add_to_date(now_datetime(), hours=5),
	from_location="A", to_location="B",
)
throws("reject without a reason", vm.update_request, reject_me["name"], status="rejected")
out = vm.update_request(reject_me["name"], status="rejected", rejection_reason="No vehicle")
check("rejected via update_request", out["status"], "rejected")
check("reason stored", out["rejection_reason"], "No vehicle")
check(
	"framework args are dropped",
	vm.update_request(reject_me["name"], cmd="x")["status"],
	"rejected",
)
check(
	"notes is a real field on both Request and Trip now",
	("notes" in vm.REQUEST_EDITABLE_FIELDS, "notes" in vm.TRIP_EDITABLE_FIELDS,
	 "notes" in vm.IGNORED_TRIP_ARGS),
	(True, True, False),
)
check(
	"the only trip args still dropped are the Phase 2 GPS spellings",
	all("gps" in k.lower().replace("_", "") for k in vm.IGNORED_TRIP_ARGS),
	True,
)


print("\n=== Phase 1 CRUD: update_trip drives check in / check out ===")
throws("unknown field on a trip", vm.update_trip, crud_trip["name"], template_id="forged")
throws("total_km is derived, not writable", vm.update_trip, crud_trip["name"], total_km=999)

started = vm.update_trip(crud_trip["name"], status="in_progress", km_start=14538)
check("status in_progress", started["status"], "in_progress")
check("checkin_time stamped automatically", bool(started["checkin_time"]), True)
check("vehicle flipped to in_trip", frappe.db.get_value("TIQN Vehicle", vehicle.name, "status"), "in_trip")

throws("km_end below km_start", vm.update_trip, crud_trip["name"], km_end=14000)
throws("cannot go back to scheduled", vm.update_trip, crud_trip["name"], status="scheduled")

finished = vm.update_trip(
	crud_trip["name"], status="completed", km_end=14600, checkout_notes="via update_trip"
)
check("status completed", finished["status"], "completed")
check("checkout_time stamped automatically", bool(finished["checkout_time"]), True)
check("total_km recomputed", finished["total_km"], 62.0)
check("vehicle released", frappe.db.get_value("TIQN Vehicle", vehicle.name, "status"), "available")

# Re-saving a finished trip must not trip the odometer rule just because a later
# trip on the same vehicle has since logged a higher KM End.
later = vm.create_trip(
	vehicle=vehicle.name, driver=driver.name, trip_date=TODAY, depart_time="18:00:00",
)
vm.update_trip(later["name"], status="in_progress", km_start=14600)
vm.update_trip(later["name"], status="completed", km_end=14700)
check(
	"editing an older completed trip still works",
	vm.update_trip(crud_trip["name"], dispatcher_note="edited later")["dispatcher_note"],
	"edited later",
)

fresh = vm.create_trip(vehicle=vehicle.name, driver=driver.name, trip_date=TODAY)
throws("odometer continuity still guarded", vm.update_trip, fresh["name"], km_start=100)


print("\n=== Phase 1 CRUD: passengers as a JSON array ===")
pax_trip = vm.create_trip(vehicle=vehicle.name, driver=driver.name, trip_date=TODAY)
updated = vm.update_trip(
	pax_trip["name"],
	passengers=[
		{"requestId": crud_req["name"], "name": "Pax One", "fromLocation": "Gate A", "order": 2},
		{"name": "Pax Two", "fromLocation": "Gate B", "order": 1},
	],
)
check("two passenger rows written", len(updated["passengers"]), 2)
check("rows come back ordered", [p["passenger_name"] for p in updated["passengers"]], ["Pax Two", "Pax One"])
check("camelCase requestId mapped", updated["passengers"][1]["request_id"], crud_req["name"])
check("camelCase fromLocation mapped", updated["passengers"][1]["from_location"], "Gate A")
check(
	"a second push replaces rather than appends",
	len(vm.update_trip(pax_trip["name"], passengers=[{"name": "Only One"}])["passengers"]),
	1,
)


print("\n=== Phase 1 CRUD: update_vehicle ===")
check("maintenance via update_vehicle", vm.update_vehicle(vehicle.name, status="maintenance")["status"], "maintenance")
check("back to available", vm.update_vehicle(vehicle.name, status="available")["status"], "available")
throws("bogus status", vm.update_vehicle, vehicle.name, status="flying")
throws("in_trip with no running trip", vm.update_vehicle, vehicle.name, status="in_trip")
throws("unknown vehicle", vm.update_vehicle, "TIQN-VEH-NOPE", status="available")

run_trip = vm.create_trip(vehicle=vehicle.name, driver=driver.name, trip_date=TODAY)
vm.update_trip(run_trip["name"], status="in_progress", km_start=14700)
check("in_trip accepted while a trip runs", vm.update_vehicle(vehicle.name, status="in_trip")["status"], "in_trip")
throws("cannot park a vehicle mid-trip", vm.update_vehicle, vehicle.name, status="maintenance")
vm.cancel_trip(run_trip["name"], "test")


print("\n=== content fields: editable only while pending ===")
editable = vm.create_request(
	employee_name="TEST Editable",
	request_time=add_to_date(now_datetime(), hours=6),
	from_location="Old From",
	to_location="Old To",
	return_time=add_to_date(now_datetime(), hours=9),
	notes="first note",
	passenger_count=2,
)
check("return_time stored on create", bool(editable["return_time"]), True)
check("notes stored on create", editable["notes"], "first note")

out = vm.update_request(
	editable["name"],
	from_location="New From",
	to_location="New To",
	purpose="New purpose",
	passenger_count=4,
	notes="second note",
	employee_name="Renamed",
	employee_id_display="EMP999",
	zalo_user_id="zalo_new",
)
check("from_location edited while pending", out["from_location"], "New From")
check("to_location edited", out["to_location"], "New To")
check("purpose edited", out["purpose"], "New purpose")
check("passenger_count edited", out["passenger_count"], 4)
check("notes edited - NOT swallowed as a legacy arg", out["notes"], "second note")
check("employee_name edited", out["employee_name"], "Renamed")
check("employee_id_display edited", out["employee_id_display"], "EMP999")
check("zalo_user_id edited", out["zalo_user_id"], "zalo_new")

later = add_to_date(now_datetime(), hours=10)
check("request_time and return_time edited", bool(vm.update_request(
	editable["name"], request_time=add_to_date(now_datetime(), hours=7), return_time=later
)["return_time"]), True)
throws(
	"return_time before request_time",
	vm.update_request, editable["name"], return_time=add_to_date(now_datetime(), hours=1),
)

# Once a dispatcher has acted on it, the ride details freeze.
lock_trip = vm.create_trip(vehicle=vehicle.name, driver=driver.name, trip_date=TODAY)
vm.update_request(editable["name"], status="assigned", assigned_trip=lock_trip["name"])
throws("content locked once assigned", vm.update_request, editable["name"], from_location="Hijacked")
throws("notes locked too", vm.update_request, editable["name"], notes="sneaky")
check(
	"from_location really unchanged",
	frappe.db.get_value("TIQN Vehicle Request", editable["name"], "from_location"),
	"New From",
)


print("\n=== status cancelled ===")
check("cancelled is a valid option",
      "cancelled" in (frappe.get_meta("TIQN Vehicle Request").get_field("status").options or "").split("\n"),
      True)

# Workflow fields stay open: an assigned ride can still be called off.
check("assigned -> cancelled", vm.update_request(editable["name"], status="cancelled")["status"], "cancelled")
throws("cancelled is terminal", vm.update_request, editable["name"], status="pending")
check(
	"a cancelled request is not resurrected when the trip is saved",
	vm.update_trip(lock_trip["name"], dispatcher_note="touched")
	and frappe.db.get_value("TIQN Vehicle Request", editable["name"], "status"),
	"cancelled",
)

pending_cancel = vm.create_request(
	employee_name="TEST Cancel while pending",
	request_time=add_to_date(now_datetime(), hours=8),
	from_location="A", to_location="B",
)
# Same call may edit and cancel: the guard reads the status BEFORE the change.
out = vm.update_request(pending_cancel["name"], notes="changed mind", status="cancelled")
check("edit + cancel in one call", (out["status"], out["notes"]), ("cancelled", "changed mind"))
throws("rejected cannot become cancelled", vm.update_request, reject_me["name"], status="cancelled")


print("\n=== passenger key spellings ===")
name_src = vm.create_request(
	employee_name="Nguoi Yeu Cau",
	request_time=add_to_date(now_datetime(), hours=11),
	from_location="X", to_location="Y",
)
pk = vm.create_trip(vehicle=vehicle.name, driver=driver.name, trip_date=TODAY)

# The exact shape the Mini App sends: snake_case request_id / from_location.
out = vm.update_trip(pk["name"], passengers=[
	{"passenger_name": "Snake Pax", "from_location": "Cong 1", "request_id": name_src["name"], "order": 1},
])
row = out["passengers"][0]
check("request_id mapped", row["request_id"], name_src["name"])
check("from_location mapped", row["from_location"], "Cong 1")
check("order mapped", row["order"], 1)

# camelCase must keep working too.
out = vm.update_trip(pk["name"], passengers=[
	{"name": "Camel Pax", "fromLocation": "Cong 2", "requestId": name_src["name"], "order": 3},
])
row = out["passengers"][0]
check("requestId still mapped", row["request_id"], name_src["name"])
check("fromLocation still mapped", row["from_location"], "Cong 2")
check("bare name used as the person", row["passenger_name"], "Camel Pax")

# passenger_name is reqd=1 on the child table: fill it from the linked request
# rather than letting the save blow up with a raw MandatoryError.
out = vm.update_trip(pk["name"], passengers=[{"request_id": name_src["name"], "from_location": "Cong 3"}])
check("name derived from the request", out["passengers"][0]["passenger_name"], "Nguoi Yeu Cau")
out = vm.update_trip(pk["name"], passengers=[{"passenger_name": "", "request_id": name_src["name"]}])
check("empty name falls back to the request", out["passengers"][0]["passenger_name"], "Nguoi Yeu Cau")

throws("no name and no request", vm.update_trip, pk["name"], passengers=[{"from_location": "Cong 4"}])

# Reading a trip and pushing the same array straight back must not turn the child
# row's docname into a person's name.
roundtrip = vm.get_trip(pk["name"])
out = vm.update_trip(pk["name"], passengers=roundtrip["passengers"])
check("round trip keeps the person's name", out["passengers"][0]["passenger_name"], "Nguoi Yeu Cau")
check("round trip does not leak the docname", out["passengers"][0]["passenger_name"] == roundtrip["passengers"][0]["row_name"], False)

# create_trip used to accept a narrower set than update_trip - now identical.
made = vm.create_trip(
	vehicle=vehicle.name, driver=driver.name, trip_date=TODAY,
	passengers=[{"name": "Created Pax", "from_location": "Cong 5", "request_id": name_src["name"], "order": 2}],
)
check("create_trip maps the same keys", made["passengers"][0]["from_location"], "Cong 5")
check("create_trip maps request_id", made["passengers"][0]["request_id"], name_src["name"])
check("create_trip keeps the sent order", made["passengers"][0]["order"], 2)


print("\n=== API contract: wire formats ===")
fmt_trip = vm.create_trip(
	vehicle=vehicle.name, driver=driver.name, trip_date=TODAY,
	depart_time="06:30:00", from_location="A", to_location="B",
	notes="contract note", status="scheduled",
)
check("depart_time is HH:MM", fmt_trip["depart_time"], "06:30")
check("trip_date is YYYY-MM-DD", fmt_trip["trip_date"], str(getdate(TODAY)))
check("notes is a Trip field now", fmt_trip["notes"], "contract note")
check("vehicle_name fetched", fmt_trip["vehicle_name"], "TEST Vehicle")
check("license_plate fetched", fmt_trip["license_plate"], "99Z-999.99")
check("driver_name fetched", fmt_trip["driver_name"], "TEST Driver")

vm.update_trip(fmt_trip["name"], status="in_progress", km_start=99900)
listed = [t for t in vm.get_trips(date=TODAY, limit=0) if t["name"] == fmt_trip["name"]][0]
check("get_trips also carries vehicle_name", listed["vehicle_name"], "TEST Vehicle")
check("get_trips also carries license_plate", listed["license_plate"], "99Z-999.99")
check("get_trips also carries driver_name", listed["driver_name"], "TEST Driver")
check("get_trips depart_time is HH:MM", listed["depart_time"], "06:30")
check(
	"checkin_time has no microseconds",
	bool(re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", listed["checkin_time"] or "")),
	True,
)
check("no T and no Z in the datetime", ("T" in (listed["checkin_time"] or ""), "Z" in (listed["checkin_time"] or "")), (False, False))

req_fmt = vm.get_request(editable["name"])
check(
	"request_time has no microseconds",
	bool(re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", req_fmt["request_time"] or "")),
	True,
)
check(
	"return_time same format",
	bool(re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", req_fmt["return_time"] or "")),
	True,
)

vm.update_trip(fmt_trip["name"], status="completed", km_end=99950)


print("\n=== API contract: get_vehicle_status ===")
statuses = vm.get_vehicle_status()
mine = [v for v in statuses if v["name"] == vehicle.name][0]
check("carries vehicle_name", mine["vehicle_name"], "TEST Vehicle")
check("carries license_plate", mine["license_plate"], "99Z-999.99")
check("carries a current_trip key", "current_trip" in mine, True)


print("\n=== API contract: create_scheduled_trips ===")
# The six real seeded schedules run most weekdays, so park them for this section
# (the whole script rolls back) and assert only on the TEST schedule.
for other in frappe.get_all("TIQN Fixed Trip Schedule", filters={"name": ("!=", template.name)}, pluck="name"):
	frappe.db.set_value("TIQN Fixed Trip Schedule", other, "is_active", 0)

sched_day = add_days(TODAY, 3)
weekday = vm.WEEKDAY_NAMES[getdate(sched_day).weekday()]
frappe.db.set_value("TIQN Fixed Trip Schedule", template.name, {
	"days_of_week": weekday,
	"trip_name_template": "Ca sang - {vehicle_name}",
})

first = vm.create_scheduled_trips(trip_date=sched_day, force_all=True)
check("one trip created", len(first["created"]), 1)
made_trip = vm.get_trip(first["created"][0])
check("trip_type fixed", made_trip["trip_type"], "fixed")
check("template_id points at the schedule", made_trip["template_id"], template.name)
check("{vehicle_name} substituted", made_trip["trip_name"], "Ca sang - TEST Vehicle")
check("status scheduled", made_trip["status"], "scheduled")

second = vm.create_scheduled_trips(trip_date=sched_day, force_all=True)
check("second run creates nothing", second["created"], [])
check("second run reports it skipped", template.name in second["skipped"], True)

# A day the schedule does not run on must be left alone.
other_day = add_days(sched_day, 1)
third = vm.create_scheduled_trips(trip_date=other_day, force_all=True)
check("wrong weekday is skipped", template.name in third["not_due"], True)

# Without force_all the clock has to match the schedule's depart_time.
frappe.db.set_value("TIQN Fixed Trip Schedule", template.name, "depart_time", "03:07:00")
fourth = vm.create_scheduled_trips(trip_date=add_days(sched_day, 7))
check("off-clock run creates nothing", fourth["created"], [])

frappe.db.set_value("TIQN Fixed Trip Schedule", template.name, "is_active", 0)
fifth = vm.create_scheduled_trips(trip_date=add_days(sched_day, 14), force_all=True)
check("inactive schedule is ignored", template.name not in fifth["created"] + fifth["skipped"], True)

check(
	"create_scheduled_trips is NOT reachable over HTTP",
	vm.create_scheduled_trips in frappe.whitelisted,
	False,
)


print("\n=== Part 1: client tolerance ===")
tol = vm.create_trip(vehicle=vehicle.name, driver=driver.name, trip_date=TODAY)

# A browser's Date.toISOString() must not reach MySQL as-is.
iso = vm.update_trip(tol["name"], status="in_progress", km_start=99960,
                     checkin_time="2026-09-15T07:28:40.415Z")
check("ISO datetime normalised", iso["checkin_time"], "2026-09-15 07:28:40")
check("no T survived", "T" in iso["checkin_time"], False)
check("no Z survived", "Z" in iso["checkin_time"], False)

# GPS keys are Phase 2 and must be DROPPED, never rejected: frappe's scrub()
# turns the Mini App's `startGPS` into `start_g_p_s`.
ok_gps = vm.update_trip(tol["name"], start_g_p_s=None, end_g_p_s=None, checkin_notes="gps ignored")
check("start_g_p_s ignored, not an error", ok_gps["checkin_notes"], "gps ignored")
ok_gps2 = vm.update_trip(tol["name"], startGPS="whatever", checkin_notes="camel gps ignored")
check("startGPS ignored too", ok_gps2["checkin_notes"], "camel gps ignored")
# A Float column reads back 0.0, never None - the point is that nothing was stored.
check("and it really was not written", flt(ok_gps2["start_gps_lat"]), 0.0)

check("vehicle busy while the trip runs",
      frappe.db.get_value("TIQN Vehicle", vehicle.name, "status"), "in_trip")

# Deleting a running trip has to release its vehicle - Frappe does not call
# on_update() on delete, and a stuck "in_trip" was seen for real on Kia.
frappe.delete_doc("TIQN Vehicle Trip", tol["name"], force=True, delete_permanently=True)
check("deleting a running trip frees the vehicle",
      frappe.db.get_value("TIQN Vehicle", vehicle.name, "status"), "available")

# ISO also accepted when creating a request.
iso_req = vm.create_request(
	employee_name="ISO Requester", request_time="2026-09-20T09:00:00.000Z",
	return_time="2026-09-20T12:00:00Z", from_location="A", to_location="B",
)
check("create_request normalises request_time", iso_req["request_time"], "2026-09-20 09:00:00")
check("create_request normalises return_time", iso_req["return_time"], "2026-09-20 12:00:00")


print("\n=== Excel export ===")
xls = vm.download_trip_report_excel(add_days(TODAY, -1), TODAY, vehicle=vehicle.name)
check("returns a url", xls["url"].startswith("/files/bao-cao-xe"), True)
# A relative path handed to window.open() inside the Zalo Mini App resolves
# against the Mini App's own origin and 404s, so an absolute one ships too.
check("returns an absolute url", xls["absolute_url"].endswith(xls["url"]), True)
check("absolute url is a full https url", xls["absolute_url"].startswith("http"), True)
check("file is public, no login needed", xls["is_private"], 0)
check("no space in the url", " " in xls["url"], False)
check("filename carries the vehicle", "TESTVehicle" in xls["filename"], True)
check("filename carries a timestamp", bool(re.search(r"-\d{6}_\d{6}\.xlsx$", xls["filename"])), True)
check("reports how many rows", xls["row_count"] >= 1, True)

import io as _io, openpyxl as _x
_content = frappe.get_doc("File", {"file_name": xls["filename"]}).get_content()
_ws = _x.load_workbook(_io.BytesIO(_content)).active
check("sheet name", _ws.title, "Vehicle Report")
check("header row frozen", _ws.freeze_panes, "A2")
check("14 columns", _ws.max_column, 14)
check("KM cells are numbers, not text", isinstance(_ws.cell(2, 11).value, (int, float)), True)
check("KM number format", _ws.cell(2, 11).number_format, "#,##0.00")
check("cost number format", _ws.cell(2, 12).number_format, "#,##0")
check("total row is a real SUM formula", str(_ws.cell(_ws.max_row, 11).value).startswith("=SUM("), True)
check("total row is labelled", _ws.cell(_ws.max_row, 1).value, "TOTAL")

check("an empty range still returns a file",
      vm.download_trip_report_excel("2020-01-01", "2020-01-02")["row_count"], 0)


print("\n=== Tạo chuyến từ NHIỀU yêu cầu (chế độ 2 của dialog Tạo chuyến) ===")
multi = [
	vm.create_request(
		employee_name=f"TEST Multi {i}",
		request_time=add_to_date(now_datetime(), hours=20 + i),
		from_location="Toray VSIP",
		to_location="San bay Chu Lai",
	)["name"]
	for i in range(3)
]
multi_trip = vm.combine_requests_to_trip(
	request_names=multi,
	vehicle=vehicle.name,
	driver=driver.name,
	trip_date=TODAY,
	depart_time="20:00:00",
	from_location="Toray VSIP",
	to_location="San bay Chu Lai",
)
check("one trip carries all three", len(multi_trip["passengers"]), 3)
check(
	"every request became assigned",
	sorted({frappe.db.get_value("TIQN Vehicle Request", r, "status") for r in multi}),
	["assigned"],
)
check(
	"every request points at that trip",
	sorted({frappe.db.get_value("TIQN Vehicle Request", r, "assigned_trip") for r in multi}),
	[multi_trip["name"]],
)
check(
	"passenger rows keep the requester names",
	sorted(p["passenger_name"] for p in multi_trip["passengers"]),
	["TEST Multi 0", "TEST Multi 1", "TEST Multi 2"],
)
check("route came through", (multi_trip["from_location"], multi_trip["to_location"]),
      ("Toray VSIP", "San bay Chu Lai"))

# Cancelling that one trip has to release all three, not just the first.
vm.cancel_trip(multi_trip["name"], "Test")
check(
	"cancelling frees all three",
	sorted({frappe.db.get_value("TIQN Vehicle Request", r, "status") for r in multi}),
	["approved"],
)


print("\n=== Chọn xe là đủ: tài xế tự điền ở MỌI đường tạo chuyến ===")
auto_veh = frappe.get_doc({
	"doctype": "TIQN Vehicle", "vehicle_name": "TEST Auto", "license_plate": "98Y-888.88",
	"vehicle_type": "MPV", "capacity": 7, "status": "available",
}).insert()
auto_drv = frappe.get_doc({
	"doctype": "TIQN Driver", "driver_name": "TEST Auto Driver",
	"assigned_vehicle": auto_veh.name, "is_active": 1,
}).insert()

check("create_trip bỏ trống driver", vm.create_trip(vehicle=auto_veh.name, trip_date=TODAY)["driver"], auto_drv.name)
check(
	"doc.insert thẳng (form Desk / import)",
	frappe.get_doc({"doctype": "TIQN Vehicle Trip", "vehicle": auto_veh.name, "trip_date": TODAY}).insert().driver,
	auto_drv.name,
)
auto_req = vm.create_request(
	employee_name="TEST Auto Req", request_time=add_to_date(now_datetime(), hours=30),
	from_location="A", to_location="B",
)
check(
	"combine_requests_to_trip bỏ trống driver",
	vm.combine_requests_to_trip(request_names=[auto_req["name"]], vehicle=auto_veh.name, trip_date=TODAY)["driver"],
	auto_drv.name,
)

# A stand-in driver must survive: only a blank is filled.
check(
	"tài xế chạy thay không bị ghi đè",
	vm.create_trip(vehicle=auto_veh.name, driver=driver.name, trip_date=TODAY)["driver"],
	driver.name,
)

# An inactive driver must never be auto-assigned - the trip would go to someone gone.
frappe.db.set_value("TIQN Driver", auto_drv.name, "is_active", 0)
throws(
	"xe chỉ còn tài xế đã nghỉ -> vẫn bắt nhập",
	frappe.get_doc({"doctype": "TIQN Vehicle Trip", "vehicle": auto_veh.name, "trip_date": TODAY}).insert,
)
frappe.db.set_value("TIQN Driver", auto_drv.name, "is_active", 1)


print("\n=== Yêu cầu quá giờ / sắp tới giờ ===")
urgent = {}
for label, minutes in [("late", -40), ("soon", 5), ("normal", 180), ("edge", 10)]:
	urgent[label] = vm.create_request(
		employee_name=f"TEST urgency {label}",
		request_time=add_to_date(now_datetime(), minutes=minutes),
		from_location="Toray VSIP",
		to_location="San bay",
	)["name"]

flagged = {r["name"]: r["minutes_until"] for r in vm.get_dispatch_overview(TODAY)["pending_requests"]}

check("mọi yêu cầu chờ duyệt đều có minutes_until", all(n in flagged for n in urgent.values()), True)
check("quá giờ -> âm", flagged[urgent["late"]] < 0, True)
check("sắp tới giờ -> 0..10", 0 <= flagged[urgent["soon"]] <= vm.DUE_SOON_MINUTES, True)
check("đúng mốc 10 phút vẫn là 'sắp tới'", flagged[urgent["edge"]] <= vm.DUE_SOON_MINUTES, True)
check("còn xa -> ngoài ngưỡng", flagged[urgent["normal"]] > vm.DUE_SOON_MINUTES, True)

# Không có request_time thì không được đoán bừa là quá giờ.
no_time = frappe.get_doc({
	"doctype": "TIQN Vehicle Request", "employee_name": "TEST no time",
	"request_time": None, "from_location": "A", "to_location": "B", "status": "pending",
})
no_time.flags.ignore_mandatory = True
no_time.insert(ignore_mandatory=True)
blank = [r for r in vm.get_dispatch_overview(TODAY)["pending_requests"] if r["name"] == no_time.name]
check("thiếu request_time -> minutes_until = None", blank[0]["minutes_until"] if blank else "missing", None)

# Card yêu cầu hiển thị đủ điểm đi/đến/giờ cho dialog "Từ yêu cầu chờ duyệt".
sample = [r for r in vm.get_dispatch_overview(TODAY)["pending_requests"] if r["name"] == urgent["soon"]][0]
check(
	"payload đủ thông tin cho picker",
	all(sample.get(f) for f in ("employee_name", "from_location", "to_location", "request_time")),
	True,
)


print("\n=== Bẫy đã vấp: MultiCheck gọi on_change chứ không phải onchange ===")
# Không chạy được JS ở đây, nhưng bẫy này im lặng tuyệt đối (không lỗi, chỉ là
# không có gì xảy ra) nên vẫn đáng ghim lại ở mức văn bản: ai đó "sửa chính tả"
# thành `onchange` là tính năng tự điền chết mà không ai biết.
import pathlib as _pathlib

_page_js = _pathlib.Path(frappe.get_app_path(
	"customize_erpnext", "vehicle_management", "page", "vehicle_dispatch", "vehicle_dispatch.js"
)).read_text()
_requests_field = _page_js[_page_js.index("fieldname: 'requests'"):]
_requests_field = _requests_field[: _requests_field.index("sb_veh")]
check("field MultiCheck dùng on_change", "on_change:" in _requests_field, True)
check("và KHÔNG dùng onchange", "onchange:" in _requests_field, False)
check("hàm tự điền tồn tại", "sync_trip_dialog_from_requests" in _page_js, True)
check(
	"tự điền cả 4 ô",
	all(
		f"set_value('{f}'" in _page_js
		for f in ("from_location", "to_location", "trip_date", "depart_time")
	),
	True,
)


frappe.db.commit = _REAL_COMMIT
frappe.db.rollback()

leaked = frappe.db.count("TIQN Vehicle", {"license_plate": "99Z-999.99"})
if leaked:
	fail += 1
	print("  FAIL rollback did not take - TEST records are in the real database")
else:
	ok += 1
	print("  ok   rollback verified: no TEST vehicle left behind")

print(f"\n{'=' * 46}\n{ok} passed, {fail} failed  (transaction rolled back)\n{'=' * 46}")
