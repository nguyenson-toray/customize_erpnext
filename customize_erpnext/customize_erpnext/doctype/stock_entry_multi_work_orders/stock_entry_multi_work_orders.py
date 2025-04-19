# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import flt, now, nowdate, nowtime
import json

class StockEntryMultiWorkOrders(Document):
    def onload(self):
        """Kiểm tra Stock Entry liên quan và cập nhật trạng thái"""
        if self.docstatus == 1:
            # Cập nhật trạng thái stock_transfer cho các Work Order
            self.update_work_order_status()
    
    def before_validate(self):
        """Trước khi validate, kiểm tra lại danh sách materials"""
        if self.work_orders:
            # Đảm bảo materials được tính toán đầy đủ
            self.refresh_material_list()
    
    def validate(self):
        """Validate thông tin nhập vào"""
        # Kiểm tra xem có Work Orders nào được chọn không
        if not self.work_orders:
            frappe.throw("Vui lòng chọn ít nhất một Work Order")
        
        # Kiểm tra các Work Order đã có Stock Entry chưa
        self.check_work_order_status()
        
        # Kiểm tra số lượng materials có đủ không
        self.check_materials_availability()
    
    def on_submit(self):
        """Khi submit, tạo các Stock Entry cho từng Work Order"""
        self.create_stock_entries()
    
    def on_cancel(self):
        """Khi cancel, hủy/cancel các Stock Entry đã tạo"""
        stock_entries = self.get_stock_entries()
        if stock_entries:
            cancelled_entries = []
            deleted_entries = []
            
            for se in stock_entries:
                try:
                    se_doc = frappe.get_doc("Stock Entry", se.name)
                    if se_doc.docstatus == 1:
                        se_doc.cancel()
                        cancelled_entries.append(se.name)
                    elif se_doc.docstatus == 0:
                        frappe.delete_doc("Stock Entry", se_doc.name)
                        deleted_entries.append(se.name)
                except Exception as e:
                    frappe.log_error(f"Error cancelling/deleting Stock Entry {se.name}: {str(e)}")
            
            message = ""
            if cancelled_entries:
                message += ("Đã hủy các Stock Entry: ") + ", ".join(cancelled_entries) + "<br>"
            if deleted_entries:
                message += ("Đã xóa các Stock Entry: ") + ", ".join(deleted_entries)
                
            if message:
                frappe.msgprint(message)
    
    def update_work_order_status(self):
        """Cập nhật trạng thái stock_transfer cho các Work Order"""
        for wo_row in self.work_orders:
            stock_entry = frappe.db.exists(
                "Stock Entry",
                {
                    "work_order": wo_row.work_order,
                    "stock_entry_type": "Material Transfer for Manufacture",
                    "docstatus": 1
                }
            )
            
            # Cập nhật trạng thái - thống nhất với yêu cầu
            wo_row.stock_transfer_status = "Completed" if stock_entry else "Not yet Transfer"
            frappe.db.set_value("Stock Entry Multi Work Orders Table WO", 
                               wo_row.name, "stock_transfer_status", wo_row.stock_transfer_status)
    
    def refresh_material_list(self):
        """Tính toán lại danh sách materials từ các Work Order đã chọn"""
        work_orders = [row.work_order for row in self.work_orders if row.work_order]
        
        # Lấy danh sách materials hiện tại để giữ lại qty đã được chỉnh sửa
        current_materials = {}
        if self.materials:
            for row in self.materials:
                current_materials[row.item_code] = flt(row.required_qty)
        
        # Xóa danh sách materials hiện tại
        self.materials = []
        
        if not work_orders:
            return
            
        # Lấy danh sách materials mới từ server
        all_materials = get_materials_for_work_orders(work_orders)
        
        # Gộp các items giống nhau
        grouped_materials = {}
        for material in all_materials:
            item_code = material.item_code
            if item_code not in grouped_materials:
                grouped_materials[item_code] = material
            else:
                grouped_materials[item_code].required_qty += flt(material.required_qty)
        
        # Thêm materials vào table
        for material in grouped_materials.values():
            # Ưu tiên giữ lại giá trị đã điều chỉnh nếu có và lớn hơn giá trị tính toán
            qty_to_use = max(current_materials.get(material.item_code, 0), flt(material.required_qty))
            
            row = self.append("materials", {
                "item_code": material.item_code,
                "item_name": material.item_name,
                "item_name_detail": material.item_name_detail,
                "required_qty": qty_to_use,
                "qty_available_in_source_warehouse": material.qty_available,
                "wip_warehouse": material.wip_warehouse,
                "source_warehouse": material.source_warehouse
            })
    
    def check_work_order_status(self):
        """Kiểm tra các Work Order đã có Stock Entry chưa"""
        for wo_row in self.work_orders:
            stock_entry = frappe.db.exists(
                "Stock Entry",
                {
                    "work_order": wo_row.work_order,
                    "stock_entry_type": "Material Transfer for Manufacture",
                    "docstatus": 1
                }
            )
            
            if stock_entry:
                wo_row.stock_transfer_status = "Completed"
                frappe.msgprint(f"Work Order {wo_row.work_order} đã có Stock Entry {stock_entry}")
    
    def check_materials_availability(self):
        """Kiểm tra số lượng materials có đủ không"""
        insufficient_items = []
        
        for material in self.materials:
            if flt(material.qty_available_in_source_warehouse) < flt(material.required_qty):
                insufficient_items.append(f"{material.item_code} - {material.item_name} (Cần: {material.required_qty}, Còn: {material.qty_available_in_source_warehouse})")
        
        if insufficient_items:
            warning_msg = "Các nguyên liệu sau không đủ số lượng:<br>"
            warning_msg += "<br>".join(insufficient_items)
            frappe.msgprint(warning_msg, title="Cảnh báo", indicator="orange")
    
    def create_stock_entries(self):
        """Tạo các Stock Entry cho từng Work Order"""
        created_entries = []
        
        # Bước 1: So sánh tổng hợp items từ materials với tổng hợp từ Work Orders
        wo_materials = get_consolidated_materials_from_work_orders([row.work_order for row in self.work_orders])
        adjusted_materials = {}
        
        # Tạo dictionary từ bảng materials
        for row in self.materials:
            adjusted_materials[row.item_code] = {
                "required_qty": flt(row.required_qty),
                "source_warehouse": row.source_warehouse,
                "wip_warehouse": row.wip_warehouse
            }
        
        # Tìm các items được điều chỉnh (qty lớn hơn)
        adjustments = {}
        for item_code, details in adjusted_materials.items():
            if item_code in wo_materials:
                original_qty = wo_materials[item_code]["required_qty"]
                if details["required_qty"] > original_qty:
                    adjustments[item_code] = {
                        "additional_qty": details["required_qty"] - original_qty,
                        "source_warehouse": details["source_warehouse"],
                        "wip_warehouse": details["wip_warehouse"]
                    }
        
        # Bước 2: Tạo Stock Entry cho từng Work Order
        for wo_row in self.work_orders:
            try:
                # Lấy thông tin Work Order
                work_order = frappe.get_doc("Work Order", wo_row.work_order)
                
                # Tạo Stock Entry mới
                stock_entry = frappe.new_doc("Stock Entry")
                stock_entry.stock_entry_type = "Material Transfer for Manufacture"
                stock_entry.purpose = "Material Transfer for Manufacture"
                stock_entry.work_order = wo_row.work_order
                stock_entry.from_bom = 1
                stock_entry.posting_date = self.posting_date
                stock_entry.posting_time = self.posting_time
                stock_entry.company = work_order.company
                stock_entry.to_warehouse = work_order.wip_warehouse
                
                # Thêm link đến Stock Entry Multi Work Orders
                stock_entry.custom_stock_entry_multi_work_orders = self.name
                
                # Thêm các nguyên liệu từ Work Order BOM
                wo_materials = get_materials_for_single_work_order(wo_row.work_order)
                
                for material in wo_materials:
                    s_warehouse = material.source_warehouse
                    
                    # Nếu không có source_warehouse, báo lỗi
                    if not s_warehouse:
                        frappe.throw(f"Không tìm thấy Source Warehouse cho item {material.item_code} trong Work Order {wo_row.work_order}")
                    
                    stock_entry.append("items", {
                        "s_warehouse": s_warehouse,
                        "t_warehouse": work_order.wip_warehouse,
                        "item_code": material.item_code,
                        "qty": material.required_qty,
                        "basic_rate": get_item_rate(material.item_code),
                        "uom": frappe.db.get_value("Item", material.item_code, "stock_uom")
                    })
                
                # Lưu Stock Entry 
                stock_entry.insert()
                created_entries.append(stock_entry.name)
                
            except Exception as e:
                frappe.log_error(f"Error creating Stock Entry for Work Order {wo_row.work_order}: {str(e)}")
                frappe.throw(f"Lỗi khi tạo Stock Entry cho Work Order {wo_row.work_order}: {str(e)}")
        
        # Bước 3: Xử lý các items được điều chỉnh
        if adjustments and created_entries:
            # Lấy Stock Entry cuối cùng để thêm items
            last_se = frappe.get_doc("Stock Entry", created_entries[-1])
            
            for item_code, details in adjustments.items():
                # Kiểm tra xem item đã có trong Stock Entry chưa
                item_exists = False
                for item in last_se.items:
                    if item.item_code == item_code:
                        # Cập nhật số lượng
                        item.qty += details["additional_qty"]
                        item_exists = True
                        break
                
                # Nếu item chưa có, thêm mới
                if not item_exists:
                    last_se.append("items", {
                        "s_warehouse": details["source_warehouse"],
                        "t_warehouse": details["wip_warehouse"],
                        "item_code": item_code,
                        "qty": details["additional_qty"],
                        "basic_rate": get_item_rate(item_code),
                        "uom": frappe.db.get_value("Item", item_code, "stock_uom")
                    })
            
            # Lưu Stock Entry
            last_se.save()
         
        # Hiển thị thông báo cho user
        if created_entries:
            message="Đã tạo các Stock Entry (Draft):" 
            message +=  ", ".join(created_entries) + "<br>" 
            frappe.msgprint(
                msg=message,
                title='Stock Entries Created' )
            # Cập nhật trạng thái work_order
            self.update_work_order_status()

    # Cập nhật hàm create_individual_stock_entries
    @frappe.whitelist()
    def create_individual_stock_entries(doc_name, work_orders):
        """Tạo Stock Entry riêng lẻ cho từng Work Order"""
        if isinstance(work_orders, str):
            try:
                import json
                work_orders = json.loads(work_orders)
            except Exception as e:
                frappe.log_error(f"Error parsing work_orders JSON: {str(e)}")
                frappe.throw(f"Lỗi khi xử lý danh sách Work Order: {str(e)}")
                return []

        # Get document
        doc = frappe.get_doc("Stock Entry Multi Work Orders", doc_name)
        
        # Get adjusted quantities from materials table
        adjusted_quantities = {}
        for row in doc.materials:
            adjusted_quantities[row.item_code] = flt(row.required_qty)
        
        # Theo dõi tổng số lượng của mỗi item trong tất cả Work Order
        total_wo_quantities = {}
        
        # Danh sách các Stock Entries được tạo
        created_entries = []
        
        # Bước 1: Tạo các Stock Entry cơ bản cho từng Work Order
        for wo_name in work_orders:
            try:
                # Lấy thông tin Work Order
                work_order = frappe.get_doc("Work Order", wo_name)
                
                # Tạo Stock Entry mới
                stock_entry = frappe.new_doc("Stock Entry")
                stock_entry.stock_entry_type = "Material Transfer for Manufacture"
                stock_entry.purpose = "Material Transfer for Manufacture"
                stock_entry.work_order = wo_name
                stock_entry.from_bom = 1
                stock_entry.posting_date = doc.posting_date
                stock_entry.posting_time = doc.posting_time
                stock_entry.company = work_order.company
                stock_entry.to_warehouse = work_order.wip_warehouse
                
                # Thêm link đến Stock Entry Multi Work Orders
                stock_entry.custom_stock_entry_multi_work_orders = doc_name
                
                # Lấy materials cho Work Order này
                wo_materials = get_materials_for_single_work_order(wo_name)
                
                # Cập nhật tổng số lượng cho từng item
                for material in wo_materials:
                    item_code = material.item_code
                    if item_code not in total_wo_quantities:
                        total_wo_quantities[item_code] = flt(material.required_qty)
                    else:
                        total_wo_quantities[item_code] += flt(material.required_qty)
                
                # Thêm các nguyên liệu vào Stock Entry
                for material in wo_materials:
                    s_warehouse = material.source_warehouse
                    
                    # Nếu không có source_warehouse, báo lỗi
                    if not s_warehouse:
                        frappe.throw(f"Không tìm thấy Source Warehouse cho item {material.item_code} trong Work Order {wo_name}")
                    
                    stock_entry.append("items", {
                        "s_warehouse": s_warehouse,
                        "t_warehouse": work_order.wip_warehouse,
                        "item_code": material.item_code,
                        "qty": material.required_qty,
                        "basic_rate": get_item_rate(material.item_code),
                        "uom": frappe.db.get_value("Item", material.item_code, "stock_uom")
                    })
                
                # Lưu Stock Entry
                stock_entry.insert()
                created_entries.append(stock_entry.name)
                
            except Exception as e:
                frappe.log_error(f"Error creating Stock Entry for Work Order {wo_name}: {str(e)}")
                frappe.throw(f"Lỗi khi tạo Stock Entry cho Work Order {wo_name}: {str(e)}")
        
        # Bước 2: Xử lý các điều chỉnh số lượng
        # Tìm các item có số lượng điều chỉnh lớn hơn tổng từ Work Order
        items_needing_adjustment = {}
        for item_code, adj_qty in adjusted_quantities.items():
            wo_qty = total_wo_quantities.get(item_code, 0)
            if adj_qty > wo_qty:
                # Lấy source_warehouse và wip_warehouse từ bảng materials
                source_warehouse = None
                wip_warehouse = None
                for row in doc.materials:
                    if row.item_code == item_code:
                        source_warehouse = row.source_warehouse
                        wip_warehouse = row.wip_warehouse
                        break
                        
                if source_warehouse and wip_warehouse:
                    items_needing_adjustment[item_code] = {
                        "additional_qty": adj_qty - wo_qty,
                        "source_warehouse": source_warehouse,
                        "wip_warehouse": wip_warehouse
                    }
        
        # Nếu có items cần điều chỉnh và đã tạo ít nhất một Stock Entry
        if items_needing_adjustment and created_entries:
            try:
                # Lấy Stock Entry cuối cùng
                last_se = frappe.get_doc("Stock Entry", created_entries[-1])
                
                for item_code, detail in items_needing_adjustment.items():
                    # Kiểm tra xem item đã có trong Stock Entry chưa
                    item_exists = False
                    for item in last_se.items:
                        if item.item_code == item_code:
                            # Cập nhật số lượng
                            item.qty += detail["additional_qty"]
                            item_exists = True
                            break
                    
                    # Nếu item chưa có, thêm mới
                    if not item_exists:
                        last_se.append("items", {
                            "s_warehouse": detail["source_warehouse"],
                            "t_warehouse": detail["wip_warehouse"],
                            "item_code": item_code,
                            "qty": detail["additional_qty"],
                            "basic_rate": get_item_rate(item_code),
                            "uom": frappe.db.get_value("Item", item_code, "stock_uom")
                        })
                
                # Lưu Stock Entry
                last_se.save()
                
                frappe.msgprint(f"Đã cập nhật số lượng điều chỉnh cho {len(items_needing_adjustment)} nguyên liệu trong Stock Entry {last_se.name}")
                
            except Exception as e:
                frappe.log_error(f"Error adjusting quantities in Stock Entry: {str(e)}")
                frappe.msgprint(f"Đã tạo các Stock Entry cơ bản nhưng gặp lỗi khi áp dụng số lượng đã điều chỉnh: {str(e)}")
        
        return created_entries
    def get_stock_entries(self):
        """Lấy danh sách Stock Entry đã tạo từ document này"""
        # Lấy tất cả Stock Entry liên kết với document này qua custom field
        stock_entries = frappe.get_all(
            "Stock Entry",
            filters={
                "custom_stock_entry_multi_work_orders": self.name,
                "stock_entry_type": "Material Transfer for Manufacture"
            },
            fields=["name", "docstatus"]
        )
        
        # Nếu không tìm thấy qua custom field, thử tìm theo work_orders (cách cũ)
        if not stock_entries:
            work_orders = [row.work_order for row in self.work_orders if row.work_order]
            if work_orders:
                stock_entries = frappe.get_all(
                    "Stock Entry",
                    filters={
                        "work_order": ["in", work_orders],
                        "stock_entry_type": "Material Transfer for Manufacture"
                    },
                    fields=["name", "docstatus"]
                )
        
        return stock_entries

