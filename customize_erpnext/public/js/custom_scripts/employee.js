// import apps/customize_erpnext/customize_erpnext/public/js/utilities.js
// import apps/customize_erpnext/customize_erpnext/public/js/shared_fingerprint_sync.js

// Store original employee value to prevent naming series interference
window.original_employee_code = null;

// Ensure FingerprintScannerDialog is available
function ensureFingerprintModule() {
    return new Promise((resolve) => {
        if (window.FingerprintScannerDialog && window.FingerprintScannerDialog.showForEmployee) {
            resolve(true);
            return;
        }

        // Try to manually load the script if needed
        if (!document.querySelector('script[src*="fingerprint_scanner_dialog.js"]')) {
            const script = document.createElement('script');
            script.src = '/assets/customize_erpnext/js/fingerprint_scanner_dialog.js';
            document.head.appendChild(script);
        }

        // Try to load module if not available
        let attempts = 0;
        const maxAttempts = 15;  // Increased attempts

        const checkModule = () => {
            attempts++;

            if (window.FingerprintScannerDialog && window.FingerprintScannerDialog.showForEmployee) {
                resolve(true);
            } else if (attempts < maxAttempts) {
                setTimeout(checkModule, 200);
            } else {
                resolve(false);
            }
        };

        checkModule();
    });
}

