# -*- coding: utf-8 -*-
# customize_erpnext/health_check/api/health_check_api.py
#
# Whitelisted API endpoints for Health Check Web App.
# All methods are called from client-side JS via frappe.call().
# Realtime events are published for instant multi-client updates.

import frappe
from frappe.utils import nowtime, today, getdate, now_datetime, get_datetime


# ===========================================================================
# EXCEL / CSV EXPORT
# ===========================================================================

@frappe.whitelist()
def get_excel_data(date=None):
    """
    Returns data formatted for frappe.desk.reportview.export_query
    so the user can download an Excel file of the Health Check data.
    """
    if not date:
        date = today()
        
    records = frappe.db.sql(
        """
        SELECT
            name as 'ID',
            date as 'Date',
            hospital_code as 'Hospital Code',
            health_check_type as 'Health Check Type',
            employee as 'Employee',
            start_time as 'Start Time',
            end_time as 'End Time',
            employee_name as 'Employee Name',
            gender as 'Gender',
            department as 'Department',
            custom_section as 'Section',
            custom_group as 'Group',
            designation as 'Designation',
            pregnant as 'Pregnant',
            start_time_actual as 'Start Time Actual',
            end_time_actual as 'End Time Actual',
            x_ray as 'X-Ray',
            gynecological_exam as 'Gynecological Exam',
            note as 'Note',
            IF(start_time_actual IS NOT NULL AND end_time_actual IS NOT NULL, 'Hoàn thành', IF(start_time_actual IS NOT NULL, 'Đang khám', 'Chưa khám')) as 'Status',
            result as 'Result'
        FROM `tabHealth Check-Up`
        WHERE date = %(date)s
        ORDER BY start_time ASC, hospital_code ASC
    """,
        {"date": date},
        as_dict=True,
    )
    
    if not records:
        return []

    # Get ordered columns map
    columns = list(records[0].keys())

    # Format row arrays
    result = [columns]
    for r in records:
        row = []
        for col in columns:
            val = r.get(col)
            # Convert timedeltas to string format HH:MM:SS
            if hasattr(val, 'seconds'):
                val = str(val)
                
            # If the value is a boolean or checkbox, make it an integer
            if col in ['Pregnant', 'X-Ray', 'Gynecological Exam']:
                val = 1 if val else 0
                
            row.append(val)
        result.append(row)

    from frappe.utils.xlsxutils import build_xlsx_response
    build_xlsx_response(result, f"Health Check Data - {date}")

# ===========================================================================
# READ APIs
# ===========================================================================


@frappe.whitelist()
def get_health_check_dates():
    """
    Get all distinct dates that have Health Check records.
    Used to populate the date selector dropdown in Web App.

    Returns:
        list[str]: Dates in YYYY-MM-DD format, sorted descending (newest first)
    """
    dates = frappe.db.sql(
        """
        SELECT DISTINCT date
        FROM `tabHealth Check-Up`
        ORDER BY date DESC
    """,
        as_dict=True,
    )
    return [str(d.date) for d in dates]


