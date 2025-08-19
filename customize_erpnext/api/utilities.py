import frappe
from frappe import _

# Python code (get_role_profile)
@frappe.whitelist()
def get_role_profile(email=None):
    """
    Lấy role_profile_name và roles của user
    Args:
        email: Email của user. Nếu không có sẽ lấy user hiện tại
        
    Returns:
        dict: Thông tin roles của user
    """
    try:
        if not email:
            email = frappe.session.user
             
        # Lấy role_profile và roles
        user = frappe.get_doc('User', email)
        role_profile = user.role_profile_name
        roles = [role.role for role in user.roles]
        # return role_profile
        return {
            'role_profile': role_profile,
            'roles': roles,
            'has_item_manager_role': 'Item Manager' in roles
        }
        
    except Exception as e:
        frappe.log_error(f"Error in get_role_profile: {str(e)}")
        return None
    
# Get color options for the selected item template 

@frappe.whitelist()
def get_colors_for_template(item_template):
    """Get all colors for an item template"""
    colors = frappe.db.sql("""
        SELECT DISTINCT attribute_value 
        FROM `tabItem Variant Attribute` 
        WHERE attribute = 'Color' 
        AND parent IN (
            SELECT name 
            FROM `tabItem` 
            WHERE variant_of = %s
        )
    """, item_template, as_list=1)
    
    return [color[0] for color in colors] if colors else []

def get_item_default_warehouse(item_code):
    """Get default warehouse for an item"""
    try:
        # Get the first default warehouse from item_defaults
        default_warehouse = frappe.db.sql("""
            SELECT default_warehouse
            FROM `tabItem Default`
            WHERE parent = %s
            AND default_warehouse IS NOT NULL
            ORDER BY idx
            LIMIT 1
        """, item_code, as_dict=True)
        
        return default_warehouse[0].default_warehouse if default_warehouse else None
    except Exception:
        return None

