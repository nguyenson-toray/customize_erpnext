// Stock Entry Quick Import - Merged functionality from stock_entry_import_excel.js and stock_entry_quick_item.js
// Features: Excel import, Quick Add items, Duplicate rows, Progress tracking, Validation
// Combined all functions, events, and logic from both files

frappe.ui.form.on('Stock Entry', {
    refresh: function (frm) {
        // Import Excel functionality
        add_import_button_if_needed(frm);
        
        // Quick Add functionality
        initialize_form_buttons_se(frm);

        // Duplicate functionality
        let duplicate_btn = frm.fields_dict.items.grid.add_custom_button(__('Duplicate Selected'),
            function () {
                try {
                    let selected_rows = frm.fields_dict.items.grid.get_selected();

                    if (frm.doc.docstatus === 1) {
                        throw new Error('Cannot duplicate rows in a submitted document');
                    }

                    if (selected_rows.length === 0) {
                        throw new Error('Please select one or more rows to duplicate');
                    }

                    // Duplicate logic using original pattern to avoid mandatory field issues
                    selected_rows.forEach(function (row_name) {
                        let source_row = locals['Stock Entry Detail'][row_name];

                        // Add new row first
                        let new_row = frm.add_child('items');

                        // Copy all fields except system fields
                        Object.keys(source_row).forEach(function (field) {
                            if (!['name', 'idx', 'docstatus', 'creation', 'modified', 'owner', 'modified_by'].includes(field)) {
                                new_row[field] = source_row[field];
                            }
                        });
                    });

                    // Refresh grid to show new rows
                    frm.refresh_field('items');

                    // Show success message
                    frappe.show_alert({
                        message: __(`${selected_rows.length} row(s) duplicated successfully`),
                        indicator: 'green'
                    });
                } catch (error) {
                    frappe.msgprint({
                        title: __('Duplicate Error'),
                        message: __(error.message),
                        indicator: 'red'
                    });
                }
            }
        );

        // Save reference for access from other functions
        frm.duplicate_btn = duplicate_btn;

        // Setup listener to monitor selection changes for duplicate button
        setup_selection_monitor_se(frm);

        // Update duplicate button style
        update_duplicate_button_style_se(frm);
    },

    purpose: function (frm) {
        add_import_button_if_needed(frm);
    },

    onload: function (frm) {
        // Import Excel functionality
        add_import_button_if_needed(frm);
        
        // Quick Add functionality
        // Setup cleanup for browser navigation/close
        $(window).on('beforeunload.quick_add_se', function () {
            // Cleanup any remaining intervals or listeners
        });

        // Setup keyboard shortcuts for duplicate functionality
        $(document).on('keydown.duplicate_rows_se', function (e) {
            // Only work when focused on this form
            if (frm.doc.name && frm.doc.doctype === 'Stock Entry') {
                // Ctrl+D to duplicate
                if (e.ctrlKey && e.keyCode === 68) {
                    e.preventDefault();

                    let selected_rows = frm.fields_dict.items.grid.get_selected();
                    if (selected_rows.length > 0) {
                        selected_rows.forEach(function (row_name) {
                            let source_row = locals['Stock Entry Detail'][row_name];

                            // Add new row first
                            let new_row = frm.add_child('items');

                            // Copy all fields except system fields
                            Object.keys(source_row).forEach(function (field) {
                                if (!['name', 'idx', 'docstatus', 'creation', 'modified', 'owner', 'modified_by'].includes(field)) {
                                    new_row[field] = source_row[field];
                                }
                            });
                        });

                        frm.refresh_field('items');
                        frappe.show_alert(__('Rows duplicated with Ctrl+D'));
                    }
                }
            }
        });
    },

    // Cleanup event when form is destroyed
    before_load: function (frm) {
        // Simple cleanup - keyboard and window events only
        $(document).off('keydown.duplicate_rows_se');
        $(window).off('beforeunload.quick_add_se');
    },

    stock_entry_type: function (frm) {
        // Re-initialize form buttons when stock entry type changes
        initialize_form_buttons_se(frm);
    },

    // Validate before submit to ensure custom fields are properly set
    before_submit: function (frm) {
        // Basic validation only - no date validation needed
        frappe.validated = true;
    },

    // Update button states when document status changes
    after_save: function (frm) {
        // Re-initialize form buttons after save
        setTimeout(() => {
            initialize_form_buttons_se(frm);
            update_duplicate_button_style_se(frm);
        }, 300);
    }
});

// Event handlers for individual child table row changes
frappe.ui.form.on('Stock Entry Detail', {
    custom_invoice_number: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        // Trim the field when user moves out of the field
        if (row.custom_invoice_number && typeof row.custom_invoice_number === 'string') {
            let trimmed_value = row.custom_invoice_number.trim();

            if (row.custom_invoice_number !== trimmed_value) {
                frappe.model.set_value(cdt, cdn, 'custom_invoice_number', trimmed_value);
            }
        }
    }
});

// ============================================
// EXCEL IMPORT FUNCTIONALITY
// ============================================

function add_import_button_if_needed(frm) {
    // Remove existing button first
    frm.remove_custom_button(__('Import Material Issue'));

    // Debug logging
    console.log('Purpose check:', frm.doc.purpose);
    console.log('Is local:', frm.doc.__islocal);

    // Only show import button for Material Issue
    if (frm.doc.purpose === 'Material Issue') {
        frm.add_custom_button(__('Import Material Issue'), function () {
            show_import_dialog(frm);
        }, __('Actions'));

        console.log('Import Material Issue button added');
    }
}

