# Sơ đồ hoạt động ERPNext v16

`template.drawio` — mở bằng [draw.io](https://app.diagrams.net) hoặc extension Draw.io Integration của VS Code. File để XML trần (không nén) nên git diff đọc được.

Sinh lại: `python3 scripts/build_erpnext_flowchart.py`
Chỉ kiểm tra, không ghi đè: `python3 scripts/build_erpnext_flowchart.py --check`

> Script từ chối ghi đè nếu file .drawio đã được sửa tay. Muốn bỏ qua thì thêm `--force` (mất hết phần sửa tay).

## Ba loại mũi tên

- **Grey solid arrow — Creates the next document** (tạo chứng từ tiếp theo) — Press Create on the first document and ERPNext opens the next one, already filled in. The two documents stay linked, so quantities and amounts are carried over and tracked.
- **Grey dashed arrow — Supplies data only** (chỉ lấy dữ liệu) — The document at the tip reads master data, a price or a plan from the one at the tail. Nothing is created and nothing is posted.
- **Blue solid arrow — Posts to the General Ledger** (ghi vào sổ cái) — Submitting the document writes its accounting entries by itself. Cancel the document and ERPNext reverses those entries.

## Đối chiếu với source ERPNext v16

Mỗi mũi tên dưới đây lấy từ source ERPNext đang cài chứ không vẽ theo trí nhớ. Cột cuối là chỗ chứng minh, tính từ `apps/erpnext/erpnext/`.

| Từ | Đến | Loại | Nghĩa | Bằng chứng |
| --- | --- | --- | --- | --- |
| Asset | Depreciation Schedule | chỉ lấy dữ liệu | Asset sinh lịch khấu hao | `assets/doctype/asset/asset.py:157` |
| BOM | Production Plan | chỉ lấy dữ liệu | Production Plan nổ vật tư theo BOM | `manufacturing/doctype/production_plan/production_plan.py:32` |
| BOM | Work Order | chỉ lấy dữ liệu | Work Order chạy theo một BOM | `manufacturing/doctype/work_order/work_order.py:171` |
| Chart of Accounts | General Ledger | chỉ lấy dữ liệu | Mỗi bút toán trỏ về một tài khoản trong hệ thống tài khoản | `accounts/doctype/gl_entry/gl_entry.json:85` |
| Cost Center | General Ledger | chỉ lấy dữ liệu | Mỗi bút toán trỏ về một cost center | `accounts/doctype/gl_entry/gl_entry.json:111` |
| Job Card | Quality Inspection | chỉ lấy dữ liệu | Quality Inspection tham chiếu Job Card | `stock/doctype/quality_inspection/quality_inspection.json:81` |
| Purchase Receipt | Quality Inspection | chỉ lấy dữ liệu | Quality Inspection tham chiếu Purchase Receipt | `stock/doctype/quality_inspection/quality_inspection.json:81` |
| Supplier | Request for Quotation | chỉ lấy dữ liệu | RFQ chọn nhà cung cấp vào bảng con, không sinh chứng từ | `buying/doctype/request_for_quotation/request_for_quotation.py:647` |
| Customer | Quotation | tạo chứng từ tiếp theo | Customer > Create > Quotation | `selling/doctype/customer/customer.py:461` |
| Delivery Note | Sales Invoice | tạo chứng từ tiếp theo | Delivery Note > Create > Sales Invoice | `stock/doctype/delivery_note/delivery_note.py:899` |
| Lead | Opportunity | tạo chứng từ tiếp theo | Lead > Create > Opportunity | `crm/doctype/lead/lead.py:361` |
| Maintenance Schedule | Maintenance Visit | tạo chứng từ tiếp theo | Maintenance Schedule > Create > Maintenance Visit | `maintenance/doctype/maintenance_schedule/maintenance_schedule.py:477` |
| Material Request | Request for Quotation | tạo chứng từ tiếp theo | Material Request > Create > RFQ | `stock/doctype/material_request/material_request.py:755` |
| Material Request | Purchase Order | tạo chứng từ tiếp theo | Material Request > Create > Purchase Order | `stock/doctype/material_request/material_request.py:613` |
| Opportunity | Customer | tạo chứng từ tiếp theo | Opportunity > Create > Customer | `crm/doctype/opportunity/opportunity.py:478` |
| Production Plan | Work Order | tạo chứng từ tiếp theo | Production Plan > Create > Work Order | `manufacturing/doctype/production_plan/production_plan.py:930` |
| Production Plan | Material Request | tạo chứng từ tiếp theo | Production Plan > Create > Material Request (nguyên liệu thiếu) | `manufacturing/doctype/production_plan/production_plan.py:988` |
| Project | Task | tạo chứng từ tiếp theo | Task nằm trong Project | `projects/doctype/task/task.py:34` |
| Purchase Invoice | Payment Entry | tạo chứng từ tiếp theo | Purchase Invoice > Create > Payment Entry | `accounts/doctype/payment_entry/payment_entry.py:2885` |
| Purchase Order | Purchase Receipt | tạo chứng từ tiếp theo | Purchase Order > Create > Purchase Receipt | `buying/doctype/purchase_order/purchase_order.py:790` |
| Purchase Order | Subcontracting Order | tạo chứng từ tiếp theo | PO gia công (is_subcontracted) > Create > Subcontracting Order | `buying/doctype/purchase_order/purchase_order.py:1041` |
| Purchase Receipt | Purchase Invoice | tạo chứng từ tiếp theo | Purchase Receipt > Create > Purchase Invoice | `stock/doctype/purchase_receipt/purchase_receipt.py:1580` |
| Purchase Receipt | Asset | tạo chứng từ tiếp theo | Dòng hàng is_fixed_asset trên PR/PI tự tạo Asset | `controllers/buying_controller.py:1139` |
| Quotation | Sales Order | tạo chứng từ tiếp theo | Quotation > Create > Sales Order | `selling/doctype/quotation/quotation.py:474` |
| Request for Quotation | Supplier Quotation | tạo chứng từ tiếp theo | RFQ > Create > Supplier Quotation | `buying/doctype/request_for_quotation/request_for_quotation.py:464` |
| Sales Invoice | Payment Entry | tạo chứng từ tiếp theo | Sales Invoice > Create > Payment Entry | `accounts/doctype/payment_entry/payment_entry.py:2885` |
| Sales Order | Delivery Note | tạo chứng từ tiếp theo | Sales Order > Create > Delivery Note | `selling/doctype/sales_order/sales_order.py:1172` |
| Sales Order | Sales Invoice | tạo chứng từ tiếp theo | Sales Order > Create > Sales Invoice | `selling/doctype/sales_order/sales_order.py:1478` |
| Sales Order | Material Request | tạo chứng từ tiếp theo | Sales Order > Create > Material Request (hàng thiếu) | `selling/doctype/sales_order/sales_order.py:1092` |
| Sales Order | Project | tạo chứng từ tiếp theo | Sales Order > Create > Project | `selling/doctype/sales_order/sales_order.py:1134` |
| Sales Order | Maintenance Schedule | tạo chứng từ tiếp theo | Sales Order > Create > Maintenance Schedule | `selling/doctype/sales_order/sales_order.py:1541` |
| Subcontracting Order | Subcontracting Receipt | tạo chứng từ tiếp theo | Subcontracting Order > Create > Subcontracting Receipt | `subcontracting/doctype/subcontracting_order/subcontracting_order.py:458` |
| Subcontracting Receipt | Purchase Receipt | tạo chứng từ tiếp theo | Nhận hàng gia công xong sinh Purchase Receipt để ghi công nợ | `subcontracting/doctype/subcontracting_receipt/subcontracting_receipt.py:992` |
| Supplier Quotation | Purchase Order | tạo chứng từ tiếp theo | Supplier Quotation > Create > Purchase Order | `buying/doctype/supplier_quotation/supplier_quotation.py:267` |
| Task | Timesheet | tạo chứng từ tiếp theo | Task > Create > Timesheet | `projects/doctype/task/task.py:405` |
| Timesheet | Sales Invoice | tạo chứng từ tiếp theo | Timesheet > Create > Sales Invoice (giờ tính tiền) | `projects/doctype/timesheet/timesheet.py:412` |
| Warranty Claim | Maintenance Visit | tạo chứng từ tiếp theo | Warranty Claim > Create > Maintenance Visit | `support/doctype/warranty_claim/warranty_claim.py:100` |
| Work Order | Job Card | tạo chứng từ tiếp theo | Work Order tạo Job Card cho từng công đoạn | `manufacturing/doctype/work_order/work_order.py:2935` |
| Work Order | Stock Entry | tạo chứng từ tiếp theo | Work Order > Start/Finish > Stock Entry (xuất NVL, nhập thành phẩm) | `manufacturing/doctype/work_order/work_order.py:2675` |
| Assets (cả khung) | Accounts (cả khung) | ghi vào sổ cái | Khấu hao định kỳ sinh bút toán | `assets/doctype/asset/depreciation.py:57` |
| Journal Entry | General Ledger | ghi vào sổ cái | Journal Entry submit thì ghi sổ cái | `accounts/doctype/journal_entry/journal_entry.py:208` |
| Payment Entry | General Ledger | ghi vào sổ cái | Payment Entry submit thì ghi sổ cái | `accounts/doctype/payment_entry/payment_entry.py:35` |
| Purchase Invoice | General Ledger | ghi vào sổ cái | Purchase Invoice submit thì ghi sổ cái | `accounts/doctype/purchase_invoice/purchase_invoice.py:30` |
| Sales Invoice | General Ledger | ghi vào sổ cái | Sales Invoice submit thì ghi sổ cái | `accounts/doctype/sales_invoice/sales_invoice.py:510` |
| Stock (cả khung) | Accounts (cả khung) | ghi vào sổ cái | Mọi phiếu kho có giá trị đều ghi bút toán giá vốn / tồn kho | `controllers/stock_controller.py:320` |

## Hai chỗ cố ý đặt khác module thật

- **Customer** thuộc module Selling, nhưng vẽ trong khung CRM cho liền mạch Lead → Opportunity → Customer.
- **Quality Inspection** thuộc module Stock, nhưng tách ra khung Quality vì nó phục vụ cả mua hàng lẫn sản xuất.

## Có trong v16 nhưng cố ý không vẽ

Sơ đồ dành cho người quản lý nhìn tổng thể, nên các nhánh phụ sau bị lược bỏ:

- Sales Order → Pick List → Delivery Note — `selling/doctype/sales_order/sales_order.py::create_pick_list`
- Sales Order → Purchase Order (drop ship) — `selling/doctype/sales_order/sales_order.py::make_purchase_order`
- Sales Order → Subcontracting Inward Order (gia công nhận ngoài, mới ở v16) — `selling/doctype/sales_order/sales_order.py::get_mapped_subcontracting_inward_order`
- Material Request → Stock Entry / Supplier Quotation — `stock/doctype/material_request/material_request.py::make_stock_entry`
- Job Card → Stock Entry / Material Request — `manufacturing/doctype/job_card/job_card.py::make_stock_entry`
- Work Order → Pick List — `manufacturing/doctype/work_order/work_order.py::create_pick_list`
- Delivery Note → Packing Slip / Shipment / Installation Note — `stock/doctype/delivery_note/delivery_note.py::make_shipment`
- Chiều ngược: Sales Invoice → Delivery Note, Purchase Invoice → Purchase Receipt — `accounts/doctype/sales_invoice/sales_invoice.py::make_delivery_note`
- Prospect / Opportunity → RFQ, Supplier Quotation — `crm/doctype/opportunity/opportunity.py::make_request_for_quotation`
- Sales Forecast → Master Production Schedule — `manufacturing/doctype/sales_forecast/sales_forecast.py::create_mps`
- Toàn bộ nhân sự (app hrms) — người dùng yêu cầu bỏ khỏi sơ đồ — `apps/hrms`
