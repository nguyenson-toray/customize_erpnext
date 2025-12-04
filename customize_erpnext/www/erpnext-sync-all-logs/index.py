import frappe

def get_context(context):
    """
    Check if user is logged in and set context
    """
    # Check if user is logged in
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/erpnext-sync-all"
        raise frappe.Redirect

    # User is logged in, allow access
    context.no_cache = 1

    return context
