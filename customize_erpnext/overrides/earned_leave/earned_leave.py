# Copyright (c) 2025, IT Team - TIQN
# License: MIT

"""
Earned Leave Override Functions

Custom functions to support multiple allocation options and
employee eligibility check based on probation period.

These functions replace the original HRMS functions via monkey patch.

Customizations:
1. Support all allocate_on_day options: First Day, Last Day, Date of Joining, 15th of Month
2. Skip first partial month if allocation_date < effective_from
3. Employee eligibility check based on:
   - Priority (1): date_of_joining + custom_probation_days (Employee)
   - Fallback (2): date_of_joining + applicable_after (Leave Type)
4. Seniority bonus: +1 day per 5 years (Vietnamese Labor Law - Điều 114 BLLĐ 2019)
5. Monthly allocation (bonus months strategy):
   - 1 day per month (standard)
   - 2+ days in June and December (bonus months)
   - Extra days from seniority go to bonus months
   - If not eligible in a month, skip (no accumulation)
"""

import datetime
import calendar

from frappe.utils import (
    add_months,
    get_first_day,
    get_last_day,
    get_quarter_ending,
    get_quarter_start,
    get_year_ending,
    get_year_start,
    flt,
    getdate,
)

import frappe
from frappe import _
from hrms.hr.utils import get_semester_start, get_semester_end


def get_15th_of_month(date):
    """Get the 15th day of the given date's month."""
    date = getdate(date)
    return datetime.date(date.year, date.month, 15)


def custom_get_expected_allocation_date_for_period(frequency, allocate_on_day, date, date_of_joining=None):
    """
    Custom version of get_expected_allocation_date_for_period that supports "15th of Month".

    Original function: hrms.hr.utils.get_expected_allocation_date_for_period

    Changes:
    - Added "15th of Month" option for all frequencies

    Args:
        frequency: Earned leave frequency (Monthly, Quarterly, Half-Yearly, Yearly)
        allocate_on_day: Day to allocate leaves (First Day, Last Day, Date of Joining, 15th of Month)
        date: Current date for calculation
        date_of_joining: Employee's date of joining

    Returns:
        datetime.date: The expected allocation date
    """
    # Handle Date of Joining for Monthly frequency
    try:
        doj = date_of_joining.replace(month=date.month, year=date.year)
    except (ValueError, AttributeError):
        # Handle cases like Feb 30 or None date_of_joining
        if date_of_joining:
            doj = datetime.date(date.year, date.month, calendar.monthrange(date.year, date.month)[1])
        else:
            doj = None

    allocation_map = {
        "Monthly": {
            "First Day": get_first_day(date),
            "Last Day": get_last_day(date),
            "Date of Joining": doj,
            "15th of Month": get_15th_of_month(date),  # NEW: 15th of current month
        },
        "Quarterly": {
            "First Day": get_quarter_start(date),
            "Last Day": get_quarter_ending(date),
            "15th of Month": get_15th_of_month(get_quarter_start(date)),  # 15th of quarter start month
        },
        "Half-Yearly": {
            "First Day": get_semester_start(date),
            "Last Day": get_semester_end(date),
            "15th of Month": get_15th_of_month(get_semester_start(date)),  # 15th of semester start month
        },
        "Yearly": {
            "First Day": get_year_start(date),
            "Last Day": get_year_ending(date),
            "15th of Month": datetime.date(date.year, 1, 15),  # January 15th
        },
    }

    return allocation_map[frequency][allocate_on_day]


def custom_is_earned_leave_applicable_for_current_period(date_of_joining, allocate_on_day, earned_leave_frequency):
    """
    Custom version that supports "15th of Month" option.

    Original function: hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment.is_earned_leave_applicable_for_current_period

    Determines if earned leave should be allocated for the current period based on:
    - The allocate_on_day setting
    - The current date relative to allocation date

    Args:
        date_of_joining: Employee's date of joining
        allocate_on_day: Day to allocate leaves (First Day, Last Day, Date of Joining, 15th of Month)
        earned_leave_frequency: Frequency (Monthly, Quarterly, Half-Yearly, Yearly)

    Returns:
        bool: True if current period should be considered for allocation
    """
    date = getdate(frappe.flags.current_date) or getdate()

    # If the date of assignment creation is >= the leave type's "Allocate On" date,
    # then the current month should be considered
    # because the employee is already entitled for the leave of that month

    condition_map = {
        "Monthly": (
            (allocate_on_day == "Date of Joining" and date.day >= date_of_joining.day)
            or (allocate_on_day == "First Day" and date >= get_first_day(date))
            or (allocate_on_day == "Last Day" and date == get_last_day(date))
            or (allocate_on_day == "15th of Month" and date.day >= 15)  # NEW: Check if past 15th
        ),
        "Quarterly": (
            (allocate_on_day == "First Day" and date >= get_quarter_start(date))
            or (allocate_on_day == "Last Day" and date == get_quarter_ending(date))
            or (allocate_on_day == "15th of Month" and date.day >= 15 and date >= get_quarter_start(date))
        ),
        "Half-Yearly": (
            (allocate_on_day == "First Day" and date >= get_semester_start(date))
            or (allocate_on_day == "Last Day" and date == get_semester_end(date))
            or (allocate_on_day == "15th of Month" and date.day >= 15 and date >= get_semester_start(date))
        ),
        "Yearly": (
            (allocate_on_day == "First Day" and date >= get_year_start(date))
            or (allocate_on_day == "Last Day" and date == get_year_ending(date))
            or (allocate_on_day == "15th of Month" and date.day >= 15 and date.month == 1)  # Past Jan 15th
        ),
    }

    return condition_map.get(earned_leave_frequency)


