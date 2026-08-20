"""Trang Dev Tool (/dev-tool) — khung tab cho các công cụ tài liệu nội bộ.

Thêm tab mới: thả một file .js vào public/js/dev_tool/tabs/ có gọi
DevTool.registerTab({...}) là xong. get_context tự quét thư mục đó nên không
phải sửa file này, cũng không phải sửa index.html.
"""

import os

import frappe

TABS_SUBDIR = os.path.join("public", "js", "dev_tool", "tabs")
TABS_ASSET_BASE = "/assets/customize_erpnext/js/dev_tool/tabs"

# Đọc tài liệu: mọi người dùng đã đăng nhập, giống trang /mindmap.
# Sửa và lưu file (tab Mindmap): chỉ Administrator — quyền do api/mindmap_docs.py giữ.
EDIT_ROLES = ("Administrator",)


def _tab_scripts():
    """Danh sách URL asset của các file tab, sắp theo tên file.

    Gắn ?v=<mtime> để sửa file tab xong là trình duyệt lấy bản mới ngay —
    /assets được cache khá lâu, không có tham số này thì phải Ctrl+Shift+R.
    """
    tabs_dir = os.path.join(frappe.get_app_path("customize_erpnext"), TABS_SUBDIR)
    if not os.path.isdir(tabs_dir):
        return []

    out = []
    for name in sorted(os.listdir(tabs_dir)):
        full = os.path.join(tabs_dir, name)
        if not name.endswith(".js") or not os.path.isfile(full):
            continue
        out.append(f"{TABS_ASSET_BASE}/{name}?v={int(os.path.getmtime(full))}")
    return out


def get_context(context):
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/dev-tool"
        raise frappe.Redirect

    user_roles = frappe.get_roles(frappe.session.user)

    context.no_cache = 1
    # get_csrf_token() sinh token nếu session chưa có; session.data.csrf_token có thể None
    context.csrf_token = frappe.sessions.get_csrf_token()
    context.can_save = 1 if any(r in user_roles for r in EDIT_ROLES) else 0
    context.tab_scripts = _tab_scripts()

    return context
