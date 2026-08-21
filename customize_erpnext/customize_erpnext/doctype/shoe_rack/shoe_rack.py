# shoe_rack.py - COMPLETE VERSION

import frappe
from frappe import _
from frappe.model.document import Document
import re

class ShoeRack(Document):
    pass


# Fields holding a person, per compartment: (link field, name field, gender field)
COMPARTMENT_FIELDS = {
    "Employee": {
        1: ("compartment_1_employee", "compartment_1_employee_name", "gender_employee_1"),
        2: ("compartment_2_employee", "compartment_2_employee_name", "employee_2_gender"),
    },
    "External Personnel": {
        1: ("compartment_1_external_personnel", None, None),
        2: ("compartment_2_external_personnel", None, None),
    },
}

# When ON, a person already sitting in another rack is MOVED here instead of the
# save being blocked. Data Import turns it on automatically (frappe.flags.in_import),
# because the imported list is meant to be the new source of truth. A bench script
# can opt in with: frappe.flags.shoe_rack_auto_reassign = True
AUTO_REASSIGN_FLAG = "shoe_rack_auto_reassign"


def is_auto_reassign_mode():
    return bool(frappe.flags.in_import or frappe.flags.get(AUTO_REASSIGN_FLAG))

def validate(doc, method):
    """Validate Shoe Rack before save"""
    
    # Auto-set user_type based on rack_type
    if doc.rack_type in ['Standard Employee', 'Japanese Employee']:
        doc.user_type = 'Employee'
    else:
        doc.user_type = 'External'
    
    # Auto-set naming series
    if doc.is_new() and doc.rack_type and not doc.naming_series:
        series_map = {
            'Standard Employee': 'RACK-',
            'Guest': 'G-',
            'Japanese Employee': 'J-',
            'External Personnel': 'A-'
        }
        doc.naming_series = series_map.get(doc.rack_type, 'RACK-')
    
    # Clear incompatible assignments
    clear_incompatible_assignments(doc)

    # Check duplicate assignment across racks
    check_duplicate_assignment(doc)

    # Validate compartments
    if doc.compartments == "1":
        doc.compartment_2_employee = None
        doc.compartment_2_external_personnel = None

    enforce_unidentified_flags(doc)

    # Auto update status
    update_status(doc)

    # Warn (do not block) if the two occupants of this rack are different genders
    check_mixed_gender(doc)
    
    # ✨ Auto-generate display name
    generate_display_name(doc)

def enforce_unidentified_flags(doc):
    """Slot có người thật thì không được tick Unknown - tự bỏ tick nếu có xung đột."""
    if doc.compartment_1_employee or doc.compartment_1_external_personnel:
        doc.compartment_1_unidentified = 0
    if doc.compartment_2_employee or doc.compartment_2_external_personnel:
        doc.compartment_2_unidentified = 0
    # Tủ 1 ngăn thì ngăn 2 không tồn tại - cờ Unknown trên đó là vô nghĩa và
    # chỉ làm nhiễu report get_unidentified_occupant_racks.
    if doc.compartments == "1":
        doc.compartment_2_unidentified = 0


def compute_status(compartments, has_comp1, has_comp2):
    """Status string từ tình trạng 2 ngăn. Nguồn duy nhất cho mọi chỗ tính status."""
    if compartments == "1":
        return "1/1" if has_comp1 else "0/1"

    total_used = (1 if has_comp1 else 0) + (1 if has_comp2 else 0)
    if total_used == 0:
        return "0/2"
    if total_used == 1:
        return "1/2"
    return "2/2"


def update_status(doc):
    """Auto update status - coi 'unidentified' như đã chiếm chỗ"""
    has_comp1 = bool(doc.compartment_1_employee or doc.compartment_1_external_personnel
                     or doc.compartment_1_unidentified)
    has_comp2 = bool(doc.compartment_2_employee or doc.compartment_2_external_personnel
                     or doc.compartment_2_unidentified)

    doc.status = compute_status(doc.compartments, has_comp1, has_comp2)

def generate_display_name(doc):
    """
    Generate friendly display name:
    - RACK-00001 → 1
    - J-00001 → J1
    - G-00001 → G1
    - A-00001 → A1
    """
    if not doc.name:
        return
    
    # Extract prefix and number
    match = re.match(r'^([A-Z]+)-(\d+)$', doc.name)
    if not match:
        doc.rack_display_name = doc.name
        return
    
    prefix = match.group(1)
    number_str = match.group(2)
    number = int(number_str.lstrip('0') or '0')
    
    # Format based on prefix
    if prefix == 'RACK':
        doc.rack_display_name = str(number)
    else:
        doc.rack_display_name = f"{prefix}{number}"

def clear_incompatible_assignments(doc):
    """Clear fields that don't match current user_type"""
    if doc.user_type == "Employee":
        doc.compartment_1_external_personnel = None
        doc.compartment_2_external_personnel = None
    else:
        doc.compartment_1_employee = None
        doc.compartment_2_employee = None

def get_person_name(person_id, person_doctype):
    if person_doctype == "Employee":
        return frappe.db.get_value("Employee", person_id, "employee_name") or person_id
    return frappe.db.get_value("External Personnel", person_id, "full_name") or person_id


