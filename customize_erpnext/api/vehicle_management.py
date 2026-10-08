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
from frappe.rate_limiter import rate_limit
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

# Đăng nhập bằng mật khẩu (Phase 1) ĐÃ BỎ 23/09/2026. Danh tính giờ là tài khoản
# Zalo: `get_user_by_zalo_id()` trả về vai trò, và vai trò đó là đăng nhập.

# Per-IP rate limits on the three endpoints worth abusing. Generous on purpose: a
# Zalo Mini App runs in a webview on a phone, so a whole 4G cell can arrive behind
# ONE carrier-NAT address. These numbers stop a script, not a busy morning.
#
# 🔴 Do NOT use site_config["rate_limit"] for this. Despite the name it is not a
# request counter and not per-IP: RateLimiter keys on
# f"rate-limit-counter-{window_number}" with no identity in it, and counts
# MICROSECONDS OF REQUEST TIME for the WHOLE SITE. Setting it means that once every
# user together has spent N seconds of server time in the window, everyone gets 429
# - the nine dispatchers on Desk included. Wrong tool entirely.
RATE_PHONE_DECODE = 60   # per IP per hour: a Zalo token is single-use, 2-min expiry
RATE_EXCEL = 20          # per IP per hour: every call writes a file to disk

# How long before departure a fixed trip appears. A shuttle created at dawn for a
# 17:15 run sits on the board all day looking like something that needs attention,
# and the dispatcher cannot tell it apart from a trip that is actually due.
SCHEDULE_LEAD_MINUTES = 15

REQUEST_FIELDS = [
	"name", "employee_name", "employee_id_display", "zalo_user_id",
	"request_time", "return_time", "from_location", "to_location", "purpose",
	"passenger_count", "notes", "status", "rejection_reason", "assigned_trip",
	"submit_time", "creation", "modified",
]