frappe.ui.form.on('Employee', {
    refresh: function (frm) {
        // Add custom button for fingerprint scanning if not new record
        if (!frm.is_new() && frm.doc.name) {
            frm.add_custom_button(__('🔍 Scan Fingerprints'), async function () {
                // Show fingerprint scanner dialog with fixed employee
                const moduleReady = await ensureFingerprintModule();
                if (moduleReady) {
                    window.FingerprintScannerDialog.showForEmployee(frm.doc.name, frm.doc.employee_name);
                } else {
                    frappe.msgprint({
                        title: __('Module Loading Failed'),
                        message: __('Fingerprint Scanner module could not be loaded. Please refresh the page and try again.'),
                        indicator: 'red'
                    });
                }
            }, __('Actions'));
        }

        // Setup image field with cropper
        setup_employee_image_cropper(frm);
    },

    onload: function (frm) {
        // Setup image field with cropper on load
        setup_employee_image_cropper(frm);
    },

    image: function (frm) {
        // Image upload is handled by custom FileUploader with auto-cropping
        // No need to manually trigger cropper

        if (frm.is_new()) {
            // Auto-populate employee code and attendance device ID for new employees
            if (!frm.doc.employee || !frm.doc.employee.startsWith('TIQN-')) {
                frappe.call({
                    method: 'customize_erpnext.api.employee.employee_utils.get_next_employee_code',
                    callback: function (r) {
                        if (r.message) {
                            frm.set_value('employee', r.message);
                            // Store the original value
                            window.original_employee_code = r.message;

                            // Update naming series to prevent duplicates
                            let employee_num = parseInt(r.message.replace('TIQN-', '')) - 1;
                            frappe.call({
                                method: 'customize_erpnext.api.employee.employee_utils.set_series',
                                args: {
                                    prefix: 'TIQN-',
                                    current_highest_id: employee_num
                                },
                                callback: function (series_r) {
                                    // Series updated successfully
                                }
                            });
                            // Auto-populated employee code successfully
                        }
                    }
                });

            } else {
                // Store existing value
                window.original_employee_code = frm.doc.employee;
            }

            if (!frm.doc.attendance_device_id) {
                frappe.call({
                    method: 'customize_erpnext.api.employee.employee_utils.get_next_attendance_device_id',
                    callback: function (r) {
                        if (r.message) {
                            frm.set_value('attendance_device_id', r.message);
                        }
                    }
                });
            }
        } else {
            // For existing employees, store current value
            window.original_employee_code = frm.doc.employee;
        }
    },

    custom_scan_fingerprint: async function (frm) {
        // Handle custom button field click
        if (!frm.is_new() && frm.doc.name) {
            const moduleReady = await ensureFingerprintModule();
            if (moduleReady) {
                window.FingerprintScannerDialog.showForEmployee(frm.doc.name, frm.doc.employee_name);
            } else {
                frappe.msgprint({
                    title: __('Module Loading Failed'),
                    message: __('Fingerprint Scanner module could not be loaded. Please refresh the page and try again.'),
                    indicator: 'red'
                });
            }
        } else {
            frappe.msgprint({
                title: __('Save Required'),
                message: __('Please save the employee record first before scanning fingerprints.'),
                indicator: 'orange'
            });
        }
    },

    custom_sync_fingerprint_data_to_machine: function (frm) {
        // Handle sync fingerprint button click
        if (!frm.is_new() && frm.doc.name) {
            // Use shared sync dialog for single employee
            const employee = {
                employee_id: frm.doc.name,
                employee_name: frm.doc.employee_name
            };
            window.showSharedSyncDialog([employee]);
        } else {
            frappe.msgprint({
                title: __('Save Required'),
                message: __('Please save the employee record first before syncing fingerprints.'),
                indicator: 'orange'
            });
        }
    },

    employee: function (frm) {
        // Store the employee value whenever it changes
        if (frm.doc.employee && frm.doc.employee.startsWith('TIQN-')) {
            window.original_employee_code = frm.doc.employee;
        }
    },

    before_save: function (frm) {
        // Ensure employee code follows TIQN-XXXX format
        if (frm.doc.employee && !frm.doc.employee.startsWith('TIQN-')) {
            frappe.msgprint(__('Employee code should follow TIQN-XXXX format'));
            frappe.validated = false;
            return;
        }

        // Check for duplicate employee code
        if (frm.doc.employee) {
            frappe.call({
                method: 'customize_erpnext.api.employee.employee_utils.check_duplicate_employee',
                args: {
                    employee_code: frm.doc.employee,
                    current_doc_name: frm.doc.name
                },
                async: false,
                callback: function (r) {
                    if (r.message && r.message.exists) {
                        frappe.msgprint(__('Employee code {0} already exists in the system', [frm.doc.employee]));
                        frappe.validated = false;
                    }
                }
            });
        }

        // Check for duplicate attendance device ID
        if (frm.doc.attendance_device_id) {
            frappe.call({
                method: 'customize_erpnext.api.employee.employee_utils.check_duplicate_attendance_device_id',
                args: {
                    attendance_device_id: frm.doc.attendance_device_id,
                    current_doc_name: frm.doc.name
                },
                async: false,
                callback: function (r) {
                    if (r.message && r.message.exists) {
                        frappe.msgprint(__('Attendance Device ID {0} already exists in the system', [frm.doc.attendance_device_id]));
                        frappe.validated = false;
                    }
                }
            });
        }

        // set employee_name = first_name + " " + midile_name + " " + last_name
        if (frm.doc.first_name && frm.doc.last_name) {
            frm.set_value('employee_name',
                [frm.doc.first_name, frm.doc.middle_name, frm.doc.last_name].filter(Boolean).join(' ')
            );
        }
        // check if employee_name icluding numbers throw error
        if (frm.doc.employee_name && /\d/.test(frm.doc.employee_name)) {
            frappe.msgprint(__('Employee name should not contain numbers'));
            frappe.validated = false;
        }

        // Validate maternity tracking date overlaps
        if (frm.doc.maternity_tracking && frm.doc.maternity_tracking.length > 1) {
            if (!validate_all_maternity_periods(frm)) {
                frappe.validated = false;
            }
        }
    },
});

// Maternity Tracking child table events
frappe.ui.form.on('Maternity Tracking', {
    type: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        // Auto-set apply_pregnant_benefit = 1 when type = 'Pregnant'
        if (row.type === 'Pregnant') {
            frappe.model.set_value(cdt, cdn, 'apply_pregnant_benefit', 1);
        } else {
            // Clear the field for other types since it's only relevant for Pregnant
            frappe.model.set_value(cdt, cdn, 'apply_pregnant_benefit', 0);
        }
    },

    from_date: function (frm, cdt, cdn) {
        validate_maternity_date_overlap(frm, cdt, cdn);
    },

    to_date: function (frm, cdt, cdn) {
        validate_maternity_date_overlap(frm, cdt, cdn);
        validate_date_sequence(frm, cdt, cdn);
    }
});

// Function to validate date sequence (from_date should be before to_date)
function validate_date_sequence(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (row.from_date && row.to_date) {
        let from_date = frappe.datetime.str_to_obj(row.from_date);
        let to_date = frappe.datetime.str_to_obj(row.to_date);

        if (from_date >= to_date) {
            frappe.msgprint({
                title: __('Invalid Date Range'),
                message: __('From Date must be earlier than To Date'),
                indicator: 'red'
            });
            frappe.model.set_value(cdt, cdn, 'to_date', '');
            return false;
        }
    }

    return true;
}