@frappe.whitelist()
def get_health_check_data(date=None):
    """
    Get all Health Check records for a specific date, plus computed statistics
    and group/section breakdowns.

    If date is not provided, uses the most recent date with data.

    Args:
        date (str, optional): Date in YYYY-MM-DD format

    Returns:
        dict: {
            "date": str,
            "records": list[dict],
            "stats": dict,
            "groups": list[dict],
            "sections": list[dict]
        }
    """
    if not date:
        result = frappe.db.sql(
            "SELECT MAX(date) as max_date FROM `tabHealth Check-Up`",
            as_dict=True,
        )
        date = result[0].max_date if result and result[0].max_date else today()

    records = frappe.db.sql(
        """
        SELECT
            name,
            date,
            hospital_code,
            employee,
            employee_name,
            gender,
            department,
            custom_section,
            custom_group,
            designation,
            health_check_type,
            pregnant,
            start_time,
            end_time,
            start_time_actual,
            end_time_actual,
            x_ray,
            gynecological_exam,
            note
        FROM `tabHealth Check-Up`
        WHERE date = %(date)s
        ORDER BY start_time ASC, hospital_code ASC
    """,
        {"date": date},
        as_dict=True,
    )

    # Convert timedelta fields to string for JSON serialization
    for r in records:
        for tf in [
            "start_time",
            "end_time",
            "start_time_actual",
            "end_time_actual",
        ]:
            if r.get(tf):
                r[tf] = str(r[tf])

    # ---- Compute statistics ----
    total = len(records)
    distributed = sum(1 for r in records if r.start_time_actual)
    completed = sum(1 for r in records if r.end_time_actual)
    in_exam = distributed - completed
    not_started = total - distributed
    x_ray_count = sum(1 for r in records if r.x_ray)
    gynec_count = sum(1 for r in records if r.gynecological_exam)
    pregnant_count = sum(1 for r in records if r.pregnant)

    # ---- Group breakdown ----
    groups = {}
    for r in records:
        g = r.custom_group or "Không xác định"
        if g not in groups:
            groups[g] = {"total": 0, "distributed": 0, "completed": 0}
        groups[g]["total"] += 1
        if r.start_time_actual:
            groups[g]["distributed"] += 1
        if r.end_time_actual:
            groups[g]["completed"] += 1

    group_list = sorted(
        [{"group": k, **v} for k, v in groups.items()],
        key=lambda x: x["group"],
    )

    # ---- Section breakdown ----
    sections = {}
    for r in records:
        s = r.custom_section or "Không xác định"
        if s not in sections:
            sections[s] = {"total": 0, "distributed": 0, "completed": 0}
        sections[s]["total"] += 1
        if r.start_time_actual:
            sections[s]["distributed"] += 1
        if r.end_time_actual:
            sections[s]["completed"] += 1

    section_list = sorted(
        [{"section": k, **v} for k, v in sections.items()],
        key=lambda x: -x["total"],
    )

    return {
        "date": str(date),
        "records": records,
        "stats": {
            "total": total,
            "distributed": distributed,
            "completed": completed,
            "in_exam": in_exam,
            "not_started": not_started,
            "x_ray": x_ray_count,
            "gynecological_exam": gynec_count,
            "pregnant": pregnant_count,
        },
        "groups": group_list,
        "sections": section_list,
    }


# ===========================================================================
# SCAN APIs (Write operations with realtime)
# ===========================================================================


@frappe.whitelist()
def scan_distribute(hospital_code=None, employee=None, date=None, note=None):
    """
    Record the actual distribution time for a health check record.
    Called when an operator scans a barcode or enters a code to distribute
    the examination folder to an employee.

    Args:
        hospital_code (str, optional): Hospital code (4 chars)
        employee (str, optional): Employee ID or short code (4 digits)
        date (str, optional): Date, defaults to today
        note (str, optional): Note to append

    Returns:
        dict: {success, already_existed, record}

    Raises:
        frappe.ValidationError: If record not found
    """
    if not date:
        date = today()

    record = _find_record(hospital_code, employee, date)
    if not record:
        frappe.throw(_build_not_found_msg(hospital_code, employee, date))

    doc = frappe.get_doc("Health Check-Up", record.name)
    
    if doc.end_time_actual:
        frappe.throw("Không thể phát hồ sơ vì hồ sơ này đã được Thu xong.")

    already_existed = bool(doc.start_time_actual)
    doc.start_time_actual = nowtime()
    
    if note:
        existing_note = doc.note or ""
        prefix = "\n" if existing_note else ""
        doc.note = f"{existing_note}{prefix}[Cấp HS] {note}"

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    # Publish realtime event for all connected clients
    _publish_update(date, doc, "distribute")

    return {
        "success": True,
        "already_existed": already_existed,
        "record": _serialize_record(doc),
    }


