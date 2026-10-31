# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Config, login and session endpoints - API_CONTRACT.md §2 and §6."""

import os
import re
from urllib.parse import quote, unquote

import frappe
from frappe import _
from frappe.model.rename_doc import rename_doc
from frappe.utils import cint, get_url, get_url_to_form, now_datetime

from customize_erpnext.api.employee_portal.core import (
	API_VERSION,
	SECRET_CONF,
	TOKEN_HEADER,
	PortalError,
	access_payload,
	create_session,
	ctx,
	feature_enabled,
	features,
	fmt_date,
	fmt_datetime,
	hash_token,
	hit_rate_limit,
	portal_api,
	request_header,
	revoke_session,
)
from customize_erpnext.employee_portal.utils import (
	clean_id_by_oa,
	designation_label,
	employee_access,
	find_employees_by_phone,
	get_settings,
	initials,
	is_review_phone,
	local_phone,
	mask_phone,
	setting_int,
	strip_company_suffix,
)
from customize_erpnext.employee_portal.doctype.tiqn_portal_link_request.tiqn_portal_link_request import (
	MAX_REQUESTS_PER_DAY,
	linked_accounts,
	normalise_name,
)
from customize_erpnext.utils import zalo_graph

# The whole factory WiFi is ONE public IP (NAT): after a payslip is published hundreds of
# people sign in within minutes. Zalo must vouch for every token, and each Zalo ID has its
# own tight limit, so the per-IP limit only stops a runaway script.
LOGIN_PER_IP_PER_MINUTE = 3000
UPLOAD_ACCEPT = ["image/jpeg", "image/png", "image/webp", "application/pdf"]


def employee_payload(employee):
	e = frappe.db.get_value(
		"Employee",
		employee,
		[
			"name",
			"employee_name",
			"designation",
			"department",
			"custom_section",
			"custom_group",
			"date_of_joining",
			"relieving_date",
			"image",
		],
		as_dict=True,
	)
	if not e:
		return None
	return {
		"employee_id": e.name,
		"full_name": e.employee_name,
		"initials": initials(e.employee_name),
		"designation": designation_label(e.designation),
		"department": strip_company_suffix(e.department),
		"section": e.custom_section,
		"group": e.custom_group,
		"date_of_joining": fmt_date(e.date_of_joining),
		"relieving_date": fmt_date(e.relieving_date),
		"avatar_url": avatar_url(e.image),
	}


def avatar_url(image):
	"""Employee.image as an absolute URL the Mini App can load WITHOUT a session.

	Read from the field, never built from "{id} {name}.jpg": the photo tool saves .png
	as well as .jpg. Private files (/private/files/...) need an ERP session the Mini
	App does not have, and missing files would show a broken image -> None, and the
	app falls back to initials. `?v=<mtime>` because a retaken photo keeps its name.
	"""
	if not image or not image.startswith("/files/"):
		return None
	path = frappe.get_site_path("public", unquote(image).split("?")[0].lstrip("/"))
	if not os.path.isfile(path):
		return None
	return get_url(f"{quote(unquote(image).split('?')[0])}?v={int(os.path.getmtime(path))}")


def oa_payload(account):
	followed = bool(cint(account.get("followed_oa")))
	return {
		"followed": followed,
		"show_invite": (not followed) and not cint(account.get("oa_invite_dismissed")) and feature_enabled("oa_invite"),
	}


def chat_payload():
	"""Where the "Chat with C&B" button goes: a 1-1 chat with the payroll staff member
	set in Settings (their ID by OA), else the Official Account when its chat is on,
	else None (hide the button). Never falls back to a zalo_user_id - it would show a
	button that opens nothing. Authenticated endpoints only: it is a person's ID."""
	s = get_settings()
	if s.get("cb_chat_id_by_oa"):
		return {"type": "user", "id": s.cb_chat_id_by_oa, "name": s.get("cb_chat_name") or None}
	if cint(s.oa_chat_enabled) and s.oa_id:
		return {"type": "oa", "id": s.oa_id, "name": s.company_short_name or s.company_display_name or None}
	return None


