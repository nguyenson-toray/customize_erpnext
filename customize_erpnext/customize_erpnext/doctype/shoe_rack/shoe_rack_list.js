// shoe_rack_list.js - WITH DISPLAY NAME

frappe.listview_settings['Shoe Rack'] = {
    onload: function(listview) {
        // Dashboard
        listview.page.add_menu_item(__('Go To Dashboard'), function() {
            frappe.set_route('shoe-rack-dashboard');
        });
        
        // Bulk Create
        listview.page.add_inner_button(__('Bulk Create'), function() {
            show_bulk_create_dialog();
        });
        
        // Bulk Edit
        listview.page.add_inner_button(__('Bulk Edit'), function() {
            show_bulk_edit_dialog();
        });
        
        // Series Management Menu
        listview.page.add_menu_item(__('Check Series Health'), function() {
            check_series_health();
        });
        
        listview.page.add_menu_item(__('Fix All Inconsistencies'), function() {
            fix_all_inconsistencies();
        });
        
        listview.page.add_menu_item(__('Bulk Delete & Reset'), function() {
            show_bulk_delete_dialog();
        });
        
        listview.page.add_menu_item(__('Reset Empty Series'), function() {
            auto_reset_empty_series();
        });
        
        // Fix All Status
        // listview.page.add_menu_item(__('Fix All Status'), function() {
        //     fix_all_rack_status();
        // });
        
        // --------- NEW: Regenerate Display Names
        // listview.page.add_menu_item(__('Regenerate Display Names'), function() {
        //     regenerate_display_names();
        // });
    },
    
    // Indicator shows status, not rack name
    get_indicator: function(doc) {
        let color = 'gray';
        let label = doc.status || '';
        
        if (doc.status === '0/1' || doc.status === '0/2') {
            color = 'green';

        } else if (doc.status === '1/1' || doc.status === '2/2') {
            color = 'red';

        } else if (doc.status === '1/2') {
            color = 'orange';

        }
        
        return [label, color, 'status,=,' + doc.status];
    },
    
    formatters: {
        status: function(value) {
            let color = '';
            switch(value) {
                case '0/1':
                case '0/2':
                    color = 'green';
                    break;
                case '1/1':
                case '2/2':
                    color = 'red';
                    break;
                case '1/2':
                    color = 'orange';
                    break;
            }
            return `<span style="color: ${color}; font-weight: bold;">${value}</span>`;
        }
    }
};

// --------- NEW: Regenerate all display names
// function regenerate_display_names() {
//     frappe.confirm(
//         __('Regenerate display names for ALL racks? This will update the friendly name field.'),
//         function() {
//             frappe.show_alert({
//                 message: __('Processing... Please wait'),
//                 indicator: 'blue'
//             });
            
//             frappe.call({
//                 method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.regenerate_all_display_names',
//                 callback: function(r) {
//                     if (r.message && r.message.success) {
//                         frappe.show_alert({
//                             message: __(' {0}', [r.message.message]),
//                             indicator: 'green'
//                         }, 7);
                        
//                         cur_list.refresh();
//                     } else {
//                         frappe.msgprint({
//                             title: __('Error'),
//                             indicator: 'red',
//                             message: r.message ? r.message.message : 'Failed'
//                         });
//                     }
//                 }
//             });
//         }
//     );
// }

// Fix All Rack Status
// function fix_all_rack_status() {
//     frappe.confirm(
//         __('Recalculate status for ALL racks? This will check each rack and update status based on current assignments.'),
//         function() {
//             frappe.show_alert({
//                 message: __('Processing... Please wait'),
//                 indicator: 'blue'
//             });
            
//             frappe.call({
//                 method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.fix_all_rack_status',
//                 callback: function(r) {
//                     if (r.message && r.message.success) {
//                         frappe.show_alert({
//                             message: __(' {0} - Updated {1}/{2} racks', 
//                                 [r.message.message, r.message.updated, r.message.total]),
//                             indicator: 'green'
//                         }, 7);
                        
//                         cur_list.refresh();
//                     } else {
//                         frappe.msgprint({
//                             title: __('Error'),
//                             indicator: 'red',
//                             message: r.message ? r.message.message : 'Failed'
//                         });
//                     }
//                 }
//             });
//         }
//     );
// }

function show_bulk_create_dialog() {
    let dialog = new frappe.ui.Dialog({
        title: __('Bulk Create Shoe Racks'),
        fields: [
            {
                fieldname: 'rack_type',
                label: __('Rack Type'),
                fieldtype: 'Select',
                options: 'Standard Employee\nJapanese Employee\nGuest\nExternal Personnel',
                reqd: 1,
                default: 'Standard Employee',
                onchange: function() {
                    update_series_preview(dialog);
                }
            },
            {
                fieldname: 'quantity',
                label: __('Quantity'),
                fieldtype: 'Int',
                reqd: 1,
                default: 10
            },
            {
                fieldname: 'section_1',
                fieldtype: 'Section Break'
            },
            {
                fieldname: 'compartments',
                label: __('Compartments'),
                fieldtype: 'Select',
                options: '1\n2',
                reqd: 1,
                default: '1'
            },
            {
                fieldname: 'column_1',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'gender',
                label: __('Gender'),
                fieldtype: 'Select',
                options: 'Male\nFemale',
                reqd: 1,
                default: 'Male'
            },
            {
                fieldname: 'section_2',
                fieldtype: 'Section Break',
                label: 'Preview'
            },
            {
                fieldname: 'preview',
                fieldtype: 'HTML',
                options: '<div id="series-preview"></div>'
            }
        ],
        primary_action_label: __('Create'),
        primary_action: function(values) {
            create_racks(values, dialog);
        }
    });
    
    dialog.show();
    update_series_preview(dialog);
}