function show_import_dialog(frm) {
    let dialog = new frappe.ui.Dialog({
        title: __('Import Material Issue from Excel'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'instructions',
                options: `
                    <div class="alert alert-info">
                        <h5><i class="fa fa-info-circle"></i> How to Import Material Issue</h5>
                        <ol>
                            <li><strong>Download Template:</strong> Click "Download Excel Template" below</li>
                            <li><strong>Fill Data:</strong> Complete the template with your material issue data</li>
                            <li><strong>Upload File:</strong> Choose your completed Excel file</li>
                            <li><strong>Validate:</strong> Click "Validate Data" to check for errors</li>
                            <li><strong>Import:</strong> If validation passes, click "Import Data" to create Stock Entries</li>
                        </ol>
                        <div class="alert alert-warning">
                            <strong>Required Columns:</strong>
                            <code>custom_item_name_detail</code>, <code>custom_no</code>, 
                            <code>qty</code>, <code>custom_invoice_number</code>
                        </div>
                    </div>
                `
            },
            {
                fieldtype: 'Section Break',
                fieldname: 'template_section',
                label: __('Step 1: Download Template')
            },
            {
                fieldtype: 'Button',
                fieldname: 'download_template',
                label: __('📥 Download Excel Template'),
                click: function () {
                    download_excel_template();
                }
            },
            {
                fieldtype: 'HTML',
                fieldname: 'template_info',
                options: '<small class="text-muted"><i class="fa fa-info-circle"></i> Template includes sample data and instructions</small>'
            },
            {
                fieldtype: 'Section Break',
                fieldname: 'upload_section',
                label: __('Step 2: Upload Your Data')
            },
            {
                fieldtype: 'Attach',
                fieldname: 'excel_file',
                label: __('📁 Select Excel File'),
                options: {
                    restrictions: {
                        allowed_file_types: ['.xlsx', '.xls']
                    }
                },
                onchange: function () {
                    // Reset validation results when new file is selected
                    dialog.fields_dict.validation_results.$wrapper.html(`
                        <div class="alert alert-info">
                            <i class="fa fa-info-circle"></i> File selected. Click <strong>"Validate Data"</strong> to check for errors.
                        </div>
                    `);

                    // Reset button to Validate
                    reset_dialog_to_validate_mode(dialog);
                }
            },
            {
                fieldtype: 'Section Break',
                fieldname: 'validation_section',
                label: __('Step 3: Validation Results')
            },
            {
                fieldtype: 'HTML',
                fieldname: 'validation_results',
                options: `
                    <div class="alert alert-warning">
                        <i class="fa fa-upload"></i> Please upload an Excel file first, then click <strong>"Validate Data"</strong>.
                    </div>
                `
            }
        ],
        size: 'large',
        primary_action_label: __('🔍 Validate Data'),
        primary_action: function (values) {
            if (!values.excel_file) {
                frappe.msgprint({
                    title: __('File Required'),
                    message: __('Please upload an Excel file first'),
                    indicator: 'orange'
                });
                return;
            }

            validate_excel_file_only(values.excel_file, dialog);
        }
    });

    dialog.show();
}

function reset_dialog_to_validate_mode(dialog) {
    // Reset primary button to validation mode
    dialog.set_primary_action(__('🔍 Validate Data'), function () {
        const values = dialog.get_values();
        if (!values.excel_file) {
            frappe.msgprint({
                title: __('File Required'),
                message: __('Please upload an Excel file first'),
                indicator: 'orange'
            });
            return;
        }
        validate_excel_file_only(values.excel_file, dialog);
    });

    // Reset button styling
    dialog.get_primary_btn().removeClass('btn-success btn-warning').addClass('btn-primary');

    // Enable button
    dialog.get_primary_btn().prop('disabled', false);
}

function validate_excel_file_only(file_url, dialog) {
    // Show loading indicator
    dialog.fields_dict.validation_results.$wrapper.html(`
        <div class="alert alert-info">
            <i class="fa fa-spinner fa-spin"></i> <strong>Validating your Excel file...</strong>
            <br><small>Please wait while we check your data for errors</small>
        </div>
    `);

    // Disable button during validation
    dialog.get_primary_btn().prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Validating...');

    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_issue.validate_excel_file',
        args: {
            file_url: file_url
        },
        callback: function (r) {
            // Re-enable button
            dialog.get_primary_btn().prop('disabled', false);

            if (r.message) {
                display_validation_results(r.message, dialog);

                // If validation successful, convert button to Import mode
                if (r.message.success) {
                    add_import_button_to_dialog(dialog, file_url);
                } else {
                    // Reset to validate mode for retry
                    dialog.get_primary_btn().html('<i class="fa fa-refresh"></i> Re-validate Data');
                    dialog.get_primary_btn().removeClass('btn-success').addClass('btn-warning');
                }
            }
        },
        error: function (err) {
            // Re-enable button
            dialog.get_primary_btn().prop('disabled', false).html('<i class="fa fa-refresh"></i> Re-validate Data');

            dialog.fields_dict.validation_results.$wrapper.html(`
                <div class="alert alert-danger">
                    <h5><i class="fa fa-exclamation-triangle"></i> Validation Error</h5>
                    <p>Error validating file: ${err.message || 'Unknown error'}</p>
                    <small>Please check your file and try again.</small>
                </div>
            `);
        }
    });
}

function add_import_button_to_dialog(dialog, file_url) {
    // Change primary button to Import mode
    dialog.set_primary_action(__('🚀 Import Data'), function () {
        import_excel_data(file_url, dialog);
    });

    // Change button styling to success (green)
    dialog.get_primary_btn().removeClass('btn-primary').addClass('btn-success');

    // Add icon and make it prominent
    dialog.get_primary_btn().html('<i class="fa fa-rocket"></i> Import Data');

    // Add confirmation before import
    dialog.set_primary_action(__('🚀 Import Data'), function () {
        frappe.confirm(
            __('Are you sure you want to import this data? This will create Stock Entry documents.'),
            function () {
                import_excel_data(file_url, dialog);
            }
        );
    });

    // Show success message in dialog
    const success_html = `
        <div class="alert alert-success">
            <h5><i class="fa fa-check-circle"></i> Validation Completed Successfully! ✅</h5>
            <p>Your data is ready for import. Click the <strong>"Import Data"</strong> button above to create Stock Entries.</p>
            <div class="alert alert-info">
                <i class="fa fa-info-circle"></i> <strong>Note:</strong> This will create actual Stock Entry documents in your system.
            </div>
        </div>
    `;

    // Prepend success message to existing validation results
    const current_html = dialog.fields_dict.validation_results.$wrapper.html();
    dialog.fields_dict.validation_results.$wrapper.html(success_html + current_html);
}

