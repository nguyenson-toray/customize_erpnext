# Shared renderer of the public pages /portal-policy and /portal-terms (www/).
import frappe
from frappe.utils import format_date
from frappe.utils.html_utils import sanitize_html


def build_context(context, fieldname, title):
	frappe.local.lang = "vi"
	s = frappe.get_cached_doc("Employee Portal Settings")
	context.no_cache = 1
	context.page_title = frappe._(title)
	context.company = s.company_display_name or frappe.defaults.get_global_default("company")
	context.version = format_date(s.legal_version) if s.legal_version else None
	context.content = sanitize_html(s.get(fieldname) or "")
