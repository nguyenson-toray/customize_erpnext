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


# ===============================================
# 👟 SHOE RACK ASSIGNMENT ENDPOINTS
# ===============================================

@frappe.whitelist()
def setup_assignment_field():
    """
    Add do_not_auto_suggest Check field to Shoe Rack doctype.
    Run once: bench --site <site> execute customize_erpnext.api.api_endpoints.setup_assignment_field
    """
    try:
        if frappe.db.exists("Custom Field", {"dt": "Shoe Rack", "fieldname": "do_not_auto_suggest"}):
            return {"success": True, "message": "Field already exists"}

        doc = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Shoe Rack",
            "fieldname": "do_not_auto_suggest",
            "fieldtype": "Check",
            "label": "Do Not Auto Suggest",
            "insert_after": "gender",
            "description": "Exclude this rack from auto-suggestion to new employees"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True, "message": "Field added successfully"}
    except Exception as e:
        frappe.log_error(f"setup_assignment_field error: {str(e)}")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def get_today_joiners(date=None):
    """
    Return Active employees whose date_of_joining equals `date` (default today).

    Every joiner is returned (none are hidden). Each one is annotated with the
    Shoe Rack they already occupy, if any, so the UI can show an accurate
    status ("Assigned" + rack number) instead of always showing "Pending".
    """
    try:
        join_date = date or frappe.utils.today()

        employees = frappe.get_all(
            "Employee",
            filters={"date_of_joining": join_date, "status": "Active"},
            fields=["name", "employee_name", "gender", "date_of_joining", "department"],
            limit_page_length=0
        )

        if not employees:
            return {"success": True, "employees": [], "date": join_date,
                    "total_joiners": 0, "already_assigned": 0}

        emp_ids = [e.name for e in employees]

        # Map employee -> the rack/compartment they currently occupy
        existing = {}
        for comp, field in [(1, "compartment_1_employee"), (2, "compartment_2_employee")]:
            rows = frappe.get_all(
                "Shoe Rack",
                filters=[[field, "in", emp_ids]],
                fields=["name", "rack_display_name", field],
                limit_page_length=0
            )
            for r in rows:
                emp = r.get(field)
                # Keep the first rack found; an employee should only ever hold one slot
                if emp and emp not in existing:
                    existing[emp] = {
                        "rack_name": r.name,
                        "rack_display_name": r.rack_display_name,
                        "compartment": comp,
                    }

        for e in employees:
            info = existing.get(e.name)
            e["already_assigned"] = bool(info)
            e["existing_rack_name"] = info["rack_name"] if info else None
            e["existing_rack_display_name"] = info["rack_display_name"] if info else None
            e["existing_compartment"] = info["compartment"] if info else None

        return {
            "success": True,
            "employees": employees,
            "date": join_date,
            "total_joiners": len(employees),
            "already_assigned": len(existing)
        }

    except Exception as e:
        frappe.log_error(f"get_today_joiners error: {str(e)}")
        return {"success": False, "employees": [], "message": str(e)}


