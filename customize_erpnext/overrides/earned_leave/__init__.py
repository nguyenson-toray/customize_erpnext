# Earned Leave Overrides Module
"""
Earned Leave Overrides - Apply Monkey Patches

Customizations:
1. Support all allocate_on_day options: First Day, Last Day, Date of Joining, 15th of Month
2. Override allocation date calculation for multiple options
3. Override earned leave applicability check for current period
4. Skip first partial month if allocation_date < effective_from
5. Employee eligibility check based on probation period:
   - Priority (1): date_of_joining + custom_number_of_probation_days (if set)
   - Fallback (2): date_of_joining + applicable_after (Leave Type)
6. Seniority bonus: +1 day per 5 years (Vietnamese Labor Law - Điều 114 BLLĐ 2019)
7. Monthly allocation with bonus months strategy:
   - 1 day per month (standard)
   - 2+ days in June and December (bonus months)
   - Extra days from seniority go to bonus months

Company Policy (TIQN):
- Base: 14 days annual leave per year (from Leave Type.max_leaves_allowed)
- Seniority: +1 day per 5 years of service
- Strategy: Bonus months (June, December get extra allocation)
- Eligibility: After probation period
"""

import frappe

# Import config first
from customize_erpnext.overrides.earned_leave.earned_leave_config import (
    get_monthly_allocation,
    get_monthly_allocation_for_month,
    get_allocation_date_for_month,
    get_annual_allocation_with_seniority,
    calculate_seniority_bonus,
)

# Import eligibility functions
from customize_erpnext.overrides.earned_leave.earned_leave_eligibility import (
    is_employee_eligible_for_earned_leave,
    get_employee_probation_days,
    get_leave_type_applicable_after,
    calculate_eligibility_date,
    get_first_eligible_allocation_date,
    log_eligibility_skip,
)

# Import main override functions
from customize_erpnext.overrides.earned_leave.earned_leave import (
    get_15th_of_month,
    custom_get_expected_allocation_date_for_period,
    custom_is_earned_leave_applicable_for_current_period,
    custom_get_periods_passed,
    custom_get_new_leaves,
    custom_get_new_leaves_with_eligibility,
    get_leaves_for_passed_period_from_eligibility,
    custom_allocate_earned_leaves,
    custom_get_earned_leave_schedule,
    get_adjusted_from_date_for_allocation,
)


# Apply monkey patches
try:
    import hrms.hr.utils as hr_utils
    from hrms.hr.doctype.leave_policy_assignment import leave_policy_assignment as lpa_module
    from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import LeavePolicyAssignment

    # 1. Override the allocation date calculation (add "15th of Month")
    hr_utils.get_expected_allocation_date_for_period = custom_get_expected_allocation_date_for_period

    # 2. Override the earned leave applicability check
    lpa_module.is_earned_leave_applicable_for_current_period = custom_is_earned_leave_applicable_for_current_period

    # 3. Override get_periods_passed to skip first partial month
    LeavePolicyAssignment.get_periods_passed = custom_get_periods_passed

    # 4. Override get_new_leaves with eligibility check
    LeavePolicyAssignment.get_new_leaves = custom_get_new_leaves_with_eligibility

    # 5. Add new method for calculating leaves from eligibility date
    LeavePolicyAssignment.get_leaves_for_passed_period_from_eligibility = get_leaves_for_passed_period_from_eligibility

    # 6. Override get_earned_leave_schedule with eligibility-aware scheduling
    LeavePolicyAssignment.get_earned_leave_schedule = custom_get_earned_leave_schedule

    # 7. Override the daily scheduler for earned leaves
    hr_utils.allocate_earned_leaves = custom_allocate_earned_leaves

    frappe.logger().info("✅ Earned Leave Overrides applied:")
    frappe.logger().info("   - get_expected_allocation_date_for_period (15th of Month support)")
    frappe.logger().info("   - is_earned_leave_applicable_for_current_period")
    frappe.logger().info("   - LeavePolicyAssignment.get_periods_passed")
    frappe.logger().info("   - LeavePolicyAssignment.get_new_leaves (with eligibility)")
    frappe.logger().info("   - LeavePolicyAssignment.get_leaves_for_passed_period_from_eligibility")
    frappe.logger().info("   - LeavePolicyAssignment.get_earned_leave_schedule (with eligibility)")
    frappe.logger().info("   - allocate_earned_leaves (scheduler with eligibility)")

except Exception as e:
    frappe.log_error(f"Failed to apply Earned Leave monkey patches: {str(e)}", "Earned Leave Monkey Patch Error")
    frappe.logger().error(f"Failed to apply Earned Leave monkey patches: {str(e)}")
