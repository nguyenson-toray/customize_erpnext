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
from datetime import timedelta

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

# Tài xế = một tài khoản Zalo có role=driver và được gán xe. DocType TIQN Driver đã bỏ.
# Zalo user ID phải là số >= 10 chữ số, nếu không validate_id_by_oa... (id_by_oa) và quy
# ước dữ liệu thật sẽ khác nhau - dùng dạng 19 chữ số y như ngoài đời.
driver = frappe.get_doc(
	{
		"doctype": "TIQN Zalo Role Map",
		"zalo_user_id": "9119000000000000001",
		"display_name": "TEST Driver",
		# ⚠ Role Map.phone là fieldtype `Phone`, BẮT BUỘC mã quốc gia - khác
		# TIQN Driver.phone cũ vốn là `Data`. Dạng nội địa "0900..." bị từ chối.
		"phone": "+84-900000000",
		"role": "driver",
		"vehicle": vehicle.name,
	}
).insert()

template = frappe.get_doc(
	{
		"doctype": "TIQN Fixed Trip Schedule",
		"schedule_name": "TEST morning run",
		"trip_name_template": "TEST morning run",
		"days_of_week": "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday",
		# driver để TRỐNG: suy từ xe lúc tạo chuyến. Lịch cố định không giữ bản sao
		# thứ hai của "ai lái xe này" - chính bản sao đó đã mục nát khi đổi tên tài xế.
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
# 🔴 MỘT bản ghi cho một người. Trước 23/09 phải có hai - TIQN Driver + một dòng Role
# Map trỏ về nó - và chúng lệch nhau được (đã lệch thật: 3 tài khoản Zalo cùng trỏ về
# một tài xế). Giờ tài khoản Zalo CHÍNH LÀ tài xế.
user = vm.get_user_by_zalo_id(driver.name)
check("role", user["role"], "driver")
check("zalo_user_id chính là docname", user["zalo_user_id"], driver.name)
check("vehicle", user["vehicle"], vehicle.name)
check("kèm tên xe", user["vehicle_name"], vehicle.vehicle_name)
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
	vehicle=vehicle.name, trip_date=TODAY,
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
# Xe của đối tác: TIQN không theo dõi bảo dưỡng hay hư hỏng, chỉ cần biết dùng được
# hay không. `maintenance` + `broken` cũ gộp thành `not_available` (23/09).
check("not_available", vm.update_vehicle_status(vehicle.name, "not_available")["status"], "not_available")
throws("trạng thái cũ maintenance bị từ chối", vm.update_vehicle_status, vehicle.name, "maintenance")
throws("trạng thái cũ broken bị từ chối", vm.update_vehicle_status, vehicle.name, "broken")
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
# 🔴 KHÔNG còn `km_by_driver`. Chuyến gán theo XE, nên "ai lái" chỉ suy được từ tài xế
# HIỆN TẠI của xe - đúng cho câu hỏi bây giờ, sai cho câu hỏi lúc đó. Tài xế đổi xe là
# lịch sử km bị viết lại, âm thầm. Thà không có con số còn hơn có một con số đổi nghĩa.
check("KHÔNG còn thống kê km theo tài xế", "km_by_driver" in report["summary"], False)
check("km theo XE vẫn còn", report["summary"]["km_by_vehicle"].get("TEST Vehicle"), 38.0)

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


print("\n=== đăng nhập: danh tính Zalo, KHÔNG còn mật khẩu ===")
# 🔴 `verify_driver_login()` đã xoá 23/09 cùng field `password`. Vai trò trả về từ
# `get_user_by_zalo_id()` CHÍNH LÀ đăng nhập. Chốt lại để không ai dựng lại đường thứ hai.
check("verify_driver_login không còn tồn tại", hasattr(vm, "verify_driver_login"), False)
check("hằng số khoá đăng nhập cũng đi theo",
      any(hasattr(vm, n) for n in ("MAX_LOGIN_ATTEMPTS", "LOCKOUT_SECONDS", "RATE_LOGIN")), False)
check("DocType TIQN Driver không còn", frappe.db.exists("DocType", "TIQN Driver"), None)

# Chặn một người: cờ `disabled` trên bản ghi Zalo Role Map.
blocked = frappe.get_doc({
	"doctype": "TIQN Zalo Role Map", "zalo_user_id": "9119000000000000009",
	"display_name": "TEST Bị chặn", "role": "driver", "vehicle": vehicle.name,
}).insert(ignore_permissions=True)
check("chưa chặn -> get_user_by_zalo_id trả vai trò",
      vm.get_user_by_zalo_id(blocked.name)["role"], "driver")
frappe.db.set_value("TIQN Zalo Role Map", blocked.name, "disabled", 1)
# Trả None chứ không trả vai trò kèm cờ: mọi chỗ gọi đã biết xử lý None, còn một cờ
# phụ thì chỉ cần sót MỘT chỗ kiểm là lọt.
check("bị chặn -> coi như chưa map", vm.get_user_by_zalo_id(blocked.name), None)
check("bị chặn -> biến khỏi danh sách tài xế",
      [d for d in vm.get_drivers() if d["name"] == blocked.name], [])
frappe.db.set_value("TIQN Zalo Role Map", blocked.name, "disabled", 0)

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
	vehicle=vehicle.name, trip_date=TODAY,
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
	vehicle=vehicle.name, trip_date=TODAY, depart_time="18:00:00",
)
vm.update_trip(later["name"], status="in_progress", km_start=14600)
vm.update_trip(later["name"], status="completed", km_end=14700)
check(
	"editing an older completed trip still works",
	vm.update_trip(crud_trip["name"], dispatcher_note="edited later")["dispatcher_note"],
	"edited later",
)

fresh = vm.create_trip(vehicle=vehicle.name, trip_date=TODAY)
throws("odometer continuity still guarded", vm.update_trip, fresh["name"], km_start=100)


print("\n=== Phase 1 CRUD: passengers as a JSON array ===")
pax_trip = vm.create_trip(vehicle=vehicle.name, trip_date=TODAY)
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
check("not_available via update_vehicle", vm.update_vehicle(vehicle.name, status="not_available")["status"], "not_available")
check("back to available", vm.update_vehicle(vehicle.name, status="available")["status"], "available")
throws("bogus status", vm.update_vehicle, vehicle.name, status="flying")
throws("in_trip with no running trip", vm.update_vehicle, vehicle.name, status="in_trip")
throws("unknown vehicle", vm.update_vehicle, "TIQN-VEH-NOPE", status="available")

run_trip = vm.create_trip(vehicle=vehicle.name, trip_date=TODAY)
vm.update_trip(run_trip["name"], status="in_progress", km_start=14700)
check("in_trip accepted while a trip runs", vm.update_vehicle(vehicle.name, status="in_trip")["status"], "in_trip")
throws("cannot park a vehicle mid-trip", vm.update_vehicle, vehicle.name, status="not_available")
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
lock_trip = vm.create_trip(vehicle=vehicle.name, trip_date=TODAY)
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
pk = vm.create_trip(vehicle=vehicle.name, trip_date=TODAY)

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
	vehicle=vehicle.name, trip_date=TODAY,
	passengers=[{"name": "Created Pax", "from_location": "Cong 5", "request_id": name_src["name"], "order": 2}],
)
check("create_trip maps the same keys", made["passengers"][0]["from_location"], "Cong 5")
check("create_trip maps request_id", made["passengers"][0]["request_id"], name_src["name"])
check("create_trip keeps the sent order", made["passengers"][0]["order"], 2)


