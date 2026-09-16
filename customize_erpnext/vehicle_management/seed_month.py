# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Full-month demo dataset for the Vehicle Management module.

    bench --site erp.tiqn.local execute \
        customize_erpnext.vehicle_management.seed_month.execute

    # a different month
    bench --site erp.tiqn.local execute \
        customize_erpnext.vehicle_management.seed_month.execute \
        --kwargs "{'year': 2026, 'month': 10, 'purge': True}"

Shape of the month, per vehicle:
  * 2 fixed shuttle runs every day except Sunday, created from the vehicle's two
    TIQN Fixed Trip Schedule rows (so `template_id` points at a real schedule).
  * 2-4 on-demand trips a day, most of them raised from a TIQN Vehicle Request.

Statuses follow the calendar rather than being sprinkled at random: a day in the
past is finished, today is half-done, tomorrow has not started. That is what makes
the dashboard, the KPI chips and the KM report show believable numbers.

Every state the code can produce appears somewhere in the month - see CASES at the
bottom of execute()'s log for the tally.

DETERMINISTIC: seeded Random, so two runs of the same month produce the same data
and a number quoted in a bug report can be reproduced.

Not whitelisted, no hook: it deletes every trip and request before it starts.
"""

import random
from datetime import timedelta

import frappe
from frappe.utils import add_to_date, flt, get_datetime, getdate, now_datetime

SEED = 20260916

# Odometer each vehicle starts the month on.
START_KM = {"TIQN-VEH-001": 48000, "TIQN-VEH-002": 26000, "TIQN-VEH-003": 28500}

PLACES = [
	"UBND Tỉnh Quảng Ngãi", "Sân bay Chu Lai", "Sân bay Đà Nẵng", "Cảng Dung Quất",
	"KCN Quảng Phú", "BV Đa Khoa Quảng Ngãi", "Sở Lao động", "Cục Thuế Quảng Ngãi",
	"Ngân hàng Vietcombank", "Khách sạn Cẩm Thành", "Ga Quảng Ngãi", "Chi cục Hải quan",
]
PURPOSES = [
	"Họp với UBND", "Đón khách", "Tiễn khách", "Nộp hồ sơ", "Làm thủ tục BHXH",
	"Đi công tác", "Khám sức khoẻ", "Nộp tờ khai thuế", "Giao chứng từ", "Kiểm hàng",
]
EMPLOYEES = [
	("Nguyễn Văn An", "EMP001"), ("Trần Thị Bình", "EMP002"), ("Lê Thị Cúc", "EMP003"),
	("Phạm Văn Dũng", "EMP004"), ("Nguyễn Thị Em", "EMP005"), ("Trần Văn Phúc", "EMP006"),
	("Lê Thị Giang", "EMP007"), ("Võ Văn Hùng", "EMP008"), ("Đặng Thị Kim", "EMP009"),
	("Bùi Văn Lâm", "EMP010"),
]
REJECT_REASONS = [
	"Không có xe trống khung giờ này",
	"Trùng lịch với chuyến ưu tiên",
	"Đề nghị đi chung với chuyến đã có",
]
CANCEL_REASONS = ["Khách hủy đột xuất", "Thay đổi lịch họp", "Mưa lớn, hoãn chuyến"]

HOME = "Toray VSIP Quảng Ngãi"


def execute(year=2026, month=9, purge=True):
	rng = random.Random(SEED)
	_require_masters()

	if purge:
		_purge()

	today = getdate(now_datetime())
	days = _days_in_month(int(year), int(month))
	schedules = _schedules_by_vehicle()
	vehicles = list(START_KM)
	odometer = dict(START_KM)

	stats = {"trips": 0, "requests": 0}
	cases = {}

	def case(name):
		cases[name] = cases.get(name, 0) + 1

	for day in days:
		is_sunday = day.weekday() == 6
		past = day < today
		future = day > today

		for vehicle in vehicles:
			# 🔴 Plan the whole day FIRST, then run it in departure order.
			# The odometer can only be handed out chronologically: a vehicle cannot
			# leave at 07:00 on a higher reading than it came back on at 17:15. An
			# earlier version created the two fixed runs and then the ad-hoc ones,
			# so a 07:00 trip inherited the evening's odometer and every such pair
			# overlapped - which in this business means the same kilometres billed
			# to TIQN twice.
			plans = []

			if not is_sunday:
				for schedule in schedules.get(vehicle, []):
					plans.append({
						"kind": "fixed",
						"depart": _clock(schedule.depart_time),
						"schedule": schedule,
					})
			else:
				case("chủ nhật không có chuyến cố định")

			for _ in range(rng.randint(2, 4) if not is_sunday else rng.randint(0, 2)):
				plans.append(_plan_on_demand(rng))

			plans.sort(key=lambda p: p["depart"])

			# On today, the vehicle is still out on the LAST trip that has already
			# departed; everything before it came back. Decided up front because it
			# needs the whole sorted day, not one row at a time.
			# Only the first vehicle is left out on the road. With all three
			# mid-trip the board would never show an idle vehicle, and there would
			# be nothing to put into maintenance - three vehicles, three statuses.
			running_depart = None
			if not past and not future and vehicle == vehicles[0]:
				now_clock = now_datetime().strftime("%H:%M:%S")
				departed = [p["depart"] for p in plans
				            if p["kind"] == "on_demand" and p["depart"] < now_clock]
				running_depart = departed[-1] if departed else None

			for plan in plans:
				if plan["kind"] == "fixed":
					schedule = plan["schedule"]
					_make_trip(
						vehicle=vehicle, day=day, depart=schedule.depart_time,
						from_location=schedule.from_location,
						to_location=schedule.to_location,
						trip_name=schedule.trip_name_template or schedule.schedule_name,
						trip_type="fixed", template_id=schedule.name,
						status=_fixed_status(past, future, schedule.depart_time, rng),
						odometer=odometer, rng=rng, stats=stats, case=case,
					)
				else:
					_make_on_demand(
						plan=plan, vehicle=vehicle, day=day, past=past, future=future,
						odometer=odometer, rng=rng, stats=stats, case=case,
						running_depart=running_depart,
					)

		frappe.db.commit()

	_make_edge_cases(today, rng, stats, case)
	frappe.db.commit()

	print(f"\n{stats['trips']} chuyến · {stats['requests']} yêu cầu "
	      f"· {days[0]} → {days[-1]}")
	print("\nCác trường hợp đã sinh:")
	for name in sorted(cases):
		print(f"  {cases[name]:>4}  {name}")
	return {"trips": stats["trips"], "requests": stats["requests"], "cases": cases}


# ---------------------------------------------------------------------------
def _require_masters():
	missing = [v for v in START_KM if not frappe.db.exists("TIQN Vehicle", v)]
	if missing:
		frappe.throw(f"Thiếu xe: {', '.join(missing)}. Chạy `bench migrate` trước.")
	if not frappe.db.count("TIQN Fixed Trip Schedule", {"is_active": 1}):
		frappe.throw("Chưa có TIQN Fixed Trip Schedule nào đang bật.")


def _purge():
	for req in frappe.get_all("TIQN Vehicle Request", pluck="name"):
		frappe.db.set_value("TIQN Vehicle Request", req, "assigned_trip", None, update_modified=False)
	for trip in frappe.get_all("TIQN Vehicle Trip", pluck="name"):
		frappe.delete_doc("TIQN Vehicle Trip", trip, force=True, ignore_permissions=True,
		                  delete_permanently=True)
	for req in frappe.get_all("TIQN Vehicle Request", pluck="name"):
		frappe.delete_doc("TIQN Vehicle Request", req, force=True, ignore_permissions=True,
		                  delete_permanently=True)
	for v in frappe.get_all("TIQN Vehicle", fields=["name", "status"]):
		if v.status != "available":
			frappe.db.set_value("TIQN Vehicle", v.name, "status", "available", update_modified=False)
	frappe.db.commit()
	print("  Đã xoá sạch chuyến và yêu cầu cũ")


def _days_in_month(year, month):
	first = getdate(f"{year}-{month:02d}-01")
	days, cursor = [], first
	while cursor.month == month:
		days.append(cursor)
		cursor += timedelta(days=1)
	return days


def _schedules_by_vehicle():
	out = {}
	for s in frappe.get_all(
		"TIQN Fixed Trip Schedule",
		filters={"is_active": 1},
		fields=["name", "vehicle", "schedule_name", "trip_name_template", "depart_time",
		        "from_location", "to_location", "trip_number"],
		order_by="trip_number asc, depart_time asc",
	):
		out.setdefault(s.vehicle, []).append(s)
	return out


def _fixed_status(past, future, depart, rng):
	if past:
		# One shuttle in the whole month gets cancelled, so the board has a
		# cancelled FIXED trip too, not only cancelled ad-hoc ones.
		return "cancelled" if rng.random() < 0.02 else "completed"
	if future:
		return "scheduled"
	# today: the morning run is done, the afternoon one has not left yet
	return "completed" if str(depart) < "12:00:00" else "scheduled"


def _make_trip(vehicle, day, depart, from_location, to_location, trip_name, trip_type,
               status, odometer, rng, stats, case, template_id=None, passengers=None,
               notes=None):
	"""Insert one trip and move that vehicle's odometer along.

	The odometer only advances for a trip that actually ran. A cancelled or
	not-yet-started trip leaves it where it was - otherwise the KM report would
	bill TIQN for journeys nobody made.
	"""
	doc = frappe.new_doc("TIQN Vehicle Trip")
	doc.update({
		"trip_name": trip_name,
		"trip_type": trip_type,
		"template_id": template_id,
		"vehicle": vehicle,
		"trip_date": day,
		"depart_time": depart,
		"from_location": from_location,
		"to_location": to_location,
		"status": status,
		"notes": notes,
	})

	if status in ("completed", "in_progress"):
		km_start = odometer[vehicle] + rng.randint(0, 3)
		doc.km_start = km_start
		doc.checkin_time = _stamp(day, depart, rng.randint(-5, 8))
		if rng.random() < 0.3:
			doc.checkin_notes = rng.choice(["Xe tốt", "Đủ nhiên liệu", "Kiểm tra lốp OK"])

	if status == "completed":
		distance = rng.randint(8, 60)
		doc.km_end = doc.km_start + distance
		doc.checkout_time = _stamp(day, depart, rng.randint(35, 190))
		odometer[vehicle] = doc.km_end
		if rng.random() < 0.18:
			doc.additional_cost = rng.choice([30000, 50000, 80000, 150000])
			doc.checkout_notes = rng.choice(["Qua trạm thu phí", "Gửi xe sân bay", "Phí cầu đường"])
			case("chuyến có chi phí phát sinh")
		case(f"chuyến {trip_type} hoàn thành")
	elif status == "in_progress":
		odometer[vehicle] = doc.km_start
		case("chuyến đang chạy")
	elif status == "cancelled":
		doc.cancelled_reason = rng.choice(CANCEL_REASONS)
		case(f"chuyến {trip_type} bị hủy")
	elif status == "confirmed":
		doc.confirmed_at = _stamp(day, depart, -30)
		case("chuyến đã xác nhận")
	else:
		case(f"chuyến {trip_type} chờ chạy")

	for row in passengers or []:
		doc.append("passengers", row)
	if passengers:
		case(f"chuyến chở {len(passengers)} khách" if len(passengers) > 1 else "chuyến có hành khách")

	doc.insert(ignore_permissions=True)
	stats["trips"] += 1
	return doc


def _plan_on_demand(rng):
	"""Decide WHEN and WHERE before anything is written, so the day can be sorted."""
	name, code = rng.choice(EMPLOYEES)
	outbound = rng.random() < 0.6
	other = rng.choice(PLACES)
	return {
		"kind": "on_demand",
		"depart": f"{rng.randint(7, 19):02d}:{rng.choice(['00', '15', '30', '45'])}:00",
		"employee": name,
		"code": code,
		"from_location": HOME if outbound else other,
		"to_location": other if outbound else HOME,
		"purpose": rng.choice(PURPOSES),
		"with_request": rng.random() < 0.75,
		"shared": rng.random() < 0.15,
		# On a day still to come, some requests are simply not dealt with yet.
		# That is where the "Chờ duyệt" queue comes from - a real backlog rather
		# than rows invented to make the colours show up.
		"unanswered": rng.random() < 0.3,
	}


def _make_on_demand(plan, vehicle, day, past, future, odometer, rng, stats, case,
                    running_depart=None):
	"""One ad-hoc trip, usually with the request that asked for it."""
	depart = plan["depart"]
	from_location, to_location = plan["from_location"], plan["to_location"]

	request_doc = None
	if plan["with_request"]:
		request_doc = _make_request(
			name=plan["employee"], code=plan["code"], day=day, depart=depart,
			from_location=from_location, to_location=to_location,
			purpose=plan["purpose"], rng=rng, stats=stats, case=case,
		)
	else:
		case("chuyến phát sinh không có yêu cầu")

	if future and request_doc and plan["unanswered"]:
		# No trip at all: the request sits in the dispatcher's queue.
		case("yêu cầu chờ duyệt (chưa xếp xe)")
		return None

	if past:
		status = "cancelled" if rng.random() < 0.08 else "completed"
	elif future:
		status = "confirmed" if rng.random() < 0.25 else "scheduled"
	else:
		status = _today_status(depart, running_depart, case)

	passengers = []
	if request_doc:
		passengers.append({
			"request": request_doc.name,
			"passenger_name": request_doc.employee_name,
			"pickup_location": request_doc.from_location,
			"pickup_order": 1,
		})
		# Now and then a colleague shares the ride - that is the combined-trip case.
		if plan["shared"]:
			mate_name, mate_code = rng.choice(EMPLOYEES)
			mate = _make_request(
				name=mate_name, code=mate_code, day=day, depart=depart,
				from_location=from_location, to_location=to_location,
				purpose="Đi chung xe", rng=rng, stats=stats, case=case,
			)
			passengers.append({
				"request": mate.name, "passenger_name": mate.employee_name,
				"pickup_location": mate.from_location, "pickup_order": 2,
			})

	trip = _make_trip(
		vehicle=vehicle, day=day, depart=depart,
		from_location=from_location, to_location=to_location,
		trip_name=f"{from_location} → {to_location}",
		trip_type="on_demand", status=status, odometer=odometer, rng=rng,
		stats=stats, case=case, passengers=passengers,
		notes=plan["purpose"] if rng.random() < 0.25 else None,
	)

	# The dispatcher re-routed a trip that was already moving and the driver has
	# not acknowledged it yet - the red "Lộ trình đã đổi" badge.
	if status == "in_progress" and rng.random() < 0.4:
		trip.db_set("route_changed", 1, update_modified=False)
		trip.db_set("dispatcher_note", "Ghé thêm Cảng Dung Quất trước khi về")
		case("chuyến bị đổi lộ trình, tài xế chưa xác nhận")

	return trip


def _today_status(depart, running_depart, case):
	"""Today: earlier trips finished, the latest departure is still out, rest waiting."""
	now = now_datetime().strftime("%H:%M:%S")
	if depart >= now:
		return "scheduled"
	if running_depart and depart == running_depart:
		case("chuyến đang chạy (hôm nay)")
		return "in_progress"
	return "completed"


def _make_request(name, code, day, depart, from_location, to_location, purpose,
                  rng, stats, case, status=None):
	doc = frappe.new_doc("TIQN Vehicle Request")
	request_time = _stamp(day, depart, 0)
	doc.update({
		"employee_name": name,
		"employee_id_display": code,
		"zalo_user_id": f"zalo_{code.lower()}",
		"request_time": request_time,
		"submit_time": add_to_date(get_datetime(request_time), hours=-rng.randint(1, 20)),
		"from_location": from_location,
		"to_location": to_location,
		"purpose": purpose,
		"passenger_count": rng.randint(1, 4),
		"status": "pending",
	})
	# Round trips: the vehicle is booked until it comes back.
	if rng.random() < 0.35:
		doc.return_time = add_to_date(get_datetime(request_time), hours=rng.randint(2, 6))
		case("yêu cầu có giờ về")
	if rng.random() < 0.2:
		doc.notes = rng.choice(["Mang theo hồ sơ", "Cần xe 7 chỗ", "Đón tại cổng phụ"])

	doc.insert(ignore_permissions=True)
	stats["requests"] += 1
	case("yêu cầu")
	return doc


def _clock(value):
	"""Always "HH:MM:SS".

	🔴 A Frappe Time column is a `timedelta`, and `str(timedelta(hours=6.5))` is
	"6:30:00" - no leading zero. Sorting those as strings puts the 06:30 shuttle
	AFTER a 07:00 ad-hoc run, which handed the morning trip the evening odometer
	and billed the same kilometres twice. Never sort raw Time values as text.
	"""
	if isinstance(value, timedelta):
		total = int(value.total_seconds())
		return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"
	parts = str(value).split(":")
	while len(parts) < 3:
		parts.append("0")
	return ":".join(f"{int(p):02d}" for p in parts[:3])


def _stamp(day, depart, offset_minutes):
	base = get_datetime(f"{day} {depart}")
	return add_to_date(base, minutes=offset_minutes)


def _make_edge_cases(today, rng, stats, case):
	"""The states the day-by-day loop never produces on its own.

	Every one of these exists to light up a specific behaviour on screen; without
	them the board looks plausible but half the code paths are never exercised.
	"""
	# --- two requests the dispatcher can merge: same route, 20 minutes apart ---
	base = add_to_date(now_datetime(), hours=4)
	# Real names, not "Gom chung xe 1/2": the board should read like a working day,
	# not like a fixture. These two exist because same-route-within-30-minutes is
	# rare enough that random data cannot be relied on to produce it.
	for idx, offset in enumerate((0, 20)):
		who, code = EMPLOYEES[idx]
		frappe.new_doc("TIQN Vehicle Request").update({
			"employee_name": who,
			"employee_id_display": code,
			"request_time": add_to_date(base, minutes=offset),
			"submit_time": now_datetime(),
			"from_location": HOME,
			"to_location": "Sân bay Chu Lai",
			"purpose": "Đi sân bay",
			"passenger_count": 1,
			"status": "pending",
		}).insert(ignore_permissions=True)
		stats["requests"] += 1
	case("2 yêu cầu có thể GOM chung một xe")

	# --- a request turned down, and one the requester called off ---------------
	rejected = frappe.new_doc("TIQN Vehicle Request").update({
		"employee_name": "Võ Văn Hùng",
		"employee_id_display": "EMP008",
		"request_time": add_to_date(now_datetime(), hours=6),
		"submit_time": now_datetime(),
		"from_location": HOME,
		"to_location": "Sở Lao động",
		"purpose": "Làm thủ tục BHXH",
		"passenger_count": 1,
		"status": "rejected",
		"rejection_reason": rng.choice(REJECT_REASONS),
	}).insert(ignore_permissions=True)
	stats["requests"] += 1
	case("yêu cầu bị TỪ CHỐI (có lý do)")

	cancelled = frappe.new_doc("TIQN Vehicle Request").update({
		"employee_name": "Đặng Thị Kim",
		"employee_id_display": "EMP009",
		"request_time": add_to_date(now_datetime(), hours=8),
		"submit_time": now_datetime(),
		"from_location": HOME,
		"to_location": "Ga Quảng Ngãi",
		"purpose": "Đón người nhà",
		"passenger_count": 2,
		"status": "pending",
	}).insert(ignore_permissions=True)
	cancelled.status = "cancelled"
	cancelled.save(ignore_permissions=True)
	stats["requests"] += 1
	case("yêu cầu người dùng TỰ HỦY")

	# --- `approved` is a Desk-only state: the Mini App never produces it, but a
	#     record in that state has to render correctly if it ever appears. -------
	approved = frappe.new_doc("TIQN Vehicle Request").update({
		"employee_name": "Bùi Văn Lâm",
		"employee_id_display": "EMP010",
		"request_time": add_to_date(now_datetime(), hours=10),
		"submit_time": now_datetime(),
		"from_location": HOME,
		"to_location": "Cảng Dung Quất",
		"purpose": "Kiểm hàng",
		"passenger_count": 1,
		"status": "pending",
	}).insert(ignore_permissions=True)
	approved.status = "approved"
	approved.save(ignore_permissions=True)
	stats["requests"] += 1
	case("yêu cầu ĐÃ DUYỆT chờ xếp xe (trạng thái chỉ có ở Desk)")

	# --- a vehicle out of service ---------------------------------------------
	# Never a vehicle that is mid-trip: "in maintenance" and "on the road" at the
	# same time is a contradiction the dashboard would happily display.
	idle = [
		v for v in frappe.get_all("TIQN Vehicle", pluck="name", order_by="name asc")
		if not frappe.db.exists("TIQN Vehicle Trip", {"vehicle": v, "status": "in_progress"})
	]
	if idle:
		frappe.db.set_value("TIQN Vehicle", idle[-1], "status", "maintenance",
		                    update_modified=False)
		case("xe đang BẢO TRÌ")
	if len(idle) > 1:
		case("xe SẴN SÀNG (đang đỗ)")

	_close_stale_requests(today, case)

	print("  Đã thêm các ca đặc biệt (quá giờ, gom xe, từ chối, tự hủy, bảo trì)")


def _close_stale_requests(today, case):
	"""Answer the requests left hanging by a cancelled trip.

	A request whose trip got cancelled stays `pending` - sync_linked_requests only
	reverts one that had reached `assigned`. Realistic, but left alone it fills the
	board with a dozen permanently-red rows from weeks ago and the genuine overdue
	warning stops meaning anything.

	The deliberately-overdue examples are recognised by name and left alone, so the
	red and amber states still have something to show.
	"""
	stale = frappe.get_all(
		"TIQN Vehicle Request",
		filters={
			"status": "pending",
			"request_time": ("<", f"{today} 00:00:00"),
			"employee_name": ("not like", "Chờ duyệt%"),
		},
		pluck="name",
	)
	for name in stale:
		frappe.db.set_value("TIQN Vehicle Request", name, {
			"status": "rejected",
			"rejection_reason": "Chuyến bị hủy, đề nghị đăng ký lại",
		}, update_modified=False)
	if stale:
		case(f"yêu cầu tồn đọng đã đóng lại ({len(stale)})")
