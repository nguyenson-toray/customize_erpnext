frappe.listview_settings['Stock Entry'] = {
    onload: function (listview) {
        // Add "Import Stock Entry - Material Issue" button to Stock Entry List
        listview.page.add_inner_button(__('Import Stock Entry - Material Issue'), function () {
            show_material_issue_dialog(listview);
        }, __('Actions'));
        
        // Add "Import Stock Entry - Material Receipt" button to Stock Entry List
        listview.page.add_inner_button(__('Import Stock Entry - Material Receipt'), function () {
            show_material_receipt_dialog(listview);
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
                            <li>Upload and validate file. If any information is incorrect, you must edit the file and upload it again.</li>
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
        primary_action: function (values) {
            import_material_issue_entries(values, dialog);
        },
        secondary_action_label: __('Validate File'),
        secondary_action: function (values) {
            validate_excel_file(values, dialog);
        }
    });

    dialog.show();

    // Disable import button initially
    dialog.set_primary_action(__('Import Stock Entries (Validate file first)'), null);

    // Performance optimization: Add event handlers immediately
    setup_material_issue_dialog_handlers(dialog);
}

// Performance optimization: Add debouncing and caching
let validation_cache = new Map();
let validation_timeout = null;
let validation_passed = false;

function open_all_draft_entries() {
    // Open all draft Stock Entries using direct URL
    window.open('/app/stock-entry?docstatus=0', '_blank');
}

function setup_material_issue_dialog_handlers(dialog) {
    // Download template button handler
    $(dialog.$wrapper).find('#download-template-btn').off('click').on('click', function () {
        download_material_issue_template(dialog);
    });

    // File upload handler with debouncing
    dialog.get_field('excel_file').$input.off('change').on('change', function () {
        const file_url = dialog.get_value('excel_file');
        if (file_url) {
            // Reset validation state
            validation_passed = false;
            dialog.set_primary_action(__('Import Stock Entries (Validate file first)'), null);

            // Clear existing timeout
            if (validation_timeout) {
                clearTimeout(validation_timeout);
            }

            // Check cache first
            if (validation_cache.has(file_url)) {
                const cached_result = validation_cache.get(file_url);
                display_validation_results(cached_result, dialog);
                return;
            }

            // Debounce validation for 500ms
            validation_timeout = setTimeout(() => {
                validate_excel_file({ excel_file: file_url }, dialog);
            }, 500);
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
        callback: function (r) {
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
        error: function (r) {
            frappe.msgprint(__('Error downloading template: {0}', [r.message || 'Unknown error']));
        }
    });
}

function validate_excel_file(values, dialog) {
    // Get file URL from dialog or values
    const file_url = values.excel_file || dialog.get_value('excel_file');

    if (!file_url) {
        frappe.msgprint(__('Please select an Excel file first'));
        return;
    }

    // Performance optimization: Show progressive loading
    const progress_html = `
        <div class="validation-progress">
            <div class="progress">
                <div class="progress-bar progress-bar-striped progress-bar-animated" 
                     style="width: 0%" id="validation-progress-bar"></div>
            </div>
            <div class="text-center mt-2">
                <i class="fa fa-spinner fa-spin"></i> 
                <span id="validation-status">Starting validation...</span>
            </div>
        </div>
    `;
    dialog.set_value('validation_results', progress_html);

    // Simulate progress updates
    let progress = 0;
    const progress_interval = setInterval(() => {
        progress += Math.random() * 20;
        if (progress > 90) progress = 90;
        $('#validation-progress-bar').css('width', progress + '%');

        if (progress > 30 && progress < 60) {
            $('#validation-status').text('Checking file format...');
        } else if (progress >= 60) {
            $('#validation-status').text('Validating data...');
        }
    }, 200);

    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_issue.validate_excel_file',
        args: {
            file_url: file_url
        },
        callback: function (r) {
            clearInterval(progress_interval);
            if (r.message) {
                // Cache the result for future use
                validation_cache.set(file_url, r.message);
                display_validation_results(r.message, dialog);
            } else {
                dialog.set_value('validation_results', '<div class="alert alert-danger">Validation failed</div>');
            }
        },
        error: function (r) {
            clearInterval(progress_interval);
            dialog.set_value('validation_results', `<div class="alert alert-danger">Error: ${r.message || 'Unknown error'}</div>`);
        }
    });
}

function display_validation_results(validation_result, dialog) {
    // Performance optimization: Use template literals and avoid DOM manipulation
    const create_success_html = () => `
        <div class="alert alert-success">
            <h5><i class="fa fa-check"></i> Validation Successful!</h5>
            <div class="row">
                <div class="col-md-4">
                    <div class="metric-card">
                        <h3>${validation_result.total_rows}</h3>
                        <p>Total Rows</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="metric-card">
                        <h3>${validation_result.valid_rows}</h3>
                        <p>Valid Rows</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="metric-card">
                        <h3>${validation_result.groups_count}</h3>
                        <p>Stock Entries</p>
                    </div>
                </div>
            </div>
        </div>
        <style>
            .metric-card { text-align: center; padding: 15px; margin: 5px; border: 1px solid #ddd; border-radius: 5px; }
            .metric-card h3 { margin: 0; color: #28a745; font-size: 2em; }
            .metric-card p { margin: 5px 0 0 0; color: #666; }
        </style>
    `;

    const create_error_section = (title, items, formatter) => {
        if (!items || items.length === 0) return '';

        // Limit display to first 10 items for performance
        const display_items = items.slice(0, 10);
        const has_more = items.length > 10;

        let section = `<h6>${title} (${items.length}):</h6>`;

        if (display_items.length <= 5) {
            section += '<ul>';
            display_items.forEach(item => {
                section += `<li>${formatter(item)}</li>`;
            });
            section += '</ul>';
        } else {
            section += '<div class="error-table-container" style="max-height: 200px; overflow-y: auto;"><table class="table table-sm"><tbody>';
            display_items.forEach(item => {
                section += `<tr><td>${formatter(item)}</td></tr>`;
            });
            section += '</tbody></table></div>';
        }

        if (has_more) {
            section += `<small class="text-muted">... and ${items.length - 10} more items</small>`;
        }

        return section;
    };

    if (validation_result.success) {
        validation_passed = true;
        dialog.set_value('validation_results', create_success_html());

        // Enable import button
        dialog.set_primary_action(__('Import Stock Entries'), function () {
            import_material_issue_entries(dialog.get_values(), dialog);
        });
    } else {
        validation_passed = false;
        const details = validation_result.validation_details || {};

        let html = '<div class="alert alert-danger"><h5><i class="fa fa-times"></i> Validation Failed</h5>';

        // Performance optimization: Use optimized formatters
        html += create_error_section('Missing Items', details.missing_items, item => {
            let result = `Row ${item.row}: "${item.custom_item_name_detail}"`;
            if (item.suggestions && item.suggestions.length > 0) {
                const suggestion_names = item.suggestions.slice(0, 3).map(s => `"${s.custom_item_name_detail}"`).join(', ');
                result += `<br><small class="text-muted">Suggestions: ${suggestion_names}</small>`;
            }
            return result;
        });

        html += create_error_section('Missing Warehouses', details.missing_warehouses, warehouse =>
            `Row ${warehouse.row}: ${warehouse.item_code} - ${warehouse.warehouse}`
        );

        html += create_error_section('Stock/Invoice Issues', details.invoice_issues, issue =>
            `Row ${issue.row}: ${issue.item_code} - Available: ${issue.available_qty}, Requested: ${issue.requested_qty}`
        );

        html += create_error_section('Other Errors', details.errors, error => error);

        html += '</div>';

        // Disable import button
        dialog.set_primary_action(__('Import Stock Entries (Fix errors first)'), null);

        dialog.set_value('validation_results', html);
    }
}

function import_material_issue_entries(values, dialog) {
    // Get file URL from dialog or values
    const file_url = values.excel_file || dialog.get_value('excel_file');

    if (!file_url) {
        frappe.msgprint(__('Please select and validate an Excel file first'));
        return;
    }

    // Check if validation passed
    if (!validation_passed) {
        frappe.msgprint(__('Please validate the file first before importing'));
        return;
    }

    // Performance optimization: Enhanced progress tracking
    const import_progress_html = `
        <div class="import-progress">
            <div class="progress mb-3">
                <div class="progress-bar progress-bar-striped progress-bar-animated" 
                     style="width: 0%" id="import-progress-bar"></div>
            </div>
            <div class="text-center">
                <i class="fa fa-cog fa-spin"></i> 
                <span id="import-status">Preparing import...</span>
            </div>
            <div class="mt-2" id="import-details" style="display: none;">
                <small class="text-muted">Processing groups: <span id="groups-processed">0</span> / <span id="total-groups">0</span></small>
            </div>
        </div>
    `;
    dialog.set_value('import_results', import_progress_html);

    // Enhanced progress simulation
    let import_progress = 0;
    const import_interval = setInterval(() => {
        import_progress += Math.random() * 15;
        if (import_progress > 95) import_progress = 95;
        $('#import-progress-bar').css('width', import_progress + '%');

        if (import_progress > 20 && import_progress < 50) {
            $('#import-status').text('Creating stock entries...');
            $('#import-details').show();
        } else if (import_progress >= 50 && import_progress < 80) {
            $('#import-status').text('Validating stock movements...');
        } else if (import_progress >= 80) {
            $('#import-status').text('Finalizing import...');
        }
    }, 300);

    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_issue.import_material_issue_from_excel',
        args: {
            file_url: file_url
        },
        callback: function (r) {
            clearInterval(import_interval);
            $('#import-progress-bar').css('width', '100%');

            setTimeout(() => {
                if (r.message) {
                    display_import_results(r.message, dialog);
                } else {
                    dialog.set_value('import_results', '<div class="alert alert-danger">Import failed</div>');
                }
            }, 500);
        },
        error: function (r) {
            clearInterval(import_interval);
            dialog.set_value('import_results', `<div class="alert alert-danger">Error: ${r.message || 'Unknown error'}</div>`);
        }
    });
}