function import_excel_data(file_url, dialog) {
    // Show importing status
    dialog.fields_dict.validation_results.$wrapper.html(`
        <div class="alert alert-warning">
            <h5><i class="fa fa-cog fa-spin"></i> Importing Material Issue Data...</h5>
            <p>Creating Stock Entry documents. This may take a few moments.</p>
            <div class="progress">
                <div class="progress-bar progress-bar-striped active" style="width: 100%"></div>
            </div>
        </div>
    `);

    // Disable the import button to prevent double-click
    dialog.get_primary_btn().prop('disabled', true).html('<i class="fa fa-cog fa-spin"></i> Importing...');

    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_issue.import_material_issue_from_excel',
        args: {
            file_url: file_url
        },
        callback: function (import_result) {
            // Re-enable button
            dialog.get_primary_btn().prop('disabled', false);

            if (import_result.message) {
                display_import_results(import_result.message, dialog);

                if (import_result.message.success_count > 0) {
                    // Show success notification
                    frappe.show_alert({
                        message: __('🎉 Successfully created {0} Material Issue Stock Entries!', [import_result.message.success_count]),
                        indicator: 'green'
                    }, 8);

                    // Change button to "Close" since import is complete
                    dialog.set_primary_action(__('✅ Close'), function () {
                        dialog.hide();
                    });
                    dialog.get_primary_btn().removeClass('btn-success').addClass('btn-default');

                    // Auto-close dialog after 5 seconds if fully successful
                    if (import_result.message.error_count === 0) {
                        setTimeout(() => {
                            dialog.hide();

                            // Refresh list view if applicable
                            if (frappe.get_route()[0] === 'List' && frappe.get_route()[1] === 'Stock Entry') {
                                cur_list.refresh();
                            }
                        }, 5000);
                    }
                } else {
                    // No successful imports
                    dialog.get_primary_btn().html('<i class="fa fa-times"></i> Close');
                    dialog.get_primary_btn().removeClass('btn-success').addClass('btn-danger');
                }
            }
        },
        error: function (err) {
            // Re-enable button
            dialog.get_primary_btn().prop('disabled', false);
            dialog.get_primary_btn().html('<i class="fa fa-exclamation-triangle"></i> Import Failed');
            dialog.get_primary_btn().removeClass('btn-success').addClass('btn-danger');

            dialog.fields_dict.validation_results.$wrapper.html(`
                <div class="alert alert-danger">
                    <h5><i class="fa fa-exclamation-triangle"></i> Import Failed</h5>
                    <p>Error importing file: ${err.message || 'Unknown error'}</p>
                    <small>Please check the error details and try again.</small>
                </div>
            `);

            frappe.show_alert({
                message: __('❌ Import failed: {0}', [err.message || 'Unknown error']),
                indicator: 'red'
            }, 10);
        }
    });
}

function download_excel_template() {
    // Show loading message
    frappe.show_alert({
        message: __('Creating Excel template...'),
        indicator: 'blue'
    }, 3);

    // Create and download Excel template
    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_issue_template.create_material_issue_template',
        callback: function (r) {
            if (r.message && r.message.file_url) {
                // Create download link
                let link = document.createElement('a');
                link.href = r.message.file_url;
                link.download = 'material_issue_template.xlsx';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);

                frappe.show_alert({
                    message: __('Excel template downloaded successfully'),
                    indicator: 'green'
                }, 3);
            } else {
                frappe.show_alert({
                    message: __('Error creating template file'),
                    indicator: 'red'
                }, 5);
            }
        },
        error: function (err) {
            frappe.show_alert({
                message: __('Error downloading template: ') + (err.message || 'Unknown error'),
                indicator: 'red'
            }, 5);
        }
    });
}