# Get color options for the selected item template
@frappe.whitelist()
def get_colors_for_template(item_template):
    colors = frappe.db.sql("""
        SELECT DISTINCT attribute_value 
        FROM `tabItem Variant Attribute` 
        WHERE attribute = 'Color' 
        AND parent IN (
            SELECT name 
            FROM `tabItem` 
            WHERE variant_of = %s
        )
    """, item_template, as_list=1)
    
    return [color[0] for color in colors] if colors else []

# Get related work orders based on selected item template and color
@frappe.whitelist()
def get_related_work_orders(item_template, color):
    work_orders = frappe.db.sql("""
        SELECT 
            wo.name as work_order, 
            wo.production_item as item_code,
            wo.status as work_order_status,
            item.item_name as item_name,
            item.description as item_name_detail,
            wo.qty as qty_to_manufacture,
            CASE 
                WHEN EXISTS (
                    SELECT 1 FROM `tabStock Entry` se 
                    WHERE se.work_order = wo.name 
                    AND se.stock_entry_type = 'Material Transfer for Manufacture'
                    AND se.docstatus = 1
                ) THEN 'Completed'
                ELSE 'Not yet Transfer'
            END as stock_transfer_status
        FROM `tabWork Order` wo
        INNER JOIN `tabItem` item ON wo.production_item = item.name
        INNER JOIN `tabItem Variant Attribute` attr ON item.name = attr.parent
        WHERE item.variant_of = %s
        AND attr.attribute = 'Color'
        AND attr.attribute_value = %s
         
        ORDER BY wo.creation DESC
    """, (item_template, color), as_dict=1) 
    
    # Get materials for all found work orders
    all_materials = []
    for wo in work_orders:
        # Get materials from Work Order BOM
        materials = frappe.db.sql("""
            SELECT 
                item.item_code as item_code,
                item.item_name as item_name,
                item.description as item_name_detail,
                bom_item.qty_consumed_per_unit * wo.qty as required_qty,
                bin.actual_qty as qty_available,
                wo.wip_warehouse as wip_warehouse,
                COALESCE(bom_item.source_warehouse, 
                        item_default.default_warehouse, 
                        wo.source_warehouse) as source_warehouse
            FROM `tabWork Order` wo
            JOIN `tabBOM` bom ON wo.bom_no = bom.name
            JOIN `tabBOM Item` bom_item ON bom.name = bom_item.parent
            JOIN `tabItem` item ON bom_item.item_code = item.name
            LEFT JOIN `tabItem Default` item_default ON item.name = item_default.parent AND item_default.company = wo.company
            LEFT JOIN `tabBin` bin ON (
                bin.item_code = item.name 
                AND bin.warehouse = COALESCE(bom_item.source_warehouse, item_default.default_warehouse, wo.source_warehouse)
            )
            WHERE wo.name = %s
        """, wo.work_order, as_dict=1)
        
        all_materials.extend(materials)
    
    return {'work_orders': work_orders, 'materials': all_materials}