# ---------------------------------------------------------------------------
@portal_api(methods=("GET",), auth=False)
def get_config():
	s = get_settings()
	company = frappe.defaults.get_global_default("company")
	return {
		"api_version": API_VERSION,
		"min_client_version": (s.min_client_version or "1.0.0").strip(),
		"company": {
			"name": s.company_display_name or company,
			"short_name": s.company_short_name or None,
			"logo_url": None,  # deprecated 1.5.0: the Mini App shows the Zalo App logo
		},
		"contacts": {"hr_hotline": s.hr_hotline or None, "company_phone": s.company_phone or None},
		"legal": {
			"privacy_policy_url": get_url("/portal-policy"),
			"terms_url": get_url("/portal-terms"),
			"version": fmt_date(s.legal_version) if s.legal_version else None,
		},
		"oa": {"oa_id": s.oa_id or None, "chat_enabled": bool(cint(s.oa_chat_enabled) and s.oa_id)},
		"uploads": {
			"max_files": setting_int("max_files", 5),
			"max_size_mb": setting_int("max_file_size_mb", 5),
			"accept": UPLOAD_ACCEPT,
		},
		"read_only_days": setting_int("read_only_days", 30),
		"dev_login": dev_login_enabled(),
		"features": features(),
		# 1.9.0: starting state of the "Ẩn khoản 0đ" toggle (false = hide 0 lines when a
		# payslip opens). get_payslip still sends every line with include_zero=1.
		"payslip": {"show_zero_lines": bool(cint(s.show_zero_lines))},
	}


# ---------------------------------------------------------------------------
@portal_api(methods=("POST",), auth=False)
def login(access_token=None, phone_token=None):
	"""Zalo always vouches for WHO (user id from access_token). The phone comes from
	Zalo when phone_token is sent, otherwise from the account (assigned by HR or saved
	at an earlier sign-in). No phone at all -> NO_PHONE + the user's Zalo ID for HR."""
	access_token = (access_token or "").strip()
	phone_token = (phone_token or "").strip()
	if not access_token:
		raise PortalError("ZALO_TOKEN_INVALID", _("Missing Zalo access token."), field="access_token")

	hit_rate_limit(f"login-ip:{getattr(frappe.local, 'request_ip', '')}", LOGIN_PER_IP_PER_MINUTE, 60)

	try:
		raw_phone = None
		if phone_token:
			# Phone first: its token dies after 2 minutes, the access token lives longer.
			raw_phone = zalo_graph.get_phone(access_token, phone_token, SECRET_CONF)
		zalo_user_id, zalo_name = zalo_graph.get_user_id(access_token, SECRET_CONF)
	except zalo_graph.ZaloError as e:
		raise PortalError(e.code, e.message, details={"zalo_code": e.zalo_code} if e.zalo_code else None)

	hit_rate_limit(f"login-zalo:{zalo_user_id}", 10, 600)
	return complete_login(zalo_user_id, raw_phone, "ZALO_PHONE" if raw_phone else "STORED_PHONE", zalo_name=zalo_name)