function display_validation_results(results, dialog) {
    let html = '<div class="validation-results">';

    if (results.success) {
        html += `
            <div class="alert alert-success">
                <h5><i class="fa fa-check-circle"></i> Validation Passed ✅</h5>
                <p><strong>Your Excel file is valid and ready for import!</strong></p>
                <div class="row" style="margin-top: 15px;">
                    <div class="col-md-4 text-center">
                        <h3 class="text-success">${results.total_rows}</h3>
                        <small>Total Rows</small>
                    </div>
                    <div class="col-md-4 text-center">
                        <h3 class="text-success">${results.valid_rows}</h3>
                        <small>Valid Rows</small>
                    </div>
                    <div class="col-md-4 text-center">
                        <h3 class="text-success">${results.groups_count}</h3>
                        <small>No# Found</small>
                    </div>
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="alert alert-danger">
                <h5><i class="fa fa-exclamation-triangle"></i> Validation Failed ❌</h5>
                <p><strong>Please fix the following errors before importing:</strong></p>
                <div class="row" style="margin-top: 10px;">
                    <div class="col-md-3 text-center">
                        <h4 class="text-muted">${results.total_rows}</h4>
                        <small>Total Rows</small>
                    </div>
                    <div class="col-md-3 text-center">
                        <h4 class="text-success">${results.valid_rows}</h4>
                        <small>Valid Rows</small>
                    </div>
                    <div class="col-md-3 text-center">
                        <h4 class="text-danger">${results.total_rows - results.valid_rows}</h4>
                        <small>Error Rows</small>
                    </div>
                    <div class="col-md-3 text-center">
                        <h4 class="text-info">${results.groups_count}</h4>
                        <small>Groups Found</small>
                    </div>
                </div>
            </div>
        `;
    }

    // Show detailed validation info only if there are errors
    if (!results.success && results.validation_details) {
        html += '<div class="validation-details">';

        // Missing items với suggestions
        if (results.validation_details.missing_items && results.validation_details.missing_items.length > 0) {
            html += `
                <div class="alert alert-warning">
                    <h6><i class="fa fa-search"></i> Items not found (${results.validation_details.missing_items.length}):</h6>
                    <div class="missing-items-list">
            `;
            results.validation_details.missing_items.slice(0, 10).forEach(item => {
                html += `
                    <div class="missing-item-row" style="margin-bottom: 10px; padding: 8px; border-left: 3px solid #f39c12; background-color: #fef9e7;">
                        <div><span class="label label-warning">Row ${item.row}</span> <strong>${item.custom_item_name_detail}</strong></div>
                `;

                // Show suggestions if available
                if (item.suggestions && item.suggestions.length > 0) {
                    html += `
                        <div style="margin-top: 5px;">
                            <small class="text-muted">Did you mean:</small>
                            <ul style="margin: 3px 0; padding-left: 20px;">
                    `;
                    item.suggestions.forEach(suggestion => {
                        html += `<li style="font-size: 12px;"><code>${suggestion.custom_item_name_detail}</code> (${suggestion.item_code})</li>`;
                    });
                    html += '</ul>';
                }

                html += '</div>';
            });

            if (results.validation_details.missing_items.length > 10) {
                html += `<div><em>... and ${results.validation_details.missing_items.length - 10} more items not found</em></div>`;
            }
            html += '</div></div>';
        }

        // Missing warehouses
        if (results.validation_details.missing_warehouses && results.validation_details.missing_warehouses.length > 0) {
            html += `
                <div class="alert alert-warning">
                    <h6><i class="fa fa-warehouse"></i> Warehouses not found (${results.validation_details.missing_warehouses.length}):</h6>
                    <ul class="list-unstyled">
            `;
            results.validation_details.missing_warehouses.slice(0, 10).forEach(warehouse => {
                html += `<li><span class="label label-warning">Row ${warehouse.row}</span> ${warehouse.item_code} - ${warehouse.warehouse}</li>`;
            });
            if (results.validation_details.missing_warehouses.length > 10) {
                html += `<li><em>... and ${results.validation_details.missing_warehouses.length - 10} more</em></li>`;
            }
            html += '</ul></div>';
        }

        // Invoice number issues
        if (results.validation_details.invoice_issues && results.validation_details.invoice_issues.length > 0) {
            html += `
                <div class="alert alert-danger">
                    <h6><i class="fa fa-exclamation-circle"></i> Insufficient Stock (${results.validation_details.invoice_issues.length}):</h6>
                    <ul class="list-unstyled">
            `;
            results.validation_details.invoice_issues.slice(0, 10).forEach(issue => {
                html += `
                    <li><span class="label label-danger">Row ${issue.row}</span> 
                    ${issue.item_code} - ${issue.warehouse}<br>
                    <small>Invoice: ${issue.custom_invoice_number} | Available: ${issue.available_qty} | Requested: ${issue.requested_qty}</small></li>
                `;
            });
            if (results.validation_details.invoice_issues.length > 10) {
                html += `<li><em>... and ${results.validation_details.invoice_issues.length - 10} more</em></li>`;
            }
            html += '</ul></div>';
        }

        // General errors
        if (results.validation_details.errors && results.validation_details.errors.length > 0) {
            html += `
                <div class="alert alert-danger">
                    <h6><i class="fa fa-times-circle"></i> General errors (${results.validation_details.errors.length}):</h6>
                    <ul class="list-unstyled">
            `;
            results.validation_details.errors.slice(0, 10).forEach(error => {
                html += `<li><i class="fa fa-times text-danger"></i> ${error}</li>`;
            });
            if (results.validation_details.errors.length > 10) {
                html += `<li><em>... and ${results.validation_details.errors.length - 10} more</em></li>`;
            }
            html += '</ul></div>';
        }

        html += '</div>';
    }

    // Show log file info
    if (results.log_file_path) {
        html += `
            <div class="alert alert-info">
                <small><i class="fa fa-file-text"></i> <strong>Detailed log:</strong> ${results.log_file_path}</small>
            </div>
        `;
    }

    html += '</div>';

    // Update the dialog
    dialog.fields_dict.validation_results.$wrapper.html(html);
}

function display_import_results(results, dialog) {
    let html = '<div class="import-results">';

    if (results.success_count > 0) {
        html += `
            <div class="alert alert-success">
                <h5><i class="fa fa-check-circle"></i> Import Completed Successfully! 🎉</h5>
                <p><strong>Created ${results.success_count} Material Issue Stock Entries</strong></p>
            </div>
        `;

        // Show created entries
        if (results.created_entries && results.created_entries.length > 0) {
            html += `
                <div class="created-entries">
                    <h6><i class="fa fa-list"></i> Created Stock Entries:</h6>
                    <ul class="list-unstyled">
            `;
            results.created_entries.forEach((entry, index) => {
                html += `<li><span class="label label-success">${index + 1}</span> <a href="/app/stock-entry/${entry}" target="_blank">${entry}</a></li>`;
            });
            html += '</ul></div>';
        }
    }

    if (results.error_count > 0) {
        html += `
            <div class="alert alert-warning">
                <h5><i class="fa fa-exclamation-triangle"></i> Some Errors Occurred</h5>
                <p><strong>${results.error_count} groups had errors during import</strong></p>
            </div>
        `;

        if (results.errors && results.errors.length > 0) {
            html += '<div class="error-details"><h6><i class="fa fa-times-circle"></i> Error Details:</h6><ul class="list-unstyled">';
            results.errors.slice(0, 5).forEach((error, index) => {
                html += `<li><span class="label label-danger">${index + 1}</span> ${error}</li>`;
            });
            if (results.errors.length > 5) {
                html += `<li><em>... and ${results.errors.length - 5} more errors</em></li>`;
            }
            html += '</ul></div>';
        }
    }

    // Summary
    html += `
        <div class="summary">
            <h6><i class="fa fa-info-circle"></i> Summary:</h6>
            <div class="row">
                <div class="col-md-3">
                    <div class="text-center">
                        <h4 class="text-primary">${results.total_items}</h4>
                        <small>Total Items</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center">
                        <h4 class="text-success">${results.success_count}</h4>
                        <small>Successful Groups</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center">
                        <h4 class="text-danger">${results.error_count}</h4>
                        <small>Failed Groups</small>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center">
                        <h4 class="text-muted">${results.created_entries ? results.created_entries.length : 0}</h4>
                        <small>Stock Entries</small>
                    </div>
                </div>
            </div>
        </div>
    `;

    if (results.log_file_path) {
        html += `
            <div class="alert alert-info">
                <small><i class="fa fa-file-text"></i> <strong>Detailed log:</strong> ${results.log_file_path}</small>
            </div>
        `;
    }

    // Auto-close message
    if (results.success_count > 0 && results.error_count === 0) {
        html += `
            <div class="alert alert-info">
                <i class="fa fa-clock-o"></i> This dialog will close automatically in 3 seconds...
            </div>
        `;
    }

    html += '</div>';

    dialog.fields_dict.validation_results.$wrapper.html(html);
}