function display_import_results(import_result, dialog) {
    // Performance optimization: Create optimized result display
    const create_success_summary = () => `
        <div class="alert alert-success">
            <h5><i class="fa fa-check-circle"></i> Import Completed Successfully!</h5>
            <div class="row mt-3">
                <div class="col-md-4">
                    <div class="result-metric success">
                        <h3>${import_result.success_count}</h3>
                        <p>Stock Entries Created</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="result-metric info">
                        <h3>${import_result.total_items}</h3>
                        <p>Items Processed</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="result-metric ${import_result.error_count > 0 ? 'warning' : 'success'}">
                        <h3>${import_result.error_count}</h3>
                        <p>Errors</p>
                    </div>
                </div>
            </div>
        </div>
    `;

    const create_entries_list = () => {
        if (!import_result.created_entries || import_result.created_entries.length === 0) {
            return '';
        }

        // Use detailed entries if available, otherwise fall back to simple names
        const entries_details = import_result.created_entries_details ||
            import_result.created_entries.map(name => ({
                name: name,
                posting_date: '',
                custom_no: '',
                custom_invoice_number: '',
                items_count: ''
            }));

        // Performance: Limit display and use efficient DOM creation
        const display_entries = entries_details.slice(0, 20);
        const has_more = entries_details.length > 20;

        let entries_html = `<div class="mt-3">
            <h6>
                <i class="fa fa-list"></i> Created Stock Entries: 
                <a href="/app/stock-entry?docstatus=0" target="_blank" class="btn btn-xs btn-primary ml-2" title="Open all Draft Stock Entries">
                    <i class="fa fa-external-link"></i> View All Draft
                </a>
            </h6>
        </div>`;

        // Always show table format for better data presentation
        entries_html += '<div class="entries-table-container" style="max-height: 400px; overflow-y: auto;">';
        entries_html += `<table class="table table-sm table-hover table-striped">
            <thead class="thead-light">
                <tr>
                    <th style="width: 5%;">#</th>
                    <th style="width: 20%;">Stock Entry</th>
                    <th style="width: 15%;">Posting Date</th>
                    <th style="width: 15%;">No</th>
                    <th style="width: 25%;">Invoice Number</th>
                    <th style="width: 10%;">Items</th>
                    <th style="width: 10%;">Action</th>
                </tr>
            </thead>
            <tbody>`;

        display_entries.forEach((entry, idx) => {
            const entry_name = entry.name || entry;
            const posting_date = entry.posting_date || '';
            const custom_no = entry.custom_no || '';
            const custom_invoice_number = entry.custom_invoice_number || '';
            const items_count = entry.items_count || '';

            entries_html += `
                <tr>
                    <td>${idx + 1}</td>
                    <td><a href="/app/stock-entry/${entry_name}" target="_blank" class="text-primary">${entry_name}</a></td>
                    <td>${posting_date}</td>
                    <td>${custom_no}</td>
                    <td title="${custom_invoice_number}">
                        ${custom_invoice_number.length > 20 ? custom_invoice_number.substring(0, 20) + '...' : custom_invoice_number}
                    </td>
                    <td><span class="badge badge-info">${items_count}</span></td>
                    <td>
                        <a href="/app/stock-entry/${entry_name}" target="_blank" class="btn btn-xs btn-outline-primary">
                            <i class="fa fa-external-link"></i>
                        </a>
                    </td>
                </tr>
            `;
        });

        entries_html += '</tbody></table></div>';

        if (has_more) {
            entries_html += `<div class="mt-2">
                <small class="text-muted">Showing ${display_entries.length} of ${entries_details.length} entries</small>
            </div>`;
        }

        return entries_html;
    };

    const create_errors_list = () => {
        if (!import_result.errors || import_result.errors.length === 0) {
            return '';
        }

        const display_errors = import_result.errors.slice(0, 10);
        const has_more = import_result.errors.length > 10;

        let errors_html = '<div class="mt-3"><h6 class="text-danger"><i class="fa fa-exclamation-triangle"></i> Errors:</h6>';
        errors_html += '<div class="alert alert-warning" style="max-height: 200px; overflow-y: auto;"><ul class="mb-0">';

        display_errors.forEach(error => {
            errors_html += `<li>${error}</li>`;
        });

        errors_html += '</ul>';

        if (has_more) {
            errors_html += `<small class="text-muted d-block mt-2">... and ${import_result.errors.length - 10} more errors</small>`;
        }

        errors_html += '</div></div>';
        return errors_html;
    };

    // Build complete HTML
    let html = '';

    if (import_result.success_count > 0) {
        html += create_success_summary();
        html += create_entries_list();
    } else {
        html += '<div class="alert alert-danger"><h5><i class="fa fa-times-circle"></i> Import Failed</h5></div>';
    }

    html += create_errors_list();

    // Add CSS for better styling
    html += `
        <style>
            .result-metric {
                text-align: center; padding: 15px; margin: 5px; border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .result-metric.success { background: #d4edda; border: 1px solid #c3e6cb; }
            .result-metric.info { background: #d1ecf1; border: 1px solid #bee5eb; }
            .result-metric.warning { background: #fff3cd; border: 1px solid #ffeaa7; }
            .result-metric h3 { margin: 0; font-size: 2.2em; font-weight: bold; }
            .result-metric.success h3 { color: #155724; }
            .result-metric.info h3 { color: #0c5460; }
            .result-metric.warning h3 { color: #856404; }
            .result-metric p { margin: 5px 0 0 0; color: #666; font-weight: 500; }
            .entries-grid { display: flex; flex-wrap: wrap; gap: 10px; }
            .entry-card { margin: 5px 0; }
            .entries-table-container { 
                border: 1px solid #dee2e6; 
                border-radius: 4px; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .entries-table-container .table th {
                background-color: #f8f9fa;
                border-bottom: 2px solid #dee2e6;
                font-weight: 600;
                position: sticky;
                top: 0;
                z-index: 10;
            }
            .entries-table-container .table td {
                vertical-align: middle;
            }
            .entries-table-container .table tr:hover {
                background-color: #f5f5f5;
            }
        </style>
    `;

    dialog.set_value('import_results', html);

    // Performance optimization: Debounced refresh
    if (import_result.success_count > 0) {
        setTimeout(() => {
            if (cur_list && cur_list.refresh) {
                cur_list.refresh();
                frappe.show_alert({
                    message: `Successfully created ${import_result.success_count} Stock Entries`,
                    indicator: 'green'
                });
            }
        }, 1000);
    }
}

