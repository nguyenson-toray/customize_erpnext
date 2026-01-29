# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
import json
import re

@frappe.whitelist()
def save_layout(layout_data):
    """
    Save layout configuration to Shoe Rack Layout Settings (Single DocType)
    
    Args:
        layout_data: JSON string containing rows and blocks configuration
    
    Returns:
        dict: {"success": True/False, "message": "..."}
    """
    try:
        # Validate JSON
        json.loads(layout_data)
        
        # Save to Single DocType
        frappe.db.set_single_value('Shoe Rack Layout Settings', 'layout_data', layout_data)
        frappe.db.set_single_value('Shoe Rack Layout Settings', 'last_modified_by', frappe.session.user)
        frappe.db.set_single_value('Shoe Rack Layout Settings', 'last_modified_date', frappe.utils.now())
        frappe.db.commit()
        
        return {
            "success": True,
            "message": "Layout saved successfully"
        }
    
    except json.JSONDecodeError as e:
        frappe.log_error(f"Invalid JSON in layout_data: {str(e)}")
        return {
            "success": False,
            "message": f"Invalid JSON: {str(e)}"
        }
    
    except Exception as e:
        frappe.log_error(f"Save layout error: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        }


@frappe.whitelist()
def load_layout():
    """
    Load saved layout configuration from database
    
    Returns:
        dict: {"layout_data": "JSON string"}
    """
    try:
        layout_data = frappe.db.get_single_value('Shoe Rack Layout Settings', 'layout_data')
        
        if not layout_data:
            # Return default empty layout
            layout_data = json.dumps([])
        
        return {
            "layout_data": layout_data
        }
    
    except Exception as e:
        frappe.log_error(f"Load layout error: {str(e)}")
        return {
            "layout_data": "[]"
        }


@frappe.whitelist()
def get_block_racks(start_rack, end_rack):
    """
    Get all racks in a block range with their current status
    
    Args:
        start_rack: e.g., "RACK-1", "J-1", "G-1", "A-1"
        end_rack: e.g., "RACK-16", "J-16", "G-16", "A-16"
    
    Returns:
        dict: {"success": True/False, "racks": [...], "count": n}
    """
    try:
        # Extract series prefix and numbers
        start_match = re.match(r'^([A-Z]+)-(\d+)$', start_rack)
        end_match = re.match(r'^([A-Z]+)-(\d+)$', end_rack)
        
        if not start_match or not end_match:
            return {
                "success": False,
                "message": "Invalid rack format. Use: RACK-1, J-1, G-1, or A-1"
            }
        
        prefix = start_match.group(1)
        start_num = int(start_match.group(2))
        end_num = int(end_match.group(2))
        
        if prefix != end_match.group(1):
            return {
                "success": False,
                "message": "Start and end racks must be from same series"
            }
        
        if start_num > end_num:
            return {
                "success": False,
                "message": "Start rack number must be <= end rack number"
            }
        
        # Build list of rack names
        rack_names = [f"{prefix}-{str(i).zfill(4)}" for i in range(start_num, end_num + 1)]
        
        # Fetch racks from database
        racks = frappe.get_all(
            "Shoe Rack",
            filters={"name": ["in", rack_names]},
            fields=[
                "name", "status", "gender", "user_type", "compartments", "rack_type",
                "compartment_1_employee", "compartment_2_employee",
                "compartment_1_external_personnel", "compartment_2_external_personnel"
            ],
            order_by="name asc"
        )
        
        return {
            "success": True,
            "racks": racks,
            "count": len(racks),
            "total_expected": len(rack_names)
        }
    
    except Exception as e:
        frappe.log_error(f"Get block racks error: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        }


@frappe.whitelist()
def validate_block_range(start_rack, end_rack):
    """
    Validate if block range contains exactly 16 racks (4x4 grid)
    
    Args:
        start_rack: Starting rack name
        end_rack: Ending rack name
    
    Returns:
        dict: {"valid": True/False, "message": "...", "rack_count": n}
    """
    try:
        start_match = re.match(r'^([A-Z]+)-(\d+)$', start_rack)
        end_match = re.match(r'^([A-Z]+)-(\d+)$', end_rack)
        
        if not start_match or not end_match:
            return {
                "valid": False,
                "message": "Invalid rack format. Use format: RACK-1, J-1, G-1, or A-1"
            }
        
        prefix_start = start_match.group(1)
        prefix_end = end_match.group(1)
        
        if prefix_start != prefix_end:
            return {
                "valid": False,
                "message": "Start and end racks must be from same series"
            }
        
        start_num = int(start_match.group(2))
        end_num = int(end_match.group(2))
        
        rack_count = end_num - start_num + 1
        
        if rack_count != 16:
            return {
                "valid": False,
                "message": f"Block must contain exactly 16 racks (4x4 grid). Current: {rack_count} racks",
                "rack_count": rack_count
            }
        
        return {
            "valid": True,
            "message": "Valid block range (16 racks)",
            "rack_count": rack_count
        }
    
    except Exception as e:
        return {
            "valid": False,
            "message": str(e)
        }


@frappe.whitelist()
def get_available_rack_ranges(series_prefix, gender=None, user_type=None):
    """
    Get suggested rack ranges for creating blocks (groups of 16)
    
    Args:
        series_prefix: 'RACK', 'J', 'G', 'A'
        gender: Optional filter (Male/Female)
        user_type: Optional filter (Employee/External)
    
    Returns:
        dict: {"success": True/False, "blocks": [...], "total_racks": n}
    """
    try:
        if series_prefix not in ['RACK', 'J', 'G', 'A']:
            return {
                "success": False,
                "message": "Invalid series prefix. Must be: RACK, J, G, or A"
            }
        
        filters = {"name": ["like", f"{series_prefix}-%"]}
        
        if gender:
            filters["gender"] = gender
        if user_type:
            filters["user_type"] = user_type
        
        # Get all racks in series
        racks = frappe.get_all(
            "Shoe Rack",
            filters=filters,
            fields=["name", "status", "gender", "user_type"],
            order_by="name asc"
        )
        
        if not racks:
            return {
                "success": False,
                "message": f"No racks found for series {series_prefix}"
            }
        
        # Group into blocks of 16
        suggested_blocks = []
        
        for i in range(0, len(racks), 16):
            block = racks[i:i+16]
            
            if len(block) == 16:
                suggested_blocks.append({
                    "start_rack": block[0]["name"],
                    "end_rack": block[-1]["name"],
                    "suggested_name": f"Block {len(suggested_blocks) + 1} ({series_prefix})",
                    "rack_count": 16
                })
        
        return {
            "success": True,
            "blocks": suggested_blocks,
            "total_racks": len(racks),
            "complete_blocks": len(suggested_blocks),
            "remaining_racks": len(racks) % 16
        }
    
    except Exception as e:
        frappe.log_error(f"Get available ranges error: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        }


@frappe.whitelist()
def get_layout_statistics():
    """
    Get statistics for current layout configuration
    
    Returns:
        dict: Statistics about rows, blocks, and slots
    """
    try:
        layout_data = frappe.db.get_single_value('Shoe Rack Layout Settings', 'layout_data')
        
        if not layout_data:
            return {
                "total_rows": 0,
                "total_blocks": 0,
                "empty_slots": 0,
                "filled_slots": 0
            }
        
        rows = json.loads(layout_data)
        
        total_rows = len(rows)
        total_blocks = 0
        empty_slots = 0
        
        for row in rows:
            for block in row.get("blocks", []):
                if block is None:
                    empty_slots += 1
                else:
                    total_blocks += 1
        
        total_slots = total_blocks + empty_slots
        
        return {
            "total_rows": total_rows,
            "total_blocks": total_blocks,
            "empty_slots": empty_slots,
            "filled_slots": total_blocks,
            "total_slots": total_slots,
            "usage_percent": round((total_blocks / total_slots * 100) if total_slots > 0 else 0, 1)
        }
    
    except Exception as e:
        frappe.log_error(f"Get statistics error: {str(e)}")
        return {
            "total_rows": 0,
            "total_blocks": 0,
            "empty_slots": 0
        }