// ============================================
// QUICK ADD FUNCTIONALITY
// ============================================

// HELPER FUNCTION: Parse Vietnamese number format (comma as decimal separator)
function parseVietnameseFloat_se(value) {
    if (!value) return 0;

    // Convert to string and trim
    let str = String(value).trim();

    // Replace Vietnamese comma decimal separator with dot
    str = str.replace(',', '.');

    // Parse the number
    let result = parseFloat(str);

    // Return 0 if not a valid number
    return isNaN(result) ? 0 : result;
}

// ENHANCED FUNCTION: Show Quick Add Dialog with validation
function show_quick_add_dialog_se(frm, dialog_type) {
    let dialog_config = get_dialog_config_se(dialog_type);

    let dialog = new frappe.ui.Dialog({
        title: dialog_config.title,
        fields: [
            {
                fieldname: 'items_data',
                fieldtype: 'Small Text',
                label: __('Items Data'),
                description: dialog_config.description,
                reqd: 1,
                default: ''
            }
        ],
        size: 'extra-large',
        primary_action_label: __('OK'),
        primary_action: function (values) {
            // Validate line count (max 100 lines like stock reconciliation)
            if (!values.items_data) {
                frappe.msgprint({
                    title: __('No Data'),
                    message: __('Please enter items data'),
                    indicator: 'red'
                });
                return;
            }

            let lines = values.items_data.split('\n').filter(line => line.trim());
            if (lines.length > 100) {
                frappe.msgprint({
                    title: __('Too Many Lines'),
                    message: __('Maximum 100 lines allowed per Quick Add operation.<br>Current lines: <strong>{0}</strong><br><br>Please split your data into smaller batches.', [lines.length]),
                    indicator: 'red'
                });
                return;
            }

            if (lines.length === 0) {
                frappe.msgprint({
                    title: __('No Valid Lines'),
                    message: __('Please enter at least one valid line of data'),
                    indicator: 'red'
                });
                return;
            }

            process_quick_add_items_se(frm, values.items_data, dialog_type);
            dialog.hide();
        }
    });

    // Set dialog width and height for full screen visibility
    dialog.$wrapper.find('.modal-dialog').css({
        'width': '95%',
        'max-width': '1200px',
        'height': '90vh'
    });
    dialog.$wrapper.find('.modal-content').css('height', '100%');
    dialog.$wrapper.find('.modal-body').css({
        'height': 'calc(100% - 120px)',
        'overflow-y': 'auto'
    });
    dialog.$wrapper.find('[data-fieldname="items_data"]').css('min-height', '250px');

    dialog.show();
}

// ENHANCED FUNCTION: Get dialog configuration with max 100 lines note
function get_dialog_config_se(dialog_type) {
    let dialog_description = `
    <div style="background: #f8f9fa; padding: 15px; border-radius: 12px; font-size: 13px; line-height: 1.4;">
                    
                    <div style="display: flex; gap: 20px;">
                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 10px 0; color: #333;">📝 Format Options</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
                                <strong>1. Full format:</strong> <code>item_name_detail; invoice_number; qty</code><br>
                                <strong>2. With Invoice:</strong> <code>item_name_detail; invoice_number</code><br>
                                <strong>3. Skip Invoice:</strong> <code>item_name_detail; ; qty</code><br>
                                <strong>4. Simple:</strong> <code>item_name_detail</code><br>
                            </div>
                            
                            <h4 style="margin: 0 0 10px 0; color: #333;">⚙️ Default Values</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px;">
                                <strong>invoice_number:</strong> empty<br>
                                <strong>qty:</strong> 1<br>
                                <strong>Number format:</strong> 52,5 or 52.5
                            </div>
                        </div>

                        <div style="flex: 1;">
                            <h4 style="margin: 0 0 10px 0; color: #333;">📋 Examples</h4>
                            <div style="background: white; padding: 10px; border-radius: 4px; font-family: monospace; font-size: 12px;">
                                <div style="margin-bottom: 12px;"><code>E79799 Black 20Mm Vital 25Ss; IV001; 25,75</code><br><small style="color: #28a745;">→ qty=25.75, Invoice=IV001</small></div>
                                <div style="margin-bottom: 12px;"><code>E79799 Black 20Mm Vital 25Ss; IV002</code><br><small style="color: #28a745;">→ qty=1, Invoice=IV002</small></div>
                                <div style="margin-bottom: 12px;"><code>E79799 Black 20Mm Vital 25Ss; ; 30</code><br><small style="color: #28a745;">→ qty=30, Invoice=empty</small></div>
                                <div style="margin-bottom: 12px;"><code>E79799 Black 20Mm Vital 25Ss</code><br><small style="color: #28a745;">→ qty=1, Invoice=empty</small></div>
                                                                
                            </div>
                            
                            <h4 style="margin: 15px 0 10px 0; color: #333;">ℹ️ Notes</h4>
                            <div style="background: #fff3cd; padding: 10px; border-radius: 4px; border-left: 4px solid #ffc107;">
                                <small>
                                • <strong>Maximum 100 lines per batch</strong><br>
                                • Each line = one item<br>
                                • System searches "Item Name Detail" field<br>
                                • Invalid items will be skipped with error report
                                </small>
                            </div>
                        </div>
                    </div>
                </div>
    `;
    if (dialog_type === 'material_issue') {
        return {
            title: __('Quick Add Items - Material Issue (Max 100 lines)'),
            description: __(dialog_description)
        };
    } else if (dialog_type === 'material_receipt') {
        return {
            title: __('Quick Add Items - Material Receipt (Max 100 lines)'),
            description: __(dialog_description)
        };
    }
}