# Get materials for changed work orders
@frappe.whitelist()
def get_materials_for_work_orders(work_orders):
    # Handle string input (single work order)
    if isinstance(work_orders, str):
        # Check if it's a JSON string
        if work_orders.startswith('[') and work_orders.endswith(']'):
            try:
                import json
                work_orders = json.loads(work_orders)
            except Exception as e:
                frappe.log_error(f"Error parsing JSON: {str(e)}")
                return []
        else:
            work_orders = [work_orders]
    
    # Kiểm tra nếu work_orders rỗng
    if not work_orders:
        return []
    
    all_materials = []
    for work_order in work_orders:
        # Kiểm tra nếu work_order là chuỗi rỗng
        if not work_order or not isinstance(work_order, str) or not work_order.strip():
            continue
        
        # Get materials from Work Order BOM
        try:
            materials = get_materials_for_single_work_order(work_order)
            all_materials.extend(materials)
        except Exception as e:
            frappe.log_error(f"Error querying materials for {work_order}: {str(e)}")
    
    return all_materials

def get_materials_for_single_work_order(work_order):
    """Lấy danh sách nguyên liệu cho một Work Order cụ thể"""
    try:
        materials = frappe.db.sql("""
            SELECT 
                item.item_code as item_code,
                item.item_name as item_name,
                item.description as item_name_detail,
                (bom_item.qty_consumed_per_unit * wo.qty) as required_qty,
                bin.actual_qty as qty_available,
                wo.wip_warehouse as wip_warehouse,
                COALESCE(bom_item.source_warehouse, 
                        item_default.default_warehouse, 
                        wo.source_warehouse) as source_warehouse
            FROM 
                `tabWork Order` wo
            JOIN 
                `tabBOM` bom ON wo.bom_no = bom.name
            JOIN 
                `tabBOM Item` bom_item ON bom.name = bom_item.parent
            JOIN 
                `tabItem` item ON bom_item.item_code = item.name
            LEFT JOIN 
                `tabItem Default` item_default ON item.name = item_default.parent AND item_default.company = wo.company
            LEFT JOIN 
                `tabBin` bin ON (
                    bin.item_code = item.name AND 
                    bin.warehouse = COALESCE(bom_item.source_warehouse, item_default.default_warehouse, wo.source_warehouse)
                )
            WHERE 
                wo.name = %s
        """, (work_order,), as_dict=1)
        
        return materials
    except Exception as e:
        frappe.log_error(f"Error in get_materials_for_single_work_order for {work_order}: {str(e)}")
        return []

