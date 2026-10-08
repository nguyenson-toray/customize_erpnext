# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Demo dataset for 14-16/09/2026, per kịch bản kiểm tra gốc (đã gộp vào README).

    bench --site erp.tiqn.local execute \
        customize_erpnext.vehicle_management.seed_test_data.execute

    # start from a clean slate (deletes every trip and request first):
    bench --site erp.tiqn.local execute \
        customize_erpnext.vehicle_management.seed_test_data.execute \
        --kwargs '{"purge": true}'

This is DEMO data for the Zalo Mini App screens - three days covering a Sunday
with no fixed trips, a full working Monday with every status represented, and a
Tuesday that is "today" with trips still to run.

Deliberately NOT whitelisted and NOT wired to any hook: it writes across the
whole fleet and must only ever be run by hand.

Vehicles are NOT created or renamed here - they are real records; the sample names
in the prompt are ignored on purpose. The script checks the three vehicles exist
and stops if they do not.

Tài xế cũng không khai ở đây: chuyến gán theo XE, tài xế được suy ra lúc đọc từ xe.

Idempotent: a trip is keyed on (trip_name, trip_date) and a request on
(employee_name, request_time), so re-running adds nothing.
"""

import frappe
from frappe.utils import flt, getdate

VEHICLES = {"bus1": "TIQN-VEH-001", "bus2": "TIQN-VEH-002", "kia": "TIQN-VEH-003"}
# Tài xế KHÔNG còn khai ở đây: chuyến gán theo XE. Một bản sao thứ hai của
# "ai lái xe này" chính là thứ đã mục nát khi đổi tên tài xế ngày 22/09.


# ---------------------------------------------------------------- 14/09 (Sun)
# No fixed trips: Sunday is not in any schedule's days_of_week. Only the two
# one-off runs that really would happen on a day off.
TRIP_14_01 = {
	"trip_name": "Đưa giám đốc — Công ty → Sân bay Đà Nẵng",
	"trip_type": "on_demand", "trip_date": "2026-09-14", "status": "completed",
	"depart_time": "06:00",
	"from_location": "Toray VSIP Quảng Ngãi", "to_location": "Sân bay Đà Nẵng",
	"vehicle": VEHICLES["bus1"],
	"km_start": 50200, "km_end": 50350,
	"checkin_time": "2026-09-14 06:10:00", "checkout_time": "2026-09-14 09:45:00",
	"additional_cost": 150000, "checkout_notes": "Qua trạm thu phí 2 lần",
}
TRIP_14_02 = {
	"trip_name": "Đưa nhân viên cấp cứu",
	"trip_type": "on_demand", "trip_date": "2026-09-14", "status": "completed",
	"depart_time": "14:30",
	"from_location": "Toray VSIP", "to_location": "BV Đa Khoa Quảng Ngãi",
	"vehicle": VEHICLES["kia"],
	"km_start": 30100, "km_end": 30140,
	"checkin_time": "2026-09-14 14:35:00", "checkout_time": "2026-09-14 15:20:00",
	"checkin_notes": "Trường hợp khẩn cấp, không có yêu cầu trước",
}
REQ_14_01 = {
	"employee_name": "Trần Thị B", "employee_id_display": "EMP002",
	"from_location": "Toray VSIP", "to_location": "Sân bay Đà Nẵng",
	"request_time": "2026-09-14 05:30:00", "submit_time": "2026-09-14 05:30:00",
	"purpose": "Đi cùng giám đốc", "passenger_count": 1,
}

# ---------------------------------------------------------------- 15/09 (Mon)
TRIP_15_01 = {
	"trip_name": "Chuyến sáng — Bus 1", "trip_type": "fixed",
	"trip_date": "2026-09-15", "status": "completed", "depart_time": "06:30",
	"from_location": "Ký túc xá VSIP", "to_location": "Toray VSIP",
	"vehicle": VEHICLES["bus1"],
	"km_start": 50350, "km_end": 50362,
	"checkin_time": "2026-09-15 06:32:00", "checkout_time": "2026-09-15 07:05:00",
}
TRIP_15_02 = {
	"trip_name": "Chuyến sáng — Bus 2", "trip_type": "fixed",
	"trip_date": "2026-09-15", "status": "completed", "depart_time": "06:30",
	"from_location": "Ký túc xá", "to_location": "Toray VSIP",
	"vehicle": VEHICLES["bus2"],
	"km_start": 28000, "km_end": 28012,
	"checkin_time": "2026-09-15 06:28:00", "checkout_time": "2026-09-15 07:10:00",
}
TRIP_15_03 = {
	"trip_name": "Họp UBND Tỉnh", "trip_type": "on_demand",
	"trip_date": "2026-09-15", "status": "completed", "depart_time": "09:00",
	"from_location": "Toray VSIP", "to_location": "UBND Tỉnh Quảng Ngãi",
	"vehicle": VEHICLES["kia"],
	"km_start": 30140, "km_end": 30158,
	"checkin_time": "2026-09-15 09:05:00", "checkout_time": "2026-09-15 11:30:00",
}
TRIP_15_04 = {
	"trip_name": "Chuyến chiều — Bus 1", "trip_type": "fixed",
	"trip_date": "2026-09-15", "status": "completed", "depart_time": "17:00",
	"from_location": "Toray VSIP", "to_location": "Ký túc xá VSIP",
	"vehicle": VEHICLES["bus1"],
	"km_start": 50362, "km_end": 50374,
	"checkin_time": "2026-09-15 17:02:00", "checkout_time": "2026-09-15 17:40:00",
}
TRIP_15_05 = {
	"trip_name": "Chuyến chiều — Bus 2", "trip_type": "fixed",
	"trip_date": "2026-09-15", "status": "in_progress", "depart_time": "17:00",
	"from_location": "Toray VSIP", "to_location": "Ký túc xá",
	"vehicle": VEHICLES["bus2"],
	"km_start": 28012, "checkin_time": "2026-09-15 17:05:00",
}
TRIP_15_06 = {
	"trip_name": "Đón khách — KCN Quảng Phú", "trip_type": "on_demand",
	"trip_date": "2026-09-15", "status": "scheduled", "depart_time": "18:30",
	"from_location": "Toray VSIP", "to_location": "KCN Quảng Phú",
	"vehicle": VEHICLES["kia"],
}
TRIP_15_07 = {
	"trip_name": "Chuyến thêm bị hủy", "trip_type": "on_demand",
	"trip_date": "2026-09-15", "status": "cancelled", "depart_time": "13:00",
	"from_location": "Toray VSIP", "to_location": "UBND TP Quảng Ngãi",
	"vehicle": VEHICLES["bus1"],
	"cancelled_reason": "Khách hủy đột xuất",
}
REQ_15_02 = {
	"employee_name": "Nguyễn Văn A", "employee_id_display": "EMP001",
	"from_location": "Toray VSIP", "to_location": "UBND Tỉnh Quảng Ngãi",
	"request_time": "2026-09-15 08:30:00", "submit_time": "2026-09-15 08:00:00",
	"purpose": "Họp UBND", "passenger_count": 1,
}
REQ_15_03 = {
	"employee_name": "Lê Thị C", "employee_id_display": "EMP003",
	"from_location": "Toray VSIP", "to_location": "UBND Tỉnh Quảng Ngãi",
	"request_time": "2026-09-15 08:30:00", "submit_time": "2026-09-15 08:10:00",
	"purpose": "Họp UBND (gom xe)", "passenger_count": 1,
}
REQ_15_04 = {
	"employee_name": "Phạm Văn D", "employee_id_display": "EMP004",
	"from_location": "Toray VSIP", "to_location": "Ngân hàng Vietcombank",
	"request_time": "2026-09-15 14:00:00", "submit_time": "2026-09-15 13:30:00",
	"purpose": "Nộp hồ sơ ngân hàng", "passenger_count": 2, "status": "pending",
}
REQ_15_05 = {
	"employee_name": "Nguyễn Thị E", "employee_id_display": "EMP005",
	"from_location": "Toray VSIP", "to_location": "Sở Lao động",
	"request_time": "2026-09-15 10:00:00", "submit_time": "2026-09-15 09:00:00",
	"purpose": "Làm thủ tục BHXH", "passenger_count": 1,
	"status": "rejected", "rejection_reason": "Không có xe trống, vui lòng sắp xếp lại",
}

# ---------------------------------------------------------------- 16/09 (Tue)
TRIP_16_01 = {
	"trip_name": "Chuyến sáng — Bus 1", "trip_type": "fixed",
	"trip_date": "2026-09-16", "status": "scheduled", "depart_time": "06:30",
	"from_location": "Ký túc xá VSIP", "to_location": "Toray VSIP",
	"vehicle": VEHICLES["bus1"],
}
TRIP_16_02 = {
	"trip_name": "Chuyến sáng — Bus 2", "trip_type": "fixed",
	"trip_date": "2026-09-16", "status": "scheduled", "depart_time": "06:30",
	"from_location": "Ký túc xá", "to_location": "Toray VSIP",
	"vehicle": VEHICLES["bus2"],
}
TRIP_16_03 = {
	"trip_name": "Kế toán — Ngân hàng", "trip_type": "on_demand",
	"trip_date": "2026-09-16", "status": "scheduled", "depart_time": "09:00",
	"from_location": "Toray VSIP", "to_location": "Vietcombank Quảng Ngãi",
	"vehicle": VEHICLES["kia"],
	"notes": "Mang theo hồ sơ công ty",
}
REQ_16_06 = {
	"employee_name": "Trần Văn F", "employee_id_display": "EMP006",
	"from_location": "Toray VSIP", "to_location": "Sở Kế hoạch Đầu tư",
	"request_time": "2026-09-16 08:00:00", "submit_time": "2026-09-16 07:45:00",
	"purpose": "Nộp báo cáo quý", "passenger_count": 1, "status": "pending",
}
REQ_16_07 = {
	"employee_name": "Lê Thị G", "employee_id_display": "EMP007",
	"from_location": "Toray VSIP", "to_location": "Cục Thuế Quảng Ngãi",
	"request_time": "2026-09-16 10:30:00", "submit_time": "2026-09-16 08:00:00",
	"purpose": "Nộp tờ khai thuế", "passenger_count": 2, "status": "pending",
}


def execute(purge=False):
	_require_masters()

	if purge:
		_purge()

	log = []

	# --- 14/09: Sunday. The request is created PENDING and becomes `assigned`
	# by being put on the trip - the same path the dispatcher uses, so the
	# passenger row and the request status can never disagree.
	req_14_01 = _request(REQ_14_01, log)
	_trip(TRIP_14_01, log, passengers=[
		{"request": req_14_01, "passenger_name": "Trần Thị B",
		 "pickup_location": "Toray VSIP", "pickup_order": 1},
	])
	_trip(TRIP_14_02, log)

	# --- 15/09: Monday, every status represented.
	_trip(TRIP_15_01, log)
	_trip(TRIP_15_02, log)

	req_15_02 = _request(REQ_15_02, log)
	req_15_03 = _request(REQ_15_03, log)
	_trip(TRIP_15_03, log, passengers=[
		{"request": req_15_02, "passenger_name": "Nguyễn Văn A",
		 "pickup_location": "Toray VSIP", "pickup_order": 1},
		{"request": req_15_03, "passenger_name": "Lê Thị C",
		 "pickup_location": "Toray VSIP", "pickup_order": 2},
	])

	_trip(TRIP_15_04, log)
	_trip(TRIP_15_05, log)
	_trip(TRIP_15_06, log)
	_trip(TRIP_15_07, log)
	_request(REQ_15_04, log)
	_request(REQ_15_05, log)

	# --- 16/09: today, nothing has started yet.
	_trip(TRIP_16_01, log)
	_trip(TRIP_16_02, log)
	_trip(TRIP_16_03, log)
	_request(REQ_16_06, log)
	_request(REQ_16_07, log)

	frappe.db.commit()

	for line in log:
		print(line)
	print(f"\n{len([x for x in log if x.startswith('  OK')])} created, "
	      f"{len([x for x in log if x.startswith('  SKIP')])} already present")
	return log


# ---------------------------------------------------------------------------
def _require_masters():
	missing = [v for v in VEHICLES.values() if not frappe.db.exists("TIQN Vehicle", v)]
	if missing:
		frappe.throw(
			"Missing master records: {0}. Run `bench migrate` so "
			"seed_vehicle_management_data creates the fleet first.".format(", ".join(missing))
		)


def _purge():
	"""Remove every trip and request. Masters and schedules are left alone."""
	for req in frappe.get_all("TIQN Vehicle Request", pluck="name"):
		# Clear the link first or deleting its trip raises LinkExistsError.
		frappe.db.set_value("TIQN Vehicle Request", req, "assigned_trip", None, update_modified=False)

	for trip in frappe.get_all("TIQN Vehicle Trip", pluck="name"):
		frappe.delete_doc("TIQN Vehicle Trip", trip, force=True, ignore_permissions=True,
		                  delete_permanently=True)
	for req in frappe.get_all("TIQN Vehicle Request", pluck="name"):
		frappe.delete_doc("TIQN Vehicle Request", req, force=True, ignore_permissions=True,
		                  delete_permanently=True)

	# on_trash keeps this in step now, but a purge of a busy fleet deserves a check.
	for vehicle in frappe.get_all("TIQN Vehicle", fields=["name", "status"]):
		if vehicle.status == "in_trip":
			frappe.db.set_value("TIQN Vehicle", vehicle.name, "status", "available",
			                    update_modified=False)
	frappe.db.commit()
	print("  PURGED all trips and requests")


def _trip(data, log, passengers=None):
	existing = frappe.db.get_value(
		"TIQN Vehicle Trip", {"trip_name": data["trip_name"], "trip_date": data["trip_date"]}, "name"
	)
	if existing:
		log.append(f"  SKIP trip {existing} — {data['trip_name']} ({data['trip_date']})")
		return existing

	doc = frappe.new_doc("TIQN Vehicle Trip")
	doc.update(data)
	for row in passengers or []:
		doc.append("passengers", row)
	# Dữ liệu mẫu dựng lại lịch sử đã qua nên cố ý tạo chuyến ở trạng thái cuối.
	# Cờ này là cách CODE SERVER nói "tôi đang ghi lịch sử"; client không đặt được.
	doc.flags.allow_backdated_status = True
	doc.insert(ignore_permissions=True)

	log.append(f"  OK   trip {doc.name} — {data['trip_name']} ({data['trip_date']}, {data['status']})")
	return doc.name


def _request(data, log):
	existing = frappe.db.get_value(
		"TIQN Vehicle Request",
		{"employee_name": data["employee_name"], "request_time": data["request_time"]},
		"name",
	)
	if existing:
		log.append(f"  SKIP req  {existing} — {data['employee_name']}")
		return existing

	doc = frappe.new_doc("TIQN Vehicle Request")
	doc.update(data)
	doc.insert(ignore_permissions=True)
	log.append(f"  OK   req  {doc.name} — {data['employee_name']} ({doc.status})")
	return doc.name


SEEDED_TRIPS = [
	TRIP_14_01, TRIP_14_02,
	TRIP_15_01, TRIP_15_02, TRIP_15_03, TRIP_15_04, TRIP_15_05, TRIP_15_06, TRIP_15_07,
	TRIP_16_01, TRIP_16_02, TRIP_16_03,
]


def seed_drift():
	"""How far the dataset has moved since it was seeded.

	The demo data exists to be USED - the Mini App team drive check-ins, approvals
	and cancellations through it, and that legitimately changes every count. So the
	exact-number checks below have to know whether they are still looking at a
	fresh dataset. Without this they cry wolf: a tester completing one trip turns
	four green checks red and hides a real failure in the noise.
	"""
	drift = []
	for spec in SEEDED_TRIPS:
		row = frappe.db.get_value(
			"TIQN Vehicle Trip",
			{"trip_name": spec["trip_name"], "trip_date": spec["trip_date"]},
			["name", "status", "km_start", "km_end"],
			as_dict=True,
		)
		if not row:
			drift.append(f"{spec['trip_name']} ({spec['trip_date']}) đã bị xoá")
			continue
		if row.status != spec["status"]:
			drift.append(f"{row.name} status {spec['status']} → {row.status}")
		if flt(row.km_start) != flt(spec.get("km_start")):
			drift.append(f"{row.name} km_start {spec.get('km_start')} → {row.km_start}")

	extra = frappe.db.count("TIQN Vehicle Trip") - len(SEEDED_TRIPS)
	if extra > 0:
		drift.append(f"{extra} chuyến được tạo thêm ngoài bộ seed")
	return drift


def verify():
	"""Checks from kịch bản kiểm tra gốc, with the KPI
	definitions both teams agreed in vehicle_management/API_CONTRACT.md mục 9.

	Read-only. Split into three kinds of check, because they fail for different
	reasons and deserve different reactions:

	  INVARIANT  — must hold no matter what anyone does. A failure here is a bug.
	  DỮ LIỆU    — data quality worth a human look, not necessarily wrong.
	  BỘ SEED    — exact counts, only meaningful on a freshly seeded dataset.
	"""
	import customize_erpnext.api.vehicle_management as vm

	problems = []

	def expect(label, got, want):
		if got == want:
			print(f"  ok   {label}: {got}")
		else:
			problems.append(label)
			print(f"  FAIL {label}: {got} (want {want})")

	print("\n── INVARIANT ─────────────────────────────────────────")

	print("3.8 Chủ nhật không có chuyến cố định")
	# Chủ nhật được TÍNH RA từ chính dữ liệu, không viết cứng ngày.
	# kịch bản kiểm tra gốc (đã gộp vào README) gọi 14/09/2026 là Chủ nhật — sai, đó là thứ Hai
	# (Chủ nhật tháng 9/2026 là 06, 13, 20, 27). Viết cứng một ngày là biến cái
	# nhầm của tài liệu thành "sự thật" của bộ kiểm tra.
	sundays = sorted({
		str(row.trip_date)
		for row in frappe.get_all(
			"TIQN Vehicle Trip", filters={"trip_type": "fixed"}, fields=["trip_date"]
		)
		if getdate(row.trip_date).weekday() == 6
	})
	expect("ngày Chủ nhật có chuyến cố định", sundays, [])

	print("3.9 không ai lái 2 chuyến cùng lúc")
	from collections import Counter
	running = Counter(
		t.vehicle for t in frappe.get_all(
			"TIQN Vehicle Trip", filters={"status": "in_progress"}, fields=["vehicle"])
	)
	# Xe mới là thứ không thể ở hai nơi cùng lúc; tài xế chỉ là thông tin suy ra.
	expect("xe chạy >1 chuyến cùng lúc", [v for v, n in running.items() if n > 1], [])

	print("3.5 / 3.6 shape của get_trips")
	trips = vm.get_trips(date="2026-09-15", limit=0)
	expect("mọi chuyến có vehicle_name", [t.name for t in trips if not t.get("vehicle_name")], [])
	expect("mọi chuyến có driver_name", [t.name for t in trips if not t.get("driver_name")], [])
	expect("mọi chuyến có license_plate", [t.name for t in trips if not t.get("license_plate")], [])
	expect("depart_time dạng HH:MM",
	       [t["depart_time"] for t in trips if t["depart_time"] and len(t["depart_time"]) != 5], [])

	meeting_name = frappe.db.get_value("TIQN Vehicle Trip", {"trip_name": "Họp UBND Tỉnh"}, "name")
	if meeting_name:
		meeting = vm.get_trip(meeting_name)
		expect("passengers là list", isinstance(meeting["passengers"], list), True)
		expect("key hành khách", sorted(meeting["passengers"][0]),
		       ["from_location", "order", "passenger_name", "request_id", "row_name"])

	print("\n── DỮ LIỆU: KM tính tiền ─────────────────────────────")
	# Xe và tài xế là của công ty đối tác; TIQN trả tiền theo SỐ KM THỰC TẾ TỪNG
	# CHUYẾN, không quan tâm nhiên liệu. Vì vậy hai kiểu lệch có ý nghĩa trái ngược:
	#
	#   HỤT  (km_start > km_end chuyến trước) — đối tác chạy việc riêng giữa hai
	#         chuyến. TIQN không trả cho đoạn đó ⇒ vô hại, chỉ in ra cho biết.
	#   ĐÈ   (km_start < km_end chuyến trước) — hai chuyến khai trùng một đoạn
	#         đường ⇒ TRẢ TIỀN HAI LẦN cho cùng số km. Đây mới là cái phải bắt.
	#
	# Server đã chặn "đè" trong cùng một ngày; kiểm ở đây bắt cả trường hợp qua ngày,
	# vốn không chặn được vì sẽ cản việc nhập bù chuyến cũ.
	for key, vehicle in VEHICLES.items():
		rows = frappe.get_all(
			"TIQN Vehicle Trip",
			filters={"vehicle": vehicle, "status": "completed"},
			fields=["name", "trip_date", "depart_time", "km_start", "km_end"],
			order_by="trip_date asc, depart_time asc",
		)
		overlaps, gaps = [], []
		for i in range(1, len(rows)):
			prev, curr = rows[i - 1], rows[i]
			delta = flt(curr.km_start) - flt(prev.km_end)
			if delta < 0:
				overlaps.append(f"{prev.name}({prev.km_end}) → {curr.name}({curr.km_start}) THỪA {-delta:g} km")
			elif delta > 0:
				gaps.append(f"{prev.name} → {curr.name} hụt {delta:g} km")

		if overlaps:
			problems.append(f"{key}: khai trùng KM")
			print(f"  FAIL {key} — KHAI TRÙNG, trả tiền 2 lần: " + "; ".join(overlaps))
		else:
			note = f" (hụt vô hại: {len(gaps)} chỗ)" if gaps else ""
			print(f"  ok   {key} — không có đoạn KM nào bị tính 2 lần{note}")
			# Chỉ in vài ví dụ: một tháng dữ liệu có hàng chục đoạn hụt hợp lệ,
			# in hết thì cảnh báo thật chìm nghỉm trong danh sách.
			for g in gaps[:3]:
				print(f"       · {g}")
			if len(gaps) > 3:
				print(f"       · … và {len(gaps) - 3} đoạn nữa")

		billable = sum(flt(r.km_end) - flt(r.km_start) for r in rows)
		print(f"       tổng KM tính tiền: {billable:g} km / {len(rows)} chuyến")

	print("\n── BỘ SEED (chỉ đúng khi dữ liệu còn nguyên) ─────────")
	drift = seed_drift()
	if drift:
		print("  BỎ QUA — dữ liệu đã được dùng/sửa sau khi seed:")
		for line in drift:
			print(f"    · {line}")
		print("  Muốn kiểm lại con số: chạy execute(purge=True) rồi verify() ngay sau đó.")
	else:
		s15 = vm.get_today_stats("2026-09-15")
		expect("15/09 Chờ duyệt", s15["pending"], 3)
		expect("15/09 Đã xếp xe", s15["scheduled"] + s15["confirmed"], 1)
		expect("15/09 Đang chạy", s15["in_progress"], 1)
		expect("15/09 Hoàn thành", s15["completed"], 4)
		expect("15/09 Đã hủy", s15["cancelled"], 1)

		s16 = vm.get_today_stats("2026-09-16")
		expect("16/09 Chờ duyệt", s16["pending"], 3)
		expect("16/09 Đã xếp xe", s16["scheduled"] + s16["confirmed"], 3)
		expect("16/09 Đang chạy", s16["in_progress"], 0)
		expect("16/09 Hoàn thành", s16["completed"], 0)

		km = vm.get_trip_report("2026-09-01", "2026-09-30")["summary"]["km_by_vehicle"]
		expect("Bus 1 km", km.get("Bus 1"), 174.0)
		expect("Bus 2 km", km.get("Bus 2"), 12.0)
		expect("Kia km", km.get("Kia"), 58.0)

		# Tài xế suy từ xe, không còn bảng ánh xạ cứng.
		for key, vehicle in VEHICLES.items():
			driver = frappe.db.get_value(
				"TIQN Zalo Role Map",
				{"role": "driver", "vehicle": vehicle, "disabled": 0},
				"name", order_by="creation asc",
			)
			expect(f"{key} có tài xế", bool(driver), True)
			if driver:
				expect(f"{key} chuyến hôm 16/09",
				       len(vm.get_today_trips_by_driver(driver, "2026-09-16")), 1)

	print("\n" + ("TẤT CẢ INVARIANT ĐỀU ĐẠT" if not problems
	              else f"{len(problems)} LỖI: {problems}"))
	return problems