function show_material_receipt_dialog(listview) {
    let dialog = new frappe.ui.Dialog({
        title: __('Import Material Receipt Stock Entry'),
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
                            <li>Upload and validate file. If any information is incorrect, you must edit the file and upload it again.</li>
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
                    <button class="btn btn-primary btn-sm" id="download-receipt-template-btn">
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
        primary_action: function (values) {
            import_material_receipt_entries(values, dialog);
        },
        secondary_action_label: __('Validate File'),
        secondary_action: function (values) {
            validate_receipt_excel_file(values, dialog);
        }
    });

    dialog.show();

    // Disable import button initially
    dialog.set_primary_action(__('Import Stock Entries (Validate file first)'), null);

    // Performance optimization: Add event handlers immediately
    setup_material_receipt_dialog_handlers(dialog);
}

// Performance optimization: Add debouncing and caching for Material Receipt
let receipt_validation_cache = new Map();
let receipt_validation_timeout = null;
let receipt_validation_passed = false;

function setup_material_receipt_dialog_handlers(dialog) {
    // Download template button handler
    $(dialog.$wrapper).find('#download-receipt-template-btn').off('click').on('click', function () {
        download_material_receipt_template(dialog);
    });

    // File upload handler with debouncing
    dialog.get_field('excel_file').$input.off('change').on('change', function () {
        const file_url = dialog.get_value('excel_file');
        if (file_url) {
            // Reset validation state
            receipt_validation_passed = false;
            dialog.set_primary_action(__('Import Stock Entries (Validate file first)'), null);

            // Clear existing timeout
            if (receipt_validation_timeout) {
                clearTimeout(receipt_validation_timeout);
            }

            // Check cache first
            if (receipt_validation_cache.has(file_url)) {
                const cached_result = receipt_validation_cache.get(file_url);
                display_receipt_validation_results(cached_result, dialog);
                return;
            }

            // Debounce validation for 500ms
            receipt_validation_timeout = setTimeout(() => {
                validate_receipt_excel_file({ excel_file: file_url }, dialog);
            }, 500);
        }
    });
}

