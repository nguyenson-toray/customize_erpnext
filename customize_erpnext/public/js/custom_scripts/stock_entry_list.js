frappe.listview_settings['Stock Entry'] = {
    onload: function (listview) {
        // Add "Import Stock Entry - Material Issue" button to Stock Entry List
        listview.page.add_inner_button(__('Import Stock Entry - Material Issue'), function () {
            show_material_issue_dialog(listview);
        }, __('Actions'));
    }
};

function show_material_issue_dialog(listview) {
    let dialog = new frappe.ui.Dialog({
        title: __('Import Material Issue Stock Entry'),
        fields: [
            {
                fieldtype: 'Section Break',
                label: __('Import Process')
            },
            {
                fieldname: 'step_info',
                fieldtype: 'HTML',
                label: __('Steps'),
                options: `
                    <div class="alert alert-info">
                        <h5>Import Process:</h5>
                        <ol>
                            <li>Download Excel template</li>
                            <li>Fill in your data</li>
                            <li>Upload and validate file</li>
                            <li>Import stock entries</li>
                        </ol>
                    </div>
                `
            },
            {
                fieldtype: 'Section Break',
                label: __('Step 1: Download Template')
            },
            {
                fieldname: 'template_info',
                fieldtype: 'HTML',
                label: __('Template'),
                options: `
                    <p>Download the Excel template with sample data and instructions.</p>
                    <button class="btn btn-primary btn-sm" id="download-template-btn">
                        <i class="fa fa-download"></i> Download Template
                    </button>
                `
            },
            {
                fieldtype: 'Section Break',
                label: __('Step 2: Upload File')
            },
            {
                fieldname: 'excel_file',
                fieldtype: 'Attach',
                label: __('Excel File'),
                reqd: 1,
                options: {
                    restrictions: {
                        allowed_file_types: ['.xlsx', '.xls']
                    }
                }
            },
            {
                fieldtype: 'Section Break',
                label: __('Step 3: Validation Results')
            },
            {
                fieldname: 'validation_results',
                fieldtype: 'HTML',
                label: __('Validation'),
                options: '<div class="text-muted">Upload a file to see validation results</div>'
            },
            {
                fieldtype: 'Section Break',
                label: __('Step 4: Import')
            },
            {
                fieldname: 'import_results',
                fieldtype: 'HTML',
                label: __('Import Results'),
                options: '<div class="text-muted">Complete validation to proceed with import</div>'
            }
        ],
        size: 'extra-large',
        primary_action_label: __('Import Stock Entries'),
        primary_action: function(values) {
            import_material_issue_entries(values, dialog);
        },
        secondary_action_label: __('Validate File'),
        secondary_action: function(values) {
            validate_excel_file(values, dialog);
        }
    });

    dialog.show();
    
    // Add event handlers after dialog is shown
    setTimeout(() => {
        setup_material_issue_dialog_handlers(dialog);
    }, 100);
}

function setup_material_issue_dialog_handlers(dialog) {
    // Download template button handler
    $(dialog.$wrapper).find('#download-template-btn').off('click').on('click', function() {
        download_material_issue_template(dialog);
    });
    
    // File upload handler
    dialog.get_field('excel_file').$input.off('change').on('change', function() {
        const file_url = dialog.get_value('excel_file');
        if (file_url) {
            // Auto-validate when file is uploaded
            validate_excel_file({excel_file: file_url}, dialog);
        }
    });
}

function download_material_issue_template(dialog) {
    frappe.show_alert({
        message: __('Generating template...'),
        indicator: 'blue'
    });
    
    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_issue_template.create_material_issue_template',
        callback: function(r) {
            if (r.message && r.message.file_url) {
                // Create download link
                const link = document.createElement('a');
                link.href = r.message.file_url;
                link.download = 'import_material_issue_template.xlsx';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
                
                frappe.show_alert({
                    message: __('Template downloaded successfully!'),
                    indicator: 'green'
                });
            } else {
                frappe.msgprint(__('Error generating template'));
            }
        },
        error: function(r) {
            frappe.msgprint(__('Error downloading template: {0}', [r.message || 'Unknown error']));
        }
    });
}

function validate_excel_file(values, dialog) {
    if (!values.excel_file) {
        frappe.msgprint(__('Please select an Excel file first'));
        return;
    }
    
    // Show loading state
    dialog.set_value('validation_results', '<div class="text-center"><i class="fa fa-spinner fa-spin"></i> Validating file...</div>');
    
    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_issue.validate_excel_file',
        args: {
            file_url: values.excel_file
        },
        callback: function(r) {
            if (r.message) {
                display_validation_results(r.message, dialog);
            } else {
                dialog.set_value('validation_results', '<div class="alert alert-danger">Validation failed</div>');
            }
        },
        error: function(r) {
            dialog.set_value('validation_results', `<div class="alert alert-danger">Error: ${r.message || 'Unknown error'}</div>`);
        }
    });
}

