# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Request plumbing for the employee portal Mini App API.

Every endpoint goes through `portal_api`, which:

1. validates the `X-Portal-Token` session (unless auth=False) and re-checks the
   employee on EVERY request - phone still the same, still allowed in;
2. runs the endpoint as the service user `portal@tiqn.com.vn` (owner/modified_by
   get a real name, messages come out in Vietnamese) and puts the caller's identity
   in `frappe.local.portal` - endpoints never take an `employee` argument;
3. wraps the result in the fixed envelope of API_CONTRACT.md §3.1, turning
   PortalError / ValidationError into `ok: false` and rolling back whatever the
   failed request had written.

🔴 No Frappe API key is involved: endpoints are allow_guest and the portal token is
the only credential. Do not use `Authorization: Bearer` for it - Frappe treats that
as OAuth and raises AuthenticationError before our code runs.
"""

import functools
import hashlib
import re
import secrets
from dataclasses import dataclass

import frappe
from frappe import _
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime, time_diff_in_seconds

from customize_erpnext.employee_portal.utils import (
	employee_access,
	find_employees_by_phone,
	get_settings,
	phone_key,
	setting_int,
)

API_VERSION = "1.0"
PORTAL_USER = "portal@tiqn.com.vn"
TOKEN_HEADER = "X-Portal-Token"
VERSION_HEADER = "X-Portal-Client-Version"
SECRET_CONF = "zalo_app_employee_portal_secret_key"
LAST_SEEN_EVERY_SECONDS = 300

FEATURES = (
	"payslip",
	"attendance",
	"overtime",
	"leave_view",
	"leave_create",
	"explanation_create",
	"notifications",
	"oa_invite",
)


class PortalError(Exception):
	def __init__(self, code, message, field=None, details=None):
		super().__init__(message)
		self.code = code
		self.message = message
		self.field = field
		self.details = details or {}


@dataclass
class PortalContext:
	session: str
	account: str
	employee: str
	employee_row: dict
	mode: str  # FULL | READ_ONLY
	read_only_until: object
	session_expires_on: object
	login_method: str = None

	@property
	def read_only(self):
		return self.mode == "READ_ONLY"


def ctx() -> PortalContext:
	return frappe.local.portal


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------
def _server_time():
	return now_datetime().strftime("%Y-%m-%d %H:%M:%S")


def _ok(data):
	return {"ok": True, "data": data, "server_time": _server_time()}


def _error(code, message, field=None, details=None):
	return {
		"ok": False,
		"error": {"code": code, "message": message, "field": field, "details": details or {}},
		"server_time": _server_time(),
	}


def _plain(message):
	"""Frappe messages may carry HTML (<b>, <br>) - the Mini App renders plain text."""
	text = re.sub(r"<br\s*/?>", "\n", str(message or ""))
	text = re.sub(r"<[^>]+>", "", text)
	return frappe.utils.html2text(text).strip() if "&" in text else text.strip()


def _validation_message(exc):
	messages = []
	for raw in frappe.local.message_log or []:
		try:
			item = frappe.parse_json(raw) if isinstance(raw, str) else raw
			messages.append(item.get("message") if isinstance(item, dict) else str(item))
		except Exception:
			messages.append(str(raw))
	text = "\n".join(m for m in messages if m) or str(exc)
	return _plain(text) or _("The request could not be completed.")


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------
def portal_api(methods=("GET",), auth=True, write=False, feature=None):
	"""Turn `fn` into a Mini App endpoint. See module docstring."""

	def decorator(fn):
		@functools.wraps(fn)
		def wrapper(**kwargs):
			frappe.local.lang = "vi"
			frappe.local.portal = None
			try:
				check_client_version()
				if auth:
					frappe.local.portal = authenticate()
				_run_as_portal_user()
				if feature and not feature_enabled(feature):
					raise PortalError("FEATURE_DISABLED", _("This feature is currently turned off."))
				if write and frappe.local.portal and frappe.local.portal.read_only:
					raise PortalError("READ_ONLY", _("Your account is in view-only mode."))
				# Unknown keys (cmd, a stray `employee`...) never reach the endpoint.
				return _ok(fn(**frappe.get_newargs(fn, kwargs)))
			except PortalError as e:
				frappe.db.rollback()
				frappe.local.message_log = []
				return _error(e.code, e.message, e.field, e.details)
			except frappe.DoesNotExistError:
				frappe.db.rollback()
				frappe.local.message_log = []
				return _error("NOT_FOUND", _("Not found."))
			except frappe.ValidationError as e:
				frappe.db.rollback()
				message = _validation_message(e)
				frappe.local.message_log = []
				return _error("VALIDATION", message)
			finally:
				_restore_guest()

		return frappe.whitelist(allow_guest=True, methods=list(methods))(wrapper)

	return decorator


def _run_as_portal_user():
	if frappe.session.user != PORTAL_USER and frappe.db.exists("User", PORTAL_USER):
		frappe.set_user(PORTAL_USER)


def _restore_guest():
	# frappe.set_user() rewrites the request's session sid. Left as the portal user,
	# Session.update() at the end of the request would persist a bogus session row
	# for it. Back to Guest = nothing is persisted.
	if frappe.session.user != "Guest":
		frappe.set_user("Guest")


def request_header(name):
	"""frappe.get_request_header raises outside an HTTP request (bench execute, tests)."""
	try:
		return frappe.get_request_header(name)
	except RuntimeError:
		return None


def request_method():
	request = getattr(frappe.local, "request", None)
	return request.method if request else "POST"


def commit_if_get():
	"""Frappe rolls back every GET at the end of the request. Writes a GET must keep
	(session revocation, last_seen) are committed explicitly - nothing else has been
	written at that point."""
	if request_method() in ("GET", "HEAD"):
		frappe.db.commit()


# ---------------------------------------------------------------------------
# Config / features / client version
# ---------------------------------------------------------------------------
def feature_enabled(name):
	return bool(cint(get_settings().get(f"feature_{name}")))


def features():
	return {name: feature_enabled(name) for name in FEATURES}


def _version_tuple(value):
	try:
		return tuple(int(x) for x in str(value).strip().split(".")[:3])
	except ValueError:
		return None


def check_client_version():
	sent = request_header(VERSION_HEADER)
	minimum = (get_settings().min_client_version or "").strip()
	if not sent or not minimum:
		return
	sent_t, min_t = _version_tuple(sent), _version_tuple(minimum)
	if sent_t and min_t and sent_t < min_t:
		raise PortalError(
			"CLIENT_TOO_OLD",
			_("Please update the app to the latest version."),
			details={"min_client_version": minimum},
		)


# ---------------------------------------------------------------------------
# Rate limiting (cache counters; login only)
# ---------------------------------------------------------------------------
def hit_rate_limit(key, limit, seconds):
	"""Count one hit for `key`; raise RATE_LIMITED past `limit` within `seconds`.

	⚠ Factory workers share the WiFi NAT = one public IP for hundreds of people, so
	per-IP limits must stay generous. The tight limit is per Zalo account.
	"""
	cache_key = f"employee_portal:rl:{key}"
	count = frappe.cache.incr(cache_key)
	if count == 1:
		frappe.cache.expire(cache_key, seconds)
	if count > limit:
		ttl = frappe.cache.ttl(cache_key)
		raise PortalError(
			"RATE_LIMITED",
			_("Too many attempts. Please wait a moment and try again."),
			details={"retry_after": max(cint(ttl), 1)},
		)


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------
def hash_token(token):
	return hashlib.sha256(token.encode()).hexdigest()


DEV_SESSION_DAYS = 1


def create_session(account, employee, phone, login_method="ZALO_PHONE"):
	token = secrets.token_urlsafe(32)
	days = DEV_SESSION_DAYS if login_method == "DEV" else setting_int("session_days", 30)
	expires_on = add_days(now_datetime(), days)
	frappe.get_doc(
		{
			"doctype": "TIQN Portal Session",
			"account": account,
			"employee": employee,
			"phone": phone,
			"token_hash": hash_token(token),
			"login_method": login_method,
			"expires_on": expires_on,
			"last_seen": now_datetime(),
			"client_version": (request_header(VERSION_HEADER) or "")[:40],
			"ip_address": getattr(frappe.local, "request_ip", None),
		}
	).insert(ignore_permissions=True)
	return token, expires_on


def revoke_session(name, reason):
	frappe.db.set_value(
		"TIQN Portal Session",
		name,
		{"revoked": 1, "revoked_reason": reason, "revoked_on": now_datetime()},
		update_modified=False,
	)


def _invalid(session_name, reason, result=None, commit=True):
	if session_name:
		# "STATUS_CHANGED:EXPIRED" - a parallel request reading the revoked row must give
		# the same answer (screen 05), not a bare REVOKED (screen 01).
		revoke_session(session_name, f"{reason}:{result}" if result else reason)
		if commit:
			# PortalError makes the wrapper roll back; the revocation must survive it.
			frappe.db.commit()
	details = {"reason": reason}
	if result:
		details["result"] = result
	return PortalError("SESSION_INVALID", _("Your session has ended. Please sign in again."), details=details)


def authenticate():
	token = (request_header(TOKEN_HEADER) or "").strip()
	if not token:
		raise PortalError("SESSION_REQUIRED", _("Please sign in."))

	session = frappe.db.get_value(
		"TIQN Portal Session",
		{"token_hash": hash_token(token)},
		["name", "account", "employee", "phone", "expires_on", "revoked", "revoked_reason", "last_seen", "login_method"],
		as_dict=True,
	)
	if not session:
		raise PortalError("SESSION_INVALID", _("Your session has ended. Please sign in again."), details={"reason": "REVOKED"})
	if session.revoked:
		# Report WHY it was revoked when the cause was recorded (HR changed the phone,
		# HR disabled the account), so the Mini App can show the right screen.
		stored = session.revoked_reason or ""
		if stored in ("PHONE_CHANGED", "EXPIRED"):
			raise _invalid(None, stored)
		if stored == "DISABLED":  # written by TIQN Portal Account.on_update
			raise _invalid(None, "STATUS_CHANGED", "DISABLED")
		if stored.startswith("STATUS_CHANGED:"):
			raise _invalid(None, "STATUS_CHANGED", stored.split(":", 1)[1])
		raise _invalid(None, "REVOKED")
	if get_datetime(session.expires_on) <= now_datetime():
		raise _invalid(session.name, "EXPIRED")

	account = frappe.db.get_value(
		"TIQN Portal Account", session.account, ["disabled", "phone", "allow_dev_login"], as_dict=True
	)
	if not account or account.disabled:
		raise _invalid(session.name, "STATUS_CHANGED", "DISABLED")
	# HR re-assigned (or cleared) the account's phone -> this session's identity is gone.
	if phone_key(account.phone) != phone_key(session.phone):
		raise _invalid(session.name, "PHONE_CHANGED")
	if session.login_method == "DEV" and not (
		cint(frappe.conf.get("employee_portal_dev_login")) and cint(account.allow_dev_login)
	):
		raise _invalid(session.name, "REVOKED")

	# The phone must still lead to THIS employee: HR changed the number, or someone
	# rejoined with a new code under the same number -> sign in again.
	matches = find_employees_by_phone(session.phone)
	if not matches or matches[0].name != session.employee:
		raise _invalid(session.name, "PHONE_CHANGED")

	employee_row = matches[0]
	result, read_only_until, _expired_on = employee_access(employee_row)
	if result == "EXPIRED":
		raise _invalid(session.name, "STATUS_CHANGED", "EXPIRED")

	if not session.last_seen or time_diff_in_seconds(now_datetime(), session.last_seen) > LAST_SEEN_EVERY_SECONDS:
		frappe.db.set_value("TIQN Portal Session", session.name, "last_seen", now_datetime(), update_modified=False)
		commit_if_get()

	return PortalContext(
		session=session.name,
		account=session.account,
		employee=session.employee,
		employee_row=employee_row,
		mode="READ_ONLY" if result == "READ_ONLY" else "FULL",
		read_only_until=read_only_until,
		session_expires_on=session.expires_on,
		login_method=session.login_method,
	)


# ---------------------------------------------------------------------------
# Small shared serialisers
# ---------------------------------------------------------------------------
def fmt_date(value):
	# Single DocTypes hand dates back as strings - normalise through getdate.
	return getdate(value).strftime("%Y-%m-%d") if value else None


def fmt_datetime(value):
	return get_datetime(value).strftime("%Y-%m-%d %H:%M:%S") if value else None


def access_payload(context_or_mode, read_only_until=None):
	if isinstance(context_or_mode, PortalContext):
		return {"mode": context_or_mode.mode, "read_only_until": fmt_date(context_or_mode.read_only_until)}
	return {"mode": context_or_mode, "read_only_until": fmt_date(read_only_until)}
