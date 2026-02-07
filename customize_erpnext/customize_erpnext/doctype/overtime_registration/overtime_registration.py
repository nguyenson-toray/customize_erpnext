# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_time, time_diff_in_hours, getdate
from frappe import _
from datetime import time, datetime, timedelta

class OvertimeRegistration(Document):
    def validate(self):
        """Validation khi lưu (Save) - theo thứ tự"""
        # 1. Kiểm tra giờ OT phải nằm ngoài giờ làm việc (bỏ qua ngày chủ nhật)
        self.validate_ot_outside_working_hours()

        # 2. Kiểm tra các trường hợp thai sản (handled by JS maternity dialog)

        # 3. Duplicate trong form
        self.validate_duplicate_employees()

        # 4. Overlap với OT đã submit
        self.validate_conflicting_ot_requests()

        # 5. Liên tục với OT cùng ngày
        self.validate_ot_continuity_same_day()

        # Calculate totals
        self.calculate_totals_and_apply_reason()

    def validate_ot_outside_working_hours(self):
        """Validate OT must be outside working hours"""
        if not self.ot_employees:
            return

        for d in self.ot_employees:
            if not d.employee or not d.date or not d.get("begin_time") or not d.get("end_time"):
                continue

            # Skip validation for Sundays
            date_obj = getdate(d.date)
            if date_obj.weekday() == 6:  # Sunday
                continue

            # Get shift for employee
            shift_type, _source = get_shift_type(d.employee, d.date)
            shift_config = get_shift_config(shift_type)

            if not shift_config:
                continue

            # Check if shift allows OT
            if not shift_config.get("allows_ot", True):
                frappe.throw(_("Row #{0}: Ca {1} không được phép đăng ký tăng ca").format(d.idx, shift_type))

            # Check if employee has maternity benefit
            has_benefit, _type, _from, _to = check_maternity_benefit(d.employee, d.date)

            # Validate OT is outside working hours (relaxed mode)
            is_valid, error_msg = validate_ot_continuity_with_shift(
                d.get("begin_time"), d.get("end_time"), shift_config, has_benefit, None, strict_mode=False
            )

            if not is_valid:
                frappe.throw(_("Row #{0}: {1}").format(d.idx, error_msg))

    def validate_ot_continuity_same_day(self):
        """Validate OT entries are continuous with each other on the same day"""
        if not self.ot_employees:
            return

        # Group entries by employee and date
        employee_date_entries = {}
        for d in self.ot_employees:
            if not d.employee or not d.date or not d.get("begin_time") or not d.get("end_time"):
                continue

            key = f"{d.employee}_{d.date}"
            if key not in employee_date_entries:
                employee_date_entries[key] = []
            employee_date_entries[key].append(d)

        # Check continuity for each employee-date group with multiple entries
        for key, entries in employee_date_entries.items():
            if len(entries) <= 1:
                continue

            # Sort entries by begin_time
            sorted_entries = sorted(entries, key=lambda x: get_time(x.get("begin_time")))

            # Get shift info
            employee = sorted_entries[0].employee
            date = sorted_entries[0].date
            shift_type, _source = get_shift_type(employee, date)
            shift_config = get_shift_config(shift_type)

            if not shift_config:
                continue

            has_benefit, _type, _from, _to = check_maternity_benefit(employee, date)

            # For maternity, shift ends 1 hour earlier
            if has_benefit:
                shift_end_dt = datetime.combine(datetime.today(), shift_config["end"])
                effective_shift_end = (shift_end_dt - timedelta(hours=1)).time()
            else:
                effective_shift_end = shift_config["end"]

            # Check first entry starts at shift end
            first_entry = sorted_entries[0]
            first_begin = get_time(first_entry.get("begin_time"))

            if first_begin != effective_shift_end:
                frappe.throw(_("Row #{0}: Giờ tăng ca đầu tiên phải bắt đầu ngay sau ca ({1})").format(
                    first_entry.idx, effective_shift_end.strftime("%H:%M")
                ))

            # Check each subsequent entry is continuous with previous
            for i in range(1, len(sorted_entries)):
                prev_entry = sorted_entries[i - 1]
                curr_entry = sorted_entries[i]

                prev_end = get_time(prev_entry.get("end_time"))
                curr_begin = get_time(curr_entry.get("begin_time"))

                if curr_begin != prev_end:
                    frappe.throw(_("Row #{0}: Giờ tăng ca phải liên tục với OT trước đó (Row #{1} kết thúc lúc {2})").format(
                        curr_entry.idx, prev_entry.idx, prev_end.strftime("%H:%M")
                    ))

    def validate_ot_continuity_strict(self):
        """Validate that all OT entries are continuous with shift or other OT entries"""
        if not self.ot_employees:
            return

        # Prepare entries
        entries = []
        for d in self.ot_employees:
            if d.employee and d.date and d.get("begin_time") and d.get("end_time"):
                entries.append({
                    "idx": d.idx,
                    "employee": d.employee,
                    "employee_name": d.employee_name,
                    "date": str(d.date),
                    "begin_time": str(d.get("begin_time")),
                    "end_time": str(d.get("end_time"))
                })

        if not entries:
            return

        # Call validation with strict_mode=True
        errors = validate_ot_entries_continuity(entries, strict_mode=True)

        if errors:
            error_messages = []
            for error in errors:
                error_messages.append(_("Row {0}: {1} ({2}) - Ca {3}: {4}").format(
                    error["idx"],
                    error["employee_name"],
                    error["employee"],
                    error["shift_type"],
                    error["error"]
                ))

            frappe.throw("<br>".join(error_messages), title=_("Lỗi giờ tăng ca"))

    def validate_duplicate_employees(self):
        """Prevent duplicate or overlapping overtime entries within the same form"""
        
        entries = []
        
        for d in self.ot_employees:
            # Debug what fields are actually available
            missing_fields = []
            if not d.employee:
                missing_fields.append("Employee")
            if not d.date:
                missing_fields.append("Date") 
            if not d.get("begin_time"):
                missing_fields.append("Begin Time")
            if not d.get("end_time"):
                missing_fields.append("End Time")
                
            if missing_fields:
                frappe.throw(_("Row #{idx}: {fields} are required.").format(idx=d.idx, fields=", ".join(missing_fields)))
            
            entries.append({
                'idx': d.idx,
                'employee': d.employee,
                'employee_name': d.employee_name,
                'date': d.date,
                'from': d.get("begin_time"),
                'to': d.get("end_time")
            })
        
        # Check for duplicates and overlaps
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                entry1 = entries[i]
                entry2 = entries[j]
                
                # Same employee and date
                if entry1['employee'] == entry2['employee'] and entry1['date'] == entry2['date']:
                    # Check for exact match or time overlap
                    if times_overlap(entry1['from'], entry1['to'], entry2['from'], entry2['to']):
                        frappe.throw(_("Row {0} and {1}: Duplicate overtime for employee {2} on {3}").format(
                            entry1['idx'],
                            entry2['idx'],
                            entry1['employee_name'],
                            entry1['date']
                        ))

    def validate_conflicting_ot_requests(self):
        """Prevent conflicts and check continuity with existing submitted overtime registrations"""
        if not self.ot_employees:
            return

        for d in self.ot_employees:
            from_time = d.get("begin_time")
            to_time = d.get("end_time")

            existing_entries = frappe.db.sql("""
                SELECT child.parent, child.begin_time as `from`, child.end_time as `to`
                FROM `tabOvertime Registration Detail` as child
                JOIN `tabOvertime Registration` as parent ON child.parent = parent.name
                WHERE child.employee = %(employee)s
                AND child.date = %(date)s
                AND parent.name != %(current_doc_name)s
                AND parent.docstatus = 1
                ORDER BY child.begin_time
            """, {
                "employee": d.employee,
                "date": d.date,
                "current_doc_name": self.name or "new"
            }, as_dict=1)

            # Check for overlaps
            for existing in existing_entries:
                if times_overlap(from_time, to_time, existing.get("from"), existing.get("to")):
                    conflicting_doc = existing.get("parent")
                    doc_link = f'<a href="/app/overtime-registration/{conflicting_doc}" target="_blank">{conflicting_doc}</a>'
                    frappe.throw(_("Row {0}: Employee {1} already has overtime on {2} ({3}-{4}). Conflicts with {5}").format(
                        d.idx,
                        d.employee_name,
                        d.date,
                        from_time,
                        to_time,
                        doc_link
                    ))

            # Check continuity with existing submitted OT
            if existing_entries:
                from_time_obj = get_time(from_time)
                to_time_obj = get_time(to_time)

                # Check if this entry is continuous with any existing entry
                is_continuous = False
                for existing in existing_entries:
                    existing_from = get_time(existing.get("from"))
                    existing_to = get_time(existing.get("to"))

                    # This entry starts where existing ends
                    if from_time_obj == existing_to:
                        is_continuous = True
                        break

                    # This entry ends where existing starts
                    if to_time_obj == existing_from:
                        is_continuous = True
                        break

                # If not continuous with existing, check if it starts at shift end
                if not is_continuous:
                    shift_type, _source = get_shift_type(d.employee, d.date)
                    shift_config = get_shift_config(shift_type)

                    if shift_config:
                        has_benefit, _type, _from, _to = check_maternity_benefit(d.employee, d.date)

                        if has_benefit:
                            shift_end_dt = datetime.combine(datetime.today(), shift_config["end"])
                            effective_shift_end = (shift_end_dt - timedelta(hours=1)).time()
                        else:
                            effective_shift_end = shift_config["end"]

                        # If entry starts at shift end, it's valid (first OT of the day)
                        if from_time_obj == effective_shift_end:
                            is_continuous = True

                if not is_continuous:
                    # Get all existing OT times for error message
                    existing_times = ", ".join([f"{e.get('from')}-{e.get('to')}" for e in existing_entries])
                    existing_docs = ", ".join([f'<a href="/app/overtime-registration/{e.get("parent")}" target="_blank">{e.get("parent")}</a>' for e in existing_entries])

                    frappe.throw(_("Row {0}: OT {1}-{2} không liên tục với OT đã đăng ký ({3}). Xem: {4}").format(
                        d.idx,
                        from_time,
                        to_time,
                        existing_times,
                        existing_docs
                    ))

    def calculate_totals_and_apply_reason(self):
        """Manage general reason field and calculate totals"""
        if not self.ot_employees:
            self.total_employees = 0
            self.total_hours = 0
            return

        distinct_employees = set()
        total_hours = 0.0
        child_reasons = set()

        # First pass: calculate totals and gather unique, non-empty child reasons
        for d in self.ot_employees:
            if d.employee:
                distinct_employees.add(d.employee)

            if d.get("begin_time") and d.get("end_time"):
                total_hours += time_diff_in_hours(d.end_time, d.get("begin_time"))
            
            if d.reason:
                child_reasons.add(d.reason.strip())

        # Update totals
        self.total_employees = len(distinct_employees)
        self.total_hours = total_hours

        # If general reason is empty, populate it from unique child reasons
        if not self.reason_general and child_reasons:
            self.reason_general = ", ".join(sorted(list(child_reasons)))

        # If a general reason now exists (either provided by user or generated),
        # apply it to any child rows that have an empty reason.
        if self.reason_general:
            for d in self.ot_employees:
                if not d.reason:
                    d.reason = self.reason_general