@portal_api(methods=("POST",), auth=False)
def dev_login(zalo_user_id=None):
	"""Sign in WITHOUT asking Zalo - for the Zalo simulator, where getAccessToken /
	getPhoneNumber do not work. Trusts the client's zalo_user_id, exactly like the
	vehicle Mini App, so it is fenced twice:

	1. site_config `employee_portal_dev_login` must be 1 (off on production by default);
	2. the account must have `allow_dev_login` ticked by HR and a phone assigned.

	An unknown ID is still recorded (result DEV_NOT_ALLOWED) so HR can find it in
	TIQN Portal Account, assign the phone and tick the box.
	"""
	if not dev_login_enabled():
		raise PortalError("FEATURE_DISABLED", _("Dev login is turned off on this server."))
	zalo_user_id = (zalo_user_id or "").strip()
	if not zalo_user_id:
		raise PortalError("VALIDATION", _("Missing zalo_user_id."), field="zalo_user_id")
	hit_rate_limit(f"dev-login-ip:{getattr(frappe.local, 'request_ip', '')}", 30, 60)

	allowed = frappe.db.get_value("TIQN Portal Account", zalo_user_id, "allow_dev_login")
	if not allowed:
		if not frappe.db.exists("TIQN Portal Account", zalo_user_id):
			account = frappe.new_doc("TIQN Portal Account")
			account.zalo_user_id = zalo_user_id
			account.first_login = now_datetime()
			account.last_login = now_datetime()
			account.last_result = "NO_PHONE"
			account.flags.from_login = True
			account.insert(ignore_permissions=True)
		payload = _empty_payload(zalo_user_id, None)
		payload["result"] = "DEV_NOT_ALLOWED"
		payload["message"] = _("This Zalo account is not allowed to use dev login. Ask HR to tick Allow Dev Login on it.")
		return payload
	return complete_login(zalo_user_id, None, "DEV")


def dev_login_enabled():
	return bool(cint(frappe.conf.get("employee_portal_dev_login")))


def _empty_payload(zalo_user_id, phone):
	return {
		"result": None,
		"token": None,
		"expires_on": None,
		"zalo_user_id": zalo_user_id,
		"masked_phone": mask_phone(phone) if phone else None,
		"employee": None,
		"access": None,
		"oa": None,
		"expired_on": None,
		"message": None,
		"link_request": None,
	}


def complete_login(zalo_user_id, raw_phone=None, login_method="ZALO_PHONE", zalo_name=None):
	"""Everything after Zalo (or dev_login) has named the user. Split out so tests can
	drive the whole decision table without a real Zalo token.

	`raw_phone` is set only when Zalo itself confirmed the number at this sign-in; it
	then replaces whatever the account held (phone_source = Zalo).
	`zalo_name` comes from Zalo's Graph API (never from the client); empty when the user
	has not shared their profile - the stored name is then kept.
	"""
	now = now_datetime()
	if frappe.db.exists("TIQN Portal Account", zalo_user_id):
		account = frappe.get_doc("TIQN Portal Account", zalo_user_id)
	else:
		account = frappe.new_doc("TIQN Portal Account")
		account.zalo_user_id = zalo_user_id
		account.first_login = now
	account.flags.from_login = True
	if zalo_name:
		account.zalo_name = zalo_name

	if raw_phone:
		account.phone = local_phone(raw_phone)
		account.phone_source = "Zalo"
	phone = account.phone
	payload = _empty_payload(zalo_user_id, phone)

	matches = find_employees_by_phone(phone) if phone else []
	employee_row = matches[0] if matches else None
	account.employee = employee_row.name if employee_row else None
	# Zalo app reviewer (Settings > Zalo App Review): a phone Zalo itself confirmed that
	# belongs to no employee. Signs in to SAMPLE data (employee_portal/demo.py).
	review = not employee_row and account.phone_source == "Zalo" and is_review_phone(phone)
	account.last_login = now
	account.apply_auto_disable()  # same as validate() will do - decide on the state that gets saved
	read_only_until = None

	# Auto-disabled = "no matching phone yet": answer NO_PHONE / NOT_FOUND so the app shows
	# the Zalo ID to send HR, not "locked by HR".
	if account.disabled and not account.auto_disabled:
		result = "DISABLED"
		payload["message"] = account.disabled_message or _(
			"Your account has been locked by the HR department. Please contact HR."
		)
	elif review:
		result = "ACTIVE"
	elif not phone:
		result = "NO_PHONE"
	elif not employee_row:
		result = "NOT_FOUND"
		payload["link_request"] = link_request_payload(zalo_user_id)
	else:
		result, read_only_until, expired_on = employee_access(employee_row)
		if result == "EXPIRED":
			payload["expired_on"] = fmt_date(expired_on)

	account.last_result = "REVIEW" if review and result == "ACTIVE" else result
	account.flags.ignore_permissions = True
	account.save() if not account.is_new() else account.insert()

	payload["result"] = result
	if account.last_result == "REVIEW":
		from customize_erpnext.employee_portal import demo

		token, expires_on = create_session(account.name, None, phone, "REVIEW")
		payload.update(
			{
				"token": token,
				"expires_on": fmt_datetime(expires_on),
				"employee": demo.employee(),
				"access": access_payload("FULL"),
				"oa": oa_payload(account),
			}
		)
	elif result in ("ACTIVE", "READ_ONLY"):
		token, expires_on = create_session(account.name, employee_row.name, phone, login_method)
		payload.update(
			{
				"token": token,
				"expires_on": fmt_datetime(expires_on),
				"employee": employee_payload(employee_row.name),
				"access": access_payload("READ_ONLY" if result == "READ_ONLY" else "FULL", read_only_until),
				"oa": oa_payload(account),
			}
		)
	return payload