@frappe.whitelist()
def export_master_data_item_attribute():
    """Export master data item attributes to Excel file"""
    import io
    import base64
    from datetime import datetime
    
    try:
        # Import openpyxl
        try:
            from openpyxl import Workbook
            from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
            from openpyxl.worksheet.table import Table, TableStyleInfo
        except ImportError:
            frappe.throw(_("openpyxl library is required for Excel export"))
        
        # Create workbook
        wb = Workbook()
        
        # Remove default sheet
        wb.remove(wb.active)
        
        # Create Item sheet
        item_sheet = wb.create_sheet("Item")
        
        # Item sheet headers
        item_headers = [
            'Item Code', 'Item Name', 'Item Name Detail', 'Item Group', 
            'Default Unit of Measure', 'Color', 'Size', 'Brand', 
            'Season', 'Info', 'Default Warehouse', 'Bin Qty', 'Creation'
        ]
        
        # Add headers to Item sheet
        for col, header in enumerate(item_headers, 1):
            cell = item_sheet.cell(row=1, column=col)
            cell.value = header
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')
        
        # Get all items with their attributes
        items_data = frappe.db.sql("""
            SELECT 
                i.item_code,
                i.item_name,
                i.custom_item_name_detail,
                i.item_group,
                i.stock_uom,
                i.creation
            FROM `tabItem` i
            WHERE i.disabled = 0
            ORDER BY i.item_code ASC
        """, as_dict=True)
        
        # Define attribute order
        attribute_order = ['Color', 'Size', 'Brand', 'Season', 'Info']
        
        # Process each item
        for row_num, item in enumerate(items_data, 2):
            # Get item attributes
            item_attributes = frappe.db.sql("""
                SELECT attribute, attribute_value
                FROM `tabItem Variant Attribute`
                WHERE parent = %s
                ORDER BY idx
            """, item.item_code, as_dict=True)
            
            # Create attribute dictionary
            attr_dict = {}
            for attr in item_attributes:
                attr_dict[attr.attribute] = attr.attribute_value
            
            # Get bin quantity
            bin_qty = frappe.db.sql("""
                SELECT SUM(actual_qty) as total_qty
                FROM `tabBin`
                WHERE item_code = %s
            """, item.item_code, as_dict=True)
            
            total_qty = bin_qty[0].total_qty if bin_qty and bin_qty[0].total_qty else 0
            
            # Get default warehouse for this item
            default_warehouse = get_item_default_warehouse(item.item_code)
            
            # Fill item data
            item_sheet.cell(row=row_num, column=1).value = item.item_code
            item_sheet.cell(row=row_num, column=2).value = item.item_name
            item_sheet.cell(row=row_num, column=3).value = item.custom_item_name_detail
            item_sheet.cell(row=row_num, column=4).value = item.item_group
            item_sheet.cell(row=row_num, column=5).value = item.stock_uom
            
            # Fill attributes in order
            for idx, attr_name in enumerate(attribute_order):
                col = 6 + idx  # Start from column 6 (Color)
                item_sheet.cell(row=row_num, column=col).value = attr_dict.get(attr_name, '')
            
            # Fill warehouse and bin qty
            item_sheet.cell(row=row_num, column=11).value = default_warehouse
            item_sheet.cell(row=row_num, column=12).value = total_qty
            
            # Fill creation time
            item_sheet.cell(row=row_num, column=13).value = item.creation
        
        # Format Item sheet as table
        if len(items_data) > 0:
            item_table = Table(
                displayName="ItemTable",
                ref=f"A1:M{len(items_data) + 1}"
            )
            # Add style
            item_table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium9",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False
            )
            item_sheet.add_table(item_table)
        
        # Create Attribute sheet
        attr_sheet = wb.create_sheet("Attribute")
        
        # Get all attribute values for each attribute type
        col = 1
        for attr_name in attribute_order:
            # Add attribute name header for abbreviation column
            cell = attr_sheet.cell(row=1, column=col)
            cell.value = f"{attr_name} Abbr"
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')
            
            # Add attribute name header for value column
            cell = attr_sheet.cell(row=1, column=col + 1)
            cell.value = f"{attr_name} Value"
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal='center')
            
            # Get all values for this attribute with abbreviation from Item Attribute Value
            attr_values = frappe.db.sql("""
                SELECT DISTINCT iav.abbr, iav.attribute_value
                FROM `tabItem Attribute Value` iav
                WHERE iav.parent = %s
                ORDER BY iav.abbr ASC
            """, attr_name, as_dict=True)
            
            # Add abbreviations and values in separate columns
            for row_num, value in enumerate(attr_values, 2):
                if value:
                    # Abbreviation column
                    attr_sheet.cell(row=row_num, column=col).value = value.abbr or ''
                    # Value column
                    attr_sheet.cell(row=row_num, column=col + 1).value = value.attribute_value or ''
            
            # Format each attribute pair as table
            if len(attr_values) > 0:
                # Get column letters
                start_col = chr(64 + col)  # Convert to letter (A, B, C, etc.)
                end_col = chr(64 + col + 1)
                
                attr_table = Table(
                    displayName=f"{attr_name}Table",
                    ref=f"{start_col}1:{end_col}{len(attr_values) + 1}"
                )
                # Add style
                attr_table.tableStyleInfo = TableStyleInfo(
                    name="TableStyleMedium2",
                    showFirstColumn=False,
                    showLastColumn=False,
                    showRowStripes=True,
                    showColumnStripes=False
                )
                attr_sheet.add_table(attr_table)
            
            # Move to next pair of columns (skip one column for spacing)
            col += 3
        
        # Auto-adjust column widths
        for sheet in [item_sheet, attr_sheet]:
            for column in sheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                sheet.column_dimensions[column_letter].width = adjusted_width
        
        # Save to memory
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        # Convert to base64
        xlsx_data = output.getvalue()
        output.close()
        
        # Create filename with current date
        filename = f"Master_Data_Item_Attribute_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        # Return file data
        return {
            'file_data': base64.b64encode(xlsx_data).decode(),
            'filename': filename,
            'items_count': len(items_data)
        }
        
    except Exception as e:
        frappe.log_error(f"Error in export_master_data_item_attribute: {str(e)}")
        frappe.throw(_("Error generating Excel file: {0}").format(str(e)))