@frappe.whitelist()
def check_overtime_conflicts(entries, current_doc_name="new"):
    """
    Server method to check conflicts with submitted overtime registrations
    Called from JavaScript validation
    """
    import json
    if isinstance(entries, str):
        entries = json.loads(entries)
    
    conflicts = []
    
    for entry in entries:
        # Query for existing overtime registrations for same employee and date
        existing_entries = frappe.db.sql("""
            SELECT child.parent, child.begin_time as `from`, child.end_time as `to`, child.employee_name
            FROM `tabOvertime Registration Detail` as child
            JOIN `tabOvertime Registration` as parent ON child.parent = parent.name
            WHERE child.employee = %(employee)s
            AND child.date = %(date)s
            AND parent.name != %(current_doc_name)s
            AND parent.docstatus = 1
        """, {
            "employee": entry["employee"],
            "date": entry["date"],
            "current_doc_name": current_doc_name
        }, as_dict=1)
        
        # Check for overlaps
        for existing in existing_entries:
            if times_overlap(entry["begin_time"], entry["end_time"], existing["from"], existing["to"]):
                conflicts.append({
                    "idx": entry["idx"],
                    "employee_name": entry["employee_name"],
                    "date": entry["date"],
                    "current_from": entry["begin_time"],
                    "current_to": entry["end_time"],
                    "existing_from": existing["from"],
                    "existing_to": existing["to"],
                    "existing_doc": existing["parent"]
                })
    
    return conflicts

