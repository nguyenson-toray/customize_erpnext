"""Lọc các Item Variant "chết": tồn kho = 0 VÀ chưa từng tham gia giao dịch kho.

Điều kiện:
  - Là item variant (variant_of có giá trị).
  - KHÔNG có bất kỳ Stock Ledger Entry nào (chưa từng tham gia giao dịch kho).
    (Mặc định tính cả phiếu đã hủy; bỏ chú thích AND sle.is_cancelled = 0 nếu muốn
     bỏ qua các phiếu đã hủy.)
  - KHÔNG có Bin nào còn actual_qty != 0 (tồn kho = 0).

Tham số:
  - item_group: bỏ trống = tất cả nhóm.
  - created_before: chỉ lấy item có creation < ngày này (bỏ trống = không lọc theo ngày).
"""

import frappe


@frappe.whitelist()
def get_unused_variants(item_group=None, created_before=None):
	conditions = ["i.variant_of IS NOT NULL", "i.variant_of != ''"]
	params = {}

	if item_group:
		conditions.append("i.item_group = %(item_group)s")
		params["item_group"] = item_group

	if created_before:
		conditions.append("i.creation < %(created_before)s")
		params["created_before"] = created_before

	where = " AND ".join(conditions)

	rows = frappe.db.sql(
		f"""
		SELECT i.name AS item_code, i.item_name, i.item_group,
		       i.variant_of, i.creation, i.disabled
		FROM `tabItem` i
		WHERE {where}
		  AND NOT EXISTS (
		        SELECT 1 FROM `tabStock Ledger Entry` sle
		        WHERE sle.item_code = i.name
		        -- AND sle.is_cancelled = 0
		  )
		  AND NOT EXISTS (
		        SELECT 1 FROM `tabBin` b
		        WHERE b.item_code = i.name AND b.actual_qty != 0
		  )
		ORDER BY i.item_group, i.name
		""",
		params,
		as_dict=True,
	)

	return {"count": len(rows), "items": rows}

"""

 Cách gọi

  Bench console:
  # tất cả nhóm, tạo trước 2026-06-01
  bench --site erp.tiqn.local execute customize_erpnext.api.item.unused_variants.get_unused_variants \
    --kwargs "{'created_before': '2026-06-01'}"

  # lọc theo nhóm
  bench --site erp.tiqn.local execute customize_erpnext.api.item.unused_variants.get_unused_variants \
    --kwargs "{'item_group': 'C-Fabric', 'created_before': '2026-06-01'}"
    
  HTTP API:
  GET /api/method/customize_erpnext.api.item.unused_variants.get_unused_variants?item_group=C-Fabric&created_before=2026-06-01

  SQL thuần (chạy bench --site erp.tiqn.local mariadb)

  SELECT i.name AS item_code, i.item_name, i.item_group,
         i.variant_of, i.creation, i.disabled
  FROM `tabItem` i
  WHERE i.variant_of IS NOT NULL AND i.variant_of != ''
    AND i.creation < '2026-06-01'                 -- bỏ dòng này nếu không lọc ngày
    AND i.item_group = 'C-Fabric'                 -- bỏ dòng này = tất cả nhóm
    AND NOT EXISTS (
          SELECT 1 FROM `tabStock Ledger Entry` sle
          WHERE sle.item_code = i.name            -- thêm: AND sle.is_cancelled = 0  để bỏ qua phiếu đã hủy
    )
    AND NOT EXISTS (
          SELECT 1 FROM `tabBin` b
          WHERE b.item_code = i.name AND b.actual_qty != 0
    )
  ORDER BY i.item_group, i.name;

  Lưu ý

  - created_before so sánh creation < ngày → '2026-06-01' nghĩa là trước 00:00 ngày 1/6 (không gồm ngày 1/6). Muốn gồm cả ngày đó thì dùng '2026-06-02'.
  - Phiếu đã hủy: mặc định nếu item từng có giao dịch rồi hủy (SLE is_cancelled=1) vẫn bị coi là "đã tham gia" → bị loại khỏi kết quả. Bỏ comment AND 
  sle.is_cancelled = 0 nếu muốn xem chúng là "chưa giao dịch".
#   - item_group đang khớp chính xác tên nhóm (không gồm nhóm con). Nếu cần gồm cả nhóm con (nested set lft/rgt) mình bổ sung được.
"""