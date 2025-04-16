# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

class StockEntryMultiWorkOrders(Document):
    pass
 # Get color options for the selected item template
@frappe.whitelist()
# query to get colors for the selected item template
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
            item.item_name as item_name,
            item.description as item_name_detail,
            wo.qty as qty_to_manufacture
        FROM `tabWork Order` wo
        INNER JOIN `tabItem` item ON wo.production_item = item.name
        INNER JOIN `tabItem Variant Attribute` attr ON item.name = attr.parent
        WHERE item.variant_of = %s
        AND attr.attribute = 'Color'
        AND attr.attribute_value = %s
        AND wo.status IN ('Not Started', 'In Process')
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
                IFNULL(bom_item.source_warehouse, item_default.default_warehouse) as source_warehouse
            FROM `tabWork Order` wo
            JOIN `tabBOM` bom ON wo.bom_no = bom.name
            JOIN `tabBOM Item` bom_item ON bom.name = bom_item.parent
            JOIN `tabItem` item ON bom_item.item_code = item.name
            LEFT JOIN `tabItem Default` item_default ON item.name = item_default.parent AND item_default.company = wo.company
            LEFT JOIN `tabBin` bin ON (
                bin.item_code = item.name 
                AND bin.warehouse = IFNULL(bom_item.source_warehouse, wo.source_warehouse)
            )
            WHERE wo.name = %s
        """, wo.work_order, as_dict=1)
        
        all_materials.extend(materials)
    
    return {'work_orders': work_orders, 'materials': all_materials}

# Get materials for changed work orders
@frappe.whitelist()
def get_materials_for_work_orders(work_orders):
    # Debug logging
    frappe.log_error(f"Received work_orders: {work_orders}, Type: {type(work_orders)}")
    
    # Handle string input (single work order)
    if isinstance(work_orders, str):
        # Check if it's a JSON string
        if work_orders.startswith('[') and work_orders.endswith(']'):
            try:
                import json
                work_orders = json.loads(work_orders)
                frappe.log_error(f"Parsed JSON work_orders: {work_orders}")
            except Exception as e:
                frappe.log_error(f"Error parsing JSON: {str(e)}")
        else:
            work_orders = [work_orders]
    
    # Kiểm tra nếu work_orders rỗng
    if not work_orders:
        frappe.log_error("Empty work_orders list")
        return []
    
    frappe.log_error(f"Processing work_orders: {work_orders}")
    
    all_materials = []
    for work_order in work_orders:
        # Kiểm tra nếu work_order là chuỗi rỗng
        if not work_order or not isinstance(work_order, str) or not work_order.strip():
            frappe.log_error(f"Invalid work order: {work_order}")
            continue
            
        # Debug log
        frappe.log_error(f"Processing work order: {work_order}")
        
        # Get materials from Work Order BOM
        try:
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
                    AND bin.warehouse = IFNULL(bom_item.source_warehouse, wo.source_warehouse)
                )
                WHERE wo.name = %s
            """, work_order, as_dict=1)
            
            frappe.log_error(f"Found {len(materials)} materials for work order {work_order}")
            all_materials.extend(materials)
        except Exception as e:
            frappe.log_error(f"Error querying materials for {work_order}: {str(e)}")
    
    frappe.log_error(f"Returning {len(all_materials)} total materials")
    return all_materials


@frappe.whitelist()
def create_individual_stock_entries(doc_name, work_orders):
    if isinstance(work_orders, str):
        import json
        work_orders = json.loads(work_orders)

    # Danh sách các Stock Entries được tạo
    created_entries = []
    
    for wo_name in work_orders:
        try:
            # Lấy thông tin Work Order
            work_order = frappe.get_doc("Work Order", wo_name)
            
            # Tạo Stock Entry mới cho Work Order này
            stock_entry = frappe.new_doc("Stock Entry")
            stock_entry.stock_entry_type = "Material Transfer for Manufacture"
            stock_entry.purpose = "Material Transfer for Manufacture"
            stock_entry.work_order = wo_name
            
            # Lọc các materials chỉ cho Work Order này
            wo_materials = get_materials_for_single_work_order(wo_name)
            
            # Thêm các nguyên liệu vào Stock Entry
            for material in wo_materials:
                # Ưu tiên sử dụng source_warehouse từ BOM Item
                s_warehouse = material.source_warehouse if hasattr(material, 'source_warehouse') else None
                
                # Nếu không có source_warehouse từ BOM Item, sử dụng source_warehouse từ Work Order
                if not s_warehouse:
                    s_warehouse = work_order.source_warehouse
                
                # Nếu vẫn không có source_warehouse, báo lỗi
                if not s_warehouse:
                    frappe.throw(f"Không tìm thấy Source Warehouse cho item {material.item_code} trong Work Order {wo_name}")
                
                stock_entry.append("items", {
                    "s_warehouse": s_warehouse,
                    "t_warehouse": work_order.wip_warehouse,
                    "item_code": material.item_code,
                    "qty": material.required_qty,
                    "basic_rate": get_item_rate(material.item_code)
                })
            
            # Lưu Stock Entry
            stock_entry.save()
            created_entries.append(stock_entry.name)
            
            frappe.db.commit()
            
        except Exception as e:
            frappe.log_error(f"Error creating Stock Entry for Work Order {wo_name}: {str(e)}")
            # Ném lỗi để người dùng biết
            frappe.throw(f"Lỗi khi tạo Stock Entry cho Work Order {wo_name}: {str(e)}")
    
    return created_entries

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
                `tabBin` bin ON (bin.item_code = item.name AND bin.warehouse = IFNULL(bom_item.source_warehouse, wo.source_warehouse))
            WHERE 
                wo.name = %s
        """, (work_order,), as_dict=1)
        
        return materials
    except Exception as e:
        frappe.log_error(f"Error in get_materials_for_single_work_order for {work_order}: {str(e)}")
        return []

def get_item_rate(item_code):
    # Lấy giá item từ Item Price hoặc Last Purchase Rate
    item_rate = frappe.db.get_value("Item", item_code, "valuation_rate") or 0
    return item_rate

def check_material_availability(work_order):
    """Kiểm tra nguyên liệu có đủ cho Work Order không"""
    materials = get_materials_for_single_work_order(work_order)
    insufficient_items = [
        item for item in materials 
        if (item.qty_available or 0) < item.required_qty
    ]
    
    return {
        'sufficient': len(insufficient_items) == 0,
        'insufficient_items': insufficient_items
    }
