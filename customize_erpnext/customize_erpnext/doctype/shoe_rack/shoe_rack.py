# shoe_rack.py - COMPLETE VERSION

import frappe
from frappe import _
from frappe.model.document import Document
import re

class ShoeRack(Document):
    pass

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
    
    # Validate gender match (only for Employee racks)
    validate_all_gender_matches(doc)
    
    # Validate compartments
    if doc.compartments == "1":
        doc.compartment_2_employee = None
        doc.compartment_2_external_personnel = None
    
    # Auto update status
    update_status(doc)
    
    # ✨ Auto-generate display name
    generate_display_name(doc)

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

def validate_all_gender_matches(doc):
    """Validate gender for compartments - Only for Employee racks"""
    
    # Skip validation for External racks
    if doc.naming_series != "RACK-":
        return
    
    # Only validate for Employee racks
    if doc.naming_series == "RACK-":
        if doc.compartment_1_employee:
            validate_gender_match(doc, doc.compartment_1_employee, "Employee", "Compartment 1")
        
        if doc.compartment_2_employee:
            validate_gender_match(doc, doc.compartment_2_employee, "Employee", "Compartment 2")

def validate_gender_match(doc, personnel_id, personnel_doctype, compartment_name):
    """Validate gender matches between personnel and rack"""
    
    personnel_gender = frappe.db.get_value(personnel_doctype, personnel_id, "gender")
    
    if personnel_gender and personnel_gender != doc.gender:
        personnel_name = frappe.db.get_value("Employee", personnel_id, "employee_name")
        
        frappe.throw(_(
            "{0}: {1} is {2}, but this rack is for {3}. "
            "Please select a {4} rack or choose a different person."
        ).format(compartment_name, personnel_name, personnel_gender, doc.gender, personnel_gender))

def update_status(doc):
    """Auto update status"""
    has_comp1 = 1 if (doc.compartment_1_employee or doc.compartment_1_external_personnel) else 0
    has_comp2 = 1 if (doc.compartment_2_employee or doc.compartment_2_external_personnel) else 0
    
    if doc.compartments == "1":
        doc.status = "1/1" if has_comp1 else "0/1"
    else:
        total_used = has_comp1 + has_comp2
        if total_used == 0:
            doc.status = "0/2"
        elif total_used == 1:
            doc.status = "1/2"
        else:
            doc.status = "2/2"

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
def bulk_create_racks_by_type(rack_type, quantity, compartments, gender):
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
                    "gender": gender,
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
                   "status"]
        )
        
        updated = 0
        errors = []
        
        for rack in racks:
            try:
                has_comp1 = 1 if (rack.compartment_1_employee or rack.compartment_1_external_personnel) else 0
                has_comp2 = 1 if (rack.compartment_2_employee or rack.compartment_2_external_personnel) else 0
                
                if rack.compartments == "1":
                    new_status = "1/1" if has_comp1 else "0/1"
                else:
                    total_used = has_comp1 + has_comp2
                    if total_used == 0:
                        new_status = "0/2"
                    elif total_used == 1:
                        new_status = "1/2"
                    else:
                        new_status = "2/2"
                
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
def get_available_racks(user_type=None, gender=None, compartments=None, series_prefix=None):
    """Get available empty racks"""
    filters = {}
    
    if user_type:
        filters["user_type"] = user_type
    if gender:
        filters["gender"] = gender
    if compartments:
        filters["compartments"] = compartments
    
    racks = frappe.get_all("Shoe Rack", 
                          filters=filters,
                          fields=["name", "rack_display_name", "compartments", "user_type", "rack_type",
                                 "gender", "status", 
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
        fields=["name", "rack_display_name", "status", "gender", "user_type", "rack_type"],
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
def bulk_edit_empty_racks(start_number, end_number, gender=None, compartments=None, series_prefix='RACK'):
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
            
            # Update gender if provided
            if gender:
                doc.gender = gender
            
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

