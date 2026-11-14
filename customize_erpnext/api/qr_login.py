# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""QR Login — sign in on a shared device (tablet) by scanning a personal QR card.

Generic: not tied to any DocType. The device decides where the user lands:
    /qr-login?next=/app/overtime-registration/new

Card content:  QRL1.<user>.<version>.<sig>
    sig = HMAC-SHA256(server key, "<user>.<version>"), first 24 hex chars.
    The server key derives from the site's encryption_key, so a card cannot be
    forged without server access. No password / API secret is on the card.

User.custom_qr_login_version: 0 = QR login off; >= 1 = on; bump = old cards stop working.

QR sessions (cookie `qr_session`, see public/js/qr_login_session.js) log out after
5 idle minutes and are capped at QR_SESSION_MAX_HOURS on the server, so a tablet left
open never keeps someone signed in.

Plan: apps/customize_erpnext/.claude/plans/ot_kiosk_qr.md (bản 4)
"""

import hashlib
import hmac
from datetime import UTC, datetime, timedelta

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import cint

PREFIX = "QRL1"
SIG_LEN = 24
FIELD = "custom_qr_login_version"
COOKIE = "qr_session"
COOKIE_MAX_AGE = 30 * 24 * 3600  # keeps the device's scan page after logout
# Only System Manager issues cards: a card = signing in as that user, so whoever
# can issue one can impersonate (an HR Manager could otherwise mint a card for a
# fellow HR Manager or an accountant).
MANAGER_ROLES = ("System Manager",)
# Server-side cap for a QR session (safety net when the browser is closed before
# the idle logout fires). Normal sessions end after 5 idle minutes on the client.
QR_SESSION_MAX_HOURS = 2


# ---------------------------------------------------------------------------
# Signing
# ---------------------------------------------------------------------------


def _key():
	from frappe.utils.password import get_encryption_key

	return hashlib.sha256((get_encryption_key() + "qr-login-v1").encode()).digest()


def _sign(user, version):
	msg = f"{user}.{version}".encode()
	return hmac.new(_key(), msg, hashlib.sha256).hexdigest()[:SIG_LEN]


def _is_blocked_user(user):
	"""Administrator / System Managers never get a QR card (too much power on a card)."""
	return user in ("Administrator", "Guest") or "System Manager" in frappe.get_roles(user)


def make_payload(user):
	version = cint(frappe.db.get_value("User", user, FIELD))
	if version < 1:
		frappe.throw(_("QR login is not enabled for {0}").format(user))
	return f"{PREFIX}.{user}.{version}.{_sign(user, version)}"


def verify_payload(payload):
	"""User name if the card is valid and current, else None (never says why)."""
	payload = (payload or "").strip()
	if not payload.startswith(PREFIX + ".") or len(payload) > 300:
		return None
	try:
		user, version, sig = payload[len(PREFIX) + 1 :].rsplit(".", 2)
	except ValueError:
		return None
	if not user or not version.isdigit() or len(sig) != SIG_LEN:
		return None
	if not hmac.compare_digest(sig, _sign(user, version)):
		return None

	row = frappe.db.get_value("User", user, ["name", "enabled", "user_type", FIELD], as_dict=True)
	if not row or row.name != user or not row.enabled or row.user_type != "System User":
		return None
	current = cint(row.get(FIELD))
	if current < 1 or str(current) != version:
		return None
	if _is_blocked_user(user):
		return None
	return user


def safe_next(next_url):
	"""Only internal desk paths; anything else lands on /app."""
	if (
		isinstance(next_url, str)
		and next_url.startswith("/app")
		and not next_url.startswith("//")
		and "\\" not in next_url
		and len(next_url) <= 500
	):
		return next_url
	return "/app"


# ---------------------------------------------------------------------------
# Login endpoint (guest)
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=60)
def login(payload=None, next=None):
	user = verify_payload(payload)
	if not user:
		frappe.throw(_("Invalid or revoked card"), frappe.AuthenticationError)

	# User.restrict_ip (e.g. only the shop-floor tablet) is enforced by login_as();
	# check it BEFORE ending the current session, or a refused card would still
	# sign out whoever is using the device.
	from frappe.auth import validate_ip_address

	validate_ip_address(user)

	# Previous person still signed in on this device -> end that session first.
	# NOT login_manager.logout(): it queues the sid cookie for deletion and
	# CookieManager.flush_cookies() runs deletions AFTER sets, which would wipe the
	# new sid and land the user on /login. login_as() below overwrites the cookies.
	if frappe.session.user != "Guest" and frappe.session.sid:
		from frappe.sessions import delete_session

		delete_session(frappe.session.sid, user=frappe.session.user, reason="Switched user by QR Login")

	frappe.flags.qr_login = True  # read by on_login hook below
	session_end = (datetime.now(tz=UTC) + timedelta(hours=QR_SESSION_MAX_HOURS)).isoformat()
	frappe.local.login_manager.login_as(user, session_end=session_end)

	target = safe_next(next)
	# Not httponly: qr_login_session.js reads it to know this is a QR session and
	# where to return after logout. CookieManager URL-encodes the value itself.
	# Persistent (not a browser-session cookie): `sid` outlives a browser restart, so
	# this must too, or a reopened browser would resume the session without idle logout.
	frappe.local.cookie_manager.set_cookie(COOKIE, target, max_age=COOKIE_MAX_AGE)
	return {"redirect": target, "full_name": frappe.utils.get_fullname(user)}


def on_login(login_manager=None):
	"""hooks.on_login: a normal (password / SSO) login on the same browser is not
	a QR session -> drop the cookie so the idle logout does not apply."""
	if not frappe.flags.get("qr_login"):
		frappe.local.cookie_manager.delete_cookie(COOKIE)


# ---------------------------------------------------------------------------
# Card management (User form buttons)
# ---------------------------------------------------------------------------


def _check_manager(user):
	frappe.only_for(MANAGER_ROLES)
	if not frappe.db.exists("User", user):
		frappe.throw(_("User {0} does not exist").format(user))


@frappe.whitelist(methods=["POST"])
def enable(user):
	_check_manager(user)
	if _is_blocked_user(user):
		frappe.throw(_("QR login is not allowed for Administrator or System Manager users"))
	if frappe.db.get_value("User", user, "user_type") != "System User":
		frappe.throw(_("QR login is only available for System Users"))
	version = cint(frappe.db.get_value("User", user, FIELD))
	if version < 1:
		frappe.db.set_value("User", user, FIELD, 1)
	return cint(frappe.db.get_value("User", user, FIELD))


@frappe.whitelist(methods=["POST"])
def revoke(user):
	"""Issue a new card number: every printed card of this user stops working."""
	_check_manager(user)
	version = cint(frappe.db.get_value("User", user, FIELD))
	if version < 1:
		frappe.throw(_("QR login is not enabled for {0}").format(user))
	frappe.db.set_value("User", user, FIELD, version + 1)
	return version + 1


@frappe.whitelist(methods=["POST"])
def disable(user):
	_check_manager(user)
	frappe.db.set_value("User", user, FIELD, 0)
	return 0


def get_card_context(user):
	"""Data for the card page (www/qr-login-card)."""
	from customize_erpnext.api.qr_svg import make_qr_svg

	_check_manager(user)
	payload = make_payload(user)
	emp = frappe.db.get_value(
		"Employee", {"user_id": user}, ["name", "employee_name", "image", "custom_group"], as_dict=True
	)
	return {
		"user": user,
		"full_name": (emp and emp.employee_name) or frappe.utils.get_fullname(user),
		"employee": emp and emp.name,
		"group": emp and emp.custom_group,
		"image": emp and emp.image,
		"version": cint(frappe.db.get_value("User", user, FIELD)),
		"qr_svg": make_qr_svg(payload),
	}