// OPTIMIZED FUNCTION: Process Quick Add Items with Progress Dialog and Batch Processing
async function process_quick_add_items_se(frm, items_data, dialog_type) {
    if (!items_data) return;

    // Create progress dialog with enhanced UI (from stock_reconciliation.js)
    let progress_dialog = new frappe.ui.Dialog({
        title: __('Processing Quick Add Items'),
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'progress_content'
            }
        ],
        size: 'small',
        static: true  // Prevent closing by clicking outside
    });

    // Show dialog first
    progress_dialog.show();

    // Set HTML content after dialog is shown
    setTimeout(() => {
        let progress_wrapper = progress_dialog.fields_dict.progress_content.$wrapper;
        progress_wrapper.html(`
            <div style="text-align: center; padding: 30px 20px;">
                <div style="width: 100%; background-color: #e9ecef; border-radius: 10px; margin: 20px 0; height: 25px; overflow: hidden;">
                    <div id="progress_bar_se" style="width: 0%; height: 100%; background: linear-gradient(90deg, #17a2b8, #20c997); transition: width 0.5s ease; border-radius: 10px;"></div>
                </div>
                <div id="progress_text_se" style="font-size: 16px; font-weight: 500; color: #495057; margin: 15px 0;">
                    Initializing...
                </div>
                <div id="progress_details_se" style="font-size: 13px; color: #6c757d; margin-top: 10px;">
                    Please wait while we process your items
                </div>
                <div id="progress_percentage_se" style="font-size: 24px; font-weight: bold; color: #17a2b8; margin-top: 15px;">
                    0%
                </div>
            </div>
        `);
    }, 100);

    // Helper function to update progress
    function updateProgress(percentage, text, details = '') {
        try {
            let progress_bar = progress_dialog.$wrapper.find('#progress_bar_se');
            let progress_text = progress_dialog.$wrapper.find('#progress_text_se');
            let progress_details = progress_dialog.$wrapper.find('#progress_details_se');
            let progress_percentage = progress_dialog.$wrapper.find('#progress_percentage_se');

            if (progress_bar.length) {
                progress_bar.css('width', percentage + '%');
            }
            if (progress_text.length) {
                progress_text.text(text);
            }
            if (progress_details.length && details) {
                progress_details.text(details);
            }
            if (progress_percentage.length) {
                progress_percentage.text(Math.round(percentage) + '%');
            }
        } catch (error) {
            console.log('Progress update error:', error);
        }
    }

    let lines = items_data.split('\n');
    let success_count = 0;
    let error_count = 0;
    let errors = [];
    let items_to_add = [];

    updateProgress(10, 'Validating input data...', `Processing ${lines.length} lines`);
    await new Promise(resolve => setTimeout(resolve, 200));

    // First pass: validate and prepare data based on dialog type
    for (let i = 0; i < lines.length; i++) {
        let line = lines[i].trim();
        if (!line) continue; // Skip empty lines

        let parts = line.split(';');
        let item_name_detail = parts[0].trim();
        let qty = 1; // Default quantity
        let field_data = {};

        // Check if we have at least the item pattern
        if (!item_name_detail) {
            errors.push(__('Line {0}: Item pattern is required', [i + 1]));
            error_count++;
            continue;
        }

        // Process invoice_number (parts[1])
        if (parts.length >= 2 && parts[1].trim() !== '') {
            field_data.custom_invoice_number = parts[1].trim();
        } else {
            field_data.custom_invoice_number = '';
        }

        // Process quantity (parts[2])
        if (parts.length >= 3 && parts[2].trim() !== '') {
            qty = parseVietnameseFloat_se(parts[2].trim());
            if (isNaN(qty) || qty <= 0) {
                errors.push(__('Line {0}: Invalid quantity: {1}', [i + 1, parts[2]]));
                error_count++;
                continue;
            }
        }
        item_name_detail += '%'; // Ensure pattern ends with %
        items_to_add.push({
            line_number: i + 1,
            search_pattern: item_name_detail,
            field_data: field_data,
            qty: qty
        });

        // Update progress during validation
        if (i % 5 === 0 || i === lines.length - 1) {
            let progress = 10 + (i / lines.length) * 20;
            updateProgress(progress, 'Validating input data...', `Processed ${i + 1}/${lines.length} lines`);
            await new Promise(resolve => setTimeout(resolve, 50));
        }
    }

    // Second pass: Find all items in batch (optimized from stock_reconciliation.js)
    updateProgress(30, 'Searching for items in database...', `Searching ${items_to_add.length} patterns`);
    await new Promise(resolve => setTimeout(resolve, 200));
    let found_items = [];
    let search_patterns = items_to_add.map(item => item.search_pattern);

    try {
        // Find all items using batch call
        let batch_responses = await Promise.all(
            search_patterns.map(pattern =>
                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Item',
                        filters: {
                            'custom_item_name_detail': ['like', pattern],
                            'variant_of': ['!=', '']  // Chỉ lấy item variants (có parent template)
                        },
                        fields: ['name', 'item_code', 'item_name', 'stock_uom'],
                        order_by: 'LENGTH(custom_item_name_detail) ASC',
                        limit: 1
                    }
                })
            )
        );

        updateProgress(50, 'Processing search results...', `Found items for ${batch_responses.length} patterns`);
        await new Promise(resolve => setTimeout(resolve, 200));

        // Process batch responses and map to original items
        for (let i = 0; i < batch_responses.length; i++) {
            let response = batch_responses[i];
            let original_item = items_to_add[i];

            if (response.message && response.message.length > 0) {
                let item = response.message[0];
                found_items.push({
                    ...original_item,
                    item_code: item.item_code,
                    item_name: item.item_name,
                    stock_uom: item.stock_uom,
                    found: true
                });
            } else {
                errors.push(__('Line {0}: Item not found with pattern: {1}', [original_item.line_number, original_item.search_pattern]));
                error_count++;
            }
        }


        // Third pass: Add all rows to table using optimized method
        updateProgress(70, 'Adding items to table...', `Adding ${found_items.length} items`);
        await new Promise(resolve => setTimeout(resolve, 200));
        let added_rows = [];

        for (let i = 0; i < found_items.length; i++) {
            let item = found_items[i];
            try {
                console.log(`Processing item: ${i + 1} ${item.item_code} for pattern: ${item.search_pattern}, qty: ${item.qty}`);

                // Add new row using optimized pattern from stock_reconciliation.js
                let new_row = frm.add_child('items');

                // Set item_code first to trigger auto-population of UOM fields
                await frappe.model.set_value(new_row.doctype, new_row.name, 'item_code', item.item_code);

                // Wait for item_code to be fully processed and UOM fields populated
                await new Promise(resolve => setTimeout(resolve, 200));

                // Set quantity and other fields directly on row object (more reliable)
                new_row.qty = item.qty;

                // Set additional fields
                for (let field of Object.keys(item.field_data)) {
                    new_row[field] = item.field_data[field];
                }

                // Store row info for backup qty setting
                added_rows.push({
                    doctype: new_row.doctype,
                    name: new_row.name,
                    qty: item.qty
                });

                success_count++;
                // Update progress for every 3 items or last item
                if (i % 3 === 0 || i === found_items.length - 1) {
                    let progress = 70 + ((i + 1) / found_items.length) * 15;
                    updateProgress(progress, 'Adding items to table...', `Added ${i + 1}/${found_items.length} items`);
                    await new Promise(resolve => setTimeout(resolve, 100));
                }

            } catch (error) {
                errors.push(__('Line {0}: Error adding item to table: {1}', [item.line_number, error.message]));
                error_count++;
            }
        }

        // Refresh grid after adding all rows
        if (added_rows.length > 0) {
            updateProgress(85, 'Refreshing table display...', 'Updating user interface');
            await new Promise(resolve => setTimeout(resolve, 200));

            frm.refresh_field('items');
            // Wait for refresh to complete, then verify and fix qty if needed
            await new Promise(resolve => setTimeout(resolve, 500));

            updateProgress(90, 'Verifying quantities...', 'Ensuring all quantities are correct');
            await new Promise(resolve => setTimeout(resolve, 200));
            for (let row_info of added_rows) {
                try {
                    let row = locals[row_info.doctype][row_info.name];
                    if (row && (!row.qty || row.qty === 0 || row.qty != row_info.qty)) {
                        await frappe.model.set_value(row_info.doctype, row_info.name, 'qty', row_info.qty);
                    }
                } catch (error) {
                    console.error(`Error verifying qty for row ${row_info.name}:`, error);
                }
            }

            // Final refresh to ensure all changes are visible
            frm.refresh_field('items');
        }

        updateProgress(100, 'Completed!', `Successfully added ${success_count} items`);
        await new Promise(resolve => setTimeout(resolve, 800));

    } catch (error) {
        console.error('Error in batch processing:', error);
        errors.push(__('Error in batch processing: {0}', [error.message]));
        error_count++;
        updateProgress(100, 'Error occurred', 'Processing failed');
        await new Promise(resolve => setTimeout(resolve, 1000));
    }

    // Close progress dialog
    progress_dialog.hide();

    // Show results
    let type_label = dialog_type === 'material_issue' ? 'Material Issue' : 'Material Receipt';
    let message = __('Quick Add {0} completed: {1} items added successfully', [type_label, success_count]);

    if (error_count > 0) {
        message += __('<br><br>Errors ({0}):<br>', [error_count]);
        message += errors.join('<br>');

        frappe.msgprint({
            title: __('Quick Add Results'),
            message: message,
            indicator: 'orange'
        });
    } else if (success_count > 0) {
        frappe.show_alert({
            message: message,
            indicator: 'green'
        }, 5);
    }
}

