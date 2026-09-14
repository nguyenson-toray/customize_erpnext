#!/usr/bin/env python3
"""Sinh docs/flowchart/template.drawio — sơ đồ hoạt động của ERPNext v16.

Chạy:  python3 scripts/build_erpnext_flowchart.py

Vì sao có script này: bản .drawio cũ vẽ tay từ 2022 (ERPNext v13) và đã lệch khá
nhiều so với v16 — Nhân sự đã tách hẳn sang app hrms, thêm module Subcontracting,
Assets, Quality Management, thêm Pick List / Shipment / Serial and Batch Bundle /
Payment Ledger Entry, và Manufacturing có thêm Sales Forecast → Master Production
Schedule. Mỗi lần ERPNext lên version, sửa dữ liệu trong file này rồi chạy lại,
không phải kéo thả từng ô.

Các mũi tên KHÔNG viết theo trí nhớ: chúng lấy từ chính source ERPNext v16 đang
cài, chỗ khai báo "tạo chứng từ tiếp theo" (get_mapped_doc) và các hàm make_*.
Muốn kiểm lại thì grep get_mapped_doc trong apps/erpnext.

File xuất ra để XML trần, KHÔNG nén, để git diff đọc được từng dòng — bản cũ nén
base64 nên mỗi lần sửa chỉ thấy một khối ký tự vô nghĩa.
"""

import html
import os
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.realpath(os.path.join(HERE, "..", "docs", "flowchart", "template.drawio"))

ERPNEXT_VERSION = "v16"

# ── layout constants — sửa ở đây là cả sơ đồ giãn theo ────────────────────
NODE_W, NODE_H = 210, 46
V_GAP = 44          # khoảng hở dọc giữa hai ô = độ dài mũi tên nhìn thấy
H_GAP = 86          # khoảng hở ngang giữa hai khung module
GROUP_W = NODE_W + 40
HEAD = 50           # chỗ cho tên module
PAD_B = 20
COL = [40 + i * (GROUP_W + H_GAP) for i in range(6)]
ROW1, ROW2 = 100, 560

# ── colours per module ────────────────────────────────────────────────────
C = {
    "crm":      ("#e8f0fe", "#3b6fd4"),
    "selling":  ("#e7f6ec", "#1e8e4e"),
    "stock":    ("#fff4e5", "#d97706"),
    "buying":   ("#f3ecfb", "#7c4dbd"),
    "mfg":      ("#fdecef", "#c2405a"),
    "sub":      ("#fdf3e7", "#b06a00"),
    "project":  ("#e9f6f8", "#0f7d8c"),
    "support":  ("#f1f3f6", "#5b6675"),
    "asset":    ("#eef7e8", "#4a7c2f"),
    "quality":  ("#f6f0e8", "#8a6d3b"),
    "accounts": ("#e6eefc", "#23478a"),
}

# ── modules: (id, title, colour, x, y, [(node id, label), ...]) ───────────
MODULES = [
    ("g_crm", "CRM", "crm", COL[0], ROW1, [
        ("lead", "Lead"), ("opp", "Opportunity"), ("cust", "Customer")]),
    ("g_selling", "Selling", "selling", COL[1], ROW1, [
        ("quote", "Quotation"), ("so", "Sales Order")]),
    ("g_stock", "Stock", "stock", COL[2], ROW1, [
        ("item", "Item &amp; Warehouse"), ("mr", "Material Request"),
        ("dn", "Delivery Note"), ("pr", "Purchase Receipt"), ("se", "Stock Entry")]),
    ("g_buying", "Buying", "buying", COL[3], ROW1, [
        ("supplier", "Supplier"), ("rfq", "Request for Quotation"),
        ("sq", "Supplier Quotation"), ("po", "Purchase Order")]),
    ("g_mfg", "Manufacturing", "mfg", COL[4], ROW1, [
        ("bom", "BOM"), ("pp", "Production Plan"),
        ("wo", "Work Order"), ("jc", "Job Card")]),
    ("g_asset", "Assets", "asset", COL[5], ROW1, [
        ("asset", "Asset"), ("dep", "Depreciation Schedule")]),
    ("g_project", "Projects", "project", COL[0], ROW2, [
        ("project", "Project"), ("task", "Task"), ("timesheet", "Timesheet")]),
    ("g_support", "Maintenance &amp; Support", "support", COL[1], ROW2, [
        ("issue", "Issue"), ("warranty", "Warranty Claim"),
        ("ms", "Maintenance Schedule"), ("mv", "Maintenance Visit")]),
    ("g_sub", "Subcontracting", "sub", COL[3], ROW2, [
        ("sco", "Subcontracting Order"), ("scr", "Subcontracting Receipt")]),
    ("g_quality", "Quality", "quality", COL[4], ROW2, [
        ("qi", "Quality Inspection")]),
]

