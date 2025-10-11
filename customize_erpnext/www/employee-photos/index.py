import frappe

def get_context(context):
    """
    Check if user is logged in.
    If not, redirect to login page with redirect-to parameter
    """
    # Check if user is logged in
    if frappe.session.user == "Guest":
        # Redirect to login page, then come back here after login
        frappe.local.flags.redirect_location = "/login?redirect-to=/employee-photos"
        raise frappe.Redirect

    # User is logged in, allow access to the page
    context.no_cache = 1

    return context