// ENHANCED FUNCTION: Monitor selection changes
function setup_selection_monitor_se(frm) {
    // Monitor click events on grid
    frm.fields_dict.items.grid.wrapper.on('click', '.grid-row-check', function () {
        setTimeout(() => {
            update_duplicate_button_style_se(frm);
        }, 50); // Small delay to ensure selection has been updated
    });

    // Monitor click on row (can select/deselect)
    frm.fields_dict.items.grid.wrapper.on('click', '.grid-row', function () {
        setTimeout(() => {
            update_duplicate_button_style_se(frm);
        }, 50);
    });

    // Monitor select all checkbox
    frm.fields_dict.items.grid.wrapper.on('click', '.grid-header-row .grid-row-check', function () {
        setTimeout(() => {
            update_duplicate_button_style_se(frm);
        }, 50);
    });

    // Monitor keyboard events (Ctrl+A, arrow keys, etc.)
    frm.fields_dict.items.grid.wrapper.on('keyup', function () {
        setTimeout(() => {
            update_duplicate_button_style_se(frm);
        }, 50);
    });
}

// NEW FUNCTION: Initialize Form-level Quick Add buttons (much simpler & stable)
function initialize_form_buttons_se(frm) {
    try {
        // Remove existing custom buttons to prevent duplicates
        frm.custom_buttons = frm.custom_buttons || {};

        // Remove existing Quick Add buttons
        if (frm.custom_buttons['Material Issue - Quick Add']) {
            frm.remove_custom_button('Material Issue - Quick Add');
        }
        if (frm.custom_buttons['Material Receipt - Quick Add']) {
            frm.remove_custom_button('Material Receipt - Quick Add');
        }

        // Get current state
        let is_submitted = frm.doc.docstatus === 1;
        let is_material_issue = frm.doc.stock_entry_type === "Material Issue";
        let is_material_receipt = frm.doc.stock_entry_type === "Material Receipt";

        // Add Material Issue button
        if (is_material_issue && !is_submitted) {
            // Enabled state
            frm.add_custom_button(__('Material Issue - Quick Add'), function () {
                handle_quick_add_click_se(frm, 'material_issue');
            }).addClass('btn btn-success').css({
                'background-color': '#5cb85c',
                'border-color': '#4cae4c',
                'color': '#fff'
            });
        } else if (is_material_issue && is_submitted) {
            // Disabled state for submitted
            frm.add_custom_button(__('Material Issue - Quick Add'), function () {
                throw_error_se('Cannot add items to submitted document');
            }).addClass('btn btn-secondary').css({
                'background-color': '#6c757d',
                'border-color': '#6c757d',
                'color': '#fff',
                'cursor': 'not-allowed',
                'opacity': '0.6'
            });
        } else {
            // Show for wrong type but disabled
            frm.add_custom_button(__('Material Issue - Quick Add'), function () {
                throw_error_se('This function is only available for Material Issue entries');
            }).addClass('btn btn-secondary').css({
                'background-color': '#6c757d',
                'border-color': '#6c757d',
                'color': '#fff',
                'cursor': 'not-allowed',
                'opacity': '0.6'
            });
        }

        // Add Material Receipt button
        if (is_material_receipt && !is_submitted) {
            // Enabled state
            frm.add_custom_button(__('Material Receipt - Quick Add'), function () {
                handle_quick_add_click_se(frm, 'material_receipt');
            }).addClass('btn btn-warning').css({
                'background-color': '#f0ad4e',
                'border-color': '#eea236',
                'color': '#fff'
            });
        } else if (is_material_receipt && is_submitted) {
            // Disabled state for submitted
            frm.add_custom_button(__('Material Receipt - Quick Add'), function () {
                throw_error_se('Cannot add items to submitted document');
            }).addClass('btn btn-secondary').css({
                'background-color': '#6c757d',
                'border-color': '#6c757d',
                'color': '#fff',
                'cursor': 'not-allowed',
                'opacity': '0.6'
            });
        } else {
            // Show for wrong type but disabled
            frm.add_custom_button(__('Material Receipt - Quick Add'), function () {
                throw_error_se('This function is only available for Material Receipt entries');
            }).addClass('btn btn-secondary').css({
                'background-color': '#6c757d',
                'border-color': '#6c757d',
                'color': '#fff',
                'cursor': 'not-allowed',
                'opacity': '0.6'
            });
        }
    } catch (error) {
        console.error('Error initializing form buttons:', error);
        throw_error_se('Failed to initialize Quick Add buttons: ' + error.message);
    }
}

