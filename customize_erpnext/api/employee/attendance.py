import frappe
from frappe import _


def auto_create_daily_attendance():
    """
    Scheduled job to auto-create attendance for all active employees at 0:00
    Status: Absent (default)
    Called from hooks.py cron schedule
    """
    from frappe.utils import today
# Nếu frappe.request tồn tại, có khả năng cao là yêu cầu HTTP (từ UI, API, v.v.)
    if frappe.request:
        frappe.msgprint("Được gọi thông qua HTTP Request (Có thể là UI)")
        frappe.logger().error("Auto-create daily attendance triggered via HTTP Request")
        print("Auto-create daily attendance triggered via HTTP Request")
        # Cẩn thận: API calls cũng có frappe.request
    else:
        frappe.msgprint("Được gọi từ Server/Task/Hook")
        frappe.logger().error("Auto-create daily attendance triggered via Server/Task/Hook")
        print("Auto-create daily attendance triggered via Server/Task/Hook")
    try:
        # Get today's date
        attendance_date = today()

        # Call the mark_attendance_all_employees function
        result = mark_attendance_all_employees(
            from_date=attendance_date,
            to_date=attendance_date,
            status="Absent",
            shift=None,
            exclude_holidays=1  # Skip holidays
        )

        # Log the result
        frappe.logger().info(
            f"Auto-created daily attendance: {result.get('marked')} marked, "
            f"{result.get('skipped')} skipped, {result.get('errors')} errors"
        )

        return result

    except Exception as e:
        frappe.log_error(
            f"Error in auto_create_daily_attendance: {str(e)}",
            "Auto Create Daily Attendance Error"
        )


@frappe.whitelist()
def mark_attendance_all_employees(from_date, to_date, status, shift=None, exclude_holidays=0):
    """
    Mark attendance for all active employees using HRMS logic

    Args:
        from_date: Start date
        to_date: End date
        status: Attendance status (Present, Absent, Half Day, Work From Home)
        shift: Shift Type (optional)
        exclude_holidays: Exclude holidays (0 or 1)

    Returns:
        dict: Summary with marked, skipped, errors count
    """
    from frappe.utils import getdate

    # Convert dates
    from_date = getdate(from_date)
    to_date = getdate(to_date)

    # Get all active employees
    employees = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name")

    if not employees:
        frappe.throw(_("No active employees found"))

    marked = 0
    skipped = 0
    errors = 0

    # Mark attendance for each employee using HRMS logic
    for employee in employees:
        try:
            # Get unmarked days for this employee
            unmarked_days = frappe.call(
                "hrms.hr.doctype.attendance.attendance.get_unmarked_days",
                employee=employee,
                from_date=from_date,
                to_date=to_date,
                exclude_holidays=exclude_holidays
            )

            if not unmarked_days:
                skipped += 1
                continue

            # Prepare data for HRMS method
            data = frappe._dict({
                "employee": employee,
                "from_date": from_date,
                "to_date": to_date,
                "status": status,
                "shift": shift,
                "exclude_holidays": exclude_holidays,
                "unmarked_days": unmarked_days
            })

            # Call HRMS mark_bulk_attendance method
            result = frappe.call(
                "hrms.hr.doctype.attendance.attendance.mark_bulk_attendance",
                data=data
            )

            if result == 1:
                marked += 1
            else:
                skipped += 1

        except Exception as e:
            errors += 1
            frappe.log_error(
                f"Error marking attendance for {employee}: {str(e)}",
                "Mark Attendance All Employees Error"
            )

    return {
        "marked": marked,
        "skipped": skipped,
        "errors": errors,
        "total_employees": len(employees)
    }


