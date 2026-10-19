"""Tổ chức lại điều hướng TIQN theo hệ sidebar frappe v16.50+ và xoá 6 DocType không dùng.

pre_model_sync: chạy TRƯỚC khi bench nạp file sidebar/workspace/icon mới, để file mới vào một DB đã
sạch. Nếu để sau, một shell cũ ở DB (standard = 0, sửa gần đây hơn `modified` trong file) sẽ làm
frappe bỏ qua file mới, rồi bước xoá lại xoá luôn shell đó.

Idempotent. Plan: .claude/plans/customize_erpnext_navigation_reorg.md (v3).
Dữ liệu Vehicle Trip (78) / Vehicle List (3) đã export ra
update_backup_20261017/deleted_doctypes_data.json trước khi chạy.
"""

import json
import os

import frappe

# Cha trước, con sau: xoá con trước thì cha còn trỏ Table vào doctype không tồn tại.
DELETED_DOCTYPES = [
	"Purchase Request", "Purchase Request Items",
	"Stock Entry Multi Work Orders",
	"Stock Entry Multi Work Orders Table WO", "Stock Entry Multi Work Orders Table Material",
	"Overtime Request", "OT Employee Detail",
	"Overtime Configuration", "Overtime Level",
	"Vehicle Trip", "Vehicle List",
]
DELETED_REPORTS = ["Vehicle Trip Report"]
DELETED_CUSTOM_FIELDS = ["Stock Entry-custom_stock_entry_multi_work_orders"]
DELETED_WORKSPACES = ["TIQN App", "CCTV"]

# Lớp site của sidebar HRMS/ERPNext do fixture `custom_sidebar.json` quản lý.
SITE_LAYER_MODULES = ["HR Setup", "Tenure", "Shift and Attendance", "Payroll", "Stock", "Manufacturing"]


def execute():
	delete_unused_doctypes()
	delete_old_navigation()
	delete_unmanaged_site_layers()
	frappe.clear_cache()


def delete_unused_doctypes():
	for name in DELETED_REPORTS:
		frappe.delete_doc("Report", name, force=True, ignore_missing=True, ignore_permissions=True)
	for name in DELETED_CUSTOM_FIELDS:
		frappe.delete_doc("Custom Field", name, force=True, ignore_missing=True, ignore_permissions=True)
	for name in DELETED_DOCTYPES:
		if not frappe.db.exists("DocType", name):
			continue
		frappe.delete_doc("DocType", name, force=True, ignore_permissions=True)
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{name}`")


def delete_old_navigation():
	tiqn_modules = frappe.get_all("Module Def", filters={"app_name": "customize_erpnext"}, pluck="name")

	# Shell do patch chuyển đổi frappe / do tay dựng ở DB (standard = 0). Thay bằng file app ship.
	for name in frappe.get_all("Sidebar", filters={"module": ["in", tiqn_modules], "standard": 0}, pluck="name"):
		frappe.delete_doc("Sidebar", name, force=True, ignore_permissions=True)

	for name in DELETED_WORKSPACES:
		frappe.delete_doc("Workspace", name, force=True, ignore_missing=True, ignore_permissions=True)

	# Icon không còn file trong customize_erpnext/desktop_icon/ (reaper của migrate cũng xoá, làm ở
	# đây cho chắc chắn và để nó biến mất ngay cả khi reaper đổi luật).
	keep = set(icon_labels_shipped())
	for name in frappe.get_all("Desktop Icon", filters={"app": "customize_erpnext"}, pluck="name"):
		if name not in keep:
			frappe.delete_doc("Desktop Icon", name, force=True, ignore_permissions=True)


def delete_unmanaged_site_layers():
	"""Lớp site của 6 sidebar: chỉ giữ đúng bản ghi có trong fixture (fixture nạp lại ngay sau đó)."""
	path = frappe.get_app_path("customize_erpnext", "fixtures", "custom_sidebar.json")
	managed = {row["name"] for row in json.load(open(path))} if os.path.exists(path) else set()
	for name in frappe.get_all(
		"Custom Sidebar",
		filters={"module": ["in", SITE_LAYER_MODULES], "user": ["in", ["", None]]},
		pluck="name",
	):
		if name not in managed:
			frappe.delete_doc("Custom Sidebar", name, force=True, ignore_permissions=True)


def icon_labels_shipped():
	folder = frappe.get_app_path("customize_erpnext", "desktop_icon")
	for fname in os.listdir(folder):
		if fname.endswith(".json"):
			yield json.load(open(os.path.join(folder, fname)))["name"]
