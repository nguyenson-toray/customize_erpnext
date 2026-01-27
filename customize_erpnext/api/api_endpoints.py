import frappe
from frappe import _
import json

@frappe.whitelist()
def save_rack_layout(layout):
    """
    Lưu toàn bộ layout của racks
    
    Args:
        layout: JSON string hoặc list
        [
            {
                "rack_name": "RACK-00001",
                "block_id": "block-0",
                "block_index": 0,
                "slot_index": 0
            },
            ...
        ]
    
    Returns:
        {"success": True, "message": "...", "updated": count}
    """
    try:
        if isinstance(layout, str):
            layout = json.loads(layout)
        
        updated = 0
        errors = []
        
        for item in layout:
            try:
                rack_name = item.get("rack_name")
                block_id = item.get("block_id")
                block_index = item.get("block_index")
                slot_index = item.get("slot_index")
                
                if not rack_name:
                    continue
                
                # Check rack exists
                if not frappe.db.exists("Shoe Rack", rack_name):
                    errors.append(f"Rack {rack_name} not found")
                    continue
                
                # Update rack position
                frappe.db.set_value(
                    "Shoe Rack",
                    rack_name,
                    {
                        "block_id": block_id,
                        "block_index": block_index,
                        "slot_index": slot_index
                    },
                    update_modified=False
                )
                
                updated += 1
                
            except Exception as e:
                errors.append(f"{item.get('rack_name', 'Unknown')}: {str(e)}")
        
        frappe.db.commit()
        
        result = {
            "success": True,
            "message": _("Đã lưu vị trí cho {0} tủ").format(updated),
            "updated": updated
        }
        
        if errors:
            result["errors"] = errors
            result["message"] += f" (có {len(errors)} lỗi)"
        
        return result
    
    except Exception as e:
        frappe.log_error(f"Save rack layout error: {str(e)}")
        return {
            "success": False,
            "message": str(e),
            "updated": 0
        }


@frappe.whitelist()
def save_block_order(order):
    """
    Lưu thứ tự của blocks
    
    Args:
        order: JSON string hoặc list
        [
            {"block_id": "block-0", "order": 0},
            {"block_id": "block-1", "order": 1},
            ...
        ]
    
    Returns:
        {"success": True, "message": "..."}
    """
    try:
        if isinstance(order, str):
            order = json.loads(order)
        
        # Save to custom doctype or settings
        # Option 1: Save to Settings doctype
        settings = frappe.get_single("Shoe Rack Settings")
        settings.block_order = json.dumps(order)
        settings.save(ignore_permissions=True)
        
        # Option 2: Save to custom field in each rack
        # (Already handled by save_rack_layout)
        
        return {
            "success": True,
            "message": _("Đã lưu thứ tự blocks")
        }
    
    except Exception as e:
        frappe.log_error(f"Save block order error: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        }


@frappe.whitelist()
def load_rack_layout():
    """
    Load layout đã lưu
    
    Returns:
        {
            "success": True,
            "racks": [...],
            "blocks": [...]
        }
    """
    try:
        # Load all racks with position info
        racks = frappe.get_all(
            "Shoe Rack",
            fields=[
                "name",
                "rack_display_name",
                "status",
                "compartments",
                "gender",
                "rack_type",
                "block_id",
                "block_index",
                "slot_index"
            ],
            order_by="block_index asc, slot_index asc"
        )
        
        # Group racks into blocks
        blocks = {}
        unassigned = []
        
        for rack in racks:
            if rack.get('block_id') and rack.get('block_index') is not None:
                block_id = rack.block_id
                if block_id not in blocks:
                    blocks[block_id] = {
                        "id": block_id,
                        "index": rack.block_index,
                        "racks": [None] * 16
                    }
                
                slot_idx = rack.get('slot_index', 0)
                if 0 <= slot_idx < 16:
                    blocks[block_id]["racks"][slot_idx] = rack
            else:
                unassigned.append(rack)
        
        # Sort blocks by index
        sorted_blocks = sorted(blocks.values(), key=lambda b: b['index'])
        
        # Fill empty slots with placeholder
        for block in sorted_blocks:
            for i in range(16):
                if block["racks"][i] is None:
                    block["racks"][i] = {
                        "name": f"empty-{block['id']}-{i}",
                        "rack_display_name": "",
                        "status": None,
                        "isEmpty": True
                    }
        
        # If there are unassigned racks, create new blocks for them
        if unassigned:
            for i, rack in enumerate(unassigned):
                block_idx = len(sorted_blocks) + i // 16
                slot_idx = i % 16
                
                if slot_idx == 0:
                    sorted_blocks.append({
                        "id": f"block-{block_idx}",
                        "index": block_idx,
                        "racks": [None] * 16
                    })
                
                sorted_blocks[-1]["racks"][slot_idx] = rack
        
        return {
            "success": True,
            "blocks": sorted_blocks,
            "total_racks": len(racks),
            "unassigned": len(unassigned)
        }
    
    except Exception as e:
        frappe.log_error(f"Load rack layout error: {str(e)}")
        return {
            "success": False,
            "blocks": [],
            "message": str(e)
        }


# ===============================================
# 📝 SETUP DATABASE FIELDS
# ===============================================
"""
Cần thêm 3 fields vào Shoe Rack DocType:

1. block_id (Data) - ID của block chứa rack này
2. block_index (Int) - Index của block trong layout
3. slot_index (Int) - Vị trí của rack trong block (0-15)

Chạy code này trong console để thêm:
"""

def add_layout_fields():
    """
    Thêm fields cần thiết cho layout
    Chạy: bench --site your-site console
    frappe.call('customize_erpnext.api.add_layout_fields')
    """
    fields = [
        {
            "fieldname": "block_id",
            "fieldtype": "Data",
            "label": "Block ID",
            "insert_after": "rack_display_name",
            "description": "ID của block chứa rack này"
        },
        {
            "fieldname": "block_index",
            "fieldtype": "Int",
            "label": "Block Index",
            "insert_after": "block_id",
            "description": "Thứ tự block trong layout"
        },
        {
            "fieldname": "slot_index",
            "fieldtype": "Int",
            "label": "Slot Index",
            "insert_after": "block_index",
            "description": "Vị trí trong block (0-15)"
        }
    ]
    
    for field in fields:
        try:
            existing = frappe.db.exists("Custom Field", {
                "dt": "Shoe Rack",
                "fieldname": field["fieldname"]
            })
            
            if existing:
                print(f"⚠️ Field {field['fieldname']} already exists")
                continue
            
            doc = frappe.get_doc({
                "doctype": "Custom Field",
                "dt": "Shoe Rack",
                **field
            })
            doc.insert(ignore_permissions=True)
            print(f"✅ Added field: {field['fieldname']}")
        
        except Exception as e:
            print(f"❌ Error adding {field['fieldname']}: {str(e)}")
    
    frappe.db.commit()
    print("\n🎉 Done! Fields added successfully")


# ===============================================
# 🧪 TEST FUNCTIONS
# ===============================================

@frappe.whitelist()
def test_save_layout():
    """Test save layout"""
    test_layout = [
        {"rack_name": "RACK-00001", "block_id": "block-0", "block_index": 0, "slot_index": 0},
        {"rack_name": "RACK-00002", "block_id": "block-0", "block_index": 0, "slot_index": 1},
    ]
    
    result = save_rack_layout(test_layout)
    print(result)
    return result


@frappe.whitelist()
def test_load_layout():
    """Test load layout"""
    result = load_rack_layout()
    print(f"Loaded {len(result.get('blocks', []))} blocks")
    return result