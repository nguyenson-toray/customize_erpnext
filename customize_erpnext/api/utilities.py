import frappe
from frappe import _

# Python code (get_role_profile)
@frappe.whitelist()
def get_role_profile(email=None):
    """
    Lấy role_profile_name và roles của user
    Args:
        email: Email của user. Nếu không có sẽ lấy user hiện tại
        
    Returns:
        dict: Thông tin roles của user
    """
    try:
        if not email:
            email = frappe.session.user
             
        # Lấy role_profile và roles
        user = frappe.get_doc('User', email)
        role_profile = user.role_profile_name
        roles = [role.role for role in user.roles]
        # return role_profile
        return {
            'role_profile': role_profile,
            'roles': roles,
            'has_item_manager_role': 'Item Manager' in roles
        }
        
    except Exception as e:
        frappe.log_error(f"Error in get_role_profile: {str(e)}")
        return None