def get_consolidated_materials_from_work_orders(work_orders):
    """Lấy danh sách nguyên liệu tổng hợp từ các Work Order"""
    materials_dict = {}
    
    # Lấy materials từ các Work Order
    all_materials = get_materials_for_work_orders(work_orders)
    
    # Gộp các items giống nhau
    for material in all_materials:
        item_code = material.item_code
        if item_code not in materials_dict:
            materials_dict[item_code] = {
                "required_qty": flt(material.required_qty),
                "source_warehouse": material.source_warehouse,
                "wip_warehouse": material.wip_warehouse
            }
        else:
            materials_dict[item_code]["required_qty"] += flt(material.required_qty)
    
    return materials_dict

def get_item_rate(item_code):
    """Lấy giá item từ Item Price hoặc Last Purchase Rate"""
    item_rate = frappe.db.get_value("Item", item_code, "valuation_rate") or 0
    return item_rate

@frappe.whitelist()
def create_individual_stock_entries(doc_name, work_orders):
    """Tạo Stock Entry riêng lẻ cho từng Work Order"""
    if isinstance(work_orders, str):
        try:
            import json
            work_orders = json.loads(work_orders)
        except Exception as e:
            frappe.log_error(f"Error parsing work_orders JSON: {str(e)}")
            frappe.throw(f"Lỗi khi xử lý danh sách Work Order: {str(e)}")
            return []

    # Get document
    doc = frappe.get_doc("Stock Entry Multi Work Orders", doc_name)
    
    # Get adjusted quantities from materials table
    adjusted_quantities = {}
    for row in doc.materials:
        adjusted_quantities[row.item_code] = flt(row.required_qty)
    
    # Theo dõi tổng số lượng của mỗi item trong tất cả Work Order
    total_wo_quantities = {}
    
    # Danh sách các Stock Entries được tạo
    created_entries = []
    
    # Bước 1: Tạo các Stock Entry cơ bản cho từng Work Order
    for wo_name in work_orders:
        try:
            # Lấy thông tin Work Order
            work_order = frappe.get_doc("Work Order", wo_name)
            
            # Tạo Stock Entry mới
            stock_entry = frappe.new_doc("Stock Entry")
            stock_entry.stock_entry_type = "Material Transfer for Manufacture"
            stock_entry.purpose = "Material Transfer for Manufacture"
            stock_entry.work_order = wo_name
            stock_entry.from_bom = 1
            stock_entry.posting_date = doc.posting_date
            stock_entry.posting_time = doc.posting_time
            stock_entry.company = work_order.company
            stock_entry.to_warehouse = work_order.wip_warehouse
            stock_entry.stock_entry_multi_work_orders = doc_name
            
            # Lấy materials cho Work Order này
            wo_materials = get_materials_for_single_work_order(wo_name)
            
            # Cập nhật tổng số lượng cho từng item
            for material in wo_materials:
                item_code = material.item_code
                if item_code not in total_wo_quantities:
                    total_wo_quantities[item_code] = flt(material.required_qty)
                else:
                    total_wo_quantities[item_code] += flt(material.required_qty)
            
            # Thêm các nguyên liệu vào Stock Entry
            for material in wo_materials:
                s_warehouse = material.source_warehouse
                
                # Nếu không có source_warehouse, báo lỗi
                if not s_warehouse:
                    frappe.throw(f"Không tìm thấy Source Warehouse cho item {material.item_code} trong Work Order {wo_name}")
                
                stock_entry.append("items", {
                    "s_warehouse": s_warehouse,
                    "t_warehouse": work_order.wip_warehouse,
                    "item_code": material.item_code,
                    "qty": material.required_qty,
                    "basic_rate": get_item_rate(material.item_code),
                    "uom": frappe.db.get_value("Item", material.item_code, "stock_uom")
                })
            
            # Lưu Stock Entry
            stock_entry.insert()
            created_entries.append(stock_entry.name)
            
        except Exception as e:
            frappe.log_error(f"Error creating Stock Entry for Work Order {wo_name}: {str(e)}")
            frappe.throw(f"Lỗi khi tạo Stock Entry cho Work Order {wo_name}: {str(e)}")
    
    # Bước 2: Xử lý các điều chỉnh số lượng
    # Tìm các item có số lượng điều chỉnh lớn hơn tổng từ Work Order
    items_needing_adjustment = {}
    for item_code, adj_qty in adjusted_quantities.items():
        wo_qty = total_wo_quantities.get(item_code, 0)
        if adj_qty > wo_qty:
            # Lấy source_warehouse và wip_warehouse từ bảng materials
            source_warehouse = None
            wip_warehouse = None
            for row in doc.materials:
                if row.item_code == item_code:
                    source_warehouse = row.source_warehouse
                    wip_warehouse = row.wip_warehouse
                    break
                    
            if source_warehouse and wip_warehouse:
                items_needing_adjustment[item_code] = {
                    "additional_qty": adj_qty - wo_qty,
                    "source_warehouse": source_warehouse,
                    "wip_warehouse": wip_warehouse
                }
    
    # Nếu có items cần điều chỉnh và đã tạo ít nhất một Stock Entry
    if items_needing_adjustment and created_entries:
        try:
            # Lấy Stock Entry cuối cùng
            last_se = frappe.get_doc("Stock Entry", created_entries[-1])
            
            for item_code, detail in items_needing_adjustment.items():
                # Kiểm tra xem item đã có trong Stock Entry chưa
                item_exists = False
                for item in last_se.items:
                    if item.item_code == item_code:
                        # Cập nhật số lượng
                        item.qty += detail["additional_qty"]
                        item_exists = True
                        break
                
                # Nếu item chưa có, thêm mới
                if not item_exists:
                    last_se.append("items", {
                        "s_warehouse": detail["source_warehouse"],
                        "t_warehouse": detail["wip_warehouse"],
                        "item_code": item_code,
                        "qty": detail["additional_qty"],
                        "basic_rate": get_item_rate(item_code),
                        "uom": frappe.db.get_value("Item", item_code, "stock_uom")
                    })
            
            # Lưu Stock Entry
            last_se.save()
            
            frappe.msgprint(f"Đã cập nhật số lượng điều chỉnh cho {len(items_needing_adjustment)} nguyên liệu trong Stock Entry {last_se.name}")
            
        except Exception as e:
            frappe.log_error(f"Error adjusting quantities in Stock Entry: {str(e)}")
            frappe.msgprint(f"Đã tạo các Stock Entry cơ bản nhưng gặp lỗi khi áp dụng số lượng đã điều chỉnh: {str(e)}")
    
    return created_entries
