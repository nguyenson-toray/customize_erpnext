"""Kiểm tra điều hướng TIQN trên hệ sidebar frappe v16.50+ — chỉ đọc.

Chạy:
    cd ~/frappe-bench/sites && ../env/bin/python -c "
    import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect()
    exec(open('../apps/customize_erpnext/customize_erpnext/scripts/test_navigation.py').read())"

Dựng bootinfo y như trình duyệt nhận, rồi soát:
- `canonical_shell` của mọi trang TIQN trên menu (trang mở từ ô tìm kiếm / link vào sidebar nào);
- đủ 8 icon TIQN, Frappe HR đủ 9 icon con, dock TIQN đủ 8 module;
- slug của shell khác slug trang đầu tiên (nếu trùng, router không ghi shell vào URL → sidebar "dính");
- 6 DocType đã xoá không còn, không link nào trỏ vào;
- tài khoản công nhân (không phải HR) thấy icon Overtime Registration.
Plan: .claude/plans/customize_erpnext_navigation_reorg.md
"""

import frappe
from frappe.boot import get_bootinfo

ICONS = {"Overtime Registration", "New Joiners", "Employee Photos", "Devices and Security",
		 "Vehicle Management", "Health Check Up", "Shoe Rack", "IT Tools"}

EXPECTED = {
	"DocType": {
		"Overtime Registration": "Overtime",
		"Employee Self Update Info": "New Joiners",
		"Employee Self Update Info Setting": "New Joiners",
		"CCTV Tracking": "Devices and Security", "Camera": "Devices and Security", "NVR": "Devices and Security",
		"Door Control Action": "Devices and Security", "Door Access Log": "Devices and Security",
		"Door Alert Setting": "Devices and Security", "Attendance Machine Setting": "Devices and Security",
		"TIQN Vehicle Trip": "Vehicle Management", "TIQN Vehicle Request": "Vehicle Management",
		"TIQN Vehicle": "Vehicle Management",
		"Health Check-Up": "Health Checkup",
		"Shoe Rack": "Shoe Rack Management", "Shoe Rack Layout Settings": "Shoe Rack Management",
		"Section": "HR Setup", "Group": "HR Setup", "Resignation Reason Group": "HR Setup",
		"Resignation Reason Group 2": "HR Setup", "Employee Maternity": "HR Setup",
		"Labor Contract": "HR Setup", "Employee Item Reissue": "HR Setup",
		"Resignation Application": "Tenure",
		"Attendance Calculation Setting": "Shift & Attendance",
		"Employee Dependent": "Payroll", "External Personnel": "Payroll",
		"Packing List": "Stock",
		"Employee": "HR Setup",
	},
	"Report": {
		"Overtime Registration": "Overtime",
		"Shift Attendance Customize": "Shift & Attendance",
		"Overtime Registration by Time Slot": "Shift & Attendance",
		"Overtime Registration Quantity": "Shift & Attendance",
		"OT Compliance": "Shift & Attendance",
		"Employee Maternity Report": "HR Setup", "Labor Contract Report": "HR Setup",
		"Employee Transfer and Promotion": "Tenure",
		"Stock Balance Customize": "Stock", "Stock Ledger Customize": "Stock",
		"BOM Balance Sheet": "Manufacturing",
		"TIQN Vehicle KM": "Vehicle Management",
	},
	"Page": {
		"vehicle-dispatch": "Vehicle Management",
		"health-check-up-management": "Health Checkup",
		"shoe-rack-dashboard": "Shoe Rack Management", "layout-manager": "Shoe Rack Management",
		"biometric-sync": "Devices and Security",
	},
}

DELETED = ["Purchase Request", "Purchase Request Items", "Stock Entry Multi Work Orders",
		   "Stock Entry Multi Work Orders Table WO", "Stock Entry Multi Work Orders Table Material",
		   "Overtime Request", "OT Employee Detail", "Overtime Configuration", "Overtime Level",
		   "Vehicle Trip", "Vehicle List"]

ok = fail = 0


def check(label, cond, extra=""):
	global ok, fail
	if cond:
		ok += 1
	else:
		fail += 1
		print(f"  FAIL  {label}  {extra}")


def boot_for(user):
	frappe.set_user(user)
	frappe.clear_cache(user=user)
	return get_bootinfo()


def shell_slug(name):
	return name.lower().replace("&", " and ").strip().replace("  ", " ").replace(" ", "-")


def entity_slug(name):
	return name.lower().replace(" ", "-")


def sidebar_for(payload, key):
	return payload.get(key) or next((e for e in payload.values() if e.get("module") == key), None)


