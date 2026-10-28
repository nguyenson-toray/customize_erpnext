#!/usr/bin/env python3
"""Sinh file điều hướng của customize_erpnext theo hệ sidebar của frappe v16.50+.

Chạy:  python3 scripts/build_navigation.py

Ghi ra (đè lên bản cũ):
- `<module>/sidebar/<x>/<x>.json`  — 1 sidebar (shell) cho mỗi module điều hướng
- `<module>/workspace/<x>/<x>.json` — trang Home cho module có nhiều nhóm quyền
- `dock/customize_erpnext/customize_erpnext.json` — dock cho chế độ "Apps"
- `desktop_icon/*.json` — icon của lưới "Desktop Icons"; xoá icon không còn trong danh sách

Quy tắc (xem .claude/plans/customize_erpnext_navigation_reorg.md):
- Mỗi icon = 1 module = đúng 1 shell. Nhiều shell chung một module làm sidebar "dính" khi chuyển trang.
- Label icon = tên shell hoặc tên module của shell: frappe tìm shell theo đó, không thấy là ẩn icon.
- Slug của shell phải KHÁC slug của trang đầu tiên trong nó, nếu không router không ghi shell vào
  URL (`names_itself` trong router.js) và desk giữ shell đang hiện. Vì vậy shell của module
  "Overtime Registration" tên "Overtime", của "Health Check Up" tên "Health Checkup".
- Slug của shell cũng KHÔNG được trùng tên một DocType/Page/Report: router đọc
  `/desk/shoe-rack/shoe-rack-dashboard` thành bản ghi Shoe Rack tên "shoe-rack-dashboard" → 404.
  Vì vậy shell của module "Shoe Rack" tên "Shoe Rack Management".
- Item chính của mỗi trang đặt `is_default_module = 1`: mở từ ô tìm kiếm luôn vào đúng shell này.
- Link TIQN nằm trong sidebar HRMS/ERPNext KHÔNG sinh ở đây — đó là lớp site, nằm ở
  `fixtures/custom_sidebar.json`.
"""

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.realpath(os.path.join(HERE, ".."))
APP_NAME = "customize_erpnext"
STAMP = "2026-10-17 12:00:00.000000"
# Dock + icons changed on 24/10 (Employee Portal added): a newer `modified` makes migrate
# re-import them - frappe skips a file whose `modified` is not newer than the DB row.
STAMP_ICONS = "2026-10-24 18:00:00.000000"
IMG = "/assets/customize_erpnext/images/"
# A sidebar whose items changed after it was first imported needs a newer `modified` too.
SIDEBAR_STAMPS = {
	"New Joiners": "2026-10-21 10:00:00.000000",
	"Employee Portal": "2026-10-28 14:00:00.000000",  # + Payslip Detail / Payslip Structure
}


def scrub(name):
	return name.replace(" ", "_").replace("-", "_").lower()


def link(label, link_type, link_to=None, url=None, icon=None, default=0, child=0):
	row = {
		"added": 0, "child": child, "collapsible": 1, "hidden": 0, "icon": icon, "indent": 0,
		"is_default_module": default, "keep_closed": 0, "label": label, "link_type": link_type,
		"open_in_new_tab": 0, "show_arrow": 0, "type": "Link",
	}
	if link_type == "URL":
		row["url"] = url
	else:
		row["link_to"] = link_to
	return {k: v for k, v in row.items() if v is not None}


def child(*args, **kwargs):
	return link(*args, child=1, **kwargs)


def section(label, icon):
	return {
		"added": 0, "child": 0, "collapsible": 1, "hidden": 0, "icon": icon, "indent": 1,
		"is_default_module": 0, "keep_closed": 0, "label": label, "link_type": "DocType",
		"open_in_new_tab": 0, "show_arrow": 0, "type": "Section Break",
	}


def home(workspace):
	return link("Home", "Workspace", workspace, icon="house")


