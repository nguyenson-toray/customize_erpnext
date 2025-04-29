import frappe
from frappe import _
from datetime import datetime, timedelta
from erpnext.setup.utils import get_exchange_rate 
import re
from typing import List, Dict, Any
import json

@frappe.whitelist()
def sum_duplicate_items(doc):
    """Sum quantities of duplicate items"""
    if isinstance(doc, str):
        doc = frappe.parse_json(doc)
    items_dict = {}
    required_by = datetime.now().date() + timedelta(days=3)
    
    for item in doc.get("items", []):
        # Get Item information if not available
        if not item.get("item_name") or not item.get("uom"):
            item_details = frappe.db.get_value("Item", 
                item["item_code"], 
                ["item_name", "stock_uom"], 
                as_dict=1
            )
            item["item_name"] = item_details.item_name
            item["uom"] = item_details.stock_uom
            item["stock_uom"] = item_details.stock_uom
            
        # Get from_warehouse if not available
        if not item.get("from_warehouse"):
            default_warehouse = frappe.db.get_value(
                "Item Default", 
                {"parent": item["item_code"], "company": doc.get("company")}, 
                "default_warehouse"
            )
            item["from_warehouse"] = default_warehouse
            
        # Ensure conversion_factor exists
        if not item.get("conversion_factor"):
            item["conversion_factor"] = 1.0
            
        key = (item["item_code"], item["uom"])
        if key in items_dict:
            items_dict[key]["qty"] += item["qty"]
        else:
            item_copy = item.copy()
            # Ensure Required By and schedule_date fields are set
            item_copy.update({
                "required_by": required_by,
                "from_warehouse": item.get("from_warehouse"),
                "warehouse": "6.1 - WIP Production - TIQN",
                "conversion_factor": item.get("conversion_factor", 1.0),
                "stock_uom": item.get("stock_uom")
            })
            items_dict[key] = item_copy
    
    return list(items_dict.values())
@frappe.whitelist()
def get_items_from_production_plan(production_plan):
    """Retrieve items from Production Plan"""
    if not frappe.has_permission("Production Plan", "read"):
        frappe.throw(_("Insufficient permissions to access Production Plan"))
        
    items = []
    pp_doc = frappe.get_doc("Production Plan", production_plan)
    
    if not pp_doc.docstatus == 1:
        frappe.throw(_("Production Plan must be in Submitted status"))
        
    # Set Required By date from Production Plan
    required_by = pp_doc.posting_date + timedelta(days=3) if pp_doc.posting_date else datetime.now().date() + timedelta(days=3)
    
    for pp_item in pp_doc.mr_items:
        # Get information from Item table
        item_details = frappe.db.get_value("Item", 
            pp_item.item_code, 
            ["item_name", "stock_uom"], 
            as_dict=1
        )
        # Get default warehouse from Item Default
        default_warehouse = frappe.db.get_value(
            "Item Default", 
            {"parent": pp_item.item_code, "company": pp_doc.company}, 
            "default_warehouse"
        )
        
        # Get conversion_factor
        conversion_factor = 1.0
        if item_details.stock_uom != pp_item.uom:
            conversion_factor = frappe.db.get_value('UOM Conversion Detail',
                {'parent': pp_item.item_code, 'uom': pp_item.uom},
                'conversion_factor'
            ) or 1.0

        items.append({
            "item_code": pp_item.item_code,
            "item_name": item_details.item_name,
            "qty": pp_item.quantity,
            "uom": item_details.stock_uom,
            "stock_uom": item_details.stock_uom,
            "conversion_factor": conversion_factor,
            "from_warehouse": default_warehouse,  # Source warehouse
            "warehouse": "6.1 - WIP Production - TIQN"  # Target warehouse
        })
    
    # Create custom_note
    finished_items_detail = []
    for item in pp_doc.po_items:
        item_name = frappe.db.get_value("Item", item.item_code, "item_name")
        finished_items_detail.append(f"{item_name}: {item.planned_qty} {item.stock_uom}")
    
    custom_note = (f"MR for plan: {pp_doc.name} {pp_doc.total_planned_qty} Pcs\n"
                  f"{pp_doc.custom_note or ''}\n"
                  f"Detail: {', '.join(finished_items_detail)}")
    
    return {
        "items": items,
        "custom_note": custom_note
    }

# def prepare_item_details(item_dict):
#     """Prepare item details with default values and conversion factor"""
#     item_code = item_dict.get("item_code")
#     uom = item_dict.get("uom")
    
#     # Get conversion factor from UOM
#     conversion_factor = frappe.get_value("UOM Conversion Detail",
#         {"parent": item_code, "uom": uom},
#         "conversion_factor"
#     ) or 1.0
    
