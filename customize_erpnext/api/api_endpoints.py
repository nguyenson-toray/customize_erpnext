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
            "insert_after": "user_type",
            "description": "Exclude this rack from auto-suggestion to new employees"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True, "message": "Field added successfully"}
    except Exception as e:
        frappe.log_error(f"setup_assignment_field error: {str(e)}")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def setup_employee_do_not_suggest_field():
    """
    Add custom_do_not_suggest_shoe_rack Check field to Employee doctype.
    Run once: bench --site <site> execute customize_erpnext.api.api_endpoints.setup_employee_do_not_suggest_field
    """
    try:
        if frappe.db.exists("Custom Field", {"dt": "Employee", "fieldname": "custom_do_not_suggest_shoe_rack"}):
            return {"success": True, "message": "Field already exists"}

        doc = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "Employee",
            "fieldname": "custom_do_not_suggest_shoe_rack",
            "fieldtype": "Check",
            "label": "Do Not Suggest Shoe Rack",
            "insert_after": "custom_shoe_rack",
            "in_list_view": 1,
            "in_standard_filter": 1,
            "default": "0",
            "description": "Exclude this employee from the Shoe Rack Suggest Slots feature"
        })
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        return {"success": True, "message": "Field added successfully"}
    except Exception as e:
        frappe.log_error(f"setup_employee_do_not_suggest_field error: {str(e)}")
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
def get_unassigned_employees():
    """
    Return every Active employee who does not currently occupy any Shoe Rack
    compartment, regardless of their date_of_joining.

    Used by the "All Unassigned" mode of the Assign Shoe Racks panel to catch
    employees who slipped through - joined a while ago but were never given
    a rack (as opposed to get_today_joiners, which only looks at one day).
    """
    try:
        employees = frappe.db.sql(
            """
            SELECT emp.name, emp.employee_name, emp.gender, emp.date_of_joining, emp.department
            FROM `tabEmployee` emp
            WHERE emp.status = 'Active'
              AND NOT EXISTS (
                  SELECT 1 FROM `tabShoe Rack` sr
                  WHERE sr.compartment_1_employee = emp.name
                     OR sr.compartment_2_employee = emp.name
              )
            ORDER BY emp.date_of_joining DESC
            """,
            as_dict=True
        )

        # Same shape as get_today_joiners's employees list, so the frontend
        # can feed either source into the same table/actions.
        for e in employees:
            e["already_assigned"] = False
            e["existing_rack_name"] = None
            e["existing_rack_display_name"] = None
            e["existing_compartment"] = None

        return {
            "success": True,
            "employees": employees,
            "total_unassigned": len(employees)
        }

    except Exception as e:
        frappe.log_error(f"get_unassigned_employees error: {str(e)}")
        return {"success": False, "employees": [], "message": str(e)}


