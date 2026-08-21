// shoe_rack_list.js - WITH DISPLAY NAME

frappe.listview_settings['Shoe Rack'] = {
    onload: function (listview) {
        // Dashboard
        listview.page.add_menu_item(__('Go To Dashboard'), function () {
            frappe.set_route('shoe-rack-dashboard');
        });

        // Bulk Create
        listview.page.add_inner_button(__('Bulk Create'), function () {
            show_bulk_create_dialog();
        });

        // Bulk Edit
        listview.page.add_inner_button(__('Bulk Edit'), function () {
            show_bulk_edit_dialog();
        });

        // Sync rack assignments -> Employee.custom_shoe_rack
        listview.page.add_inner_button(__('Sync to Employee'), function () {
            // show_sync_to_employee_dialog(listview);
            // temp disable
        });

        // Bulk flag Employee.custom_do_not_suggest_shoe_rack by Group, so
        // "Suggest Slots" (Assign Shoe Racks dashboard) never pairs a new
        // person into a rack these employees already occupy
        listview.page.add_menu_item(__('Bulk Set: Do Not Suggest Rack (by Group)'), function () {
            show_bulk_set_do_not_suggest_dialog();
        });

        // Series Management Menu
        // listview.page.add_menu_item(__('Check Series Health'), function () {
        //     check_series_health();
        // });

        listview.page.add_menu_item(__('Bulk Delete & Reset'), function () {
            show_bulk_delete_dialog();
        });

        listview.page.add_menu_item(__('Reset Empty Series'), function () {
            auto_reset_empty_series();
        });

        // Clear people out of racks (keep racks) so a new list can be imported fast
        listview.page.add_menu_item(__('Clear All Assignments'), function () {
            show_clear_assignments_dialog();
        });

        // Untick the "Chưa xác định (Unknown)" checkboxes in bulk
        listview.page.add_menu_item(__('Clear Unknown Flags'), function () {
            show_clear_unknown_dialog();
        });

        listview.page.add_menu_item(__('Fix All Inconsistencies'), function() {

            
            fix_all_inconsistencies();

            
        });

        // Fix All Status

        
        listview.page.add_menu_item(__('Fix All Status'), function() {
            fix_all_rack_status();
        });

        // --------- NEW: Regenerate Display Names
        listview.page.add_menu_item(__('Regenerate Display Names'), function() {
            regenerate_display_names();
        });
    },

    // Indicator shows status, not rack name
    get_indicator: function (doc) {
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
        status: function (value) {
            let color = '';
            switch (value) {
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
                onchange: function () {
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
        primary_action: function (values) {
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
        'Standard Employee': { prefix: 'RACK', display: 'Standard (1, 2, 3...)' },
        'Japanese Employee': { prefix: 'J', display: 'Japanese (J1, J2, J3...)' },
        'Guest': { prefix: 'G', display: 'Guest (G1, G2, G3...)' },
        'External Personnel': { prefix: 'A', display: 'External (A1, A2, A3...)' }
    };

    let series_info = series_map[rack_type];

    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.get_next_series_number',
        args: {
            series_prefix: series_info.prefix
        },
        callback: function (r) {
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
            compartments: values.compartments
        },
        callback: function (r) {
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
            }
        ],
        primary_action_label: __('Update'),
        primary_action: function (values) {
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
        callback: function (r) {
            if (r.message && r.message.total > 0) {
                frappe.confirm(
                    __('Found {0} empty racks. Update them?', [r.message.total]),
                    function () {
                        frappe.call({
                            method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.bulk_edit_empty_racks',
                            args: {
                                start_number: values.start_number,
                                end_number: values.end_number,
                                compartments: values.compartments,
                                series_prefix: values.series_prefix
                            },
                            callback: function (r) {
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

// SYNC TO EMPLOYEE
function show_sync_to_employee_dialog(listview) {
    // No rows ticked -> sync everything; ticked rows -> sync only those racks
    let selected = (listview.get_checked_items() || []).map(d => d.name);

    let scope_html = selected.length
        ? `<div style="padding: 10px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 5px; margin-bottom: 15px;">
               <strong>${__('Scope')}:</strong> ${__('only the {0} selected rack(s)', [selected.length])}
           </div>`
        : `<div style="padding: 10px; background: #e7f3ff; border: 1px solid #007bff; border-radius: 5px; margin-bottom: 15px;">
               <strong>${__('Scope')}:</strong> ${__('ALL racks (nothing selected)')}
           </div>`;

    let dialog = new frappe.ui.Dialog({
        title: __('Sync Racks to Employee'),
        fields: [
            {
                fieldname: 'info',
                fieldtype: 'HTML',
                options: `
                    ${scope_html}
                    <div style="padding: 10px; background: #e7f3ff; border: 1px solid #007bff; border-radius: 5px; margin-bottom: 15px;">
                        <strong>ℹ️ ${__('Info')}:</strong><br>
                        ${__('Shoe Rack is the source of truth. Each employee assigned to a compartment gets that rack written to their <b>Shoe Rack</b> field.')}
                    </div>
                `
            },
            {
                fieldname: 'clear_orphans',
                label: selected.length
                    ? __('Clear employees who point at a selected rack but are no longer in it')
                    : __('Clear employees no longer assigned to any rack'),
                fieldtype: 'Check',
                default: 0
            },
            {
                fieldname: 'section_1',
                fieldtype: 'Section Break',
                label: __('Preview')
            },
            {
                fieldname: 'preview',
                fieldtype: 'HTML',
                options: '<div id="sync-preview" class="text-muted">' + __('Loading...') + '</div>'
            }
        ],
        primary_action_label: __('Sync Now'),
        primary_action: function (values) {
            run_sync_to_employee(selected, values.clear_orphans, 0, dialog);
        }
    });

    dialog.fields_dict.clear_orphans.$input.on('change', function () {
        load_sync_preview(selected, dialog);
    });

    dialog.show();
    load_sync_preview(selected, dialog);
}

function load_sync_preview(selected, dialog) {
    run_sync_to_employee(selected, dialog.get_value('clear_orphans'), 1, dialog);
}

function run_sync_to_employee(selected, clear_orphans, dry_run, dialog) {
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.sync_racks_to_employees',
        args: {
            rack_names: selected,
            clear_orphans: clear_orphans ? 1 : 0,
            dry_run: dry_run
        },
        freeze: !dry_run,
        freeze_message: __('Syncing...'),
        callback: function (r) {
            if (!r.message || !r.message.success) {
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: (r.message && r.message.message) || __('Failed')
                });
                return;
            }

            if (dry_run) {
                $('#sync-preview').html(render_sync_summary(r.message));
                return;
            }

            dialog.hide();
            frappe.show_alert({
                message: r.message.message,
                indicator: 'green'
            }, 7);

            if (r.message.conflicts.length || r.message.missing.length) {
                frappe.msgprint({
                    title: __('Sync Result'),
                    message: render_sync_summary(r.message),
                    wide: true
                });
            }
        }
    });
}

function render_sync_summary(res) {
    let html = `<table class="table table-bordered" style="font-size: 13px;">
        <tr><td>${__('Racks scanned')}</td><td>${res.total_racks}</td></tr>
        <tr><td>${__('Employees to update')}</td><td><strong>${res.updated.length}</strong></td></tr>
        <tr><td>${__('To be cleared')}</td><td><strong>${res.cleared.length}</strong></td></tr>
    </table>`;

    if (res.conflicts.length) {
        html += `<div style="padding: 10px; background: #fff3cd; border: 1px solid #ffc107; border-radius: 5px; margin-top: 10px;">
            <strong>${__('Skipped - employee assigned to multiple racks')}:</strong><ul style="margin: 5px 0 0 0;">`;
        res.conflicts.forEach(c => {
            html += `<li>${frappe.utils.escape_html(c.employee)} → ${c.racks.map(frappe.utils.escape_html).join(', ')}</li>`;
        });
        html += '</ul></div>';
    }

    if (res.missing.length) {
        html += `<div style="padding: 10px; background: #f8d7da; border: 1px solid #dc3545; border-radius: 5px; margin-top: 10px;">
            <strong>${__('Employee not found')}:</strong> ${res.missing.map(frappe.utils.escape_html).join(', ')}
        </div>`;
    }

    if (!res.updated.length && !res.cleared.length) {
        html += `<div class="text-muted" style="margin-top: 10px;">${__('Everything is already in sync.')}</div>`;
    }

    return html;
}

function check_series_health() {
    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.check_series_consistency',
        callback: function (r) {
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
        function () {
            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.fix_all_inconsistencies',
                callback: function (r) {
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
        function () {
            frappe.call({
                method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.auto_reset_empty_series',
                callback: function (r) {
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

function show_clear_assignments_dialog() {
    let dialog = new frappe.ui.Dialog({
        title: __('Clear All Assignments'),
        fields: [
            {
                fieldname: 'info',
                fieldtype: 'HTML',
                options: `
                    <div style="padding: 15px; background: #d1ecf1; border: 1px solid #bee5eb; border-radius: 5px; color: #0c5460;">
                        <strong>${__('This will empty the racks, but KEEP them')}</strong><br><br>
                        ${__('Removes every employee / external personnel out of the compartments so the racks become empty. Useful before importing a new list.')}<br><br>
                        • ${__('Racks are NOT deleted')}<br>
                        • ${__('Series counter is NOT reset')}<br>
                        • ${__('Only the people are removed')}
                    </div>
                `
            },
            {
                fieldname: 'series_prefix',
                label: __('Scope'),
                fieldtype: 'Select',
                options: [
                    { value: '', label: __('All series') },
                    { value: 'RACK', label: 'RACK' },
                    { value: 'J', label: 'J' },
                    { value: 'G', label: 'G' },
                    { value: 'A', label: 'A' }
                ],
                default: '',
                description: __('Choose a series to clear, or "All series" to clear everything')
            }
        ],
        primary_action_label: __('Clear People'),
        primary_action: function (values) {
            let scope_label = values.series_prefix || __('ALL');
            frappe.confirm(
                __('Remove all people from {0} racks? Racks will stay, only assignments are cleared.', [scope_label]),
                function () {
                    frappe.call({
                        method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.clear_all_assignments',
                        args: {
                            series_prefix: values.series_prefix || null
                        },
                        freeze: true,
                        freeze_message: __('Clearing racks...'),
                        callback: function (r) {
                            if (r.message && r.message.success) {
                                frappe.show_alert({
                                    message: r.message.message,
                                    indicator: 'green'
                                }, 10);
                                dialog.hide();
                                cur_list.refresh();
                            } else {
                                frappe.msgprint({
                                    title: __('Error'),
                                    indicator: 'red',
                                    message: (r.message && r.message.message) || __('Failed')
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

// CLEAR UNKNOWN FLAGS
// The compartment_2_unidentified field used to default to 1, so every rack created
// in bulk came out pre-ticked as "Unknown" and counted as occupied. This unticks
// them in bulk and recalculates status.
function show_clear_unknown_dialog() {
    let dialog = new frappe.ui.Dialog({
        title: __('Clear Unknown Flags'),
        size: 'large',
        fields: [
            {
                fieldname: 'info',
                fieldtype: 'HTML',
                options: `
                    <div style="padding: 12px; background: #d1ecf1; border: 1px solid #bee5eb; border-radius: 5px; color: #0c5460; margin-bottom: 10px;">
                        ${__('Unticks the "Chưa xác định (Unknown)" checkbox on the selected compartments and recalculates each rack status.')}<br><br>
                        • ${__('Racks and people assignments are NOT touched')}<br>
                        • ${__('A rack flagged Unknown counts as occupied, so clearing it frees the slot up for Suggest Slots')}
                    </div>
                `
            },
            {
                fieldname: 'rack_type',
                label: __('Rack Type'),
                fieldtype: 'Select',
                options: [
                    { value: '', label: __('All rack types') },
                    { value: 'Standard Employee', label: 'Standard Employee' },
                    { value: 'Japanese Employee', label: 'Japanese Employee' },
                    { value: 'Guest', label: 'Guest' },
                    { value: 'External Personnel', label: 'External Personnel' }
                ],
                default: '',
                onchange: function () {
                    load_clear_unknown_preview(dialog);
                }
            },
            {
                fieldname: 'column_1',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'target',
                label: __('Compartment'),
                fieldtype: 'Select',
                options: [
                    { value: 'both', label: __('Both compartments') },
                    { value: '1', label: __('Compartment 1 only') },
                    { value: '2', label: __('Compartment 2 only') }
                ],
                default: 'both',
                reqd: 1,
                onchange: function () {
                    load_clear_unknown_preview(dialog);
                }
            },
            {
                fieldname: 'section_preview',
                fieldtype: 'Section Break',
                label: __('Preview')
            },
            {
                fieldname: 'preview',
                fieldtype: 'HTML',
                options: `<div id="clear-unknown-preview" class="text-muted">${__('Loading...')}</div>`
            }
        ],
        primary_action_label: __('Clear Flags'),
        primary_action: function (values) {
            run_clear_unknown(dialog, values, 0);
        }
    });

    dialog.show();
    load_clear_unknown_preview(dialog);
}

function load_clear_unknown_preview(dialog) {
    run_clear_unknown(dialog, dialog.get_values(true), 1);
}

function run_clear_unknown(dialog, values, dry_run) {
    if (!values) return;

    frappe.call({
        method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.clear_unidentified_flags',
        args: {
            rack_type: values.rack_type || null,
            target: values.target || 'both',
            dry_run: dry_run
        },
        freeze: !dry_run,
        freeze_message: __('Clearing flags...'),
        callback: function (r) {
            if (!r.message || !r.message.success) {
                frappe.msgprint({
                    title: __('Error'),
                    indicator: 'red',
                    message: (r.message && r.message.message) || __('Failed')
                });
                return;
            }

            if (dry_run) {
                $('#clear-unknown-preview').html(render_clear_unknown_summary(r.message));
                dialog.get_primary_btn().prop('disabled', r.message.racks_affected === 0);
                return;
            }

            dialog.hide();
            frappe.show_alert({
                message: r.message.message,
                indicator: 'green'
            }, 10);
            cur_list.refresh();
        }
    });
}

function render_clear_unknown_summary(res) {
    if (!res.racks_affected) {
        return `<div class="text-muted">${__('No rack has the Unknown flag ticked in this scope.')}</div>`;
    }

    let html = `<table class="table table-bordered" style="font-size: 13px;">
        <tr><td>${__('Racks to update')}</td><td><strong>${res.racks_affected}</strong></td></tr>
        <tr><td>${__('Compartment 1 flags to clear')}</td><td>${res.c1_cleared}</td></tr>
        <tr><td>${__('Compartment 2 flags to clear')}</td><td>${res.c2_cleared}</td></tr>
        <tr><td>${__('Racks whose status will change')}</td><td><strong>${res.status_changed}</strong></td></tr>
    </table>`;

    if (res.samples && res.samples.length) {
        html += `<div style="margin-top: 10px;"><strong>${__('Sample status changes')}:</strong>
            <table class="table table-bordered" style="font-size: 12px; margin-top: 5px;">
                <thead><tr><th>${__('Rack')}</th><th>${__('Before')}</th><th>${__('After')}</th></tr></thead><tbody>`;
        res.samples.forEach(s => {
            html += `<tr>
                <td>${frappe.utils.escape_html(String(s.rack))}</td>
                <td>${frappe.utils.escape_html(String(s.old_status || ''))}</td>
                <td><strong>${frappe.utils.escape_html(String(s.new_status || ''))}</strong></td>
            </tr>`;
        });
        html += '</tbody></table></div>';
    }

    return html;
}

// BULK SET DO NOT SUGGEST (by Group)
function show_bulk_set_do_not_suggest_dialog() {
    let dialog = new frappe.ui.Dialog({
        title: __('Bulk Set: Do Not Suggest Rack'),
        fields: [
            {
                fieldname: 'info',
                fieldtype: 'HTML',
                options: ` 
                    <div style="padding: 10px; background: #e7f3ff; border: 1px solid #007bff; border-radius: 5px; margin-bottom: 15px;">
                        <strong>ℹ️ ${__('Info')}:</strong><br>
                        ${__('Flags Employee.Do Not Suggest Shoe Rack for everyone in the selected Group. Once flagged, if that employee already occupies a rack compartment, the "Suggest Slots" action on the Shoe Rack Dashboard will never pair a new person into the other compartment of that same rack. It does not stop the flagged employee from being suggested a rack themselves if they don\'t have one yet.')}
                    </div>
                `
            },
            {
                fieldname: 'custom_group',
                label: __('Group'),
                fieldtype: 'Link',
                options: 'Group',
                reqd: 1
            },
            {
                fieldname: 'column_1',
                fieldtype: 'Column Break'
            },
            {
                fieldname: 'mode',
                label: __('Action'),
                fieldtype: 'Select',
                options: [__('Mark as Do Not Suggest'), __('Clear Do Not Suggest')].join('\n'),
                default: __('Mark as Do Not Suggest'),
                reqd: 1
            },
            {
                fieldname: 'section_1',
                fieldtype: 'Section Break'
            },
            {
                fieldname: 'active_only',
                label: __('Active employees only'),
                fieldtype: 'Check',
                default: 1
            }
        ],
        primary_action_label: __('Apply'),
        primary_action: function (values) {
            let value = values.mode === __('Mark as Do Not Suggest') ? 1 : 0;
            let action_desc = value
                ? __('flag "Do Not Suggest Shoe Rack" for')
                : __('clear "Do Not Suggest Shoe Rack" for');

            frappe.confirm(
                __('This will {0} every {1} employee in group "{2}". Continue?', [
                    action_desc,
                    values.active_only ? __('active') : __('active or left'),
                    values.custom_group
                ]),
                function () {
                    frappe.call({
                        method: 'customize_erpnext.api.api_endpoints.bulk_set_do_not_suggest_shoe_rack',
                        args: {
                            custom_group: values.custom_group,
                            value: value,
                            active_only: values.active_only ? 1 : 0
                        },
                        freeze: true,
                        freeze_message: __('Updating employees...'),
                        callback: function (r) {
                            if (r.exc || !r.message || !r.message.success) {
                                frappe.msgprint({
                                    title: __('Error'),
                                    indicator: 'red',
                                    message: (r.message && r.message.message) || __('Failed to update employees. Check Error Log.')
                                });
                                return;
                            }
                            dialog.hide();
                            frappe.show_alert({
                                message: __('Updated {0} employee(s).', [r.message.updated]),
                                indicator: 'green'
                            }, 5);
                        }
                    });
                }
            );
        }
    });

    dialog.show();
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
        primary_action: function (values) {
            frappe.confirm(
                __('Are you ABSOLUTELY SURE? This will delete all {0}-* racks and reset to 0.',
                    [values.series_prefix]),
                function () {
                    frappe.call({
                        method: 'customize_erpnext.customize_erpnext.doctype.shoe_rack.shoe_rack.bulk_delete_and_reset',
                        args: {
                            series_prefix: values.series_prefix
                        },
                        callback: function (r) {
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