# ── module điều hướng: (module, title shell, header icon, items) ──────────────
SIDEBARS = [
	("Overtime Registration", "Overtime", "clock", [
		link("Overtime Registration", "DocType", "Overtime Registration", icon="clipboard-list", default=1),
		section("Reports", "table"),
		child("Overtime Registration Report", "Report", "Overtime Registration", default=1),
	]),
	("New Joiners", "New Joiners", "user-plus", [
		link("Employee", "DocType", "Employee", icon="square-user-round"),
		link("Self Update Info Setting", "DocType", "Employee Self Update Info Setting", icon="settings", default=1),
		link("Self Update Info Records", "DocType", "Employee Self Update Info", icon="file-text", default=1),
		# Employee Quiz (8cca17d, 21/10/2026) - added to the JSON by hand at the time.
		link("Quiz", "DocType", "TIQN Quiz", icon="clipboard-check", default=1),
		link("Quiz Responses", "DocType", "TIQN Quiz Response", icon="list-checks", default=1),
		link("Quiz Result", "Report", "TIQN Quiz Result", icon="file-chart-column", default=1),
	]),
	("Employee Photos", "Employee Photos", "images", [
		link("Employee Photos", "URL", url="/employee-photos", icon="images"),
	]),
	("Network", "Devices and Security", "shield", [
		home("Devices and Security"),
		section("CCTV", "cctv"),
		child("CCTV Tracking", "DocType", "CCTV Tracking", default=1),
		child("Camera", "DocType", "Camera", default=1),
		child("NVR", "DocType", "NVR", default=1),
		section("Door Control", "door-open"),
		child("Door Control", "URL", url="/door_control"),
		child("Door Control Action", "DocType", "Door Control Action", default=1),
		child("Door Access Log", "DocType", "Door Access Log", default=1),
		child("Door Alert Setting", "DocType", "Door Alert Setting", default=1),
		section("Attendance Devices", "fingerprint"),
		child("Biometric Sync", "Page", "biometric-sync", default=1),
		child("Attendance Machine Setting", "DocType", "Attendance Machine Setting", default=1),
	]),
	("Vehicle Management", "Vehicle Management", "car", [
		link("Vehicle Dispatch", "Page", "vehicle-dispatch", icon="dashboard-list", default=1),
		link("Zalo Role Map", "DocType", "TIQN Zalo Role Map", icon="list", default=1),
		link("Vehicle Trip", "DocType", "TIQN Vehicle Trip", icon="app-window-mac", default=1),
		link("Vehicle Request", "DocType", "TIQN Vehicle Request", icon="briefcase-business", default=1),
		section("Masters", "list"),
		child("Vehicle", "DocType", "TIQN Vehicle", default=1),
		child("Fixed Trip Schedule", "DocType", "TIQN Fixed Trip Schedule", default=1),
		section("Reports", "list"),
		child("Vehicle KM Report", "Report", "TIQN Vehicle KM", default=1),
	]),
	("Health Check Up", "Health Checkup", "stethoscope", [
		link("Health Check-Up", "DocType", "Health Check-Up", icon="clipboard-list", default=1),
		link("Health Check Up Management", "Page", "health-check-up-management", icon="layout-dashboard", default=1),
	]),
	("Shoe Rack", "Shoe Rack Management", "layout-grid", [
		link("Shoe Rack Dashboard", "Page", "shoe-rack-dashboard", icon="layout-dashboard", default=1),
		link("Shoe Rack", "DocType", "Shoe Rack", icon="list", default=1),
		link("Layout Manager", "Page", "layout-manager", icon="layout-grid", default=1),
		link("Shoe Rack Layout Settings", "DocType", "Shoe Rack Layout Settings", icon="settings", default=1),
	]),
	("Employee Portal", "Employee Portal", "smartphone", [
		link("Payslip Upload", "Page", "payslip-upload", icon="upload", default=1),
		link("Payslip", "DocType", "TIQN Payslip", icon="file-text", default=1),
		link("Payslip Period Summary", "Report", "Payslip Period Summary", icon="table", default=1),
		link("Payslip Detail", "Report", "Payslip Detail", icon="sheet", default=1),
		link("Payslip Structure", "DocType", "TIQN Payslip Structure", icon="list-tree", default=1),
		section("Mini App", "smartphone"),
		child("Notification", "DocType", "TIQN Portal Notification", default=1),
		child("Link Request", "DocType", "TIQN Portal Link Request", default=1),
		child("Zalo Account", "DocType", "TIQN Portal Account", default=1),
		child("Employee Portal Settings", "DocType", "Employee Portal Settings", default=1),
	]),
	("IT Tools", "IT Tools", "wrench", [
		home("IT Tools"),
		link("Dev Tool", "URL", url="/dev-tool", icon="code"),
		link("Mindmap", "URL", url="/mindmap", icon="network"),
		link("QR Code Generator", "URL", url="/qr-code", icon="qr-code"),
	]),
]

