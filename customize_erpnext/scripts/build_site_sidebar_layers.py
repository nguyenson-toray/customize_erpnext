"""Dựng lớp SITE (Custom Sidebar, user rỗng) cho 6 sidebar HRMS/ERPNext rồi export ra fixture.

Chạy (cần frappe đã connect):
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
    exec(open('../apps/customize_erpnext/customize_erpnext/scripts/build_site_sidebar_layers.py').read())"

App chỉ được ship sidebar cho module của chính nó, nên link TIQN trong sidebar của hrms/erpnext phải
đi qua lớp site. Ghi xong export ra `fixtures/custom_sidebar.json` (hooks.py khai fixture này) để có
trong code. ⚠ Script XOÁ lớp site hiện có của 6 module rồi dựng lại — mọi chỉnh tay "For everyone"
trên 6 sidebar đó sẽ mất; muốn giữ thì thêm vào LAYERS dưới đây.
"""

import os

import frappe
from frappe.desk.doctype.custom_sidebar.custom_sidebar import add_site_sidebar_item
from frappe.utils.fixtures import export_json


def _link(label, link_type, link_to, icon=None, child=1):
	return {"type": "Link", "label": label, "link_type": link_type, "link_to": link_to,
			"icon": icon, "child": child, "collapsible": 1}


def _section(label, icon):
	return {"type": "Section Break", "label": label, "link_type": "DocType", "icon": icon,
			"collapsible": 1, "indent": 1, "keep_closed": 0}


LAYERS = {
	"HR Setup": [
		_link("HR Overview", "Dashboard", "HR Overview", icon="layout-dashboard", child=0),
		_section("TIQN Masters", "database"),
		_link("Section", "DocType", "Section"),
		_link("Group", "DocType", "Group"),
		_link("Resignation Reason Group", "DocType", "Resignation Reason Group"),
		_link("Resignation Reason Group 2", "DocType", "Resignation Reason Group 2"),
		_section("TIQN Employee", "square-user-round"),
		_link("Employee Maternity", "DocType", "Employee Maternity"),
		_link("Labor Contract", "DocType", "Labor Contract"),
		_link("Employee Self Update Info", "DocType", "Employee Self Update Info"),
		_link("Employee Self Update Info Setting", "DocType", "Employee Self Update Info Setting"),
		_link("Employee Item Reissue", "DocType", "Employee Item Reissue"),
		_section("TIQN Reports", "table"),
		_link("Employee Maternity Report", "Report", "Employee Maternity Report"),
		_link("Labor Contract Report", "Report", "Labor Contract Report"),
		_link("Employee Item Reissue Report", "Report", "Employee Item Reissue"),
	],
	"Tenure": [
		_section("TIQN", "user-clock"),
		_link("Resignation Application", "DocType", "Resignation Application"),
		_link("Employee Transfer", "DocType", "Employee Transfer"),
		_link("Employee Promotion", "DocType", "Employee Promotion"),
		_link("Employee Transfer and Promotion", "Report", "Employee Transfer and Promotion"),
		_section("Health Check-Up", "stethoscope"),
		_link("Health Check-Up", "DocType", "Health Check-Up"),
		_link("Health Check Up Management", "Page", "health-check-up-management"),
	],
	"Shift and Attendance": [
		_link("Daily Attendance", "Dashboard", "Daily Attendance", icon="layout-dashboard", child=0),
		_section("TIQN", "clock"),
		_link("Overtime Registration", "DocType", "Overtime Registration"),
		_link("Attendance Calculation Setting", "DocType", "Attendance Calculation Setting"),
		_section("TIQN Reports", "table"),
		_link("Shift Attendance Customize", "Report", "Shift Attendance Customize"),
		_link("Overtime Registration Report", "Report", "Overtime Registration"),
		_link("Overtime Registration by Time Slot", "Report", "Overtime Registration by Time Slot"),
		_link("Overtime Registration Quantity", "Report", "Overtime Registration Quantity"),
		_link("OT Compliance", "Report", "OT Compliance"),
	],
	"Payroll": [
		_section("TIQN", "users"),
		_link("Employee Dependent", "DocType", "Employee Dependent"),
		_link("External Personnel", "DocType", "External Personnel"),
	],
	"Stock": [
		_section("TIQN", "package"),
		_link("Packing List", "DocType", "Packing List"),
		_link("Stock Balance Customize", "Report", "Stock Balance Customize"),
		_link("Stock Ledger Customize", "Report", "Stock Ledger Customize"),
	],
	"Manufacturing": [
		_section("TIQN", "factory"),
		_link("BOM Balance Sheet", "Report", "BOM Balance Sheet"),
	],
}


def build():
	missing = [
		f"{module}: {i['link_type']} {i['link_to']}"
		for module, items in LAYERS.items()
		for i in items
		if i["type"] == "Link" and not frappe.db.exists(i["link_type"], i["link_to"])
	]
	if missing:
		frappe.throw("Targets missing: " + "; ".join(missing))

	for module, items in LAYERS.items():
		for name in frappe.get_all("Custom Sidebar", filters={"module": module, "user": ["in", ["", None]]}, pluck="name"):
			frappe.delete_doc("Custom Sidebar", name, force=True, ignore_permissions=True)
		for item in items:
			add_site_sidebar_item(module, {k: v for k, v in item.items() if v is not None})
	frappe.db.commit()

	path = frappe.get_app_path("customize_erpnext", "fixtures", "custom_sidebar.json")
	export_json(
		"Custom Sidebar", path,
		filters=[["user", "in", ["", None]], ["module", "in", list(LAYERS)]],
		order_by="module asc",
	)
	frappe.clear_cache()
	print("layers:", {m: len(i) for m, i in LAYERS.items()}, "->", os.path.relpath(path))


build()