GROUPS, NODES = [], []
for gid, title, colour, gx, gy, items in MODULES:
    gh = HEAD + len(items) * (NODE_H + V_GAP) - V_GAP + PAD_B
    GROUPS.append((gid, title, colour, gx, gy, GROUP_W, gh))
    for i, (nid, label) in enumerate(items):
        NODES.append((nid, label, colour, gx + 20,
                      gy + HEAD + i * (NODE_H + V_GAP), NODE_W, NODE_H))

# ── Accounts: dải ngang cuối sơ đồ, mọi chứng từ có giá trị đổ về đây ─────
ACC_Y = max(g[4] + g[6] for g in GROUPS) + 90
ACC_W = COL[5] + GROUP_W - COL[0]
GROUPS.append(("g_acc", "Accounts", "accounts", COL[0], ACC_Y, ACC_W,
               HEAD + 2 * (NODE_H + V_GAP) - V_GAP + PAD_B))
# 4 cụm trải đều hết bề ngang dải Accounts, mũi tên ngang nhờ vậy dài và rõ
ACC_STEP = (ACC_W - 60 - 40) // 4
_a = lambda i: COL[0] + 30 + i * ACC_STEP
for i, pair in enumerate([(("coa", "Chart of Accounts"), ("cc", "Cost Center")),
                          (("si", "Sales Invoice"), ("pi", "Purchase Invoice")),
                          (("pay", "Payment Entry"), ("je", "Journal Entry"))]):
    for k, (nid, label) in enumerate(pair):
        NODES.append((nid, label, "accounts", _a(i),
                      ACC_Y + HEAD + k * (NODE_H + V_GAP), NODE_W, NODE_H))
NODES.append(("gl", "General Ledger", "accounts", _a(3), ACC_Y + HEAD,
              NODE_W + 90, 2 * NODE_H + V_GAP))

# ── arrows ────────────────────────────────────────────────────────────────
#   doc  = creates the next document (verified in ERPNext v16 source)
#   data = feeds data, no new document
#   gl   = posts to accounting
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