def times_overlap(from1, to1, from2, to2):
    """
    Check if two time ranges overlap
    Adjacent periods (where one ends exactly when another begins) are NOT overlapping
    """
    try:
        # Convert time strings to time objects for comparison
        time1_start = get_time(from1)
        time1_end = get_time(to1)
        time2_start = get_time(from2)
        time2_end = get_time(to2)

        # Check for overlap: start1 < end2 && start2 < end1
        condition1 = time1_start < time2_end
        condition2 = time2_start < time1_end
        overlap = condition1 and condition2

        return overlap
    except Exception:
        # If there's any error in time conversion, assume no overlap
        return False

def check_maternity_benefit(employee, date):
    """Check if employee has maternity benefit on given date
    - Pregnant with apply_benefit=1: gets benefit
    - Maternity Leave: automatically gets benefit
    - Young Child: automatically gets benefit
    Returns: (has_benefit, benefit_type, from_date, to_date)
    """
    maternity_records = frappe.db.sql("""
        SELECT type, from_date, to_date, apply_benefit
        FROM `tabEmployee Maternity`
        WHERE employee = %(employee)s
          AND type IN ('Pregnant', 'Maternity Leave', 'Young Child')
          AND from_date <= %(date)s
          AND to_date >= %(date)s
    """, {"employee": employee, "date": date}, as_dict=1)

    if not maternity_records:
        return False, None, None, None

    for record in maternity_records:
        if record.type == 'Young Child':
            return True, "Nuôi con nhỏ", record.from_date, record.to_date
        elif record.type == 'Maternity Leave':
            return True, "Nghỉ thai sản", record.from_date, record.to_date
        elif record.type == 'Pregnant':
            if record.apply_benefit == 1:
                return True, "Mang thai", record.from_date, record.to_date

    return False, None, None, None

