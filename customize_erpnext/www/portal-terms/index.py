# Public page for the Zalo Mini App "Cổng nhân viên" - Zalo requires a policy URL when
# the Mini App is submitted for review. Content = Employee Portal Settings.terms_of_use,
# written by HR. Public on purpose; nothing else from Settings is rendered.
from customize_erpnext.employee_portal.legal_page import build_context

no_cache = 1


def get_context(context):
	build_context(context, "terms_of_use", "Terms of Use")
