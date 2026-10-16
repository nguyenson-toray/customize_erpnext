# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Config, login and session endpoints - API_CONTRACT.md §2 and §6."""

import os
from urllib.parse import quote, unquote

import frappe
from frappe import _
from frappe.utils import cint, get_url, now_datetime

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
	designation_label,
	employee_access,
	find_employees_by_phone,
	get_settings,
	initials,
	local_phone,
	mask_phone,
	setting_int,
	strip_company_suffix,
)
from customize_erpnext.utils import zalo_graph

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
			"logo_url": get_url(s.logo) if s.logo else None,
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

	hit_rate_limit(f"login-ip:{getattr(frappe.local, 'request_ip', '')}", 120, 60)

	try:
		raw_phone = None
		if phone_token:
			# Phone first: its token dies after 2 minutes, the access token lives longer.
			raw_phone = zalo_graph.get_phone(access_token, phone_token, SECRET_CONF)
		zalo_user_id, _zalo_name = zalo_graph.get_user_id(access_token, SECRET_CONF)
	except zalo_graph.ZaloError as e:
		raise PortalError(e.code, e.message, details={"zalo_code": e.zalo_code} if e.zalo_code else None)

	hit_rate_limit(f"login-zalo:{zalo_user_id}", 10, 600)
	return complete_login(zalo_user_id, raw_phone, "ZALO_PHONE" if raw_phone else "STORED_PHONE")


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
	}


def complete_login(zalo_user_id, raw_phone=None, login_method="ZALO_PHONE"):
	"""Everything after Zalo (or dev_login) has named the user. Split out so tests can
	drive the whole decision table without a real Zalo token.

	`raw_phone` is set only when Zalo itself confirmed the number at this sign-in; it
	then replaces whatever the account held (phone_source = Zalo).
	"""
	now = now_datetime()
	if frappe.db.exists("TIQN Portal Account", zalo_user_id):
		account = frappe.get_doc("TIQN Portal Account", zalo_user_id)
	else:
		account = frappe.new_doc("TIQN Portal Account")
		account.zalo_user_id = zalo_user_id
		account.first_login = now
	account.flags.from_login = True

	if raw_phone:
		account.phone = local_phone(raw_phone)
		account.phone_source = "Zalo"
	phone = account.phone
	payload = _empty_payload(zalo_user_id, phone)

	matches = find_employees_by_phone(phone) if phone else []
	employee_row = matches[0] if matches else None
	account.employee = employee_row.name if employee_row else None
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
	elif not phone:
		result = "NO_PHONE"
	elif not employee_row:
		result = "NOT_FOUND"
	else:
		result, read_only_until, expired_on = employee_access(employee_row)
		if result == "EXPIRED":
			payload["expired_on"] = fmt_date(expired_on)

	account.last_result = result
	account.flags.ignore_permissions = True
	account.save() if not account.is_new() else account.insert()

	payload["result"] = result
	if result in ("ACTIVE", "READ_ONLY"):
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
	}


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