def get_shift_type(employee, date):
    """Get shift type for employee on date
    Reuses same logic from daily_timesheet.py get_shift_type method
    """
    # Check if it's Sunday
    if isinstance(date, str):
        date_obj = getdate(date)
    else:
        date_obj = date

    if date_obj.weekday() == 6:  # Sunday
        return "Day", "Default Day Shift For Sunday"

    # Priority 1: Shift Registration Detail
    shift_reg = frappe.db.sql("""
        SELECT srd.shift
        FROM `tabShift Registration Detail` srd
        JOIN `tabShift Registration` sr ON srd.parent = sr.name
        WHERE srd.employee = %(employee)s
          AND srd.begin_date <= %(date)s
          AND srd.end_date >= %(date)s
          AND sr.docstatus = 1
        ORDER BY sr.creation DESC
        LIMIT 1
    """, {"employee": employee, "date": date}, as_dict=1)

    if shift_reg:
        return shift_reg[0].shift, "Registration"

    # Priority 2: Employee custom_group
    emp_group = frappe.db.get_value("Employee", employee, "custom_group")
    if emp_group == "Canteen":
        return "Canteen", "Employee Group"

    # Default: Day shift
    return "Day", "Default"

def get_shift_config(shift_type):
    """Get shift configuration
    Reuses same config from daily_timesheet.py
    """
    SHIFT_CONFIGS = {
        "Day": {
            "start": time(8, 0),
            "end": time(17, 0),
            "break_start": time(12, 0),
            "break_end": time(13, 0),
            "allows_ot": True
        },
        "Canteen": {
            "start": time(7, 0),
            "end": time(16, 0),
            "break_start": time(11, 0),
            "break_end": time(12, 0),
            "allows_ot": True
        },
        "Shift 1": {
            "start": time(6, 0),
            "end": time(14, 0),
            "break_start": time(10, 0),
            "break_end": time(10, 0),
            "allows_ot": False
        },
        "Shift 2": {
            "start": time(14, 0),
            "end": time(22, 0),
            "break_start": time(18, 0),
            "break_end": time(18, 0),
            "allows_ot": False
        }
    }

    return SHIFT_CONFIGS.get(shift_type)

