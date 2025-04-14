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
    # Query to find work orders related to the selected item template and color
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
                wo.wip_warehouse as wip_warehouse
            FROM `tabWork Order` wo
            JOIN `tabBOM` bom ON wo.bom_no = bom.name
            JOIN `tabBOM Item` bom_item ON bom.name = bom_item.parent
            JOIN `tabItem` item ON bom_item.item_code = item.name
            LEFT JOIN `tabBin` bin ON (
                bin.item_code = item.name 
                AND bin.warehouse = wo.source_warehouse
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
    
    frappe.log_error(f"Processing work_orders: {work_orders}")
    
    all_materials = []
    for work_order in work_orders:
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
                    wo.wip_warehouse as wip_warehouse
                FROM `tabWork Order` wo
                JOIN `tabBOM` bom ON wo.bom_no = bom.name
                JOIN `tabBOM Item` bom_item ON bom.name = bom_item.parent
                JOIN `tabItem` item ON bom_item.item_code = item.name
                LEFT JOIN `tabBin` bin ON (
                    bin.item_code = item.name 
                    AND bin.warehouse = wo.source_warehouse
                )
                WHERE wo.name = %s
            """, work_order, as_dict=1)
            
            frappe.log_error(f"Found {len(materials)} materials for work order {work_order}")
            all_materials.extend(materials)
        except Exception as e:
            frappe.log_error(f"Error querying materials for {work_order}: {str(e)}")
    
    frappe.log_error(f"Returning {len(all_materials)} total materials")
    return all_materials