#     return {
#         "item_code": item_code,
#         "item_name": item_dict.get("item_name"),
#         "qty": item_dict.get("qty", 0),
#         "uom": uom,
#         "conversion_factor": conversion_factor,
#         # "schedule_date": item_dict.get("schedule_date", add_days(today(), 3)),
#         "warehouse": item_dict.get("warehouse", "6.1 - WIP Production - TIQN"),
#         "from_warehouse": item_dict.get("source_warehouse")
#     }
@frappe.whitelist()
def get_items_from_production_plan(production_plan):
    """Retrieve items from Production Plan"""
    if not frappe.has_permission("Production Plan", "read"):
        frappe.throw(_("Insufficient permissions to access Production Plan"))
        
    items = []
    pp_doc = frappe.get_doc("Production Plan", production_plan)
    
    if not pp_doc.docstatus == 1:
        frappe.throw(_("Production Plan must be in Submitted status"))
    
    for pp_item in pp_doc.mr_items:
        # Get information from Item table
        item_details = frappe.db.get_value("Item", 
            pp_item.item_code, 
            ["item_name", "stock_uom"], 
            as_dict=1
        )
        
        # Get default warehouse from Item Default
        default_warehouse = frappe.db.get_value(
            "Item Default", 
            {"parent": pp_item.item_code, "company": pp_doc.company}, 
            "default_warehouse"
        )
        
        # Set conversion factor to 1.0 as we're using stock_uom
        conversion_factor = 1.0
        
        items.append({
            "item_code": pp_item.item_code,
            "item_name": item_details.item_name,
            "qty": pp_item.quantity,
            "uom": item_details.stock_uom,  # Use stock_uom from Item
            "stock_uom": item_details.stock_uom,
            "conversion_factor": conversion_factor,
            "from_warehouse": default_warehouse,  # Source warehouse
            # "warehouse": "6.1 - WIP Production - TIQN"  # Target warehouse
        })
    
    # Create custom_note with production items detail
    finished_items_detail = []
    for item in pp_doc.po_items:
        item_name = frappe.db.get_value("Item", item.item_code, "item_name")
        # Get stock_uom from Item
        stock_uom = frappe.db.get_value("Item", item.item_code, "stock_uom")
        finished_items_detail.append(f"{item_name}: {item.planned_qty} {stock_uom}")
    
    custom_note = (f"MR for plan: {pp_doc.name} {pp_doc.total_planned_qty} Pcs\n"
                  f"{pp_doc.custom_note or ''}\n"
                  f"Detail: {', '.join(finished_items_detail)}")
    
    return {
        "items": items,
        "custom_note": custom_note,
        "name": pp_doc.name,
        "planned_qty": pp_doc.total_planned_qty
    }