function update_series_preview(dialog) {
    let rack_type = dialog.get_value('rack_type');
    if (!rack_type) return;
    
    let series_map = {
        'Standard Employee': {prefix: 'RACK', display: 'Standard (1, 2, 3...)'},
        'Japanese Employee': {prefix: 'J', display: 'Japanese (J1, J2, J3...)'},
        'Guest': {prefix: 'G', display: 'Guest (G1, G2, G3...)'},
        'External Personnel': {prefix: 'A', display: 'External (A1, A2, A3...)'}
    };
    
    let series_info = series_map[rack_type];
    
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.get_next_series_number',
        args: {
            series_prefix: series_info.prefix
        },
        callback: function(r) {
            let next = r.message || 1;
            let quantity = dialog.get_value('quantity') || 10;
            let end = next + quantity - 1;
            
            let html = `
                <div style="padding: 15px; background: #e7f3ff; border: 1px solid #007bff; border-radius: 5px;">
                    <strong>📊 Series: ${series_info.display}</strong><br><br>
                    <table class="table table-bordered" style="font-size: 13px;">
                        <tr>
                            <td><strong>Next Number:</strong></td>
                            <td>${next}</td>
                        </tr>
                        <tr>
                            <td><strong>Will Create:</strong></td>
                            <td>${quantity} racks</td>
                        </tr>
                        <tr>
                            <td><strong>Display Range:</strong></td>
                            <td><strong>${format_display(series_info.prefix, next)} - ${format_display(series_info.prefix, end)}</strong></td>
                        </tr>
                    </table>
                </div>
            `;
            
            $('#series-preview').html(html);
        }
    });
}

function format_display(prefix, number) {
    return prefix === 'RACK' ? String(number) : prefix + number;
}

function create_racks(values, dialog) {
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.bulk_create_racks_by_type',
        args: {
            rack_type: values.rack_type,
            quantity: values.quantity,
            compartments: values.compartments,
            gender: values.gender
        },
        callback: function(r) {
            if (r.message && r.message.success) {
                frappe.show_alert({
                    message: __(' {0}', [r.message.message]),
                    indicator: 'green'
                }, 7);
                
                dialog.hide();
                cur_list.refresh();
            } else {
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: r.message.message || 'Failed'
                });
            }
        }
    });
}

// BULK EDIT
function show_bulk_edit_dialog() {
    let dialog = new frappe.ui.Dialog({
        title: __('Bulk Edit Empty Racks'),
        fields: [
            {
                fieldname: 'info',
                fieldtype: 'HTML',
                options: `
                    <div style="padding: 10px; background: #e7f3ff; border: 1px solid #007bff; border-radius: 5px; margin-bottom: 15px;">
                        <strong>ℹ️ Info:</strong><br>
                        Only <strong>empty racks (0/1 or 0/2)</strong> will be updated.<br>
                         Racks with assigned personnel must be cleared first.
                    </div>
                `
            },
            {
                fieldname: 'section_1',
                fieldtype: 'Section Break',
                label: 'Select Racks'
            },
            {
                fieldname: 'start_number',
                label: __('Start Number'),
                fieldtype: 'Int',
                reqd: 1,
                default: 1
            },
            {
                fieldname: 'column_1',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'end_number',
                label: __('End Number'),
                fieldtype: 'Int',
                reqd: 1,
                default: 10
            },
            {
                fieldname: 'column_2',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'series_prefix',
                label: __('Series'),
                fieldtype: 'Select',
                options: 'RACK\nJ\nG\nA',
                reqd: 1,
                default: 'RACK'
            },
            {
                fieldname: 'section_2',
                fieldtype: 'Section Break',
                label: 'Update Fields (leave blank to keep existing)'
            },
            {
                fieldname: 'compartments',
                label: __('Compartments'),
                fieldtype: 'Select',
                options: '\n1\n2',
                description: 'Leave blank to keep existing compartments'
            },
            {
                fieldname: 'column_3',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'gender',
                label: __('Gender'),
                fieldtype: 'Select',
                options: '\nMale\nFemale',
                description: 'Leave blank to keep existing gender'
            }
        ],
        primary_action_label: __('Update'),
        primary_action: function(values) {
            bulk_edit_racks(values, dialog);
        }
    });
    
    dialog.show();
}

