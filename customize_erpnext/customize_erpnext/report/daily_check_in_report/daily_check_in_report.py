import frappe
from frappe import _
from datetime import datetime

def execute(filters=None):
    if not filters:
        filters = {}
   
    # Define columns for the report
    columns = [
        {"label": _("Employee"), "fieldname": "employee_code", "fieldtype": "Link", "options": "Employee", "width": 120},
        {"label": _("Employee Name"), "fieldname": "employee_name", "fieldtype": "Data", "width": 200},
        {"label": _("Department"), "fieldname": "department", "fieldtype": "Data", "width": 120},
        {"label": _("Group"), "fieldname": "custom_group", "fieldtype": "Data", "width": 120},
        {"label": _("Designation"), "fieldname": "designation", "fieldtype": "Data", "width": 120},
        {"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
        {"label": _("Status Info"), "fieldname": "status_info", "fieldtype": "Data", "width": 140, "align": "left"},
        {"label": _("Check-in Time"), "fieldname": "check_in_time", "fieldtype": "Datetime", "width": 220, "align": "left"},
        {"label": _("Device"), "fieldname": "device_id", "fieldtype": "Data", "width": 150, "align": "left"}
    ]
   
    # Get report data
    data = get_data(filters)
   
    return columns, data

def get_data(filters):
    # Lấy ngày từ bộ lọc
    report_date = filters.get("date") or frappe.utils.today()
    department = filters.get("department")
    custom_group = filters.get("custom_group")
    status_filter = filters.get("status")
    show_all_checkins = filters.get("show_all_checkins", 0)  # Checkbox mới
    
    # Các điều kiện lọc bổ sung
    conditions = [] 
    if department:
        conditions.append(f"e.department = '{department}'")
    if custom_group:
        conditions.append(f"e.custom_group = '{custom_group}'")
    
    # Kết hợp các điều kiện
    additional_conditions = " AND " + " AND ".join(conditions) if conditions else ""
    
    # Xây dựng truy vấn dựa trên checkbox
    if show_all_checkins:
        # Hiển thị tất cả check-in trong ngày
        result = frappe.db.sql(f"""
            SELECT 
                e.name AS employee_code,
                e.employee_name,
                e.department,
                e.custom_group,
                e.designation,
                c.time AS check_in_time,
                c.device_id,
                CASE 
                    WHEN c.time IS NOT NULL THEN 'Present'
                    WHEN ml.name IS NOT NULL THEN 'Present'
                    ELSE 'Absent' 
                END AS status,
                CASE 
                    WHEN ml.name IS NOT NULL THEN 'Maternity Leave'
                    ELSE NULL
                END AS status_info
            FROM 
                `tabEmployee` e
            -- Lấy tất cả check-in trong ngày
            LEFT JOIN 
                `tabEmployee Checkin` c
            ON 
                e.name = c.employee
                AND DATE(c.time) = '{report_date}'
            LEFT JOIN
                `tabMaternity Leave` ml
            ON
                ml.parent = e.name
                AND ml.type = 'Maternity Leave'
                AND '{report_date}' BETWEEN ml.from_date AND ml.to_date
            WHERE 
                e.status = 'Active'
                {additional_conditions}
                AND (c.time IS NOT NULL OR ml.name IS NOT NULL)
            ORDER BY 
                e.name, c.time
        """, as_dict=1)
        
        # Thêm nhân viên vắng mặt (không có check-in và không nghỉ thai sản)
        absent_employees = frappe.db.sql(f"""
            SELECT 
                e.name AS employee_code,
                e.employee_name,
                e.department,
                e.custom_group,
                e.designation,
                NULL AS check_in_time,
                NULL AS device_id,
                'Absent' AS status,
                NULL AS status_info
            FROM 
                `tabEmployee` e
            WHERE 
                e.status = 'Active'
                {additional_conditions}
                AND e.name NOT IN (
                    SELECT DISTINCT employee 
                    FROM `tabEmployee Checkin` 
                    WHERE DATE(time) = '{report_date}'
                )
                AND e.name NOT IN (
                    SELECT DISTINCT ml.parent
                    FROM `tabMaternity Leave` ml
                    WHERE ml.type = 'Maternity Leave'
                    AND '{report_date}' BETWEEN ml.from_date AND ml.to_date
                )
            ORDER BY 
                e.name
        """, as_dict=1)
        
        # Kết hợp kết quả
        result.extend(absent_employees)
        
    else:
        # Chỉ hiển thị check-in đầu tiên trong ngày (logic cũ)
        result = frappe.db.sql(f"""
            SELECT 
                e.name AS employee_code,
                e.employee_name,
                e.department,
                e.custom_group,
                e.designation,
                c.time AS check_in_time,
                c.device_id,
                CASE 
                    WHEN c.time IS NOT NULL THEN 'Present'
                    WHEN ml.name IS NOT NULL THEN 'Present'
                    ELSE 'Absent' 
                END AS status,
                CASE 
                    WHEN ml.name IS NOT NULL THEN 'Maternity Leave'
                    ELSE NULL
                END AS status_info
            FROM 
                `tabEmployee` e
            LEFT JOIN 
                (SELECT 
                    employee, 
                    MIN(time) AS time,
                    device_id
                 FROM 
                    `tabEmployee Checkin`
                 WHERE 
                    DATE(time) = '{report_date}'
                 GROUP BY 
                    employee) c
            ON 
                e.name = c.employee
            LEFT JOIN
                `tabMaternity Leave` ml
            ON
                ml.parent = e.name
                AND ml.type = 'Maternity Leave'
                AND '{report_date}' BETWEEN ml.from_date AND ml.to_date
            WHERE 
                e.status = 'Active'
                {additional_conditions}
            ORDER BY 
                e.name
        """, as_dict=1)
    
    # Lọc kết quả theo status nếu được chọn
    if status_filter and status_filter != "All":
        result = [r for r in result if r.status == status_filter]
    
    return result