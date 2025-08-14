import frappe
import re
from frappe import _

@frappe.whitelist()
def get_next_employee_code():
    """Generate next employee code in TIQN-XXXX format"""
    print("=== DEBUG: Starting get_next_employee_code ===")
    
    # Use SQL to get the highest employee number with proper numeric ordering
    result = frappe.db.sql("""
        SELECT employee
        FROM tabEmployee 
        WHERE employee LIKE 'TIQN-%'
        ORDER BY CAST(SUBSTRING(employee, 6) AS UNSIGNED) DESC
        LIMIT 1
    """, as_dict=True)
    
    print(f"DEBUG: SQL result: {result}")
    
    if not result:
        print("DEBUG: No existing TIQN employees found, returning TIQN-0001")
        return "TIQN-0001"
    
    highest_employee = result[0].employee
    print(f"DEBUG: Highest employee found: {highest_employee}")
    
    # Extract number from the highest employee code
    match = re.match(r'TIQN-(\d+)', highest_employee)
    if match:
        current_num = int(match.group(1))
        next_num = current_num + 1
        next_code = f"TIQN-{next_num:04d}"
        print(f"DEBUG: Current number: {current_num}, Next number: {next_num}, Next code: {next_code}")
        return next_code
    
    # Fallback if pattern doesn't match
    print(f"DEBUG: Pattern didn't match for {highest_employee}, returning fallback TIQN-0001")
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
def create_employees_bulk(employees_data):
    """
    Create multiple employees from formatted string data
    Format: employee_name; gender; date_of_birth; [date_of_joining]
    """
    import datetime
    from datetime import datetime as dt
    
    if not employees_data:
        frappe.throw(_("No employee data provided"))
    
    lines = employees_data.strip().split('\n')
    created_employees = []
    errors = []
    
    # Get the starting employee number and attendance device ID
    employee_result = frappe.db.sql("""
        SELECT employee
        FROM tabEmployee 
        WHERE employee LIKE 'TIQN-%'
        ORDER BY CAST(SUBSTRING(employee, 6) AS UNSIGNED) DESC
        LIMIT 1
    """, as_dict=True)
    
    attendance_result = frappe.db.sql("""
        SELECT MAX(CAST(attendance_device_id AS UNSIGNED)) as max_id 
        FROM tabEmployee 
        WHERE attendance_device_id IS NOT NULL 
        AND attendance_device_id != ''
        AND attendance_device_id REGEXP '^[0-9]+$'
    """, as_dict=True)
    
    if employee_result:
        match = re.match(r'TIQN-(\d+)', employee_result[0].employee)
        next_employee_num = int(match.group(1)) + 1 if match else 1
    else:
        next_employee_num = 1
        
    next_attendance_device_id = attendance_result[0].max_id + 1 if attendance_result and attendance_result[0].max_id else 1
        
    print(f"DEBUG: Starting bulk creation with employee number: {next_employee_num}, attendance device ID: {next_attendance_device_id}")
    
    for line_num, line in enumerate(lines, 1):
        if not line.strip():
            continue
            
        try:
            parts = [p.strip() for p in line.split(';')]
            
            if len(parts) < 3:
                errors.append(_("Line {0}: Invalid format. Expected: name; gender; date_of_birth; [date_of_joining]").format(line_num))
                continue
            
            employee_name = parts[0]
            gender = parts[1]
            date_of_birth = parts[2]
            date_of_joining = parts[3] if len(parts) > 3 and parts[3] else None
            
            # Validate gender
            if gender.lower() not in ['male', 'female', 'other']:
                errors.append(_("Line {0}: Invalid gender '{1}'. Use: Male, Female, or Other").format(line_num, gender))
                continue
            
            # Parse dates
            try:
                dob = dt.strptime(date_of_birth, '%d/%m/%Y').date()
                if date_of_joining:
                    doj = dt.strptime(date_of_joining, '%d/%m/%Y').date()
                else:
                    doj = datetime.date.today()
            except ValueError as e:
                errors.append(_("Line {0}: Invalid date format. Use dd/mm/yyyy").format(line_num))
                continue
            
            # Generate sequential employee code and attendance device ID
            employee_code = f"TIQN-{next_employee_num:04d}"
            
            # Check if employee code already exists
            while frappe.db.exists("Employee", {"employee": employee_code}):
                print(f"DEBUG: Employee {employee_code} already exists, incrementing...")
                next_employee_num += 1
                employee_code = f"TIQN-{next_employee_num:04d}"
            
            # Use sequential attendance device ID for bulk creation
            current_attendance_device_id = str(next_attendance_device_id)
            next_employee_num += 1  # Increment for next employee
            next_attendance_device_id += 1  # Increment for next attendance device
            print(f"DEBUG: Generated for line {line_num}: employee_code={employee_code}, attendance_device_id={current_attendance_device_id}")
            
            # Split employee name into first and last name
            name_parts = employee_name.split()
            first_name = name_parts[0] if name_parts else employee_name
            last_name = ' '.join(name_parts[1:]) if len(name_parts) > 1 else ""
            
            # Create employee - the custom Employee class will handle naming
            emp = frappe.new_doc("Employee")
            emp.employee = employee_code  # This will be used by our custom autoname method
            emp.employee_name = employee_name
            emp.first_name = first_name
            emp.last_name = last_name
            emp.gender = gender.title()
            emp.date_of_birth = dob
            emp.date_of_joining = doj
            emp.attendance_device_id = current_attendance_device_id  # Set sequential ID for bulk creation
            emp.status = "Active"
            
            print(f"DEBUG: Creating employee with employee='{emp.employee}'")
            emp.insert()
            print(f"DEBUG: After insert - name='{emp.name}', employee='{emp.employee}'")
            created_employees.append({
                "employee": employee_code,
                "employee_name": employee_name,
                "attendance_device_id": current_attendance_device_id
            })
            
        except Exception as e:
            errors.append(_("Line {0}: {1}").format(line_num, str(e)))
    
    return {
        "success": len(created_employees),
        "created_employees": created_employees,
        "errors": errors
    }