// NEW FUNCTION: Handle Quick Add button clicks with error handling
function handle_quick_add_click_se(frm, dialog_type) {
    try {
        // Validate document state
        if (frm.doc.docstatus === 1) {
            throw new Error('Cannot add items to a submitted document');
        }

        // Validate stock entry type
        if (dialog_type === 'material_issue' && frm.doc.stock_entry_type !== "Material Issue") {
            throw new Error('This function is only available for Material Issue entries');
        }

        if (dialog_type === 'material_receipt' && frm.doc.stock_entry_type !== "Material Receipt") {
            throw new Error('This function is only available for Material Receipt entries');
        }

        // Validate grid existence
        if (!frm.fields_dict || !frm.fields_dict.items || !frm.fields_dict.items.grid) {
            throw new Error('Items table is not ready. Please wait and try again.');
        }

        // All validations passed - show dialog
        show_quick_add_dialog_se(frm, dialog_type);

    } catch (error) {
        throw_error_se(error.message);
    }
}

// NEW FUNCTION: Standardized error throwing
function throw_error_se(message) {
    frappe.msgprint({
        title: __('Quick Add Error'),
        message: __(message),
        indicator: 'red'
    });
    console.error('Quick Add Error:', message);
}

// NEW FUNCTION: Update Duplicate button style (simplified - no text change)
function update_duplicate_button_style_se(frm) {
    try {
        if (!frm.duplicate_btn) {
            return;
        }

        let selected_rows = frm.fields_dict.items.grid.get_selected();
        let is_submitted = frm.doc.docstatus === 1;
        let has_selection = selected_rows.length > 0;

        // Always show button, but style it based on state
        if (is_submitted || !has_selection) {
            // Disabled state - gray color only
            frm.duplicate_btn.removeClass('btn-primary').addClass('btn-secondary').css({
                'background-color': '#6c757d',
                'border-color': '#6c757d',
                'color': '#fff',
                'cursor': 'not-allowed',
                'opacity': '0.6',
                'pointer-events': 'none'
            });
        } else {
            // Enabled state
            frm.duplicate_btn.removeClass('btn-secondary').addClass('btn-primary').css({
                'background-color': '#6495ED',
                'border-color': '#6495ED',
                'color': '#fff',
                'cursor': 'pointer',
                'opacity': '1',
                'pointer-events': 'auto'
            });
        }
    } catch (error) {
        console.error('Error updating Duplicate button style:', error);
    }
}

// Debug console logging
console.log('🚀 Stock Entry Quick Import JS loaded successfully!');