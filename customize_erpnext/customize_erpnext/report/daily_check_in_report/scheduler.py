import frappe
from frappe import _
from frappe.utils import today, formatdate, get_datetime, add_days
from datetime import datetime

@frappe.whitelist()
def send_daily_check_in_report():
    """
    Scheduled job to send Daily Check-in Report every day at 8:15 AM
    Sends to: it@tiqn.com.vn & ni.nht@tiqn.com.vn
    Can also be called manually from Web Console for testing
    """
    try:
        # Get current date
        report_date = today()

        # Import the report execute function
        from customize_erpnext.customize_erpnext.report.daily_check_in_report.daily_check_in_report import get_data

        # Prepare filters
        filters = {
            "date": report_date,
            "status": "Absent",
            "show_maternity_leave": 1,
            "show_all_checkins": 0
        }

        # Get report data
        data = get_data(filters)

        # Get incomplete check-ins from previous day
        previous_date = add_days(report_date, -1)
        incomplete_checkins = get_incomplete_checkins(previous_date)

        # Calculate statistics
        stats = calculate_statistics(report_date, data, incomplete_checkins)

        # Generate email content
        email_subject = f"Báo cáo hiện diện / vắng ngày {formatdate(report_date, 'dd/MM/yyyy')}"
        email_content = generate_email_content(report_date, stats, data)

        # Send email
        recipients = ["it@tiqn.com.vn",  "ni.nht@tiqn.com.vn",  "hoanh.tk@tiqn.com.vn"]
        # , "ni.nht@tiqn.com.vn"
        frappe.sendmail(
            recipients=recipients,
            subject=email_subject,
            message=email_content,
            delayed=False
        )

        frappe.logger().info(f"Daily Check-in Report sent successfully for {report_date}")

    except Exception as e:
        frappe.logger().error(f"Error sending Daily Check-in Report: {str(e)}")
        frappe.log_error(
            title="Daily Check-in Report Scheduler Error",
            message=frappe.get_traceback()
        )

def get_incomplete_checkins(date):
    """
    Get list of employees who have only 1 check-in for the given date
    Returns list of employees with incomplete check-ins (missing check-out)
    """
    result = frappe.db.sql(f"""
        SELECT
            e.attendance_device_id,
            e.name AS employee_code,
            e.employee_name,
            e.department,
            e.custom_group,
            e.designation,
            MIN(ec.time) AS first_check_in,
            COUNT(ec.name) AS checkin_count,
            COALESCE(
                (SELECT srd.shift
                 FROM `tabShift Registration Detail` srd
                 JOIN `tabShift Registration` sr ON srd.parent = sr.name
                 WHERE srd.employee = e.name
                   AND srd.begin_date <= '{date}'
                   AND srd.end_date >= '{date}'
                   AND sr.docstatus = 1
                 ORDER BY sr.creation DESC
                 LIMIT 1),
                CASE
                    WHEN e.custom_group = 'Canteen' THEN 'Canteen'
                    ELSE 'Day'
                END
            ) AS shift
        FROM
            `tabEmployee` e
        INNER JOIN
            `tabEmployee Checkin` ec
        ON
            e.name = ec.employee
            AND DATE(ec.time) = '{date}'
        WHERE
            e.status = 'Active'
        GROUP BY
            e.name
        HAVING
            COUNT(ec.name) = 1
        ORDER BY
            e.custom_group, e.name
    """, as_dict=1)

    return result

def calculate_statistics(report_date, absent_data, incomplete_checkins):
    """
    Calculate statistics for the report:
    - Total active employees
    - Total present
    - Total absent (excluding maternity leave)
    - Total on maternity leave
    - Incomplete check-ins from previous day
    """
    # Count total active employees
    total_employees = frappe.db.count("Employee", filters={"status": "Active"})

    # Separate absent data into regular absent and maternity leave
    absent_regular = []
    absent_maternity = []

    for emp in absent_data:
        status_info = emp.get("status_info") or ""
        if status_info == "Maternity Leave":
            absent_maternity.append(emp)
        else:
            absent_regular.append(emp)

    # Sort both lists by custom_group (A-Z)
    absent_regular = sorted(absent_regular, key=lambda x: (x.get("custom_group") or "").lower())
    absent_maternity = sorted(absent_maternity, key=lambda x: (x.get("custom_group") or "").lower())

    # Sort incomplete check-ins by custom_group (A-Z)
    incomplete_sorted = sorted(incomplete_checkins, key=lambda x: (x.get("custom_group") or "").lower())

    # Count absent employees (excluding maternity leave)
    total_absent = len(absent_regular)

    # Count employees on maternity leave
    maternity_count = len(absent_maternity)

    # Count incomplete check-ins
    incomplete_count = len(incomplete_checkins)

    # Calculate present employees
    total_present = total_employees - total_absent - maternity_count

    return {
        "total_employees": total_employees,
        "total_present": total_present,
        "total_absent": total_absent,
        "maternity_count": maternity_count,
        "incomplete_count": incomplete_count,
        "absent_regular": absent_regular,
        "absent_maternity": absent_maternity,
        "incomplete_checkins": incomplete_sorted
    }