# ===========================
# FINGERPRINT SYNC FUNCTIONS
# ===========================

@frappe.whitelist()
def get_employee_fingerprint_data(employee_id):
    """Get employee fingerprint data for display"""
    emp = frappe.get_doc("Employee", employee_id)
    return {
        "employee": emp.employee,
        "employee_name": emp.employee_name,
        "attendance_device_id": emp.attendance_device_id or "Not Set"
    }

@frappe.whitelist()
def save_fingerprint_data(employee_id, finger_index, template_data, quality_score=0):
    """Saves fingerprint template data to the Employee document."""
    try:
        employee = frappe.get_doc("Employee", employee_id)
        
        # Assuming a child table with fieldname 'custom_fingerprints' in Employee Doctype
        # And the child Doctype has fields 'finger_index' and 'template_data'
        
        existing_fingerprint = None
        for fp in employee.get("custom_fingerprints"):
            if str(fp.finger_index) == str(finger_index):
                existing_fingerprint = fp
                break
        
        # Get finger name from index
        finger_name = get_finger_name(int(finger_index))
        
        fingerprint_id = None
        if existing_fingerprint:
            existing_fingerprint.template_data = template_data
            existing_fingerprint.finger_name = finger_name
            existing_fingerprint.quality_score = int(quality_score) if quality_score else 0
            fingerprint_id = existing_fingerprint.name
        else:
            new_fingerprint = employee.append("custom_fingerprints", {
                "finger_index": finger_index,
                "finger_name": finger_name,
                "template_data": template_data,
                "quality_score": int(quality_score) if quality_score else 0
            })
            fingerprint_id = new_fingerprint.name

        employee.save(ignore_permissions=True)
        frappe.db.commit()
        
        return {"success": True, "fingerprint_id": fingerprint_id}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to save fingerprint data")
        return {"success": False, "message": str(e)}

