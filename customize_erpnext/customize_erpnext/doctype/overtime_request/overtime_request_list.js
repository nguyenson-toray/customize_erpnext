// Simplified List View Override for Overtime Request
// Place this in: DocType > Overtime Request > List Settings > Client Script

frappe.listview_settings['Overtime Request'] = {
    add_fields: ["status", "requested_by", "manager_approver", "factory_manager_approver", "docstatus"],
    
    get_indicator: function(doc) {
        let status_color = {
            "Draft": "grey",
            "Pending Manager Approval": "orange", 
            "Pending Factory Manager Approval": "blue",
            "Approved": "green",
            "Rejected": "red",
            "Cancelled": "red"
        };
        
        return [doc.status, status_color[doc.status] || "grey", "status,=," + doc.status];
    },
    
    onload: function(listview) {
        console.log("Overtime Request List View Loaded");
        
        // Add manager-specific filters
        add_manager_filters(listview);
        
        // Add debug menu for System Manager
        // if (frappe.user.has_role(['System Manager', 'HR Manager'])) {
        //     add_debug_menu(listview);
        // }
    },
    
    // Custom formatting
    formatters: {
        status: function(value, field, doc) {
            let colors = {
                "Draft": "text-muted",
                "Pending Manager Approval": "text-warning",
                "Pending Factory Manager Approval": "text-info", 
                "Approved": "text-success",
                "Rejected": "text-danger",
                "Cancelled": "text-danger"
            };
            
            return `<span class="${colors[value] || 'text-muted'}">${value}</span>`;
        }
    }
};

function add_manager_filters(listview) {
    // Get current user's employee ID
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'Employee',
            filters: { 'user_id': frappe.session.user },
            fieldname: 'name'
        },
        callback: function(r) {
            if (r.message && r.message.name) {
                let employee_id = r.message.name;
                console.log("Current Employee ID:", employee_id);
                
                // Add "My Pending Approvals" filter for managers
                if (frappe.user.has_role(['Department Manager', 'TIQN Manager'])) {
                    listview.page.add_menu_item(__('My Pending Manager Approvals'), function() {
                        listview.filter_area.clear();
                        listview.filter_area.add([
                            ['Overtime Request', 'manager_approver', '=', employee_id],
                            ['Overtime Request', 'status', '=', 'Pending Manager Approval']
                        ]);
                        listview.refresh();
                    });
                }
                
                // Add "My Factory Manager Approvals" filter
                if (frappe.user.has_role(['Factory Manager', 'TIQN Factory Manager'])) {
                    listview.page.add_menu_item(__('My Pending Factory Approvals'), function() {
                        listview.filter_area.clear();
                        listview.filter_area.add([
                            ['Overtime Request', 'factory_manager_approver', '=', employee_id],
                            ['Overtime Request', 'status', '=', 'Pending Factory Manager Approval']
                        ]);
                        listview.refresh();
                    });
                }
                
                // Add "My Requests" filter for all employees
                listview.page.add_menu_item(__('My Requests'), function() {
                    listview.filter_area.clear();
                    listview.filter_area.add([
                        ['Overtime Request', 'requested_by', '=', employee_id]
                    ]);
                    listview.refresh();
                });
                
                // Add "All Requests" filter for managers
                if (frappe.user.has_role(['Department Manager', 'Factory Manager', 'TIQN Manager', 'TIQN Factory Manager', 'HR Manager'])) {
                    listview.page.add_menu_item(__('All Requests'), function() {
                        listview.filter_area.clear();
                        listview.refresh();
                    });
                }
            }
        }
    });
}

// function add_debug_menu(listview) {
//     // Debug permissions
//     listview.page.add_menu_item(__('Debug Permissions'), function() {
//         frappe.call({
//             method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.debug_user_permissions',
//             callback: function(r) {
//                 if (r.message) {
//                     console.log("Permission Debug Info:", r.message);
                    
//                     let debug_dialog = new frappe.ui.Dialog({
//                         title: 'Permission Debug Info',
//                         size: 'large',
//                         fields: [
//                             {
//                                 fieldname: 'debug_info',
//                                 fieldtype: 'Code',
//                                 label: 'Debug Information',
//                                 options: 'JSON',
//                                 value: JSON.stringify(r.message, null, 2)
//                             }
//                         ]
//                     });
//                     debug_dialog.show();
//                 } else {
//                     frappe.msgprint("No debug info available");
//                 }
//             },
//             error: function(r) {
//                 console.error("Debug error:", r);
//                 frappe.msgprint("Debug method not available. Check if Python code is updated.");
//             }
//         });
//     });
    
//     // Test custom query
//     listview.page.add_menu_item(__('Test Custom Query'), function() {
//         frappe.call({
//             method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.get_overtime_requests_list',
//             args: {
//                 filters: {},
//                 limit: 10
//             },
//             callback: function(r) {
//                 if (r.message) {
//                     console.log("Custom Query Result:", r.message);
//                     frappe.msgprint(`Custom query returned ${r.message.length} records. Check console for details.`);
//                 } else {
//                     frappe.msgprint("Custom query returned no results");
//                 }
//             },
//             error: function(r) {
//                 console.error("Custom query error:", r);
//                 frappe.msgprint("Custom query method not available. Check if Python code is updated.");
//             }
//         });
//     });
    
//     // Force refresh permissions
//     listview.page.add_menu_item(__('Force Refresh Permissions'), function() {
//         frappe.call({
//             method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.force_refresh_permissions',
//             callback: function(r) {
//                 frappe.show_alert({
//                     message: 'Permissions refreshed. Reloading...',
//                     indicator: 'green'
//                 });
//                 setTimeout(() => location.reload(), 1500);
//             },
//             error: function(r) {
//                 console.error("Refresh permissions error:", r);
//                 frappe.msgprint("Refresh permissions method not available.");
//             }
//         });
//     });
// }

// Add visual indicators with CSS when DOM is ready
$(document).ready(function() {
    console.log("Adding Overtime Request CSS styles");
    
    // Add CSS for status indicators
    let style = `
        <style id="overtime-request-styles">
            .list-row[data-status="Pending Manager Approval"] {
                border-left: 3px solid #ffa00a !important;
            }
            .list-row[data-status="Pending Factory Manager Approval"] {
                border-left: 3px solid #17a2b8 !important;
            }
            .list-row[data-status="Approved"] {
                border-left: 3px solid #28a745 !important;
            }
            .list-row[data-status="Rejected"] {
                border-left: 3px solid #dc3545 !important;
            }
            .list-row[data-status="Draft"] {
                border-left: 3px solid #6c757d !important;
            }
            .list-row[data-status="Cancelled"] {
                border-left: 3px solid #dc3545 !important;
            }
        </style>
    `;
    
    // Remove existing style if present
    $('#overtime-request-styles').remove();
    
    // Add new style
    $('head').append(style);
});

// Console logging for debugging
console.log("Overtime Request List View Script Loaded");
console.log("Current User Roles:", frappe.user_roles);
console.log("Current User:", frappe.session.user);