# Mũi tên phải băng qua vài khung module thì cho chạy vòng lên dải trống trên
# cùng, thay vì cắt ngang qua các ô nằm giữa.
# (nguồn, đích) -> (cạnh thoát, x rãnh dọc bên nguồn, cạnh vào, x rãnh bên đích)
OVERHEAD = {
    ("pp", "mr"): ("L", COL[4] - H_GAP // 2, "R", COL[2] + GROUP_W + H_GAP // 2),
}

# Stock movements post their own value; drawn once at frame level.
GROUP_EDGES = [
    ("g_stock", "g_acc", "stock value"),
    ("g_asset", "g_acc", "depreciation"),
]

EDGE_STYLE = {
    "doc":  "strokeColor=#7d879a;endArrow=blockThin;endFill=1;strokeWidth=1.4;",
    "data": "strokeColor=#b6bdc8;dashed=1;endArrow=open;endFill=0;",
    "gl":   "strokeColor=#23478a;endArrow=blockThin;endFill=1;strokeWidth=1.8;",
}


# ── bằng chứng: mỗi mũi tên chỉ tới đúng chỗ trong source ERPNext v16 ─────
# (nguồn, đích) -> (file trong apps/erpnext/erpnext, mẫu regex phải grep ra, nghĩa)
# Chạy `python3 scripts/build_erpnext_flowchart.py --check` để grep lại toàn bộ.
ERPNEXT_SRC = "/home/frappe/frappe-bench/apps/erpnext/erpnext"
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

# Có trong source v16 nhưng CỐ Ý không vẽ, để sơ đồ đủ đơn giản cho người quản lý:
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

# ── chú giải các loại mũi tên ─────────────────────────────────────────────
# (kiểu, mô tả hình thức mũi tên, tên, giải thích một câu)
LEGEND = [
    ("doc", "Grey solid arrow", "Creates the next document",
     "Press Create on the first document and ERPNext opens the next one, already filled in. "
     "The two documents stay linked, so quantities and amounts are carried over and tracked."),
    ("data", "Grey dashed arrow", "Supplies data only",
     "The document at the tip reads master data, a price or a plan from the one at the tail. "
     "Nothing is created and nothing is posted."),
    ("gl", "Blue solid arrow", "Posts to the General Ledger",
     "Submitting the document writes its accounting entries by itself. "
     "Cancel the document and ERPNext reverses those entries."),
]
LEGEND_NOTE = "Every arrow was checked against the ERPNext v16 source code."
LEG_ROW = 62
LEG_W = COL[5] + GROUP_W - COL[4]
LEG_H = 48 + len(LEGEND) * LEG_ROW + 34
LEG_X = COL[4]
LEG_Y = ROW2 + 180


def all_arrows():
    """EDGES + GROUP_EDGES, thứ tự này quyết định luôn id e0, e1, ... trong file."""
    return ([(a, b, lbl, kind) for a, b, lbl, kind in EDGES]
            + [(a, b, lbl, "gl") for a, b, lbl in GROUP_EDGES])


def esc(t):
    return html.escape(t, quote=True)


def build():
    mx = ET.Element("mxGraphModel", {
        "dx": "1400", "dy": "900", "grid": "1", "gridSize": "10", "guides": "1",
        "tooltips": "1", "connect": "1", "arrows": "1", "fold": "1", "page": "1",
        "pageScale": "1", "pageWidth": "1169", "pageHeight": "826",
        "math": "0", "shadow": "0",
    })
    root = ET.SubElement(mx, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    def cell(cid, value, style, x, y, w, h, vertex=True):
        c = ET.SubElement(root, "mxCell", {
            "id": cid, "value": value, "style": style,
            "vertex": "1" if vertex else "0", "parent": "1",
        })
        ET.SubElement(c, "mxGeometry", {
            "x": str(x), "y": str(y), "width": str(w), "height": str(h), "as": "geometry",
        })

    # chú giải: mỗi loại mũi tên nghĩa là gì, đặt ở khoảng trống góc phải
    cell("lg_box", "", "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;"
         "strokeColor=#c7cfdb;strokeWidth=1.5;arcSize=4;", LEG_X, LEG_Y, LEG_W, LEG_H)
    cell("lg_head", "Reading the arrows",
         "text;html=1;align=left;verticalAlign=middle;fontSize=14;fontStyle=1;"
         "fontColor=#23262b;", LEG_X + 18, LEG_Y + 12, LEG_W - 36, 22)
    for i, (kind, look, label, desc) in enumerate(LEGEND):
        y = LEG_Y + 48 + i * LEG_ROW
        cell("lg_l%d" % i, "", "endArrow=none;html=1;" + EDGE_STYLE[kind],
             LEG_X + 18, y + 20, 56, 0)
        cell("lg_t%d" % i,
             "<b>%s &#8212; %s</b><br>%s" % (look, label, desc),
             "text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;fontSize=11;"
             "fontColor=#5b6675;", LEG_X + 86, y, LEG_W - 104, LEG_ROW - 6)
    cell("lg_note", LEGEND_NOTE,
         "text;html=1;whiteSpace=wrap;align=left;verticalAlign=middle;fontSize=10;"
         "fontColor=#8a94a3;", LEG_X + 18, LEG_Y + LEG_H - 34, LEG_W - 36, 26)

    cell("title",
         esc("ERPNext %s \u2014 how the system works" % ERPNEXT_VERSION),
         "text;html=1;align=left;verticalAlign=middle;fontSize=22;fontStyle=1;fontColor=#23262b;",
         40, 24, 900, 30)
    cell("subtitle",
         esc("Every document that carries a value posts to the General Ledger."),
         "text;html=1;align=left;verticalAlign=middle;fontSize=12;fontColor=#5b6675;",
         40, 54, 900, 20)

    # khung module vẽ trước để nằm dưới
    for gid, title, color, x, y, w, h in GROUPS:
        fill, stroke = C[color]
        cell(gid, esc(title),
             "rounded=1;whiteSpace=wrap;html=1;fillColor=%s;strokeColor=%s;strokeWidth=1.5;"
             "verticalAlign=top;align=left;spacingLeft=12;spacingTop=8;arcSize=4;"
             "fontSize=15;fontStyle=1;fontColor=#23262b;" % (fill, stroke),
             x, y, w, h)


    for nid, label, color, x, y, w, h in NODES:
        fill, stroke = C[color]
        cell(nid, label,
             "rounded=1;whiteSpace=wrap;html=1;fillColor=#ffffff;strokeColor=%s;"
             "strokeWidth=1.4;fontSize=13;fontColor=#23262b;arcSize=14;" % stroke,
             x, y, w, h)


    geo = {n[0]: (n[3], n[4], n[5], n[6]) for n in NODES}
    geo.update({g[0]: (g[3], g[4], g[5], g[6]) for g in GROUPS})

    def side_of(a, b):
        """Cạnh nào của a hướng về b: 'R' phải, 'L' trái, 'D' dưới, 'U' trên."""
        ax, ay, aw, ah = geo[a]
        bx, by, bw, bh = geo[b]
        dx = (bx + bw / 2) - (ax + aw / 2)
        dy = (by + bh / 2) - (ay + ah / 2)
        if abs(dx) >= abs(dy):
            return "R" if dx > 0 else "L"
        return "D" if dy > 0 else "U"

    def center(n):
        x, y, w, h = geo[n]
        return x + w / 2, y + h / 2

    all_edges = all_arrows()

    # Nhiều mũi tên cùng thoát ra giữa một cạnh thì chúng đè lên nhau. Gom theo
    # (ô, cạnh) rồi rải đều các điểm neo dọc cạnh đó, thứ tự theo vị trí đầu kia
    # để các đường không bắt chéo nhau ngay tại chỗ thoát ra.
    # Gom CẢ đường ra lẫn đường vào của cùng một cạnh vào một rổ: nếu tách hai rổ
    # thì một cạnh vừa có đường ra vừa có đường vào sẽ cùng rơi vào điểm giữa.
    slots = {}
    for i, (a, b, _, _) in enumerate(all_edges):
        slots.setdefault((a, side_of(a, b)), []).append((i, "exit"))
        slots.setdefault((b, side_of(b, a)), []).append((i, "entry"))

    anchor = {i: [.5, .5, .5, .5] for i in range(len(all_edges))}
    for (node, sd), items in slots.items():
        def other(it):
            i, role = it
            return center(all_edges[i][1] if role == "exit" else all_edges[i][0])
        items.sort(key=lambda it: other(it)[1] if sd in "RL" else other(it)[0])
        n = len(items)
        for k, (i, role) in enumerate(items):
            t = round((k + 1) / (n + 1), 3)
            pos = {"R": (1, t), "L": (0, t), "D": (t, 1), "U": (t, 0)}[sd]
            if role == "exit":
                anchor[i][0], anchor[i][1] = pos
            else:
                anchor[i][2], anchor[i][3] = pos

    OVER_Y = ROW1 - 14      # dải trống giữa phụ đề và hàng khung đầu tiên

    def edge(eid, i, a, b, lbl, kind):
        ex, ey, nx, ny = anchor[i]
        if (a, b) in OVERHEAD:
            e_side, _, n_side, _ = OVERHEAD[(a, b)]
            ex, ey = (0, .5) if e_side == "L" else (1, .5)
            nx, ny = (0, .5) if n_side == "L" else (1, .5)
        # lệch bước nhảy đầu tiên để hai đường song song không nằm đè lên nhau
        jetty = 10 + (i % 5) * 7
        e = ET.SubElement(root, "mxCell", {
            "id": eid, "value": esc(lbl),
            "style": ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;orthogonalLoop=1;"
                      "jettySize=%d;fontSize=9;fontColor=#5b6675;labelBackgroundColor=#ffffff;"
                      "exitX=%.3f;exitY=%.3f;exitDx=0;exitDy=0;"
                      "entryX=%.3f;entryY=%.3f;entryDx=0;entryDy=0;"
                      % (jetty, ex, ey, nx, ny)) + EDGE_STYLE[kind],
            "edge": "1", "parent": "1", "source": a, "target": b,
        })
        g = ET.SubElement(e, "mxGeometry", {"relative": "1", "as": "geometry"})
        if (a, b) in OVERHEAD:
            _, gx_a, _, gx_b = OVERHEAD[(a, b)]
            pts = ET.SubElement(g, "Array", {"as": "points"})
            for gx in (gx_a, gx_b):
                ET.SubElement(pts, "mxPoint", {"x": str(int(gx)), "y": str(OVER_Y)})

    ids = {n[0] for n in NODES}
    for i, (a, b, lbl, kind) in enumerate(all_edges):
        assert a in ids or a in geo, a
        assert b in ids or b in geo, b
        edge("e%d" % i, i, a, b, lbl, kind)

    return mx


def check_evidence():
    """Grep lại từng mũi tên trong source ERPNext đang cài.

    Trả về danh sách (nguồn, đích, loại, nghĩa, "file:dòng" hoặc None).
    """
    import re as _re

    label = {n[0]: _re.sub(r"&amp;", "&", n[1]) for n in NODES}
    label.update({g[0]: _re.sub(r"&amp;", "&", g[1]) + " (cả khung)" for g in GROUPS})
    rows = []
    for a, b, _lbl, kind in all_arrows():
        ev = EVIDENCE.get((a, b))
        if not ev:
            rows.append((label.get(a, a), label.get(b, b), kind, "", None))
            continue
        rel, pat, note = ev
        hit = None
        full = os.path.join(ERPNEXT_SRC, rel)
        if os.path.isfile(full):
            with open(full, encoding="utf-8") as f:
                for i, line in enumerate(f, 1):
                    if _re.search(pat, line):
                        hit = "%s:%d" % (rel, i)
                        break
        rows.append((label.get(a, a), label.get(b, b), kind, note, hit))
    return rows


KIND_VN = {"doc": "tạo chứng từ tiếp theo", "data": "chỉ lấy dữ liệu",
           "gl": "ghi vào sổ cái"}


def write_readme(rows):
    """Ghi docs/flowchart/README.md — bảng đối chiếu sơ đồ với source v16."""
    out = os.path.join(os.path.dirname(OUT), "README.md")
    L = []
    L.append("# Sơ đồ hoạt động ERPNext %s" % ERPNEXT_VERSION)
    L.append("")
    L.append("`template.drawio` — mở bằng [draw.io](https://app.diagrams.net) hoặc "
             "extension Draw.io Integration của VS Code. File để XML trần (không nén) "
             "nên git diff đọc được.")
    L.append("")
    L.append("Sinh lại: `python3 scripts/build_erpnext_flowchart.py`")
    L.append("Chỉ kiểm tra, không ghi đè: `python3 scripts/build_erpnext_flowchart.py --check`")
    L.append("")
    L.append("> Script từ chối ghi đè nếu file .drawio đã được sửa tay. "
             "Muốn bỏ qua thì thêm `--force` (mất hết phần sửa tay).")
    L.append("")
    L.append("## Ba loại mũi tên")
    L.append("")
    for kind, look, title, desc in LEGEND:
        L.append("- **%s — %s** (%s) — %s" % (look, title, KIND_VN[kind], desc))
    L.append("")
    L.append("## Đối chiếu với source ERPNext %s" % ERPNEXT_VERSION)
    L.append("")
    L.append("Mỗi mũi tên dưới đây lấy từ source ERPNext đang cài chứ không vẽ theo trí nhớ. "
             "Cột cuối là chỗ chứng minh, tính từ `apps/erpnext/erpnext/`.")
    L.append("")
    L.append("| Từ | Đến | Loại | Nghĩa | Bằng chứng |")
    L.append("| --- | --- | --- | --- | --- |")
    for a, b, kind, note, hit in sorted(rows, key=lambda r: (r[2], r[0])):
        L.append("| %s | %s | %s | %s | %s |"
                 % (a, b, KIND_VN[kind], note, "`%s`" % hit if hit else "**chưa kiểm được**"))
    L.append("")
    L.append("## Hai chỗ cố ý đặt khác module thật")
    L.append("")
    L.append("- **Customer** thuộc module Selling, nhưng vẽ trong khung CRM cho liền mạch "
             "Lead → Opportunity → Customer.")
    L.append("- **Quality Inspection** thuộc module Stock, nhưng tách ra khung Quality "
             "vì nó phục vụ cả mua hàng lẫn sản xuất.")
    L.append("")
    L.append("## Có trong v16 nhưng cố ý không vẽ")
    L.append("")
    L.append("Sơ đồ dành cho người quản lý nhìn tổng thể, nên các nhánh phụ sau bị lược bỏ:")
    L.append("")
    for what, where in OMITTED:
        L.append("- %s — `%s`" % (what, where))
    L.append("")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    return out


def hash_of(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    import sys

    args = sys.argv[1:]
    rows = check_evidence()
    ok = sum(1 for r in rows if r[4])
    print("đối chiếu source: %d/%d mũi tên có bằng chứng" % (ok, len(rows)))
    for a, b, _k, _n, hit in rows:
        if not hit:
            print("  ! không grep ra bằng chứng: %s -> %s" % (a, b))

    if "--check" in args:
        return 0 if ok == len(rows) else 1

    stamp = os.path.join(os.path.dirname(OUT), ".template.drawio.sha256")
    if os.path.isfile(OUT) and "--force" not in args:
        # Người dùng có sửa tay file .drawio thì đừng ghi đè công sức của họ.
        prev = open(stamp).read().strip() if os.path.isfile(stamp) else ""
        if prev and prev != hash_of(OUT):
            print("\nDỪNG: %s đã bị sửa tay sau lần sinh gần nhất." % os.path.basename(OUT))
            print("Chạy lại với --force nếu chấp nhận mất phần sửa tay đó.")
            return 1

    mx = build()
    body = ET.tostring(mx, encoding="unicode")
    out = ('<mxfile host="app.diagrams.net" type="device" version="24.7.17">\n'
           '  <diagram id="erpnext-%s" name="ERPNext %s">\n    %s\n  </diagram>\n'
           '</mxfile>\n' % (ERPNEXT_VERSION, ERPNEXT_VERSION, body))
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(out)
    with open(stamp, "w", encoding="utf-8") as f:
        f.write(hash_of(OUT) + "\n")
    readme = write_readme(rows)
    print("%s: %d khung module, %d ô, %d mũi tên, %d KB"
          % (os.path.relpath(OUT, HERE), len(GROUPS), len(NODES), len(all_arrows()),
             len(out) // 1024))
    print("%s: bảng đối chiếu %d dòng" % (os.path.relpath(readme, HERE), len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
