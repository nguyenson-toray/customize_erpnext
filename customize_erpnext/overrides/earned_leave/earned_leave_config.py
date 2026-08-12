# Copyright (c) 2025, IT Team - TIQN
# License: MIT

"""
Earned Leave Configuration

Constants and helper functions for earned leave allocation.
Centralized configuration to avoid hard-coding values.

Allocation Rules (TIQN + Vietnamese Labor Law):
- Base: From Leave Type.max_leaves_allowed (default 14 days)
- Seniority: +1 day per 5 years (Điều 114 BLLĐ 2019)
- Strategy: Bonus months (June, December get extra)
- Eligibility: After probation period
- If not eligible in a month, skip it (no accumulation)
"""

import datetime
import calendar
from frappe.utils import flt, getdate, get_first_day, get_last_day

# =============================================================================
# SENIORITY CONFIGURATION (Vietnamese Labor Law - Điều 114 BLLĐ 2019)
# =============================================================================

# Enable seniority bonus calculation
ENABLE_SENIORITY_BONUS = True

# Years of service required for each bonus day
SENIORITY_YEARS_PER_BONUS = 5  # Every 5 years = +1 day

# Bonus days per seniority milestone
SENIORITY_BONUS_DAYS = 1


# =============================================================================
# ALLOCATION STRATEGY CONFIGURATION
# =============================================================================

# Base annual allocation (used for distribution calculation)
# This is the standard without seniority bonus
BASE_ANNUAL_ALLOCATION = 14

# Tháng gánh phần chênh khi chia annual cho 12 (xem get_monthly_allocation_for_month)
ADJUSTMENT_MONTH = 12

# ❌ Đã bỏ 10/08/2026: chiến lược "tháng bonus" (BONUS_MONTHS / STANDARD_MONTHLY_ALLOCATION /
# BASE_BONUS_ALLOCATION) cấp số nguyên 1 ngày/tháng, tháng 6 và 12 mỗi tháng 2 ngày.
# Nay cấp theo TỶ LỆ làm tròn xuống 1 chữ số thập phân, tháng 12 điều chỉnh cho khớp tổng.


# =============================================================================
# SENIORITY FUNCTIONS
# =============================================================================

def calculate_seniority_years(date_of_joining, reference_date):
    """
    Calculate years of service from DOJ to reference date.

    Args:
        date_of_joining: Employee's date of joining
        reference_date: Date to calculate seniority up to (usually LPA creation date)

    Returns:
        float: Years of service
    """
    doj = getdate(date_of_joining)
    ref = getdate(reference_date)

    if ref < doj:
        return 0

    return (ref - doj).days / 365.0