@frappe.whitelist()
def bulk_mark_attendance_simple(employee_selection, employee=None, from_date=None, to_date=None):
    """
    Simple bulk mark attendance - create attendance records for date range
    Skip if attendance already exists

    Args:
        employee_selection: 'All Active Employees' or 'Specific Employee'
        employee: Employee ID (required if employee_selection is 'Specific Employee')
        from_date: Start date
        to_date: End date

    Returns:
        dict: Summary with created, skipped, errors count
    """
    from frappe.utils import getdate, date_diff, add_days

    # Convert "null" string to None
    if employee == "null":
        employee = None

    # Validate dates
    if not from_date or not to_date:
        frappe.throw(_("From Date and To Date are required"))

    from_date = getdate(from_date)
    to_date = getdate(to_date)

    if from_date > to_date:
        frappe.throw(_("From Date cannot be greater than To Date"))

    # Get employee list
    employee_filters = {"status": "Active"}

    if employee_selection == 'Specific Employee':
        if not employee:
            frappe.throw(_("Please select an employee"))
        # Verify employee exists and is active
        if not frappe.db.exists("Employee", {"name": employee, "status": "Active"}):
            frappe.throw(_("Employee {0} not found or not active").format(employee))
        employees = [employee]
    else:
        # All Active Employees
        employees = frappe.get_all("Employee", filters=employee_filters, pluck="name")

    if not employees:
        frappe.throw(_("No active employees found"))

    # Generate date list
    dates = []
    current_date = from_date
    while current_date <= to_date:
        dates.append(current_date)
        current_date = add_days(current_date, 1)

    # Process each employee and date
    created = 0
    skipped = 0
    errors = 0

    for emp in employees:
        for att_date in dates:
            try:
                # Check if attendance already exists
                existing = frappe.db.exists("Attendance", {
                    "employee": emp,
                    "attendance_date": att_date
                })

                if existing:
                    skipped += 1
                    continue

                # Create new attendance record
                doc = frappe.new_doc("Attendance")
                doc.employee = emp
                doc.attendance_date = att_date
                doc.company = frappe.get_value("Employee", emp, "company")
                doc.status = "Absent"  # Default status

                # Auto-detect shift for this employee and date
                try:
                    from hrms.hr.doctype.shift_assignment.shift_assignment import get_employee_shift
                    shift_details = get_employee_shift(
                        emp,
                        att_date,
                        consider_default_shift=True,
                        next_shift_direction="forward"
                    )
                    if shift_details:
                        doc.shift = shift_details.shift_type.name
                except Exception as shift_error:
                    # If shift detection fails, continue without shift
                    frappe.log_error(
                        f"Could not detect shift for {emp} on {att_date}: {str(shift_error)}",
                        "Shift Detection Warning"
                    )

                # Insert
                doc.insert(ignore_permissions=True)
                created += 1

            except Exception as e:
                errors += 1
                frappe.log_error(
                    f"Error creating attendance for {emp} on {att_date}: {str(e)}",
                    "Bulk Mark Attendance Error"
                )

    return {
        "created": created,
        "skipped": skipped,
        "errors": errors,
        "total_employees": len(employees),
        "total_dates": len(dates)
    }

@frappe.whitelist()
def bulk_mark_attendance_enhanced(
    attendance_date,
    selection_type='All Active Employees',
    department=None,
    designation=None,
    branch=None,
    custom_group=None,
    employee=None,
    auto_calculate=1,
    manual_status=None,
    manual_shift=None
):
    """
    Enhanced bulk mark attendance with more filter options and auto-calculation

    Args:
        attendance_date: Date to mark attendance for
        selection_type: Type of employee selection (All Active Employees, Department, Designation, Branch, Custom Group, Specific Employee)
        department: Department filter
        designation: Designation filter
        branch: Branch filter
        custom_group: Custom group filter
        employee: Specific employee
        auto_calculate: Auto-calculate status and shift from check-ins (1/0)
        manual_status: Manual status override (if auto_calculate is disabled)
        manual_shift: Manual shift override (if auto_calculate is disabled)

    Returns:
        dict: Result with created, updated, skipped, errors count
    """
    # Convert string to int
    if isinstance(auto_calculate, str):
        auto_calculate = int(auto_calculate)

    # Convert "null" strings to None
    for field in [department, designation, branch, custom_group, employee, manual_status, manual_shift]:
        if field == "null":
            field = None

    # Build employee filters
    employee_filters = {"status": "Active"}

    if selection_type == "Department" and department:
        employee_filters["department"] = department
    elif selection_type == "Designation" and designation:
        employee_filters["designation"] = designation
    elif selection_type == "Branch" and branch:
        employee_filters["branch"] = branch
    elif selection_type == "Custom Group" and custom_group:
        employee_filters["custom_group"] = custom_group
    elif selection_type == "Specific Employee" and employee:
        # Verify employee exists and is active
        if not frappe.db.exists("Employee", {"name": employee, "status": "Active"}):
            frappe.throw(_("Employee {0} not found or not active").format(employee))
        employee_filters["name"] = employee
    # else: All Active Employees (no additional filters)

    # Get employee list
    employees = frappe.get_all("Employee", filters=employee_filters, pluck="name")

    if not employees:
        frappe.throw(_("No employees found matching the criteria"))

    # Process each employee
    created = 0
    updated = 0
    skipped = 0
    errors = 0

    for emp in employees:
        try:
            # Check if attendance already exists
            existing_name = frappe.db.get_value("Attendance", {
                "employee": emp,
                "attendance_date": attendance_date
            })

            if existing_name:
                # Update existing attendance
                doc = frappe.get_doc("Attendance", existing_name)

                if auto_calculate:
                    # Auto-calculate from check-ins
                    checkin_logs = _calculate_from_checkins(doc)
                else:
                    # Use manual values
                    checkin_logs = None
                    if manual_status:
                        doc.status = manual_status
                    if manual_shift:
                        doc.shift = manual_shift

                doc.save(ignore_permissions=True)

                # Link check-ins after save
                if auto_calculate and checkin_logs:
                    _link_checkins_to_attendance(checkin_logs, doc.name)

                updated += 1
            else:
                # Create new attendance
                doc = frappe.new_doc("Attendance")
                doc.employee = emp
                doc.attendance_date = attendance_date
                doc.company = frappe.get_value("Employee", emp, "company")

                if auto_calculate:
                    # Auto-calculate from check-ins
                    checkin_logs = _calculate_from_checkins(doc)
                else:
                    # Use manual values or defaults
                    checkin_logs = None
                    doc.status = manual_status or "Absent"
                    if manual_shift:
                        doc.shift = manual_shift

                doc.insert(ignore_permissions=True)

                # Link check-ins after insert
                if auto_calculate and checkin_logs:
                    _link_checkins_to_attendance(checkin_logs, doc.name)

                created += 1

        except Exception as e:
            errors += 1
            frappe.log_error(
                f"Error marking attendance for {emp} on {attendance_date}: {str(e)}",
                "Bulk Mark Attendance Error"
            )

    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "errors": errors,
        "total_employees": len(employees)
    }