def check_duplicate_assignment(doc):
    """One person = one rack.

    Normal (manual) save: block the save and point at the rack already holding them.
    Auto-reassign mode (Data Import): the incoming list wins - the person is pulled
    out of the old rack instead, and the move is recorded on doc.flags so on_update
    can log it.
    """

    person_doctype = "Employee" if doc.user_type == "Employee" else "External Personnel"
    f1 = COMPARTMENT_FIELDS[person_doctype][1][0]
    f2 = COMPARTMENT_FIELDS[person_doctype][2][0]

    checks = []
    if doc.get(f1):
        checks.append((doc.get(f1), _("Compartment 1"), person_doctype))
    if doc.get(f2):
        checks.append((doc.get(f2), _("Compartment 2"), person_doctype))

    # Same person in BOTH compartments of this very rack: always an error. Moving
    # them somewhere else cannot fix it, so auto-reassign must not swallow it.
    if len(checks) == 2 and checks[0][0] == checks[1][0]:
        person_id = checks[0][0]
        frappe.throw(_("{0} ({1}) is assigned to both compartments of this rack.").format(
            get_person_name(person_id, person_doctype), person_id))

    auto = is_auto_reassign_mode()
    current_name = doc.name or ""

    for person_id, compartment_label, person_doctype in checks:
        existing = frappe.get_all("Shoe Rack",
            filters={"name": ["!=", current_name]},
            or_filters={f1: person_id, f2: person_id},
            fields=["name", "rack_display_name"],
            limit_page_length=0,
        )

        if not existing:
            continue

        person_name = get_person_name(person_id, person_doctype)

        if not auto:
            rack_display = existing[0].rack_display_name or existing[0].name
            frappe.throw(_(
                "{0}: {1} ({2}) is already assigned to Shoe Rack <b>{3}</b>. "
                "One person cannot be in two racks."
            ).format(compartment_label, person_name, person_id, rack_display))

        for old_rack in existing:
            for compartment in release_person_from_rack(old_rack.name, person_id, person_doctype):
                doc.flags.rack_reassignments = (doc.flags.rack_reassignments or []) + [{
                    "person": person_id,
                    "person_name": person_name,
                    "from_rack": old_rack.name,
                    "from_rack_display": old_rack.rack_display_name or old_rack.name,
                    "from_compartment": compartment,
                    "to_compartment": compartment_label,
                }]


def release_person_from_rack(rack_name, person_id, person_doctype):
    """Empty every compartment of `rack_name` currently holding `person_id`.

    Written with db.set_value, not doc.save: the old rack must not re-run validate
    (it would recurse back into this check) and its `modified` stamp should not
    matter for a row the import never mentioned. Status is recomputed here because
    nothing else will do it for that rack.
    """
    slots = COMPARTMENT_FIELDS[person_doctype]

    rack = frappe.db.get_value("Shoe Rack", rack_name, [
        "compartments",
        "compartment_1_employee", "compartment_2_employee",
        "compartment_1_external_personnel", "compartment_2_external_personnel",
        "compartment_1_unidentified", "compartment_2_unidentified",
    ], as_dict=True)

    if not rack:
        return []

    updates = {}
    released = []

    for compartment, (link_field, name_field, gender_field) in slots.items():
        if rack.get(link_field) != person_id:
            continue
        updates[link_field] = None
        # Data fields get "" not None: gender_employee_1 is not_nullable, so a
        # NULL write blows up with IntegrityError 1048.
        if name_field:
            updates[name_field] = ""
        if gender_field:
            updates[gender_field] = ""
        rack[link_field] = None
        released.append(compartment)

    if not updates:
        return []

    has_comp1 = bool(rack.compartment_1_employee or rack.compartment_1_external_personnel
                     or rack.compartment_1_unidentified)
    has_comp2 = bool(rack.compartment_2_employee or rack.compartment_2_external_personnel
                     or rack.compartment_2_unidentified)
    updates["status"] = compute_status(rack.compartments, has_comp1, has_comp2)

    frappe.db.set_value("Shoe Rack", rack_name, updates)

    return released


def get_evicted_occupants(doc):
    """People who sat in THIS rack before the save and are in no compartment after.

    An import that overwrites a compartment silently leaves the previous occupant
    with no rack at all - that person is usually not in the import file, so nothing
    else would ever mention them. Worth a line in the log.
    """
    before = doc.get_doc_before_save()
    if not before:
        return []

    all_fields = [f[0] for slots in COMPARTMENT_FIELDS.values() for f in slots.values()]
    now = {doc.get(f) for f in all_fields if doc.get(f)}

    evicted = []
    for person_doctype, slots in COMPARTMENT_FIELDS.items():
        for link_field, _name_field, _gender_field in slots.values():
            person_id = before.get(link_field)
            if person_id and person_id not in now:
                evicted.append((person_id, person_doctype))

    return evicted


def log_reassignments(doc):
    """Leave an audit trail of everyone this save moved in or pushed out.

    Only in auto-reassign mode: a manual edit needs no explanation, the person
    doing it is looking straight at the form.
    """
    if not is_auto_reassign_mode():
        return

    moves = doc.flags.rack_reassignments or []
    evicted = get_evicted_occupants(doc)
    if not moves and not evicted:
        return

    lines = []

    for person_id, person_doctype in evicted:
        lines.append(_("{0} ({1}) no longer has a compartment in this rack.").format(
            get_person_name(person_id, person_doctype), person_id))

    for m in moves:
        lines.append(_("{0} ({1}) was removed from rack {2} (compartment {3}) and placed in {4} of this rack.").format(
            m["person_name"], m["person"], m["from_rack_display"],
            m["from_compartment"], m["to_compartment"]))

    text = "<br>".join(lines)

    try:
        doc.add_comment("Info", text)
    except Exception:
        # An audit comment must never be the reason an import row fails.
        frappe.log_error(frappe.get_traceback(), "Shoe Rack Reassign Comment Error")

    frappe.msgprint(text, title=_("Moved from another rack"), indicator="orange")

    doc.flags.rack_reassignments = []