@frappe.whitelist()
def scan_collect(
    hospital_code=None,
    employee=None,
    date=None,
    x_ray=0,
    gynecological_exam=0,
    note=None,
    manual_start_time=None,
):
    """
    Record the actual collection time for a health check record.
    Called when an operator scans a barcode or enters a code to collect
    the examination folder back from an employee.

    Also records X-Ray and Gynecological Exam checkboxes.

    Args:
        hospital_code (str, optional): Hospital code (4 chars)
        employee (str, optional): Employee ID or short code (4 digits)
        date (str, optional): Date, defaults to today
        x_ray (int): 1 if X-Ray was done, 0 otherwise
        gynecological_exam (int): 1 if Gynecological exam was done, 0 otherwise
        note (str, optional): Note to append
        manual_start_time (str, optional): Time string to record as start_time_actual

    Returns:
        dict: {success, already_existed, record}
    """
    if not date:
        date = today()

    x_ray = int(x_ray)
    gynecological_exam = int(gynecological_exam)

    record = _find_record(hospital_code, employee, date)
    if not record:
        frappe.throw(_build_not_found_msg(hospital_code, employee, date))

    doc = frappe.get_doc("Health Check-Up", record.name)

    already_existed = bool(doc.end_time_actual)
    doc.end_time_actual = nowtime()
    doc.x_ray = x_ray
    doc.gynecological_exam = gynecological_exam

    if manual_start_time:
        doc.start_time_actual = manual_start_time

    if note:
        existing_note = doc.note or ""
        prefix = "\n" if existing_note else ""
        doc.note = f"{existing_note}{prefix}[Thu HS] {note}"

    doc.save(ignore_permissions=True)
    frappe.db.commit()

    # Publish realtime event for all connected clients
    _publish_update(date, doc, "collect")

    return {
        "success": True,
        "already_existed": already_existed,
        "record": _serialize_record(doc),
    }


@frappe.whitelist()
def lookup_record(code, date=None):
    """
    Quick lookup a Health Check record by hospital_code or employee code.
    Used for preview/validation before confirming a scan action.

    Args:
        code (str): Hospital code or employee code
        date (str, optional): Date, defaults to today

    Returns:
        dict: {found: bool, record: dict or None}
    """
    if not date:
        date = today()

    # Try as hospital_code first
    record = _find_record(hospital_code=code, employee=None, date=date)

    # If not found, try as employee code
    if not record:
        record = _find_record(hospital_code=None, employee=code, date=date)

    if not record:
        return {"found": False}

    return {"found": True, "record": record}


# ===========================================================================
# PRIVATE HELPERS
# ===========================================================================


def _find_record(hospital_code=None, employee=None, date=None):
    """
    Find a Health Check record by hospital_code or employee for a given date.
    Supports both full employee ID (HR-MFG-00009) and short code (0009 or 9).
    """
    fields = [
        "name",
        "hospital_code",
        "employee",
        "employee_name",
        "gender",
        "department",
        "custom_section",
        "custom_group",
        "designation",
        "pregnant",
        "health_check_type",
        "start_time",
        "end_time",
        "start_time_actual",
        "end_time_actual",
        "x_ray",
        "gynecological_exam",
        "note",
    ]

    if hospital_code:
        records = frappe.get_all(
            			"Health Check-Up",
            filters={"hospital_code": hospital_code.strip(), "date": date},
            fields=fields,
            limit=1,
        )
        if records:
            return _convert_time_fields(records[0])

    if employee:
        employee = str(employee).strip()

        # Case 1: Short numeric code (4 digits) → search with LIKE
        if len(employee) <= 5 and employee.isdigit():
            records = frappe.db.sql(
                """
                SELECT {fields}
                FROM `tabHealth Check-Up`
                WHERE date = %(date)s
                  AND employee LIKE %(pattern)s
                LIMIT 1
            """.format(
                    fields=", ".join(fields)
                ),
                {"date": date, "pattern": f"%{employee.zfill(4)}%"},
                as_dict=True,
            )
            if records:
                return _convert_time_fields(records[0])

        # Case 2: Full employee ID
        else:
            records = frappe.get_all(
                			"Health Check-Up",
                filters={"employee": employee, "date": date},
                fields=fields,
                limit=1,
            )
            if records:
                return _convert_time_fields(records[0])

    return None


def _convert_time_fields(record):
    """Convert timedelta objects to strings for JSON serialization"""
    for tf in ["start_time", "end_time", "start_time_actual", "end_time_actual"]:
        if record.get(tf):
            record[tf] = str(record[tf])
    return record


def _build_not_found_msg(hospital_code, employee, date):
    """Build a user-friendly not-found error message"""
    identifier = hospital_code or employee or "?"
    return frappe._(
        "Không tìm thấy hồ sơ khám cho mã <b>{0}</b> ngày <b>{1}</b>"
    ).format(identifier, date)