def _calculate_from_checkins(attendance_doc):
    """
    Calculate attendance status, shift, and other fields from Employee Checkin records

    Args:
        attendance_doc: Attendance document to populate

    Returns:
        list: List of check-in logs to link to attendance (or None if no logs)
    """
    from frappe.utils import getdate
    from hrms.hr.doctype.shift_assignment.shift_assignment import get_employee_shift
    from datetime import date

    # Ensure attendance_date is a date object
    attendance_date = attendance_doc.attendance_date
    if isinstance(attendance_date, str):
        attendance_date = getdate(attendance_date)
    elif isinstance(attendance_date, date):
        # Already a date object, no need to convert
        pass

    # Get employee's shift for this date
    shift_details = get_employee_shift(
        attendance_doc.employee,
        attendance_date,
        consider_default_shift=True,
        next_shift_direction="forward"
    )

    if not shift_details:
        # No shift assigned - mark as Absent
        attendance_doc.status = "Absent"
        return None

    shift_type_name = shift_details.shift_type.name
    attendance_doc.shift = shift_type_name

    # Get check-ins for this employee, date, and shift
    checkins = frappe.get_all(
        "Employee Checkin",
        filters={
            "employee": attendance_doc.employee,
            "attendance": ["is", "not set"],
            "time": ["between", [shift_details.actual_start, shift_details.actual_end]],
            "skip_auto_attendance": 0
        },
        fields=["name", "time", "log_type", "device_id", "shift"],
        order_by="time"
    )

    if not checkins:
        # No check-ins found - mark as Absent
        attendance_doc.status = "Absent"
        return None

    # Get shift type document to calculate attendance
    shift_type = frappe.get_cached_doc("Shift Type", shift_type_name)

    # Convert check-ins to the format expected by get_attendance
    from frappe import _dict
    logs = []
    for log in checkins:
        logs.append(_dict({
            "name": log.name,
            "time": log.time,
            "log_type": log.get("log_type", ""),
            "shift_start": shift_details.start_datetime,
            "shift_end": shift_details.end_datetime,
            "shift_actual_start": shift_details.actual_start,
            "shift_actual_end": shift_details.actual_end
        }))

    # Use shift type's get_attendance method to calculate
    try:
        status, working_hours, late_entry, early_exit, in_time, out_time = shift_type.get_attendance(logs)

        # Populate attendance document
        attendance_doc.status = status
        attendance_doc.working_hours = working_hours
        attendance_doc.in_time = in_time
        attendance_doc.out_time = out_time
        attendance_doc.late_entry = late_entry
        attendance_doc.early_exit = early_exit

        # Return logs to be linked later (after document is saved)
        return logs

    except Exception as e:
        frappe.log_error(f"Error calculating attendance from check-ins: {str(e)}", "Calculate Attendance Error")
        # Fallback to Absent
        attendance_doc.status = "Absent"
        return None


def _link_checkins_to_attendance(logs, attendance_name):
    """
    Link check-in logs to an attendance record

    Args:
        logs: List of check-in log dictionaries
        attendance_name: Name of the attendance document
    """
    if not logs or not attendance_name:
        return

    for log in logs:
        frappe.db.set_value("Employee Checkin", log.name, "attendance", attendance_name, update_modified=False)


@frappe.whitelist()
def recalculate_attendance_records(attendance_names):
    """Recalculate selected attendance records from check-in data"""
    if isinstance(attendance_names, str):
        import json
        attendance_names = json.loads(attendance_names)

    updated_count = 0
    for name in attendance_names:
        try:
            doc = frappe.get_doc("Attendance", name)
            # Trigger recalculation
            from customize_erpnext.override_methods.attendance import calculate_attendance_fields
            calculate_attendance_fields(doc)
            doc.save(ignore_permissions=True)
            updated_count += 1
        except Exception as e:
            frappe.log_error(f"Error recalculating attendance {name}: {str(e)}")

    return {
        "success": True,
        "updated_count": updated_count,
        "message": _("{0} attendance record(s) have been recalculated").format(updated_count)
    }

