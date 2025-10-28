import frappe
from frappe import _

def set_default_holiday_list(doc, method=None):
    """
    Tự động gán Default Holiday List từ Company cho Employee
    """
    try:
        # Chỉ gán nếu Employee chưa có Holiday List
        if doc.holiday_list:
            frappe.logger().info(f"Employee {doc.name} đã có Holiday List: {doc.holiday_list}")
            return
        
        # Kiểm tra có Company không
        if not doc.company:
            frappe.logger().warning(f"Employee {doc.name} không có Company")
            return
        
        # Lấy Default Holiday List từ Company
        default_holiday_list = frappe.db.get_value(
            "Company", 
            doc.company, 
            "default_holiday_list"
        )
        
        if default_holiday_list:
            # Gán Holiday List cho Employee
            frappe.db.set_value(
                "Employee",
                doc.name,
                "holiday_list",
                default_holiday_list,
                update_modified=False
            )
            
            # Cập nhật doc hiện tại
            doc.holiday_list = default_holiday_list
            
            # frappe.msgprint(
            #     _("Đã tự động gán Holiday List <b>{0}</b> từ công ty {1}").format(
            #         default_holiday_list, 
            #         doc.company
            #     ),
            #     indicator='green',
            #     alert=True
            # )
            
            frappe.logger().info(
                f"Đã gán Holiday List {default_holiday_list} cho Employee {doc.name}"
            )
        else:
            frappe.logger().warning(
                f"Company {doc.company} không có Default Holiday List"
            )
            
    except Exception as e:
        frappe.log_error(
            message=frappe.get_traceback(),
            title=f"Lỗi khi gán Holiday List cho Employee {doc.name}"
        )
        frappe.throw(_("Có lỗi khi gán Holiday List tự động: {0}").format(str(e)))