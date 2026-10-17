#!/usr/bin/env python3
"""Sinh docs/flowchart/erpnext.drawio — sơ đồ hoạt động của ERPNext v16.

Chạy:  python3 scripts/build_erpnext_flowchart.py
Đối chiếu source mà không ghi đè file:  ... --check

Vì sao có script này: bản .drawio cũ vẽ tay từ 2022 (ERPNext v13) và đã lệch khá
nhiều so với v16 — nhân sự tách hẳn sang app hrms, thêm module Subcontracting,
Assets, Quality Management. Mỗi lần ERPNext lên version, sửa dữ liệu trong file
này rồi chạy lại, không phải kéo thả từng ô.

Các mũi tên KHÔNG viết theo trí nhớ: mỗi cái kèm một chỗ trong source ERPNext
đang cài (bảng EVIDENCE), `--check` sẽ grep lại toàn bộ.

Phần bố cục / sinh XML / ghi tài liệu nằm ở flowchart_common.py.
Sơ đồ nhân sự là file riêng: build_hrms_flowchart.py.
"""

from flowchart_common import COL, GROUP_W, H_GAP, Flowchart, main

VERSION = "v16"
SRC = "/home/frappe/frappe-bench/apps/erpnext/erpnext"

# ── khung module: (id, tên, màu, cột, hàng, [(id ô, nhãn), ...]) ──────────
MODULES = [
    ("g_crm", "CRM", "crm", 0, 0, [
        ("lead", "Lead"), ("opp", "Opportunity"), ("cust", "Customer")]),
    ("g_selling", "Selling", "selling", 1, 0, [
        ("quote", "Quotation"), ("so", "Sales Order")]),
    ("g_stock", "Stock", "stock", 2, 0, [
        ("item", "Item &amp; Warehouse"), ("mr", "Material Request"),
        ("dn", "Delivery Note"), ("pr", "Purchase Receipt"), ("se", "Stock Entry")]),
    ("g_buying", "Buying", "buying", 3, 0, [
        ("supplier", "Supplier"), ("rfq", "Request for Quotation"),
        ("sq", "Supplier Quotation"), ("po", "Purchase Order")]),
    ("g_mfg", "Manufacturing", "mfg", 4, 0, [
        ("bom", "BOM"), ("pp", "Production Plan"),
        ("wo", "Work Order"), ("jc", "Job Card")]),
    ("g_asset", "Assets", "asset", 5, 0, [
        ("asset", "Asset"), ("dep", "Depreciation Schedule")]),
    ("g_project", "Projects", "project", 0, 1, [
        ("project", "Project"), ("task", "Task"), ("timesheet", "Timesheet")]),
    ("g_support", "Maintenance &amp; Support", "support", 1, 1, [
        ("issue", "Issue"), ("warranty", "Warranty Claim"),
        ("ms", "Maintenance Schedule"), ("mv", "Maintenance Visit")]),
    ("g_sub", "Subcontracting", "sub", 3, 1, [
        ("sco", "Subcontracting Order"), ("scr", "Subcontracting Receipt")]),
    ("g_quality", "Quality", "quality", 4, 1, [
        ("qi", "Quality Inspection")]),
]

EDGES = [
    ("lead", "opp", "", "doc"), ("opp", "cust", "", "doc"),
    ("cust", "quote", "", "doc"), ("quote", "so", "", "doc"),
    ("so", "dn", "deliver", "doc"), ("so", "si", "bill", "doc"),
    ("so", "mr", "shortage", "doc"), ("so", "project", "", "doc"),
    ("so", "ms", "service contract", "doc"),
    ("dn", "si", "", "doc"),
    ("supplier", "rfq", "", "data"),
    ("mr", "rfq", "", "doc"), ("rfq", "sq", "", "doc"), ("sq", "po", "", "doc"),
    ("mr", "po", "direct", "doc"),
    ("po", "pr", "", "doc"), ("pr", "pi", "", "doc"),
    ("po", "sco", "subcontract", "doc"), ("sco", "scr", "", "doc"),
    ("scr", "pr", "", "doc"),
    ("pr", "asset", "fixed asset", "doc"), ("asset", "dep", "", "data"),
    ("bom", "pp", "", "data"), ("bom", "wo", "", "data"),
    ("pp", "wo", "", "doc"), ("pp", "mr", "raw material", "doc"),
    ("wo", "jc", "", "doc"), ("wo", "se", "finished goods", "doc"),
    ("pr", "qi", "", "data"), ("jc", "qi", "", "data"),
    ("project", "task", "", "doc"), ("task", "timesheet", "", "doc"),
    ("timesheet", "si", "billable hours", "doc"),
    ("warranty", "mv", "", "doc"), ("ms", "mv", "", "doc"),
    ("si", "pay", "receipt", "doc"), ("pi", "pay", "payment", "doc"),
    ("si", "gl", "", "gl"), ("pi", "gl", "", "gl"),
    ("pay", "gl", "", "gl"), ("je", "gl", "", "gl"),
    ("coa", "gl", "", "data"), ("cc", "gl", "", "data"),
]