function download_material_receipt_template(dialog) {
    frappe.show_alert({
        message: __('Generating template...'),
        indicator: 'blue'
    });

    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_receipt_template.create_material_receipt_template',
        callback: function (r) {
            if (r.message && r.message.file_url) {
                // Create download link
                const link = document.createElement('a');
                link.href = r.message.file_url;
                link.download = 'import_material_receipt_template.xlsx';
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
        error: function (r) {
            frappe.msgprint(__('Error downloading template: {0}', [r.message || 'Unknown error']));
        }
    });
}

function validate_receipt_excel_file(values, dialog) {
    // Get file URL from dialog or values
    const file_url = values.excel_file || dialog.get_value('excel_file');

    if (!file_url) {
        frappe.msgprint(__('Please select an Excel file first'));
        return;
    }

    // Performance optimization: Show progressive loading
    const progress_html = `
        <div class="validation-progress">
            <div class="progress">
                <div class="progress-bar progress-bar-striped progress-bar-animated" 
                     style="width: 0%" id="receipt-validation-progress-bar"></div>
            </div>
            <div class="text-center mt-2">
                <i class="fa fa-spinner fa-spin"></i> 
                <span id="receipt-validation-status">Starting validation...</span>
            </div>
        </div>
    `;
    dialog.set_value('validation_results', progress_html);

    // Simulate progress updates
    let progress = 0;
    const progress_interval = setInterval(() => {
        progress += Math.random() * 20;
        if (progress > 90) progress = 90;
        $('#receipt-validation-progress-bar').css('width', progress + '%');

        if (progress > 30 && progress < 60) {
            $('#receipt-validation-status').text('Checking file format...');
        } else if (progress >= 60) {
            $('#receipt-validation-status').text('Validating data...');
        }
    }, 200);

    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_receipt.validate_excel_file',
        args: {
            file_url: file_url
        },
        callback: function (r) {
            clearInterval(progress_interval);
            if (r.message) {
                // Cache the result for future use
                receipt_validation_cache.set(file_url, r.message);
                display_receipt_validation_results(r.message, dialog);
            } else {
                dialog.set_value('validation_results', '<div class="alert alert-danger">Validation failed</div>');
            }
        },
        error: function (r) {
            clearInterval(progress_interval);
            dialog.set_value('validation_results', `<div class="alert alert-danger">Error: ${r.message || 'Unknown error'}</div>`);
        }
    });
}