def get_adjusted_from_date_for_allocation(effective_from, allocate_on_day, frequency):
    """
    Adjust from_date to skip months where allocation_date < effective_from.

    Problem: Period 26/12/2025 - 25/12/2026, allocate on 15th
    - 15/12/2025 < 26/12/2025 → December should NOT count
    - Should start counting from January 2026

    Solution: Move from_date to next month if allocation_date < effective_from

    Args:
        effective_from: Start date of leave period (e.g., 2025-12-26)
        allocate_on_day: Day to allocate (First Day, Last Day, 15th of Month, Date of Joining)
        frequency: Earned leave frequency (Monthly, Quarterly, etc.)

    Returns:
        datetime.date: Adjusted from_date
    """
    effective_from = getdate(effective_from)

    # Get the allocation date for the effective_from's month
    allocation_date = custom_get_expected_allocation_date_for_period(
        frequency, allocate_on_day, effective_from, effective_from
    )

    # If allocation_date is before effective_from, move to next period
    if allocation_date and allocation_date < effective_from:
        # Move to next month/period
        months_to_add = {"Monthly": 1, "Quarterly": 3, "Half-Yearly": 6, "Yearly": 12}.get(frequency, 1)
        adjusted_date = add_months(effective_from, months_to_add)
        # Return first day of that month for period calculation
        return get_first_day(adjusted_date)

    return effective_from