def get_rack_occupants(doc_or_row):
    """Return the two people sharing a rack as [{id, name, gender}, ...].

    A rack has no gender of its own: the only rule is that the two people
    sharing a 2-compartment rack should be the same gender. Racks with a
    single compartment are never checked - one person, no pairing.
    """
    d = doc_or_row

    if (d.get("compartments") if isinstance(d, dict) else d.compartments) != "2":
        return []

    def _f(field):
        return d.get(field) if isinstance(d, dict) else d.get(field)

    if _f("user_type") == "Employee":
        doctype, name_field = "Employee", "employee_name"
        ids = [_f("compartment_1_employee"), _f("compartment_2_employee")]
    else:
        doctype, name_field = "External Personnel", "full_name"
        ids = [_f("compartment_1_external_personnel"), _f("compartment_2_external_personnel")]

    if not all(ids):
        return []

    occupants = []
    for idx, person_id in enumerate(ids, start=1):
        info = frappe.db.get_value(doctype, person_id, [name_field, "gender"], as_dict=True) or {}
        occupants.append({
            "compartment": idx,
            "id": person_id,
            "name": info.get(name_field) or person_id,
            "gender": info.get("gender") or "",
        })

    return occupants

def check_mixed_gender(doc):
    """Warn (do not block) when the two people in a rack are different genders.

    This is surfaced as a warning - like the "left employee still in a rack"
    warning - so historical data stays editable and can be cleaned up from the
    dashboard instead of blocking every save.
    """
    occupants = get_rack_occupants(doc)
    if len(occupants) != 2:
        return

    p1, p2 = occupants
    if not (p1["gender"] and p2["gender"]) or p1["gender"] == p2["gender"]:
        return

    frappe.msgprint(
        _("Mixed gender: {0} ({1}) and {2} ({3}) are sharing this rack.").format(
            p1["name"], _(p1["gender"]), p2["name"], _(p2["gender"])
        ),
        title=_("Gender Warning"),
        indicator="orange",
    )


@frappe.whitelist()
def get_gender_mismatch_racks():
    """Return all 2-compartment racks whose two occupants have different genders.

    Mirrors get_left_employees_in_racks: read-only list for a dashboard panel.
    Gender lives on Employee / External Personnel, not on Shoe Rack, so this
    joins both possible person doctypes and compares gender pairwise.
    """
    emp_rows = frappe.db.sql("""
        SELECT sr.name as rack_name, sr.rack_display_name,
               e1.name as c1_id, e1.employee_name as c1_name, e1.gender as c1_gender,
               e2.name as c2_id, e2.employee_name as c2_name, e2.gender as c2_gender
        FROM `tabShoe Rack` sr
        JOIN `tabEmployee` e1 ON e1.name = sr.compartment_1_employee
        JOIN `tabEmployee` e2 ON e2.name = sr.compartment_2_employee
        WHERE sr.compartments = '2'
          AND sr.user_type = 'Employee'
          AND e1.gender IS NOT NULL AND e1.gender != ''
          AND e2.gender IS NOT NULL AND e2.gender != ''
          AND e1.gender != e2.gender
    """, as_dict=True)

    ext_rows = frappe.db.sql("""
        SELECT sr.name as rack_name, sr.rack_display_name,
               p1.name as c1_id, p1.full_name as c1_name, p1.gender as c1_gender,
               p2.name as c2_id, p2.full_name as c2_name, p2.gender as c2_gender
        FROM `tabShoe Rack` sr
        JOIN `tabExternal Personnel` p1 ON p1.name = sr.compartment_1_external_personnel
        JOIN `tabExternal Personnel` p2 ON p2.name = sr.compartment_2_external_personnel
        WHERE sr.compartments = '2'
          AND sr.user_type = 'External'
          AND p1.gender IS NOT NULL AND p1.gender != ''
          AND p2.gender IS NOT NULL AND p2.gender != ''
          AND p1.gender != p2.gender
    """, as_dict=True)

    items = []
    for r in (emp_rows + ext_rows):
        items.append({
            "rack_name": r.rack_name,
            "rack_display_name": r.rack_display_name,
            "compartment_1": {"id": r.c1_id, "name": r.c1_name, "gender": r.c1_gender},
            "compartment_2": {"id": r.c2_id, "name": r.c2_name, "gender": r.c2_gender},
        })

    # Sort by ID: it is zero-padded (RACK-00001), so string order == number order.
    # rack_display_name strips the zeros ("1", "10", "100") and would sort 1,10,100,101...
    items.sort(key=lambda i: i["rack_name"])

    return {
        "success": True,
        "items": items,
        "total": len(items),
    }

@frappe.whitelist()
def get_unidentified_occupant_racks():
    """Danh sách các compartment đang bị đánh dấu Unknown, để review định kỳ."""
    rows = frappe.db.sql("""
        SELECT name as rack_name, rack_display_name,
               compartment_1_unidentified, compartment_2_unidentified
        FROM `tabShoe Rack`
        WHERE compartment_1_unidentified = 1 OR compartment_2_unidentified = 1
    """, as_dict=True)

    items = []
    for r in rows:
        if r.compartment_1_unidentified:
            items.append({"rack_name": r.rack_name, "rack_display_name": r.rack_display_name, "compartment": 1})
        if r.compartment_2_unidentified:
            items.append({"rack_name": r.rack_name, "rack_display_name": r.rack_display_name, "compartment": 2})

    # Sort by ID: it is zero-padded (RACK-00001), so string order == number order.
    # rack_display_name strips the zeros ("1", "10", "100") and would sort 1,10,100,101...
    items.sort(key=lambda i: i["rack_name"])
    return {"success": True, "items": items, "total": len(items)}

