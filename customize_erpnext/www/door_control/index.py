import json
import os
import re

import frappe
from frappe import _
from frappe.sessions import get_csrf_token

ROLE = "Door Control"

# Every __('...') string of the page script, collected once from the template so
# the translation map can never drift from the code. Translated per request
# (the user's language), shipped to the page as window.__messages.
_JS_STRING_RE = re.compile(r"__\('((?:[^'\\]|\\.)+)'")
_js_strings = None


def _page_strings():
    global _js_strings
    if _js_strings is None:
        with open(os.path.join(os.path.dirname(__file__), "index.html"), encoding="utf-8") as f:
            _js_strings = sorted(set(m.replace("\\'", "'") for m in _JS_STRING_RE.findall(f.read())))
    return _js_strings


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/door_control"
        raise frappe.Redirect

    # Same role as every api/door_control.py endpoint. Administrator has all roles.
    if ROLE not in frappe.get_roles():
        raise frappe.PermissionError(_("You do not have permission to access this page"))

    context.no_cache = 1
    # get_csrf_token() generates one if the session does not have it yet
    context.csrf_token = get_csrf_token()
    # Jinja has no autoescape here: "</" is escaped so a translation can never close the <script>
    context.messages_json = json.dumps(
        {s: _(s) for s in _page_strings()}, ensure_ascii=False
    ).replace("</", "<\\/")
    context.lang = frappe.local.lang or "en"
    return context