# ---------------------------------------------------------------------------
# NOT_FOUND -> "I am employee X" -> HR approves (TIQN Portal Link Request)
# ---------------------------------------------------------------------------
LINK_REQUEST = "TIQN Portal Link Request"
EMPLOYEE_ID_RE = re.compile(r"^TIQN-\d{4}$")
# Saved requests are limited in the record itself (MAX_REQUESTS_PER_DAY = 2, shown on
# ERP and in the app). This cache limit counts every attempt, refused ones included,
# so nobody can probe employee codes.
LINK_ATTEMPTS_PER_DAY = 10


@portal_api(methods=("POST",), auth=False)
def link_employee_request(access_token=None, employee_id=None, full_name=None):
	"""Ask HR to link this Zalo account to employee `employee_id`.

	Who is asking comes from Zalo (access_token), never from the client - a
	`zalo_user_id` parameter is ignored. The phone HR will approve is the one Zalo
	confirmed at the last sign-in. The code and name must match the employee record
	(accents / capitals ignored); an unknown code and a wrong name get the same
	NOT_FOUND, so nobody learns which codes exist.

	One record per Zalo account: a new request overwrites it (back to Pending, also
	while still Pending - to fix a typo), at most MAX_REQUESTS_PER_DAY a day. An employee
	that an active account already signs in as cannot be requested (EMPLOYEE_LINKED).
	"""
	access_token = (access_token or "").strip()
	employee_id = (employee_id or "").strip().upper()
	full_name = " ".join((full_name or "").split())
	if not access_token:
		raise PortalError("ZALO_TOKEN_INVALID", _("Missing Zalo access token."), field="access_token")
	if not EMPLOYEE_ID_RE.match(employee_id):
		raise PortalError("VALIDATION", _("Employee code must look like TIQN-0123."), field="employee_id")
	if len(full_name) < 2 or len(full_name) > 140:
		raise PortalError("VALIDATION", _("Please enter your full name."), field="full_name")

	hit_rate_limit(f"link-ip:{getattr(frappe.local, 'request_ip', '')}", 120, 60)
	try:
		zalo = zalo_graph.get_user_info(access_token, SECRET_CONF)
	except zalo_graph.ZaloError as e:
		raise PortalError(e.code, e.message, details={"zalo_code": e.zalo_code} if e.zalo_code else None)
	zalo_user_id, zalo_name = zalo["id"], zalo["name"]

	account = frappe.db.get_value(
		"TIQN Portal Account", zalo_user_id, ["name", "phone", "disabled", "auto_disabled", "zalo_name"], as_dict=True
	)
	if not account:
		raise PortalError("LOGIN_AGAIN", _("Please open the app again."))
	if account.disabled and not account.auto_disabled:
		raise PortalError("DISABLED", _("Your account has been locked by the HR department. Please contact HR."))
	if not account.phone:
		raise PortalError("VALIDATION", _("Please allow the app to read your phone number, then try again."))
	if find_employees_by_phone(account.phone):
		raise PortalError("LOGIN_AGAIN", _("Your phone now matches an employee record. Please open the app again."))

	hit_rate_limit(f"link-try:{zalo_user_id}", LINK_ATTEMPTS_PER_DAY, 86400)
	doc = _own_request(zalo_user_id, account.phone)
	mine = not doc.is_new() and doc.account == zalo_user_id
	if mine and doc.count_today() >= MAX_REQUESTS_PER_DAY:
		raise PortalError(
			"REQUEST_LIMIT",
			_("You can send at most {0} requests a day. Please try again tomorrow.").format(MAX_REQUESTS_PER_DAY),
			details={"max_per_day": MAX_REQUESTS_PER_DAY, "requests_today": doc.count_today()},
		)

	employee = frappe.db.get_value(
		"Employee", employee_id, ["name", "employee_name", "status", "relieving_date"], as_dict=True
	)
	# Unknown code, no longer allowed in the app, or a name that does not match: ONE answer,
	# so the form cannot be used to find out which codes exist (attempts are limited above).
	if (
		not employee
		or employee_access(employee)[0] not in ("ACTIVE", "READ_ONLY")
		or normalise_name(employee.employee_name) != normalise_name(full_name)
	):
		raise PortalError("NOT_FOUND", _("The employee code or full name is not correct. Please check again."))
	if linked_accounts(employee.name, exclude=zalo_user_id):
		raise PortalError(
			"EMPLOYEE_LINKED",
			_("This employee code already has an account on the app. Please contact the HR department."),
			field="employee_id",
		)

	doc.update(
		{
			"account": zalo_user_id,
			"zalo_name": zalo_name or account.zalo_name,
			"zalo_avatar": zalo["picture"],
			"phone": account.phone,
			"employee": employee.name,
			"full_name": full_name,
			"status": "Pending",
			"reviewed_by": None,
			"reviewed_on": None,
			"reject_reason": None,
		}
	)
	if not mine:  # new, or left under this phone by another Zalo account: start counting again
		doc.request_count = doc.requests_today = 0
	doc.count_request()
	doc.flags.ignore_permissions = True
	doc.insert() if doc.is_new() else doc.save()
	chat = link_request_chat_payload()
	return {
		"status": "PENDING",
		"message": _("Your request has been sent. The HR department will check it."),
		"link_request": link_request_payload(zalo_user_id),
		# 1.10.0: the Mini App opens this chat with a message holding approval_url. Both
		# null = off. Here and not in get_config (Mini App asked for that): get_config
		# needs no login, and the C&B ID by OA is a person's ID (see chat_payload).
		"link_request_chat": chat,
		"approval_url": get_url_to_form(LINK_REQUEST, doc.name) if chat else None,
	}