function bulk_edit_racks(values, dialog) {
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.get_empty_racks_in_range',
        args: {
            start_number: values.start_number,
            end_number: values.end_number,
            series_prefix: values.series_prefix
        },
        callback: function(r) {
            if (r.message && r.message.total > 0) {
                frappe.confirm(
                    __('Found {0} empty racks. Update them?', [r.message.total]),
                    function() {
                        frappe.call({
                            method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.bulk_edit_empty_racks',
                            args: {
                                start_number: values.start_number,
                                end_number: values.end_number,
                                compartments: values.compartments,
                                gender: values.gender,
                                series_prefix: values.series_prefix
                            },
                            callback: function(r) {
                                if (r.message && r.message.success) {
                                    frappe.show_alert({
                                        message: __(' {0}', [r.message.message]),
                                        indicator: 'green'
                                    }, 7);
                                    
                                    dialog.hide();
                                    cur_list.refresh();
                                }
                            }
                        });
                    }
                );
            } else {
                frappe.msgprint(__('No empty racks found in this range'));
            }
        }
    });
}

function check_series_health() {
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.check_series_consistency',
        callback: function(r) {
            if (r.message) {
                let html = '<div style="padding: 20px;">';
                html += '<h4>📊 Series Health Check</h4><br>';
                html += '<table class="table table-bordered">';
                html += '<thead><tr><th>Series</th><th>Racks</th><th>Last#</th><th>Counter</th><th>Status</th></tr></thead><tbody>';
                
                for (let [prefix, info] of Object.entries(r.message)) {
                    let status_icon = info.is_consistent ? '' : '';
                    let status_text = info.is_consistent ? 'OK' : 'Needs Fix';
                    let status_color = info.is_consistent ? 'green' : 'orange';
                    
                    if (info.needs_reset) {
                        status_icon = '🔴';
                        status_text = 'Needs Reset';
                        status_color = 'red';
                    }
                    
                    html += `<tr>
                        <td><strong>${prefix}</strong></td>
                        <td>${info.rack_count}</td>
                        <td>${info.last_number}</td>
                        <td>${info.series_current}</td>
                        <td style="color: ${status_color};">${status_icon} ${status_text}</td>
                    </tr>`;
                }
                
                html += '</tbody></table>';
                html += '<div style="margin-top: 20px; padding: 15px; background: #fff3cd; border-radius: 5px;">';
                html += '<strong>💡 Recommendations:</strong><br>';
                html += '• If "Needs Reset" → Click "Fix All Inconsistencies"<br>';
                html += '• If "Needs Fix" → Check manually or click "Fix All"<br>';
                html += '• After bulk delete → Always run "Reset Empty Series"';
                html += '</div></div>';
                
                frappe.msgprint({
                    title: __('Series Health Report'),
                    message: html,
                    wide: true
                });
            }
        }
    });
}

function fix_all_inconsistencies() {
    frappe.confirm(
        __('This will reset all empty series to 0. Continue?'),
        function() {
            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.fix_all_inconsistencies',
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __(' {0}', [r.message.message]),
                            indicator: 'green'
                        }, 5);
                        
                        check_series_health();
                    }
                }
            });
        }
    );
}

function auto_reset_empty_series() {
    frappe.confirm(
        __('Reset all empty series (series with 0 racks) to 0?'),
        function() {
            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.auto_reset_empty_series',
                callback: function(r) {
                    if (r.message && r.message.success) {
                        frappe.show_alert({
                            message: __(' {0}', [r.message.message]),
                            indicator: 'green'
                        }, 5);
                    }
                }
            });
        }
    );
}

function show_bulk_delete_dialog() {
    let dialog = new frappe.ui.Dialog({
        title: __('Bulk Delete & Reset'),
        fields: [
            {
                fieldname: 'warning',
                fieldtype: 'HTML',
                options: `
                    <div style="padding: 15px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 5px; color: #856404;">
                        <strong> WARNING</strong><br><br>
                        This will:<br>
                        1. Delete ALL racks of selected series<br>
                        2. Reset series counter to 0<br>
                        3. Next rack will start from 1<br><br>
                        <strong style="color: red;">THIS CANNOT BE UNDONE!</strong>
                    </div>
                `
            },
            {
                fieldname: 'series_prefix',
                label: __('Select Series'),
                fieldtype: 'Select',
                options: 'RACK\nJ\nG\nA',
                reqd: 1,
                description: 'All racks of this series will be DELETED'
            }
        ],
        primary_action_label: __('Delete & Reset'),
        primary_action: function(values) {
            frappe.confirm(
                __('Are you ABSOLUTELY SURE? This will delete all {0}-* racks and reset to 0.', 
                   [values.series_prefix]),
                function() {
                    frappe.call({
                        method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.bulk_delete_and_reset',
                        args: {
                            series_prefix: values.series_prefix
                        },
                        callback: function(r) {
                            if (r.message && r.message.success) {
                                frappe.show_alert({
                                    message: __(' {0}', [r.message.message]),
                                    indicator: 'green'
                                }, 10);
                                
                                dialog.hide();
                                cur_list.refresh();
                            } else {
                                frappe.msgprint({
                                    title: __('Error'),
                                    indicator: 'red',
                                    message: r.message.message
                                });
                            }
                        }
                    });
                }
            );
        }
    });
    
    dialog.show();
}