@frappe.whitelist()
def split_items_by_groups(items, groups, docname=None):
    """Split items and create separate Material Requests by groups.
    
    Args:
        items: List of items from the original Material Request
        groups: List of item groups to split by
        docname: ID of the original Material Request
        
    Returns:
        List of new Material Request IDs
    """
    try:
        # Start a database transaction
        frappe.db.begin()
        
        # Process input data
        if isinstance(items, str):
            items = json.loads(items)
        if isinstance(groups, str):
            groups = json.loads(groups)
        
        # Validate document
        if not docname:
            docname = frappe.form_dict.get("docname")
        if not docname:
            frappe.throw(_("Material Request ID is required"))
            
        original_mr = frappe.get_doc("Material Request", docname)
        if original_mr.docstatus != 0:
            frappe.throw(_("Can only split Material Request in Draft status"))

        # Validate input data
        if not groups or not isinstance(groups, (list, tuple)) or len(groups) == 0:
            frappe.throw(_("Please select at least one group to split the Material Request"))
        
        if not items or not isinstance(items, (list, tuple)) or len(items) == 0:
            frappe.throw(_("Material Request has no items to split"))

        # Get item groups mapping
        item_groups = {}
        for item in items:
            item_code = item.get("item_code")
            if item_code:
                item_group = frappe.db.get_value("Item", item_code, "item_group")
                if item_group:
                    item_groups[item_code] = item_group

        # Classify items by group
        grouped_items = {group: [] for group in groups}
        remaining_items = []
        
        # Track processed items to update original MR
        processed_items = set()

        for item in items:
            item_code = item.get("item_code")
            if not item_code:
                continue
                
            item_group = item_groups.get(item_code)
            if not item_group:
                remaining_items.append(item)
                continue
                
            grouped = False
            for group in groups:
                if group in item_group:
                    grouped_items[group].append(item)
                    processed_items.add(item_code)
                    grouped = True
                    break
                    
            if not grouped:
                remaining_items.append(item)

        # Create new Material Requests for each group
        mr_list = []
        mr_messages = []

        for group, group_items in grouped_items.items():
            if not group_items:
                continue
                
            group_name = group.split("-")[2]
            
            # Create new Material Request
            new_mr = frappe.new_doc("Material Request")
            new_mr.material_request_type = original_mr.material_request_type
            # new_mr.schedule_date = original_mr.schedule_date
            new_mr.company = original_mr.company
            
            # Copy custom fields
            for field in original_mr.meta.get_custom_fields():
                if hasattr(original_mr, field.fieldname):
                    setattr(new_mr, field.fieldname, getattr(original_mr, field.fieldname))
            
            new_mr.custom_note = f"{original_mr.custom_note} - {group_name}" if original_mr.custom_note else group_name
            new_mr.schedule_date = datetime.now().date() + timedelta(days=3)
            # Add items
            for item in group_items:
                new_mr.append("items", {
                    "item_code": item.get("item_code"),
                    "item_name": item.get("item_name"),
                    "qty": item.get("qty"),
                    "uom": item.get("uom"),
                    # "schedule_date": item.get("schedule_date"),
                    "warehouse": item.get("warehouse"),
                    "from_warehouse": item.get("from_warehouse") or item.get("source_warehouse"),
                    "stock_uom": item.get("stock_uom"),
                    "description": item.get("description"),
                    "conversion_factor": item.get("conversion_factor", 1.0)
                })
            
            new_mr.insert()
            mr_list.append(new_mr.name)
            mr_messages.append(_("Material Request {0} created for group {1} with {2} items").format(
                new_mr.name, group_name, len(group_items)))

        # Update original Material Request
        if remaining_items:
            # Clear existing items and add remaining ones
            original_mr.items = []
            for item in remaining_items:
                original_mr.append("items", {
                    "item_code": item.get("item_code"),
                    "item_name": item.get("item_name"),
                    "qty": item.get("qty"),
                    "uom": item.get("uom"),
                    # "schedule_date": item.get("schedule_date"),
                    "warehouse": item.get("warehouse"),
                    "from_warehouse": item.get("from_warehouse") or item.get("source_warehouse"),
                    "stock_uom": item.get("stock_uom"),
                    "description": item.get("description"),
                    "conversion_factor": item.get("conversion_factor", 1.0)
                })
            original_mr.custom_note = f"{original_mr.custom_note} - Remaining Items" if original_mr.custom_note else "Remaining Items"
            original_mr.save()
            mr_messages.append(_("Original Material Request updated with {0} remaining items").format(len(remaining_items)))
            mr_list.append(original_mr.name)
        else:
            # Delete original MR if no items remain
            original_mr.flags.ignore_permissions = True
            frappe.delete_doc("Material Request", original_mr.name, force=1)
            mr_messages.append(_("Original Material Request deleted as all items were split"))

        # Commit the transaction
        frappe.db.commit()
        
        # Display summary messages
        frappe.msgprint("<br>".join(mr_messages))

        return mr_list
        
    except Exception as e:
        # Rollback transaction on error
        frappe.db.rollback()
        frappe.log_error(f"Material Request Split Error: {str(e)}")
        frappe.throw(_("Error splitting Material Request: {0}").format(str(e)))

@frappe.whitelist()
def get_materials_from_work_orders(work_orders):
    """
    Get required materials from selected Work Orders
    Args:
        work_orders: List of Work Order IDs
    Returns:
        dict: Contains items list and custom note
    """
    if isinstance(work_orders, str):
        work_orders = json.loads(work_orders)
        
    if not work_orders:
        frappe.throw(_("Please select at least one Work Order"))
        
    items_dict = {}
    wo_details = []
    
    for wo_id in work_orders:
        wo = frappe.get_doc("Work Order", wo_id)
        if wo.docstatus != 1:
            continue
            
        # Calculate pending qty
        pending_qty = wo.qty - wo.material_transferred_for_manufacturing
        if pending_qty <= 0:
            continue
            
        # Get item details for custom note
        wo_details.append(f"{wo.name}: {pending_qty} Pcs {wo.item_name or wo.production_item}")
        
        # Get required items from BOM
        bom = frappe.get_doc("BOM", wo.bom_no)
        for item in bom.items:
            # Calculate required quantity based on pending Work Order quantity
            req_qty = (item.qty / bom.quantity) * pending_qty
            
            # Get item details
            item_info = frappe.db.get_value("Item",
                item.item_code,
                ["item_name", "stock_uom", "item_group"],
                as_dict=1
            )
            
            # Get default warehouse
            default_warehouse = frappe.db.get_value(
                "Item Default",
                {"parent": item.item_code, "company": wo.company},
                "default_warehouse"
            )
            
            key = (item.item_code, item.stock_uom)
            if key in items_dict:
                items_dict[key]["qty"] += req_qty
            else:
                items_dict[key] = {
                    "item_code": item.item_code,
                    "item_name": item_info.item_name,
                    "qty": req_qty,
                    "uom": item_info.stock_uom,
                    "stock_uom": item_info.stock_uom,
                    "conversion_factor": 1.0,
                    "from_warehouse": default_warehouse,
                    "warehouse": "WIP Production - TIQN"
                }
    
    # Prepare custom note
    custom_note = "MR for:\n" + "\n".join(wo_details)
    
    return {
        "items": list(items_dict.values()),
        "custom_note": custom_note
    }        