def link_request_chat_payload():
	"""Chat the Mini App opens after a link request: the C&B staff member of Settings,
	only while Settings > Chat with C&B After a Link Request is on (off by default:
	no chat flood when the app goes out to everyone). Never the OA."""
	s = get_settings()
	if not (cint(s.get("link_request_chat_enabled")) and s.get("cb_chat_id_by_oa")):
		return None
	return {"type": "user", "id": s.cb_chat_id_by_oa, "name": s.get("cb_chat_name") or None}


def _own_request(zalo_user_id, phone):
	"""The request record of this Zalo account - named after its Zalo phone - locked, or a
	new one. Phone changed since the last request -> the record is renamed to the new
	number; a record another Zalo account left under this number (the number moved to
	this account) is replaced."""
	mine = frappe.db.get_value(LINK_REQUEST, {"account": zalo_user_id}, "name", for_update=True)
	by_phone = frappe.db.get_value(LINK_REQUEST, phone, "name", for_update=True)
	if mine and mine != phone:
		if by_phone:
			frappe.delete_doc(LINK_REQUEST, by_phone, force=True, ignore_permissions=True)
		# frappe.rename_doc() has no ignore_permissions; the Mini App user has no rights on this DocType.
		rename_doc(doctype=LINK_REQUEST, old=mine, new=phone, force=True, ignore_permissions=True, show_alert=False)
		mine = phone
	name = mine or by_phone
	return frappe.get_doc(LINK_REQUEST, name) if name else frappe.new_doc(LINK_REQUEST)