def extract_rack_number(name):
    """Extract number from rack name"""
    if not name:
        return None
    
    match = re.search(r'-(\d+)$', name)
    if match:
        num_str = match.group(1).lstrip('0')
        return int(num_str) if num_str else 0
    
    return None

def extract_series_prefix(name):
    """Extract series prefix from name"""
    if not name:
        return None
    
    if 'RACK-' in name:
        return 'RACK'
    elif 'G-' in name:
        return 'G'
    elif 'J-' in name:
        return 'J'
    elif 'A-' in name:
        return 'A'
    
    return None

def on_update(doc, method):
    """Hook: After update/save"""
    update_status(doc)
    generate_display_name(doc)
    doc.db_set('status', doc.status, update_modified=False)
    doc.db_set('rack_display_name', doc.rack_display_name, update_modified=False)
    log_reassignments(doc)

# ================== SERIES MANAGEMENT ==================

@frappe.whitelist()
def get_next_series_number(series_prefix):
    """Get next number correctly"""
    series_map = {
        'RACK': 'RACK-',
        'J': 'J-',
        'G': 'G-',
        'A': 'A-'
    }
    
    naming_series = series_map.get(series_prefix)
    if not naming_series:
        return 1
    
    result = frappe.db.sql("""
        SELECT IFNULL(current, 0) as current
        FROM `tabSeries` 
        WHERE name = %s
    """, (naming_series,), as_dict=True)
    
    if result and result[0].current:
        return int(result[0].current) + 1
    else:
        return 1

@frappe.whitelist()
def bulk_create_racks_by_type(rack_type, quantity, compartments):
    """Bulk create racks - Let ERPNext handle naming"""
    try:
        quantity = int(quantity)
        
        if quantity <= 0 or quantity > 500:
            return {"success": False, "message": _("Quantity must be between 1-500")}
        
        # Determine user_type
        if rack_type in ['Standard Employee', 'Japanese Employee']:
            user_type = 'Employee'
        else:
            user_type = 'External'
        
        # Get naming series
        series_map = {
            'Standard Employee': 'RACK-',
            'Guest': 'G-',
            'Japanese Employee': 'J-',
            'External Personnel': 'A-'
        }
        
        naming_series = series_map.get(rack_type)
        if not naming_series:
            return {"success": False, "message": _("Invalid rack type")}
        
        created = []
        errors = []
        default_status = '0/1' if compartments == '1' else '0/2'
        
        for i in range(quantity):
            try:
                doc = frappe.get_doc({
                    "doctype": "Shoe Rack",
                    "rack_type": rack_type,
                    "naming_series": naming_series,
                    "user_type": user_type,
                    "compartments": compartments,
                    "status": default_status
                })
                
                doc.insert(ignore_permissions=True)
                created.append(doc.name)
                
            except Exception as e:
                error_msg = str(e)
                frappe.log_error(f"Bulk create error #{i+1}: {error_msg}")
                errors.append(f"#{i+1}: {error_msg}")
                
                if len(errors) >= 10:
                    break
        
        frappe.db.commit()
        
        # Build result message
        if created:
            first = parse_rack_name(created[0])
            last = parse_rack_name(created[-1])
            range_display = f"{first['display_name']} - {last['display_name']}"
        else:
            range_display = "None"
        
        result = {
            "success": len(created) > 0,
            "message": _(" Created {0} racks: {1}").format(len(created), range_display),
            "created_count": len(created),
            "error_count": len(errors),
            "created_racks": created
        }
        
        if errors:
            result["errors"] = errors
            result["message"] += f"\n {len(errors)} errors occurred"
        
        return result
    
    except Exception as e:
        frappe.log_error(f"Bulk create failed: {str(e)}")
        return {
            "success": False, 
            "message": _("❌ Error: {0}").format(str(e))
        }

def parse_rack_name(name):
    """Parse rack name to display format"""
    if not name:
        return {'prefix': '', 'number': 0, 'display_name': '0'}
    
    match = re.match(r'^([A-Z]+)-(\d+)$', name)
    if match:
        prefix = match.group(1)
        number = int(match.group(2).lstrip('0') or '0')
        
        if prefix == 'RACK':
            display_name = str(number)
        else:
            display_name = prefix + str(number)
        
        return {'prefix': prefix, 'number': number, 'display_name': display_name}
    
    return {'prefix': '', 'number': 0, 'display_name': name}

@frappe.whitelist()
def auto_reset_empty_series():
    """Auto reset series if no racks exist"""
    series_map = {
        'RACK': 'RACK-',
        'J': 'J-',
        'G': 'G-',
        'A': 'A-'
    }
    
    reset_count = 0
    
    for prefix, naming_series in series_map.items():
        count = frappe.db.count("Shoe Rack", {"name": ["like", f"{prefix}-%"]})
        
        if count == 0:
            try:
                frappe.db.sql(f"DELETE FROM `tabSeries` WHERE name = '{naming_series}'")
                reset_count += 1
            except Exception as e:
                frappe.log_error(f"Error resetting {prefix}: {str(e)}")
    
    frappe.db.commit()
    
    return {
        "success": True,
        "message": _(" Reset {0} empty series").format(reset_count),
        "reset_count": reset_count
    }

