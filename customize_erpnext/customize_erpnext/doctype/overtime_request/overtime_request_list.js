// Enhanced List View with Advanced Popup Approval Management (English Version)
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
        console.log("Enhanced Overtime Request List View Loaded");
        
        // Check user authority and add buttons
        check_user_authority_and_add_buttons(listview);
    },
    
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

function check_user_authority_and_add_buttons(listview) {
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.get_user_approval_authority',
        callback: function(r) {
            if (r.message && r.message.has_authority) {
                let authority_info = r.message;
                console.log("User has approval authority:", authority_info);
                
                add_enhanced_approval_buttons(listview, authority_info);
                add_approval_dashboard(listview, authority_info.employee_id);
            } else {
                console.log("User does not have approval authority");
                add_basic_user_filters(listview);
            }
        }
    });
}

function add_enhanced_approval_buttons(listview, authority_info) {
    let employee_id = authority_info.employee_id;
    
    // Main approval buttons with enhanced UI
    listview.page.add_inner_button(__('🔔 Pending Approval'), function() {
        show_enhanced_pending_popup(employee_id, authority_info);
    }).addClass('btn-warning btn-approval-main').attr('id', 'pending-approvals-btn');
    
    listview.page.add_inner_button(__('📋 Processed'), function() {
        show_enhanced_processed_popup(employee_id, authority_info);
    }).addClass('btn-success btn-approval-main');
    
    // Update button with live count
    update_pending_button_count(employee_id);
    
    // Auto-refresh count every 30 seconds
    setInterval(() => {
        update_pending_button_count(employee_id);
    }, 30000);
}

function update_pending_button_count(employee_id) {
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.get_pending_approvals_count',
        args: { employee_id: employee_id },
        callback: function(r) {
            if (r.message && r.message.count > 0) {
                let btn = $('#pending-approvals-btn');
                if (btn.length) {
                    btn.html(`🔔 Pending Approval (${r.message.count})`).addClass('btn-pulse');
                }
            }
        }
    });
}

function show_enhanced_pending_popup(employee_id, authority_info) {
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.get_pending_approvals_for_user',
        args: { employee_id: employee_id },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                create_enhanced_approval_popup(r.message, 'pending', employee_id, authority_info);
            } else {
                show_no_data_message('No requests pending your approval', 'blue');
            }
        }
    });
}

function show_enhanced_processed_popup(employee_id, authority_info) {
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.get_processed_approvals_for_user',
        args: { employee_id: employee_id },
        callback: function(r) {
            if (r.message && r.message.length > 0) {
                create_enhanced_approval_popup(r.message, 'processed', employee_id, authority_info);
            } else {
                show_no_data_message('You haven\'t processed any overtime requests', 'grey');
            }
        }
    });
}

function create_enhanced_approval_popup(data, type, employee_id, authority_info) {
    let title = type === 'pending' ? 
        `🔔 Pending Approval Requests (${data.length})` : 
        `📋 Processed Requests (${data.length})`;
    
    let dialog = new frappe.ui.Dialog({
        title: title,
        size: 'extra-large',
        fields: [
            {
                fieldname: 'header_section',
                fieldtype: 'HTML'
            },
            {
                fieldname: 'records_section',
                fieldtype: 'HTML'
            },
            {
                fieldname: 'footer_section',
                fieldtype: 'HTML'
            }
        ],
        primary_action_label: type === 'pending' ? 'Refresh' : 'Close',
        primary_action: function() {
            if (type === 'pending') {
                dialog.hide();
                show_enhanced_pending_popup(employee_id, authority_info);
            } else {
                dialog.hide();
            }
        }
    });
    
    // Add header with user info and bulk actions
    let header_html = create_popup_header(authority_info, type, data.length);
    dialog.fields_dict.header_section.$wrapper.html(header_html);
    
    // Add main records table
    let records_html = create_enhanced_records_table(data, type, employee_id);
    dialog.fields_dict.records_section.$wrapper.html(records_html);
    
    // Add footer with summary
    if (type === 'pending') {
        let footer_html = create_pending_footer(data);
        dialog.fields_dict.footer_section.$wrapper.html(footer_html);
    }
    
    // Add event handlers
    add_enhanced_popup_handlers(dialog, employee_id, authority_info);
    
    dialog.show();
    
    // Auto-resize dialog
    dialog.$wrapper.find('.modal-dialog').css('max-width', '95vw');
}