// Function to validate all maternity tracking periods on form save
function validate_all_maternity_periods(frm) {
    let maternity_tracking = frm.doc.maternity_tracking || [];
    let valid_periods = [];

    // First, validate each row for date sequence
    for (let i = 0; i < maternity_tracking.length; i++) {
        let row = maternity_tracking[i];

        if (!row.from_date || !row.to_date) {
            continue; // Skip incomplete rows
        }

        let from_date = frappe.datetime.str_to_obj(row.from_date);
        let to_date = frappe.datetime.str_to_obj(row.to_date);

        // Check date sequence
        if (from_date >= to_date) {
            frappe.msgprint({
                title: __('Invalid Date Range'),
                message: __('Row {0}: From Date must be earlier than To Date', [row.idx]),
                indicator: 'red'
            });
            return false;
        }

        valid_periods.push({
            idx: row.idx,
            type: row.type,
            from_date: from_date,
            to_date: to_date,
            from_date_str: frappe.datetime.str_to_user(row.from_date),
            to_date_str: frappe.datetime.str_to_user(row.to_date)
        });
    }

    // Check for overlapping periods
    for (let i = 0; i < valid_periods.length; i++) {
        for (let j = i + 1; j < valid_periods.length; j++) {
            let period1 = valid_periods[i];
            let period2 = valid_periods[j];

            // Check for overlap
            let has_overlap = (period1.from_date < period2.to_date && period1.to_date > period2.from_date);

            if (has_overlap) {
                frappe.msgprint({
                    title: __('Date Period Overlap Detected'),
                    message: __('Overlapping periods found:<br><br>Row {0}: {1} ({2} - {3})<br>Row {4}: {5} ({6} - {7})<br><br>Please adjust the dates to avoid overlapping periods.', [
                        period1.idx, period1.type, period1.from_date_str, period1.to_date_str,
                        period2.idx, period2.type, period2.from_date_str, period2.to_date_str
                    ]),
                    indicator: 'red'
                });
                return false;
            }
        }
    }

    return true;
}

// Function to validate overlapping date periods
function validate_maternity_date_overlap(frm, cdt, cdn) {
    let current_row = locals[cdt][cdn];

    // Only validate if both dates are filled
    if (!current_row.from_date || !current_row.to_date) {
        return;
    }

    let current_from = frappe.datetime.str_to_obj(current_row.from_date);
    let current_to = frappe.datetime.str_to_obj(current_row.to_date);

    // Validate date sequence first
    if (current_from >= current_to) {
        return; // Will be handled by validate_date_sequence
    }

    // Check for overlaps with other rows
    let maternity_tracking = frm.doc.maternity_tracking || [];
    let overlapping_rows = [];

    maternity_tracking.forEach(function (row) {
        // Skip current row and rows without both dates
        if (row.name === current_row.name || !row.from_date || !row.to_date) {
            return;
        }

        let row_from = frappe.datetime.str_to_obj(row.from_date);
        let row_to = frappe.datetime.str_to_obj(row.to_date);

        // Check for overlap: two periods overlap if one starts before the other ends
        let has_overlap = (current_from < row_to && current_to > row_from);

        if (has_overlap) {
            overlapping_rows.push({
                idx: row.idx,
                type: row.type,
                from_date: frappe.datetime.str_to_user(row.from_date),
                to_date: frappe.datetime.str_to_user(row.to_date)
            });
        }
    });

    if (overlapping_rows.length > 0) {
        let overlap_details = overlapping_rows.map(row =>
            `Row ${row.idx}: ${row.type} (${row.from_date} - ${row.to_date})`
        ).join('<br>');

        frappe.msgprint({
            title: __('Date Period Overlap Detected'),
            message: __('The current date period overlaps with existing records:<br><br>{0}<br><br>Please adjust the dates to avoid overlapping periods.', [overlap_details]),
            indicator: 'red'
        });

        // Clear both dates to force user to re-enter correct values
        frappe.model.set_value(cdt, cdn, 'from_date', '');
        frappe.model.set_value(cdt, cdn, 'to_date', '');

        return false;
    }

    return true;
}

// Legacy sync dialog functions removed - now using shared_fingerprint_sync.js

