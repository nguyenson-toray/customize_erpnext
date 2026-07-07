import frappe

# Roles allowed to use the biometric sync page and its APIs
# (machine reboot/delete users are destructive; log viewer reads server files)
BIOMETRIC_ROLES = ("System Manager", "HR Manager", "HR User")


def check_biometric_access():
    """Block API access for users without a biometric-admin role.

    Called at the top of every biometric-related whitelisted method so the
    endpoints are protected even when invoked directly via /api/method/.
    """
    frappe.only_for(BIOMETRIC_ROLES)


def has_biometric_access():
    """Non-raising variant for page controllers."""
    user_roles = set(frappe.get_roles())
    return bool(user_roles.intersection(BIOMETRIC_ROLES))