# ===========================================================================
# ADMIN BULK OPERATIONS
# ===========================================================================

@frappe.whitelist()
def clear_actual_data(date):
    """
    Clear start_time_actual and end_time_actual for all Health Check-Up records
    on the given date. Password validation is done on the client side (ddmm).
    """
    if not date:
        frappe.throw("Vui lòng chọn ngày.")

    records = frappe.get_all(
        "Health Check-Up",
        filters={"date": date},
        fields=["name"],
    )
    if not records:
        frappe.throw(f"Không có bảng ghi nào cho ngày {date}.")

    count = 0
    for r in records:
        doc = frappe.get_doc("Health Check-Up", r["name"])
        if doc.start_time_actual or doc.end_time_actual or doc.x_ray or doc.gynecological_exam:
            doc.start_time_actual = None
            doc.end_time_actual = None
            doc.x_ray = None
            doc.gynecological_exam = None
            doc.save(ignore_permissions=True)
            count += 1

    frappe.db.commit()
    return {"cleared": count, "total": len(records)}


@frappe.whitelist()
def change_date(from_date, to_date):
    """
    Change the date field of all Health Check-Up records from from_date to to_date.
    Password validation is done on the client side (ddmm).
    """
    if not from_date or not to_date:
        frappe.throw("Vui lòng cung cấp ngày nguồn và ngày đích.")

    if from_date == to_date:
        frappe.throw("Ngày đích phải khác ngày nguồn.")

    # Prevent duplicate: if records already exist on to_date
    existing = frappe.db.count("Health Check-Up", {"date": to_date})
    if existing:
        frappe.throw(
            f"Đã có {existing} bảng ghi vào ngày {to_date}. Không thể chuyển để tránh trùng lặp."
        )

    records = frappe.get_all(
        "Health Check-Up",
        filters={"date": from_date},
        fields=["name"],
    )
    if not records:
        frappe.throw(f"Không có bảng ghi nào cho ngày {from_date}.")

    count = len(records)
    frappe.db.sql(
        "UPDATE `tabHealth Check-Up` SET `date` = %s WHERE `date` = %s",
        (to_date, from_date)
    )
    frappe.db.commit()
    return {"updated": count}


def _serialize_record(doc):
    """Serialize a Health Check document for API response"""
    return {
        "name": doc.name,
        "hospital_code": doc.hospital_code,
        "employee": doc.employee,
        "employee_name": doc.employee_name,
        "gender": doc.gender,
        "department": doc.department,
        "custom_section": doc.custom_section,
        "custom_group": doc.custom_group,
        "designation": doc.designation,
        "pregnant": doc.pregnant,
        "start_time": str(doc.start_time)
        if doc.start_time
        else None,
        "end_time": str(doc.end_time)
        if doc.end_time
        else None,
        "start_time_actual": str(doc.start_time_actual)
        if doc.start_time_actual
        else None,
        "end_time_actual": str(doc.end_time_actual)
        if doc.end_time_actual
        else None,
        "x_ray": doc.x_ray,
        "gynecological_exam": doc.gynecological_exam,
        "note": doc.note,
    }


def _publish_update(date, doc, action):
    """
    Publish a realtime event via Socket.IO so all connected Web App clients
    update instantly without manual refresh.

    Event name: "health_check_update"
    Payload includes the changed record data and action type.
    """
    frappe.publish_realtime(
        event="health_check_update",
        message={
            "date": str(date),
            "action": action,  # "distribute" or "collect"
            "record_name": doc.name,
            "hospital_code": doc.hospital_code,
            "employee": doc.employee,
            "employee_name": doc.employee_name,
            "custom_group": doc.custom_group,
            "custom_section": doc.custom_section,
            "start_time": str(doc.start_time)
            if doc.start_time
            else None,
            "end_time": str(doc.end_time)
            if doc.end_time
            else None,
            "start_time_actual": str(doc.start_time_actual)
            if doc.start_time_actual
            else None,
            "end_time_actual": str(doc.end_time_actual)
            if doc.end_time_actual
            else None,
            "x_ray": doc.x_ray,
            "gynecological_exam": doc.gynecological_exam,
        },
        room="task_progress:health_check_updates",
        after_commit=True,
    )
