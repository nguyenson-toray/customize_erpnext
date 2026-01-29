"""
Shift Type Overrides - Apply Monkey Patches

IMPORTANT: This module replaces HRMS shift attendance functions with optimized versions.
The optimized code (shift_type_optimized.py) is used for BOTH:
1. HRMS hourly hook (process_auto_attendance_for_all_shifts)
2. UI manual processing (bulk_update_attendance_optimized)
"""

import frappe
from customize_erpnext.overrides.shift_type.shift_type import (
	custom_get_employee_checkins,
	custom_update_last_sync_of_checkin,
	custom_should_mark_attendance,
	custom_process_auto_attendance,
	get_employee_checkins_name_with_null_shift,
	update_fields_for_employee_checkins
)

# Import OPTIMIZED version for hourly hook
from customize_erpnext.overrides.shift_type.shift_type_optimized import (
	custom_process_auto_attendance_for_all_shifts
)

import hrms.hr.doctype.shift_type.shift_type as hrms_st

# Save original functions (for debugging/rollback)
if not hasattr(hrms_st.ShiftType, '_original_get_employee_checkins'):
	hrms_st.ShiftType._original_get_employee_checkins = hrms_st.ShiftType.get_employee_checkins

if not hasattr(hrms_st.ShiftType, '_original_should_mark_attendance'):
	hrms_st.ShiftType._original_should_mark_attendance = hrms_st.ShiftType.should_mark_attendance

if not hasattr(hrms_st.ShiftType, '_original_process_auto_attendance'):
	hrms_st.ShiftType._original_process_auto_attendance = hrms_st.ShiftType.process_auto_attendance

# update_last_sync_of_checkin is a module-level function, not a class method
if not hasattr(hrms_st, '_original_update_last_sync_of_checkin'):
	hrms_st._original_update_last_sync_of_checkin = hrms_st.update_last_sync_of_checkin

# process_auto_attendance_for_all_shifts is also a module-level function
if not hasattr(hrms_st, '_original_process_auto_attendance_for_all_shifts'):
	hrms_st._original_process_auto_attendance_for_all_shifts = hrms_st.process_auto_attendance_for_all_shifts

# Replace with custom methods
hrms_st.ShiftType.get_employee_checkins = custom_get_employee_checkins
hrms_st.ShiftType.should_mark_attendance = custom_should_mark_attendance
hrms_st.ShiftType.process_auto_attendance = custom_process_auto_attendance
# Patch module-level functions
hrms_st.update_last_sync_of_checkin = custom_update_last_sync_of_checkin
hrms_st.process_auto_attendance_for_all_shifts = custom_process_auto_attendance_for_all_shifts

frappe.logger().info("✅ Monkey patch applied: customize_erpnext/overrides/shift_type")



#   ┌──────────────────────┬─────────────────────────────────────────────────┬─────────────────────────────────────────────────────────────┐
#   │ Tiêu chí             │ Function (Hàm)                                  │ Method (Phương thức)                                        │
#   ├──────────────────────┼─────────────────────────────────────────────────┼─────────────────────────────────────────────────────────────┤
#   │ **Liên kết**         │ Độc lập                                         │ Thuộc về một class/đối tượng.                               │
#   │ **Cách gọi**         │ `function_name(params)`                         │ `object.method_name(params)`                                │
#   │ **Truy cập dữ liệu** │ Chỉ truy cập dữ liệu được truyền vào (tham số). │ Có thể truy cập và thay đổi dữ liệu của đối tượng (`self`). │
#   └──────────────────────┴─────────────────────────────────────────────────┴─────────────────────────────────────────────────────────────┘
#   Trong file shift_type.py, get_attendance được định nghĩa bên trong class ShiftType. Vì vậy, nó là một method.
# => hrms_st.ShiftType.get_attendance = custom_get_attendance