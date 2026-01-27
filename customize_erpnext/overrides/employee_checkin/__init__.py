"""
Employee Checkin Overrides - Apply Monkey Patches
"""

import frappe
from customize_erpnext.overrides.employee_checkin.employee_checkin import (  
	custom_create_or_update_attendance)
import hrms.hr.doctype.employee_checkin.employee_checkin as hrms_ec

# Save original functions (for debugging/rollback) 
if not hasattr(hrms_ec, '_original_create_or_update_attendance'):
	hrms_ec._original_create_or_update_attendance = hrms_ec.create_or_update_attendance


# Replace with custom functions  
hrms_ec.create_or_update_attendance = custom_create_or_update_attendance 

frappe.logger().info("✅ Monkey patch applied: customize_erpnext/overrides/employee_checkin")