def calculate_seniority_bonus(date_of_joining, reference_date):
    """
    Calculate seniority bonus based on years worked.

    Vietnamese Labor Law (Điều 114 BLLĐ 2019):
    - Every 5 years of service = +1 day annual leave

    Args:
        date_of_joining: Employee's date of joining (probation counts)
        reference_date: Date to calculate seniority up to (LPA creation date)

    Returns:
        int: Number of bonus days (0, 1, 2, 3, ...)

    Example:
        DOJ 01/03/2020, Ref 01/03/2026 → 6 years → bonus = 1
        DOJ 01/03/2020, Ref 01/03/2031 → 11 years → bonus = 2
    """
    if not ENABLE_SENIORITY_BONUS:
        return 0

    years_worked = calculate_seniority_years(date_of_joining, reference_date)

    if years_worked < SENIORITY_YEARS_PER_BONUS:
        return 0

    return int(years_worked // SENIORITY_YEARS_PER_BONUS) * SENIORITY_BONUS_DAYS


def get_annual_allocation_with_seniority(base_allocation, date_of_joining, reference_date):
    """
    Calculate total annual allocation including seniority bonus.

    Args:
        base_allocation: Base annual leave from Leave Type.max_leaves_allowed
        date_of_joining: Employee's DOJ
        reference_date: LPA creation date

    Returns:
        int: Total annual allocation
    """
    seniority_bonus = calculate_seniority_bonus(date_of_joining, reference_date)
    return base_allocation + seniority_bonus


# =============================================================================
# MONTHLY ALLOCATION FUNCTIONS
# =============================================================================

def get_monthly_allocation_for_month(month, annual_allocation=None):
    """Số ngày phép tích luỹ của một tháng — **theo tỷ lệ**, làm tròn XUỐNG 1 chữ số thập phân.

    `annual / 12`, floor 1 chữ số. **Tháng 12 gánh phần chênh** để cả năm cộng lại đúng
    bằng `annual_allocation`.

        14 ngày/năm -> 1,1/tháng · tháng 12 = 14 − 11×1,1 = 1,9
        15 ngày/năm -> 1,2/tháng · tháng 12 = 15 − 11×1,2 = 1,8
        16 ngày/năm -> 1,3/tháng · tháng 12 = 16 − 11×1,3 = 1,7

    Trước 10/08/2026 hàm này chia theo "tháng bonus" (10 tháng × 1 ngày, tháng 6 và 12 mỗi
    tháng 2 ngày). Cách đó cho số dư tròn ngày nhưng **không phản ánh mức tích luỹ thực** —
    nghỉ việc cuối tháng 6 được tính 7 ngày trong khi theo tỷ lệ chỉ 6,9.

    ⚠ Tháng 12 ở đây là mức **chuẩn** khi cả 11 tháng trước đều đã cấp đủ theo tỷ lệ.
    Lịch cấp thực tế (`Earned Leave Schedule`) tính lại tháng 12 = `annual − tổng các kỳ khác`
    để đúng cả khi có kỳ gộp hoặc năm không trọn.
    """
    import math

    if annual_allocation is None:
        annual_allocation = BASE_ANNUAL_ALLOCATION

    annual = flt(annual_allocation)
    # floor 1 chữ số; +epsilon để 1,2 không bị nhị phân đẩy xuống 1,1
    monthly = math.floor(annual / 12 * 10 + 1e-9) / 10

    if month == 12:
        return flt(annual - monthly * 11, 1)
    return monthly


# Số ngày làm việc tối thiểu trong một tháng dương lịch để tháng đó được tính là
# "01 tháng làm việc thực tế" — Điều 66 Nghị định 145/2020/NĐ-CP.
MIN_DAYS_FOR_WORKING_MONTH = 14


def count_worked_days_in_month(any_date_in_month, date_of_joining, relieving_date=None):
    """Số ngày người lao động thực sự thuộc biên chế trong tháng dương lịch chứa `any_date_in_month`."""
    month_start = get_first_day(getdate(any_date_in_month))
    month_end = get_last_day(getdate(any_date_in_month))

    start = max(month_start, getdate(date_of_joining)) if date_of_joining else month_start
    end = min(month_end, getdate(relieving_date)) if relieving_date else month_end

    if start > end:
        return 0
    return (end - start).days + 1


def is_working_month(any_date_in_month, date_of_joining, relieving_date=None):
    """Tháng này có được tính là **01 tháng làm việc thực tế** không?

    Điều 66 NĐ 145/2020: làm **từ đủ 14 ngày trở lên** trong tháng dương lịch thì tháng đó
    tính là một tháng; dưới 14 ngày thì **không tính**.

    Chạm tới hai đầu: tháng vào làm (DOJ giữa tháng) và tháng nghỉ việc.
    """
    return count_worked_days_in_month(
        any_date_in_month, date_of_joining, relieving_date
    ) >= MIN_DAYS_FOR_WORKING_MONTH


def get_annual_allocation_breakdown(annual_allocation=None):
    """
    Get breakdown of annual allocation by month.

    Args:
        annual_allocation: Total annual allocation

    Returns:
        dict: {month: allocation} for all 12 months
    """
    if annual_allocation is None:
        annual_allocation = BASE_ANNUAL_ALLOCATION

    return {
        month: get_monthly_allocation_for_month(month, annual_allocation)
        for month in range(1, 13)
    }


def get_total_from_breakdown(annual_allocation=None):
    """
    Calculate total from monthly breakdown (for verification).
    """
    return sum(get_annual_allocation_breakdown(annual_allocation).values())


# =============================================================================
# ALLOCATION DATE FUNCTIONS (Support all allocate_on_day options)
# =============================================================================

def get_allocation_date_for_month(date, allocate_on_day, date_of_joining=None):
    """
    Get allocation date for a month based on allocate_on_day option.

    Args:
        date: Any date in the target month
        allocate_on_day: "First Day", "Last Day", "Date of Joining", "15th of Month"
        date_of_joining: Employee's DOJ (required for "Date of Joining" option)

    Returns:
        datetime.date: Allocation date for that month
    """
    date = getdate(date)

    if allocate_on_day == "First Day":
        return get_first_day(date)

    elif allocate_on_day == "Last Day":
        return get_last_day(date)

    elif allocate_on_day == "Date of Joining":
        if not date_of_joining:
            # Fallback to first day if DOJ not provided
            return get_first_day(date)

        doj = getdate(date_of_joining)
        doj_day = doj.day

        # Handle edge cases (e.g., DOJ is 31st but current month has 30 days)
        max_day = calendar.monthrange(date.year, date.month)[1]
        day = min(doj_day, max_day)

        return datetime.date(date.year, date.month, day)

    elif allocate_on_day == "15th of Month":
        return datetime.date(date.year, date.month, 15)

    else:
        # Default to first day
        return get_first_day(date)


def get_next_allocation_date(current_date, allocate_on_day, date_of_joining=None):
    """
    Get the next allocation date after current_date.

    Args:
        current_date: Current date
        allocate_on_day: Allocation day option
        date_of_joining: Employee's DOJ

    Returns:
        datetime.date: Next allocation date
    """
    from frappe.utils import add_months

    current_date = getdate(current_date)

    # Get allocation date for current month
    current_month_alloc = get_allocation_date_for_month(
        current_date, allocate_on_day, date_of_joining
    )

    # If current month's allocation date hasn't passed, return it
    if current_month_alloc > current_date:
        return current_month_alloc

    # Otherwise, return next month's allocation date
    next_month = add_months(current_date, 1)
    return get_allocation_date_for_month(next_month, allocate_on_day, date_of_joining)


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def round_earned_leaves(earned_leaves, rounding):
    """
    Round earned leaves based on rounding option.

    Args:
        earned_leaves: Number of leaves to round
        rounding: "0.25", "0.5", "1.0", or None

    Returns:
        float: Rounded leaves
    """
    if not rounding:
        return earned_leaves

    if rounding == "0.25":
        return round(earned_leaves * 4) / 4
    elif rounding == "0.5":
        return round(earned_leaves * 2) / 2
    else:  # "1.0"
        return round(earned_leaves)


# Legacy function for compatibility
def get_monthly_allocation(max_leaves_allowed, rounding=None):
    """Legacy — dùng `get_monthly_allocation_for_month()` để có số đúng theo tháng."""
    return get_monthly_allocation_for_month(1, max_leaves_allowed)


# =============================================================================
# DEBUG/VERIFICATION
# =============================================================================

print("✅ Earned Leave Config loaded")
# print(f"   Seniority bonus: {'Enabled' if ENABLE_SENIORITY_BONUS else 'Disabled'}")
# print(f"   Base annual: {BASE_ANNUAL_ALLOCATION} days")
# print(f"   Example (14 days): {get_annual_allocation_breakdown(14)}")
# print(f"   Example (15 days): {get_annual_allocation_breakdown(15)}")
# print(f"   Example (16 days): {get_annual_allocation_breakdown(16)}")