function create_popup_header(authority_info, type, count) {
    let user_info = `
        <div class="approval-header bg-light p-3 mb-3 rounded">
            <div class="row">
                <div class="col-md-8">
                    <h5 class="mb-1">
                        <i class="fa fa-user-circle text-primary"></i>
                        ${authority_info.employee_name} (${authority_info.employee_id})
                    </h5>
                    <p class="text-muted mb-0">
                        <strong>Position:</strong> ${authority_info.designation || 'N/A'} | 
                        <strong>Department:</strong> ${authority_info.department || 'N/A'}
                    </p>
                </div>
                <div class="col-md-4 text-right">
                    <span class="badge badge-${type === 'pending' ? 'warning' : 'success'} badge-lg">
                        ${count} request${count > 1 ? 's' : ''}
                    </span>
                </div>
            </div>
    `;
    
    if (type === 'pending' && count > 0) {
        user_info += `
            <div class="row mt-3">
                <div class="col-12">
                    <div class="btn-group" role="group">
                        <button type="button" class="btn btn-success btn-sm bulk-approve-all">
                            <i class="fa fa-check-circle"></i> Approve All
                        </button>
                        <button type="button" class="btn btn-outline-success btn-sm bulk-approve-selected">
                            <i class="fa fa-check"></i> Approve Selected
                        </button>
                        <button type="button" class="btn btn-outline-secondary btn-sm select-all-records">
                            <i class="fa fa-check-square-o"></i> Select All
                        </button>
                        <button type="button" class="btn btn-outline-secondary btn-sm deselect-all-records">
                            <i class="fa fa-square-o"></i> Deselect All
                        </button>
                    </div>
                </div>
            </div>
        `;
    }
    
    user_info += '</div>';
    return user_info;
}

function create_enhanced_records_table(data, type, employee_id) {
    if (!data || data.length === 0) {
        return create_empty_state(type);
    }
    
    let html = `
        <div class="records-container">
            <div class="table-responsive">
                <table class="table table-striped table-hover approval-records-table">
                    <thead class="thead-dark sticky-top">
                        <tr>
    `;
    
    if (type === 'pending') {
        html += '<th width="40px" class="text-center"><input type="checkbox" class="select-all-checkbox"></th>';
    }
    
    html += `
                            <th width="120px" class="text-center">ID</th>
                            <th width="180px" class="text-center">Requested By</th>
                            <th width="100px" class="text-center">OT Date</th>
                            <th width="80px" class="text-center">People</th>
                            <th width="80px" class="text-center">Total Hours</th>
                            <th width="120px" class="text-center">Status</th>
                            <th width="120px" class="text-center">Approval Level</th>
                            <th width="150px" class="text-center">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
    `;
    
    data.forEach(function(record, index) {
        let approval_level = get_approval_level_for_user(record, employee_id);
        let row_class = type === 'pending' ? 'pending-row' : 'processed-row';
        
        html += `<tr class="${row_class}" data-name="${record.name}" data-approval-level="${approval_level}">`;
        
        if (type === 'pending') {
            let can_approve = approval_level.includes('pending');
            html += `
                <td class="text-center">
                    <input type="checkbox" class="record-checkbox" 
                           data-name="${record.name}" 
                           data-approval-type="${approval_level.replace('_pending', '')}"
                           ${can_approve ? '' : 'disabled'}>
                </td>
            `;
        }
        
        html += `
            <td class="text-center">
                <a href="/app/overtime-request/${record.name}" target="_blank" class="text-primary font-weight-bold">
                    ${record.name}
                </a>
            </td>
            <td class="text-center">
                <div class="employee-info">
                    <div class="font-weight-medium">${record.requested_by_name || record.requested_by}</div>
                    <small class="text-muted">${record.requested_by}</small>
                </div>
            </td>
            <td class="text-center">
                <span class="text-nowrap">${frappe.datetime.str_to_user(record.ot_date)}</span>
            </td>
            <td class="text-center">
                <span class="badge badge-info">${record.total_employees || 0}</span>
            </td>
            <td class="text-center">
                <span class="badge badge-secondary">${record.total_hours || 0}h</span>
            </td>
            <td class="text-center">${get_status_badge(record.status)}</td>
            <td class="text-center">${get_approval_level_badge(approval_level)}</td>
            <td class="text-center">${get_enhanced_action_buttons(record, type, approval_level)}</td>
        </tr>`;
    });
    
    html += `
                    </tbody>
                </table>
            </div>
        </div>
    `;
    
    return html;
}

