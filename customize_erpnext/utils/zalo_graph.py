# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Server-side calls to Zalo's Graph API for a Mini App.

Used by the employee portal (`api/employee_portal`). Same error knowledge as
`api/vehicle_management.decode_phone_token`, which stays untouched - that endpoint
throws for the vehicle Mini App's contract; this module raises `ZaloError` with a
portal error code instead.

🔴 Never put an exception's text into a user-facing message: `requests` errors can
quote the request headers back, and those carry the app secret.
🔴 Zalo checks the SESSION before the SECRET KEY, so a made-up access_token always
says "Session key invalid" whether the key is right or not. Only a real login from
the Mini App proves the key.
"""

import hashlib
import hmac

import frappe

ZALO_ME_URL = "https://graph.zalo.me/v2.0/me"
ZALO_PHONE_URL = "https://graph.zalo.me/v2.0/me/info"
TIMEOUT_SECONDS = 10

# docs.zaloplatforms.com/docs/MA/api/errorCode - mapped to WHOSE problem it is.
SERVER_CONFIG_ERRORS = {116, 117, 118}
TOKEN_ERRORS = {114, 115}
TOKEN_USED_ERRORS = {119}
PERMISSION_ERRORS = {-1401}


class ZaloError(Exception):
	def __init__(self, code, message, zalo_code=None):
		super().__init__(message)
		self.code = code
		self.message = message
		self.zalo_code = zalo_code


def _secret(conf_key):
	secret = (frappe.conf.get(conf_key) or "").strip()
	if not secret:
		raise ZaloError(
			"ZALO_SERVER_CONFIG",
			frappe._("{0} is not set in site_config.json on this server. Ask IT to add it.").format(conf_key),
		)
	return secret


def _appsecret_proof(access_token, secret):
	"""Header `appsecret_proof` = HMAC-SHA256(message=access_token, key=app secret), hex.

	Same as Zalo's official PHP SDK (`hash_hmac('sha256', $accessToken, $secret)`), which
	sends it on EVERY Graph call once enabled. Sent on both calls here so the Zalo app
	setting "Bật kiểm tra app secret proof" can be switched on; harmless while it is off.
	"""
	return hmac.new(secret.encode(), access_token.encode(), hashlib.sha256).hexdigest()


def _get(url, headers, params=None):
	import requests

	try:
		resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT_SECONDS)
		return resp.json()
	except requests.Timeout:
		raise ZaloError("ZALO_UNAVAILABLE", frappe._("Zalo did not answer within {0} seconds. Please try again.").format(TIMEOUT_SECONDS))
	except (requests.RequestException, ValueError):
		frappe.log_error(title="Zalo Graph call failed", message=frappe.get_traceback())
		raise ZaloError("ZALO_UNAVAILABLE", frappe._("Could not reach Zalo. Please try again."))


def _raise_for(data, conf_key):
	code = frappe.utils.cint(data.get("error"))
	message = str(data.get("message") or "")
	if code in SERVER_CONFIG_ERRORS or "secret_key" in message:
		if code == 118:
			text = frappe._(
				"{0} belongs to a DIFFERENT Zalo app than the one the Mini App logged in with. "
				"The key itself is valid - it is the wrong app."
			).format(conf_key)
		elif code == 116:
			text = frappe._("{0} is empty in site_config.json on this server.").format(conf_key)
		else:
			text = frappe._(
				"Zalo rejected {0}: it is not the App Secret Key of this Mini App's Zalo app."
			).format(conf_key)
		raise ZaloError("ZALO_SERVER_CONFIG", f"{text} (Zalo {code}: {message})", code)
	if code in TOKEN_USED_ERRORS:
		raise ZaloError(
			"ZALO_TOKEN_USED",
			frappe._("This phone token has already been used or is older than 2 minutes. Please try again."),
			code,
		)
	if code in PERMISSION_ERRORS:
		raise ZaloError("ZALO_PERMISSION", frappe._("Please allow the app to read your phone number."), code)
	raise ZaloError(
		"ZALO_TOKEN_INVALID",
		frappe._("Zalo did not accept the login token. Please try again. (Zalo {0}: {1})").format(code, message),
		code,
	)


def get_user_id(access_token, secret_conf_key):
	"""App-scoped Zalo user id of whoever holds `access_token`."""
	secret = _secret(secret_conf_key)
	data = _get(
		ZALO_ME_URL,
		headers={"access_token": access_token, "appsecret_proof": _appsecret_proof(access_token, secret)},
		params={"fields": "id,name"},
	)
	if frappe.utils.cint(data.get("error")) != 0 or not data.get("id"):
		_raise_for(data, secret_conf_key)
	return str(data["id"]).strip(), (data.get("name") or "").strip() or None


def get_phone(access_token, phone_token, secret_conf_key):
	"""Exchange a getPhoneNumber() token for the real number (digits as Zalo sends them).

	The token works ONCE and expires after 2 minutes - never retry with the same one.
	"""
	secret = _secret(secret_conf_key)
	data = _get(
		ZALO_PHONE_URL,
		headers={
			"access_token": access_token,
			"code": phone_token,
			"secret_key": secret,
			"appsecret_proof": _appsecret_proof(access_token, secret),
		},
	)
	number = (data.get("data") or {}).get("number")
	if frappe.utils.cint(data.get("error")) != 0 or not number:
		_raise_for(data, secret_conf_key)
	return str(number).strip()