def validate_ot_continuity_with_shift(begin_time, end_time, shift_config, has_maternity=False, other_ot_entries=None, strict_mode=False):
    """Validate that OT time is continuous with shift or other OT entries

    When strict_mode=False (save):
    - Pre-shift: ends at or before shift start
    - Lunch break: during break_start to break_end
    - Post-shift: starts at or after shift end (or shift_end - 1h for maternity)

    When strict_mode=True (submit):
    - Pre-shift: ends exactly at shift start
    - Lunch break: during break_start to break_end
    - Post-shift: starts exactly at shift end, OR continuous with another OT entry

    Returns: (is_valid, error_message)
    """
    begin_time_obj = get_time(begin_time)
    end_time_obj = get_time(end_time)

    shift_start = shift_config["start"]
    shift_end = shift_config["end"]
    break_start = shift_config["break_start"]
    break_end = shift_config["break_end"]

    # For maternity, shift ends 1 hour earlier
    if has_maternity:
        shift_end_dt = datetime.combine(datetime.today(), shift_end)
        maternity_shift_end = (shift_end_dt - timedelta(hours=1)).time()
    else:
        maternity_shift_end = shift_end

    if strict_mode:
        # STRICT MODE (Submit): require exact continuity

        # Check pre-shift OT (must end exactly at shift start)
        if end_time_obj == shift_start and begin_time_obj < shift_start:
            return True, None

        # Check lunch break OT (during break)
        if break_start != break_end:
            if begin_time_obj >= break_start and end_time_obj <= break_end:
                return True, None

        # Check post-shift OT (must start exactly at shift end)
        if begin_time_obj == maternity_shift_end:
            return True, None

        # Check if this OT is continuous with another OT entry
        if other_ot_entries:
            for other_entry in other_ot_entries:
                other_begin = get_time(other_entry.get("begin_time"))
                other_end = get_time(other_entry.get("end_time"))

                # This OT starts where another ends
                if begin_time_obj == other_end:
                    return True, None

                # This OT ends where another starts
                if end_time_obj == other_begin:
                    return True, None

        # Invalid in strict mode
        if has_maternity:
            return False, _("Giờ tăng ca phải bắt đầu ngay sau ca ({0}), trong giờ nghỉ trưa ({1}-{2}), kết thúc đúng lúc bắt đầu ca ({3}), hoặc liên tục với OT khác").format(
                maternity_shift_end.strftime("%H:%M"),
                break_start.strftime("%H:%M"),
                break_end.strftime("%H:%M"),
                shift_start.strftime("%H:%M")
            )
        else:
            return False, _("Giờ tăng ca phải bắt đầu ngay sau ca ({0}), trong giờ nghỉ trưa ({1}-{2}), kết thúc đúng lúc bắt đầu ca ({3}), hoặc liên tục với OT khác").format(
                shift_end.strftime("%H:%M"),
                break_start.strftime("%H:%M"),
                break_end.strftime("%H:%M"),
                shift_start.strftime("%H:%M")
            )
    else:
        # NORMAL MODE (Save): allow any time after shift end

        # Check pre-shift OT (ends at or before shift start)
        if end_time_obj <= shift_start and begin_time_obj < shift_start:
            return True, None

        # Check lunch break OT (during break)
        if break_start != break_end:
            if begin_time_obj >= break_start and end_time_obj <= break_end:
                return True, None

        # Check post-shift OT (starts at or after shift end)
        if begin_time_obj >= maternity_shift_end:
            return True, None

        # Invalid: OT overlaps with working hours
        if has_maternity:
            return False, _("Giờ tăng ca phải nằm ngoài giờ làm việc (trước {0}, trong giờ nghỉ trưa {1}-{2}, hoặc sau {3})").format(
                shift_start.strftime("%H:%M"),
                break_start.strftime("%H:%M"),
                break_end.strftime("%H:%M"),
                maternity_shift_end.strftime("%H:%M")
            )
        else:
            return False, _("Giờ tăng ca phải nằm ngoài giờ làm việc (trước {0}, trong giờ nghỉ trưa {1}-{2}, hoặc sau {3})").format(
                shift_start.strftime("%H:%M"),
                break_start.strftime("%H:%M"),
                break_end.strftime("%H:%M"),
                shift_end.strftime("%H:%M")
            )

