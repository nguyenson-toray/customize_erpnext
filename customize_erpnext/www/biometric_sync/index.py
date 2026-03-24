import frappe

def get_context(context):
    """
    Check if user is logged in and set context
    """
    # Check if user is logged in
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/biometric_sync"
        raise frappe.Redirect

    # User is logged in, allow access
    context.no_cache = 1
    context.csrf_token = frappe.session.data.csrf_token

    return context
