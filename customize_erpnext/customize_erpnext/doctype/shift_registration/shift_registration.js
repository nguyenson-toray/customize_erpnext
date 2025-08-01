// Copyright (c) 2025, IT Team - TIQN and contributors
// For license information, please see license.txt

// Approach tốt hơn: Ngăn chặn chọn trùng + Filter danh sách employee

frappe.ui.form.on('Shift Registration', {
    // Khi thay đổi begin_time, cập nhật tất cả rows hiện có
    begin_time: function(frm) {
        if (frm.doc.begin_time) {
            frm.doc.employees_list.forEach(function(row) {
                frappe.model.set_value(row.doctype, row.name, 'begin_time', frm.doc.begin_time);
            });
            frm.refresh_field('employees_list');
        }
    },
    
    // Khi thay đổi end_time, cập nhật tất cả rows hiện có  
    end_time: function(frm) {
        if (frm.doc.end_time) {
            frm.doc.employees_list.forEach(function(row) {
                frappe.model.set_value(row.doctype, row.name, 'end_time', frm.doc.end_time);
            });
            frm.refresh_field('employees_list');
        }
    },
    
    // Function để tính toán total employees
    calculate_total_employees: function(frm) {
        var total = 0;
        if (frm.doc.employees_list) {
            frm.doc.employees_list.forEach(function(row) {
                if (row.employee) {
                    total++;
                }
            });
        }
        frm.set_value('total_employees', total);
    },
    
    // Tính total employees khi load form
    refresh: function(frm) {
        frm.events.calculate_total_employees(frm);
    }
});

frappe.ui.form.on('Shift Registration Detail', {
    // Khi thêm row mới, tự động điền thông tin từ parent
    employees_list_add: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        
        // Set begin_time từ parent
        if (frm.doc.begin_time) {
            frappe.model.set_value(cdt, cdn, 'begin_time', frm.doc.begin_time);
        }
        
        // Set end_time từ parent  
        if (frm.doc.end_time) {
            frappe.model.set_value(cdt, cdn, 'end_time', frm.doc.end_time);
        }
        
        // Set begin_date và end_date từ parent
        if (frm.doc.begin_date) {
            frappe.model.set_value(cdt, cdn, 'begin_date', frm.doc.begin_date);
        }
        
        if (frm.doc.end_date) {
            frappe.model.set_value(cdt, cdn, 'end_date', frm.doc.end_date);
        }
        
        frm.refresh_field('employees_list');
        // Không cần tính total vì chưa có employee
    },
    
    // Khi xóa row, cập nhật total employees
    employees_list_remove: function(frm, cdt, cdn) {
        setTimeout(function() {
            frm.events.calculate_total_employees(frm);
        }, 100);
    },
    
    // Setup filter cho employee field
    employee: function(frm, cdt, cdn) {
        var row = locals[cdt][cdn];
        
        if (row.employee) {
            // Kiểm tra trùng lặp
            var selected_employees = [];
            frm.doc.employees_list.forEach(function(emp_row) {
                if (emp_row.name !== cdn && emp_row.employee) {
                    selected_employees.push(emp_row.employee);
                }
            });
            
            // Nếu employee đã được chọn
            if (selected_employees.includes(row.employee)) {
                frappe.msgprint({
                    title: __('Lỗi'),
                    message: __('Nhân viên {0} đã có trong danh sách. Vui lòng chọn nhân viên khác.', [row.employee]),
                    indicator: 'red'
                });
                
                // Function để reset toàn bộ row
                setTimeout(function() {
                    // Clear tất cả thông tin trong row
                    var fields_to_clear = ['employee', 'full_name', 'group', 'department', 'designation'];
                    
                    fields_to_clear.forEach(function(field) {
                        if (row.hasOwnProperty(field)) {
                            frappe.model.set_value(cdt, cdn, field, '');
                        }
                    });
                    
                    // Set lại time từ parent
                    if (frm.doc.begin_time) {
                        frappe.model.set_value(cdt, cdn, 'begin_time', frm.doc.begin_time);
                    }
                    if (frm.doc.end_time) {
                        frappe.model.set_value(cdt, cdn, 'end_time', frm.doc.end_time);
                    }
                    if (frm.doc.begin_date) {
                        frappe.model.set_value(cdt, cdn, 'begin_date', frm.doc.begin_date);
                    }
                    if (frm.doc.end_date) {
                        frappe.model.set_value(cdt, cdn, 'end_date', frm.doc.end_date);
                    }
                    
                    frm.refresh_field('employees_list');
                    
                    // Tính lại total employees sau khi clear duplicate
                    frm.events.calculate_total_employees(frm);
                }, 100);
                return;
            }
            
            // Set time cho dòng hợp lệ
            if (!row.begin_time && frm.doc.begin_time) {
                frappe.model.set_value(cdt, cdn, 'begin_time', frm.doc.begin_time);
            }
            if (!row.end_time && frm.doc.end_time) {
                frappe.model.set_value(cdt, cdn, 'end_time', frm.doc.end_time);
            }
            
            // Tính toán total employees khi có employee được chọn
            setTimeout(function() {
                frm.events.calculate_total_employees(frm);
            }, 200);
        } else if (!row.employee) {
            // Nếu employee bị clear, cũng cần tính lại total
            setTimeout(function() {
                frm.events.calculate_total_employees(frm);
            }, 200);
        }
    },
    
    // Validation trước khi save form
    validate: function(frm) {
        // Kiểm tra trùng lặp employee một lần nữa khi save
        var employees = [];
        var has_duplicate = false;
        
        frm.doc.employees_list.forEach(function(row) {
            if (row.employee) {
                if (employees.includes(row.employee)) {
                    has_duplicate = true;
                    frappe.validated = false;
                    frappe.msgprint({
                        title: __('Validation Error'),
                        message: __('Nhân viên {0} được chọn nhiều lần trong danh sách', [row.employee]),
                        indicator: 'red'
                    });
                } else {
                    employees.push(row.employee);
                }
            }
        });
        
        return !has_duplicate;
    }
});

// Optional: Thêm filter để ẩn employees đã được chọn
frappe.ui.form.on('Shift Registration Detail', {
    form_render: function(frm, cdt, cdn) {
        // Get employees đã được chọn
        var selected_employees = [];
        if (frm.doc.employees_list) {
            frm.doc.employees_list.forEach(function(row) {
                if (row.employee && row.name !== cdn) {
                    selected_employees.push(row.employee);
                }
            });
        }
        
        // Set filter cho employee field
        frm.set_query('employee', 'employees_list', function() {
            return {
                filters: {
                    'name': ['not in', selected_employees]
                }
            };
        });
    }
});