@frappe.whitelist()
def force_reset_series(series_prefix):
    """Force reset a specific series"""
    series_map = {
        'RACK': 'RACK-',
        'J': 'J-',
        'G': 'G-',
        'A': 'A-'
    }
    
    if series_prefix not in series_map:
        return {"success": False, "message": _("Invalid series prefix")}
    
    naming_series = series_map[series_prefix]
    count = frappe.db.count("Shoe Rack", {"name": ["like", f"{series_prefix}-%"]})
    
    if count > 0:
        return {
            "success": False,
            "message": _("❌ Cannot reset {0} - {1} racks exist").format(series_prefix, count)
        }
    
    try:
        frappe.db.sql(f"DELETE FROM `tabSeries` WHERE name = '{naming_series}'")
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _(" Reset {0} series to 0").format(series_prefix)
        }
    except Exception as e:
        frappe.log_error(f"Force reset error: {str(e)}")
        return {"success": False, "message": _("Error: {0}").format(str(e))}

@frappe.whitelist()
def clear_all_assignments(series_prefix=None):
    """Remove ALL people (employees + external personnel) from racks, but KEEP the racks.

    This empties the racks so a fresh list can be imported quickly.
    It does NOT delete racks and does NOT touch the naming series counter.

    Args:
        series_prefix: optional 'RACK' | 'J' | 'G' | 'A'. If given, only that
            series is cleared; if omitted, ALL racks are cleared.
    """
    filters = {}
    if series_prefix:
        if series_prefix not in ['RACK', 'J', 'G', 'A']:
            return {"success": False, "message": _("Invalid series prefix")}
        filters = {"name": ["like", f"{series_prefix}-%"]}

    racks = frappe.get_all("Shoe Rack", filters=filters, fields=[
        "name", "compartments",
        "compartment_1_employee", "compartment_1_external_personnel",
        "compartment_2_employee", "compartment_2_external_personnel",
    ])

    cleared_count = 0

    for r in racks:
        has_any = (
            r.compartment_1_employee or r.compartment_1_external_personnel
            or r.compartment_2_employee or r.compartment_2_external_personnel
        )
        if not has_any:
            continue

        empty_status = "0/1" if r.compartments == "1" else "0/2"

        frappe.db.set_value("Shoe Rack", r.name, {
            "compartment_1_employee": None,
            "compartment_1_external_personnel": None,
            "compartment_1_employee_name": None,
            "compartment_2_employee": None,
            "compartment_2_external_personnel": None,
            "compartment_2_employee_name": None,
            "status": empty_status,
        }, update_modified=True)

        cleared_count += 1

    frappe.db.commit()

    scope = series_prefix if series_prefix else _("all")
    return {
        "success": True,
        "message": _("Cleared people from {0} racks ({1}). Racks are now empty.").format(
            cleared_count, scope
        ),
        "cleared_count": cleared_count,
    }

@frappe.whitelist()
def clear_unidentified_flags(rack_type=None, target="both", dry_run=0):
    """Bỏ tick 'Chưa xác định (Unknown)' hàng loạt rồi tính lại status.

    Cần thiết vì field compartment_2_unidentified từng có default = 1: mọi tủ tạo
    mới đều bị tick sẵn ngăn 2, khiến tủ trống bị tính là đã có người (0/2 -> 1/2,
    1/2 -> 2/2) và Suggest Slots bỏ qua chúng.

    Args:
        rack_type: lọc theo Rack Type. Bỏ trống = tất cả các loại tủ.
        target: 'both' | '1' | '2' - gỡ cờ Unknown của ngăn nào.
        dry_run: 1 = chỉ đếm và trả về preview, không ghi gì vào DB.
    """
    dry_run = int(dry_run or 0)

    if target not in ("both", "1", "2"):
        return {"success": False, "message": _("Invalid target")}

    clear_c1 = target in ("both", "1")
    clear_c2 = target in ("both", "2")

    filters = {}
    if rack_type:
        filters["rack_type"] = rack_type

    or_filters = {}
    if clear_c1:
        or_filters["compartment_1_unidentified"] = 1
    if clear_c2:
        or_filters["compartment_2_unidentified"] = 1

    racks = frappe.get_all("Shoe Rack",
        filters=filters,
        or_filters=or_filters,
        fields=["name", "rack_display_name", "compartments", "status",
                "compartment_1_employee", "compartment_1_external_personnel",
                "compartment_2_employee", "compartment_2_external_personnel",
                "compartment_1_unidentified", "compartment_2_unidentified"],
        limit_page_length=0,
    )

    c1_cleared = 0
    c2_cleared = 0
    status_changed = 0
    samples = []

    for r in racks:
        updates = {}

        if clear_c1 and r.compartment_1_unidentified:
            updates["compartment_1_unidentified"] = 0
            c1_cleared += 1
        if clear_c2 and r.compartment_2_unidentified:
            updates["compartment_2_unidentified"] = 0
            c2_cleared += 1

        if not updates:
            continue

        # Cờ nào KHÔNG nằm trong phạm vi gỡ thì vẫn tiếp tục chiếm chỗ.
        has_comp1 = bool(r.compartment_1_employee or r.compartment_1_external_personnel
                         or (r.compartment_1_unidentified and not clear_c1))
        has_comp2 = bool(r.compartment_2_employee or r.compartment_2_external_personnel
                         or (r.compartment_2_unidentified and not clear_c2))

        new_status = compute_status(r.compartments, has_comp1, has_comp2)
        if new_status != r.status:
            updates["status"] = new_status
            status_changed += 1
            if len(samples) < 15:
                samples.append({
                    "rack": r.rack_display_name or r.name,
                    "old_status": r.status,
                    "new_status": new_status,
                })

        if not dry_run:
            frappe.db.set_value("Shoe Rack", r.name, updates)

    if not dry_run:
        frappe.db.commit()

    racks_affected = len(racks)
    scope = rack_type or _("all rack types")

    return {
        "success": True,
        "dry_run": dry_run,
        "racks_affected": racks_affected,
        "c1_cleared": c1_cleared,
        "c2_cleared": c2_cleared,
        "status_changed": status_changed,
        "samples": samples,
        "message": _("Cleared Unknown flag on {0} rack(s) ({1}); {2} status recalculated.").format(
            racks_affected, scope, status_changed
        ),
    }