@frappe.whitelist()
def check_employees_with_maternity_benefits(entries):
    """
    Check if any employees in the entries have active maternity benefits
    and their begin_time starts at their shift end time
    Returns list of employees who need time adjustment (-1h)
    """
    import json

    if isinstance(entries, str):
        entries = json.loads(entries)

    employees_needing_adjustment = []

    for entry in entries:
        employee = entry.get("employee")
        date = entry.get("date")
        begin_time = entry.get("begin_time")

        if not employee or not date or not begin_time:
            continue

        # Get shift type and config for this employee
        shift_type, _source = get_shift_type(employee, date)
        shift_config = get_shift_config(shift_type)

        if not shift_config:
            continue

        # Check if begin_time equals shift end (normal shift end, not maternity adjusted)
        begin_time_obj = get_time(begin_time)
        shift_end = shift_config["end"]

        if begin_time_obj != shift_end:
            continue

        # Check for maternity benefit
        has_benefit, benefit_type, from_date, to_date = check_maternity_benefit(employee, date)

        if has_benefit:
            # Get employee name
            employee_name = frappe.db.get_value("Employee", employee, "employee_name")

            # Format dates for display
            from_date_str = from_date.strftime("%d/%m/%Y") if from_date else ""
            to_date_str = to_date.strftime("%d/%m/%Y") if to_date else ""

            # Calculate adjusted times (-1 hour)
            shift_end_dt = datetime.combine(datetime.today(), shift_end)
            adjusted_shift_end = (shift_end_dt - timedelta(hours=1)).time()

            employees_needing_adjustment.append({
                "idx": entry.get("idx"),
                "employee": employee,
                "employee_name": employee_name,
                "date": date,
                "begin_time": entry.get("begin_time"),
                "end_time": entry.get("end_time"),
                "benefit_type": benefit_type,
                "from_date": from_date_str,
                "to_date": to_date_str,
                "shift_type": shift_type,
                "shift_end": shift_end.strftime("%H:%M"),
                "adjusted_shift_end": adjusted_shift_end.strftime("%H:%M")
            })

    return employees_needing_adjustment

@frappe.whitelist()
def validate_ot_entries_continuity(entries, strict_mode=False):
    """
    Validate that all OT entries have times continuous with their shifts
    or continuous with other OT entries for same employee on same day

    strict_mode=False (save): allow any time after shift end
    strict_mode=True (submit): require exact continuity with shift or other OT
    Returns list of errors for invalid entries
    """
    import json

    if isinstance(entries, str):
        entries = json.loads(entries)

    if isinstance(strict_mode, str):
        strict_mode = strict_mode.lower() == 'true'

    errors = []

    # Group entries by employee and date for checking continuity between OT entries
    employee_date_entries = {}
    for entry in entries:
        employee = entry.get("employee")
        date = entry.get("date")
        if employee and date:
            key = f"{employee}_{date}"
            if key not in employee_date_entries:
                employee_date_entries[key] = []
            employee_date_entries[key].append(entry)

    for entry in entries:
        employee = entry.get("employee")
        date = entry.get("date")
        begin_time = entry.get("begin_time")
        end_time = entry.get("end_time")

        if not employee or not date or not begin_time or not end_time:
            continue

        # Get shift type for this employee on this date
        shift_type, _source = get_shift_type(employee, date)
        shift_config = get_shift_config(shift_type)

        if not shift_config:
            continue

        # Check if shift allows OT (Shift 1 and Shift 2 do not allow OT)
        if not shift_config.get("allows_ot", True):
            employee_name = frappe.db.get_value("Employee", employee, "employee_name")
            errors.append({
                "idx": entry.get("idx"),
                "employee": employee,
                "employee_name": employee_name,
                "date": date,
                "begin_time": begin_time,
                "end_time": end_time,
                "shift_type": shift_type,
                "error": _("Ca {0} không được phép đăng ký tăng ca").format(shift_type)
            })
            continue

        # Check if employee has maternity benefit
        has_benefit, _type, _from, _to = check_maternity_benefit(employee, date)

        # Get other OT entries for same employee on same day
        key = f"{employee}_{date}"
        other_entries = [e for e in employee_date_entries.get(key, []) if e.get("idx") != entry.get("idx")]

        # Validate OT continuity
        is_valid, error_msg = validate_ot_continuity_with_shift(
            begin_time, end_time, shift_config, has_benefit, other_entries, strict_mode
        )

        if not is_valid:
            employee_name = frappe.db.get_value("Employee", employee, "employee_name")
            errors.append({
                "idx": entry.get("idx"),
                "employee": employee,
                "employee_name": employee_name,
                "date": date,
                "begin_time": begin_time,
                "end_time": end_time,
                "shift_type": shift_type,
                "error": error_msg
            })

    return errors