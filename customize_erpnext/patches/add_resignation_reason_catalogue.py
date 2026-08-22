# Copyright (c) 2026, IT Team - TIQN
# License: MIT

"""Chuyển danh mục lý do nghỉ việc từ file JSON sang DocType, và đổi 2 field trên Employee
từ `Select` sang `Link`.

## Trước

`custom_reason_for_leaving_group` / `_group_2` là **Select với `options` rỗng**; danh sách bơm
vào lúc chạy bằng ~95 dòng JS đọc `employee_reason_for_leaving.json`. HR muốn tự thêm/bớt thì
phải nhờ IT sửa file.

## Sau

`Resignation Reason Group` + `Resignation Reason Group 2` là DocType thật, hai field thành `Link`. Xoá
được cả file JSON lẫn khối JS.

## Vì sao đổi fieldtype an toàn

Đo trên site trước khi viết patch: **3** Employee mang giá trị `Personal` ở field cha, **0** ở
field con. Patch tạo record danh mục TRƯỚC khi đổi fieldtype nên 3 giá trị đó trỏ tới bản ghi có
thật. Giá trị nào không có trong danh mục sẽ được tạo bổ sung — đổi sang Link mà để lại giá trị
mồ côi thì form báo lỗi link không tồn tại và HR tưởng mất dữ liệu.

⚠ Hai field nằm trong `fixtures/custom_field.json`. Sau khi chạy patch phải
`bench export-fixtures --app customize_erpnext`, nếu không lần migrate sau fixture sẽ lật fieldtype
về Select.
"""

import frappe

# Nội dung của `employee_reason_for_leaving.json` tại thời điểm chuyển đổi (commit da53584).
CATALOGUE = {
	"Personal": [
		"Chăm sóc gia đình",
		"Không phù hợp với công việc/ có việc khác",
		"Lương thấp",
		"Sức khỏe",
		"Định hướng nghề nghiệp",
		"Khoảng cách địa lý",
		"Tự ý nghỉ việc/ NLĐ không đồng ý tái ký",
		"Vấn đề khác",
	],
	"Termination": [
		"Không đạt yêu cầu tái ký",
		"Không đạt yêu cầu thử việc",
	],
}

GROUP_FIELD = "custom_reason_for_leaving_group"
REASON_FIELD = "custom_reason_for_leaving_group_2"

# Nhóm gán cho giá trị mồ côi tìm thấy trong dữ liệu cũ.
ORPHAN_GROUP = "Other"


def execute():
	_seed_catalogue()
	_adopt_orphans()
	_convert_fields()


def _seed_catalogue():
	for group, reasons in CATALOGUE.items():
		_ensure_group(group)
		for reason in reasons:
			_ensure_reason(reason, group)


def _ensure_group(group: str):
	if frappe.db.exists("Resignation Reason Group", group):
		return
	frappe.get_doc({
		"doctype": "Resignation Reason Group", "group_name": group, "is_active": 1,
	}).insert(ignore_permissions=True)


def _ensure_reason(reason: str, group: str):
	if frappe.db.exists("Resignation Reason Group 2", reason):
		return
	frappe.get_doc({
		"doctype": "Resignation Reason Group 2",
		"reason_for_leaving_group_2": reason,
		"reason_for_leaving_group": group,
		"is_active": 1,
	}).insert(ignore_permissions=True)


def _adopt_orphans():
	"""Giá trị đang có trong dữ liệu mà danh mục chưa có -> tạo bổ sung.

	Bỏ trắng thì sau khi đổi sang Link, form sẽ báo link không tồn tại trên đúng những hồ sơ cũ
	đó và trông như dữ liệu bị mất.
	"""
	groups = _distinct(GROUP_FIELD)
	reasons = _distinct(REASON_FIELD)

	for group in groups:
		_ensure_group(group)

	if reasons:
		_ensure_group(ORPHAN_GROUP)
	for reason in reasons:
		if frappe.db.exists("Resignation Reason Group 2", reason):
			continue
		# Không suy được nhóm từ giá trị lẻ -> xếp vào Other, HR tự chuyển sau.
		_ensure_reason(reason, ORPHAN_GROUP)


def _distinct(fieldname: str) -> list[str]:
	rows = frappe.db.sql(
		f"""SELECT DISTINCT `{fieldname}` v FROM `tabEmployee`
		    WHERE TRIM(IFNULL(`{fieldname}`, '')) <> ''""",
		pluck=True,
	)
	return [str(v).strip() for v in rows if str(v).strip()]


def _convert_fields():
	"""Đổi `Select` -> `Link` bằng cách ghi thẳng, KHÔNG qua `cf.save()`.

	`CustomField.validate` chặn cứng đổi fieldtype ngoài danh sách `ALLOWED_FIELDTYPE_CHANGE`
	(`frappe/custom/doctype/custom_field/custom_field.py:198`), và cặp `Select -> Link` không nằm
	trong đó.

	Ở đây bỏ qua guard đó là **an toàn và có kiểm chứng**, vì guard tồn tại để chặn đổi sang kiểu
	lưu trữ không tương thích:

	  · Hai kiểu dùng **cùng một cột `varchar(140)`** — đã kiểm trên `information_schema`. Không
	    có thay đổi schema nào cần chạy, `migrate` sau đó cũng không đụng cột.
	  · Giá trị đang có đều đã tồn tại làm bản ghi danh mục (`_seed_catalogue` + `_adopt_orphans`
	    chạy TRƯỚC hàm này), nên không sinh Link mồ côi.

	Đường còn lại là xoá Custom Field rồi tạo lại kiểu Link. Không chọn vì `on_trash` xoá luôn
	mọi Property Setter của field (`custom_field.py:231`) — mất các tinh chỉnh khác đang có mà
	không có gì báo.
	"""
	for fieldname, options in (
		(GROUP_FIELD, "Resignation Reason Group"),
		(REASON_FIELD, "Resignation Reason Group 2"),
	):
		name = frappe.db.get_value("Custom Field", {"dt": "Employee", "fieldname": fieldname})
		if not name:
			continue

		values = {"fieldtype": "Link", "options": options}
		# `custom_reason_for_leaving_group_2` chỉ có nghĩa khi đã chọn nhóm.
		if fieldname == REASON_FIELD:
			values["depends_on"] = f"eval:doc.{GROUP_FIELD}"

		frappe.db.set_value("Custom Field", name, values)

	frappe.clear_cache(doctype="Employee")
