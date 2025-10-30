import frappe
import os
from frappe.utils import get_site_path
from frappe import _


@frappe.whitelist(allow_guest=False)
def get_employee_photos(show_active_only=1, sort_order='asc', custom_group=''):
    """
    Get list of all employee photos from employee_photos folder.
    Args:
        show_active_only: 1 to show only Active employees (default), 0 to show all
        sort_order: 'asc' for A-Z, 'desc' for Z-A
        custom_group: Filter by custom_group (optional)
    Returns list of photo info including filename, URL, file size, employee name, and modification time.
    """
    try:
        site_path = get_site_path()
        photos_folder = os.path.join(site_path, 'public', 'files', 'employee_photos')

        if not os.path.exists(photos_folder):
            return {
                'status': 'success',
                'photos': [],
                'total': 0,
                'message': 'Employee photos folder does not exist'
            }

        # Get employees with their names and status from database
        filters = {}
        if int(show_active_only) == 1:
            # Only show Active employees
            filters['status'] = 'Active'

        if custom_group:
            # Filter by custom_group if provided
            filters['custom_group'] = custom_group

        employees = frappe.db.get_all('Employee',
            fields=['name', 'employee_name', 'status', 'custom_group'],
            filters=filters
        )

        frappe.logger().info(f"get_employee_photos: show_active_only={show_active_only}, found {len(employees)} employees")

        # Create a mapping of employee_id -> employee info
        employee_map = {emp['name']: {
            'employee_name': emp['employee_name'],
            'status': emp['status'],
            'custom_group': emp.get('custom_group', '')
        } for emp in employees}

        photos = []
        for filename in os.listdir(photos_folder):
            file_path = os.path.join(photos_folder, filename)

            # Skip directories and hidden files
            if os.path.isdir(file_path) or filename.startswith('.'):
                continue

            # Only include image files
            if not filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                continue

            file_stat = os.stat(file_path)

            # Extract employee_id from filename (format: "TIQN-XXXX Employee Name.jpg")
            employee_id = filename.split(' ')[0] if ' ' in filename else None

            # Get employee info
            emp_info = employee_map.get(employee_id)

            # If show_active_only is enabled and employee not found in filtered list, skip
            if int(show_active_only) == 1 and not emp_info:
                continue

            # Get employee details
            employee_name = emp_info.get('employee_name', '') if emp_info else ''
            employee_status = emp_info.get('status', '') if emp_info else ''
            employee_group = emp_info.get('custom_group', '') if emp_info else ''

            # Create display name in format: "TIQN-XXXX Employee Name"
            display_name = f"{employee_id} {employee_name}" if employee_id and employee_name else filename

            photos.append({
                'filename': filename,
                'display_name': display_name,
                'url': f'/files/employee_photos/{filename}',
                'size': file_stat.st_size,
                'modified': file_stat.st_mtime,
                'employee_id': employee_id,
                'employee_name': employee_name,
                'status': employee_status,
                'custom_group': employee_group
            })

        # Sort by display_name based on sort_order
        reverse = (sort_order == 'desc')
        photos.sort(key=lambda x: x['display_name'].lower(), reverse=reverse)

        return {
            'status': 'success',
            'photos': photos,
            'total': len(photos)
        }

    except Exception as e:
        frappe.log_error(f"Error getting employee photos: {str(e)}", "Employee Photos Viewer Error")
        return {
            'status': 'error',
            'message': str(e)
        }


@frappe.whitelist(allow_guest=False)
def get_groups():
    """
    Get all available groups from the Employee table.
    Returns list of unique custom_group values.
    """
    try:
        groups = frappe.db.sql("""
            SELECT DISTINCT custom_group
            FROM `tabEmployee`
            WHERE custom_group IS NOT NULL AND custom_group != ''
            ORDER BY custom_group
        """, as_dict=True)

        return {
            'status': 'success',
            'groups': [g['custom_group'] for g in groups]
        }

    except Exception as e:
        frappe.log_error(f"Error getting groups: {str(e)}", "Employee Photos Viewer Error")
        return {
            'status': 'error',
            'message': str(e)
        }