def _build_slot_pools(exclude_slots=None, exclude_racks=None):
    """
    Build the two pools of free Standard Employee compartments used by the
    suggestion engine.

    A compartment counts as taken when it holds an Employee, an External
    Personnel, OR when it is flagged "Chưa xác định (Unknown)" - the flag is
    exactly how the floor team records "someone we cannot identify already
    put their shoes here", so those slots must never be suggested again.

    Args:
        exclude_slots: iterable of (rack_name, compartment) tuples to skip
        exclude_racks: iterable of rack names to skip entirely

    Returns:
        (paired_slots, empty_slots)
        paired_slots -> free compartment of a rack that already has one occupant
        empty_slots  -> free compartment of a rack with nobody in it yet
        Each slot: {"rack_name", "rack_display_name", "compartment", "required_gender"}
    """
    exclude_slots = set(exclude_slots or [])
    exclude_racks = set(exclude_racks or [])

    _rack_meta = frappe.get_meta("Shoe Rack")
    _rack_fields = [
        "name", "rack_display_name", "compartments",
        "compartment_1_employee", "compartment_2_employee"
    ]
    for _optional in (
        "do_not_auto_suggest",
        "compartment_1_external_personnel", "compartment_2_external_personnel",
        "compartment_1_unidentified", "compartment_2_unidentified",
    ):
        if _rack_meta.has_field(_optional):
            _rack_fields.append(_optional)

    available_racks = frappe.get_all(
        "Shoe Rack",
        filters={"rack_type": "Standard Employee"},
        fields=_rack_fields,
        order_by="name asc",
        limit_page_length=0
    )

    # Exclude racks marked do_not_auto_suggest (safe if field absent)
    filtered_racks = [
        r for r in available_racks
        if not r.get("do_not_auto_suggest") and r.name not in exclude_racks
    ]

    # Look up the gender of anyone already occupying a compartment, in bulk
    occupant_ids = set()
    for r in filtered_racks:
        if r.get("compartment_1_employee"):
            occupant_ids.add(r["compartment_1_employee"])
        if r.get("compartment_2_employee"):
            occupant_ids.add(r["compartment_2_employee"])

    occupant_gender = {}
    occupant_no_pair = set()
    if occupant_ids:
        _occ_fields = ["name", "gender"]
        if frappe.get_meta("Employee").has_field("custom_do_not_suggest_shoe_rack"):
            _occ_fields.append("custom_do_not_suggest_shoe_rack")
        for e in frappe.get_all(
            "Employee",
            filters=[["name", "in", list(occupant_ids)]],
            fields=_occ_fields,
            limit_page_length=0
        ):
            occupant_gender[e.name] = e.gender or ""
            if e.get("custom_do_not_suggest_shoe_rack"):
                occupant_no_pair.add(e.name)

    # A paired slot is dropped entirely (not offered to anyone) when its
    # existing occupant is flagged "Do Not Suggest Shoe Rack".
    paired_slots = []
    empty_slots = []

    for rack in filtered_racks:
        comp_count = int(rack.get("compartments") or 1)
        taken = {}
        for comp in (1, 2):
            taken[comp] = bool(
                rack.get(f"compartment_{comp}_employee")
                or rack.get(f"compartment_{comp}_external_personnel")
                or rack.get(f"compartment_{comp}_unidentified")
            )

        for comp in (1, 2):
            if comp == 2 and comp_count != 2:
                continue
            if taken[comp] or (rack.name, comp) in exclude_slots:
                continue

            other = 2 if comp == 1 else 1
            other_emp = rack.get(f"compartment_{other}_employee") if comp_count == 2 else None
            if other_emp and other_emp in occupant_no_pair:
                continue  # rack-mate opted out of being paired with a new person

            occupied_other = taken[other] if comp_count == 2 else False
            slot = {
                "rack_name": rack.name,
                "rack_display_name": rack.rack_display_name,
                "compartment": comp,
                "required_gender": occupant_gender.get(other_emp, "") if other_emp else "",
            }
            (paired_slots if occupied_other else empty_slots).append(slot)

    return paired_slots, empty_slots


