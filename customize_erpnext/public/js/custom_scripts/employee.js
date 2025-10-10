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
        // Check if employee can be modified (name and attendance_device_id)
        if (!frm.is_new() && frm.doc.name) {
            frappe.call({
                method: 'customize_erpnext.api.employee.employee_utils.allow_change_name_attendance_device_id',
                args: {
                    name: frm.doc.name
                },
                callback: function (r) {
                    if (!r.message) {
                        // Employee has checkin records, set fields as read-only
                        frm.set_df_property('employee', 'read_only', 1);
                        frm.set_df_property('attendance_device_id', 'read_only', 1);

                        // Add indicator
                        frm.dashboard.add_indicator(__('Employee ID and Attendance Device ID are locked (has attendance records)'), 'orange');
                    } else {
                        // Allow editing
                        frm.set_df_property('employee', 'read_only', 0);
                        frm.set_df_property('attendance_device_id', 'read_only', 0);
                    }
                }
            });
        }

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
            },);

            // Add Photo Management buttons
            frm.add_custom_button(__('📷 Take Photo'), function () {
                open_camera_dialog(frm);
            },);

            frm.add_custom_button(__('📁 Upload Photo'), function () {
                open_file_upload_dialog(frm);
            },);
        }
        if (frm.is_new()) {
            // Auto-populate employee code and attendance device ID for new employees
            if (!frm.doc.employee || !frm.doc.employee.startsWith('TIQN-')) {
                frappe.call({
                    method: 'customize_erpnext.api.employee.employee_utils.get_next_employee_code',
                    callback: function (r) {
                        if (r.message) {
                            frm.set_value('employee', r.message);
                            console.log('get_next_employee_code:', r.message);
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
                                    console.log('set_series response:', series_r);
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
// EMPLOYEE PHOTO FUNCTIONS - TAKE PHOTO & UPLOAD PHOTO
// ============================================================

// Global variable to store camera stream
let currentCameraStream = null;

// Open camera dialog to capture photo
function open_camera_dialog(frm) {
    const dialog = new frappe.ui.Dialog({
        title: __('Take Photo'),
        size: 'large',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'camera_container',
            }
        ],
        primary_action_label: __('Capture'),
        primary_action: function () {
            const video = dialog.$wrapper.find('video')[0];
            const canvas = document.createElement('canvas');
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0);

            // Stop camera stream
            stop_camera_stream();

            // Get image data
            const imageDataUrl = canvas.toDataURL('image/jpeg', 0.95);

            // Close camera dialog
            dialog.hide();

            // Show cropper dialog
            show_crop_dialog(frm, imageDataUrl);
        },
        secondary_action_label: __('Cancel'),
        secondary_action: function () {
            stop_camera_stream();
            dialog.hide();
        }
    });

    dialog.show();

    // Make dialog full screen on mobile
    if (window.innerWidth < 768) {
        dialog.$wrapper.find('.modal-dialog').css({
            'max-width': '100%',
            'margin': '0',
            'height': '100vh'
        });
    }

    // Wait for dialog to be rendered, then initialize camera
    setTimeout(() => {
        const container = dialog.fields_dict.camera_container.$wrapper;

        // Check if getUserMedia is supported
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            container.html(`
                <div style="text-align: center; padding: 40px;">
                    <div style="color: #d32f2f; font-size: 16px; margin-bottom: 20px;">
                        ⚠️ Camera not available
                    </div>
                    <p style="color: #666; font-size: 14px; line-height: 1.6;">
                        Camera access is not supported in this browser or requires HTTPS.<br><br>
                        <strong>Solutions:</strong><br>
                        • Access this page via HTTPS (https://...)<br>
                        • Use a modern browser (Chrome, Firefox, Safari, Edge)<br>
                        • Or use "Upload Photo" instead
                    </p>
                </div>
            `);

            // Hide primary action button
            dialog.get_primary_btn().hide();

            return;
        }

        container.html(`
            <div style="text-align: center;">
                <video id="camera-preview" autoplay playsinline style="max-width: 100%; max-height: 60vh; background: #000;"></video>
                <p style="margin-top: 10px; color: #888;">Position yourself in the frame and click Capture</p>
            </div>
        `);

        const video = container.find('video')[0];

        if (!video) {
            frappe.msgprint({
                title: __('Error'),
                message: __('Could not initialize video element'),
                indicator: 'red'
            });
            dialog.hide();
            return;
        }

        // Request camera access - use rear camera on mobile
        navigator.mediaDevices.getUserMedia({
            video: {
                facingMode: 'environment', // Rear camera
                width: { ideal: 1280 },
                height: { ideal: 1280 }
            },
            audio: false
        }).then(function (stream) {
            currentCameraStream = stream;
            video.srcObject = stream;

            // Play video explicitly (needed for some browsers)
            video.play().catch(function (playErr) {
                console.error('Error playing video:', playErr);
            });
        }).catch(function (err) {
            console.error('Camera access error:', err);

            let errorMsg = err.message;
            if (err.name === 'NotAllowedError') {
                errorMsg = 'Camera access denied. Please allow camera permission in your browser settings.';
            } else if (err.name === 'NotFoundError') {
                errorMsg = 'No camera found on this device.';
            } else if (err.name === 'NotReadableError') {
                errorMsg = 'Camera is already in use by another application.';
            }

            frappe.msgprint({
                title: __('Camera Error'),
                message: __(errorMsg),
                indicator: 'red'
            });
            dialog.hide();
        });
    }, 300);
}

// Stop camera stream
function stop_camera_stream() {
    if (currentCameraStream) {
        currentCameraStream.getTracks().forEach(track => track.stop());
        currentCameraStream = null;
    }
}

// Open file upload dialog
function open_file_upload_dialog(frm) {
    const $input = $('<input type="file" accept="image/*" style="display: none;">');

    $input.on('change', function (e) {
        const file = e.target.files[0];
        if (!file) return;

        // Check file size (max 5MB)
        const maxSize = 5 * 1024 * 1024; // 5MB
        if (file.size > maxSize) {
            frappe.msgprint({
                title: __('File Too Large'),
                message: __('Please select an image smaller than 5MB'),
                indicator: 'red'
            });
            return;
        }

        // Read file as data URL
        const reader = new FileReader();
        reader.onload = function (event) {
            show_crop_dialog(frm, event.target.result);
        };
        reader.readAsDataURL(file);
    });

    $input.trigger('click');
}

// Show crop dialog with remove background option
function show_crop_dialog(frm, imageDataUrl) {
    const dialog = new frappe.ui.Dialog({
        title: __('Crop Photo - Ratio 3:4'),
        size: 'large',
        fields: [
            {
                fieldtype: 'HTML',
                fieldname: 'cropper_container',
            },
            {
                fieldtype: 'Check',
                fieldname: 'remove_bg',
                label: __('Remove Background'),
                default: 0
            }
        ],
        primary_action_label: __('Save Photo'),
        primary_action: function () {
            const cropper = dialog.cropper_instance;
            const remove_bg = dialog.get_value('remove_bg');

            if (!cropper) {
                frappe.msgprint(__('Cropper not initialized'));
                return;
            }

            // Get cropped canvas at original size
            const canvas = cropper.getCroppedCanvas({
                maxWidth: 2400,
                maxHeight: 3200,
                imageSmoothingEnabled: true,
                imageSmoothingQuality: 'high',
            });

            // Convert to blob
            canvas.toBlob(function (blob) {
                const reader = new FileReader();
                reader.onloadend = function () {
                    const base64data = reader.result;

                    // Show processing message
                    frappe.show_alert({
                        message: __('Processing photo...'),
                        indicator: 'blue'
                    });

                    // Call backend to process photo
                    frappe.call({
                        method: 'customize_erpnext.api.employee.employee_utils.process_employee_photo',
                        args: {
                            employee_id: frm.doc.name,
                            employee_name: frm.doc.employee_name,
                            image_data: base64data,
                            remove_bg: remove_bg ? 1 : 0
                        },
                        callback: function (r) {
                            if (r.message && r.message.status === 'success') {
                                dialog.hide();

                                frappe.show_alert({
                                    message: __('Photo saved successfully. Refreshing...'),
                                    indicator: 'green'
                                });

                                // Reload the entire form to show the new image
                                setTimeout(() => {
                                    frm.reload_doc();
                                }, 500);
                            } else {
                                frappe.msgprint({
                                    title: __('Error'),
                                    message: __('Failed to save photo'),
                                    indicator: 'red'
                                });
                            }
                        },
                        error: function (err) {
                            frappe.msgprint({
                                title: __('Error'),
                                message: __('Error processing photo: {0}', [err.message || 'Unknown error']),
                                indicator: 'red'
                            });
                        }
                    });
                };
                reader.readAsDataURL(blob);
            }, 'image/jpeg', 0.92);
        },
        secondary_action_label: __('Cancel'),
    });

    dialog.show();

    // Make dialog responsive
    dialog.$wrapper.find('.modal-dialog').css('max-width', '90%');

    // Mobile full-screen
    if (window.innerWidth < 768) {
        dialog.$wrapper.find('.modal-dialog').css({
            'max-width': '100%',
            'margin': '0',
            'height': '100vh'
        });
    }

    setTimeout(() => {
        const container = dialog.fields_dict.cropper_container.$wrapper;
        container.html(`
            <div style="max-height: 60vh; overflow: hidden; position: relative;">
                <img id="image-to-crop" src="${imageDataUrl}" style="max-width: 100%; display: block;">
            </div>
            <div style="margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 5px;">
                <p style="margin: 0; color: #6c757d; font-size: 13px;">
                    <strong>Instructions:</strong>
                    Pinch to zoom, drag to move. Crop box is fixed at 3:4 ratio.
                </p>
            </div>
        `);

        const image = document.getElementById('image-to-crop');

        // Check if Cropper.js is available
        if (typeof Cropper === 'undefined') {
            frappe.msgprint({
                title: __('Library Not Loaded'),
                message: __('Cropper.js not loaded. Please refresh and try again.'),
                indicator: 'red'
            });
            dialog.hide();
            return;
        }

        // Initialize Cropper.js with 3:4 aspect ratio
        dialog.cropper_instance = new Cropper(image, {
            aspectRatio: 3 / 4,  // Fixed 3:4 ratio
            viewMode: 1,
            dragMode: 'move',
            autoCropArea: 0.85,
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
            zoomOnTouch: true,
            zoomOnWheel: true,
            wheelZoomRatio: 0.1,
        });
    }, 300);
}