@frappe.whitelist()
def suggest_shoe_racks(employees):
    """
    Suggest the first available Standard Employee rack slot for each employee.
    Matches on gender when both employee and rack have a gender set.
    Excludes racks with do_not_auto_suggest = 1.

    Args:
        employees: JSON list of {"name": "...", "employee_name": "...", "gender": "..."}

    Returns:
        {"success": True, "suggestions": [...], "matched": N, "unmatched": N}
    """
    try:
        if isinstance(employees, str):
            employees = json.loads(employees)

        _rack_fields = [
            "name", "rack_display_name", "gender", "compartments",
            "compartment_1_employee", "compartment_2_employee"
        ]
        _dna_exists = frappe.get_meta("Shoe Rack").has_field("do_not_auto_suggest")
        if _dna_exists:
            _rack_fields.append("do_not_auto_suggest")

        available_racks = frappe.get_all(
            "Shoe Rack",
            filters={"rack_type": "Standard Employee"},
            fields=_rack_fields,
            order_by="rack_display_name asc",
            limit_page_length=0
        )

        # Exclude racks marked do_not_auto_suggest (safe if field absent)
        filtered_racks = [r for r in available_racks if not r.get("do_not_auto_suggest")]

        # Build ordered list of available (rack, compartment) slots
        available_slots = []
        for rack in filtered_racks:
            comp_count = int(rack.get("compartments") or 1)
            gender = rack.get("gender") or ""

            if not rack.get("compartment_1_employee"):
                available_slots.append({
                    "rack_name": rack.name,
                    "rack_display_name": rack.rack_display_name,
                    "compartment": 1,
                    "gender": gender
                })

            if comp_count == 2 and not rack.get("compartment_2_employee"):
                available_slots.append({
                    "rack_name": rack.name,
                    "rack_display_name": rack.rack_display_name,
                    "compartment": 2,
                    "gender": gender
                })

        used_slots = set()

        def _take_slot(emp_gender, gender_strict):
            """Return the first free slot. When gender_strict, only same-gender
            slots are considered (used for the preference pass)."""
            for slot in available_slots:
                slot_key = (slot["rack_name"], slot["compartment"])
                if slot_key in used_slots:
                    continue
                if gender_strict and emp_gender and slot["gender"] and emp_gender != slot["gender"]:
                    continue
                used_slots.add(slot_key)
                return slot
            return None

        emp_meta = []
        for emp in employees:
            emp_meta.append({
                "id": emp.get("name") or emp.get("employee"),
                "name": emp.get("employee_name") or (emp.get("name") or emp.get("employee")),
                "gender": (emp.get("gender") or "").strip(),
            })

        assigned_slot = {}

        # Pass 1: prefer a same-gender empty slot for each employee.
        for meta in emp_meta:
            assigned_slot[meta["id"]] = _take_slot(meta["gender"], gender_strict=True)

        # Pass 2: any employee still without a slot gets the next free
        # Standard Employee slot regardless of gender (only condition: rack_type).
        for meta in emp_meta:
            if assigned_slot[meta["id"]] is None:
                assigned_slot[meta["id"]] = _take_slot(meta["gender"], gender_strict=False)

        suggestions = []
        for meta in emp_meta:
            found = assigned_slot[meta["id"]]
            suggestions.append({
                "employee": meta["id"],
                "employee_name": meta["name"],
                "gender": meta["gender"],
                "rack_name": found["rack_name"] if found else None,
                "rack_display_name": found["rack_display_name"] if found else None,
                "compartment": found["compartment"] if found else None,
                "suggested": found is not None
            })

        return {
            "success": True,
            "suggestions": suggestions,
            "matched": sum(1 for s in suggestions if s["suggested"]),
            "unmatched": sum(1 for s in suggestions if not s["suggested"])
        }

    except Exception as e:
        frappe.log_error(f"suggest_shoe_racks error: {str(e)}")
        return {"success": False, "suggestions": [], "message": str(e)}


@frappe.whitelist()
def assign_shoe_racks(assignments):
    """
    Assign employees to specific rack compartments.

    Args:
        assignments: JSON list of {"employee": "...", "rack_name": "...", "compartment": 1}

    Returns:
        {"success": True, "assigned": N, "errors": [...]}
    """
    try:
        if isinstance(assignments, str):
            assignments = json.loads(assignments)

        assigned = 0
        errors = []

        for item in assignments:
            emp = item.get("employee")
            rack_name = item.get("rack_name")
            compartment = int(item.get("compartment", 1))

            if not emp or not rack_name:
                errors.append(f"Missing employee or rack_name: {item}")
                continue

            try:
                if not frappe.db.exists("Shoe Rack", rack_name):
                    errors.append(f"Rack {rack_name} not found")
                    continue

                rack = frappe.get_doc("Shoe Rack", rack_name)
                field = f"compartment_{compartment}_employee"

                current = getattr(rack, field, None)
                if current:
                    errors.append(f"Rack {rack_name} compartment {compartment} already occupied by {current}")
                    continue

                setattr(rack, field, emp)
                rack.save(ignore_permissions=True)
                assigned += 1

            except Exception as e:
                errors.append(f"{rack_name}: {str(e)}")

        frappe.db.commit()
        return {"success": True, "assigned": assigned, "errors": errors}

    except Exception as e:
        frappe.log_error(f"assign_shoe_racks error: {str(e)}")
        return {"success": False, "assigned": 0, "message": str(e)}