function display_receipt_validation_results(validation_result, dialog) {
    // Performance optimization: Use template literals and avoid DOM manipulation
    const create_success_html = () => `
        <div class="alert alert-success">
            <h5><i class="fa fa-check"></i> Validation Successful!</h5>
            <div class="row">
                <div class="col-md-4">
                    <div class="metric-card">
                        <h3>${validation_result.total_rows}</h3>
                        <p>Total Rows</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="metric-card">
                        <h3>${validation_result.valid_rows}</h3>
                        <p>Valid Rows</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="metric-card">
                        <h3>${validation_result.groups_count}</h3>
                        <p>Stock Entries</p>
                    </div>
                </div>
            </div>
        </div>
        <style>
            .metric-card { text-align: center; padding: 15px; margin: 5px; border: 1px solid #ddd; border-radius: 5px; }
            .metric-card h3 { margin: 0; color: #28a745; font-size: 2em; }
            .metric-card p { margin: 5px 0 0 0; color: #666; }
        </style>
    `;

    const create_error_section = (title, items, formatter) => {
        if (!items || items.length === 0) return '';

        // Limit display to first 10 items for performance
        const display_items = items.slice(0, 10);
        const has_more = items.length > 10;

        let section = `<h6>${title} (${items.length}):</h6>`;

        if (display_items.length <= 5) {
            section += '<ul>';
            display_items.forEach(item => {
                section += `<li>${formatter(item)}</li>`;
            });
            section += '</ul>';
        } else {
            section += '<div class="error-table-container" style="max-height: 200px; overflow-y: auto;"><table class="table table-sm"><tbody>';
            display_items.forEach(item => {
                section += `<tr><td>${formatter(item)}</td></tr>`;
            });
            section += '</tbody></table></div>';
        }

        if (has_more) {
            section += `<small class="text-muted">... and ${items.length - 10} more items</small>`;
        }

        return section;
    };

    if (validation_result.success) {
        receipt_validation_passed = true;
        dialog.set_value('validation_results', create_success_html());

        // Enable import button
        dialog.set_primary_action(__('Import Stock Entries'), function () {
            import_material_receipt_entries(dialog.get_values(), dialog);
        });
    } else {
        receipt_validation_passed = false;
        const details = validation_result.validation_details || {};

        let html = '<div class="alert alert-danger"><h5><i class="fa fa-times"></i> Validation Failed</h5>';

        // Performance optimization: Use optimized formatters
        html += create_error_section('Missing Items', details.missing_items, item => {
            let result = `Row ${item.row}: "${item.custom_item_name_detail}"`;
            if (item.suggestions && item.suggestions.length > 0) {
                const suggestion_names = item.suggestions.slice(0, 3).map(s => `"${s.custom_item_name_detail}"`).join(', ');
                result += `<br><small class="text-muted">Suggestions: ${suggestion_names}</small>`;
            }
            return result;
        });

        html += create_error_section('Missing Warehouses', details.missing_warehouses, warehouse =>
            `Row ${warehouse.row}: ${warehouse.item_code} - ${warehouse.warehouse}`
        );

        html += create_error_section('Stock/Invoice Issues', details.invoice_issues, issue =>
            `Row ${issue.row}: ${issue.item_code} - Available: ${issue.available_qty}, Requested: ${issue.requested_qty}`
        );

        html += create_error_section('Other Errors', details.errors, error => error);

        html += '</div>';

        // Disable import button
        dialog.set_primary_action(__('Import Stock Entries (Fix errors first)'), null);

        dialog.set_value('validation_results', html);
    }
}

