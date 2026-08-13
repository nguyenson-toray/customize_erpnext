import frappe

# Mọi người dùng đã đăng nhập đều xem được sơ đồ ở chế độ chỉ đọc.
# Bấm vào link của từng mục thì Frappe tự kiểm quyền của người đó với chức năng đó,
# nên không cần chặn thêm ở đây.
# Sửa và lưu file tài liệu: chỉ role Administrator.
EDIT_ROLES = ("Administrator",)


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/mindmap"
        raise frappe.Redirect

    user_roles = frappe.get_roles(frappe.session.user)

    context.no_cache = 1
    # get_csrf_token() sinh token nếu session chưa có; session.data.csrf_token có thể None
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.can_save = 1 if any(r in user_roles for r in EDIT_ROLES) else 0

    return context
