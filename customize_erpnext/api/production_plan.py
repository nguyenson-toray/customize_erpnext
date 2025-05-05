import frappe
import json
from frappe.query_builder.functions import IfNull, Sum
from frappe import _
from erpnext.manufacturing.doctype.production_plan.production_plan import get_exploded_items as original_get_exploded_items
from erpnext.manufacturing.doctype.production_plan.production_plan import get_items_for_material_requests as original_get_items_for_mr
from erpnext.manufacturing.doctype.production_plan.production_plan import get_subitems as original_get_subitems
from erpnext.manufacturing.doctype.production_plan.production_plan import get_material_request_items as original_get_material_request_items

def get_exploded_items(item_details, company, bom_no, include_non_stock_items, planned_qty=1, doc=None):
    """
    Override the standard get_exploded_items to include the loss percentage
    in the BOM items when calculating required quantities.
    """
    # First get the original exploded items
    items = original_get_exploded_items(item_details, company, bom_no, include_non_stock_items, planned_qty, doc)
    
    # Check if we should apply lost percent
    if not doc or not getattr(doc, 'custom_include_lost_percent_in_bom', 0):
        return items
    
    # Then fetch the loss percentages from the BOM and apply them
    bei = frappe.qb.DocType("BOM Explosion Item")
    bom = frappe.qb.DocType("BOM")
    bom_item = frappe.qb.DocType("BOM Item")
    
    # Get all items with their loss percentages from the BOM
    lost_data = (
        frappe.qb.from_(bom_item)
        .join(bom)
        .on(bom.name == bom_item.parent)
        .select(
            bom_item.item_code,
            bom_item.custom_lost
        )
        .where(
            (bom.name == bom_no) &
            (bom_item.docstatus < 2)
        )
    ).run(as_dict=True)
    
    # Create a mapping of item_code to loss percentage
    loss_map = {d.item_code: d.custom_lost for d in lost_data}
    
    # Apply the loss percentage to each item
    for item_code, item in items.items():
        loss_percentage = loss_map.get(item_code, 0)
        if loss_percentage:
            # Increase the quantity by the loss percentage
            original_qty = item.qty
            item.qty = item.qty * (1 + (loss_percentage / 100))
            frappe.logger().debug(f"Adjusted quantity for {item_code} from {original_qty} to {item.qty} with loss percentage {loss_percentage}%")
    
    return items

def get_subitems(doc, data, item_details, bom_no, company, include_non_stock_items, include_subcontracted_items, parent_qty, planned_qty=1):
    """
    Override the standard get_subitems to include the loss percentage
    in the BOM items when calculating required quantities.
    """
    # Get original subitems
    original_get_subitems(doc, data, item_details, bom_no, company, include_non_stock_items, include_subcontracted_items, parent_qty, planned_qty)
    
    # Check if we should apply lost percent
    if not doc or not getattr(doc, 'custom_include_lost_percent_in_bom', 0):
        return item_details
    
    # Apply the loss percentages to the items
    bom_item = frappe.qb.DocType("BOM Item")
    bom = frappe.qb.DocType("BOM")
    
    # Get all items with their loss percentages from the BOM
    lost_data = (
        frappe.qb.from_(bom_item)
        .join(bom)
        .on(bom.name == bom_item.parent)
        .select(
            bom_item.item_code,
            bom_item.custom_lost
        )
        .where(
            (bom.name == bom_no) &
            (bom_item.docstatus < 2)
        )
    ).run(as_dict=True)
    
    # Create a mapping of item_code to loss percentage
    loss_map = {d.item_code: d.custom_lost for d in lost_data}
    
    # Apply the loss percentage to each item
    for item_code, item in item_details.items():
        loss_percentage = loss_map.get(item_code, 0)
        if loss_percentage:
            # Increase the quantity by the loss percentage
            original_qty = item.qty
            item.qty = item.qty * (1 + (loss_percentage / 100))
            frappe.logger().debug(f"Adjusted quantity in get_subitems for {item_code} from {original_qty} to {item.qty} with loss percentage {loss_percentage}%")
    
    return item_details