function import_material_receipt_entries(values, dialog) {
    // Get file URL from dialog or values
    const file_url = values.excel_file || dialog.get_value('excel_file');

    if (!file_url) {
        frappe.msgprint(__('Please select and validate an Excel file first'));
        return;
    }

    // Check if validation passed
    if (!receipt_validation_passed) {
        frappe.msgprint(__('Please validate the file first before importing'));
        return;
    }

    // Performance optimization: Enhanced progress tracking
    const import_progress_html = `
        <div class="import-progress">
            <div class="progress mb-3">
                <div class="progress-bar progress-bar-striped progress-bar-animated" 
                     style="width: 0%" id="receipt-import-progress-bar"></div>
            </div>
            <div class="text-center">
                <i class="fa fa-cog fa-spin"></i> 
                <span id="receipt-import-status">Preparing import...</span>
            </div>
            <div class="mt-2" id="receipt-import-details" style="display: none;">
                <small class="text-muted">Processing groups: <span id="receipt-groups-processed">0</span> / <span id="receipt-total-groups">0</span></small>
            </div>
        </div>
    `;
    dialog.set_value('import_results', import_progress_html);

    // Enhanced progress simulation
    let import_progress = 0;
    const import_interval = setInterval(() => {
        import_progress += Math.random() * 15;
        if (import_progress > 95) import_progress = 95;
        $('#receipt-import-progress-bar').css('width', import_progress + '%');

        if (import_progress > 20 && import_progress < 50) {
            $('#receipt-import-status').text('Creating stock entries...');
            $('#receipt-import-details').show();
        } else if (import_progress >= 50 && import_progress < 80) {
            $('#receipt-import-status').text('Validating stock movements...');
        } else if (import_progress >= 80) {
            $('#receipt-import-status').text('Finalizing import...');
        }
    }, 300);

    frappe.call({
        method: 'customize_erpnext.api.bulk_update_scripts.create_material_receipt.import_material_receipt_from_excel',
        args: {
            file_url: file_url
        },
        callback: function (r) {
            clearInterval(import_interval);
            $('#receipt-import-progress-bar').css('width', '100%');

            setTimeout(() => {
                if (r.message) {
                    display_receipt_import_results(r.message, dialog);
                } else {
                    dialog.set_value('import_results', '<div class="alert alert-danger">Import failed</div>');
                }
            }, 500);
        },
        error: function (r) {
            clearInterval(import_interval);
            dialog.set_value('import_results', `<div class="alert alert-danger">Error: ${r.message || 'Unknown error'}</div>`);
        }
    });
}