TRIP_FIELDS = [
	# `driver` KHÔNG có ở đây: chuyến thuộc về XE, tài xế được suy ra lúc đọc.
	"name", "trip_name", "trip_type", "template_id", "vehicle",
	"trip_date", "depart_time", "from_location", "to_location", "purpose",
	"dispatcher_note", "notes", "status", "route_changed",
	"km_start", "km_end", "total_km", "km_start_photo", "km_end_photo",
	"start_gps_lat", "start_gps_lng", "end_gps_lat", "end_gps_lng",
	"additional_cost", "checkin_notes", "checkout_notes",
	"checkin_time", "checkout_time", "cancelled_reason",
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
# (template_id, total_km...) is derived and must stay derived.
TRIP_EDITABLE_FIELDS = {
	"trip_name", "trip_type", "vehicle", "trip_date", "depart_time",
	"from_location", "to_location", "purpose", "dispatcher_note", "notes", "additional_cost",
	"status", "cancelled_reason", "route_changed",
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
	"checkin_time", "checkout_time",
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
	"name", "schedule_name", "vehicle", "depart_time",
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


def _driver_lookup(vehicle_names):
	"""Xe -> tài xế đang được gán cho xe đó, một truy vấn.

	🔴 Chuyến LUÔN gán theo XE, không gán cho người (23/09/2026). Tài xế của một chuyến
	được suy ra lúc đọc, từ xe. Tài xế xe nào thì thấy chuyến của xe đó.

	Vì sao không lưu `driver` trên chuyến: lưu tức là giữ một bản sao thứ hai của
	"ai lái xe này". Bản sao đó đã mục nát hai lần trong dự án này - lần đổi tên tài xế
	làm chết 6 lịch cố định, và ba tài khoản Zalo cùng trỏ về một tài xế.

	⚠ Đây là câu trả lời cho câu hỏi BÂY GIỜ ("gọi ai về chuyến này"), không phải câu
	hỏi LÚC ĐÓ. Xem get_trip_report() về việc vì sao không còn thống kê km theo tài xế.

	Nhiều tài khoản cùng một xe (tài xế thay ca) thì lấy bản ghi tạo sớm nhất, bỏ qua
	`disabled`, để kết quả ổn định giữa các lần đọc.
	"""
	vehicle_names = [n for n in set(vehicle_names) if n]
	if not vehicle_names:
		return {}

	out = {}
	for d in frappe.get_all(
		"TIQN Zalo Role Map",
		filters={"role": "driver", "disabled": 0, "vehicle": ("in", vehicle_names)},
		fields=["name", "display_name", "phone", "id_by_oa", "is_leader", "vehicle"],
		order_by="creation asc",
		limit_page_length=0,
	):
		out.setdefault(d.vehicle, d)
	return out


def _vehicle_of_driver(driver_name):
	"""Xe của một tài xế. Lọc "chuyến của tài xế X" thực chất là lọc theo xe của X."""
	return frappe.db.get_value(
		"TIQN Zalo Role Map", {"name": driver_name, "role": "driver"}, "vehicle"
	)


def _decorate_trips(rows):
	"""Add vehicle_name / license_plate / driver_name and fix the wire formats.

	The contract requires these three to be present whenever the trip has a
	vehicle or a driver, so they are resolved in bulk rather than per row.
	"""
	vehicles = _vehicle_lookup([r.get("vehicle") for r in rows])
	drivers = _driver_lookup([r.get("vehicle") for r in rows])

	for row in rows:
		vehicle = vehicles.get(row.get("vehicle"))
		driver = drivers.get(row.get("vehicle"))
		# Khoá `driver` vẫn có trong payload cho client, nhưng là giá trị SUY RA từ xe,
		# không phải cột lưu trên chuyến.
		row["driver"] = driver.name if driver else None
		row["vehicle_name"] = vehicle.vehicle_name if vehicle else None
		row["license_plate"] = vehicle.license_plate if vehicle else None
		row["driver_name"] = driver.display_name if driver else None
		row["driver_phone"] = driver.phone if driver else None
		# Both, because they are different things and only one opens a chat.
		# docname CHÍNH LÀ zalo_user_id - không còn field rời để lệch nhau.
		row["driver_zalo_user_id"] = driver.name if driver else None
		row["driver_zalo_id_by_oa"] = driver.id_by_oa if driver else None

		row["trip_date"] = _fmt_date(row.get("trip_date"))
		row["depart_time"] = _fmt_time(row.get("depart_time"))
		for field in ("checkin_time", "checkout_time", "creation", "modified"):
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
	return data


# ---------------------------------------------------------------------------
# 3.1 Auth & Role
# ---------------------------------------------------------------------------
ZALO_GRAPH_PHONE_URL = "https://graph.zalo.me/v2.0/me/info"
ZALO_TIMEOUT_SECONDS = 10

# docs.zaloplatforms.com/docs/MA/api/errorCode. Zalo's own text is four terse English
# words that do not say WHOSE problem it is, and the difference matters enormously:
# 116/117/118 are this server's configuration and no amount of Mini App debugging will
# help, while 114/115/119 are the token and no amount of key-swapping will.
#
# 118 deserves its own note. "code is invalid - code belongs to different application"
# is what you get when the secret key is a perfectly valid secret OF THE WRONG ZALO
# APP. Read as plain English it sounds like the token is broken; it is not.
# 🔴 Plain strings, NOT _() calls. `_()` at module level resolves once at import and
# freezes whatever language that worker happened to boot in; every later request then
# gets that same language. Translation happens at throw time below.
ZALO_SERVER_CONFIG_ERRORS = {
	116: "zalo_app_vehicle_management_secret_key is empty in site_config.json on this server.",
	117: ("Zalo rejected this server's zalo_app_vehicle_management_secret_key: the value in site_config.json "
	      "is not a valid App Secret Key. Get it from developers.zalo.me, in the management "
	      "page of the Zalo app this Mini App belongs to."),
	118: ("This server's zalo_app_vehicle_management_secret_key belongs to a DIFFERENT Zalo app than the one "
	      "the Mini App logged in with. The key itself is valid - it is the wrong app. "
	      "Check that site_config.json holds the secret of the same app."),
}

ZALO_CALLER_ERRORS = {
	114: "No phone token was sent.",
	115: "Zalo says this phone token is not valid.",
	119: ("This phone token has already been used. Each token works once and expires after "
	      "2 minutes - call getPhoneNumber() again for a fresh one rather than retrying "
	      "this request."),
	-1401: "The user has to authorise the Mini App before the phone number can be read.",
}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=RATE_PHONE_DECODE, seconds=60 * 60, methods="POST")
def decode_phone_token(phone_token, access_token, zalo_user_id=None):
	"""Turn the token Zalo's getPhoneNumber() hands the Mini App into a real number.

	Returns {"phone", "phone_local", "raw", "saved_to"}.

	POST only, and deliberately so: it reaches an external service and it writes.
	A GET would be rolled back by frappe/app.py sync_database() - the same trap that
	made download_trip_report_excel hand out URLs for files it had just deleted.

	`zalo_user_id` is optional. Pass it and the number is written straight onto that
	TIQN Zalo Role Map row, which saves the Mini App a second round trip and, more
	importantly, stops a decoded phone number from travelling back out to the client
	and in again just to be stored.
	"""
	_guard("TIQN Zalo Role Map", "write" if zalo_user_id else "read")

	phone_token = (phone_token or "").strip()
	access_token = (access_token or "").strip()
	if not phone_token or not access_token:
		frappe.throw(_("phone_token and access_token are required"))

	# 🔴 No default. The spec suggested falling back to "YOUR_ZALO_APP_SECRET_KEY",
	# which would send a placeholder to Zalo and come back with a generic failure -
	# the one error message that tells nobody the key was never configured. And a
	# real secret must never sit in source: this file is in git and app/public is
	# served without authentication.
	secret_key = frappe.conf.get("zalo_app_vehicle_management_secret_key")
	if not secret_key:
		frappe.throw(
			_("zalo_app_vehicle_management_secret_key is not set in site_config.json - ask the administrator "
			  "to add it before using Zalo phone lookup")
		)

	import requests

	try:
		# A request with no timeout can hold a gunicorn worker until the 120s SIGKILL
		# (config/supervisor.conf: -t 120); Zalo being slow must not cost us a worker.
		resp = requests.get(
			ZALO_GRAPH_PHONE_URL,
			headers={
				"access_token": access_token,
				"code": phone_token,
				"secret_key": secret_key,
			},
			timeout=ZALO_TIMEOUT_SECONDS,
		)
		data = resp.json()
	except requests.Timeout:
		frappe.throw(_("Zalo did not answer within {0} seconds").format(ZALO_TIMEOUT_SECONDS))
	except (requests.RequestException, ValueError):
		# 🔴 Never put the exception text in the message: it can quote the request
		# headers back, and those carry the app secret. The detail goes to the error
		# log, which only Desk users can read.
		frappe.log_error(title="Zalo phone lookup failed", message=frappe.get_traceback())
		frappe.throw(_("Could not reach Zalo to look up the phone number"))

	code = cint(data.get("error"))
	if code != 0 or not (data.get("data") or {}).get("number"):
		message = data.get("message") or _("unknown error")

		# 🔴 Zalo validates the SESSION first and the SECRET KEY second, so a wrong
		# secret only surfaces once a real access_token is sent. A made-up token
		# returns "Session key invalid" and proves nothing about the key - a false
		# all-clear I gave once already (21/09/2026). Do not test this with fake
		# tokens and conclude anything.
		if code in ZALO_SERVER_CONFIG_ERRORS or "secret_key" in str(message):
			frappe.throw("{0} ({1} {2}: {3})".format(
				_(ZALO_SERVER_CONFIG_ERRORS.get(code, ZALO_SERVER_CONFIG_ERRORS[117])),
				_("Zalo error"), code, message,
			))

		if code in ZALO_CALLER_ERRORS:
			frappe.throw("{0} ({1} {2}: {3})".format(
				_(ZALO_CALLER_ERRORS[code]), _("Zalo error"), code, message
			))

		# Unmapped: pass Zalo's own wording on. It says nothing about our key.
		frappe.throw(_("Zalo refused the phone token: {0} ({1} {2})").format(
			message, _("Zalo error"), code
		))

	raw = str(data["data"]["number"]).strip()
	phone, phone_local = _format_zalo_phone(raw)

	saved_to = None
	if zalo_user_id:
		zalo_user_id = str(zalo_user_id).strip()
		name = frappe.db.get_value("TIQN Zalo Role Map", {"zalo_user_id": zalo_user_id}, "name")
		if not name:
			frappe.throw(
				_("No Zalo Role Map entry for {0} - it must exist before a phone number "
				  "can be stored on it").format(zalo_user_id)
			)
		# db_set: one denormalised field, and a save() here would re-run validation
		# that has nothing to do with storing a phone number.
		frappe.db.set_value("TIQN Zalo Role Map", name, "phone", phone)
		saved_to = name

	return {"phone": phone, "phone_local": phone_local, "raw": raw, "saved_to": saved_to}


@frappe.whitelist(methods=["POST", "PUT"])
def update_zalo_id_by_oa(zalo_user_id, id_by_oa):
	"""Store getUserInfo().idByOA on the caller's TIQN Zalo Role Map row.

	The Mini App can also PUT this straight to /api/resource/TIQN Zalo Role Map/<name>
	- the key already has write permission. This endpoint exists so that path is not
	the only one: it writes exactly one field, refuses a blank, and cannot be used to
	change a role, which the generic REST route can.

	Separate from update_zalo_user_id() because `id_by_oa` lives only on the Role Map,
	while that one writes to three different doctypes. Folding them together would
	mean a `role` argument that silently ignores this field for two of its three
	values.
	"""
	_guard("TIQN Zalo Role Map", "write")

	zalo_user_id = (zalo_user_id or "").strip()
	id_by_oa = (id_by_oa or "").strip()
	if not zalo_user_id or not id_by_oa:
		frappe.throw(_("zalo_user_id and id_by_oa are required"))

	name = frappe.db.get_value("TIQN Zalo Role Map", {"zalo_user_id": zalo_user_id}, "name")
	if not name:
		frappe.throw(
			_("No Zalo Role Map entry for {0}").format(zalo_user_id), frappe.DoesNotExistError
		)

	frappe.db.set_value("TIQN Zalo Role Map", name, "id_by_oa", id_by_oa)
	return {"name": name, "zalo_user_id": zalo_user_id, "id_by_oa": id_by_oa}


def _format_zalo_phone(raw):
	"""Zalo's "84962200089" -> ("+84-962200089", "0962200089").

	Two spellings on purpose. `phone` is the format the Mini App asked for. But
	`TIQN Zalo Role Map.phone` holds local numbers ("0905..."), so a lookup that compares
	against the +84 form would never match anything - a mismatch that shows up as
	"driver not found" long after anyone remembers this conversion happened.
	`phone_local` is the one to compare with.

	Only the digits are trusted; Zalo has been seen returning both "84..." and a
	leading-zero local number.
	"""
	digits = "".join(ch for ch in str(raw) if ch.isdigit())
	if not digits:
		frappe.throw(_("Zalo returned a phone number that has no digits in it"))

	if digits.startswith("84") and len(digits) > 9:
		subscriber = digits[2:]
	elif digits.startswith("0"):
		subscriber = digits[1:]
	else:
		subscriber = digits

	return f"+84-{subscriber}", f"0{subscriber}"


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
		["zalo_user_id", "id_by_oa", "display_name", "phone", "role", "vehicle",
		 "is_leader", "disabled", "employee_id"],
		as_dict=True,
	)
	if not row:
		return None

	# Bị chặn thì coi như chưa map: Mini App đã biết cách xử lý `null` (màn chọn vai
	# trò), còn trả về một vai trò kèm cờ `disabled` thì mọi chỗ gọi đều phải nhớ kiểm
	# cờ đó - sót một chỗ là lọt.
	if cint(row.disabled):
		return None

	result = {
		"zalo_user_id": row.zalo_user_id,
		# The ID openChat() actually needs. zalo_user_id is app-scoped and will not
		# open a chat, so the two are never interchangeable - see TIQN Zalo Role Map.
		"id_by_oa": row.id_by_oa,
		"display_name": row.display_name,
		# Filled by decode_phone_token(); null until the user has granted Zalo's
		# phone permission at least once.
		"phone": row.phone,
		"role": row.role,
	}

	if row.role == "driver":
		result["is_leader"] = cint(row.is_leader)
		result["vehicle"] = row.vehicle
		vehicle = (
			frappe.db.get_value(
				"TIQN Vehicle", row.vehicle, ["vehicle_name", "license_plate"], as_dict=True
			)
			if row.vehicle
			else None
		)
		result["vehicle_name"] = vehicle.vehicle_name if vehicle else None
		result["license_plate"] = vehicle.license_plate if vehicle else None
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