@frappe.whitelist()
def bulk_delete_and_reset(series_prefix):
    """Delete all racks of a series and reset to 0"""
    if series_prefix not in ['RACK', 'J', 'G', 'A']:
        return {"success": False, "message": _("Invalid series prefix")}
    
    racks = frappe.get_all("Shoe Rack",
        filters={"name": ["like", f"{series_prefix}-%"]},
        fields=["name"]
    )
    
    if not racks:
        return {
            "success": False,
            "message": _("No racks found for series {0}").format(series_prefix)
        }
    
    deleted_count = 0
    errors = []
    
    for rack in racks:
        try:
            frappe.delete_doc("Shoe Rack", rack.name, force=True, ignore_permissions=True)
            deleted_count += 1
        except Exception as e:
            errors.append(f"{rack.name}: {str(e)}")
    
    frappe.db.commit()
    
    # Reset series
    series_map = {
        'RACK': 'RACK-',
        'J': 'J-',
        'G': 'G-',
        'A': 'A-'
    }
    
    naming_series = series_map[series_prefix]
    
    try:
        frappe.db.sql(f"DELETE FROM `tabSeries` WHERE name = '{naming_series}'")
        frappe.db.commit()
    except Exception as e:
        errors.append(f"Reset error: {str(e)}")
    
    result = {
        "success": True,
        "message": _(" Deleted {0} racks and reset {1} series").format(
            deleted_count, series_prefix
        ),
        "deleted_count": deleted_count,
        "series_reset": True
    }
    
    if errors:
        result["errors"] = errors
    
    return result

@frappe.whitelist()
def check_series_consistency():
    """Check series consistency"""
    series_map = {
        'RACK': 'RACK-',
        'J': 'J-',
        'G': 'G-',
        'A': 'A-'
    }
    
    result = {}
    
    for prefix, naming_series in series_map.items():
        rack_count = frappe.db.count("Shoe Rack", {"name": ["like", f"{prefix}-%"]})
        
        last_rack = frappe.db.get_all("Shoe Rack",
            filters={"name": ["like", f"{prefix}-%"]},
            fields=["name"],
            order_by="name desc",
            limit=1
        )
        
        last_number = 0
        if last_rack:
            match = re.search(r'-(\d+)$', last_rack[0].name)
            if match:
                last_number = int(match.group(1))
        
        series_result = frappe.db.sql("""
            SELECT IFNULL(current, 0) as current
            FROM `tabSeries` 
            WHERE name = %s
        """, (naming_series,), as_dict=True)
        
        series_current = int(series_result[0].current) if series_result and series_result[0].current else 0
        
        is_consistent = (rack_count == 0 and series_current == 0) or \
                       (rack_count > 0 and last_number == series_current)
        
        result[prefix] = {
            "naming_series": naming_series,
            "rack_count": rack_count,
            "last_number": last_number,
            "series_current": series_current,
            "is_consistent": is_consistent,
            "needs_reset": rack_count == 0 and series_current > 0
        }
    
    return result

@frappe.whitelist()
def fix_all_inconsistencies():
    """Auto fix all inconsistent series"""
    issues = check_series_consistency()
    
    fixed_count = 0
    
    for prefix, info in issues.items():
        if info["needs_reset"]:
            result = force_reset_series(prefix)
            if result["success"]:
                fixed_count += 1
    
    return {
        "success": True,
        "message": _(" Fixed {0} series").format(fixed_count),
        "fixed_count": fixed_count,
        "details": issues
    }

@frappe.whitelist()
def fix_all_rack_status():
    """Fix status for all shoe racks"""
    
    try:
        racks = frappe.get_all("Shoe Rack",
            fields=["name", "compartments",
                   "compartment_1_employee", "compartment_2_employee",
                   "compartment_1_external_personnel", "compartment_2_external_personnel",
                   "compartment_1_unidentified", "compartment_2_unidentified",
                   "status"]
        )

        updated = 0
        errors = []

        for rack in racks:
            try:
                # Phải tính y hệt update_status (kể cả cờ Unknown), nếu không mỗi
                # lần chạy "Fix All Status" sẽ ghi đè ngược lại status do save sinh ra.
                has_comp1 = bool(rack.compartment_1_employee or rack.compartment_1_external_personnel
                                 or rack.compartment_1_unidentified)
                has_comp2 = bool(rack.compartment_2_employee or rack.compartment_2_external_personnel
                                 or rack.compartment_2_unidentified)

                new_status = compute_status(rack.compartments, has_comp1, has_comp2)

                if rack.status != new_status:
                    frappe.db.set_value("Shoe Rack", rack.name, "status", new_status)
                    updated += 1
            
            except Exception as e:
                errors.append(f"{rack.name}: {str(e)}")
        
        frappe.db.commit()
        
        result = {
            "success": True,
            "message": _(" Updated {0}/{1} racks").format(updated, len(racks)),
            "updated": updated,
            "total": len(racks)
        }
        
        if errors:
            result["errors"] = errors
        
        return result
    
    except Exception as e:
        frappe.log_error(f"Fix status error: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        }

@frappe.whitelist()
def regenerate_all_display_names():
    """
    ✨ Regenerate display names for all existing racks
    Called from List View menu action
    """
    try:
        racks = frappe.get_all("Shoe Rack", fields=["name"])
        
        updated = 0
        
        for rack in racks:
            doc = frappe.get_doc("Shoe Rack", rack.name)
            generate_display_name(doc)
            doc.db_set('rack_display_name', doc.rack_display_name, update_modified=False)
            updated += 1
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": _(" Updated {0} display names").format(updated),
            "updated": updated
        }
    
    except Exception as e:
        frappe.log_error(f"Regenerate display names error: {str(e)}")
        return {
            "success": False,
            "message": str(e)
        }