def run():
	global ok, fail
	ok = fail = 0

	print("=== 1. Administrator")
	b = boot_for("Administrator")
	icons = {i.label for i in b.desktop_icons if i.get("app") == "customize_erpnext"}
	check("đúng 8 icon TIQN", icons == ICONS, f"thừa {icons - ICONS} · thiếu {ICONS - icons}")
	hr = [i.label for i in b.desktop_icons if i.get("parent_icon") == "Frappe HR"]
	check("Frappe HR đủ 9 icon con", len(hr) == 9, hr)
	dock = (b.get("dock") or {}).get("customize_erpnext") or {}
	dock_items = dock.get("items") if isinstance(dock, dict) else dock
	check("dock TIQN đủ 8 module", len(dock_items or []) == 8, dock_items)

	for icon in ICONS:
		check(f"icon {icon} tìm được shell", sidebar_for(b.module_sidebars, icon) is not None)

	print("=== 2. Trang mở đúng sidebar (canonical_shell)")
	for kind, entities in EXPECTED.items():
		for name, shell in entities.items():
			got = (b.canonical_shell.get(kind) or {}).get(name)
			check(f"{kind} {name} → {shell}", got == shell, f"ra {got}")

	print("=== 3. Quy tắc slug của shell TIQN")
	for name, entry in b.module_sidebars.items():
		if entry.get("app") != "customize_erpnext":
			continue
		first = next((i for i in entry.get("items", []) if i.get("type") == "Link"), None)
		if first and first.get("link_type") in ("DocType", "Report", "Page", "Dashboard"):
			check(f"shell {name}: slug khác trang đầu", shell_slug(name) != entity_slug(first["link_to"]),
				  f"{shell_slug(name)} == {entity_slug(first['link_to'])}")
	# Shell trùng slug DocType/Page/Report: router đọc /desk/<shell>/<x> thành bản ghi <x> → 404.
	taken = {entity_slug(n) for n in frappe.get_all("DocType", pluck="name")}
	taken |= set(frappe.get_all("Page", pluck="name"))
	taken |= {entity_slug(n) for n in frappe.get_all("Report", pluck="name")}
	for name, entry in b.module_sidebars.items():
		if entry.get("app") == "customize_erpnext":
			check(f"shell {name}: slug không trùng DocType/Page/Report", shell_slug(name) not in taken)
	check("module Customize Erpnext không còn shell",
		  not [n for n, e in b.module_sidebars.items() if e.get("module") == "Customize Erpnext"])

	print("=== 4. 6 DocType đã xoá")
	for dt in DELETED:
		check(f"{dt} không còn", not frappe.db.exists("DocType", dt))
		check(f"không link nào trỏ {dt}", not frappe.db.exists("Sidebar Item", {"link_to": dt}))
	check("không còn report Vehicle Trip Report", not frappe.db.exists("Report", "Vehicle Trip Report"))
	check("không còn custom field multi WO",
		  not frappe.db.exists("Custom Field", "Stock Entry-custom_stock_entry_multi_work_orders"))

	print("=== 5. User HR")
	hr_user = frappe.db.sql("""select u.name from tabUser u join `tabHas Role` r on r.parent=u.name
		where u.enabled=1 and u.user_type='System User' and r.role='HR Manager' and u.name!='Administrator'
		order by u.name limit 1""", pluck=True)
	if hr_user:
		b = boot_for(hr_user[0])
		icons = {i.label for i in b.desktop_icons if i.get("app") == "customize_erpnext"}
		for icon in ("New Joiners", "Employee Photos", "Overtime Registration", "Health Check Up", "Shoe Rack"):
			check(f"{hr_user[0]} thấy icon {icon}", icon in icons, icons)

	print("=== 6. Tài khoản công nhân / tổ trưởng tạo phiếu tăng ca (không phải HR)")
	worker = frappe.db.sql("""select o.owner from `tabOvertime Registration` o join tabUser u on u.name=o.owner
		where u.enabled=1 and u.user_type='System User' and not exists (select 1 from `tabHas Role` h
		where h.parent=o.owner and h.role in ('HR Manager','HR User','System Manager'))
		group by o.owner order by max(o.creation) desc limit 1""", pluck=True)
	if worker:
		b = boot_for(worker[0])
		icons = {i.label for i in b.desktop_icons if i.get("app") == "customize_erpnext"}
		check(f"{worker[0]} thấy icon Overtime Registration", "Overtime Registration" in icons, icons)
		check(f"{worker[0]}: Overtime Registration → Overtime",
			  (b.canonical_shell.get("DocType") or {}).get("Overtime Registration") == "Overtime")
	else:
		print("  (không tìm được tài khoản tạo phiếu tăng ca ngoài HR — bỏ qua)")

	frappe.set_user("Administrator")
	print(f"\n{'=' * 60}\nPASS {ok}   FAIL {fail}\n{'=' * 60}")
	frappe.db.rollback()
	return {"pass": ok, "fail": fail}


run()
