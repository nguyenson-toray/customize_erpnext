"""Tạo Item Variant theo lô — bỏ qua (skip) variant bị trùng thay vì dừng cả lô.

Bản gốc `erpnext.controllers.item_variant.create_multiple_variants` chỉ kiểm tra
`get_variant()` (so khớp theo tổ hợp attribute). Trong một số trường hợp tổ hợp
abbreviation lại sinh ra item_code/name ĐÃ tồn tại (vd variant cũ lệch attribute,
hoặc đụng mã) → `variant.save()` ném DuplicateEntryError và dừng toàn bộ.

Hàm ở đây bọc mỗi lần insert trong một savepoint: nếu trùng thì rollback riêng
dòng đó, ghi nhận tên item bị bỏ qua rồi tiếp tục tạo các variant còn lại.
Trả về {"created": <số tạo mới>, "skipped": [<tên item trùng>...]} để client
hiển thị frappe.show_alert.
"""

import json

import frappe
from frappe import _

from erpnext.controllers.item_variant import (
    create_variant,
    generate_keyed_value_combinations,
    get_variant,
)


@frappe.whitelist()
def enqueue_multiple_variant_creation(item, args, use_template_image=False):
	"""Giữ nguyên hành vi enqueue của ERPNext (sync khi nhỏ, background khi lớn),
	nhưng dùng create_multiple_variants_skip_duplicates để bỏ qua item trùng."""
	variants = json.loads(args) if isinstance(args, str) else args

	total_variants = 1
	for key in variants:
		total_variants *= len(variants[key])

	if total_variants >= 600:
		frappe.throw(_("Please do not create more than 500 items at a time"))
		return

	if total_variants < 10:
		return create_multiple_variants_skip_duplicates(item, args, use_template_image)
	else:
		frappe.enqueue(
			"customize_erpnext.api.item.create_variants.create_multiple_variants_skip_duplicates",
			item=item,
			args=args,
			use_template_image=use_template_image,
			now=frappe.in_test,
		)
		return "queued"


@frappe.whitelist()
def create_multiple_variants_skip_duplicates(item, args, use_template_image=False):
	if isinstance(args, str):
		args = json.loads(args)
	args = {key: values for key, values in args.items() if values}

	template_item = frappe.get_doc("Item", item)
	args_set = generate_keyed_value_combinations(args)

	created = 0
	skipped = []

	for attribute_values in args_set:
		# Đã tồn tại đúng tổ hợp attribute → bỏ qua (như ERPNext gốc)
		if get_variant(item, args=attribute_values):
			continue

		variant = create_variant(item, attribute_values)
		if use_template_image and template_item.image:
			variant.image = template_item.image

		savepoint = "create_variant_skip_dup"
		try:
			frappe.db.savepoint(savepoint)
			variant.insert()
			created += 1
		except frappe.DuplicateEntryError:
			# Trùng tên item (vd tổ hợp abbr tạo ra name đã có) → rollback riêng dòng này, bỏ qua
			frappe.db.rollback(save_point=savepoint)
			skipped.append(variant.name or variant.item_code)

	return {"created": created, "skipped": skipped}
