"""
Dashboard Chart Employee By Age Overrides - Apply Monkey Patches
"""

import frappe
from customize_erpnext.overrides.employees_by_age.employees_by_age import (  
	custom_get_ranges)
import hrms.hr.dashboard_chart_source.employees_by_age.employees_by_age as hrms_employees_by_age

# Save original functions (for debugging/rollback) 
if not hasattr(hrms_employees_by_age, '_original_get_ranges'):
	hrms_employees_by_age._original_get_ranges = hrms_employees_by_age.get_ranges


# Replace with custom functions  
hrms_employees_by_age.get_ranges = custom_get_ranges 

frappe.logger().info("✅ Monkey patch applied: /customize_erpnext/overrides/employees_by_age/employees_by_age")
