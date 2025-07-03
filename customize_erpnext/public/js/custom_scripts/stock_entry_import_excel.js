// stock_entry_import_excel.js
// Custom button and dialog for importing Material Issue from Excel

frappe.ui.form.on('Stock Entry', {
    refresh: function (frm) {
        add_import_button_if_needed(frm);
    },

    purpose: function (frm) {
        add_import_button_if_needed(frm);
    },

    onload: function (frm) {
        add_import_button_if_needed(frm);
    }
});

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

function validate_excel_only(file_url, dialog) {
    // Show loading indicator in dialog
    update_dialog_status(dialog, 'Validating Excel file...', 'blue');

    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_issue.validate_excel_file',
        args: {
            file_url: file_url
        },
        callback: function (r) {
            if (r.message) {
                display_validation_results(r.message, dialog);
            }
        },
        error: function (err) {
            update_dialog_status(dialog, 'Error validating file: ' + (err.message || 'Unknown error'), 'red');
        }
    });
}

function validate_and_import_excel(file_url, dialog) {
    // First validate
    update_dialog_status(dialog, 'Validating Excel file...', 'blue');

    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_issue.validate_excel_file',
        args: {
            file_url: file_url
        },
        callback: function (r) {
            if (r.message && r.message.success) {
                // If validation passed, proceed with import
                update_dialog_status(dialog, 'Importing Material Issue entries...', 'orange');

                frappe.call({
                    method: 'customize_erpnext.api.bulk_update_scripts.create_material_issue.import_material_issue_from_excel',
                    args: {
                        file_url: file_url
                    },
                    callback: function (import_result) {
                        if (import_result.message) {
                            display_import_results(import_result.message, dialog);

                            if (import_result.message.success_count > 0) {
                                // Show success message
                                frappe.show_alert({
                                    message: __('Successfully created {0} Material Issue entries', [import_result.message.success_count]),
                                    indicator: 'green'
                                }, 5);

                                // Optionally refresh the list view
                                if (frappe.get_route()[0] === 'List' && frappe.get_route()[1] === 'Stock Entry') {
                                    setTimeout(() => cur_list.refresh(), 1000);
                                }
                            }
                        }
                    },
                    error: function (err) {
                        update_dialog_status(dialog, 'Error importing file: ' + (err.message || 'Unknown error'), 'red');
                    }
                });
            } else {
                // Show validation errors
                display_validation_results(r.message, dialog);
            }
        },
        error: function (err) {
            update_dialog_status(dialog, 'Error validating file: ' + (err.message || 'Unknown error'), 'red');
        }
    });
}

function update_dialog_status(dialog, message, color) {
    // Update dialog with status message
    const status_html = `
        <div class="alert alert-info" style="border-left: 4px solid ${color};">
            <i class="fa fa-spinner fa-spin"></i> ${message}
        </div>
    `;

    dialog.fields_dict.validation_results.$wrapper.html(status_html);
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

// Debug console logging
console.log('🚀 Stock Entry Import Excel JS loaded successfully!');