# Module điều hướng mới — chỉ có sidebar/workspace, không chứa DocType (mẫu hrms/hr_setup).
NAV_ONLY_MODULES = ["Overtime Registration", "New Joiners", "Employee Photos", "Shoe Rack", "IT Tools"]

# ── workspace Home: (module, name, shortcuts [(label, type, link_to|url)]) ────
WORKSPACES = [
	("Network", "Devices and Security", "shield", [
		("Door Control", "URL", "/door_control"),
		("Biometric Sync", "Page", "biometric-sync"),
		("CCTV Tracking", "DocType", "CCTV Tracking"),
		("Door Access Log", "DocType", "Door Access Log"),
		("Camera", "DocType", "Camera"),
	]),
	("IT Tools", "IT Tools", "wrench", [
		("Dev Tool", "URL", "/dev-tool"),
		("Mindmap", "URL", "/mindmap"),
		("QR Code Generator", "URL", "/qr-code"),
	]),
]

# ── desktop icon: (label, link, logo, roles) ── thứ tự = thứ tự trên lưới ────
ICONS = [
	("Overtime Registration", "/desk/overtime/overtime-registration", "tiqn_app_icon_4.svg", []),
	("New Joiners", "/desk/new-joiners/employee", "new_joiners.svg", ["HR Manager", "HR User"]),
	("Employee Photos", "/employee-photos", "gallery.svg", ["HR Manager", "HR User", "Administrator"]),
	("Devices and Security", "/desk/devices-and-security", "cctv.svg", ["System Manager", "Door Control"]),
	("Vehicle Management", "/desk/vehicle-management/vehicle-dispatch", "vehicle_dispatch.svg", ["Vehicle Manager", "System Manager"]),
	("Health Check Up", "/desk/health-checkup/health-check-up", "doctor.svg", ["HR Manager", "HR User", "Administrator"]),
	("Shoe Rack", "/desk/shoe-rack-management/shoe-rack-dashboard", "shoe_rack.svg", ["HR Manager", "HR User", "Administrator"]),
	("Employee Portal", "/desk/employee-portal/payslip-upload", "employee_portal.svg", ["CnB", "System Manager"]),
	("IT Tools", "/desk/it-tools", "coding.svg", []),
]


def module_path(module):
	return os.path.join(APP, scrub(module))


