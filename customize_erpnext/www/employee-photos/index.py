import frappe

def get_context(context):
    """
    Check if user is logged in and has required role.
    If not, redirect to login page or show permission error
    """
    # Check if user is logged in
    if frappe.session.user == "Guest":
        # Redirect to login page, then come back here after login
        frappe.local.flags.redirect_location = "/login?redirect-to=/employee-photos"
        raise frappe.Redirect

    # Check if user has required role
    allowed_keywords = ["admin", "hr", "manager","ga"]
    user_roles = frappe.get_roles(frappe.session.user)

    # Check if any user role contains at least one of the allowed keywords (case-insensitive)
    has_permission = any(
        any(keyword in role.lower() for keyword in allowed_keywords)
        for role in user_roles
    )

    if not has_permission:
        frappe.throw(
            "Bạn không có quyền truy cập trang này. Vui lòng liên hệ quản trị viên để được cấp quyền.",
            frappe.PermissionError
        )

    # User is logged in and has permission, allow access to the page
    context.no_cache = 1

    return context
