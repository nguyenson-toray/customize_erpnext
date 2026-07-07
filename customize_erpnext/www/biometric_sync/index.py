import frappe
from customize_erpnext.api.biometric_auth import has_biometric_access


def get_context(context):
    """
    Check if user is logged in, has a biometric-admin role, and set context
    """
    # Check if user is logged in
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/biometric_sync"
        raise frappe.Redirect

    # Same roles as the biometric API endpoints (see api/biometric_auth.py)
    if not has_biometric_access():
        raise frappe.PermissionError(frappe._("You do not have permission to access this page"))

    # User is logged in, allow access
    context.no_cache = 1
    # get_csrf_token() generates one if the session does not have it yet,
    # while session.data.csrf_token can be None and would break every POST
    context.csrf_token = frappe.sessions.get_csrf_token()
    # Delete-OT card on the Manual Re-sync tab is shown only to System Managers
    # (the API enforces this server-side as well)
    context.is_system_manager = "System Manager" in frappe.get_roles()

    return context