def auto_set_employee_naming(doc, method=None):
    """Handle employee naming before ERPNext's naming series kicks in"""
    print(f"=== DEBUG: auto_set_employee_naming called ===")
    print(f"DEBUG: Current doc.employee: {doc.employee}")
    
    # Set employee code if not set or not in TIQN format
    if not doc.employee or not doc.employee.startswith('TIQN-'):
        employee_code = get_next_employee_code()
        doc.employee = employee_code
        print(f"DEBUG: Set employee code to '{employee_code}'")
    
    # Override the name to be the same as employee code
    doc.name = doc.employee
    print(f"DEBUG: Set document name to '{doc.name}'")

def auto_set_employee_fields(doc, method=None):
    """Auto-set attendance_device_id and other fields before insert"""
    print(f"=== DEBUG: auto_set_employee_fields called ===")
    print(f"DEBUG: Current doc.employee: {doc.employee}")
    print(f"DEBUG: Current doc.name: {doc.name}")
    print(f"DEBUG: Current doc.attendance_device_id: {doc.attendance_device_id}")
    
    # Set attendance device ID if not set
    if not doc.attendance_device_id:
        doc.attendance_device_id = get_next_attendance_device_id()
        print(f"DEBUG: Set attendance_device_id to '{doc.attendance_device_id}'")

@frappe.whitelist()
def get_employee_creation_preview():
    """Get preview info for employee creation including next codes"""
    highest_info = get_highest_employee_info()
    next_employee_code = get_next_employee_code()
    next_attendance_device_id = get_next_attendance_device_id()
    
    print(f"DEBUG: get_employee_creation_preview results:")
    print(f"  - next_employee_code: {next_employee_code}")
    print(f"  - next_attendance_device_id: {next_attendance_device_id}")
    
    return {
        "highest_employee": highest_info,
        "next_employee_code": next_employee_code,
        "next_attendance_device_id": next_attendance_device_id
    }

@frappe.whitelist()
def get_highest_employee_info():
    """Get information about the highest existing employee"""
    # Get highest employee code using proper numeric ordering
    employee = frappe.db.sql("""
        SELECT employee, employee_name, attendance_device_id
        FROM tabEmployee 
        WHERE employee LIKE 'TIQN-%'
        ORDER BY CAST(SUBSTRING(employee, 6) AS UNSIGNED) DESC
        LIMIT 1
    """, as_dict=True)
    
    if employee:
        return employee[0]
    
    return {
        "employee": _("No existing employees"),
        "employee_name": "",
        "attendance_device_id": ""
    }

@frappe.whitelist()
def check_employee_code_formats():
    """Check all employee codes for format issues"""
    print("=== CHECKING EMPLOYEE CODE FORMATS ===")
    
    # Get all TIQN employees
    all_tiqn_employees = frappe.db.sql("""
        SELECT employee, name, employee_name
        FROM tabEmployee 
        WHERE employee LIKE 'TIQN-%'
        ORDER BY CAST(SUBSTRING(employee, 6) AS UNSIGNED) DESC
        LIMIT 20
    """, as_dict=True)
    
    print(f"Found {len(all_tiqn_employees)} TIQN employees:")
    
    correct_format = []
    wrong_format = []
    
    for emp in all_tiqn_employees:
        employee_code = emp.employee
        # Check if format is TIQN-XXXX (exactly 4 digits)
        if re.match(r'^TIQN-\d{4}$', employee_code):
            correct_format.append(emp)
            print(f"✅ CORRECT: {employee_code} - {emp.employee_name}")
        else:
            wrong_format.append(emp)
            print(f"❌ WRONG: {employee_code} - {emp.employee_name}")
    
    return {
        "total_employees": len(all_tiqn_employees),
        "correct_format": len(correct_format),
        "wrong_format": len(wrong_format),
        "wrong_format_employees": wrong_format,
        "correct_format_employees": correct_format
    }