def get_material_request_items(doc, row, sales_order, company, ignore_existing_ordered_qty, include_safety_stock, warehouse, bin_dict):
    """
    Override the standard get_material_request_items to use default item warehouse
    when for_warehouse is not specified.
    """
    # Get the default warehouse for the item if not specified
    if not warehouse:
        item_defaults = frappe.db.get_value("Item Default", 
            {"parent": row.item_code, "company": company}, 
            ["default_warehouse"], as_dict=1
        )
        
        if item_defaults and item_defaults.default_warehouse:
            warehouse = item_defaults.default_warehouse
            
        # If still no warehouse, try to get from item group defaults
        if not warehouse:
            item_group = frappe.db.get_value("Item", row.item_code, "item_group")
            if item_group:
                item_group_defaults = frappe.db.get_value("Item Group Default", 
                    {"parent": item_group, "company": company}, 
                    ["default_warehouse"], as_dict=1
                )
                if item_group_defaults and item_group_defaults.default_warehouse:
                    warehouse = item_group_defaults.default_warehouse
        
        # If still no warehouse, set to source warehouse or default warehouse from row
        if not warehouse:
            warehouse = row.get("source_warehouse") or row.get("default_warehouse")
    
    # Call the original function with the determined warehouse
    result = original_get_material_request_items(doc, row, sales_order, company, ignore_existing_ordered_qty, include_safety_stock, warehouse, bin_dict)
    
    # If we have a result and no warehouse was determined, make another attempt to set warehouse
    if result and not result.get("warehouse"):
        result["warehouse"] = warehouse or row.get("default_warehouse") or ""
        
    return result

@frappe.whitelist()
def get_items_for_material_requests(doc, warehouses=None, get_parent_warehouse_data=None):
    """
    Override the standard function to use our custom get_exploded_items
    that includes the loss percentage.
    """
    if isinstance(doc, str):
        doc = frappe._dict(json.loads(doc))
    
    # Check if we should apply custom functions
    if not doc.get('custom_include_lost_percent_in_bom'):
        frappe.logger().info("Skipping custom lost percentage handling as it's disabled")
        return get_items_for_material_requests_default(doc, warehouses, get_parent_warehouse_data)
    
    # Import the original module to patch it temporarily
    import erpnext.manufacturing.doctype.production_plan.production_plan as production_plan
    
    # Save the original functions
    original_exploded_func = production_plan.get_exploded_items
    original_subitems_func = production_plan.get_subitems
    original_material_request_items_func = production_plan.get_material_request_items
    
    try:
        # Replace with our customized functions
        production_plan.get_exploded_items = get_exploded_items
        production_plan.get_subitems = get_subitems
        production_plan.get_material_request_items = get_material_request_items
        
        # Log that we're using the custom function
        frappe.logger().info("Using customized get_items_for_material_requests with loss percentage support")
        
        # Call the original function which will now use our custom functions
        result = original_get_items_for_mr(doc, warehouses, get_parent_warehouse_data)
        
        return result
    except Exception as e:
        frappe.logger().error(f"Error in customized get_items_for_material_requests: {str(e)}")
        # Fallback to original function if our custom one fails
        return original_get_items_for_mr(doc, warehouses, get_parent_warehouse_data)
    finally:
        # Restore the original functions
        production_plan.get_exploded_items = original_exploded_func
        production_plan.get_subitems = original_subitems_func
        production_plan.get_material_request_items = original_material_request_items_func

@frappe.whitelist()
def get_items_for_material_requests_default(doc, warehouses=None, get_parent_warehouse_data=None):
    """
    Modified version of the standard function to use default item warehouse
    when for_warehouse is not specified, but without applying loss percentage.
    """
    if isinstance(doc, str):
        doc = frappe._dict(json.loads(doc))
    
    # Import the original module to patch it temporarily
    import erpnext.manufacturing.doctype.production_plan.production_plan as production_plan
    
    # Save the original function
    original_material_request_items_func = production_plan.get_material_request_items
    
    try:
        # Replace only the material_request_items function
        production_plan.get_material_request_items = get_material_request_items
        
        # Log that we're using the custom function
        frappe.logger().info("Using default get_items_for_material_requests with warehouse handling")
        
        # Call the original function which will now use our custom get_material_request_items
        result = original_get_items_for_mr(doc, warehouses, get_parent_warehouse_data)
        
        return result
    except Exception as e:
        frappe.logger().error(f"Error in default get_items_for_material_requests_default: {str(e)}")
        # Fallback to original function if our custom one fails
        return original_get_items_for_mr(doc, warehouses, get_parent_warehouse_data)
    finally:
        # Restore the original function
        production_plan.get_material_request_items = original_material_request_items_func