function get_enhanced_action_buttons(record, type, approval_level) {
    if (type === 'pending') {
        if (approval_level === 'manager_pending') {
            return `
                <div class="btn-group-vertical btn-group-sm">
                    <button class="btn btn-success btn-xs approve-btn" 
                            data-name="${record.name}" data-type="manager">
                        <i class="fa fa-check"></i> Approve
                    </button>
                    <button class="btn btn-danger btn-xs reject-btn mt-1" 
                            data-name="${record.name}" data-type="manager">
                        <i class="fa fa-times"></i> Reject
                    </button>
                </div>
            `;
        } else if (approval_level === 'factory_manager_pending') {
            return `
                <div class="btn-group-vertical btn-group-sm">
                    <button class="btn btn-success btn-xs approve-btn" 
                            data-name="${record.name}" data-type="factory_manager">
                        <i class="fa fa-check"></i> Approve
                    </button>
                    <button class="btn btn-danger btn-xs reject-btn mt-1" 
                            data-name="${record.name}" data-type="factory_manager">
                        <i class="fa fa-times"></i> Reject
                    </button>
                </div>
            `;
        } else {
            return '<span class="text-muted small">Cannot approve</span>';
        }
    } else {
        // Processed records - Link directly to record
        let processed_date = '';
        if (record.manager_approved_on && approval_level.includes('manager')) {
            processed_date = frappe.datetime.str_to_user(record.manager_approved_on);
        } else if (record.factory_manager_approved_on && approval_level.includes('factory')) {
            processed_date = frappe.datetime.str_to_user(record.factory_manager_approved_on);
        }
        
        return `
            <div class="text-center">
                <a href="/app/overtime-request/${record.name}" target="_blank" 
                   class="btn btn-outline-primary btn-xs">
                    <i class="fa fa-external-link"></i> Details
                </a>
                ${processed_date ? `<br><small class="text-muted">${processed_date}</small>` : ''}
            </div>
        `;
    }
}