OVERHEAD = {
    ("pp", "mr"): ("L", COL[4] - H_GAP // 2, "R", COL[2] + GROUP_W + H_GAP // 2),
}

GROUP_EDGES = [
    ("g_stock", "g_acc", "stock value"),
    ("g_asset", "g_acc", "depreciation"),
]

EVIDENCE = {
    ("lead", "opp"): ("crm/doctype/lead/lead.py", r"def make_opportunity",
                      "Lead > Create > Opportunity"),
    ("opp", "cust"): ("crm/doctype/opportunity/opportunity.py", r"def make_customer",
                      "Opportunity > Create > Customer"),
    ("cust", "quote"): ("selling/doctype/customer/customer.py", r"def make_quotation",
                        "Customer > Create > Quotation"),
    ("quote", "so"): ("selling/doctype/quotation/quotation.py", r'"doctype": "Sales Order"',
                      "Quotation > Create > Sales Order"),
    ("so", "dn"): ("selling/doctype/sales_order/sales_order.py", r'"doctype": "Delivery Note"',
                   "Sales Order > Create > Delivery Note"),
    ("so", "si"): ("selling/doctype/sales_order/sales_order.py", r'"doctype": "Sales Invoice"',
                   "Sales Order > Create > Sales Invoice"),
    ("so", "mr"): ("selling/doctype/sales_order/sales_order.py", r'"doctype": "Material Request"',
                   "Sales Order > Create > Material Request (hàng thiếu)"),
    ("so", "project"): ("selling/doctype/sales_order/sales_order.py", r'"doctype": "Project"',
                        "Sales Order > Create > Project"),
    ("so", "ms"): ("selling/doctype/sales_order/sales_order.py", r'"doctype": "Maintenance Schedule"',
                   "Sales Order > Create > Maintenance Schedule"),
    ("dn", "si"): ("stock/doctype/delivery_note/delivery_note.py", r'"doctype": "Sales Invoice"',
                   "Delivery Note > Create > Sales Invoice"),
    ("supplier", "rfq"): ("buying/doctype/request_for_quotation/request_for_quotation.py",
                          r"Request for Quotation Supplier",
                          "RFQ chọn nhà cung cấp vào bảng con, không sinh chứng từ"),
    ("mr", "rfq"): ("stock/doctype/material_request/material_request.py",
                    r'"doctype": "Request for Quotation"', "Material Request > Create > RFQ"),
    ("mr", "po"): ("stock/doctype/material_request/material_request.py",
                   r'"doctype": "Purchase Order"', "Material Request > Create > Purchase Order"),
    ("rfq", "sq"): ("buying/doctype/request_for_quotation/request_for_quotation.py",
                    r'"doctype": "Supplier Quotation"', "RFQ > Create > Supplier Quotation"),
    ("sq", "po"): ("buying/doctype/supplier_quotation/supplier_quotation.py",
                   r'"doctype": "Purchase Order"', "Supplier Quotation > Create > Purchase Order"),
    ("po", "pr"): ("buying/doctype/purchase_order/purchase_order.py",
                   r'"doctype": "Purchase Receipt"', "Purchase Order > Create > Purchase Receipt"),
    ("pr", "pi"): ("stock/doctype/purchase_receipt/purchase_receipt.py",
                   r'"doctype": "Purchase Invoice"', "Purchase Receipt > Create > Purchase Invoice"),
    ("po", "sco"): ("buying/doctype/purchase_order/purchase_order.py",
                    r'"doctype": "Subcontracting Order"',
                    "PO gia công (is_subcontracted) > Create > Subcontracting Order"),
    ("sco", "scr"): ("subcontracting/doctype/subcontracting_order/subcontracting_order.py",
                     r'"doctype": "Subcontracting Receipt"',
                     "Subcontracting Order > Create > Subcontracting Receipt"),
    ("scr", "pr"): ("subcontracting/doctype/subcontracting_receipt/subcontracting_receipt.py",
                    r"def make_purchase_receipt",
                    "Nhận hàng gia công xong sinh Purchase Receipt để ghi công nợ"),
    ("pr", "asset"): ("controllers/buying_controller.py", r"def make_asset",
                      "Dòng hàng is_fixed_asset trên PR/PI tự tạo Asset"),
    ("asset", "dep"): ("assets/doctype/asset/asset.py", r"Asset Depreciation Schedule",
                       "Asset sinh lịch khấu hao"),
    ("bom", "pp"): ("manufacturing/doctype/production_plan/production_plan.py", r"bom_no",
                    "Production Plan nổ vật tư theo BOM"),
    ("bom", "wo"): ("manufacturing/doctype/work_order/work_order.py", r"self\.bom_no",
                    "Work Order chạy theo một BOM"),
    ("pp", "wo"): ("manufacturing/doctype/production_plan/production_plan.py",
                   r'frappe\.new_doc\("Work Order"\)', "Production Plan > Create > Work Order"),
    ("pp", "mr"): ("manufacturing/doctype/production_plan/production_plan.py",
                   r'frappe\.new_doc\("Material Request"\)',
                   "Production Plan > Create > Material Request (nguyên liệu thiếu)"),
    ("wo", "jc"): ("manufacturing/doctype/work_order/work_order.py",
                   r'frappe\.new_doc\("Job Card"\)', "Work Order tạo Job Card cho từng công đoạn"),
    ("wo", "se"): ("manufacturing/doctype/work_order/work_order.py", r"def make_stock_entry",
                   "Work Order > Start/Finish > Stock Entry (xuất NVL, nhập thành phẩm)"),
    ("pr", "qi"): ("stock/doctype/quality_inspection/quality_inspection.json", r"Purchase Receipt",
                   "Quality Inspection tham chiếu Purchase Receipt"),
    ("jc", "qi"): ("stock/doctype/quality_inspection/quality_inspection.json", r"Job Card",
                   "Quality Inspection tham chiếu Job Card"),
    ("project", "task"): ("projects/doctype/task/task.py", r"project", "Task nằm trong Project"),
    ("task", "timesheet"): ("projects/doctype/task/task.py", r"def make_timesheet",
                            "Task > Create > Timesheet"),
    ("timesheet", "si"): ("projects/doctype/timesheet/timesheet.py", r"def make_sales_invoice",
                          "Timesheet > Create > Sales Invoice (giờ tính tiền)"),
    ("warranty", "mv"): ("support/doctype/warranty_claim/warranty_claim.py",
                         r'"doctype": "Maintenance Visit"',
                         "Warranty Claim > Create > Maintenance Visit"),
    ("ms", "mv"): ("maintenance/doctype/maintenance_schedule/maintenance_schedule.py",
                   r'"doctype": "Maintenance Visit"',
                   "Maintenance Schedule > Create > Maintenance Visit"),
    ("si", "pay"): ("accounts/doctype/payment_entry/payment_entry.py", r"def get_payment_entry",
                    "Sales Invoice > Create > Payment Entry"),
    ("pi", "pay"): ("accounts/doctype/payment_entry/payment_entry.py", r"def get_payment_entry",
                    "Purchase Invoice > Create > Payment Entry"),
    ("si", "gl"): ("accounts/doctype/sales_invoice/sales_invoice.py", r"make_gl_entries",
                   "Sales Invoice submit thì ghi sổ cái"),
    ("pi", "gl"): ("accounts/doctype/purchase_invoice/purchase_invoice.py", r"make_gl_entries",
                   "Purchase Invoice submit thì ghi sổ cái"),
    ("pay", "gl"): ("accounts/doctype/payment_entry/payment_entry.py", r"make_gl_entries",
                    "Payment Entry submit thì ghi sổ cái"),
    ("je", "gl"): ("accounts/doctype/journal_entry/journal_entry.py", r"make_gl_entries",
                   "Journal Entry submit thì ghi sổ cái"),
    ("coa", "gl"): ("accounts/doctype/gl_entry/gl_entry.json", r'"options": "Account"',
                    "Mỗi bút toán trỏ về một tài khoản trong hệ thống tài khoản"),
    ("cc", "gl"): ("accounts/doctype/gl_entry/gl_entry.json", r'"options": "Cost Center"',
                   "Mỗi bút toán trỏ về một cost center"),
    ("g_stock", "g_acc"): ("controllers/stock_controller.py", r"def make_gl_entries",
                           "Mọi phiếu kho có giá trị đều ghi bút toán giá vốn / tồn kho"),
    ("g_asset", "g_acc"): ("assets/doctype/asset/depreciation.py", r"make_depreciation_entry",
                           "Khấu hao định kỳ sinh bút toán"),
}

OMITTED = [
    ("Sales Order → Pick List → Delivery Note", "selling/doctype/sales_order/sales_order.py::create_pick_list"),
    ("Sales Order → Purchase Order (drop ship)", "selling/doctype/sales_order/sales_order.py::make_purchase_order"),
    ("Sales Order → Subcontracting Inward Order (gia công nhận ngoài, mới ở v16)",
     "selling/doctype/sales_order/sales_order.py::get_mapped_subcontracting_inward_order"),
    ("Material Request → Stock Entry / Supplier Quotation",
     "stock/doctype/material_request/material_request.py::make_stock_entry"),
    ("Job Card → Stock Entry / Material Request", "manufacturing/doctype/job_card/job_card.py::make_stock_entry"),
    ("Work Order → Pick List", "manufacturing/doctype/work_order/work_order.py::create_pick_list"),
    ("Delivery Note → Packing Slip / Shipment / Installation Note",
     "stock/doctype/delivery_note/delivery_note.py::make_shipment"),
    ("Chiều ngược: Sales Invoice → Delivery Note, Purchase Invoice → Purchase Receipt",
     "accounts/doctype/sales_invoice/sales_invoice.py::make_delivery_note"),
    ("Prospect / Opportunity → RFQ, Supplier Quotation",
     "crm/doctype/opportunity/opportunity.py::make_request_for_quotation"),
    ("Sales Forecast → Master Production Schedule",
     "manufacturing/doctype/sales_forecast/sales_forecast.py::create_mps"),
    ("Toàn bộ nhân sự (app hrms) — người dùng yêu cầu bỏ khỏi sơ đồ", "apps/hrms"),
]


CHART = Flowchart(
    key="erpnext",
    app="ERPNext",
    version=VERSION,
    src=SRC,
    title="ERPNext %s \u2014 how the system works" % VERSION,
    subtitle="Every document that carries a value posts to the General Ledger.",
    modules=MODULES,
    band=("g_acc", "Accounts", "accounts",
          [(("coa", "Chart of Accounts"), ("cc", "Cost Center")),
           (("si", "Sales Invoice"), ("pi", "Purchase Invoice")),
           (("pay", "Payment Entry"), ("je", "Journal Entry"))],
          ("gl", "General Ledger")),
    edges=EDGES,
    group_edges=GROUP_EDGES,
    overhead=OVERHEAD,
    evidence=EVIDENCE,
    omitted=OMITTED,
    quirks=[
        "**Customer** thuộc module Selling, nhưng vẽ trong khung CRM cho liền mạch "
        "Lead → Opportunity → Customer.",
        "**Quality Inspection** thuộc module Stock, nhưng tách ra khung Quality "
        "vì nó phục vụ cả mua hàng lẫn sản xuất.",
    ],
    rows=(100, 560),
)


if __name__ == "__main__":
    raise SystemExit(main(CHART))
