from __future__ import unicode_literals
import frappe
from frappe import _
from datetime import datetime

def execute(filters=None):
    if not filters:
        filters = {}
        
    # Define columns
    columns = get_columns()
    
    # Get detailed data in merged row format
    data = get_detailed_data(filters)
    
    # Create report summary
    summary = get_report_summary(data)
    
    return columns, data, None, None, summary

def get_detailed_data(filters):
    """Get detailed data with row merging format like Excel"""
    conditions = get_conditions(filters)
    
    detailed_data = frappe.db.sql("""
        SELECT 
            name as document_id,
            employee,
            employee_name, 
            department,
            issue_date,
            employee_card,
            hat,
            water_bottle,
            uniform,
            reason,
            comments
        FROM 
            `tabEmployee Item Reissue` 
        WHERE 
            docstatus = 1 
            {conditions}
        ORDER BY
            employee, issue_date DESC
    """.format(conditions=conditions), filters, as_dict=1)
    
    # Format data with row merging
    formatted_data = []
    current_employee = None
    
    for idx, d in enumerate(detailed_data):
        # Check if this is a new employee
        is_new_employee = current_employee != d.employee
        current_employee = d.employee
        
        # Format the date
        issue_date = d.issue_date
        if isinstance(issue_date, str):
            try:
                issue_date = datetime.strptime(issue_date, '%Y-%m-%d').strftime('%d-%m-%Y')
            except:
                pass
        elif hasattr(issue_date, 'strftime'):
            issue_date = issue_date.strftime('%d-%m-%Y')
        
        # Add to results
        formatted_data.append({
            # Only show employee ID and name for the first row of each employee
            "employee": d.employee if is_new_employee else "",
            "employee_name": d.employee_name if is_new_employee else "",
            "department": d.department,
            "issue_date": issue_date,
            "employee_card": "x" if d.employee_card else "",
            "hat": "x" if d.hat else "",
            "water_bottle": "x" if d.water_bottle else "",
            "uniform": "x" if d.uniform else "",
            "reason": d.reason,
            "comments": d.comments
        })
    
    return formatted_data

def get_columns():
    """Define columns to display in the report"""
    return [
        {
            "fieldname": "employee",
            "label": _("Employee ID"),
            "fieldtype": "Link",
            "options": "Employee",
            "width": 120
        },
        # {
        #     "fieldname": "employee_name",
        #     "label": _("Employee Name"),
        #     "fieldtype": "Data",
        #     "width": 180
        # },
        {
            "fieldname": "department",
            "label": _("Department"),
            "fieldtype": "Data",
            "width": 120
        },
        {
            "fieldname": "issue_date",
            "label": _("Issue Date"),
            "fieldtype": "Data",
            "width": 100
        },
        {
            "fieldname": "employee_card",
            "label": _("Employee Card"),
            "fieldtype": "Data",
            "width": 120
        },
        {
            "fieldname": "hat",
            "label": _("Hat"),
            "fieldtype": "Data",
            "width": 80
        },
        {
            "fieldname": "water_bottle",
            "label": _("Water Bottle"),
            "fieldtype": "Data",
            "width": 120
        },
        {
            "fieldname": "uniform",
            "label": _("Uniform"),
            "fieldtype": "Data",
            "width": 90
        },
        {
            "fieldname": "reason",
            "label": _("Reason"),
            "fieldtype": "Data",
            "width": 100
        },
        {
            "fieldname": "comments",
            "label": _("Comments"),
            "fieldtype": "Data",
            "width": 150
        }
    ]