@frappe.whitelist()
def update_fingerprint_names(employee_id):
    """Update finger names for existing fingerprints that don't have names set"""
    try:
        employee = frappe.get_doc("Employee", employee_id)
        updated_count = 0
        
        if employee.get("custom_fingerprints"):
            for fp in employee.get("custom_fingerprints"):
                if not fp.finger_name or fp.finger_name.strip() == "":
                    fp.finger_name = get_finger_name(fp.finger_index)
                    updated_count += 1
                    
            if updated_count > 0:
                employee.save(ignore_permissions=True)
                frappe.db.commit()
                
        return {
            "success": True, 
            "updated_count": updated_count,
            "message": f"Updated {updated_count} fingerprint names"
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to update fingerprint names")
        return {"success": False, "message": str(e)}

@frappe.whitelist()
def get_employee_fingerprints_status(employee_id):
    """Returns a list of finger_index for which fingerprint data exists for the given employee."""
    try:
        employee = frappe.get_doc("Employee", employee_id)
        existing_fingers = []
        if employee.get("custom_fingerprints"):
            for fp in employee.get("custom_fingerprints"):
                existing_fingers.append(fp.finger_index)
        return {"success": True, "existing_fingers": existing_fingers}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to get employee fingerprints status")
        return {"success": False, "message": str(e)}

def get_finger_name(finger_index):
    """Get standardized finger name from index"""
    finger_names = {
        0: "Left Thumb", 1: "Left Index", 2: "Left Middle", 3: "Left Ring", 4: "Left Little",
        5: "Right Thumb", 6: "Right Index", 7: "Right Middle", 8: "Right Ring", 9: "Right Little"
    }
    return finger_names.get(finger_index, f"Finger {finger_index}")

def get_finger_index(finger_name):
    """Get finger index from standardized name"""
    finger_map = {
        'Left Thumb': 0, 'Left Index': 1, 'Left Middle': 2, 'Left Ring': 3, 'Left Little': 4,
        'Right Thumb': 5, 'Right Index': 6, 'Right Middle': 7, 'Right Ring': 8, 'Right Little': 9
    }
    return finger_map.get(finger_name, -1)

@frappe.whitelist()
def get_employees_for_fingerprint():
    """Get employees sorted by employee code (descending) for fingerprint dialog"""
    try:
        employees = frappe.get_list("Employee", 
            fields=["name", "employee", "employee_name", "attendance_device_id"],
            filters={"status": "Active"},
            order_by="employee desc"
        )
        return {"success": True, "employees": employees}
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to get employees for fingerprint")
        return {"success": False, "message": str(e)}

@frappe.whitelist()
def sync_employee_fingerprint_to_machines(employee_id):
    """Sync employee fingerprint data to all enabled attendance machines"""
    try:
        # Get employee data, filter only required fields (excluding fingerprints child table)
        employee = frappe.get_doc("Employee", employee_id, 
            ["employee", "employee_name", "attendance_device_id", "custom_privilege", "custom_password"])
        
        if not employee.attendance_device_id:
            return {
                "success": False, 
                "message": f"Employee {employee.employee} does not have attendance_device_id"
            }
        
        # Get enabled attendance machines
        machines = frappe.get_list("Attendance Machine",
            filters={"enable": 1},
            fields=["name", "device_name", "ip_address", "port", "timeout", "force_udp", "ommit_ping"]
        )
        
        if not machines:
            return {
                "success": False,
                "message": "No enabled attendance machines found"
            }
        
        # Get employee fingerprint data using direct SQL query for better performance
        fingerprints_data = frappe.db.sql("""
            SELECT finger_index, template_data
            FROM `tabFingerprint Data`
            WHERE parent = %s AND template_data IS NOT NULL AND template_data != ''
            ORDER BY finger_index
        """, employee_id, as_dict=True)
        
        fingerprints = []
        for fp in fingerprints_data:
            fingerprints.append({
                "finger_index": fp.finger_index,
                "template_data": fp.template_data
            })
        
        if not fingerprints:
            return {
                "success": False,
                "message": f"Employee {employee.employee} has no fingerprint data"
            }
        
        # Prepare employee data for sync
        # Import pyzk constants for privilege levels
        try:
            from zk import const
            # Map string privilege to pyzk constants (int values)
            privilege_str = getattr(employee, 'custom_privilege', 'USER_DEFAULT')
            privilege = const.USER_ADMIN if privilege_str == "USER_ADMIN" else const.USER_DEFAULT
        except ImportError:
            # Fallback if const not available
            privilege = 14 if getattr(employee, 'custom_privilege', 'USER_DEFAULT') == "USER_ADMIN" else 0
        
        # Convert password from int to string for machine
        # If custom_password is 0 or None, it means no password
        password_int = getattr(employee, 'custom_password', None)
        password = str(password_int) if password_int and password_int != 0 else ""
        
        employee_data = {
            "employee": employee.employee,
            "employee_name": employee.employee_name,
            "attendance_device_id": employee.attendance_device_id,
            "password": password,
            "privilege": privilege,
            "fingerprints": fingerprints
        }
        
        sync_results = []
        success_count = 0
        
        # Sync to each machine
        for machine in machines:
            try:
                result = sync_to_single_machine(machine, employee_data)
                sync_results.append({
                    "machine": machine.device_name,
                    "ip": machine.ip_address,
                    "success": result["success"],
                    "message": result["message"]
                })
                
                if result["success"]:
                    success_count += 1
                    
            except Exception as e:
                sync_results.append({
                    "machine": machine.device_name,
                    "ip": machine.ip_address,
                    "success": False,
                    "message": str(e)
                })
        
        # Create summary message
        total_machines = len(machines)
        if success_count == total_machines:
            status = "success"
            message = f"Successfully synced to all {total_machines} machines"
        elif success_count > 0:
            status = "partial"
            message = f"Synced to {success_count}/{total_machines} machines"
        else:
            status = "failed"
            message = f"Failed to sync to any machines"
        
        return {
            "success": success_count > 0,
            "status": status,
            "message": message,
            "sync_results": sync_results,
            "summary": {
                "employee": employee.employee,
                "employee_name": employee.employee_name,
                "attendance_device_id": employee.attendance_device_id,
                "privilege": f"{privilege_str} ({privilege})",
                "password": password if password else "No password set",
                "fingerprints_count": len(fingerprints),
                "machines_total": total_machines,
                "machines_success": success_count,
                "machines_failed": total_machines - success_count
            }
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to sync employee fingerprint to machines")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }

def sync_to_single_machine(machine_config, employee_data):
    """Sync employee data to a single attendance machine"""
    try:
        import socket
        from zk import ZK
        from zk.base import Finger
        import base64
        import time
        
        # Prepare device config
        device_config = {
            "device_name": machine_config.device_name,
            "ip_address": machine_config.ip_address,
            "port": machine_config.port or 4370,
            "timeout": machine_config.timeout or 10,
            "force_udp": machine_config.force_udp or True,
            "ommit_ping": machine_config.ommit_ping or True
        }
        
        # Check network connectivity
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((device_config["ip_address"], device_config["port"]))
            sock.close()
            
            if result != 0:
                return {
                    "success": False,
                    "message": f"Cannot connect to {device_config['ip_address']}:{device_config['port']}"
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Network error: {str(e)}"
            }
        
        # Connect to device
        zk = ZK(
            device_config["ip_address"],
            port=device_config["port"],
            timeout=device_config["timeout"],
            force_udp=device_config["force_udp"],
            ommit_ping=device_config["ommit_ping"]
        )
        
        conn = zk.connect()
        if not conn:
            return {
                "success": False,
                "message": "Failed to connect to device"
            }
        
        try:
            # Disable device during sync
            conn.disable_device()
            
            attendance_device_id = employee_data["attendance_device_id"]
            
            # Check if user exists and delete if found
            existing_users = conn.get_users()
            user_exists = any(u.user_id == attendance_device_id for u in existing_users)
            
            if user_exists:
                conn.delete_user(user_id=attendance_device_id)
                time.sleep(0.1)  # Give device time to process
            
            # Create new user
            full_name = employee_data["employee_name"]
            shortened_name = shorten_name(full_name, 24)
            
            # Set user with correct parameter order and group_id
            password = employee_data.get("password", "")
            privilege = employee_data.get("privilege", 0)  # Default to USER_DEFAULT
            
            if password:
                # Create user with password
                conn.set_user(
                    name=shortened_name,
                    privilege=privilege,
                    password=password,
                    group_id='',
                    user_id=attendance_device_id
                )
            else:
                # Create user without password
                conn.set_user(
                    name=shortened_name,
                    privilege=privilege,
                    group_id='',
                    user_id=attendance_device_id
                )
            
            # Get user info after creation
            users = conn.get_users()
            user = next((u for u in users if u.user_id == attendance_device_id), None)
            
            if not user:
                return {
                    "success": False,
                    "message": f"Could not create or find user {attendance_device_id}"
                }
            
            # Prepare fingerprint templates
            templates_to_send = []
            fingerprint_count = 0
            
            # Create fingerprint data lookup for fast access
            fingerprint_lookup = {fp.get("finger_index"): fp for fp in employee_data["fingerprints"] if fp.get("template_data")}
            
            # Pre-decode all template data to avoid repeated base64 operations
            decoded_templates = {}
            for finger_index, fp in fingerprint_lookup.items():
                try:
                    decoded_templates[finger_index] = base64.b64decode(fp["template_data"])
                except Exception:
                    pass  # Skip invalid templates
            
            # Create 10 Finger objects in batch (for all 10 fingers)
            templates_to_send = []
            for i in range(10):
                if i in decoded_templates:
                    finger_obj = Finger(uid=user.uid, fid=i, valid=True, template=decoded_templates[i])
                    fingerprint_count += 1
                else:
                    finger_obj = Finger(uid=user.uid, fid=i, valid=False, template=b'')
                templates_to_send.append(finger_obj)
            
            # Send all templates to device
            conn.save_user_template(user, templates_to_send)
            
            return {
                "success": True,
                "message": f"Successfully synced {fingerprint_count} fingerprints for user {attendance_device_id}"
            }
            
        finally:
            # Re-enable device and disconnect
            try:
                conn.enable_device()
                conn.disconnect()
            except:
                pass
                
    except Exception as e:
        return {
            "success": False,
            "message": f"Sync error: {str(e)}"
        }

@frappe.whitelist()
def get_enabled_attendance_machines():
    """Get list of enabled attendance machines with connection status"""
    try:
        # Get enabled machines
        machines = frappe.get_list("Attendance Machine",
            filters={"enable": 1},
            fields=["name", "device_name", "ip_address", "port", "timeout", "force_udp", "ommit_ping", "location"]
        )
        
        if not machines:
            return {
                "success": True,
                "machines": [],
                "message": "No enabled attendance machines found"
            }
        
        # Check connection status for each machine
        machines_with_status = []
        for machine in machines:
            connection_status = check_machine_connection(machine)
            machine_info = {
                "name": machine.name,
                "device_name": machine.device_name,
                "ip_address": machine.ip_address,
                "port": machine.port or 4370,
                "location": machine.location or "",
                "connection_status": connection_status["status"],
                "connection_message": connection_status["message"],
                "response_time": connection_status.get("response_time", 0)
            }
            machines_with_status.append(machine_info)
        
        return {
            "success": True,
            "machines": machines_with_status,
            "total_machines": len(machines_with_status),
            "online_machines": len([m for m in machines_with_status if m["connection_status"] == "online"]),
            "offline_machines": len([m for m in machines_with_status if m["connection_status"] == "offline"])
        }
        
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Failed to get enabled attendance machines")
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }

def check_machine_connection(machine_config):
    """Check if attendance machine is reachable"""
    try:
        import socket
        import time
        
        ip_address = machine_config.ip_address
        port = machine_config.port or 4370
        timeout = 3  # Quick connection check
        
        start_time = time.time()
        
        # Test TCP connection
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((ip_address, port))
        sock.close()
        
        response_time = round((time.time() - start_time) * 1000, 2)  # ms
        
        if result == 0:
            return {
                "status": "online",
                "message": f"Connected ({response_time}ms)",
                "response_time": response_time
            }
        else:
            return {
                "status": "offline", 
                "message": f"Connection failed (Error: {result})",
                "response_time": 0
            }
            
    except Exception as e:
        return {
            "status": "error",
            "message": f"Connection error: {str(e)}",
            "response_time": 0
        }

def shorten_name(full_name, max_length=24):
    """Shorten employee name if it exceeds max length and convert Vietnamese to non-accented"""
    from unidecode import unidecode
    if not full_name:
        return full_name 
    text_processed = unidecode(full_name)  # Convert to non-accented text
    # Remove extra spaces
    text_processed = ' '.join(text_processed.split()).strip()
    
    if len(text_processed) > max_length:
        parts = text_processed.split()
        if len(parts) > 1:
            # Take first letter of all parts except the last one
            initials = "".join(part[0].upper() for part in parts[:-1])
            last_part = parts[-1]
            return f"{initials} {last_part}"
        else:
            # If only one word and too long, truncate it
            return text_processed[:max_length]
    else:
        return text_processed