def custom_calculate_periods_passed(
    current_date, from_date, periods_per_year, months_per_period, consider_current_period,
    effective_from=None, allocate_on_day=None, frequency=None
):
    """
    Custom version of calculate_periods_passed that skips first partial period
    if allocation_date < effective_from.

    Original function: hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment.calculate_periods_passed

    Changes:
    - Added parameters for effective_from, allocate_on_day, frequency
    - Adjusts from_date if first month's allocation_date < effective_from

    Args:
        current_date: Current date
        from_date: Original from date (may be adjusted)
        periods_per_year: Number of periods per year
        months_per_period: Number of months per period
        consider_current_period: Whether to count current period
        effective_from: Original effective_from (for adjustment check)
        allocate_on_day: Allocation day setting
        frequency: Earned leave frequency

    Returns:
        int: Number of periods passed
    """
    periods_passed = 0

    # Adjust from_date if needed (skip first partial month)
    if effective_from and allocate_on_day and frequency:
        from_date = get_adjusted_from_date_for_allocation(effective_from, allocate_on_day, frequency)

    from_period = (from_date.year * periods_per_year) + ((from_date.month - 1) // months_per_period)
    current_period = (current_date.year * periods_per_year) + ((current_date.month - 1) // months_per_period)

    periods_passed = current_period - from_period
    if consider_current_period:
        periods_passed += 1

    # Ensure non-negative
    return max(0, periods_passed)


# Store original method reference
_original_get_periods_passed = None


def custom_get_periods_passed(self, earned_leave_frequency, current_date, from_date, consider_current_period):
    """
    Custom version of LeavePolicyAssignment.get_periods_passed that skips
    first partial period if allocation_date < effective_from.

    Original method: LeavePolicyAssignment.get_periods_passed

    Changes:
    - Checks if first month's allocation_date < effective_from
    - If so, adjusts from_date to next month

    Example:
        Period: 26/12/2025 - 25/12/2026, allocate on 15th
        - 15/12/2025 < 26/12/2025 → Skip December
        - Start counting from January 2026
    """
    from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import (
        calculate_periods_passed,
        get_leave_type_details,
    )

    periods_per_year, months_per_period = {
        "Monthly": (12, 1),
        "Quarterly": (4, 3),
        "Half-Yearly": (2, 6),
        "Yearly": (1, 12),
    }.get(earned_leave_frequency)

    # Get leave type details to check allocate_on_day
    leave_type_details = get_leave_type_details()

    # Find the leave type being processed
    allocate_on_day = None
    if hasattr(self, '_current_leave_details'):
        allocate_on_day = self._current_leave_details.allocate_on_day
    else:
        # Try to get from leave policy
        if self.leave_policy:
            leave_policy = frappe.get_doc("Leave Policy", self.leave_policy)
            for detail in leave_policy.leave_policy_details:
                lt = leave_type_details.get(detail.leave_type)
                if lt and lt.is_earned_leave:
                    allocate_on_day = lt.allocate_on_day
                    break

    # Adjust from_date if needed
    adjusted_from_date = from_date
    if allocate_on_day:
        adjusted_from_date = get_adjusted_from_date_for_allocation(
            getdate(self.effective_from),
            allocate_on_day,
            earned_leave_frequency
        )

    periods_passed = calculate_periods_passed(
        current_date, adjusted_from_date, periods_per_year, months_per_period, consider_current_period
    )

    return periods_passed


def custom_get_new_leaves(self, annual_allocation, leave_details, date_of_joining):
    """
    Custom version of LeavePolicyAssignment.get_new_leaves that stores
    current leave_details for use in get_periods_passed.

    Original method: LeavePolicyAssignment.get_new_leaves
    """
    from frappe.model.meta import get_field_precision
    from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import (
        calculate_pro_rated_leaves,
    )

    # Store leave_details for use in get_periods_passed
    self._current_leave_details = leave_details

    precision = get_field_precision(frappe.get_meta("Leave Allocation").get_field("new_leaves_allocated"))
    current_date = getdate(frappe.flags.current_date) or getdate()

    # Earned Leaves and Compensatory Leaves are allocated by scheduler, initially allocate 0
    if leave_details.is_compensatory:
        new_leaves_allocated = 0
    # if earned leave is being allocated after the effective period, then let them be calculated pro-rata
    elif leave_details.is_earned_leave and current_date < getdate(self.effective_to):
        new_leaves_allocated = self.get_leaves_for_passed_period(
            annual_allocation, leave_details, date_of_joining
        )
    else:
        # calculate pro-rated leaves for other leave types
        new_leaves_allocated = calculate_pro_rated_leaves(
            annual_allocation,
            date_of_joining,
            self.effective_from,
            self.effective_to,
            is_earned_leave=False,
        )

    # leave allocation should not exceed annual allocation as per policy assignment
    # except when allocation is of earned type and yearly
    if new_leaves_allocated > annual_allocation and not (
        leave_details.is_earned_leave and leave_details.earned_leave_frequency == "Yearly"
    ):
        new_leaves_allocated = annual_allocation

    # Clean up
    if hasattr(self, '_current_leave_details'):
        delattr(self, '_current_leave_details')

    from frappe.utils import flt
    return flt(new_leaves_allocated, precision)


# =============================================================================
# ELIGIBILITY-AWARE FUNCTIONS
# =============================================================================

def custom_get_new_leaves_with_eligibility(self, annual_allocation, leave_details, date_of_joining):
    """
    Custom version of LeavePolicyAssignment.get_new_leaves with eligibility check.

    Changes from original:
    1. Check if employee is eligible based on probation period
    2. If not eligible, return 0 (scheduler will allocate later)
    3. If eligible, calculate leaves only from eligibility_date onwards

    Original method: LeavePolicyAssignment.get_new_leaves
    """
    from frappe.model.meta import get_field_precision
    from frappe.utils import flt
    from hrms.hr.doctype.leave_policy_assignment.leave_policy_assignment import (
        calculate_pro_rated_leaves,
    )
    from customize_erpnext.overrides.earned_leave.earned_leave_eligibility import (
        is_employee_eligible_for_earned_leave,
    )

    # Store leave_details for use in get_periods_passed
    self._current_leave_details = leave_details

    precision = get_field_precision(frappe.get_meta("Leave Allocation").get_field("new_leaves_allocated"))
    current_date = getdate(frappe.flags.current_date) or getdate()

    # Earned Leaves and Compensatory Leaves are allocated by scheduler, initially allocate 0
    if leave_details.is_compensatory:
        new_leaves_allocated = 0

    elif leave_details.is_earned_leave and current_date < getdate(self.effective_to):
        # ========== NEW: ELIGIBILITY CHECK ==========
        eligibility_result = is_employee_eligible_for_earned_leave(
            self.employee,
            current_date,
            leave_details.name
        )

        if not eligibility_result["is_eligible"]:
            # Not yet eligible - scheduler will allocate later when eligible
            new_leaves_allocated = 0
            frappe.msgprint(
                f"Earned leave for {leave_details.name} will start from "
                f"{eligibility_result['eligibility_date']} ({eligibility_result['reason']})",
                indicator="blue",
                alert=True
            )
        else:
            # Eligible - calculate leaves for passed periods from eligibility_date
            new_leaves_allocated = self.get_leaves_for_passed_period_from_eligibility(
                annual_allocation, leave_details, date_of_joining, eligibility_result["eligibility_date"]
            )
        # ========== END NEW ==========
    else:
        # calculate pro-rated leaves for other leave types
        new_leaves_allocated = calculate_pro_rated_leaves(
            annual_allocation,
            date_of_joining,
            self.effective_from,
            self.effective_to,
            is_earned_leave=False,
        )

    # leave allocation should not exceed annual allocation as per policy assignment
    # except when allocation is of earned type and yearly
    if new_leaves_allocated > annual_allocation and not (
        leave_details.is_earned_leave and leave_details.earned_leave_frequency == "Yearly"
    ):
        new_leaves_allocated = annual_allocation

    # Clean up
    if hasattr(self, '_current_leave_details'):
        delattr(self, '_current_leave_details')

    return flt(new_leaves_allocated, precision)


def get_leaves_for_passed_period_from_eligibility(
    self, annual_allocation, leave_details, date_of_joining, eligibility_date
):
    """
    Calculate earned leaves for periods that have passed since eligibility_date.

    This is used when Leave Policy Assignment is created after the employee
    has become eligible for earned leave.

    Logic:
    - Support all allocate_on_day options (First Day, Last Day, DOJ, 15th)
    - Calculate annual allocation with seniority bonus
    - Use bonus months strategy for distribution
    - Sum up allocation for each eligible month that has passed

    Args:
        annual_allocation: Annual allocation from Leave Policy (base, without seniority)
        leave_details: Leave type details
        date_of_joining: Employee's date of joining
        eligibility_date: Date when employee became eligible

    Returns:
        float: Number of leaves to allocate
    """
    from customize_erpnext.overrides.earned_leave.earned_leave_config import (
        get_annual_allocation_with_seniority,
    )

    current_date = getdate(frappe.flags.current_date) or getdate()
    doj = getdate(date_of_joining)

    total_annual = get_annual_allocation_with_seniority(
        annual_allocation, doj, current_date
    )

    # Dùng chung bộ dựng lịch với custom_get_earned_leave_schedule() để hai bên không lệch:
    # phần "đã qua" chính là tổng các kỳ có ngày cấp <= hôm nay.
    rows = build_earned_leave_rows(
        self.employee,
        total_annual,
        self.effective_from,
        self.effective_to,
        doj,
        eligibility_date,
    )

    return flt(
        sum(r["number_of_leaves"] for r in rows if getdate(r["allocation_date"]) <= current_date),
        2,
    )


# =============================================================================
# SCHEDULER OVERRIDE
# =============================================================================

def custom_allocate_earned_leaves():
    """
    Custom version of allocate_earned_leaves with eligibility check and
    new allocation logic (1 day/month + bonus in June/December).

    This function is called by the scheduler (hourly) to allocate earned leaves.

    Changes from original (hrms.hr.utils.allocate_earned_leaves):
    1. Added eligibility check before allocating
    2. Skip allocation if employee not yet eligible (probation not completed)
    3. Use new allocation: 1 day/month, 2 days in June & December
    4. Log skipped allocations for debugging

    Original function: hrms.hr.utils.allocate_earned_leaves
    """
    from frappe.utils import flt, comma_and, get_link_to_form
    from frappe.query_builder.functions import Count
    from hrms.hr.utils import (
        get_earned_leaves,
        get_leave_allocations,
        get_upcoming_earned_leave_from_schedule,
        get_annual_allocation_from_policy,
        log_allocation_error,
        create_additional_leave_ledger_entry,
        OverAllocationError,
    )
    from customize_erpnext.overrides.earned_leave.earned_leave_eligibility import (
        is_employee_eligible_for_earned_leave,
        log_eligibility_skip,
    )
    from customize_erpnext.overrides.earned_leave.earned_leave_config import (
        get_monthly_allocation_for_month,
        get_annual_allocation_with_seniority,
    )

    e_leave_types = get_earned_leaves()
    today = frappe.flags.current_date or getdate()
    failed_allocations = []
    skipped_allocations = []
    successful_allocations = []

    for e_leave_type in e_leave_types:
        leave_allocations = get_leave_allocations(today, e_leave_type.name)

        for allocation in leave_allocations:
            # Get employee info
            emp_info = frappe.db.get_value(
                "Employee", allocation.employee,
                ["date_of_joining"], as_dict=True
            )
            date_of_joining = emp_info.date_of_joining if emp_info else None

            # Determine allocation date
            if allocation.earned_leave_schedule_exists:
                allocation_date, scheduled_leaves = get_upcoming_earned_leave_from_schedule(
                    allocation.name, today
                ) or (None, None)
                base_annual_allocation = get_annual_allocation_from_policy(allocation, e_leave_type)
            else:
                allocation_date = custom_get_expected_allocation_date_for_period(
                    e_leave_type.earned_leave_frequency,
                    e_leave_type.allocate_on_day,
                    today,
                    date_of_joining
                )
                base_annual_allocation = get_annual_allocation_from_policy(allocation, e_leave_type)

            if not allocation_date or allocation_date != today:
                continue

            # ========== ELIGIBILITY CHECK ==========
            eligibility_result = is_employee_eligible_for_earned_leave(
                allocation.employee,
                allocation_date,
                e_leave_type.name
            )

            if not eligibility_result["is_eligible"]:
                # Log and skip
                log_eligibility_skip(
                    allocation.employee,
                    allocation_date,
                    e_leave_type.name,
                    eligibility_result
                )
                skipped_allocations.append({
                    "employee": allocation.employee,
                    "leave_type": e_leave_type.name,
                    "eligibility_date": eligibility_result["eligibility_date"],
                    "reason": eligibility_result["reason"]
                })
                continue

            # ========== CALCULATE MONTHLY ALLOCATION WITH SENIORITY ==========
            # Calculate annual allocation with seniority bonus
            annual_allocation = get_annual_allocation_with_seniority(
                base_annual_allocation, date_of_joining, today
            ) if date_of_joining else base_annual_allocation

            # Ưu tiên số đã lên lịch trong Earned Leave Schedule: kỳ tháng 12 đã được
            # điều chỉnh cho khớp tổng năm (_true_up_december), tính lại ở đây sẽ ra con số
            # khác và làm cả năm cộng không đủ annual_allocation.
            if allocation.earned_leave_schedule_exists and scheduled_leaves is not None:
                earned_leaves = flt(scheduled_leaves)
            else:
                earned_leaves = get_monthly_allocation_for_month(today.month, annual_allocation)

            try:
                # Update allocation using custom logic
                custom_update_leave_allocation(
                    allocation, annual_allocation, e_leave_type, earned_leaves, today
                )
                successful_allocations.append({
                    "employee": allocation.employee,
                    "leave_type": e_leave_type.name,
                    "leaves": earned_leaves,
                    "month": today.month
                })
            except Exception as e:
                log_allocation_error(allocation.name, e)
                failed_allocations.append(allocation.name)

    if failed_allocations:
        notify_failed_allocations(failed_allocations)

    # Log summary
    if skipped_allocations:
        frappe.log_error(
            message=f"Skipped {len(skipped_allocations)} allocations due to eligibility:\n" +
                    "\n".join([f"- {s['employee']}: {s['leave_type']} (eligible from {s['eligibility_date']})"
                              for s in skipped_allocations]),
            title="Earned Leave Eligibility - Daily Summary"
        )

    if successful_allocations:
        frappe.logger().info(
            f"Allocated earned leaves for {len(successful_allocations)} employees:\n" +
            "\n".join([f"- {s['employee']}: {s['leaves']} days (month {s['month']})"
                      for s in successful_allocations])
        )


def notify_failed_allocations(failed_allocations):
    """Tell whoever is configured that the nightly allocation had failures.

    Replaces the HRMS version, which mails every enabled user holding the HR
    Manager role. That list is not a subscription anyone opted into — it grows
    silently as roles are handed out, and on this site it already carried the
    `Administrator` username, which is not an address: MS 365 answered
    "501 Invalid address" and refused the whole batch, so nobody was told
    anything at all.

    Recipients come from HR Settings > Earned Leave Alert Recipients. Blank
    means send nothing: an alert must never guess who should read it.
    """
    recipients = [
        r.strip()
        for r in str(
            frappe.db.get_single_value("HR Settings", "custom_earned_leave_alert_recipients") or ""
        )
        .replace("\n", ",")
        .split(",")
        if r.strip()
    ]
    if not recipients:
        frappe.logger().warning(
            f"{len(failed_allocations)} earned leave allocations failed but "
            "HR Settings > Earned Leave Alert Recipients is empty; no mail sent"
        )
        return

    from frappe.utils import comma_and, get_link_to_form

    frappe.sendmail(
        recipients=recipients,
        subject=_("Failure of Automatic Allocation of Earned Leaves"),
        message=_(
            "Automatic Leave Allocation has failed for the following Earned Leaves: {0}. "
            "Please check {1} for more details."
        ).format(
            comma_and([get_link_to_form("Leave Allocation", x) for x in failed_allocations]),
            get_link_to_form("Error Log", label="Error Log List"),
        ),
    )


def custom_update_leave_allocation(allocation, annual_allocation, e_leave_type, earned_leaves, today):
    """
    Custom update function for leave allocation with new allocation logic.

    Args:
        allocation: Leave Allocation record
        annual_allocation: Annual allocation from policy
        e_leave_type: Leave Type details
        earned_leaves: Number of leaves to allocate (1 or 2)
        today: Current date
    """
    from frappe.utils import flt
    from hrms.hr.utils import (
        create_additional_leave_ledger_entry,
        OverAllocationError,
    )

    allocation_doc = frappe.get_doc("Leave Allocation", allocation.name)
    precision = allocation_doc.precision("total_leaves_allocated")

    new_allocation = flt(allocation_doc.total_leaves_allocated) + flt(earned_leaves)
    new_allocation_without_cf = flt(
        flt(allocation_doc.get_existing_leave_count()) + flt(earned_leaves),
        precision,
    )

    # Check max_leaves_allowed
    if new_allocation > e_leave_type.max_leaves_allowed and e_leave_type.max_leaves_allowed > 0:
        frappe.throw(
            _(
                "Allocation was skipped due to maximum leave allocation limit set in leave type. Please increase the limit and retry failed allocation."
            ),
            OverAllocationError,
        )

    # Check annual allocation (skip for yearly frequency)
    if (
        new_allocation_without_cf > annual_allocation and e_leave_type.earned_leave_frequency != "Yearly"
    ):
        frappe.throw(
            _("Allocation was skipped due to exceeding annual allocation set in leave policy"),
            OverAllocationError,
        )

    # Update allocation
    allocation_doc.db_set("total_leaves_allocated", new_allocation, update_modified=False)
    create_additional_leave_ledger_entry(allocation_doc, earned_leaves, today)

    # Update schedule if exists
    earned_leave_schedule = frappe.qb.DocType("Earned Leave Schedule")
    frappe.qb.update(earned_leave_schedule).where(
        (earned_leave_schedule.parent == allocation.name) & (earned_leave_schedule.allocation_date == today)
    ).set(earned_leave_schedule.is_allocated, 1).set(earned_leave_schedule.attempted, 1).set(
        earned_leave_schedule.allocated_via, "Scheduler"
    ).run()


# =============================================================================
# EARNED LEAVE SCHEDULE OVERRIDE
# =============================================================================

def custom_get_earned_leave_schedule(
    self, annual_allocation, leave_details, date_of_joining, new_leaves_allocated
):
    """
    Custom version of get_earned_leave_schedule that considers eligibility
    and uses new allocation logic with seniority bonus.

    Logic:
    1. On LPA creation: Calculate total leaves for past allocation dates (lump sum)
    2. Future: Scheduler allocates on configured allocation day each month

    Schedule only shows:
    - Row 1: Initial allocation (if any) on LPA creation date
    - Row 2+: Future allocation dates for scheduler

    Supports all allocate_on_day options:
    - First Day, Last Day, Date of Joining, 15th of Month

    Original method: LeavePolicyAssignment.get_earned_leave_schedule
    """
    from customize_erpnext.overrides.earned_leave.earned_leave_eligibility import (
        is_employee_eligible_for_earned_leave,
    )
    from customize_erpnext.overrides.earned_leave.earned_leave_config import (
        get_annual_allocation_with_seniority,
    )

    today = getdate(frappe.flags.current_date) or getdate()
    from_date = getdate(self.effective_from)
    doj = getdate(date_of_joining) if date_of_joining else None

    total_annual = get_annual_allocation_with_seniority(
        annual_allocation, doj, today
    ) if doj else annual_allocation

    eligibility_result = is_employee_eligible_for_earned_leave(
        self.employee, from_date, leave_details.name
    )
    eligibility_date = eligibility_result["eligibility_date"] or from_date

    rows = build_earned_leave_rows(
        self.employee, total_annual, from_date, self.effective_to, doj, eligibility_date
    )

    schedule = []
    past = [r for r in rows if getdate(r["allocation_date"]) <= today]
    future = [r for r in rows if getdate(r["allocation_date"]) > today]

    # Các kỳ đã qua được cấp gộp một lần vào hôm nay (giá trị này chính là
    # new_leaves_allocated do get_leaves_for_passed_period_from_eligibility trả về —
    # cùng nguồn build_earned_leave_rows nên luôn khớp).
    if past:
        schedule.append({
            "allocation_date": today,
            "number_of_leaves": flt(sum(r["number_of_leaves"] for r in past), 2),
            "is_allocated": 1,
            "allocated_via": "Leave Policy Assignment",
            "attempted": 1,
        })

    for r in future:
        schedule.append({
            "allocation_date": r["allocation_date"],
            "number_of_leaves": r["number_of_leaves"],
            "is_allocated": 0,
            "allocated_via": None,
            "attempted": 0,
        })

    return schedule


def build_earned_leave_rows(
    employee, annual_allocation, period_from, period_to, date_of_joining, eligibility_date
):
    """Nguồn sự thật DUY NHẤT cho lịch cấp phép năm của một kỳ.

    Cả `get_leaves_for_passed_period_from_eligibility()` (phần đã qua, cấp gộp lúc tạo LPA)
    lẫn `custom_get_earned_leave_schedule()` (phần còn lại) đều gọi hàm này, nên hai bên
    không thể lệch nhau.

    Quy tắc (xem earned_leave_override.md):
      1. Kỳ cấp = ngày 15 của mỗi tháng ĐỦ ĐIỀU KIỆN nằm trong kỳ phép.
      2. Các tháng rơi vào thời gian thử việc KHÔNG mất — được **truy thu** gộp vào kỳ cấp
         đầu tiên sau ngày hết thử việc.
      3. Tổng cả lịch = quyền lợi cả kỳ đã làm tròn theo Điều 66; kỳ cuối gánh phần dư.

    Trả về list[dict] đã sắp theo ngày, mỗi dict có allocation_date + number_of_leaves.
    """
    from frappe.utils import add_months
    from customize_erpnext.overrides.earned_leave.earned_leave_config import (
        QUALIFYING_DAY_OF_MONTH,
        get_monthly_rate,
        get_period_entitlement,
        is_working_month,
    )

    period_from, period_to = getdate(period_from), getdate(period_to)
    doj = getdate(date_of_joining) if date_of_joining else None
    eligibility_date = getdate(eligibility_date) if eligibility_date else period_from
    relieving_date = frappe.db.get_value("Employee", employee, "relieving_date")

    entitlement = get_period_entitlement(
        annual_allocation, period_from, period_to, doj, relieving_date
    )
    if not entitlement:
        return []

    # Mọi kỳ cấp đủ điều kiện trong kỳ phép
    qualifying = []
    cursor = datetime.date(period_from.year, period_from.month, QUALIFYING_DAY_OF_MONTH)
    while cursor <= period_to:
        if cursor >= period_from and is_working_month(cursor, doj, relieving_date):
            qualifying.append(cursor)
        cursor = getdate(add_months(cursor, 1))

    if not qualifying:
        return []

    # Tách phần bị thử việc chặn — KHÔNG bỏ, dồn vào kỳ cấp đầu tiên sau khi hết thử việc
    deferred = [d for d in qualifying if d < eligibility_date]
    payable = [d for d in qualifying if d >= eligibility_date]

    if not payable:
        # Hết thử việc sau kỳ cấp cuối cùng (vd vào làm cuối tháng 11). Không được để mất:
        # cấp bù đúng ngày hết thử việc, miễn là còn nằm trong kỳ phép.
        if eligibility_date > period_to:
            return []
        payable = [eligibility_date]

    monthly = get_monthly_rate(annual_allocation)
    rows = []
    for idx, d in enumerate(payable):
        months = 1 + len(deferred) if idx == 0 else 1
        rows.append({"allocation_date": d, "number_of_leaves": flt(monthly * months, 2)})

    _true_up_last_period(rows, entitlement)
    return rows


def _true_up_last_period(schedule, entitlement):
    """Kỳ **cuối cùng** gánh phần dư để tổng lịch đúng bằng `entitlement`.

    Các kỳ khác cấp theo `annual/12` làm tròn 2 chữ số nên cộng lại luôn lệch chút ít so với
    quyền lợi đã làm tròn theo Điều 66. Dồn hết chênh lệch vào kỳ cuối.

    ⚠ Khác hẳn `_true_up_december()` cũ: hàm cũ dồn về `total_annual` (nguyên năm) **vô điều
    kiện**, nên người làm 5 tháng vẫn nhận đủ 14 ngày. Nay dồn về `entitlement` đã tính theo
    tỷ lệ số tháng thực làm.
    """
    if not schedule:
        return

    last = len(schedule) - 1
    others = sum(flt(r["number_of_leaves"]) for i, r in enumerate(schedule) if i != last)
    schedule[last]["number_of_leaves"] = flt(flt(entitlement) - others, 2)

    # Không để kỳ cuối âm khi các kỳ trước đã vượt quyền lợi (làm tròn xuống)
    if schedule[last]["number_of_leaves"] < 0:
        schedule[last]["number_of_leaves"] = 0.0


def _true_up_december(schedule, total_annual):
    """⚠ ĐÃ BỎ 15/08/2026 — giữ lại để không vỡ import cũ. Dùng `_true_up_last_period()`.

    Hàm này đặt kỳ tháng 12 = `total_annual − tổng các kỳ khác` **vô điều kiện**, nên nhân
    viên vào làm giữa kỳ vẫn nhận đủ phép cả năm (đo 15/08/2026: 379 NV, thừa ~2.022 ngày).

    Các kỳ khác cấp theo tỷ lệ `annual/12` làm tròn xuống 1 chữ số nên cộng lại luôn **thiếu**
    (14 -> 11×1,1 = 12,1). Phần thiếu dồn hết vào tháng 12.

    Tính bằng `annual − tổng các kỳ khác` chứ không dùng công thức cố định `annual − 11×1,1`,
    vì lịch thật có thể có **kỳ gộp** (nhiều tháng đã qua gộp làm một dòng) hoặc **năm không
    trọn** (vào làm giữa năm, hoặc chưa đủ điều kiện mấy tháng đầu).
    """
    if not schedule:
        return

    december_idx = None
    for i, row in enumerate(schedule):
        if getdate(row["allocation_date"]).month == 12:
            december_idx = i
    # Không có kỳ tháng 12 -> dồn vào kỳ cuối, để tổng vẫn khớp thay vì thiếu âm thầm
    if december_idx is None:
        december_idx = len(schedule) - 1

    others = sum(
        flt(r["number_of_leaves"]) for i, r in enumerate(schedule) if i != december_idx
    )
    schedule[december_idx]["number_of_leaves"] = flt(flt(total_annual) - others, 1)


print("✅ Earned Leave functions loaded")




# =============================================================================
# BACKFILL — chuyển lịch cũ (tháng bonus, số nguyên) sang tỷ lệ 1 chữ số thập phân
# =============================================================================


def rebalance_earned_leave_schedule(dry_run: int = 1, batch_size: int = 200):
	"""Tính lại `number_of_leaves` cho các kỳ **CHƯA cấp**, rồi điều chỉnh tháng 12.

	🔴 **Không đụng kỳ đã cấp** (`is_allocated = 1`): mỗi kỳ đó đã sinh một
	`Leave Ledger Entry` tương ứng. Sửa số trên lịch mà không sửa sổ cái sẽ làm hai bên
	lệch nhau, và sổ cái mới là thứ quyết định số dư phép.

	Vì vậy tháng 12 gánh **toàn bộ** phần chênh:

	    tháng 12 = annual − (tổng kỳ ĐÃ cấp) − (tổng kỳ chưa cấp khác × tỷ lệ mới)

	Nhờ đó tổng cả năm vẫn đúng `annual` dù các kỳ đầu năm đã cấp theo cách cũ.
	"""
	from customize_erpnext.overrides.earned_leave.earned_leave_config import (
		get_monthly_allocation_for_month,
	)

	dry_run = int(dry_run)
	parents = {
		r.parent for r in frappe.get_all(
			"Earned Leave Schedule", fields=["parent"], group_by="parent"
		)
	}
	names = [
		r.name for r in frappe.get_all(
			"Leave Allocation", filters={"docstatus": 1}, fields=["name"], order_by="name"
		)
		if r.name in parents
	]
	print(f"Leave Allocation (submitted) có lịch: {len(names)}")

	changed = unchanged = 0
	problems = []
	for i, name in enumerate(names, 1):
		doc = frappe.get_doc("Leave Allocation", name)
		rows = doc.get("earned_leave_schedule") or []
		if not rows:
			continue

		annual = flt(doc.total_leaves_allocated)
		# total_leaves_allocated chỉ phản ánh phần ĐÃ cấp; mức năm là tổng của lịch cũ
		annual_target = sum(flt(r.number_of_leaves) for r in rows)

		monthly = get_monthly_allocation_for_month(1, annual_target)
		pending = [r for r in rows if not r.is_allocated]
		if not pending:
			unchanged += 1
			continue

		december = None
		for r in pending:
			if getdate(r.allocation_date).month == 12:
				december = r
		if december is None:
			december = pending[-1]

		new_values = {}
		for r in pending:
			if r.name != december.name:
				new_values[r.name] = monthly
		allocated_total = sum(flt(r.number_of_leaves) for r in rows if r.is_allocated)
		new_values[december.name] = flt(
			annual_target - allocated_total - sum(new_values.values()), 1
		)

		if new_values[december.name] < 0:
			problems.append((name, annual_target, allocated_total,
			                 new_values[december.name]))
			continue

		if not dry_run:
			for row_name, v in new_values.items():
				frappe.db.set_value("Earned Leave Schedule", row_name,
				                    "number_of_leaves", v, update_modified=False)
		changed += 1
		if not dry_run and i % batch_size == 0:
			frappe.db.commit()
			print(f"  ... {i}/{len(names)}")

	if not dry_run:
		frappe.db.commit()
	print(f"{'[DRY RUN] ' if dry_run else ''}cập nhật: {changed} | "
	      f"không còn kỳ chờ: {unchanged} | ⚠ tháng 12 ÂM: {len(problems)}")
	for p in problems[:10]:
		print(f"   ⚠ {p[0]}: năm={p[1]}, đã cấp={p[2]}, tháng 12 ra {p[3]}")
	return {"changed": changed, "unchanged": unchanged, "problems": problems[:50]}