function display_validation_results(validation_result, dialog) {
    let html = '';
    
    if (validation_result.success) {
        html = `
            <div class="alert alert-success">
                <h5><i class="fa fa-check"></i> Validation Successful!</h5>
                <ul>
                    <li>Total rows: ${validation_result.total_rows}</li>
                    <li>Valid rows: ${validation_result.valid_rows}</li>
                    <li>Groups (Stock Entries): ${validation_result.groups_count}</li>
                </ul>
            </div>
        `;
        
        // Enable import button
        dialog.set_primary_action(__('Import Stock Entries'), function() {
            import_material_issue_entries(dialog.get_values(), dialog);
        });
    } else {
        html = '<div class="alert alert-danger"><h5><i class="fa fa-times"></i> Validation Failed</h5>';
        
        const details = validation_result.validation_details || {};
        
        // Missing items
        if (details.missing_items && details.missing_items.length > 0) {
            html += '<h6>Missing Items:</h6><ul>';
            details.missing_items.forEach(item => {
                html += `<li>Row ${item.row}: "${item.custom_item_name_detail}"`;
                if (item.suggestions && item.suggestions.length > 0) {
                    html += '<br><small class="text-muted">Suggestions: ';
                    item.suggestions.forEach((suggestion, idx) => {
                        html += `${idx > 0 ? ', ' : ''}"${suggestion.custom_item_name_detail}"`;
                    });
                    html += '</small>';
                }
                html += '</li>';
            });
            html += '</ul>';
        }
        
        // Missing warehouses
        if (details.missing_warehouses && details.missing_warehouses.length > 0) {
            html += '<h6>Missing Warehouses:</h6><ul>';
            details.missing_warehouses.forEach(warehouse => {
                html += `<li>Row ${warehouse.row}: ${warehouse.item_code} - ${warehouse.warehouse}</li>`;
            });
            html += '</ul>';
        }
        
        // Invoice issues
        if (details.invoice_issues && details.invoice_issues.length > 0) {
            html += '<h6>Stock/Invoice Issues:</h6><ul>';
            details.invoice_issues.forEach(issue => {
                html += `<li>Row ${issue.row}: ${issue.item_code} - Available: ${issue.available_qty}, Requested: ${issue.requested_qty}</li>`;
            });
            html += '</ul>';
        }
        
        // General errors
        if (details.errors && details.errors.length > 0) {
            html += '<h6>Other Errors:</h6><ul>';
            details.errors.forEach(error => {
                html += `<li>${error}</li>`;
            });
            html += '</ul>';
        }
        
        html += '</div>';
        
        // Disable import button
        dialog.set_primary_action(__('Import Stock Entries (Fix errors first)'), null);
    }
    
    dialog.set_value('validation_results', html);
}

function import_material_issue_entries(values, dialog) {
    if (!values.excel_file) {
        frappe.msgprint(__('Please select and validate an Excel file first'));
        return;
    }
    
    // Show loading state
    dialog.set_value('import_results', '<div class="text-center"><i class="fa fa-spinner fa-spin"></i> Importing stock entries...</div>');
    
    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_issue.import_material_issue_from_excel',
        args: {
            file_url: values.excel_file
        },
        callback: function(r) {
            if (r.message) {
                display_import_results(r.message, dialog);
            } else {
                dialog.set_value('import_results', '<div class="alert alert-danger">Import failed</div>');
            }
        },
        error: function(r) {
            dialog.set_value('import_results', `<div class="alert alert-danger">Error: ${r.message || 'Unknown error'}</div>`);
        }
    });
}

function display_import_results(import_result, dialog) {
    let html = '';
    
    if (import_result.success_count > 0) {
        html += `
            <div class="alert alert-success">
                <h5><i class="fa fa-check"></i> Import Completed!</h5>
                <ul>
                    <li>Successfully created: ${import_result.success_count} Stock Entries</li>
                    <li>Total items processed: ${import_result.total_items}</li>
                    <li>Errors: ${import_result.error_count}</li>
                </ul>
            </div>
        `;
        
        // Show created entries
        if (import_result.created_entries && import_result.created_entries.length > 0) {
            html += '<h6>Created Stock Entries:</h6><ul>';
            import_result.created_entries.forEach(entry_name => {
                html += `<li><a href="/app/stock-entry/${entry_name}" target="_blank">${entry_name}</a></li>`;
            });
            html += '</ul>';
        }
    } else {
        html += '<div class="alert alert-danger"><h5><i class="fa fa-times"></i> Import Failed</h5>';
    }
    
    // Show errors if any
    if (import_result.errors && import_result.errors.length > 0) {
        html += '<h6>Errors:</h6><ul>';
        import_result.errors.forEach(error => {
            html += `<li>${error}</li>`;
        });
        html += '</ul>';
    }
    
    if (import_result.success_count === 0) {
        html += '</div>';
    }
    
    dialog.set_value('import_results', html);
    
    // Refresh the listview if import was successful
    if (import_result.success_count > 0) {
        setTimeout(() => {
            cur_list.refresh();
        }, 1000);
    }
}