# Written into dispatcher_note, so it is STORED DATA, not a UI label. That is why it
# is not wrapped in _(): a translated string would freeze whichever language the
# caller happened to have, and the note is read by Vietnamese drivers in the Mini App
# long after the request that created it is gone. Same exception as the
# vehicle-dispatch page content.
EXTRA_STOPS_PREFIX = "Ghé thêm"


def _extra_destinations(requests, destination):
	"""Điểm đến của các yêu cầu được gộp mà KHÁC điểm đến của chuyến.

	A combined trip has one `to_location` - the first request's. The others are not
	lost: they go into dispatcher_note so the driver reads them in the same place as
	every other instruction. They are deliberately NOT concatenated into
	`to_location`: that field is matched, filtered and grouped in reports, and
	"Sân bay Chu Lai | Ga Quảng Ngãi" is one place that does not exist.

	Order follows `request_names`, repeats collapse, blanks drop.
	"""
	seen = {(destination or "").strip().lower()}
	out = []
	for doc in requests:
		text = (doc.to_location or "").strip()
		if text and text.lower() not in seen:
			seen.add(text.lower())
			out.append(text)
	return out


def _build_dispatch_note(extra, typed):
	"""Extra destinations first, then whatever the dispatcher typed.

	The drop-offs are what the driver has to act on; a dispatcher's remark that
	pushed them below the fold would be worse than useless.
	"""
	parts = []
	if extra:
		parts.append(f"{EXTRA_STOPS_PREFIX}: " + ", ".join(extra))
	if typed and typed.strip():
		parts.append(typed.strip())
	return "\n".join(parts) or None