function create_pending_footer(data) {
    let total_employees = data.reduce((sum, record) => sum + (record.total_employees || 0), 0);
    let total_hours = data.reduce((sum, record) => sum + (record.total_hours || 0), 0);
    
    return `
        <div class="approval-footer bg-light p-3 mt-3 rounded">
            <div class="row">
                <div class="col-md-4">
                    <div class="text-center">
                        <h4 class="mb-1 text-primary">${data.length}</h4>
                        <small class="text-muted">Pending requests</small>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="text-center">
                        <h4 class="mb-1 text-info">${total_employees}</h4>
                        <small class="text-muted">Total employees</small>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="text-center">
                        <h4 class="mb-1 text-warning">${total_hours.toFixed(1)}</h4>
                        <small class="text-muted">Total OT hours</small>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function add_enhanced_popup_handlers(dialog, employee_id, authority_info) {
    // Existing handlers
    add_standard_popup_handlers(dialog, employee_id);
    
    // Enhanced handlers
    
    // Select all checkbox
    dialog.$wrapper.on('change', '.select-all-checkbox', function() {
        let checked = $(this).is(':checked');
        dialog.$wrapper.find('.record-checkbox:not(:disabled)').prop('checked', checked);
    });
    
    // Bulk approve selected
    dialog.$wrapper.on('click', '.bulk-approve-selected', function() {
        let selected = dialog.$wrapper.find('.record-checkbox:checked');
        if (selected.length === 0) {
            frappe.msgprint('Please select at least one request to approve');
            return;
        }
        
        let requests = [];
        selected.each(function() {
            requests.push({
                name: $(this).data('name'),
                approval_type: $(this).data('approval-type')
            });
        });
        
        bulk_approve_requests(requests, dialog, employee_id, authority_info);
    });
    
    // Bulk approve all
    dialog.$wrapper.on('click', '.bulk-approve-all', function() {
        let all_checkboxes = dialog.$wrapper.find('.record-checkbox:not(:disabled)');
        let requests = [];
        
        all_checkboxes.each(function() {
            requests.push({
                name: $(this).data('name'),
                approval_type: $(this).data('approval-type')
            });
        });
        
        if (requests.length === 0) {
            frappe.msgprint('No requests can be approved');
            return;
        }
        
        bulk_approve_requests(requests, dialog, employee_id, authority_info);
    });
    
    // Select/Deselect all buttons
    dialog.$wrapper.on('click', '.select-all-records', function() {
        dialog.$wrapper.find('.record-checkbox:not(:disabled)').prop('checked', true);
    });
    
    dialog.$wrapper.on('click', '.deselect-all-records', function() {
        dialog.$wrapper.find('.record-checkbox').prop('checked', false);
    });
}

function bulk_approve_requests(requests, dialog, employee_id, authority_info) {
    if (requests.length === 0) return;
    
    frappe.confirm(
        `Are you sure you want to approve ${requests.length} request(s)?`,
        function() {
            // Show progress
            let progress_dialog = show_progress_dialog('Processing...', requests.length);
            
            let completed = 0;
            let errors = [];
            
            requests.forEach(function(request, index) {
                setTimeout(() => {
                    frappe.call({
                        method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.approve_overtime_request',
                        args: {
                            name: request.name,
                            approval_type: request.approval_type,
                            comments: 'Bulk approval'
                        },
                        callback: function(r) {
                            completed++;
                            
                            if (r.exc) {
                                errors.push(`${request.name}: ${r.exc}`);
                            }
                            
                            // Update progress
                            let progress = (completed / requests.length) * 100;
                            progress_dialog.set_progress(progress);
                            
                            // If all completed
                            if (completed === requests.length) {
                                progress_dialog.hide();
                                
                                if (errors.length === 0) {
                                    frappe.show_alert({
                                        message: `Successfully approved ${requests.length} request(s)!`,
                                        indicator: 'green'
                                    });
                                } else {
                                    frappe.msgprint({
                                        title: 'Processing Results',
                                        message: `
                                            <p><strong>Success:</strong> ${requests.length - errors.length}</p>
                                            <p><strong>Errors:</strong> ${errors.length}</p>
                                            ${errors.length > 0 ? '<hr><small>' + errors.join('<br>') + '</small>' : ''}
                                        `,
                                        indicator: errors.length > 0 ? 'orange' : 'green'
                                    });
                                }
                                
                                // Refresh popup
                                dialog.hide();
                                setTimeout(() => {
                                    show_enhanced_pending_popup(employee_id, authority_info);
                                }, 1000);
                            }
                        }
                    });
                }, index * 500); // Stagger requests
            });
        }
    );
}

function show_progress_dialog(title, total) {
    let dialog = new frappe.ui.Dialog({
        title: title,
        fields: [
            {
                fieldname: 'progress_html',
                fieldtype: 'HTML'
            }
        ]
    });
    
    dialog.set_progress = function(percent) {
        let html = `
            <div class="progress mb-3">
                <div class="progress-bar bg-success" style="width: ${percent}%"></div>
            </div>
            <p class="text-center">${Math.round(percent)}% completed</p>
        `;
        dialog.fields_dict.progress_html.$wrapper.html(html);
    };
    
    dialog.set_progress(0);
    dialog.show();
    
    return dialog;
}

// CSS Styles
$(document).ready(function() {
    let enhanced_styles = `
        <style id="enhanced-approval-styles">
            .btn-approval-main {
                margin-right: 10px !important;
                font-weight: 600 !important;
                border-radius: 6px !important;
                padding: 8px 16px !important;
            }
            
            .btn-pulse {
                animation: pulse 2s infinite;
            }
            
            @keyframes pulse {
                0% { box-shadow: 0 0 0 0 rgba(255, 193, 7, 0.7); }
                70% { box-shadow: 0 0 0 10px rgba(255, 193, 7, 0); }
                100% { box-shadow: 0 0 0 0 rgba(255, 193, 7, 0); }
            }
            
            .approval-records-table {
                font-size: 0.875rem;
            }
            
            .approval-records-table thead th {
                background-color: #343a40 !important;
                color: white !important;
                border-color: #454d55 !important;
                font-weight: 600;
                text-align: center !important;
                vertical-align: middle !important;
            }
            
            .approval-records-table tbody td {
                text-align: center !important;
                vertical-align: middle !important;
                padding: 8px !important;
            }
            
            .approval-records-table tbody tr:hover {
                background-color: rgba(0,123,255,0.1) !important;
            }
            
            .employee-info {
                line-height: 1.2;
            }
            
            .btn-xs {
                padding: 2px 6px;
                font-size: 0.75rem;
                line-height: 1.2;
            }
            
            .approval-header {
                border: 1px solid #dee2e6;
            }
            
            .approval-footer {
                border: 1px solid #dee2e6;
            }
            
            .badge-lg {
                font-size: 0.875rem;
                padding: 0.5rem 0.75rem;
            }
            
            .records-container {
                max-height: 60vh;
                overflow-y: auto;
            }
            
            .sticky-top {
                position: sticky;
                top: 0;
                z-index: 10;
            }
            
            /* Center align specific elements */
            .approval-records-table .text-center {
                text-align: center !important;
            }
            
            .approval-records-table .employee-info {
                text-align: center !important;
            }
            
            .approval-records-table .btn-group-vertical {
                display: inline-block;
            }
        </style>
    `;
    
    $('#enhanced-approval-styles').remove();
    $('head').append(enhanced_styles);
});

// Helper functions
function get_status_badge(status) {
    let badge_class = {
        "Draft": "secondary",
        "Pending Manager Approval": "warning",
        "Pending Factory Manager Approval": "info",
        "Approved": "success",
        "Rejected": "danger",
        "Cancelled": "dark"
    };
    
    return `<span class="badge badge-${badge_class[status] || 'secondary'}">${status}</span>`;
}

function get_approval_level_for_user(record, employee_id) {
    let is_manager_approver = record.manager_approver && record.manager_approver.startsWith(employee_id + ' -');
    let is_factory_manager_approver = record.factory_manager_approver && record.factory_manager_approver.startsWith(employee_id + ' -');
    
    if (record.status === 'Pending Manager Approval' && is_manager_approver) {
        return 'manager_pending';
    } else if (record.status === 'Pending Factory Manager Approval' && is_factory_manager_approver) {
        return 'factory_manager_pending';
    } else if (is_manager_approver) {
        return 'manager_processed';
    } else if (is_factory_manager_approver) {
        return 'factory_manager_processed';
    }
    
    return 'other';
}

function get_approval_level_badge(approval_level) {
    switch(approval_level) {
        case 'manager_pending':
            return '<span class="badge badge-warning">Dept. Manager</span>';
        case 'factory_manager_pending':
            return '<span class="badge badge-info">Factory Manager</span>';
        case 'manager_processed':
            return '<span class="badge badge-success">Dept. Manager ✓</span>';
        case 'factory_manager_processed':
            return '<span class="badge badge-success">Factory Manager ✓</span>';
        default:
            return '<span class="badge badge-light">Other</span>';
    }
}

function add_standard_popup_handlers(dialog, employee_id) {
    // Individual approve button
    dialog.$wrapper.on('click', '.approve-btn', function() {
        let name = $(this).data('name');
        let type = $(this).data('type');
        
        frappe.confirm(
            `Are you sure you want to approve overtime request ${name}?`,
            function() {
                frappe.call({
                    method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.approve_overtime_request',
                    args: {
                        name: name,
                        approval_type: type,
                        comments: ''
                    },
                    callback: function(r) {
                        if (!r.exc) {
                            frappe.show_alert({
                                message: 'Successfully approved!',
                                indicator: 'green'
                            });
                            
                            // Remove row or refresh
                            dialog.$wrapper.find(`tr[data-name="${name}"]`).fadeOut();
                        }
                    }
                });
            }
        );
    });
    
    // Individual reject button
    dialog.$wrapper.on('click', '.reject-btn', function() {
        let name = $(this).data('name');
        let type = $(this).data('type');
        
        frappe.prompt([
            {
                label: 'Rejection Reason',
                fieldname: 'comments',
                fieldtype: 'Text',
                reqd: 1
            }
        ], function(values) {
            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.overtime_request.overtime_request.reject_overtime_request',
                args: {
                    name: name,
                    rejection_type: type,
                    comments: values.comments
                },
                callback: function(r) {
                    if (!r.exc) {
                        frappe.show_alert({
                            message: 'Successfully rejected!',
                            indicator: 'orange'
                        });
                        
                        dialog.$wrapper.find(`tr[data-name="${name}"]`).fadeOut();
                    }
                }
            });
        }, 'Reject Request', 'Reject');
    });
}

function show_no_data_message(message, indicator) {
    frappe.msgprint({
        title: 'Notification',
        message: message,
        indicator: indicator
    });
}

function create_empty_state(type) {
    let icon = type === 'pending' ? 'fa-clock-o' : 'fa-check-circle';
    let message = type === 'pending' ? 
        'No pending approval requests' : 
        'No processed requests yet';
    
    return `
        <div class="text-center text-muted p-5">
            <i class="fa ${icon} fa-4x mb-3"></i>
            <h4>${message}</h4>
            <p>Data will appear when new requests are available.</p>
        </div>
    `;
}

function add_basic_user_filters(listview) {
    // Basic filters for non-managers
    listview.page.add_menu_item(__('📝 My Requests'), function() {
        frappe.call({
            method: 'frappe.client.get_value',
            args: {
                doctype: 'Employee',
                filters: { 'user_id': frappe.session.user },
                fieldname: 'name'
            },
            callback: function(r) {
                if (r.message && r.message.name) {
                    listview.filter_area.clear();
                    listview.filter_area.add([
                        ['Overtime Request', 'requested_by', '=', r.message.name]
                    ]);
                    listview.refresh();
                }
            }
        });
    });
}