def generate_email_content(report_date, stats, absent_data):
    """
    Generate HTML email content with statistics and two separate absent employee lists
    """
    formatted_date = formatdate(report_date, "dd/MM/yyyy")
    current_time = datetime.now().strftime("%H:%M:%S %d/%m/%Y")

    # Build regular absent employee table (excluding maternity leave)
    absent_regular_rows = ""
    absent_regular_list = stats.get('absent_regular', [])
    if absent_regular_list:
        for idx, emp in enumerate(absent_regular_list, 1):
            status_info = emp.get("status_info") or ""
            absent_regular_rows += f"""
            <tr>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{idx}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('attendance_device_id') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('employee_code') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('employee_name') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('department') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('custom_group') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('shift') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('designation') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{status_info}</td>
            </tr>
            """
    else:
        absent_regular_rows = """
        <tr>
            <td colspan="9" style="border: 1px solid #ddd; padding: 8px; text-align: center; color: #999;">
                Không có nhân viên vắng
            </td>
        </tr>
        """

    # Build maternity leave employee table
    maternity_leave_rows = ""
    absent_maternity_list = stats.get('absent_maternity', [])
    if absent_maternity_list:
        for idx, emp in enumerate(absent_maternity_list, 1):
            status_info = emp.get("status_info") or ""
            maternity_leave_rows += f"""
            <tr>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{idx}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('attendance_device_id') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('employee_code') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('employee_name') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('department') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('custom_group') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('shift') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('designation') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{status_info}</td>
            </tr>
            """
    else:
        maternity_leave_rows = """
        <tr>
            <td colspan="9" style="border: 1px solid #ddd; padding: 8px; text-align: center; color: #999;">
                Không có nhân viên nghỉ thai sản
            </td>
        </tr>
        """

    # Build incomplete check-ins table (from previous day)
    incomplete_checkin_rows = ""
    incomplete_list = stats.get('incomplete_checkins', [])
    previous_date_formatted = formatdate(add_days(report_date, -1), "dd/MM/yyyy")

    if incomplete_list:
        for idx, emp in enumerate(incomplete_list, 1):
            # Format datetime using strftime instead of formatdate
            first_checkin_time = emp.get("first_check_in")
            if first_checkin_time:
                if isinstance(first_checkin_time, str):
                    first_checkin_time = get_datetime(first_checkin_time)
                first_checkin = first_checkin_time.strftime("%H:%M:%S %d/%m/%Y")
            else:
                first_checkin = ""

            incomplete_checkin_rows += f"""
            <tr>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{idx}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('attendance_device_id') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('employee_code') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('employee_name') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('department') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('custom_group') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('shift') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px;">{emp.get('designation') or ''}</td>
                <td style="border: 1px solid #ddd; padding: 8px; text-align: center;">{first_checkin}</td>
            </tr>
            """
    else:
        incomplete_checkin_rows = """
        <tr>
            <td colspan="9" style="border: 1px solid #ddd; padding: 8px; text-align: center; color: #999;">
                Không có nhân viên chấm công thiếu
            </td>
        </tr>
        """

    html_content = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
            .summary {{ margin: 20px 0; padding: 15px; background-color: #f5f5f5; border-radius: 5px; }}
            .summary-item {{ margin: 10px 0; font-size: 14px; }}
            .summary-item strong {{ color: #333; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th {{ background-color: #4CAF50; color: white; padding: 10px; text-align: left; border: 1px solid #ddd; }}
            .number {{ color: #2196F3; font-weight: bold; }}
            .present {{ color: #4CAF50; font-weight: bold; }}
            .absent {{ color: #f44336; font-weight: bold; }}
            .maternity {{ color: #FF9800; font-weight: bold; }}
            .incomplete {{ color: #9C27B0; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h2 style="color: #333;">Báo cáo hiện diện / vắng ngày {formatted_date}</h2>

        <div class="summary">
        <h3 style="margin-top: 0; color: #555;">Email này được gửi tự động từ hệ thống ERPNext vào lúc {current_time}</h3> 
            <h3 style="margin-top: 0; color: #555;">Tổng quan:</h3>
            <div class="summary-item">
                <strong>Số lượng nhân viên (Active):</strong>
                <span class="number">{stats['total_employees']}</span> người
            </div>
            <div class="summary-item">
                <strong>Số lượng hiện diện:</strong>
                <span class="present">{stats['total_present']}</span> người
            </div>
            <div class="summary-item">
                <strong>Số lượng vắng (không bao gồm nghỉ thai sản):</strong>
                <span class="absent">{stats['total_absent']}</span> người
            </div>
            <div class="summary-item">
                <strong>Số lượng nghỉ thai sản:</strong>
                <span class="maternity">{stats['maternity_count']}</span> người
            </div>
            <div class="summary-item">
                <strong>Số lượng chấm công thiếu (Chỉ có 1 lần chấm công) ngày {previous_date_formatted}:</strong>
                <span class="incomplete">{stats['incomplete_count']}</span> người
            </div>
        </div>

        <h3 style="color: #555;">Danh sách nhân viên vắng (không bao gồm nghỉ thai sản):</h3>
        <table>
            <thead>
                <tr>
                    <th style="width: 5%; text-align: center;">STT</th>
                    <th style="width: 8%;">Att ID</th>
                    <th style="width: 10%;">Employee</th>
                    <th style="width: 18%;">Employee Name</th>
                    <th style="width: 12%;">Department</th>
                    <th style="width: 12%;">Group</th>
                    <th style="width: 10%;">Shift</th>
                    <th style="width: 15%;">Designation</th>
                    <th style="width: 10%; text-align: center;">Status Info</th>
                </tr>
            </thead>
            <tbody>
                {absent_regular_rows}
            </tbody>
        </table>

        <h3 style="color: #555; margin-top: 30px;">Danh sách nhân viên nghỉ thai sản:</h3>
        <table>
            <thead>
                <tr>
                    <th style="width: 5%; text-align: center;">STT</th>
                    <th style="width: 8%;">Att ID</th>
                    <th style="width: 10%;">Employee</th>
                    <th style="width: 18%;">Employee Name</th>
                    <th style="width: 12%;">Department</th>
                    <th style="width: 12%;">Group</th>
                    <th style="width: 10%;">Shift</th>
                    <th style="width: 15%;">Designation</th>
                    <th style="width: 10%; text-align: center;">Status Info</th>
                </tr>
            </thead>
            <tbody>
                {maternity_leave_rows}
            </tbody>
        </table>

        <h3 style="color: #555; margin-top: 30px;">Danh sách nhân viên chấm công thiếu ngày {previous_date_formatted}:</h3>
        <table>
            <thead>
                <tr>
                    <th style="width: 5%; text-align: center;">STT</th>
                    <th style="width: 8%;">Att ID</th>
                    <th style="width: 10%;">Employee</th>
                    <th style="width: 18%;">Employee Name</th>
                    <th style="width: 12%;">Department</th>
                    <th style="width: 12%;">Group</th>
                    <th style="width: 10%;">Shift</th>
                    <th style="width: 15%;">Designation</th>
                    <th style="width: 10%; text-align: center;">Check-in Time</th>
                </tr>
            </thead>
            <tbody>
                {incomplete_checkin_rows}
            </tbody>
        </table>

    </body>
    </html>
    """

    return html_content

# cmd test from web console
''' 
  frappe.call({
      method: "customize_erpnext.customize_erpnext.report.daily_check_in_report.scheduler.send_daily_check_in_report",
      callback: function(r) {
          if (!r.exc) {
              frappe.msgprint("Email đã được gửi thành công!");
          } else {
              frappe.msgprint("Có lỗi xảy ra khi gửi email.");
          }
      }
  });

'''