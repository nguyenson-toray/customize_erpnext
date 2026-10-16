# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Signed, short-lived links to private attachments for the Mini App.

`<img src>` cannot send the X-Portal-Token header, and the Zalo webview has no ERP
cookie, so a private file URL is useless there. Each Document object carries a URL
whose `sig` names the File and the employee and expires in 10 minutes; the HMAC key
is the site's encryption key, never sent anywhere.
"""

import base64
import hashlib
import hmac
import time

import frappe
from frappe.utils import add_to_date, cint, get_url, now_datetime


TTL_SECONDS = 600
DOWNLOAD_METHOD = "customize_erpnext.api.employee_portal.download_document"


def _key():
	from frappe.utils.password import get_encryption_key

	return get_encryption_key().encode()


def _b64(data):
	return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text):
	return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(file_name, employee, ttl=TTL_SECONDS):
	expires = int(time.time()) + ttl
	payload = f"{file_name}|{employee}|{expires}"
	mac = hmac.new(_key(), payload.encode(), hashlib.sha256).digest()
	return f"{_b64(payload.encode())}.{_b64(mac)}", expires


def verify(sig):
	"""(file_name, employee) for a valid unexpired signature, else None."""
	try:
		payload_b64, mac_b64 = (sig or "").split(".", 1)
		payload = _unb64(payload_b64)
		expected = hmac.new(_key(), payload, hashlib.sha256).digest()
		if not hmac.compare_digest(expected, _unb64(mac_b64)):
			return None
		file_name, employee, expires = payload.decode().split("|")
		if cint(expires) < time.time():
			return None
		return file_name, employee
	except Exception:
		return None


def document_payload(file_row, employee, can_delete=False):
	sig, expires = sign(file_row.name, employee)
	portal_owner = file_row.owner in ("portal@tiqn.com.vn", "Guest")
	return {
		"id": file_row.name,
		"file_name": file_row.file_name,
		"mime_type": _mime(file_row.file_name),
		"size_bytes": cint(file_row.file_size),
		"uploaded_at": fmt_datetime(file_row.creation),
		"uploaded_by": "EMPLOYEE" if portal_owner else "HR",
		"can_delete": bool(can_delete and portal_owner),
		"url": get_url(f"/api/method/{DOWNLOAD_METHOD}?sig={sig}"),
		# `expires` is a UTC epoch for the check; shown to the client in server local time.
		"url_expires_at": fmt_datetime(add_to_date(now_datetime(), seconds=expires - int(time.time()))),
	}


def fmt_datetime(value):
	return frappe.utils.get_datetime(value).strftime("%Y-%m-%d %H:%M:%S") if value else None


def _mime(file_name):
	import mimetypes

	return mimetypes.guess_type(file_name or "")[0] or "application/octet-stream"


def attachments(doctype, name):
	return frappe.get_all(
		"File",
		filters={"attached_to_doctype": doctype, "attached_to_name": name, "is_folder": 0},
		fields=["name", "file_name", "file_size", "creation", "owner", "file_url", "is_private"],
		order_by="creation asc",
	)