@frappe.whitelist()
def fix_employee_code_formats():
    """Fix employee codes that don't follow TIQN-XXXX format"""
    print("=== FIXING EMPLOYEE CODE FORMATS ===")
    
    # Get employees with wrong format
    wrong_employees = frappe.db.sql("""
        SELECT employee, name, employee_name
        FROM tabEmployee 
        WHERE employee LIKE 'TIQN-%'
        AND employee NOT REGEXP '^TIQN-[0-9]{4}$'
        ORDER BY employee
    """, as_dict=True)
    
    if not wrong_employees:
        return {"message": "No employees found with wrong format", "fixed": 0}
    
    print(f"Found {len(wrong_employees)} employees with wrong format")
    
    # Get the current highest correct employee number
    correct_highest = frappe.db.sql("""
        SELECT employee
        FROM tabEmployee 
        WHERE employee REGEXP '^TIQN-[0-9]{4}$'
        ORDER BY CAST(SUBSTRING(employee, 6) AS UNSIGNED) DESC
        LIMIT 1
    """, as_dict=True)
    
    if correct_highest:
        match = re.match(r'TIQN-(\d+)', correct_highest[0].employee)
        next_num = int(match.group(1)) + 1 if match else 1
    else:
        next_num = 1
    
    fixed_count = 0
    errors = []
    
    for emp in wrong_employees:
        try:
            old_code = emp.employee
            new_code = f"TIQN-{next_num:04d}"
            
            # Update the employee record
            frappe.db.set_value("Employee", emp.name, "employee", new_code)
            
            # If name also needs to be updated to match
            if emp.name == old_code:
                frappe.rename_doc("Employee", old_code, new_code, merge=False)
                print(f"Fixed and renamed: {old_code} → {new_code}")
            else:
                print(f"Fixed employee code: {old_code} → {new_code} (name: {emp.name})")
            
            next_num += 1
            fixed_count += 1
            
        except Exception as e:
            error_msg = f"Error fixing {emp.employee}: {str(e)}"
            print(error_msg)
            errors.append(error_msg)
    
    frappe.db.commit()
    
    return {
        "message": f"Fixed {fixed_count} out of {len(wrong_employees)} employees",
        "fixed": fixed_count,
        "total": len(wrong_employees),
        "errors": errors
    }

@frappe.whitelist()
def debug_employee_code_issue():
    """Debug the employee code issue"""
    print("=== DEBUGGING EMPLOYEE CODE ISSUE ===")
    
    # Test the SQL query directly
    sql_result = frappe.db.sql("""
        SELECT employee
        FROM tabEmployee 
        WHERE employee LIKE 'TIQN-%'
        ORDER BY CAST(SUBSTRING(employee, 6) AS UNSIGNED) DESC
        LIMIT 5
    """, as_dict=True)
    
    print(f"Top 5 employees from SQL: {sql_result}")
    
    # Test get_next_employee_code
    next_code = get_next_employee_code()
    print(f"get_next_employee_code returned: {next_code}")
    
    # Test get_next_attendance_device_id  
    next_device_id = get_next_attendance_device_id()
    print(f"get_next_attendance_device_id returned: {next_device_id}")
    
    return {
        "sql_result": sql_result,
        "next_employee_code": next_code,
        "next_attendance_device_id": next_device_id
    }

@frappe.whitelist()
def test_employee_code_generation():
    """Test function to debug employee code generation"""
    highest_info = get_highest_employee_info()
    next_code = get_next_employee_code()
    
    return {
        "highest_employee": highest_info.get("employee"),
        "next_employee_code": next_code,
        "debug_info": {
            "sql_query_result": frappe.db.sql("""
                SELECT employee, employee_name
                FROM tabEmployee 
                WHERE employee LIKE 'TIQN-%'
                ORDER BY CAST(SUBSTRING(employee, 6) AS UNSIGNED) DESC
                LIMIT 5
            """, as_dict=True)
        }
    }

@frappe.whitelist()
def fix_employee_naming():
    """Fix existing employees that have wrong naming pattern"""
    # Find employees where name doesn't match employee field
    wrong_employees = frappe.db.sql("""
        SELECT name, employee 
        FROM tabEmployee 
        WHERE employee LIKE 'TIQN-%' 
        AND name != employee
    """, as_dict=True)
    
    print(f"Found {len(wrong_employees)} employees with mismatched names")
    
    fixed_count = 0
    for emp in wrong_employees:
        try:
            # Rename the document
            old_name = emp.name
            new_name = emp.employee
            
            # Use frappe.rename_doc to properly rename the document
            frappe.rename_doc("Employee", old_name, new_name, merge=False)
            print(f"Renamed {old_name} to {new_name}")
            fixed_count += 1
            
        except Exception as e:
            print(f"Error renaming {emp.name}: {str(e)}")
    
    frappe.db.commit()
    return {
        "total_found": len(wrong_employees),
        "fixed_count": fixed_count,
        "message": f"Fixed {fixed_count} out of {len(wrong_employees)} employees"
    }

@frappe.whitelist()
def get_employee_fingerprint_data(employee_id):
    """Get employee fingerprint data for display"""
    emp = frappe.get_doc("Employee", employee_id)
    return {
        "employee": emp.employee,
        "employee_name": emp.employee_name,
        "attendance_device_id": emp.attendance_device_id or "Not Set"
    }