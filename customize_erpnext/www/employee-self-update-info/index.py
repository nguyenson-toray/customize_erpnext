import os

import frappe


def get_context(context):
    context.no_cache = 1
    context.csrf_token = frappe.sessions.get_csrf_token()
    # Opt in to User-Agent Client Hints so the browser sends the device model
    # (Chromium/Android only) on the subsequent submit request. No JS, no
    # permission prompt. Read back server-side in _submit_device_info().
    frappe.local.response_headers["Accept-CH"] = (
        "Sec-CH-UA-Model, Sec-CH-UA-Platform, Sec-CH-UA-Platform-Version"
    )
    context.company = (
        frappe.defaults.get_global_default("company")
        or frappe.db.get_single_value("Global Defaults", "default_company")
        or ""
    )
    # Cache-busting cho form.js / style.css (như /quiz; KHÔNG đặt tên index.js — Frappe sẽ đọc nó làm colocated_js mỗi request): đổi file → URL ?v= đổi theo.
    here = os.path.dirname(__file__)
    context.asset_version = int(
        max(os.path.getmtime(os.path.join(here, f)) for f in ("form.js", "qr_worker.js", "style.css"))
    )