print("\n=== API contract: wire formats ===")
fmt_trip = vm.create_trip(
	vehicle=vehicle.name, trip_date=TODAY,
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
tol = vm.create_trip(vehicle=vehicle.name, trip_date=TODAY)

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
# Đọc vị trí cột từ EXCEL_HEADERS thay vì viết cứng: 3 assert này từng đứt hàng
# loạt chỉ vì chèn thêm cột Purpose, che mất lỗi thật nếu có.
check("số cột khớp EXCEL_HEADERS", _ws.max_column, len(vm.EXCEL_HEADERS))
_km, _cost = vm.TOTAL_KM_COLUMN, vm.COST_COLUMN
check("KM cells are numbers, not text", isinstance(_ws.cell(2, _km).value, (int, float)), True)
check("KM number format", _ws.cell(2, _km).number_format, "#,##0.00")
check("cost number format", _ws.cell(2, _cost).number_format, "#,##0")
check("total row is a real SUM formula", str(_ws.cell(_ws.max_row, _km).value).startswith("=SUM("), True)
check("SUM trỏ đúng cột của chính nó",
      f"=SUM({_x.utils.get_column_letter(_km)}2:" in str(_ws.cell(_ws.max_row, _km).value), True)
check("SUM chi phí trỏ đúng cột của chính nó",
      f"=SUM({_x.utils.get_column_letter(_cost)}2:" in str(_ws.cell(_ws.max_row, _cost).value), True)
check("total row is labelled", _ws.cell(_ws.max_row, 1).value, "TOTAL")

check("an empty range still returns a file",
      vm.download_trip_report_excel("2020-01-01", "2020-01-02")["row_count"], 0)

# 🔴 Endpoint này GHI (tạo File). Frappe rollback mọi request có method "an toàn"
# (GET/HEAD/OPTIONS) trong frappe/app.py sync_database(), và File.on_rollback()
# XOÁ LUÔN file vừa ghi trên đĩa. Kết quả: URL trả về đúng, file đã biến mất trước
# khi response rời server - link 404 mà log không nói gì.
# Sự cố thật 21/09/2026. flags.commit là thứ duy nhất chặn được, nên chốt nó lại.
frappe.local.flags.pop("commit", None)
vm.download_trip_report_excel(add_days(TODAY, -1), TODAY)
check("bật flags.commit để file sống qua một request GET",
      frappe.local.flags.get("commit"), True)


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


print("\n=== chuyến gán theo XE: tài xế suy ra, không lưu ===")
auto_veh = frappe.get_doc({
	"doctype": "TIQN Vehicle", "vehicle_name": "TEST Auto", "license_plate": "98Y-888.88",
	"vehicle_type": "MPV", "capacity": 7, "status": "available",
}).insert()
auto_drv = frappe.get_doc({
	"doctype": "TIQN Zalo Role Map", "zalo_user_id": "9119000000000000002",
	"display_name": "TEST Auto Driver", "role": "driver", "vehicle": auto_veh.name,
}).insert()

# 🔴 `driver` KHÔNG còn là cột trên chuyến - nó là giá trị SUY RA từ xe lúc đọc.
made_auto = vm.create_trip(vehicle=auto_veh.name, trip_date=TODAY)
check("create_trip: tài xế suy từ xe", made_auto["driver"], auto_drv.name)
check("kèm tên để hiển thị", made_auto["driver_name"], "TEST Auto Driver")
check("KHÔNG lưu cột driver trên chuyến",
      "driver" in [c["Field"] for c in frappe.db.sql("DESC `tabTIQN Vehicle Trip`", as_dict=True)],
      False)
check("create_trip không còn nhận tham số driver",
      "driver" in vm.create_trip.__wrapped__.__code__.co_varnames
      if hasattr(vm.create_trip, "__wrapped__") else "driver" in vm.create_trip.__code__.co_varnames,
      False)

check(
	"doc.insert thẳng (form Desk / import) cũng vậy",
	vm.get_trip(frappe.get_doc({
		"doctype": "TIQN Vehicle Trip", "vehicle": auto_veh.name, "trip_date": TODAY,
	}).insert().name)["driver"],
	auto_drv.name,
)
auto_req = vm.create_request(
	employee_name="TEST Auto Req", request_time=add_to_date(now_datetime(), hours=30),
	from_location="A", to_location="B",
)
check(
	"combine_requests_to_trip cũng suy từ xe",
	vm.combine_requests_to_trip(request_names=[auto_req["name"]], vehicle=auto_veh.name,
	                            trip_date=TODAY)["driver"],
	auto_drv.name,
)

# Đổi tài xế của xe -> MỌI chuyến của xe đó đổi theo, kể cả chuyến đã tạo trước đó.
# Đây chính là điều không làm được khi driver là một cột lưu trên từng chuyến.
frappe.db.set_value("TIQN Zalo Role Map", auto_drv.name, "disabled", 1)
thay = frappe.get_doc({
	"doctype": "TIQN Zalo Role Map", "zalo_user_id": "9119000000000000007",
	"display_name": "TEST Thay Ca", "role": "driver", "vehicle": auto_veh.name,
}).insert(ignore_permissions=True)
check("đổi tài xế của xe -> chuyến CŨ cũng đổi theo",
      vm.get_trip(made_auto["name"])["driver"], thay.name)

# Tài xế bị chặn không bao giờ được suy ra.
check("tài xế bị chặn không xuất hiện",
      vm.get_trip(made_auto["name"])["driver"] == auto_drv.name, False)

# "Chuyến của tài xế X" = chuyến của XE mà X lái.
check("get_today_trips_by_driver lọc qua xe",
      all(t["vehicle"] == auto_veh.name for t in vm.get_today_trips_by_driver(thay.name)), True)
check("tài xế chưa có xe -> rỗng, KHÔNG trả hết",
      vm.get_today_trips_by_driver("khong-co-ai-the-nay"), [])

frappe.db.set_value("TIQN Zalo Role Map", thay.name, "disabled", 1)
check("xe không còn tài xế -> driver None, chuyến vẫn tồn tại",
      vm.get_trip(made_auto["name"])["driver"], None)
frappe.db.set_value("TIQN Zalo Role Map", auto_drv.name, "disabled", 0)
frappe.db.set_value("TIQN Zalo Role Map", thay.name, "disabled", 1)


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


print("\n=== get_requests lọc theo nhân viên ===")
mine = [
	vm.create_request(
		employee_name="TEST Mine", employee_id_display="EMP-MINE",
		request_time=add_to_date(now_datetime(), hours=40 + i),
		from_location="A", to_location="B",
	)["name"]
	for i in range(2)
]
other = vm.create_request(
	employee_name="TEST Other", employee_id_display="EMP-OTHER",
	request_time=add_to_date(now_datetime(), hours=45),
	from_location="A", to_location="B",
)["name"]

got = vm.get_requests(employee_id="EMP-MINE", limit=0)
check("chỉ trả yêu cầu của mã đó", sorted(r["name"] for r in got), sorted(mine))
check("không lẫn của người khác", other in [r["name"] for r in got], False)
check("cách viết employee_id_display cũng nhận",
      sorted(r["name"] for r in vm.get_requests(employee_id_display="EMP-MINE", limit=0)), sorted(mine))
check("kết hợp với status",
      [r["name"] for r in vm.get_requests(status="pending", employee_id="EMP-MINE", limit=0)], sorted(mine))
check("mã không tồn tại -> rỗng, KHÔNG trả hết",
      vm.get_requests(employee_id="EMP-KHONG-TON-TAI", limit=0), [])
check("không truyền -> vẫn là hàng đợi đầy đủ (dispatcher không đổi)",
      len(vm.get_requests(limit=0)) > len(got), True)
# Khoá tên field trả về: Mini App đọc employee_id_display, không phải employee_id.
check("key mã NV trong payload", "employee_id_display" in got[0], True)
check("KHÔNG có key employee_id", "employee_id" in got[0], False)


print("\n=== purpose trên chuyến (Mini App tách khỏi notes) ===")
p_reqs = [
	vm.create_request(
		employee_name=f"TEST Purpose {i}", employee_id_display="EMP-PUR",
		request_time=add_to_date(now_datetime(), hours=60 + i),
		from_location="A", to_location="B", purpose=text,
	)["name"]
	# Trùng nhau cố ý ở 2 dòng đầu + 1 dòng rỗng: gộp phải khử trùng và bỏ rỗng.
	for i, text in enumerate(["Khám sức khỏe", "khám sức khỏe", "", "Nộp hồ sơ"])
]
combined = vm.combine_requests_to_trip(p_reqs, vehicle=vehicle.name)
check("gộp purpose từ các yêu cầu, khử trùng + bỏ rỗng",
      combined["purpose"], "Khám sức khỏe | Nộp hồ sơ")
check("purpose có trong payload chuyến", "purpose" in combined, True)
check("gộp yêu cầu -> status assigned, KHÔNG phải approved",
      frappe.db.get_value("TIQN Vehicle Request", p_reqs[0], "status"), "assigned")

# Dispatcher tự gõ thì giữ nguyên, không bị ghi đè bởi bản gộp.
typed = vm.combine_requests_to_trip(
	[vm.create_request(
		employee_name="TEST Purpose Own", employee_id_display="EMP-PUR",
		request_time=add_to_date(now_datetime(), hours=70),
		from_location="A", to_location="B", purpose="Việc của yêu cầu",
	)["name"]],
	vehicle=vehicle.name, purpose="Việc dispatcher gõ",
)
check("purpose dispatcher gõ thắng bản gộp", typed["purpose"], "Việc dispatcher gõ")

made = vm.create_trip(vehicle=vehicle.name, trip_date=TODAY, purpose="Đi sân bay")
check("create_trip lưu purpose", made["purpose"], "Đi sân bay")
check("update_trip sửa được purpose",
      vm.update_trip(made["name"], purpose="Đổi ý")["purpose"], "Đổi ý")
check("get_trip trả purpose", vm.get_trip(made["name"])["purpose"], "Đổi ý")
check("purpose có trong get_trips", "purpose" in vm.get_trips(limit=1)[0], True)
check("purpose có trong get_today_trips_by_driver",
      "purpose" in vm.get_today_trips_by_driver(made["driver"])[0], True)
# purpose là LÝ DO chuyến, notes là ghi chú tự do - đừng để cái này ghi đè cái kia.
check("purpose không đụng vào notes",
      frappe.db.get_value("TIQN Vehicle Trip", made["name"], "notes"), None)

print("\n=== is_leader + zalo_user_id ===")
frappe.db.set_value("TIQN Zalo Role Map", driver.name, "is_leader", 1)
listed = next(d for d in vm.get_drivers() if d["name"] == driver.name)
check("get_drivers trả is_leader", listed["is_leader"], 1)
# Danh sách tài xế đọc được bằng API key dùng chung -> không phát tán Zalo ID ở đây.
check("get_drivers KHÔNG lộ zalo_user_id", "zalo_user_id" in listed, False)

# zalo_user_id của tài xế CHÍNH LÀ docname - không còn field rời để lệch nhau.
trip_row = vm.get_today_trips_by_driver(driver.name)[0]
check("chuyến kèm zalo của tài xế để openChat",
      trip_row["driver_zalo_user_id"], driver.name)

# 🔴 Ghi zalo_user_id cho driver/dispatcher là thao tác vô nghĩa (docname LÀ id) nên bị
# từ chối kèm giải thích, thay vì im lặng chấp nhận một lời gọi không làm gì.
throws("update_zalo_user_id cho driver bị từ chối",
       vm.update_zalo_user_id, "driver", driver.name, "9119000000000000003")
throws("update_zalo_user_id cho dispatcher cũng vậy",
       vm.update_zalo_user_id, "dispatcher", driver.name, "9119000000000000003")
req_for_zalo = vm.create_request(
	employee_name="TEST Zalo", employee_id_display="EMP-ZALO",
	request_time=add_to_date(now_datetime(), hours=80),
	from_location="A", to_location="B",
)["name"]
vm.update_request(req_for_zalo, status="approved")
check("ghi được cả khi yêu cầu đã duyệt (db_set, không chạy lại validate)",
      vm.update_zalo_user_id("requester", req_for_zalo, "zalo-req")["zalo_user_id"], "zalo-req")
# `role` là dữ liệu client gửi lên; chỉ 3 vai được ánh xạ, phần còn lại phải bị chặn.
throws("role lạ bị từ chối", vm.update_zalo_user_id, "User", driver.name, "x")
throws("doctype tùy ý bị từ chối", vm.update_zalo_user_id, "Sales Invoice", driver.name, "x")
throws("zalo id rỗng bị từ chối", vm.update_zalo_user_id, "driver", driver.name, "   ")
throws("doc không tồn tại bị từ chối", vm.update_zalo_user_id, "driver", "KHONG-CO", "x")

print("\n=== báo cáo: biển số đi kèm số km ===")
rep = vm.get_trip_report(TODAY, TODAY)
check("summary có nhánh vehicles", "vehicles" in rep["summary"], True)
check("km_by_vehicle giữ nguyên hình dạng cũ",
      isinstance(rep["summary"]["km_by_vehicle"], dict), True)
if rep["summary"]["vehicles"]:
	first = rep["summary"]["vehicles"][0]
	check("mỗi dòng xe có biển số", set(first) >= {"vehicle", "name", "license_plate", "km", "trips"}, True)
	check("sắp giảm dần theo km",
	      [v["km"] for v in rep["summary"]["vehicles"]],
	      sorted((v["km"] for v in rep["summary"]["vehicles"]), reverse=True))

# Cột Excel phải bám theo EXCEL_HEADERS, không phải số viết cứng: thêm 1 cột mà
# quên sửa hằng số là công thức tổng cộng nhầm cột, im lặng.
labels = [label for label, _w in vm.EXCEL_HEADERS]
check("Excel có cột Purpose", "Purpose" in labels, True)
check("TOTAL_KM_COLUMN bám theo header",
      vm.TOTAL_KM_COLUMN, labels.index("Billable KM") + 1)
check("COST_COLUMN bám theo header", vm.COST_COLUMN, labels.index("Additional Cost") + 1)
check("KM_COLUMNS bám theo header", list(vm.KM_COLUMNS),
      [labels.index(x) + 1 for x in ("KM Start", "KM End", "Billable KM")])


print("\n=== decode_phone_token (Zalo getPhoneNumber) ===")
# Chuẩn hoá số: chỉ tin chữ số, và LUÔN trả kèm dạng nội địa.
# ⚠ Lý do đổi từ 23/09: `Role Map.phone` là fieldtype `Phone` nên CHỈ lưu được dạng có
# mã quốc gia ("+84-..."). `phone_local` giờ dùng để HIỂN THỊ và BẤM GỌI, không còn để
# đối chiếu với field đã lưu.
for raw, want in [
	("84962200089", ("+84-962200089", "0962200089")),
	("0962200089", ("+84-962200089", "0962200089")),
	("962200089", ("+84-962200089", "0962200089")),
	("+84 962 200 089", ("+84-962200089", "0962200089")),
]:
	check(f"chuẩn hoá {raw}", vm._format_zalo_phone(raw), want)
throws("số không có chữ số nào bị từ chối", vm._format_zalo_phone, "khong-phai-so")

# Không có khoá trong site_config thì phải NÓI RÕ là thiếu cấu hình, chứ không gửi
# một chuỗi placeholder sang Zalo rồi trả về lỗi chung chung.
_real_conf_get = frappe.conf.get
frappe.conf["zalo_app_vehicle_management_secret_key"] = None
throws("thiếu zalo_app_vehicle_management_secret_key -> báo rõ", vm.decode_phone_token, "tok", "acc")
frappe.conf["zalo_app_vehicle_management_secret_key"] = "test-secret"

throws("thiếu phone_token bị từ chối", vm.decode_phone_token, "", "acc")
throws("thiếu access_token bị từ chối", vm.decode_phone_token, "tok", "")

import requests as _rq

class _Resp:
	def __init__(self, payload):
		self._p = payload
	def json(self):
		return self._p

_calls = []
_real_get = _rq.get

def _fake_get(url, headers=None, timeout=None, **kw):
	_calls.append({"url": url, "headers": headers, "timeout": timeout})
	return _Resp(_fake_get.payload)

_fake_get.payload = {"error": 0, "message": "Success", "data": {"number": "84962200089"}}
_rq.get = _fake_get
try:
	out = vm.decode_phone_token("tok-123", "acc-456")
	check("trả đúng định dạng Mini App yêu cầu", out["phone"], "+84-962200089")
	check("kèm dạng nội địa để hiển thị / bấm gọi", out["phone_local"], "0962200089")
	check("không lưu khi không truyền zalo_user_id", out["saved_to"], None)
	check("gọi đúng endpoint Zalo", _calls[-1]["url"], vm.ZALO_GRAPH_PHONE_URL)
	check("gửi đủ 3 header Zalo cần",
	      sorted(_calls[-1]["headers"]), ["access_token", "code", "secret_key"])
	# 🔴 Request không timeout giữ worker tới mốc SIGKILL 120s của gunicorn.
	check("CÓ timeout", _calls[-1]["timeout"], vm.ZALO_TIMEOUT_SECONDS)

	# Zalo từ chối token -> báo lại nguyên văn message của Zalo (an toàn: nói về
	# token, không nói về secret key của mình).
	_fake_get.payload = {"error": -201, "message": "Invalid code", "data": {}}
	throws("Zalo trả lỗi -> throw kèm message của Zalo", vm.decode_phone_token, "tok", "acc")

	# Bảng mã lỗi chính thức: docs.zaloplatforms.com/docs/MA/api/errorCode
	# Điều quan trọng nhất mà message gốc của Zalo KHÔNG nói: lỗi của AI.
	# 116/117/118 = cấu hình server (mò trong Mini App là vô ích)
	# 114/115/119/-1401 = token hoặc quyền (đổi khoá là vô ích)
	def zalo_says(code, message):
		_fake_get.payload = {"error": code, "message": message, "data": {}}
		try:
			vm.decode_phone_token("tok", "acc")
			return "KHÔNG THROW"
		except Exception as e:
			return str(e)

	m = zalo_says(117, "secret_key is invalid")
	check("117 -> chỉ đúng vào khoá của SERVER", "zalo_app_vehicle_management_secret_key" in m, True)
	check("117 -> KHÔNG đổ cho phone token", "phone token" in m.lower(), False)
	check("117 -> giữ nguyên mã gốc của Zalo để tra cứu", "117" in m, True)

	m = zalo_says(116, "secret_key is empty")
	check("116 -> báo thiếu khoá trong site_config", "site_config.json" in m, True)

	# 🔴 118 đọc như lỗi token ("code is invalid") nhưng THỰC RA là khoá đúng của SAI
	# ứng dụng. Nếu để nguyên văn Zalo, người đọc sẽ đi lùng Mini App.
	m = zalo_says(118, "code is invalid")
	check("118 -> nói rõ là SAI ỨNG DỤNG, không phải token hỏng",
	      "DIFFERENT Zalo app" in m, True)

	m = zalo_says(119, "code has already been used")
	check("119 -> bảo lấy token mới thay vì thử lại", "getPhoneNumber()" in m, True)
	check("119 -> KHÔNG đổ cho khoá của server", "zalo_app_vehicle_management_secret_key" in m, False)

	m = zalo_says(-1401, "User Authentication Required")
	check("-1401 -> là chuyện cấp quyền của user", "authorise" in m, True)

    # Mã lạ: chuyển nguyên văn lời Zalo, không bịa nguyên nhân.
	m = zalo_says(-2000, "Unknown error")
	check("mã chưa map -> chuyển nguyên văn lời Zalo", "Unknown error" in m, True)

	# 🔴 Bảng thông điệp phải là CHUỖI THƯỜNG, không phải _() gọi ở cấp module:
	# _() lúc import đóng băng ngôn ngữ của worker cho mọi request về sau.
	check("bảng lỗi lưu chuỗi thường, dịch lúc dùng",
	      all(isinstance(v, str) for v in
	          list(vm.ZALO_SERVER_CONFIG_ERRORS.values()) + list(vm.ZALO_CALLER_ERRORS.values())),
	      True)

	_fake_get.payload = {"error": 0, "message": "Success", "data": {}}
	throws("Zalo trả rỗng -> throw", vm.decode_phone_token, "tok", "acc")

	_fake_get.payload = {"error": 0, "message": "Success", "data": {"number": "84962200089"}}
	throws("zalo_user_id chưa có trong Role Map -> throw",
	       vm.decode_phone_token, "tok", "acc", "khong-co-trong-map")

	frappe.get_doc({
		"doctype": "TIQN Zalo Role Map",
		"zalo_user_id": "zalo-test-map",
		"display_name": "TEST Map",
		# role=driver đòi `vehicle` (TIQNZaloRoleMap.validate) - gán luôn xe test, để
		# bản ghi này giống thật chứ không né luật.
		"role": "driver",
		"vehicle": vehicle.name,
	}).insert(ignore_permissions=True)
	out = vm.decode_phone_token("tok", "acc", "zalo-test-map")
	check("lưu thẳng vào Role Map", out["saved_to"], "zalo-test-map")
	check("số đã nằm trong DB",
	      frappe.db.get_value("TIQN Zalo Role Map", "zalo-test-map", "phone"), "+84-962200089")
	check("get_user_by_zalo_id trả kèm phone",
	      vm.get_user_by_zalo_id("zalo-test-map")["phone"], "+84-962200089")
finally:
	_rq.get = _real_get
	frappe.conf["zalo_app_vehicle_management_secret_key"] = None

# 🔴 Endpoint này GHI và gọi ra ngoài -> chỉ POST. Cho GET là bị rollback y hệt
# sự cố Excel 21/09: ghi xong rồi mất, không báo lỗi.
check("chỉ nhận POST", frappe.allowed_http_methods_for_whitelisted_func.get(
      vm.decode_phone_token), ["POST"])
# Excel là bản sửa của chính sự cố đó, nên chốt luôn: nó CÓ cho GET, và phải bù
# bằng flags.commit (assert ở mục "Excel export"). Hai hàm, hai cách xử lý, cùng
# một cái bẫy.
check("download_trip_report_excel vẫn cho GET (tương thích ngược)",
      "GET" in frappe.allowed_http_methods_for_whitelisted_func.get(
          vm.download_trip_report_excel), True)


print("\n=== get_vehicle (Mini App vẫn gọi, trước nay chưa hề có) ===")
one = vm.get_vehicle(vehicle.name)
check("trả đúng xe", one["name"], vehicle.name)
check("có image (thẻ xe cần)", "image" in one, True)
# Dựng trên get_vehicles() nên không thể lệch nhau; current_trip là giá trị TÍNH,
# không lưu, nên fetch doc thẳng sẽ thiếu nó.
check("có current_trip như một dòng của get_vehicles", "current_trip" in one, True)
check("cùng hình dạng với get_vehicles",
      sorted(one), sorted(next(v for v in vm.get_vehicles() if v["name"] == vehicle.name)))
throws("xe không tồn tại -> throw, không trả None lặng lẽ", vm.get_vehicle, "KHONG-CO-XE")


print("\n=== scheduler: 1 lịch hỏng KHÔNG được kéo cả đội xe theo ===")
# Sự cố 21/09: đổi tên tài xế xong, cả 6 lịch cố định trỏ tới TIQN-DRV-00x-old.
# Vòng lặp không bắt lỗi nên dòng đầu ném ra ngoài và KHÔNG chuyến nào được tạo.
broken = frappe.new_doc("TIQN Fixed Trip Schedule")
broken.update({
	"schedule_name": "TEST lịch hỏng", "vehicle": vehicle.name,
	"depart_time": "05:05:00", "from_location": "A", "to_location": "B",
	"is_active": 1, "days_of_week": "",
})
broken.insert(ignore_permissions=True)
# Link chết chỉ dựng được bằng db_set - insert sẽ chặn, đó chính là điều đang test.
frappe.db.set_value("TIQN Fixed Trip Schedule", broken.name, "vehicle",
                    "TIQN-VEH-KHONG-TON-TAI", update_modified=False)

good = frappe.new_doc("TIQN Fixed Trip Schedule")
good.update({
	"schedule_name": "TEST lịch tốt", "vehicle": vehicle.name,
	"depart_time": "05:06:00", "from_location": "A", "to_location": "B",
	"is_active": 1, "days_of_week": "",
})
good.insert(ignore_permissions=True)

sched_day = add_days(TODAY, 9)
out = vm.create_scheduled_trips(trip_date=sched_day, force_all=True)
check("lịch hỏng bị ghi nhận là failed", broken.name in out["failed"], True)
check("lịch tốt VẪN được tạo", any(
	frappe.db.get_value("TIQN Vehicle Trip", t, "depart_time") == timedelta(hours=5, minutes=6)
	for t in out["created"]), True)
# Savepoint chứ không phải rollback trần: chuyến tạo TRƯỚC dòng hỏng phải còn.
check("chuyến tạo trước dòng hỏng không bị cuốn theo",
      frappe.db.count("TIQN Vehicle Trip", {"trip_date": sched_day}) >= len(out["created"]), True)


print("\n=== id_by_oa: ID mở chat, KHÁC zalo_user_id ===")
disp = frappe.get_doc({
	"doctype": "TIQN Zalo Role Map",
	"zalo_user_id": "zalo-dispatcher-test",
	"display_name": "TEST Điều hành",
	"role": "dispatcher",
}).insert(ignore_permissions=True)

# 🔴 Chưa có id_by_oa thì bản ghi này KHÔNG được chọn, và tuyệt đối không được rơi
# về zalo_user_id: id app-scoped trông y như một id hợp lệ nhưng openChat() không mở
# được, nên nút chat "có mà bấm không ra gì" - lỗi không ai tái hiện nổi.
# ⚠ KHÔNG assert `is None`: site thật có thể đã có dispatcher khác (đúng là đang có),
# và một assert neo vào dữ liệu production sẽ đỏ vì lý do chẳng liên quan gì.
check("chưa có id_by_oa -> KHÔNG rơi về zalo_user_id của chính nó",
      vm.get_dispatcher_zalo_id() == disp.zalo_user_id, False)

check("update_zalo_id_by_oa ghi được",
      vm.update_zalo_id_by_oa("zalo-dispatcher-test", " 4295057266797901281 ")["id_by_oa"], "4295057266797901281")
check("ghi thật xuống DB",
      frappe.db.get_value("TIQN Zalo Role Map", disp.name, "id_by_oa"), "4295057266797901281")
# Bản ghi vừa ghi id_by_oa là mới nhất theo `modified` nên nó phải thắng.
check("có id_by_oa rồi -> dispatcher_zalo_id trả ID CỦA OA",
      vm.get_dispatcher_zalo_id(), "4295057266797901281")
check("và KHÁC zalo_user_id", vm.get_dispatcher_zalo_id() == disp.zalo_user_id, False)
check("get_user_by_zalo_id trả cả hai",
      [vm.get_user_by_zalo_id("zalo-dispatcher-test")[k] for k in ("zalo_user_id", "id_by_oa")],
      ["zalo-dispatcher-test", "4295057266797901281"])

throws("thiếu id_by_oa bị từ chối", vm.update_zalo_id_by_oa, "zalo-dispatcher-test", "  ")
throws("zalo_user_id không có trong map bị từ chối",
       vm.update_zalo_id_by_oa, "khong-co", "1450193930627209791")

# Tài xế CHÍNH LÀ bản ghi Role Map, nên id_by_oa nằm ngay trên đó - không còn hai bản
# ghi để lệch nhau như thời `driver_ref`.
frappe.db.set_value("TIQN Zalo Role Map", driver.name, "id_by_oa", "7664780689128284452")
trip_row = vm.get_today_trips_by_driver(driver.name)[0]
check("chuyến kèm driver_zalo_id_by_oa", trip_row["driver_zalo_id_by_oa"], "7664780689128284452")
check("vẫn giữ driver_zalo_user_id (hai thứ khác nhau)",
      trip_row["driver_zalo_user_id"], driver.name)

# Tài xế chưa có id_by_oa thì phải là None, không được mượn tạm id của ai khác.
other_drv = frappe.get_doc({
	"doctype": "TIQN Zalo Role Map", "zalo_user_id": "9119000000000000004",
	"display_name": "TEST Chưa map", "role": "driver", "vehicle": vehicle.name,
}).insert(ignore_permissions=True)
# Xe test đang có `driver` (tạo trước) nên nó thắng theo creation asc; `other_drv` chỉ
# để chứng minh tài xế KHÔNG có id_by_oa thì trả None chứ không mượn của ai.
frappe.db.set_value("TIQN Zalo Role Map", driver.name, "disabled", 1)
t_unmapped = vm.create_trip(vehicle=vehicle.name, trip_date=TODAY)
check("tài xế chưa map -> driver_zalo_id_by_oa None",
      vm.get_trip(t_unmapped["name"])["driver_zalo_id_by_oa"], None)
check("vẫn có tài xế (xe luôn có người)", bool(vm.get_trip(t_unmapped["name"])["driver"]), True)
frappe.db.set_value("TIQN Zalo Role Map", driver.name, "disabled", 0)


print("\n=== luật trạng thái khi TẠO phải nằm ở controller, không chỉ ở endpoint ===")
# 🔴 Sự cố 22/09: POST thẳng /api/resource/TIQN Vehicle Trip tạo được chuyến ĐÃ
# `completed` với 999.998 km và 50.000.000đ. Bảng ALLOWED_TRANSITIONS chỉ gác UPDATE
# (không có dòng cũ để so), còn create_trip() thì Mini App có thể đi vòng qua bằng
# REST - key nằm sẵn trong client. TIQN trả tiền theo km thực tế nên đây chính là
# chứng từ thanh toán.
def new_trip_doc(status):
	d = frappe.new_doc("TIQN Vehicle Trip")
	d.update({"vehicle": vehicle.name, "driver": driver.name, "trip_date": TODAY,
	          "depart_time": "04:04:00", "from_location": "A", "to_location": "B",
	          "status": status})
	return d

throws("insert thẳng doc ở trạng thái completed bị chặn",
       lambda: new_trip_doc("completed").insert(ignore_permissions=True))
throws("insert thẳng doc ở trạng thái in_progress bị chặn",
       lambda: new_trip_doc("in_progress").insert(ignore_permissions=True))
throws("insert thẳng doc ở trạng thái cancelled bị chặn",
       lambda: new_trip_doc("cancelled").insert(ignore_permissions=True))
for ok_status in ("scheduled", "confirmed"):
	d = new_trip_doc(ok_status)
	d.insert(ignore_permissions=True)
	check(f"vẫn tạo được ở trạng thái {ok_status}", d.status, ok_status)

# Cờ dành cho CODE SERVER ghi lại lịch sử (seeder, backfill). Client không đặt được:
# nó chỉ gửi field, không gửi flags.
back = new_trip_doc("completed")
back.km_start, back.km_end = 10, 30
back.flags.allow_backdated_status = True
back.insert(ignore_permissions=True)
check("cờ allow_backdated_status cho phép ghi lịch sử", back.status, "completed")
check("và vẫn tính total_km như thường", back.total_km, 20.0)

# Luật phải giống hệt ở endpoint - hai đường, một luật.
throws("create_trip cũng từ chối trạng thái cuối",
       lambda: vm.create_trip(vehicle=vehicle.name, trip_date=TODAY, status="completed"))


print("\n=== rate limit trên 3 endpoint đáng bị lạm dụng ===")
_limited = frappe.rate_limiter  # module, để đọc lại decorator đã gắn
# verify_driver_login đã xoá cùng RATE_LOGIN (23/09) - còn hai endpoint.
for fn, want in ((vm.decode_phone_token, vm.RATE_PHONE_DECODE),
                 (vm.download_trip_report_excel, vm.RATE_EXCEL)):
	# Decorator bọc hàm nên hàm gốc nằm ở __wrapped__; có nó nghĩa là đã gắn.
	check(f"{fn.__name__} có rate limit", hasattr(fn, "__wrapped__"), True)
	check(f"{fn.__name__} có hạn mức > 0", want > 0, True)

# 🔴 site_config["rate_limit"] KHÔNG phải bộ đếm request và KHÔNG theo IP: nó khoá
# trên f"rate-limit-counter-{window}" (không có danh tính) và cộng MICRO-GIÂY thời
# gian xử lý của CẢ SITE. Bật nó = cả công ty cùng bị 429, kể cả điều hành trên Desk.
# Chốt lại để không ai "bật rate limit" bằng cách đó.
check("KHÔNG dùng site_config rate_limit toàn site",
      frappe.conf.get("rate_limit"), None)
# Hạn mức phải rộng tay: Mini App chạy trong webview điện thoại, cả một cell 4G có
# thể ra cùng MỘT địa chỉ NAT của nhà mạng.
check("hạn mức decode SĐT đủ rộng", vm.RATE_PHONE_DECODE >= 30, True)


print("\n=== nội dung yêu cầu phải ĐÓNG BĂNG ở controller, không chỉ ở endpoint ===")
# 🔴 Đo 22/09 bằng chính API key của Mini App: PUT /api/resource/... đổi được
# from_location của một yêu cầu ĐÃ XẾP XE. Tài xế bị gửi tới nhầm chỗ, không lỗi,
# không dấu vết. update_request() chặn; REST thì không. Luật chỉ sống ở một endpoint
# thì không phải là luật.
froz = vm.create_request(
	employee_name="TEST Đóng băng", employee_id_display="EMP-FRZ",
	request_time=add_to_date(now_datetime(), hours=90),
	from_location="Điểm A", to_location="Điểm B", purpose="Việc gốc",
)["name"]

d = frappe.get_doc("TIQN Vehicle Request", froz)
d.from_location = "Sửa lúc còn pending"
d.save(ignore_permissions=True)
check("còn pending thì sửa thoải mái", d.from_location, "Sửa lúc còn pending")

vm.update_request(froz, status="approved")
for field, value in (("from_location", "Đổi lén"), ("request_time", add_to_date(now_datetime(), hours=99)),
                     ("purpose", "Việc khác"), ("passenger_count", 9)):
	doc = frappe.get_doc("TIQN Vehicle Request", froz)
	doc.set(field, value)
	throws(f"đã duyệt -> KHÔNG sửa được {field} (kể cả qua doc.save)",
	       doc.save, ignore_permissions=True)

# Field quy trình thì vẫn phải chạy được, nếu không thì điều hành bị khoá cứng.
doc = frappe.get_doc("TIQN Vehicle Request", froz)
doc.status = "rejected"
doc.rejection_reason = "Không còn xe"
doc.save(ignore_permissions=True)
check("field quy trình vẫn đổi được sau khi duyệt", doc.status, "rejected")

# Lưu lại mà KHÔNG đổi gì thì không được báo lỗi - nếu không, mọi thao tác
# db-level hay save() thường lệ trên yêu cầu cũ đều gãy.
doc = frappe.get_doc("TIQN Vehicle Request", froz)
doc.save(ignore_permissions=True)
check("save không đổi gì vẫn chạy bình thường", doc.status, "rejected")


print("\n=== id_by_oa phải trông như một Zalo ID ===")
# 🔴 Sự cố 22/09: dòng dispatcher được lưu với id_by_oa = "34". Không null ⇒
# get_dispatcher_zalo_id() trả về nó ⇒ Mini App HIỆN nút chat ⇒ bấm không ra gì.
# Đúng cái hỏng im lặng mà luật "không fallback" sinh ra để tránh, chỉ khác là lần
# này giá trị xấu đến từ DỮ LIỆU chứ không từ code.
def role_map(zid, oa):
	d = frappe.new_doc("TIQN Zalo Role Map")
	d.update({"zalo_user_id": zid, "display_name": "TEST OA", "role": "requester", "id_by_oa": oa})
	return d

throws("id_by_oa = '34' bị chặn", lambda: role_map("zid-oa-1", "34").insert(ignore_permissions=True))
throws("id_by_oa có chữ bị chặn", lambda: role_map("zid-oa-2", "abc1234567").insert(ignore_permissions=True))
throws("id_by_oa lẫn dấu cách giữa bị chặn",
       lambda: role_map("zid-oa-3", "123 456 7890").insert(ignore_permissions=True))

good = role_map("zid-oa-4", " 4295057266797901281 ")
good.insert(ignore_permissions=True)
check("ID thật 19 chữ số vẫn nhận", good.id_by_oa, "4295057266797901281")
check("cắt khoảng trắng thừa", " " in (good.id_by_oa or ""), False)

blank = role_map("zid-oa-5", "")
blank.insert(ignore_permissions=True)
check("để trống vẫn hợp lệ (chưa map là chuyện bình thường)", blank.id_by_oa, None)

# Luật nằm ở controller nên đường REST cũng dính - cùng nguyên tắc với hai lỗ đã vá.
doc = frappe.get_doc("TIQN Zalo Role Map", good.name)
doc.id_by_oa = "7"
throws("sửa thành giá trị rác cũng bị chặn", doc.save, ignore_permissions=True)


print("\n=== chuyến cố định chỉ sinh ra trước giờ đi 15 phút ===")
# 🔴 Luật cũ so CHUỖI HH:MM chính xác với lúc cron chạy. Cron ở "30 6" và "0 17",
# lịch chiều đi lúc 17:15 ⇒ ba chuyến chiều CHƯA TỪNG được tạo, mỗi ngày làm việc,
# và không có gì trong log vì lịch không khớp chỉ bị đếm là "not_due".
sched_v = frappe.get_doc({
	"doctype": "TIQN Vehicle", "vehicle_name": "TEST Lead", "license_plate": "99Y-111.11",
	"vehicle_type": "MPV", "capacity": 7, "status": "available",
}).insert()

def make_schedule(minutes_from_now, tag):
	depart = add_to_date(now_datetime(), minutes=minutes_from_now)
	d = frappe.new_doc("TIQN Fixed Trip Schedule")
	d.update({
		"schedule_name": f"TEST {tag}", "vehicle": sched_v.name, "driver": driver.name,
		"depart_time": depart.strftime("%H:%M:00"), "from_location": "A", "to_location": "B",
		"is_active": 1, "days_of_week": "",
	})
	d.insert(ignore_permissions=True)
	return d.name

soon   = make_schedule(8,   "trong cửa sổ")      # còn 8 phút  -> phải tạo
edge   = make_schedule(14,  "sát mép")           # còn 14 phút -> phải tạo
far    = make_schedule(90,  "còn xa")            # còn 90 phút -> CHƯA tạo
past   = make_schedule(-30, "đã qua giờ")        # qua 30 phút -> KHÔNG tạo nữa

out = vm.create_scheduled_trips()
check("lịch còn 8 phút -> tạo", soon in out["created"] or any(
	frappe.db.get_value("TIQN Vehicle Trip", t, "template_id") == soon for t in out["created"]), True)
check("lịch còn 14 phút (sát mép 15) -> tạo", any(
	frappe.db.get_value("TIQN Vehicle Trip", t, "template_id") == edge for t in out["created"]), True)
check("lịch còn 90 phút -> CHƯA tạo", far in out["not_due"], True)
check("lịch đã qua giờ -> không tạo", past in out["not_due"], True)
check("ngưỡng đúng bằng 15 phút", vm.SCHEDULE_LEAD_MINUTES, 15)

# Gọi lại trong cùng cửa sổ không được nhân đôi.
again = vm.create_scheduled_trips()
check("chạy lại -> bỏ qua, không tạo trùng", len(again["created"]), 0)
check("và được đếm là skipped", edge in again["skipped"], True)

# force_all vẫn bỏ qua cửa sổ, dành cho chạy bù thủ công.
forced = vm.create_scheduled_trips(force_all=True)
check("force_all tạo cả lịch còn xa", any(
	frappe.db.get_value("TIQN Vehicle Trip", t, "template_id") == far for t in forced["created"]), True)

# 🔴 Chốt: cron phải là tick ngắn, KHÔNG phải giờ cố định. Giờ cố định thì cron time
# và depart_time phải khớp tay mãi mãi, lệch một phút là im lặng mất chuyến.
import customize_erpnext.hooks as _hooks
_cron = _hooks.scheduler_events["cron"]
_sched_crons = [k for k, v in _cron.items()
                if any("create_scheduled_trips" in f for f in v)]
check("chỉ còn MỘT mục cron cho chuyến cố định", len(_sched_crons), 1)
check("và nó là tick định kỳ, không phải giờ cố định",
      _sched_crons[0].startswith("*/"), True)

# 🔴 Luật tổng quát, áp cho TOÀN BỘ hooks: Frappe khoá `Scheduled Job Type` theo
# `method` (core/doctype/scheduled_job_type: `db.exists(..., {"method": event})`),
# nên KHAI MỘT METHOD DƯỚI HAI CRON THÌ CHỈ MỘT CÁI SỐNG SÓT - cái sau ghi đè cái
# trước, không lỗi, không cảnh báo. Đúng chuyện đã xảy ra: "30 6" bị "0 17" nuốt.
from collections import defaultdict as _dd
_seen = _dd(list)
for _expr, _methods in _cron.items():
	for _m in _methods:
		_seen[_m].append(_expr)
_dups = {m: e for m, e in _seen.items() if len(e) > 1}
check("KHÔNG method nào khai dưới nhiều cron (cái sau nuốt cái trước)", _dups, {})

# Và DB phải khớp hooks: `bench restart` KHÔNG đồng bộ bảng này, chỉ `bench migrate`.
_db = {r.method: r.cron_format for r in frappe.get_all(
	"Scheduled Job Type", filters={"frequency": "Cron"}, fields=["method", "cron_format"],
	limit_page_length=0)}
_lech = {m: (e, _db.get(m)) for m, e in _seen.items() if _db.get(m) not in e}
check("Scheduled Job Type trong DB khớp hooks.py", _lech, {})


print("\n=== tên chuyến: chỉ lộ trình, KHÔNG ngày giờ ===")
auto = vm.create_trip(vehicle=vehicle.name, trip_date=TODAY, depart_time="09:45:00",
                      from_location="Toray VSIP", to_location="Sân bay Chu Lai")
check("tên = lộ trình thôi", auto["trip_name"], "Toray VSIP → Sân bay Chu Lai")
# Giờ và ngày đã có cột riêng và luôn hiện cạnh tên ở mọi chỗ - nhét vào tên chỉ làm
# tiêu đề dài tới mức bị cắt trên điện thoại.
check("không có giờ trong tên", "09:45" in auto["trip_name"], False)
check("không có ngày trong tên", str(TODAY) in auto["trip_name"], False)

# Tên do người dùng đặt thì giữ nguyên, không bị dựng lại.
named = vm.create_trip(vehicle=vehicle.name, trip_date=TODAY, trip_name="Đưa giám đốc",
                       from_location="A", to_location="B")
check("tên tự đặt được giữ nguyên", named["trip_name"], "Đưa giám đốc")

# Thiếu địa điểm thì vẫn phải có tên, không để rỗng.
bare = vm.create_trip(vehicle=vehicle.name, trip_date=TODAY)
check("thiếu địa điểm -> vẫn có tên", bool(bare["trip_name"]), True)

# 🔴 trip_name là cột Data = 140 ký tự. Chuyến gộp có thể mang nhiều điểm đến nối lại,
# nên lộ trình dài chạm trần - vượt trần là INSERT GÃY chứ không tự cắt.
long_trip = vm.create_trip(vehicle=vehicle.name, trip_date=TODAY,
                           from_location="X" * 100, to_location="Y" * 100)
check("lộ trình quá dài -> cắt, không gãy", len(long_trip["trip_name"]) <= 140, True)
check("và có dấu ba chấm cho biết đã cắt", long_trip["trip_name"].endswith("…"), True)


print("\n=== chuyến gộp: MỘT điểm đến, phần còn lại vào Dispatcher Note ===")
# 🔴 Mini App từng nối nhiều điểm đến vào to_location ("A | B"). Field đó bị so khớp,
# lọc và gom nhóm trong báo cáo, nên "A | B" thành MỘT địa điểm không hề tồn tại.
multi = [
	vm.create_request(
		employee_name=f"TEST Đa điểm {i}", employee_id_display="EMP-MULTI",
		request_time=add_to_date(now_datetime(), hours=100 + i),
		from_location="Toray VSIP", to_location=dest, purpose=f"Việc {i}",
	)["name"]
	# Trùng lặp cố ý ở dòng 3: khử trùng, không liệt kê hai lần.
	for i, dest in enumerate(["Sân bay Chu Lai", "Ga Quảng Ngãi", "sân bay chu lai", "Cảng Dung Quất"])
]
t = vm.combine_requests_to_trip(multi, vehicle=vehicle.name)
check("to_location = điểm đến của yêu cầu ĐẦU TIÊN", t["to_location"], "Sân bay Chu Lai")
check("KHÔNG nối nhiều nơi vào to_location", "|" in t["to_location"], False)
check("các điểm còn lại nằm trong dispatcher_note",
      t["dispatcher_note"], "Ghé thêm: Ga Quảng Ngãi, Cảng Dung Quất")
check("khử trùng không phân biệt hoa thường",
      t["dispatcher_note"].count("Chu Lai"), 0)

# Dispatcher gõ ghi chú riêng thì cả hai cùng có, điểm đến đứng trước.
t2 = vm.combine_requests_to_trip(
	[vm.create_request(
		employee_name="TEST Ghi chú", employee_id_display="EMP-MULTI",
		request_time=add_to_date(now_datetime(), hours=110),
		from_location="Toray VSIP", to_location="Ga Quảng Ngãi",
	)["name"], multi[0] if False else vm.create_request(
		employee_name="TEST Ghi chú 2", employee_id_display="EMP-MULTI",
		request_time=add_to_date(now_datetime(), hours=111),
		from_location="Toray VSIP", to_location="Cảng Dung Quất",
	)["name"]],
	vehicle=vehicle.name, dispatcher_note="Nhớ mang giấy tờ",
)
check("điểm đến đứng TRƯỚC ghi chú của dispatcher",
      t2["dispatcher_note"], "Ghé thêm: Cảng Dung Quất\nNhớ mang giấy tờ")

# Tất cả cùng một nơi -> không sinh dòng thừa.
same = [
	vm.create_request(
		employee_name=f"TEST Cùng nơi {i}", employee_id_display="EMP-MULTI",
		request_time=add_to_date(now_datetime(), hours=120 + i),
		from_location="Toray VSIP", to_location="Sân bay Chu Lai",
	)["name"]
	for i in range(2)
]
t3 = vm.combine_requests_to_trip(same, vehicle=vehicle.name)
check("cùng một điểm đến -> dispatcher_note rỗng", t3["dispatcher_note"], None)
t4 = vm.combine_requests_to_trip(
	[vm.create_request(
		employee_name="TEST Chỉ ghi chú", employee_id_display="EMP-MULTI",
		request_time=add_to_date(now_datetime(), hours=130),
		from_location="Toray VSIP", to_location="Sân bay Chu Lai",
	)["name"]],
	vehicle=vehicle.name, dispatcher_note="Chỉ ghi chú",
)
check("không có điểm phụ -> chỉ còn ghi chú", t4["dispatcher_note"], "Chỉ ghi chú")

# Hành khách vẫn mang điểm ĐÓN của từng người - đó là lý do không cần bảng stops.
check("mỗi hành khách vẫn có điểm đón riêng",
      all(p["from_location"] for p in vm.get_trip(t["name"])["passengers"]), True)

print("\n=== bảng stops đã bỏ hẳn ===")
check("DocType TIQN Trip Stop không còn", frappe.db.exists("DocType", "TIQN Trip Stop"), None)
check("bảng mồ côi đã drop",
      bool(frappe.db.sql("SHOW TABLES LIKE 'tabTIQN Trip Stop'")), False)
check("payload chuyến KHÔNG còn khoá stops", "stops" in vm.get_trip(t["name"]), False)
# Client cũ còn gửi `stops` thì Frappe lặng lẽ bỏ qua, không được gãy.
check("create_trip bỏ qua tham số stops cũ, không lỗi",
      bool(vm.create_trip(vehicle=vehicle.name, trip_date=TODAY,
                          from_location="A", to_location="B")["name"]), True)


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