function display_receipt_import_results(import_result, dialog) {
    // Performance optimization: Create optimized result display
    const create_success_summary = () => `
        <div class="alert alert-success">
            <h5><i class="fa fa-check-circle"></i> Import Completed Successfully!</h5>
            <div class="row mt-3">
                <div class="col-md-4">
                    <div class="result-metric success">
                        <h3>${import_result.success_count}</h3>
                        <p>Stock Entries Created</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="result-metric info">
                        <h3>${import_result.total_items}</h3>
                        <p>Items Processed</p>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="result-metric ${import_result.error_count > 0 ? 'warning' : 'success'}">
                        <h3>${import_result.error_count}</h3>
                        <p>Errors</p>
                    </div>
                </div>
            </div>
        </div>
    `;

    const create_entries_list = () => {
        if (!import_result.created_entries || import_result.created_entries.length === 0) {
            return '';
        }

        // Use detailed entries if available, otherwise fall back to simple names
        const entries_details = import_result.created_entries_details ||
            import_result.created_entries.map(name => ({
                name: name,
                posting_date: '',
                custom_no: '',
                custom_invoice_number: '',
                items_count: ''
            }));

        // Performance: Limit display and use efficient DOM creation
        const display_entries = entries_details.slice(0, 20);
        const has_more = entries_details.length > 20;

        let entries_html = `<div class="mt-3">
            <h6>
                <i class="fa fa-list"></i> Created Stock Entries: 
                <a href="/app/stock-entry?docstatus=0" target="_blank" class="btn btn-xs btn-primary ml-2" title="Open all Draft Stock Entries">
                    <i class="fa fa-external-link"></i> View All Draft
                </a>
            </h6>
        </div>`;

        // Always show table format for better data presentation
        entries_html += '<div class="entries-table-container" style="max-height: 400px; overflow-y: auto;">';
        entries_html += `<table class="table table-sm table-hover table-striped">
            <thead class="thead-light">
                <tr>
                    <th style="width: 5%;">#</th>
                    <th style="width: 20%;">Stock Entry</th>
                    <th style="width: 15%;">Posting Date</th>
                    <th style="width: 15%;">No</th>
                    <th style="width: 25%;">Invoice Number</th>
                    <th style="width: 10%;">Items</th>
                    <th style="width: 10%;">Action</th>
                </tr>
            </thead>
            <tbody>`;

        display_entries.forEach((entry, idx) => {
            const entry_name = entry.name || entry;
            const posting_date = entry.posting_date || '';
            const custom_no = entry.custom_no || '';
            const custom_invoice_number = entry.custom_invoice_number || '';
            const items_count = entry.items_count || '';

            entries_html += `
                <tr>
                    <td>${idx + 1}</td>
                    <td><a href="/app/stock-entry/${entry_name}" target="_blank" class="text-primary">${entry_name}</a></td>
                    <td>${posting_date}</td>
                    <td>${custom_no}</td>
                    <td title="${custom_invoice_number}">
                        ${custom_invoice_number.length > 20 ? custom_invoice_number.substring(0, 20) + '...' : custom_invoice_number}
                    </td>
                    <td><span class="badge badge-info">${items_count}</span></td>
                    <td>
                        <a href="/app/stock-entry/${entry_name}" target="_blank" class="btn btn-xs btn-outline-primary">
                            <i class="fa fa-external-link"></i>
                        </a>
                    </td>
                </tr>
            `;
        });

        entries_html += '</tbody></table></div>';

        if (has_more) {
            entries_html += `<div class="mt-2">
                <small class="text-muted">Showing ${display_entries.length} of ${entries_details.length} entries</small>
            </div>`;
        }

        return entries_html;
    };

    const create_errors_list = () => {
        if (!import_result.errors || import_result.errors.length === 0) {
            return '';
        }

        const display_errors = import_result.errors.slice(0, 10);
        const has_more = import_result.errors.length > 10;

        let errors_html = '<div class="mt-3"><h6 class="text-danger"><i class="fa fa-exclamation-triangle"></i> Errors:</h6>';
        errors_html += '<div class="alert alert-warning" style="max-height: 200px; overflow-y: auto;"><ul class="mb-0">';

        display_errors.forEach(error => {
            errors_html += `<li>${error}</li>`;
        });

        errors_html += '</ul>';

        if (has_more) {
            errors_html += `<small class="text-muted d-block mt-2">... and ${import_result.errors.length - 10} more errors</small>`;
        }

        errors_html += '</div></div>';
        return errors_html;
    };

    // Build complete HTML
    let html = '';

    if (import_result.success_count > 0) {
        html += create_success_summary();
        html += create_entries_list();
    } else {
        html += '<div class="alert alert-danger"><h5><i class="fa fa-times-circle"></i> Import Failed</h5></div>';
    }

    html += create_errors_list();

    // Add CSS for better styling
    html += `
        <style>
            .result-metric {
                text-align: center; padding: 15px; margin: 5px; border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .result-metric.success { background: #d4edda; border: 1px solid #c3e6cb; }
            .result-metric.info { background: #d1ecf1; border: 1px solid #bee5eb; }
            .result-metric.warning { background: #fff3cd; border: 1px solid #ffeaa7; }
            .result-metric h3 { margin: 0; font-size: 2.2em; font-weight: bold; }
            .result-metric.success h3 { color: #155724; }
            .result-metric.info h3 { color: #0c5460; }
            .result-metric.warning h3 { color: #856404; }
            .result-metric p { margin: 5px 0 0 0; color: #666; font-weight: 500; }
            .entries-grid { display: flex; flex-wrap: wrap; gap: 10px; }
            .entry-card { margin: 5px 0; }
            .entries-table-container { 
                border: 1px solid #dee2e6; 
                border-radius: 4px; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .entries-table-container .table th {
                background-color: #f8f9fa;
                border-bottom: 2px solid #dee2e6;
                font-weight: 600;
                position: sticky;
                top: 0;
                z-index: 10;
            }
            .entries-table-container .table td {
                vertical-align: middle;
            }
            .entries-table-container .table tr:hover {
                background-color: #f5f5f5;
            }
        </style>
    `;

    dialog.set_value('import_results', html);

    // Performance optimization: Debounced refresh
    if (import_result.success_count > 0) {
        setTimeout(() => {
            if (cur_list && cur_list.refresh) {
                cur_list.refresh();
                frappe.show_alert({
                    message: `Successfully created ${import_result.success_count} Stock Entries`,
                    indicator: 'green'
                });
            }
        }, 1000);
    }
}