def get_report_data(filters):
    """
    Lấy dữ liệu chi tiết cho báo cáo, liệt kê từng vật dụng bị cấp phát lại và 
    áp dụng logic "gộp ô" cho MSNV và HỌ TÊN.
    """
    conditions = get_conditions(filters)
    
    # Lấy tất cả các đơn đã submit, SẮP XẾP theo nhân viên và ngày cấp phát
    reissues = frappe.db.sql("""
        SELECT 
            issue_date,
            employee, 
            employee_name, 
            department,
            employee_card,
            hat,
            water_bottle,
            uniform,
            reason
        FROM 
            `tabEmployee Item Reissue` 
        WHERE 
            docstatus = 1 
            {conditions}
        ORDER BY
            employee, issue_date
    """.format(conditions=conditions), filters, as_dict=1)
    
    result = []
    last_employee = None
    
    # Định nghĩa ánh xạ giữa trường DB và trường báo cáo
    item_fields = [
        ("employee_card", "item_employee_card"),
        ("hat", "item_hat"),
        ("water_bottle", "item_water_bottle"),
        ("uniform", "item_uniform"),
    ]

    for reissue in reissues:
        current_employee = reissue.employee
        current_issue_date = reissue.issue_date.strftime('%Y-%m-%d') if reissue.issue_date else None
        
        # Cờ để kiểm tra xem dòng đầu tiên cho nhân viên/ngày này đã được xử lý chưa
        is_first_row_for_employee = (current_employee != last_employee)
        is_first_row_for_reissue = True # Cờ cho dòng đầu tiên của bản ghi reissue này
        
        # 1. Tách bản ghi cấp phát thành nhiều dòng chi tiết (mỗi dòng một vật dụng)
        for db_field, result_field in item_fields:
            if reissue.get(db_field): # Nếu vật dụng này được cấp phát lại (có 'x')
                
                # Tạo một dòng cơ sở
                row = {
                    "issue_date": current_issue_date,
                    "employee": current_employee,
                    "employee_name": reissue.employee_name,
                    "department": reissue.department,
                    "reason": reissue.reason,
                    
                    # Khởi tạo tất cả các cột vật dụng khác là None (để không có 'x' thừa)
                    "item_employee_card": None,
                    "item_hat": None,
                    "item_water_bottle": None,
                    "item_uniform": None,
                }
                
                # Đặt 'x' cho cột vật dụng cụ thể này
                row[result_field] = 'x' 
                
                # --- ÁP DỤNG LOGIC GỘP Ô ---
                
                # 2. Xóa thông tin nhân viên (gộp ô) nếu trùng lặp
                if not is_first_row_for_employee:
                    # Nếu cùng nhân viên với dòng trước đó
                    row["employee"] = None
                    row["employee_name"] = None
                
                # 3. Xóa thông tin Ngày Cấp và Bộ Phận nếu đây không phải là dòng đầu tiên của bản ghi cấp phát này
                if not is_first_row_for_reissue:
                    row["issue_date"] = None
                    row["department"] = None
                
                result.append(row)
                
                # Sau khi thêm dòng đầu tiên của bản ghi reissue này, đặt cờ lại
                is_first_row_for_reissue = False
                is_first_row_for_employee = False
        
        # Cập nhật nhân viên cuối cùng được xử lý
        last_employee = current_employee
                
    return result

def get_conditions(filters):
    """Create SQL conditions from filters"""
    conditions = ""
    
    if filters.get("from_date"):
        conditions += " AND issue_date >= %(from_date)s"
    if filters.get("to_date"):
        conditions += " AND issue_date <= %(to_date)s"
    if filters.get("employee"):
        conditions += " AND employee = %(employee)s"
    if filters.get("department"):
        conditions += " AND department = %(department)s"
    if filters.get("reason"):
        conditions += " AND reason = %(reason)s"
        
    return conditions

def get_chart_data(data):
    """Tạo biểu đồ cho báo cáo"""
    if not data:
        return None
    
    # Đếm số lượng nhân viên theo số lần cấp phát
    reissue_counts = {}
    for row in data:
        count = row["reissue_count"]
        if count not in reissue_counts:
            reissue_counts[count] = 0
        reissue_counts[count] += 1
    
    # Sắp xếp theo số lần cấp phát
    labels = sorted(list(reissue_counts.keys()))
    values = [reissue_counts[count] for count in labels]
    
    chart = {
        "data": {
            "labels": [str(count) for count in labels],
            "datasets": [
                {
                    "name": _("Number of Employees"),
                    "values": values
                }
            ]
        },
        "type": "bar",
        "colors": ["#7cd6fd"],
        "title": _("Employees by Reissue Count")
    }
    
    return chart

def get_report_summary(data):
    """Create report summary"""
    if not data:
        return None
    
    # Count unique employees
    employees = set()
    employee_card_count = 0
    hat_count = 0
    water_bottle_count = 0
    uniform_count = 0
    lost_count = 0
    worn_out_count = 0
    damaged_count = 0
    
    for row in data:
        if row.get("employee"):
            employees.add(row["employee"])
        
        if row.get("employee_card") == "x":
            employee_card_count += 1
        
        if row.get("hat") == "x":
            hat_count += 1
            
        if row.get("water_bottle") == "x":
            water_bottle_count += 1
            
        if row.get("uniform") == "x":
            uniform_count += 1
            
        if row.get("reason") == "Lost":
            lost_count += 1
        elif row.get("reason") == "Worn Out":
            worn_out_count += 1
        elif row.get("reason") == "Damaged":
            damaged_count += 1
    
    total_items = employee_card_count + hat_count + water_bottle_count + uniform_count
    
    return [
        {
            "value": len(employees),
            "label": _("Total Employees"),
            "indicator": "blue"
        },
        {
            "value": total_items,
            "label": _("Total Items Reissued"),
            "indicator": "green"
        },
        {
            "value": employee_card_count,
            "label": _("Employee Cards"),
            "indicator": "gray"
        },
        {
            "value": hat_count,
            "label": _("Hats"),
            "indicator": "gray"
        },
        {
            "value": water_bottle_count,
            "label": _("Water Bottles"),
            "indicator": "gray"
        },
        {
            "value": uniform_count,
            "label": _("Uniforms"),
            "indicator": "gray"
        },
        {
            "value": lost_count,
            "label": _("Lost Items"),
            "indicator": "red"
        },
        {
            "value": worn_out_count + damaged_count,
            "label": _("Worn Out/Damaged Items"),
            "indicator": "orange"
        }
    ]