def _merge_purposes(requests):
	"""The reasons of the merged requests as one " | " string.

	Order follows `request_names` so the trip reads in the order the dispatcher
	picked. Blanks are dropped and repeats collapse - three people going to the same
	medical check should read "Kham suc khoe", not the same phrase three times.
	Returns None rather than "" so a trip with nothing to say leaves the field empty
	instead of storing a blank string.
	"""
	seen, parts = set(), []
	for doc in requests:
		text = (doc.purpose or "").strip()
		if text and text.lower() not in seen:
			seen.add(text.lower())
			parts.append(text)
	return " | ".join(parts) or None


@frappe.whitelist(methods=["POST", "PUT"])
def combine_requests_to_trip(
	request_names,
	vehicle,
	trip_date=None,
	depart_time=None,
	from_location=None,
	to_location=None,
	purpose=None,
	notes=None,
	dispatcher_note=None,
	trip_type="on_demand",
):
	"""Create one trip carrying several approved requests.

	Không có tham số `driver`: chuyến gán theo XE. Tài xế được suy ra lúc đọc, từ xe.

	`purpose` is likewise optional: left out, it is gathered from the requests being
	merged (see _merge_purposes). A dispatcher who types one keeps theirs.

	The trip gets ONE `to_location` - the first request's, unless the caller names
	another. Every other destination among the merged requests is listed in
	`dispatcher_note` instead of being concatenated into `to_location`.

	Passengers are NOT a parameter. They are derived from `request_names`, because
	the passenger rows carry the request link that TIQNVehicleTrip.sync_linked_requests()
	follows to move each request to `assigned` and to hand it back to `approved` if
	the trip is later cancelled. A client-supplied passenger list would quietly cut
	that link and strand the requests.
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
	# ONE destination, the first request's. The rest are listed in dispatcher_note by
	# _build_dispatch_note() - see _extra_destinations() for why they must not be
	# joined into this field.
	destination = to_location or first.to_location

	trip = frappe.get_doc(
		{
			"doctype": "TIQN Vehicle Trip",
			"trip_type": trip_type or "on_demand",
			"vehicle": vehicle,
			"trip_date": getdate(trip_date) if trip_date else getdate(first.request_time),
			"depart_time": depart_time or get_time(first.request_time),
			"from_location": from_location or first.from_location,
			"to_location": destination,
			"purpose": purpose or _merge_purposes(requests),
			"notes": notes,
			"dispatcher_note": _build_dispatch_note(
				_extra_destinations(requests, destination), dispatcher_note
			),
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
		# Chuyến gán theo XE, nên "chuyến của tài xế X" = chuyến của xe X lái.
		# Tài xế chưa được gán xe thì không có chuyến nào: trả RỖNG, không trả hết.
		filters["vehicle"] = _vehicle_of_driver(driver) or "__khong-co-xe__"
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
	"""driver_name là docname của `TIQN Zalo Role Map`, tức chính Zalo user ID."""
	_guard("TIQN Vehicle Trip")
	return _decorate_trips(frappe.get_all(
		"TIQN Vehicle Trip",
		filters={
			"vehicle": _vehicle_of_driver(driver_name) or "__khong-co-xe__",
			"trip_date": getdate(date) if date else getdate(nowdate()),
		},
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
	"""Lịch cố định của một tài xế, mỗi lịch kèm cờ đã tạo chuyến hôm nay chưa.

	🔴 "Của tài xế này" = của XE mà tài xế đó lái. Lịch cố định không còn field `driver`
	(23/09): nó nói xe nào chạy ca nào, thế là đủ. Tài xế xe nào thì thấy lịch xe đó.

	Tài xế chưa được gán xe thì không có lịch nào - trả rỗng, không trả hết.
	"""
	_guard("TIQN Fixed Trip Schedule")
	on_date = getdate(trip_date) if trip_date else getdate(nowdate())

	vehicle = _vehicle_of_driver(driver_name)
	if not vehicle:
		return []

	templates = frappe.get_all(
		"TIQN Fixed Trip Schedule",
		filters={"is_active": 1, "vehicle": vehicle},
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
	depart_time=None,
	from_location=None,
	to_location=None,
	trip_type="on_demand",
	purpose=None,
	dispatcher_note=None,
	trip_name=None,
	notes=None,
	status=None,
	template_id=None,
	passengers=None,
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
			"trip_date": getdate(trip_date),
			"depart_time": depart_time,
			"from_location": from_location,
			"to_location": to_location,
			"purpose": purpose,
			"dispatcher_note": dispatcher_note,
			"notes": notes,
			"status": status or "scheduled",
			"passengers": _build_passenger_rows(passengers),
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
			"trip_date": on_date,
			"depart_time": template.depart_time,
			"from_location": template.from_location,
			"to_location": template.to_location,
			"status": "confirmed",
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
			"vehicle": doc.vehicle,
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
			"name", "vehicle", "trip_name", "from_location", "to_location",
			"depart_time", "checkin_time", "km_start", "route_changed",
		],
		order_by="checkin_time desc",
	)
	by_vehicle = {}
	for row in running:
		by_vehicle.setdefault(row.vehicle, row)

	drivers = _driver_lookup([v.name for v in vehicles])

	for vehicle in vehicles:
		# Tài xế thuộc về XE, nên gắn thẳng lên xe - chuyến chỉ mượn lại.
		driver = drivers.get(vehicle.name)
		vehicle["driver"] = driver.name if driver else None
		vehicle["driver_name"] = driver.display_name if driver else None

		trip = by_vehicle.get(vehicle.name)
		if trip:
			trip["driver"] = vehicle["driver"]
			trip["driver_name"] = vehicle["driver_name"]
			trip["depart_time"] = _fmt_time(trip.get("depart_time"))
			trip["checkin_time"] = _fmt_datetime(trip.get("checkin_time"))
		vehicle["current_trip"] = trip

	return vehicles


@frappe.whitelist(methods=["GET", "POST"])
def get_vehicle(name):
	"""One vehicle, same shape as a row of get_vehicles() including `current_trip`.

	The Mini App has been calling this all along and getting "Method Not Found" -
	it was simply never written. Built on get_vehicles() rather than fetching the
	doc directly so the two can never disagree about what a vehicle looks like;
	`current_trip` in particular is computed, not stored.
	"""
	_guard("TIQN Vehicle")
	if not frappe.db.exists("TIQN Vehicle", name):
		frappe.throw(_("Vehicle {0} not found").format(name), frappe.DoesNotExistError)

	for vehicle in get_vehicles():
		if vehicle["name"] == name:
			return vehicle
	return None


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
	"""Tài xế đang hoạt động, cho màn chọn tài xế.

	Tài xế = bản ghi `TIQN Zalo Role Map` có `role = driver` và chưa bị `disabled`.

	`zalo_user_id` bằng chính docname nên không giấu được, nhưng `id_by_oa` thì CỐ Ý
	không trả: đây là danh sách MỌI tài xế, đọc được bằng API key nằm trong client.
	Muốn ID mở chat thì lấy `driver_zalo_id_by_oa` trong object chuyến - chỉ lộ tài xế
	của đúng chuyến đang xem.
	"""
	_guard("TIQN Zalo Role Map")

	drivers = frappe.get_all(
		"TIQN Zalo Role Map",
		filters={"role": "driver", "disabled": 0},
		fields=["name", "display_name", "phone", "vehicle", "is_leader"],
		order_by="display_name asc",
		limit_page_length=0,
	)
	if not drivers:
		return []

	vehicles = {
		v.name: v
		for v in frappe.get_all(
			"TIQN Vehicle",
			filters={"name": ("in", [d.vehicle for d in drivers if d.vehicle])},
			fields=["name", "vehicle_name", "license_plate"],
			limit_page_length=0,
		)
	}

	for driver in drivers:
		vehicle = vehicles.get(driver.vehicle)
		# Tên cũ giữ nguyên để client không phải đổi: `driver_name` và
		# `assigned_vehicle` là hai khoá Mini App đang đọc.
		driver["driver_name"] = driver.display_name
		driver["assigned_vehicle"] = driver.vehicle
		driver["assigned_vehicle_name"] = (
			f"{vehicle.vehicle_name} \u2022 {vehicle.license_plate}" if vehicle else driver.vehicle
		)
		driver["is_active"] = 1  # đã lọc disabled=0; giữ khoá cũ cho client

	return drivers


# 🔴 `verify_driver_login()` ĐÃ XOÁ 23/09/2026, cùng field `password` và bốn hàm khoá
# chống dò mật khẩu (`_login_cache_key`, `_check_login_lockout`, `_record_failed_login`,
# `_clear_failed_logins`).
#
# Nó ra đời vì lúc đó chưa nối được danh tính Zalo. Giờ đã nối: `get_user_by_zalo_id()`
# trả vai trò của tài khoản Zalo, và vai trò đó CHÍNH LÀ đăng nhập. Giữ thêm một đường
# đăng nhập thứ hai bằng tên + mật khẩu dùng chung, trên một DocType không còn tồn tại,
# là giữ một cánh cửa mà không ai nhớ ra để khoá.
#
# Chặn một người dùng: đặt cờ `disabled` trên bản ghi Zalo Role Map của họ.


def get_dispatcher_zalo_id():
	"""The dispatcher's OA-scoped Zalo id, or None.

	🔴 Returns `id_by_oa`, NOT `zalo_user_id`. This used to return `zalo_user_id`,
	which was wrong: that id is APP-scoped and openChat() cannot use it. It looks
	like a valid id and it is a valid id - just not for opening a chat, so the
	failure is a chat that never opens with nothing to explain why.

	No fallback to `zalo_user_id` on purpose. A missing chat button is honest; a
	button that silently does nothing is a bug report nobody can reproduce. Empty
	until the Mini App is verified by the OA, or the dispatcher follows the linked OA.
	"""
	return frappe.db.get_value(
		"TIQN Zalo Role Map",
		{"role": "dispatcher", "id_by_oa": ("is", "set")},
		"id_by_oa",
		order_by="modified desc",
	)


# Chỉ còn `requester`: đó là khoá `zalo_user_id` nằm trên bản ghi YÊU CẦU, để biết ai đã
# đặt xe.
#
# `driver` và `dispatcher` đã bỏ: danh tính của họ LÀ bản ghi `TIQN Zalo Role Map`, mà
# docname của bản ghi đó chính là zalo_user_id - ghi id lên chính nó là thao tác vô
# nghĩa. Từ chối thẳng kèm lời giải thích, còn hơn im lặng chấp nhận một lời gọi không
# làm gì.
ZALO_ID_TARGETS = {
	"requester": "TIQN Vehicle Request",
}


@frappe.whitelist(methods=["POST", "PUT"])
def update_zalo_user_id(role, doc_name, zalo_user_id):
	"""Store the Zalo id the Mini App just read from getUserInfo().

	The id is what openChat() needs to put two people in a conversation, and the
	Mini App is the only place it can be obtained - so it has to travel back here.

	⚠ Nothing proves the caller owns the id being written. Every Mini App install
	shares one API key, so this endpoint would let a holder of that key point any
	driver's chat at themselves. It is deliberately narrow because of that: the
	target doctype comes from ZALO_ID_TARGETS rather than from the client, and only
	this one field is written. Real ownership needs Phase 2 server-side identity -
	the same gap recorded for get_requests() and get_my_requests().
	"""
	role = (role or "").strip().lower()
	if role in ("driver", "dispatcher"):
		frappe.throw(
			_("A {0} is identified by their TIQN Zalo Role Map record, whose name IS the "
			  "Zalo user ID - there is nothing to write. Create or update that record "
			  "instead.").format(role)
		)

	doctype = ZALO_ID_TARGETS.get(role)
	if not doctype:
		frappe.throw(_("Unknown role {0}").format(role))

	_guard(doctype, "write")

	if not frappe.db.exists(doctype, doc_name):
		frappe.throw(_("{0} {1} not found").format(_(doctype), doc_name), frappe.DoesNotExistError)

	zalo_user_id = (zalo_user_id or "").strip()
	if not zalo_user_id:
		frappe.throw(_("Zalo User ID is required"))

	# db_set, not doc.save(): this is one denormalised field and saving a request
	# would re-run the workflow validation that update_request() enforces - a
	# requester re-opening the app should not be blocked from storing a chat id
	# because their request has since been approved.
	frappe.db.set_value(doctype, doc_name, "zalo_user_id", zalo_user_id)

	return {"doctype": doctype, "name": doc_name, "zalo_user_id": zalo_user_id}


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
		# Chuyến gán theo XE, nên "chuyến của tài xế X" = chuyến của xe X lái.
		# Tài xế chưa được gán xe thì không có chuyến nào: trả RỖNG, không trả hết.
		filters["vehicle"] = _vehicle_of_driver(driver) or "__khong-co-xe__"

	trips = _decorate_trips(frappe.get_all(
		"TIQN Vehicle Trip",
		filters=filters,
		fields=TRIP_FIELDS,
		order_by="trip_date asc, depart_time asc",
		limit_page_length=0,
	))

	km_by_vehicle = {}
	# Keyed by docname, so two vehicles sharing a display name stay apart - which
	# km_by_vehicle, keyed by the name people type, cannot do.
	by_vehicle = {}
	total_km = total_cost = 0.0
	completed = cancelled = 0

	for trip in trips:
		# _decorate_trips() already resolved the names; fall back to the docname so
		# a deleted vehicle still groups under something readable.
		trip["vehicle_name"] = trip.get("vehicle_name") or trip.get("vehicle")

		if trip.status == "completed":
			completed += 1
		elif trip.status == "cancelled":
			cancelled += 1

		km = flt(trip.total_km)
		total_km += km
		total_cost += flt(trip.additional_cost)

		if km:
			km_by_vehicle[trip["vehicle_name"]] = flt(km_by_vehicle.get(trip["vehicle_name"], 0)) + km

			key = trip.get("vehicle") or trip["vehicle_name"]
			entry = by_vehicle.setdefault(
				key,
				{
					"vehicle": trip.get("vehicle"),
					"name": trip["vehicle_name"],
					"license_plate": trip.get("license_plate"),
					"km": 0.0,
					"trips": 0,
				},
			)
			entry["km"] += km
			entry["trips"] += 1

	return {
		"trips": trips,
		"summary": {
			"total_trips": len(trips),
			"total_km": flt(total_km, 1),
			"total_additional_cost": flt(total_cost, 2),
			"completed": completed,
			"cancelled": cancelled,
			# Unchanged shape, still {display name: km} - the Mini App reads this and
			# a rename here would break it. `vehicles` below is the richer view.
			"km_by_vehicle": {k: flt(v, 1) for k, v in km_by_vehicle.items()},
			# 🔴 KHÔNG còn `km_by_driver`. Chuyến gán theo XE, nên "ai lái" chỉ suy được
			# từ tài xế HIỆN TẠI của xe. Với câu hỏi BÂY GIỜ (gọi ai) thì suy là đúng;
			# với câu hỏi LÚC ĐÓ - tháng 9 ai chạy bao nhiêu km - thì sai: tài xế đổi
			# xe là lịch sử bị viết lại, âm thầm. Thà không có con số còn hơn có một
			# con số lặng lẽ đổi nghĩa.
			# Same numbers with the plate attached, biggest first, for a report
			# heading that has to read "Bus 1 - 43A-12345".
			"vehicles": sorted(
				({**v, "km": flt(v["km"], 1)} for v in by_vehicle.values()),
				key=lambda v: v["km"],
				reverse=True,
			),
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
	now = now_datetime()

	schedules = frappe.get_all(
		"TIQN Fixed Trip Schedule",
		filters={"is_active": 1},
		fields=SCHEDULE_FIELDS,
		order_by="depart_time asc, name asc",
		limit_page_length=0,
	)

	created, skipped, not_due, failed = [], [], [], []

	for schedule in schedules:
		allowed = [d.strip() for d in (schedule.days_of_week or "").split(",") if d.strip()]
		if allowed and weekday not in allowed:
			not_due.append(schedule.name)
			continue

		# A trip appears SCHEDULE_LEAD_MINUTES before it leaves, not at dawn for the
		# whole day.
		#
		# 🔴 This used to be an exact string match against the current HH:MM, which
		# meant the job only ever created schedules departing at the very minute cron
		# fired. Cron ran at 06:30 and 17:00; the afternoon shuttles depart at 17:15.
		# They therefore NEVER got created - three vehicles, every working day, and
		# nothing in the log to say so, because a schedule that does not match is
		# simply counted as "not due". Only the demo seeder ever produced them, which
		# is exactly why it looked fine on screen.
		#
		# A window also survives a cron tick that runs a few seconds late, which an
		# exact minute match does not.
		depart = _fmt_time(schedule.depart_time)
		if not force_all:
			minutes_away = (get_datetime(f"{on_date} {depart}") - now).total_seconds() / 60
			if not (0 <= minutes_away <= SCHEDULE_LEAD_MINUTES):
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

		# 🔴 One bad schedule must not take the whole fleet's morning with it.
		# Without this, a single dangling link raised out of the loop and NOTHING
		# got created - every shuttle missing, one traceback in the log, and the
		# working schedules never even tried. Seen for real 21/09/2026: renaming
		# the drivers left all six schedules pointing at TIQN-DRV-00x-old, and
		# set_default_driver() could not heal it because it only fills a BLANK
		# driver, never replaces one that is merely wrong.
		# Savepoint, not a bare rollback: rollback() would throw away the trips
		# already created earlier in this same loop, turning one broken schedule
		# into an empty morning anyway.
		save_point = f"fixed_trip_{schedule.name}".replace("-", "_")
		frappe.db.savepoint(save_point)
		try:
			created.append(_create_trip_from_schedule(schedule, on_date))
		except Exception:
			frappe.db.rollback(save_point=save_point)
			failed.append(schedule.name)
			frappe.log_error(
				title=f"Fixed trip not created: {schedule.name}",
				message=frappe.get_traceback(),
			)

	frappe.db.commit()  # scheduler task: nothing else commits for us

	summary = {
		"date": str(on_date),
		"weekday": weekday,
		"clock": now.strftime("%H:%M"),
		"lead_minutes": SCHEDULE_LEAD_MINUTES,
		"created": created,
		"skipped": skipped,
		"not_due": not_due,
		"failed": failed,
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
	("From", 28), ("To", 28), ("Purpose", 30),
	("KM Start", 12), ("KM End", 12), ("Billable KM", 12),
	("Additional Cost", 18), ("Status", 14), ("Notes", 30),
]
# 1-based column numbers, derived from the headers above rather than written out:
# inserting a column used to mean editing four separate constants and a pair of
# hand-spelled "K2:K" formula ranges, and missing one silently formats the wrong
# column or totals the wrong one.
_COL = {label: i for i, (label, _w) in enumerate(EXCEL_HEADERS, 1)}
KM_COLUMNS = (_COL["KM Start"], _COL["KM End"], _COL["Billable KM"])
TOTAL_KM_COLUMN = _COL["Billable KM"]
COST_COLUMN = _COL["Additional Cost"]
KM_FORMAT = "#,##0.00"
COST_FORMAT = "#,##0"

# How long an exported file survives. The hourly cleanup below removes anything
# older; a download link the user opens straight away does not need to outlive that.
EXPORT_RETENTION_MINUTES = 45


@frappe.whitelist(methods=["GET", "POST"])
@rate_limit(limit=RATE_EXCEL, seconds=60 * 60)
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
			trip.get("purpose") or "",
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
		for column, fmt in ((TOTAL_KM_COLUMN, KM_FORMAT), (COST_COLUMN, COST_FORMAT)):
			letter = get_column_letter(column)
			cell = ws.cell(total, column, f"=SUM({letter}2:{letter}{last})")
			cell.number_format = fmt
			cell.font = Font(bold=True)

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

	# 🔴 This endpoint WRITES, and Frappe throws away the writes of any request
	# whose HTTP method is "safe". frappe/app.py sync_database() commits only for
	# POST/PUT/DELETE/PATCH or when this flag is set - a GET is rolled back.
	# On top of that, File registers a rollback observer: File.on_rollback() sees
	# flags.new_file and calls _delete_file_on_disk(). So a GET here built the
	# spreadsheet, wrote it, returned a correct URL, and then DELETED the file
	# before the response left the server. The link works in the payload and 404s
	# in the browser, with nothing in the log to say why.
	# Seen for real 21/09/2026: the Mini App showed
	# /files/bao-cao-xe-...-260921_105145.xlsx and the file was already gone 80
	# seconds later - long before the 45-minute cleanup could have touched it.
	#
	# Setting the flag, rather than calling frappe.db.commit() here, is deliberate:
	# commit() inside a whitelisted method flushes whatever else the caller had
	# open and makes the test suite leak records into the real database. The flag
	# is read once by the request layer and is simply absent outside a request, so
	# bench console and the tests behave exactly as before.
	frappe.local.flags.commit = True

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