def write(path, doc):
	os.makedirs(os.path.dirname(path), exist_ok=True)
	with open(path, "w") as f:
		f.write(json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n")


def build_sidebars():
	for module, title, header_icon, items in SIDEBARS:
		for idx, item in enumerate(items, 1):
			item["idx"] = idx
		write(os.path.join(module_path(module), "sidebar", scrub(title), f"{scrub(title)}.json"), {
			"app": APP_NAME, "creation": STAMP, "docstatus": 0, "doctype": "Sidebar",
			"header_icon": header_icon, "idx": 0, "items": items, "modified": SIDEBAR_STAMPS.get(title, STAMP),
			"modified_by": "Administrator", "module": module, "name": title, "owner": "Administrator",
			"standard": 1, "title": title,
		})


def build_workspaces():
	for module, name, icon, shortcuts in WORKSPACES:
		content = [{"id": "hdr", "type": "header", "data": {"text": f'<span class="h4"><b>{name}</b></span>', "col": 12}}]
		rows = []
		for i, (label, kind, target) in enumerate(shortcuts, 1):
			row = {"doctype": "Workspace Shortcut", "label": label, "type": kind, "color": "Grey", "idx": i}
			if kind == "URL":
				row["url"] = target
			else:
				row["link_to"] = target
				if kind == "DocType":
					row["doc_view"] = "List"
			rows.append(row)
			content.append({"id": f"sc{i}", "type": "shortcut", "data": {"shortcut_name": label, "col": 3}})
		write(os.path.join(module_path(module), "workspace", scrub(name), f"{scrub(name)}.json"), {
			"charts": [], "content": json.dumps(content), "creation": STAMP, "custom_blocks": [],
			"docstatus": 0, "doctype": "Workspace", "for_user": "", "hide_custom": 0, "icon": icon,
			"idx": 0, "is_hidden": 0, "label": name, "links": [], "modified": STAMP,
			"modified_by": "Administrator", "module": module, "name": name, "number_cards": [],
			"owner": "Administrator", "public": 1, "quick_lists": [], "roles": [], "sequence_id": 1.0,
			"shortcuts": rows, "standard": 1, "title": name,
		})


def build_nav_modules():
	for module in NAV_ONLY_MODULES:
		path = os.path.join(module_path(module), "__init__.py")
		os.makedirs(os.path.dirname(path), exist_ok=True)
		if not os.path.exists(path):
			open(path, "w").close()
	with open(os.path.join(APP, "modules.txt")) as f:
		modules = [m.strip() for m in f if m.strip()]
	for module in NAV_ONLY_MODULES:
		if module not in modules:
			modules.append(module)
	with open(os.path.join(APP, "modules.txt"), "w") as f:
		f.write("\n".join(modules) + "\n")


def build_dock():
	titles = {module: title for module, title, _, _ in SIDEBARS}
	icons = {module: icon for module, _, icon, _ in SIDEBARS}
	items = [
		{"added": 0, "hidden": 0, "icon": icons[module], "link_to": titles[module], "link_type": "Sidebar",
		 "title": titles[module], "idx": i}
		for i, (module, *_rest) in enumerate(SIDEBARS, 1)
	]
	write(os.path.join(APP, "dock", APP_NAME, f"{APP_NAME}.json"), {
		"app": APP_NAME, "creation": STAMP, "docstatus": 0, "doctype": "Dock", "idx": 0,
		"items": items, "modified": STAMP_ICONS, "modified_by": "Administrator", "name": APP_NAME,
		"owner": "Administrator", "standard": 1, "user": "",
	})


def build_icons():
	folder = os.path.join(APP, "desktop_icon")
	keep = set()
	for idx, (label, route, logo, roles) in enumerate(ICONS):
		fname = f"{scrub(label)}.json"
		keep.add(fname)
		write(os.path.join(folder, fname), {
			"app": APP_NAME, "bg_color": "blue", "creation": STAMP, "docstatus": 0,
			"doctype": "Desktop Icon", "hidden": 0, "icon_type": "Link", "idx": idx, "label": label,
			"link": route, "link_type": "External", "logo_url": IMG + logo, "modified": STAMP_ICONS,
			"modified_by": "Administrator", "name": label, "owner": "Administrator",
			"restrict_removal": 0, "roles": [{"role": r} for r in roles], "standard": 1,
		})
	for fname in os.listdir(folder):
		if fname.endswith(".json") and fname not in keep:
			os.remove(os.path.join(folder, fname))
			print("removed icon", fname)


if __name__ == "__main__":
	build_nav_modules()
	build_sidebars()
	build_workspaces()
	build_dock()
	build_icons()
	print("sidebars:", len(SIDEBARS), "| workspaces:", len(WORKSPACES), "| icons:", len(ICONS))