# ================== OTHER FUNCTIONS ==================

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def external_personnel_query(doctype, txt, searchfield, start, page_len, filters):
    """
    Custom query for External Personnel Link field
    Display: Full Name - Company Name
    Search by: name, full_name, company_name, phone
    """
    
    return frappe.db.sql("""
        SELECT 
            name,
            CONCAT(
                IFNULL(full_name, ''), 
                CASE 
                    WHEN company_name IS NOT NULL AND company_name != '' 
                    THEN CONCAT(' - ', company_name)
                    ELSE ''
                END
            ) as label
        FROM `tabExternal Personnel`
        WHERE 
            (name LIKE %(txt)s
            OR full_name LIKE %(txt)s  
            OR company_name LIKE %(txt)s
            OR phone LIKE %(txt)s)
        ORDER BY 
            CASE 
                WHEN full_name LIKE %(txt)s THEN 0
                WHEN company_name LIKE %(txt)s THEN 1
                WHEN name LIKE %(txt)s THEN 2
                ELSE 3
            END,
            full_name
        LIMIT %(start)s, %(page_len)s
    """, {
        'txt': f"%{txt}%",
        'start': start,
        'page_len': page_len
    })

@frappe.whitelist()
def get_available_racks(user_type=None, compartments=None, series_prefix=None):
    """Get available empty racks"""
    filters = {}
    
    if user_type:
        filters["user_type"] = user_type
    if compartments:
        filters["compartments"] = compartments
    
    racks = frappe.get_all("Shoe Rack", 
                          filters=filters,
                          fields=["name", "rack_display_name", "compartments", "user_type", "rack_type",
                                 "status", 
                                 "compartment_1_employee", "compartment_2_employee",
                                 "compartment_1_external_personnel", "compartment_2_external_personnel"],
                          order_by="name asc")
    
    available_racks = []
    for rack in racks:
        if series_prefix:
            prefix = extract_series_prefix(rack.name)
            if prefix != series_prefix:
                continue
        
        if rack.status in ["0/1", "0/2", "1/2"]:
            rack.rack_number = extract_rack_number(rack.name)
            rack.series_prefix = extract_series_prefix(rack.name)
            available_racks.append(rack)
    
    return available_racks
@frappe.whitelist()
def get_empty_racks_in_range(start_number, end_number, series_prefix='RACK'):
    """
    Get empty racks in range - FIXED to support multiple padding formats
    Now handles: RACK-21, RACK-0021, RACK-00021
    """
    start = int(start_number)
    end = int(end_number)
    
    if start > end:
        return {"total": 0, "racks": []}
    
    # 🔧 FIX: Build possible rack names - try multiple padding formats
    names = []
    for num in range(start, end + 1):
        names.append(f"{series_prefix}-{num}")  # RACK-21
        names.append(f"{series_prefix}-{str(num).zfill(4)}")  # RACK-0021
        names.append(f"{series_prefix}-{str(num).zfill(5)}")  # RACK-00021
    
    # Remove duplicates
    names = list(set(names))
    
    # 📊 Debug: Print what we're searching for
    # frappe.log_error(f"Searching for racks: {names[:10]}...", "Bulk Edit Debug")
    
    racks = frappe.get_all("Shoe Rack",
        filters={
            "name": ["in", names],
            "status": ["in", ["0/1", "0/2"]]
        },
        fields=["name", "rack_display_name", "status", "user_type", "rack_type"],
        order_by="name asc"
    )
    
    for rack in racks:
        info = parse_rack_name(rack.name)
        rack.rack_number = info['number']
        rack.display_name = info['display_name']

    return {
        "total": len(racks),
        "racks": racks
    }
    