function toProperCase(str) {
    if (!str) return str;

    let result = str.trim().toLowerCase();

    // First, handle regular word boundaries (spaces, punctuation)
    result = result.replace(/\b\w/g, function (char) {
        return char.toUpperCase();
    });

    // Special handling: ensure first non-number character is uppercase
    // This handles cases like "26ss" → "26Ss"
    result = result.replace(/^(\d*)([a-z])/, function (_, numbers, firstLetter) {
        return numbers + firstLetter.toUpperCase();
    });

    return result;
}

// ============================================================
// IMAGE CROPPER CONFIGURATION
// ============================================================
// Set to true to enable custom 3:4 ratio image cropper
// Set to false to use default Frappe upload (no cropping)
const ENABLE_EMPLOYEE_IMAGE_CROPPER = false;
//   const ENABLE_EMPLOYEE_IMAGE_CROPPER = true;
//   2. Sửa hooks.py dòng 327-337: Uncomment các dòng Cropper.js:
//   app_include_css = [
//       "https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.css"
//   ]
//   app_include_js = [
//       "/assets/customize_erpnext/js/fingerprint_scanner_dialog.js",
//       "https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.js"
//   ]
//   3. Build lại:
//   bench build --app customize_erpnext && bench --site erp-sonnt.tiqn.local clear-cache
// ============================================================

// Image cropper functions - using custom Cropper.js
function setup_employee_image_cropper(frm) {
    if (!frm.fields_dict.image) return;

    const image_field = frm.fields_dict.image;

    // Override the attach field's upload method completely
    setTimeout(() => {
        if (image_field && image_field.$wrapper) {
            console.log('Setting up image field for Employee');

            // Always hide camera-related buttons
            image_field.$wrapper.find('[data-action="capture_image"]').hide();
            image_field.$wrapper.find('.btn:contains("Take Photo")').hide();
            image_field.$wrapper.find('.btn:contains("Chụp ảnh")').hide();
            image_field.$wrapper.find('.webcam-container').hide();

            // Only enable custom cropper if ENABLE_EMPLOYEE_IMAGE_CROPPER is true
            if (!ENABLE_EMPLOYEE_IMAGE_CROPPER) {
                console.log('Custom image cropper is DISABLED - using default upload');
                return;
            }

            console.log('Custom image cropper is ENABLED');

            // CRITICAL: Override FileUploader options to disable built-in cropper
            // and use custom aspect ratio
            const original_FileUploader = frappe.ui.FileUploader;

            // Intercept FileUploader creation for this field
            frappe.ui.FileUploader = class CustomFileUploader extends original_FileUploader {
                constructor(opts) {
                    // Check if this is for the employee image field
                    if (opts && opts.doctype === 'Employee' && opts.fieldname === 'image') {
                        console.log('Intercepting FileUploader for Employee image');
                        // Disable built-in cropper
                        opts.crop_image_aspect_ratio = null;

                        // Store original on_success
                        const original_on_success = opts.on_success;

                        // Replace on_success to trigger our custom cropper
                        opts.on_success = (file_doc) => {
                            console.log('File uploaded, showing custom cropper');
                            console.log('File doc:', file_doc);
                            // Show our custom cropper instead
                            if (file_doc && file_doc.file_url) {
                                console.log('Reading file content from:', file_doc.file_url);
                                // Use custom method to get file content as base64
                                frappe.call({
                                    method: 'customize_erpnext.api.employee.employee_utils.get_file_content_base64',
                                    args: {
                                        file_url: file_doc.file_url
                                    },
                                    callback: function (r) {
                                        console.log('File content response:', r);
                                        if (r.message) {
                                            console.log('Base64 data received, length:', r.message.length);
                                            // r.message contains base64 data URI
                                            show_custom_image_cropper_dialog(frm, r.message, file_doc.file_name);
                                        } else {
                                            console.error('No base64 data in response');
                                        }
                                    },
                                    error: function (err) {
                                        console.error('Error reading file:', err);
                                        frappe.msgprint({
                                            title: __('Error'),
                                            message: __('Failed to read uploaded file'),
                                            indicator: 'red'
                                        });
                                    }
                                });
                            }
                        };
                    }
                    super(opts);
                }
            };

            // Restore original FileUploader after field is initialized
            setTimeout(() => {
                frappe.ui.FileUploader = original_FileUploader;
            }, 2000);
        }
    }, 500);
}