def link_request_payload(zalo_user_id):
	"""The request of this Zalo account if it is waiting or was rejected, else None
	(approved = the phone matches, so login no longer answers NOT_FOUND)."""
	if not frappe.db.table_exists(LINK_REQUEST):  # code deployed before migrate
		return None
	if not frappe.db.has_column(LINK_REQUEST, "request_count"):  # v4 code before migrate
		return None
	name = frappe.db.get_value(LINK_REQUEST, {"account": zalo_user_id}, "name", order_by="creation desc")
	if not name:
		return None
	doc = frappe.get_doc(LINK_REQUEST, name)
	if doc.status not in ("Pending", "Rejected"):
		return None
	requests_today = doc.count_today()
	requested_at = fmt_datetime(doc.last_requested_on or doc.creation)
	return {
		"status": doc.status.upper(),
		"employee_id": doc.employee,
		"requested_at": requested_at,
		"created_at": requested_at,  # name before 1.6.0
		"reject_reason": doc.reject_reason if doc.status == "Rejected" else None,
		"request_count": doc.request_count or 0,
		"requests_today": requests_today,
		"max_per_day": MAX_REQUESTS_PER_DAY,
		"remaining_today": max(MAX_REQUESTS_PER_DAY - requests_today, 0),
		"can_resend": requests_today < MAX_REQUESTS_PER_DAY,
	}


# ---------------------------------------------------------------------------
@portal_api(methods=("GET",))
def me():
	c = ctx()
	account = frappe.db.get_value(
		"TIQN Portal Account", c.account, ["followed_oa", "oa_invite_dismissed", "phone"], as_dict=True
	)
	return {
		"employee": employee_payload(c.employee),
		"access": access_payload(c),
		"zalo_user_id": c.account,
		"login_method": c.login_method,
		"masked_phone": mask_phone(account.phone),
		"session_expires_on": fmt_datetime(c.session_expires_on),
		"oa": oa_payload(account),
		"chat": chat_payload(),
	}


@portal_api(methods=("POST",))
def set_id_by_oa(id_by_oa=None):
	"""Mini App sends getUserInfo().idByOA after login (empty until the Mini App is
	verified by the OA or the user follows it). Stored on the caller's OWN account only;
	HR copies the payroll staff member's value into Settings → C&B Chat ID."""
	try:
		value = clean_id_by_oa(id_by_oa)
	except frappe.ValidationError:
		frappe.clear_messages()
		raise PortalError("VALIDATION", _("id_by_oa must be the Zalo ID by OA (digits only)."), field="id_by_oa")
	if value:
		frappe.db.set_value("TIQN Portal Account", ctx().account, "id_by_oa", value, update_modified=False)
	return {"saved": bool(value)}


@portal_api(methods=("POST",), auth=False)
def logout():
	token = (request_header(TOKEN_HEADER) or "").strip()
	if token:
		name = frappe.db.get_value("TIQN Portal Session", {"token_hash": hash_token(token), "revoked": 0})
		if name:
			revoke_session(name, "LOGOUT")
	return None


@portal_api(methods=("POST",))
def set_oa_follow(action=None):
	action = (action or "").strip().upper()
	values = {
		"FOLLOWED": {"followed_oa": 1},
		"UNFOLLOWED": {"followed_oa": 0},
		"DISMISSED": {"oa_invite_dismissed": 1},
	}.get(action)
	if values is None:
		raise PortalError("VALIDATION", _("action must be FOLLOWED, UNFOLLOWED or DISMISSED."), field="action")
	frappe.db.set_value("TIQN Portal Account", ctx().account, values)
	account = frappe.db.get_value("TIQN Portal Account", ctx().account, ["followed_oa", "oa_invite_dismissed"], as_dict=True)
	return oa_payload(account)