@frappe.whitelist()
def bulk_edit_empty_racks(start_number, end_number, compartments=None, series_prefix='RACK'):
    """
    Bulk edit empty racks in range - ALREADY FIXED 
    Handles multiple padding formats correctly
    """
    start = int(start_number)
    end = int(end_number)
    
    if start > end:
        return {"success": False, "message": _("Invalid range")}
    
    # Build possible rack names - try both padded and non-padded
    names = []
    for num in range(start, end + 1):
        names.append(f"{series_prefix}-{num}")  # RACK-21
        names.append(f"{series_prefix}-{str(num).zfill(4)}")  # RACK-0021
        names.append(f"{series_prefix}-{str(num).zfill(5)}")  # RACK-00021
    
    # Remove duplicates
    names = list(set(names))
    
    # Get all racks in range (not just empty ones, to show which are occupied)
    all_racks = frappe.get_all("Shoe Rack",
        filters={"name": ["in", names]},
        fields=["name", "status", "compartments",
                "compartment_1_employee", "compartment_2_employee",
                "compartment_1_external_personnel", "compartment_2_external_personnel"]
    )
    
    if not all_racks:
        return {
            "success": False,
            "message": _("No racks found in range {0}-{1} (series: {2})").format(start, end, series_prefix),
            "updated": 0,
            "skipped": 0,
            "occupied": []
        }
    
    updated_count = 0
    skipped_count = 0
    occupied_racks = []
    
    for rack in all_racks:
        try:
            # Check if rack has any personnel assigned
            has_personnel = (
                rack.compartment_1_employee or 
                rack.compartment_2_employee or
                rack.compartment_1_external_personnel or 
                rack.compartment_2_external_personnel
            )
            
            if has_personnel:
                occupied_racks.append(rack.name)
                skipped_count += 1
                continue
            
            # Rack is empty, can update
            doc = frappe.get_doc("Shoe Rack", rack.name)
            
            # Update compartments if provided
            if compartments:
                doc.compartments = compartments
                # If changing to 1 compartment, clear compartment 2
                if compartments == "1":
                    doc.compartment_2_employee = None
                    doc.compartment_2_external_personnel = None
            
            doc.save(ignore_permissions=True)
            updated_count += 1
            
        except Exception as e:
            frappe.log_error(f"Bulk edit error for {rack.name}: {str(e)}")
            skipped_count += 1
    
    frappe.db.commit()
    
    result = {
        "success": True,
        "message": _(" Updated {0} racks, skipped {1}").format(updated_count, skipped_count),
        "updated": updated_count,
        "skipped": skipped_count,
        "total_found": len(all_racks)
    }
    
    if occupied_racks:
        result["occupied"] = occupied_racks
        result["message"] += f"\n {len(occupied_racks)} racks are occupied and cannot be edited"

    return result

# ================== SYNC TO EMPLOYEE ==================

@frappe.whitelist()
def sync_racks_to_employees(rack_names=None, clear_orphans=1, dry_run=0):
    """
    Push rack assignments into Employee.custom_shoe_rack.

    Shoe Rack is the source of truth: for every rack, whoever sits in
    compartment_1_employee / compartment_2_employee gets that rack written
    onto their Employee record. Employees still pointing at a rack that no
    longer holds them are cleared (unless clear_orphans is off).

    rack_names: list of Shoe Rack names to limit the sync to. Empty/None
    syncs every Employee rack. When scoped, orphan clearing only touches
    employees currently pointing at one of the selected racks.
    """
    clear_orphans = int(clear_orphans)
    dry_run = int(dry_run)

    if isinstance(rack_names, str):
        rack_names = frappe.parse_json(rack_names)
    rack_names = [r for r in (rack_names or []) if r]

    filters = {"user_type": "Employee"}
    if rack_names:
        filters["name"] = ["in", rack_names]

    racks = frappe.get_all("Shoe Rack",
        filters=filters,
        fields=["name", "rack_display_name",
                "compartment_1_employee", "compartment_2_employee"]
    )

    # employee -> rack (from racks), plus employees sitting in more than one rack
    expected = {}
    conflicts = {}

    for rack in racks:
        for emp in (rack.compartment_1_employee, rack.compartment_2_employee):
            if not emp:
                continue
            if emp in expected and expected[emp] != rack.name:
                conflicts.setdefault(emp, [expected[emp]]).append(rack.name)
                continue
            expected[emp] = rack.name

    # Current state on Employee side.
    # Scoped run: only employees involved in the selected racks - either they
    # sit in one now, or they still point at one. Everyone else is untouched.
    if rack_names:
        current = {
            e.name: e.custom_shoe_rack
            for e in frappe.get_all("Employee",
                or_filters={
                    "custom_shoe_rack": ["in", rack_names],
                    "name": ["in", list(expected.keys()) or [""]],
                },
                fields=["name", "custom_shoe_rack"])
        }
        orphan_pool = {
            emp: rack for emp, rack in current.items() if rack in rack_names
        }
    else:
        current = {
            e.name: e.custom_shoe_rack
            for e in frappe.get_all("Employee",
                filters={"custom_shoe_rack": ["is", "set"]},
                fields=["name", "custom_shoe_rack"])
        }
        orphan_pool = current

    updated, cleared, missing = [], [], []

    for emp, rack_name in expected.items():
        if current.get(emp) == rack_name:
            continue
        if not frappe.db.exists("Employee", emp):
            missing.append(emp)
            continue
        if not dry_run:
            frappe.db.set_value("Employee", emp, "custom_shoe_rack", rack_name,
                                update_modified=False)
        updated.append({"employee": emp, "rack": rack_name, "old": current.get(emp)})

    if clear_orphans:
        for emp, rack_name in orphan_pool.items():
            if emp in expected or emp in conflicts:
                continue
            if not dry_run:
                frappe.db.set_value("Employee", emp, "custom_shoe_rack", None,
                                    update_modified=False)
            cleared.append({"employee": emp, "old": rack_name})

    if not dry_run:
        frappe.db.commit()

    return {
        "success": True,
        "message": _("Synced {0} employees, cleared {1}").format(len(updated), len(cleared)),
        "updated": updated,
        "cleared": cleared,
        "conflicts": [{"employee": e, "racks": r} for e, r in conflicts.items()],
        "missing": missing,
        "total_racks": len(racks),
        "dry_run": dry_run,
    }