function show_custom_image_cropper_dialog(frm, imageDataUrl, fileName) {
    // Create dialog with custom cropper
    const dialog = new frappe.ui.Dialog({
        title: __('Crop Image - Fixed Ratio 3:4 (Portrait)'),
        size: 'large',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'cropper_container',
            }
        ],
        primary_action_label: __('Crop & Upload'),
        primary_action: function () {
            const cropper = dialog.cropper_instance;
            if (cropper) {
                // Get cropped canvas
                const canvas = cropper.getCroppedCanvas({
                    maxWidth: 1200,
                    maxHeight: 1600,
                    imageSmoothingEnabled: true,
                    imageSmoothingQuality: 'high',
                });

                // Convert to blob
                canvas.toBlob(function (blob) {
                    // Convert blob to base64
                    const reader = new FileReader();
                    reader.onloadend = function () {
                        const base64data = reader.result;

                        // Upload the cropped image
                        upload_cropped_employee_image(frm, base64data, fileName, dialog);
                    };
                    reader.readAsDataURL(blob);
                }, 'image/jpeg', 0.9);
            }
        },
        secondary_action_label: __('Cancel'),
    });

    dialog.show();

    // Wait for dialog to render, then initialize Cropper.js
    dialog.$wrapper.find('.modal-dialog').css('max-width', '90%');

    setTimeout(() => {
        const container = dialog.fields_dict.cropper_container.$wrapper;
        container.html(`
            <div style="max-height: 70vh; overflow: hidden;">
                <img id="image-to-crop" src="${imageDataUrl}" style="max-width: 100%; display: block;">
            </div>
            <div style="margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 5px;">
                <p style="margin: 0; color: #6c757d; font-size: 13px;">
                    <strong>Instructions:</strong>
                    Use mouse wheel to zoom, drag to move image.
                    The crop box is fixed at 3:4 ratio (portrait).
                </p>
            </div>
        `);

        const image = document.getElementById('image-to-crop');

        // Check if Cropper.js is available
        if (typeof Cropper === 'undefined') {
            frappe.msgprint({
                title: __('Library Not Loaded'),
                message: __('Cropper.js library is not available. Please refresh the page and try again.'),
                indicator: 'red'
            });
            dialog.hide();
            return;
        }

        // Initialize Cropper.js with fixed 3:4 aspect ratio
        dialog.cropper_instance = new Cropper(image, {
            aspectRatio: 3 / 4,  // Fixed 3:4 ratio (portrait)
            viewMode: 1,
            dragMode: 'move',
            autoCropArea: 0.8,
            restore: false,
            guides: true,
            center: true,
            highlight: false,
            cropBoxMovable: true,
            cropBoxResizable: true,
            toggleDragModeOnDblclick: false,
            responsive: true,
            background: true,
            modal: true,
            zoomable: true,
            zoomOnWheel: true,
            wheelZoomRatio: 0.1,
        });
    }, 300);
}

function upload_cropped_employee_image(frm, base64data, fileName, dialog) {
    // Show uploading message
    frappe.show_alert({
        message: __('Uploading image...'),
        indicator: 'blue'
    });

    // Create file name
    const employee_name = frm.doc.name || 'new';
    const full_name = (frm.doc.employee_name || 'employee').replace(/\s+/g, '_');
    const file_name = `${employee_name}_${full_name}.jpg`;

    // Upload to custom path
    frappe.call({
        method: 'customize_erpnext.api.employee.employee_utils.upload_employee_image',
        args: {
            employee_id: frm.doc.name,
            employee_name: frm.doc.employee_name,
            file_content: base64data,
            file_name: file_name
        },
        callback: function (response) {
            if (response.message) {
                // Set the image value
                frm.set_value('image', response.message.file_url);

                dialog.hide();

                // Save the form to persist the image field
                frm.save().then(() => {
                    frappe.show_alert({
                        message: __('Image cropped and saved successfully'),
                        indicator: 'green'
                    });
                });
            } else {
                frappe.msgprint({
                    title: __('Upload Failed'),
                    message: __('Failed to save image'),
                    indicator: 'red'
                });
            }
        },
        error: function (error) {
            console.error('Error uploading image:', error);
            frappe.msgprint({
                title: __('Upload Error'),
                message: __('Error uploading image. Please try again.'),
                indicator: 'red'
            });
        }
    });
}