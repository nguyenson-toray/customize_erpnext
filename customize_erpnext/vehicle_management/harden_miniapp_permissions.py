# Copyright (c) 2026, IT Team - TIQN and contributors
# For license information, please see license.txt

"""Give the Zalo Mini App its own role instead of `Vehicle Manager`.

    bench --site erp.tiqn.local execute \
        customize_erpnext.vehicle_management.harden_miniapp_permissions.execute

    # xem trước, không ghi gì
    bench --site erp.tiqn.local execute \
        customize_erpnext.vehicle_management.harden_miniapp_permissions.execute \
        --kwargs "{'dry_run': True}"

Vì sao: `miniapp@tiqn.com.vn` đang mang role `Vehicle Manager` - CÙNG role với 9 nhân
viên thật. Role đó có `delete = 1` trên cả 6 DocType, và API key của Mini App **nằm
trong chính file client**. Đo ngày 22/09/2026: một lệnh DELETE qua REST xoá vĩnh viễn
một chuyến (HTTP 202, biến mất khỏi DB).

Không thể siết thẳng `Vehicle Manager` - làm thế là cắt quyền của 9 người đang dùng
Desk. Nên Mini App có role riêng, hẹp đúng bằng những gì nó thật sự gọi.

Mức quyền dưới đây suy từ các lệnh `_guard(...)` trong api/vehicle_management.py cộng
với 4 đường REST mà Mini App đang dùng trên `TIQN Zalo Role Map`. KHÔNG có `delete`,
KHÔNG có `export` (fleet data), KHÔNG có `share`/`email`/`print`.
"""

import frappe

ROLE = "Vehicle Mini App"
API_USER = "miniapp@tiqn.com.vn"

# doctype -> các quyền được bật. Mọi quyền không liệt kê đều là 0.
PERMISSIONS = {
	# create_trip, combine_requests_to_trip, update_trip, checkin/checkout...
	"TIQN Vehicle Trip": ("read", "write", "create"),
	# create_request, update_request, approve/reject, assign_request_to_trip
	"TIQN Vehicle Request": ("read", "write", "create"),
	# get_vehicles, update_vehicle_status
	"TIQN Vehicle": ("read", "write"),
	# get_drivers, verify_driver_login, update_zalo_user_id(role="driver")
	# 4 đường REST Mini App đang dùng: GET một bản ghi, GET có filter, POST, PUT
	"TIQN Zalo Role Map": ("read", "write", "create"),
	# get_fixed_templates_for_driver - chỉ đọc; lịch cố định do điều hành đặt
	"TIQN Fixed Trip Schedule": ("read",),
}

ALL_PERMS = ("read", "write", "create", "delete", "submit", "cancel", "amend",
             "report", "export", "import", "share", "print", "email")


def execute(dry_run=False):
	changes = []

	if not frappe.db.exists("Role", ROLE):
		changes.append(f"tạo Role {ROLE}")
		if not dry_run:
			frappe.get_doc({
				"doctype": "Role", "role_name": ROLE, "desk_access": 1,
				"disabled": 0,
			}).insert(ignore_permissions=True)

	for doctype, granted in PERMISSIONS.items():
		wanted = {p: (1 if p in granted else 0) for p in ALL_PERMS}
		existing = frappe.db.get_value(
			"Custom DocPerm", {"parent": doctype, "role": ROLE, "permlevel": 0}, "name"
		)
		if existing:
			current = frappe.db.get_value("Custom DocPerm", existing, list(ALL_PERMS), as_dict=True)
			if all(current.get(p) == wanted[p] for p in ALL_PERMS):
				continue
			changes.append(f"sửa quyền {doctype}: {', '.join(granted)}")
			if not dry_run:
				frappe.db.set_value("Custom DocPerm", existing, wanted)
		else:
			changes.append(f"cấp quyền {doctype}: {', '.join(granted)}")
			if not dry_run:
				frappe.get_doc({
					"doctype": "Custom DocPerm", "parent": doctype, "parenttype": "DocType",
					"parentfield": "permissions", "role": ROLE, "permlevel": 0, **wanted,
				}).insert(ignore_permissions=True)

	user = frappe.get_doc("User", API_USER)
	roles = {r.role for r in user.roles}

	if ROLE not in roles:
		changes.append(f"thêm role {ROLE} cho {API_USER}")
		if not dry_run:
			user.append("roles", {"role": ROLE})

	# 🔴 Gỡ Vehicle Manager là bước thật sự đóng lỗ DELETE. Làm SAU khi role mới đã
	# được thêm, để không có khoảnh khắc nào key mất sạch quyền.
	if "Vehicle Manager" in roles:
		changes.append(f"GỠ role Vehicle Manager khỏi {API_USER} (đây là chỗ có delete)")
		if not dry_run:
			user.roles = [r for r in user.roles if r.role != "Vehicle Manager"]

	if not dry_run and changes:
		user.save(ignore_permissions=True)
		frappe.db.commit()
		frappe.clear_cache()

	print(("[XEM TRƯỚC] " if dry_run else "") + f"{len(changes)} thay đổi:")
	for c in changes:
		print("  - " + c)
	if not changes:
		print("  (không có gì để làm)")
	return changes