@frappe.whitelist()
def suggest_shoe_racks(employees):
    """
    Suggest the first available Standard Employee rack slot for each employee.

    Racks no longer carry a fixed gender field - the only rule is that the
    two people sharing a rack should be the same gender. Slots are ranked:

      1. The open compartment of a rack that already has one occupant of the
         SAME gender as the employee - fills the rack without creating a
         mismatch.
      2. A fully empty rack (nobody in either compartment yet).
      3. Last resort: any remaining open compartment, even if its existing
         occupant is a different gender, so nobody is left unassigned. Racks
         assigned this way will show up in the "Tủ lệch giới tính" list for
         manual follow-up.

    Excludes racks with do_not_auto_suggest = 1.

    If an occupied compartment's occupant has
    Employee.custom_do_not_suggest_shoe_rack = 1, the rack's other (free)
    compartment is NOT offered to anyone else - that employee's rack is
    protected from being auto-paired with a new person. The flagged
    employee themselves is unaffected as a suggestion target (if they don't
    have a rack yet, they can still be suggested one normally).

    Args:
        employees: JSON list of {"name": "...", "employee_name": "...", "gender": "..."}

    Returns:
        {"success": True, "suggestions": [...], "matched": N, "unmatched": N}
    """
    try:
        if isinstance(employees, str):
            employees = json.loads(employees)

        paired_slots, empty_slots = _build_slot_pools()

        used_slots = set()

        def _take_slot(emp_gender, pool, gender_strict):
            for slot in pool:
                slot_key = (slot["rack_name"], slot["compartment"])
                if slot_key in used_slots:
                    continue
                if gender_strict and slot["required_gender"] and emp_gender and slot["required_gender"] != emp_gender:
                    continue
                used_slots.add(slot_key)
                return slot
            return None

        emp_meta = []
        for emp in employees:
            emp_id = emp.get("name") or emp.get("employee")
            emp_meta.append({
                "id": emp_id,
                "name": emp.get("employee_name") or emp_id,
                "gender": (emp.get("gender") or "").strip(),
            })

        assigned_slot = {}

        # Pass 1: fill a rack that already has a same-gender occupant (no mismatch created)
        for meta in emp_meta:
            assigned_slot[meta["id"]] = _take_slot(meta["gender"], paired_slots, gender_strict=True)

        # Pass 2: put into a fully empty rack
        for meta in emp_meta:
            if assigned_slot[meta["id"]] is None:
                assigned_slot[meta["id"]] = _take_slot(meta["gender"], empty_slots, gender_strict=False)

        # Pass 3: last resort - any remaining open compartment, even mixed-gender
        for meta in emp_meta:
            if assigned_slot[meta["id"]] is None:
                assigned_slot[meta["id"]] = _take_slot(meta["gender"], paired_slots, gender_strict=False)

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
def swap_shoe_rack(employee, rack_name, compartment, exclude_slots=None):
    """
    Move an employee off a rack compartment that turns out to be physically
    occupied, and mark that compartment as "Chưa xác định (Unknown)".

    Real-world case: "Suggest Slots" proposes rack N compartment 1, but when
    the team walks the floor someone's shoes are already in there and nobody
    knows whose they are. This endpoint, in one step:

      1. Flags the old compartment `compartment_N_unidentified = 1` so the
         suggestion engine never offers it again (and the rack status counts
         it as occupied), removing the employee from it when the assignment
         had already been written to the DB.
      2. Finds another slot for the employee using the normal suggestion
         ranking, skipping the whole old rack plus `exclude_slots`.
      3. Re-assigns the employee to that new slot if - and only if - they
         were really assigned to the old one in the DB. A row that was only
         a pending suggestion stays pending on its new slot.

    The old compartment is NOT flagged when it holds a different, known
    employee: that is a stale suggestion, not an unidentified occupant, so
    the employee is simply pointed at another slot.

    Args:
        employee: Employee ID being moved.
        rack_name: Shoe Rack the employee should be moved off.
        compartment: 1 or 2 - the compartment to mark Unknown.
        exclude_slots: optional JSON list of {"rack_name", "compartment"}
            (or [rack_name, compartment] pairs) reserved by other rows of
            the panel, so two people never get pointed at the same slot.

    Returns:
        {
            "success": bool,
            "marked_unknown": bool,        # old compartment flagged?
            "released": bool,              # employee removed from old slot?
            "assigned": bool,              # written into the new slot?
            "suggested": bool,             # a new slot was found?
            "rack_name", "rack_display_name", "compartment",   # new slot
            "old_rack_display_name",
            "message": str
        }
    """
    try:
        compartment = int(compartment)
        if compartment not in (1, 2):
            return {"success": False, "message": f"Invalid compartment: {compartment}"}

        if not employee or not frappe.db.exists("Employee", employee):
            return {"success": False, "message": f"Employee {employee} not found"}

        if not rack_name or not frappe.db.exists("Shoe Rack", rack_name):
            return {"success": False, "message": f"Rack {rack_name} not found"}

        if isinstance(exclude_slots, str):
            exclude_slots = json.loads(exclude_slots or "[]")

        skip = set()
        for s in (exclude_slots or []):
            try:
                if isinstance(s, dict):
                    skip.add((s.get("rack_name"), int(s.get("compartment"))))
                else:
                    skip.add((s[0], int(s[1])))
            except (TypeError, ValueError, IndexError):
                continue

        rack = frappe.get_doc("Shoe Rack", rack_name)
        emp_field = f"compartment_{compartment}_employee"
        flag_field = f"compartment_{compartment}_unidentified"
        old_display = rack.rack_display_name or rack_name
        occupant = rack.get(emp_field)

        marked_unknown = False
        released = False

        if occupant and occupant != employee:
            # Someone else legitimately holds the slot - leave the rack alone.
            note = (f"Rack {old_display} compartment {compartment} is already "
                    f"assigned to {occupant}, so it was not marked Unknown.")
        else:
            if occupant == employee:
                rack.set(emp_field, None)
                released = True
            rack.set(flag_field, 1)
            rack.save(ignore_permissions=True)
            marked_unknown = True
            note = f"Rack {old_display} compartment {compartment} marked Unknown."

        # Find a replacement slot - the whole old rack is off the table
        paired_slots, empty_slots = _build_slot_pools(
            exclude_slots=skip, exclude_racks={rack_name}
        )

        gender = (frappe.db.get_value("Employee", employee, "gender") or "").strip()

        def _pick(pool, gender_strict):
            for slot in pool:
                if gender_strict and slot["required_gender"] and gender \
                        and slot["required_gender"] != gender:
                    continue
                return slot
            return None

        # Same ranking as suggest_shoe_racks: same-gender rack-mate, then a
        # fully empty rack, then any open compartment as a last resort.
        new_slot = (_pick(paired_slots, True)
                    or _pick(empty_slots, False)
                    or _pick(paired_slots, False))

        if not new_slot:
            frappe.db.commit()
            return {
                "success": True,
                "marked_unknown": marked_unknown,
                "released": released,
                "assigned": False,
                "suggested": False,
                "rack_name": None,
                "rack_display_name": None,
                "compartment": None,
                "old_rack_display_name": old_display,
                "message": f"{note} No free rack left for {employee}."
            }

        assigned = False
        if released:
            # The employee really held the old slot, so keep them assigned.
            new_rack = frappe.get_doc("Shoe Rack", new_slot["rack_name"])
            new_field = f"compartment_{new_slot['compartment']}_employee"
            if new_rack.get(new_field):
                frappe.db.commit()
                return {
                    "success": False,
                    "marked_unknown": marked_unknown,
                    "released": released,
                    "assigned": False,
                    "suggested": False,
                    "rack_name": None,
                    "rack_display_name": None,
                    "compartment": None,
                    "old_rack_display_name": old_display,
                    "message": (f"{note} But rack {new_rack.rack_display_name} "
                                f"compartment {new_slot['compartment']} was taken "
                                f"meanwhile - {employee} now has no rack, please "
                                f"run Suggest Slots again.")
                }
            new_rack.set(new_field, employee)
            new_rack.save(ignore_permissions=True)
            assigned = True

        frappe.db.commit()

        return {
            "success": True,
            "marked_unknown": marked_unknown,
            "released": released,
            "assigned": assigned,
            "suggested": True,
            "rack_name": new_slot["rack_name"],
            "rack_display_name": new_slot["rack_display_name"],
            "compartment": new_slot["compartment"],
            "old_rack_display_name": old_display,
            "message": (f"{note} {employee} moved to rack "
                        f"{new_slot['rack_display_name']} compartment "
                        f"{new_slot['compartment']}.")
        }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(f"swap_shoe_rack error: {str(e)}")
        return {"success": False, "message": str(e)}