@frappe.whitelist()
def get_left_employees_in_racks():
    """
    Return all shoe rack compartments that are still assigned to an employee
    whose status is 'Left'.
    """
    try:
        racks = frappe.get_all(
            "Shoe Rack",
            filters=[
                ["compartment_1_employee", "!=", ""],
                ["compartment_1_employee", "is", "set"]
            ],
            fields=["name", "rack_display_name", "compartment_1_employee", "compartment_2_employee"],
            limit_page_length=0,
            or_filters=[
                ["compartment_1_employee", "is", "set"],
                ["compartment_2_employee", "is", "set"]
            ]
        )

        # Fetch all employees with status Left in a single query for efficiency
        left_set = set(
            r.name for r in frappe.get_all(
                "Employee",
                filters={"status": "Left"},
                fields=["name"],
                limit_page_length=0
            )
        )

        # Also fetch employee details we'll need
        all_emp_ids = set()
        for rack in racks:
            if rack.get("compartment_1_employee"):
                all_emp_ids.add(rack["compartment_1_employee"])
            if rack.get("compartment_2_employee"):
                all_emp_ids.add(rack["compartment_2_employee"])

        emp_details = {}
        if all_emp_ids:
            for emp in frappe.get_all(
                "Employee",
                filters=[["name", "in", list(all_emp_ids)]],
                fields=["name", "employee_name", "department", "status"],
                limit_page_length=0
            ):
                emp_details[emp.name] = emp

        items = []
        for rack in racks:
            for compartment in [1, 2]:
                field = f"compartment_{compartment}_employee"
                emp_id = rack.get(field)
                if emp_id and emp_id in left_set:
                    emp = emp_details.get(emp_id, {})
                    items.append({
                        "rack_name": rack.name,
                        "rack_display_name": rack.get("rack_display_name") or rack.name,
                        "compartment": compartment,
                        "employee": emp_id,
                        "employee_name": emp.get("employee_name") or emp_id,
                        "department": emp.get("department") or "",
                    })

        items.sort(key=lambda x: (x["rack_display_name"], x["compartment"]))
        return {"success": True, "items": items, "total": len(items)}

    except Exception as e:
        frappe.log_error(f"get_left_employees_in_racks error: {str(e)}")
        return {"success": False, "items": [], "message": str(e)}


@frappe.whitelist()
def clear_left_employees_from_racks(items):
    """
    Clear the compartment field for the given list of {rack_name, compartment}.

    Args:
        items: JSON list of {"rack_name": "...", "compartment": 1}

    Returns:
        {"success": True, "cleared": N, "errors": [...]}
    """
    try:
        if isinstance(items, str):
            items = json.loads(items)

        cleared = 0
        errors = []

        for item in items:
            rack_name = item.get("rack_name")
            compartment = int(item.get("compartment", 1))

            if not rack_name:
                errors.append(f"Missing rack_name: {item}")
                continue

            try:
                if not frappe.db.exists("Shoe Rack", rack_name):
                    errors.append(f"Rack {rack_name} not found")
                    continue

                rack = frappe.get_doc("Shoe Rack", rack_name)
                field = f"compartment_{compartment}_employee"
                setattr(rack, field, None)
                rack.save(ignore_permissions=True)
                cleared += 1

            except Exception as e:
                errors.append(f"{rack_name} C{compartment}: {str(e)}")

        frappe.db.commit()
        return {"success": True, "cleared": cleared, "errors": errors}

    except Exception as e:
        frappe.log_error(f"clear_left_employees_from_racks error: {str(e)}")
        return {"success": False, "cleared": 0, "message": str(e)}