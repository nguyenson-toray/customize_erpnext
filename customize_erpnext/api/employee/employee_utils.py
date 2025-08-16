import frappe
import re
from frappe import _

@frappe.whitelist()
def get_next_employee_code():
    """Generate next employee code in TIQN-XXXX format"""
    # Use SQL to get the highest employee number with proper numeric ordering
    result = frappe.db.sql("""
        SELECT employee
        FROM tabEmployee 
        WHERE employee LIKE 'TIQN-%'
        ORDER BY CAST(SUBSTRING(employee, 6) AS UNSIGNED) DESC
        LIMIT 1
    """, as_dict=True)
    
    if not result:
        return "TIQN-0001"
    
    highest_employee = result[0].employee
    
    # Extract number from the highest employee code
    match = re.match(r'TIQN-(\d+)', highest_employee)
    if match:
        current_num = int(match.group(1))
        next_num = current_num + 1
        next_code = f"TIQN-{next_num:04d}"
        return next_code
    
    # Fallback if pattern doesn't match
    return "TIQN-0001"

@frappe.whitelist()
def get_next_attendance_device_id():
    """Generate next attendance_device_id"""
    # Get maximum attendance_device_id
    result = frappe.db.sql("""
        SELECT MAX(CAST(attendance_device_id AS UNSIGNED)) as max_id 
        FROM tabEmployee 
        WHERE attendance_device_id IS NOT NULL 
        AND attendance_device_id != ''
        AND attendance_device_id REGEXP '^[0-9]+$'
    """, as_dict=True)
    
    max_id = result[0].max_id if result and result[0].max_id else 0
    return str(max_id + 1)

@frappe.whitelist()
def set_series(prefix, current_highest_id):
    """Set naming series to prevent duplicate auto-generated IDs"""
    try:
        # Always update the series value using direct SQL
        frappe.db.sql("""
            UPDATE tabSeries SET current = %s WHERE name = %s
        """, (current_highest_id, prefix))
        frappe.db.commit()
        return {"status": "success", "message": f"Series {prefix} updated to {current_highest_id}"}
        
    except Exception as e:
        frappe.log_error(f"Error updating series {prefix}: {str(e)}")
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def check_duplicate_employee(employee_code, current_doc_name=None):
    """Check if employee code already exists"""
    filters = {"employee": employee_code}
    if current_doc_name:
        filters["name"] = ["!=", current_doc_name]
    
    existing = frappe.db.exists("Employee", filters)
    return {"exists": bool(existing), "employee_code": employee_code}

@frappe.whitelist()
def check_duplicate_attendance_device_id(attendance_device_id, current_doc_name=None):
    """Check if attendance device ID already exists"""
    if not attendance_device_id:
        return {"exists": False, "attendance_device_id": attendance_device_id}
    
    filters = {"attendance_device_id": attendance_device_id}
    if current_doc_name:
        filters["name"] = ["!=", current_doc_name]
    
    existing = frappe.db.exists("Employee", filters)
    return {"exists": bool(existing), "attendance_device_id": attendance_device_id}