@frappe.whitelist()
def bulk_set_do_not_suggest_shoe_rack(custom_group, value=1, active_only=1):
    """
    Bulk set (or clear) Employee.custom_do_not_suggest_shoe_rack for every
    employee in a given Group, so the Shoe Rack "Suggest Slots" feature
    skips them without having to tick the field one employee at a time.

    Args:
        custom_group: Group name (Employee.custom_group) to match (required).
        value: 1 to flag "do not suggest", 0 to clear the flag. Default 1.
        active_only: If truthy (default), only Active employees are updated.

    Returns:
        {"success": True, "updated": N}
    """
    if not frappe.has_permission("Employee", "write"):
        frappe.throw(_("Not permitted to update Employee"), frappe.PermissionError)

    if not custom_group:
        frappe.throw(_("Group is required"))

    if not frappe.db.exists("Group", custom_group):
        frappe.throw(_("Group {0} not found").format(custom_group))

    value = 1 if int(value) else 0
    filters = {"custom_group": custom_group}
    if int(active_only or 0):
        filters["status"] = "Active"

    matched = frappe.get_all("Employee", filters=filters, pluck="name")
    if not matched:
        return {"success": True, "updated": 0}

    frappe.db.set_value("Employee", filters, "custom_do_not_suggest_shoe_rack", value)
    frappe.db.commit()

    return {"success": True, "updated": len(matched)}


@frappe.whitelist()
def get_employees_by_group(custom_group):
    """
    Return the ids of every Employee in a given Group, for the Shoe Rack
    Layout Manager's "highlight by Group" filter. Not restricted to Active
    employees so racks still held by a since-left member of the group are
    highlighted too.

    Args:
        custom_group: Group name (Employee.custom_group).

    Returns:
        {"success": True, "employees": ["EMP-0001", ...]}
    """
    if not custom_group:
        return {"success": True, "employees": []}

    employees = frappe.get_all(
        "Employee",
        filters={"custom_group": custom_group},
        pluck="name"
    )
    return {"success": True, "employees": employees}


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

        items.sort(key=lambda x: (x["rack_name"], x["compartment"]))
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