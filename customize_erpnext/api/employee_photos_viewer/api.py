import frappe
import os
from frappe.utils import get_site_path
from frappe import _


@frappe.whitelist(allow_guest=False)
def get_employee_photos(show_active_only=1, sort_order='asc', custom_group=''):
    """
    Get list of all employees (with or without photos).
    Args:
        show_active_only: 1 to show only Active employees (default), 0 to show all
        sort_order: 'asc' for A-Z, 'desc' for Z-A
        custom_group: Filter by custom_group (optional)
    Returns list of employee info including image URL, employee name, and date of joining.
    """
    try:
        filters = {}
        if int(show_active_only) == 1:
            filters['status'] = 'Active'

        if custom_group:
            filters['custom_group'] = custom_group

        employees = frappe.db.get_all('Employee',
            fields=['name', 'employee_name', 'status', 'custom_group', 'cell_number', 'custom_current_address_full', 'image', 'date_of_joining'],
            filters=filters
        )

        frappe.logger().info(f"get_employee_photos: show_active_only={show_active_only}, found {len(employees)} employees")

        photos = []
        for emp in employees:
            employee_id = emp['name']
            employee_name = emp.get('employee_name', '')
            display_name = f"{employee_id} {employee_name}" if employee_id and employee_name else employee_id
            
            # Format date of joining to string if present
            date_of_joining_str = ''
            if emp.get('date_of_joining'):
                date_of_joining_str = emp['date_of_joining'].strftime('%Y-%m-%d') if hasattr(emp['date_of_joining'], 'strftime') else str(emp['date_of_joining'])

            url = emp.get('image', '')
            filename = url.split('/')[-1] if url else ''

            photos.append({
                'filename': filename,
                'display_name': display_name,
                'url': url,
                'size': 0, # Don't need real size for DB fetch unless we stat the file
                'modified': 0,
                'employee_id': employee_id,
                'employee_name': employee_name,
                'status': emp.get('status', ''),
                'custom_group': emp.get('custom_group', ''),
                'cell_number': emp.get('cell_number', ''),
                'custom_current_address_full': emp.get('custom_current_address_full', ''),
                'date_of_joining': date_of_joining_str
            })

        # Sort by display_name
        reverse = (sort_order == 'desc')
        photos.sort(key=lambda x: x['display_name'].lower(), reverse=reverse)

        return {
            'status': 'success',
            'photos': photos,
            'total': len(photos)
        }

    except Exception as e:
        frappe.log_error(f"Error getting employees: {str(e)}", "Employee Photos Viewer Error")
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
