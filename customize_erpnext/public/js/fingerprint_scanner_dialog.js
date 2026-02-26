/**
 * Fingerprint Scanner Dialog - Shared Module
 * Can be used from Employee Form and Employee List
 */

window.FingerprintScannerDialog = {

    // Desktop Bridge API Configuration
    DESKTOP_BRIDGE_URL: 'http://127.0.0.1:8080/api',

    // Vietnamese error messages mapping from bridge ERROR_CODES
    VIETNAMESE_ERROR_CODES: {
        // Connection errors (1xxx)
        1001: "Không tìm thấy tệp DLL máy quét",
        1002: "Khởi tạo SDK thất bại",
        1003: "Không tìm thấy thiết bị máy quét",
        1004: "Mở thiết bị thất bại",
        1005: "Khởi tạo bộ nhớ đệm thất bại",
        1006: "Máy quét đã ngắt kết nối",

        // Scan errors (2xxx)
        2001: "Hết thời gian chờ quét",
        2002: "Lỗi quét vân tay",
        2003: "Chất lượng vân tay thấp",
        2004: "Mẫu vân tay không hợp lệ",

        // Process errors (3xxx)
        3001: "Ghép mẫu vân tay thất bại",
        3002: "Tràn bộ đệm",
        3003: "Chỉ số ngón tay không hợp lệ",

        // Success codes (1-4)
        1: "Đã kết nối",
        2: "Quét thành công",
        3: "Hoàn tất đăng ký vân tay",
        4: "Đã ngắt kết nối"
    },

    // Function to translate error messages
    translateErrorMessage: function (message) {
        if (!message) return message;

        // Check for error codes in message
        for (const [code, translation] of Object.entries(FingerprintScannerDialog.VIETNAMESE_ERROR_CODES)) {
            if (message.includes(code)) {
                return translation;
            }
        }

        // Check for common English phrases and translate
        const translations = {
            'Scanner not connected': 'Máy quét chưa kết nối',
            'Timeout': 'Hết thời gian chờ',
            'Connection failed': 'Kết nối thất bại',
            'Initialization failed': 'Khởi tạo thất bại',
            'Scan failed': 'Quét thất bại',
            'Network error': 'Lỗi mạng',
            'Device not found': 'Không tìm thấy thiết bị'
        };

        for (const [english, vietnamese] of Object.entries(translations)) {
            if (message.includes(english)) {
                return message.replace(english, vietnamese);
            }
        }

        return message;
    },

    // Function to translate bridge messages to Vietnamese
    translateBridgeMessage: function (message) {
        if (!message) return message;


        // Handle structured log messages from bridge - exact matching only
        if (message === 'S1/3:waiting') {
            return '🔵 LẦN 1: ĐANG ĐỢI QUÉT VÂN TAY';
        }
        if (message === 'S2/3:waiting') {
            return '🟡 LẦN 2: ĐANG ĐỢI QUÉT VÂN TAY';
        }
        if (message === 'S3/3:waiting') {
            return '🟠 LẦN 3: ĐANG ĐỢI QUÉT VÂN TAY';
        }
        // Skip raw success codes - bridge already provides detailed success messages
        // if ((message.includes('S1/3:2') && !message.includes('S1/3:2001')) ||
        //     (message.includes('S2/3:2') && !message.includes('S2/3:2001')) ||
        //     (message.includes('S3/3:2') && !message.includes('S3/3:2001'))) {
        //     return '✅ QUÉT THÀNH CÔNG!';
        // }
        if (message.includes('S1/3:2001') || message.includes('S2/3:2001') || message.includes('S3/3:2001')) {
            return '❌ Hết thời gian chờ quét';
        }
        if (message.match(/E:[^:]+:[0-9]+:[0-9]+:3$/) || message.includes('ENROLLMENT_COMPLETE')) {
            return '✅ HOÀN TẤT ĐĂNG KÝ VÂN TAY';
        }

        // Direct translations
        const bridgeTranslations = {
            'Ready for scan': 'Sẵn sàng quét',
            'Please place finger on scanner': 'Vui lòng đặt ngón tay lên máy quét',
            'Scan completed': 'Quét hoàn tất',
            'Quality': 'Chất lượng',
            'ENROLLMENT COMPLETED': 'HOÀN TẤT ĐĂNG KÝ',
            'Fingerprint enrollment completed': 'Hoàn tất đăng ký vân tay',
            'Waiting for fingerprint': 'Đang chờ vân tay',
            'MERGE:START': 'Bắt đầu ghép mẫu vân tay',
            'Next scan ready': 'Sẵn sàng cho lần quét tiếp theo'
        };

        for (const [english, vietnamese] of Object.entries(bridgeTranslations)) {
            if (message.includes(english)) {
                message = message.replace(english, vietnamese);
            }
        }

        return message;
    },

    // Global variables for tracking
    scan_dialog: null,
    scan_count: 0,

    /**
     * Show fingerprint scanner dialog for Employee Form (fixed employee)
     * @param {string} employee_id - Required employee ID (cannot be changed)
     * @param {string} employee_name - Employee name for display
     */
    showForEmployee: function (employee_id, employee_name = null) {
        // BUGFIX: Clean up old dialog completely before creating new one
        if (FingerprintScannerDialog.scan_dialog) {
            try {
                FingerprintScannerDialog.scan_dialog.hide();
                FingerprintScannerDialog.scan_dialog.$wrapper.remove();
            } catch (e) {
                console.log('Error cleaning old dialog:', e);
            }
        }

        // Reset all global state
        FingerprintScannerDialog.scan_dialog = null;
        FingerprintScannerDialog.scan_count = 0;
        if (FingerprintScannerDialog.scan_attempts) {
            FingerprintScannerDialog.scan_attempts = {};
        }

        // Small delay to ensure DOM cleanup is complete
        setTimeout(() => {
            FingerprintScannerDialog._createDialog(employee_id, employee_name);
        }, 100);
    },

    _createDialog: function (employee_id, employee_name) {
        let d = new frappe.ui.Dialog({
            title: __('🔍 Fingerprint Scanner - {0} {1}', [employee_id, employee_name]),
            fields: [
                {
                    fieldname: 'left_column',
                    fieldtype: 'Column Break',
                    label: ''
                },
                {
                    fieldname: 'finger_selection_visual',
                    fieldtype: 'HTML',
                    options: `
                        <style>
                            .finger-selection-container {
                                padding: 25px;
                                background: #ffffff;
                                border-radius: 12px;
                                height: 100%;
                                min-height: 600px;
                                border: 1px solid #dee2e6;
                            }
                            .finger-selection-title {
                                text-align: center;
                                font-size: 1.5rem;
                                font-weight: bold;
                                color: #2c3e50;
                                margin-bottom: 25px;
                            }
                            .finger-visual-container {
                                position: relative;
                                width: 100%;
                                max-width: 500px;
                                aspect-ratio: 3 / 2;
                                margin: 0 auto;
                            }
                            .finger-visual-container svg {
                                display: block;
                                width: 100%;
                                height: 100%;
                            }
                            .finger-btn {
                                position: absolute;
                                z-index: 2;
                                transform: translate(-50%, -50%);
                                background: #e0e0e0;
                                border-radius: 100px;
                                padding: 13px;
                                border: none;
                                cursor: pointer;
                                transition: all 0.3s ease-in-out;
                            }
                            .finger-btn:hover {
                                background: #bdbdbd;
                            }
                            .finger-btn.selected {
                                background: #ff9800;
                                box-shadow: 0 0 0 4px rgba(255, 152, 0, 0.4);
                                animation: pulse 1.5s infinite;
                            }
                            .finger-btn.enrolled {
                                background: #4caf50;
                                border-color: #2e7d32;
                            }
                            @keyframes pulse {
                                0%, 100% { box-shadow: 0 0 0 4px rgba(255, 152, 0, 0.4); }
                                50% { box-shadow: 0 0 0 8px rgba(255, 152, 0, 0.2); }
                            }
                            .finger-1  { top: 23%; left: 5%; }
                            .finger-2  { top: 7%;  left: 14%; }
                            .finger-3  { top: 4%;  left: 25.5%; }
                            .finger-4  { top: 10%; left: 33.5%; }
                            .finger-5  { top: 48%; left: 44%; }
                            .finger-6  { top: 48%; left: 56%; }
                            .finger-7  { top: 10%; left: 66.5%; }
                            .finger-8  { top: 4%;  left: 74.5%; }
                            .finger-9  { top: 7%;  left: 86%; }
                            .finger-10 { top: 23%; left: 95%; }
                            .selected-finger-display {
                                text-align: center;
                                margin-top: 25px;
                                padding: 15px;
                                background: white;
                                border-radius: 8px;
                                font-size: 1.2rem;
                                font-weight: bold;
                                color: #007bff;
                                min-height: 50px;
                            }
                        </style>
                        <div class="finger-selection-container">
                            <div class="finger-selection-title">👆 Chọn Ngón Tay Để Quét</div>
                            <div class="finger-visual-container">
                                <svg version="1.0" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 400">
                                    <g id="left-hand">
                                        <path fill="#F4C5B0" d="M159,374.3l-0.9-72.9c0,0,24.7-11.3,37.5-34.4c12.8-23.1,43.7-50.3,50.9-52.9c0,0,12-7.5,17-8c5-0.5,15.1,1,17-3.6c1.9-4.6-2.4-18-27.9-15.4c-25.5,2.6-33.6,13.4-43.8,14.6c-10.3,1.2-15.9-5.1-17.2-10.8c-1.4-5.6,0.9-33.7,1.9-41.2c1-7.4,10.5-38.3,14.4-55c3.9-16.7,10-47,2.6-55s-15.2,1-17.5,8c-2.3,6.9-10.3,35.4-13.6,42.9c-3.3,7.4-10.3,39.6-12.1,42.4c-1.8,2.8-4.4,8-9.5,4.6c-5.1-3.3,4.9-34.7,4.4-51.1s2.1-32.4,3.6-47.3c1.5-14.9-4.6-24.7-12.6-24.7s-12.1,9.5-14.1,26.2c-2.1,16.7-7.2,47.3-8.5,55.2c-1.3,8-1.8,32.6-5.9,36.7c-4.1,4.1-10.3,4.6-12.8-4.6c-2.6-9.2-2.6-29-6.2-41.9S97.2,43.8,97.2,43c0-0.8-1.3-14.6-12.3-14.4c-11,0.3-11.6,14.6-10,31.3c1.5,16.7,2.3,41.3,4.1,47.8c1.8,6.4,3.6,34.2,2.8,37c-0.8,2.8-9.2,10.3-17-3.9c-7.7-14.1-27.7-49.3-33.6-49.6c-5.9-0.3-9.8,2.1-10.3,11c-0.5,9,21.1,47.8,23.9,52.6c2.8,4.9,13.1,24.9,15.2,34c2.1,9.1-3.7,35.5-3.4,52.8c0.5,27.8,15.6,31.7,14.2,40.7c-0.5,3-2.7,91.8-2.7,91.8H159z"/>
                                    </g>
                                    <g id="right-hand">
                                        <path fill="#F4C5B0" d="M441,374.3l0.9-72.9c0,0-24.7-11.3-37.5-34.4c-12.8-23.1-43.7-50.3-50.9-52.9c0,0-12-7.5-17-8c-5-0.5-15.1,1-17-3.6c-1.9-4.6,2.4-18,27.9-15.4c25.5,2.6,33.6,13.4,43.8,14.6c10.3,1.2,15.9-5.1,17.2-10.8c1.4-5.6-0.9-33.7-1.9-41.2c-1-7.4-10.5-38.3-14.4-55s-10-47-2.6-55c7.4-8,15.2,1,17.5,8c2.3,6.9,10.3,35.4,13.6,42.9c3.3,7.4,10.3,39.6,12.1,42.4c1.8,2.8,4.4,8,9.5,4.6c5.1-3.3-4.9-34.7-4.4-51.1S436,54,434.5,39.2c-1.5-14.9,4.6-24.7,12.6-24.7c8,0,12.1,9.5,14.1,26.2c2.1,16.7,7.2,47.3,8.5,55.2c1.3,8,1.8,32.6,5.9,36.7c4.1,4.1,10.3,4.6,12.8-4.6c2.6-9.2,2.6-29,6.2-41.9c3.6-12.8,8.2-42.4,8.2-43.1c0-0.8,1.3-14.6,12.3-14.4c11,0.3,11.6,14.6,10,31.3c-1.5,16.7-2.3,41.3-4.1,47.8s-3.6,34.2-2.8,37c0.8,2.8,9.2,10.3,17-3.9c7.7-14.1,27.7-49.3,33.6-49.6c5.9-0.3,9.8,2.1,10.3,11c0.5,9-21.1,47.8-23.9,52.6c-2.8,4.9-13.1,24.9-15.2,34c-2.1,9.1,3.7,35.5,3.4,52.8c-0.5,27.8-15.6,31.7-14.2,40.7c0.5,3,2.7,91.8,2.7,91.8H441z"/>
                                    </g>
                                </svg>
                                <button type="button" class="finger-btn finger-1" data-finger="0" data-finger-name="Ngón út trái" title="Ngón út trái"></button>
                                <button type="button" class="finger-btn finger-2" data-finger="1" data-finger-name="Ngón áp út trái" title="Ngón áp út trái"></button>
                                <button type="button" class="finger-btn finger-3" data-finger="2" data-finger-name="Ngón giữa trái" title="Ngón giữa trái"></button>
                                <button type="button" class="finger-btn finger-4" data-finger="3" data-finger-name="Ngón trỏ trái" title="Ngón trỏ trái"></button>
                                <button type="button" class="finger-btn finger-5" data-finger="4" data-finger-name="Ngón cái trái" title="Ngón cái trái"></button>
                                <button type="button" class="finger-btn finger-6" data-finger="5" data-finger-name="Ngón cái phải" title="Ngón cái phải"></button>
                                <button type="button" class="finger-btn finger-7" data-finger="6" data-finger-name="Ngón trỏ phải" title="Ngón trỏ phải"></button>
                                <button type="button" class="finger-btn finger-8" data-finger="7" data-finger-name="Ngón giữa phải" title="Ngón giữa phải"></button>
                                <button type="button" class="finger-btn finger-9" data-finger="8" data-finger-name="Ngón áp út phải" title="Ngón áp út phải"></button>
                                <button type="button" class="finger-btn finger-10" data-finger="9" data-finger-name="Ngón út phải" title="Ngón út phải"></button>
                            </div>
                            <div id="selected-finger-display" class="selected-finger-display">
                                Vui lòng chọn ngón tay từ hình trên
                            </div>
                            <input type="hidden" id="finger_selection_value" value="">
                        </div>
                    `
                },
                {
                    fieldname: 'right_column',
                    fieldtype: 'Column Break',
                    label: ''
                },
                {
                    fieldname: 'scan_status',
                    fieldtype: 'HTML',
                    options: '<div id="scan-status-container" style="background: #fff; border: 2px solid #e9ecef; border-radius: 8px; padding: 20px; margin-bottom: 20px;"><div class="d-flex align-items-center mb-3"><i class="fa fa-desktop" style="font-size: 22px; color: #007bff; margin-right: 10px;"></i><h5 class="mb-0">Scanner Activity</h5></div><div id="scan-status" style="height: 320px; overflow-y: auto; padding: 15px; border-radius: 6px; background: #f8f9fa; font-family: Monaco, Menlo, monospace; font-size: 13px; line-height: 1.4;"><div class="log-entry text-info"><strong>[' + new Date().toLocaleTimeString() + ']</strong> 🟢 Ready to scan fingerprints</div></div></div>'
                },
                {
                    fieldname: 'scan_history',
                    fieldtype: 'HTML',
                    options: '<div id="scan-history-container" style="background: #fff; border: 2px solid #dee2e6; border-radius: 8px; padding: 20px;"><div class="d-flex align-items-center justify-content-between mb-3"><div class="d-flex align-items-center"><i class="fa fa-history" style="font-size: 20px; color: #28a745; margin-right: 10px;"></i><h5 class="mb-0">Recent Activity</h5></div><small class="text-muted">Last 10 scans</small></div><div id="scan-list" style="max-height: 200px; overflow-y: auto;"><div class="text-center text-muted py-3"><i class="fa fa-clock-o"></i> No scans yet</div></div></div>'
                }
            ],
            primary_action_label: __('🔍 Bắt Đầu Quét'),
            primary_action(values) {
                // Get finger selection from visual selector
                const fingerSelectionValue = d.$wrapper.find('#finger_selection_value').val();

                if (!fingerSelectionValue) {
                    frappe.msgprint({
                        title: __('⚠️ Thiếu Thông Tin'),
                        message: __('Vui lòng chọn ngón tay từ hình trên trước khi quét.'),
                        indicator: 'orange'
                    });
                    return;
                }

                // Parse finger selection (format: "index|name")
                const [fingerIndex, fingerName] = fingerSelectionValue.split('|');

                // Create values object with fixed employee
                const scanValues = {
                    employee: employee_id,
                    finger_selection: fingerName,
                    finger_index: parseInt(fingerIndex)
                };
                FingerprintScannerDialog.startFingerprintCapture(scanValues, d);
            },
            secondary_action_label: __('🔄 Đặt Lại'),
            secondary_action() {
                // Clear visual finger selection
                d.$wrapper.find('.finger-btn').removeClass('selected');
                d.$wrapper.find('#selected-finger-display').html('Vui lòng chọn ngón tay từ hình trên').css('color', '#007bff');
                d.$wrapper.find('#finger_selection_value').val('');

                FingerprintScannerDialog.updateScanStatus('<div style="text-align: center; font-size: 1.2em; font-weight: bold; color: #007bff; margin: 10px 0;">🔄 Đã xóa dữ liệu - Sẵn sàng quét mới</div>', 'info');

                // Re-initialize finger selection to reload enrolled status
                setTimeout(() => {
                    FingerprintScannerDialog.initializeFingerSelection(d, employee_id);
                }, 100);
            }
        });

        // BUGFIX: Add cleanup on dialog close
        d.$wrapper.on('hidden.bs.modal', function () {
            // Clean up all references when dialog is closed
            FingerprintScannerDialog.scan_dialog = null;
            FingerprintScannerDialog.scan_count = 0;
            if (FingerprintScannerDialog.scan_attempts) {
                FingerprintScannerDialog.scan_attempts = {};
            }
        });

        d.show();

        // Initialize finger selection UI
        setTimeout(() => {
            FingerprintScannerDialog.initializeFingerSelection(d, employee_id);
        }, 200);

        // Make dialog larger and add custom styling
        d.$wrapper.find('.modal-dialog').addClass('modal-xl');
        d.$wrapper.find('.modal-content').css({
            'border-radius': '12px',
            'box-shadow': '0 10px 30px rgba(0,0,0,0.2)'
        });
        d.$wrapper.find('.modal-header').css({
            'background': 'linear-gradient(135deg, #007bff 0%, #0056b3 100%)',
            'color': 'white',
            'border-bottom': 'none',
            'border-radius': '12px 12px 0 0'
        });

        // Initialize scan status
        FingerprintScannerDialog.scan_dialog = d;
        FingerprintScannerDialog.scan_count = 0;

        // Store the fixed employee ID in the dialog for use in reset function
        d.employee_id = employee_id;

    },

    startFingerprintCapture: function (values, dialog) {
        // Get finger index from values (already parsed from visual selector)
        const finger_index = values.finger_index;

        // Initialize scan attempt counter if not exists
        if (!FingerprintScannerDialog.scan_attempts) {
            FingerprintScannerDialog.scan_attempts = {};
        }

        // Reset attempt counter for this finger
        const attempt_key = `${values.employee}_${finger_index}`;
        FingerprintScannerDialog.scan_attempts[attempt_key] = 0;

        // Keep dialog open but disable scan button during process
        dialog.set_primary_action(__('Đang Quét...'), null);
        dialog.disable_primary_action();

        // Update status in dialog with scan attempt indicator
        FingerprintScannerDialog.updateScanStatus('<div style="text-align: center; font-size: 1.5em; font-weight: bold; color: #007bff; margin: 10px 0;">🔍 Bắt đầu quét vân tay...</div>', 'info');
        FingerprintScannerDialog.updateScanStatus('📡 Kiểm tra kết nối app Fingerprint Scanner...', 'info');
        FingerprintScannerDialog.updateScanStatus('<div style="text-align: center; font-size: 1.2em; font-weight: bold; color: #28a745; margin: 8px 0;">📋 Quy trình: LẦN 1 → LẦN 2 → LẦN 3 → Ghép → Hoàn tất</div>', 'info');

        // Step 1: Check desktop bridge availability
        FingerprintScannerDialog.checkDesktopBridgeStatus(function (bridgeAvailable) {
            if (!bridgeAvailable) {
                FingerprintScannerDialog.updateScanStatus('<div style="text-align: center; font-size: 1.3em; font-weight: bold; color: #dc3545; margin: 10px 0;">❌ Kết nối app Fingerprint Scanner thất bại!</div>', 'danger');
                FingerprintScannerDialog.updateScanStatus('Vui lòng kiểm tra kết nối USB của máy quét & khởi động lại app Fingerprint Scanner.', 'danger');
                FingerprintScannerDialog.resetScanButton(dialog);
                return;
            }

            FingerprintScannerDialog.updateScanStatus('✅ Đã kết nối app Fingerprint Scanner. Đang khởi tạo máy quét...', 'success');

            // Step 2: Initialize scanner via desktop bridge
            FingerprintScannerDialog.initializeScannerViaBridge(function (success, message) {
                if (success) {
                    FingerprintScannerDialog.updateScanStatus(__('🔍 Máy quét sẵn sàng ! Bắt đầu quét ...'), 'success');

                    // Step 3: Capture fingerprint
                    setTimeout(() => {
                        FingerprintScannerDialog.captureFingerprintData(values.employee, finger_index, values.finger_selection, dialog);
                    }, 500);

                } else {
                    FingerprintScannerDialog.updateScanStatus(__('❌ Khởi tạo máy quét thất bại: ' + message), 'danger');
                    FingerprintScannerDialog.resetScanButton(dialog);
                }
            });
        });
    },

    captureFingerprintData: function (employee_id, finger_index, finger_name, dialog) {
        FingerprintScannerDialog.updateScanStatus(__('🔄 Starting fingerprint enrollment process...'), 'info');

        // Use direct enrollment via bridge (single API call with real-time updates)
        FingerprintScannerDialog.captureFingerprintViaBridge(employee_id, finger_index, function (success, data, message) {
            if (success) {
                const final_template_data = data.template_data;
                const final_template_size = data.template_size;
                const quality_score = data.quality_score || data.quality || 0; // Try different property names re, data_keys: Object.keys(data) });

                FingerprintScannerDialog.updateScanStatus(`✅ Fingerprint enrollment completed! (${final_template_size} bytes, Quality: ${quality_score})`, 'success');

                // Save to ERPNext database   
                FingerprintScannerDialog.saveFingerprintToERPNext(employee_id, finger_index, final_template_data, quality_score, function (saveSuccess, fingerprintId) {
                    if (saveSuccess) {
                        FingerprintScannerDialog.updateScanStatus(__('💾 Fingerprint saved to database successfully'), 'success');
                        FingerprintScannerDialog.addScanToHistory(employee_id, finger_name, final_template_size, 'success');

                        setTimeout(() => {
                            // Clear visual finger selection
                            dialog.$wrapper.find('.finger-btn').removeClass('selected');
                            dialog.$wrapper.find('#selected-finger-display').html('Vui lòng chọn ngón tay từ hình trên').css('color', '#007bff');
                            dialog.$wrapper.find('#finger_selection_value').val('');

                            FingerprintScannerDialog.updateScanStatus('<div style="text-align: center; font-size: 1.2em; font-weight: bold; color: #28a745; margin: 10px 0;">🟢 Sẵn sàng quét vân tay tiếp theo</div>', 'info');
                            FingerprintScannerDialog.resetScanButton(dialog);

                            // Re-initialize finger selection to update enrolled status
                            setTimeout(() => {
                                FingerprintScannerDialog.initializeFingerSelection(dialog, employee_id);
                            }, 100);
                        }, 1000);  // Optimized delay for faster workflow
                    } else {
                        FingerprintScannerDialog.updateScanStatus('<div style="text-align: center; font-size: 1.2em; font-weight: bold; color: #dc3545; margin: 10px 0;">❌ Lưu vào cơ sở dữ liệu thất bại</div>', 'danger');
                        FingerprintScannerDialog.addScanToHistory(employee_id, finger_name, 0, 'failed');
                        FingerprintScannerDialog.resetScanButton(dialog);
                    }
                    FingerprintScannerDialog.disconnectScannerViaBridge();
                });
            } else {
                FingerprintScannerDialog.updateScanStatus(`<div style="text-align: center; font-size: 1.2em; font-weight: bold; color: #dc3545; margin: 10px 0;">❌ ĐĂNG KÝ VÂN TAY THẤT BẠI</div>`, 'danger');
                FingerprintScannerDialog.updateScanStatus(`Chi tiết lỗi: ${FingerprintScannerDialog.translateErrorMessage(message)}`, 'danger');
                FingerprintScannerDialog.addScanToHistory(employee_id, finger_name, 0, 'failed');
                FingerprintScannerDialog.resetScanButton(dialog);
                FingerprintScannerDialog.disconnectScannerViaBridge();
            }
        });
    },

    updateScanStatus: function (message, type = 'info') {
        // BUGFIX: Use dialog-scoped selector instead of document.getElementById
        let statusDiv = null;
        if (FingerprintScannerDialog.scan_dialog && FingerprintScannerDialog.scan_dialog.$wrapper) {
            statusDiv = FingerprintScannerDialog.scan_dialog.$wrapper.find('#scan-status')[0];
        }

        if (statusDiv && message !== '') {
            const timestamp = new Date().toLocaleTimeString();
            let textClass = 'text-info';
            let icon = '🔵';

            if (type === 'success') {
                textClass = 'text-success';
                icon = '✅';
            } else if (type === 'danger') {
                textClass = 'text-danger';
                icon = '❌';
            } else if (type === 'warning') {
                textClass = 'text-warning';
                icon = '⚠️';
            }

            // Check if message contains HTML (attempt number display)
            let logEntry;
            if (message.includes('<div style=')) {
                // Special handling for HTML content (attempt display)
                logEntry = `<div class="log-entry mb-1">${message}</div>`;
            } else {
                // Regular text message
                logEntry = `<div class="log-entry ${textClass} mb-1"><strong>[${timestamp}]</strong> ${icon} ${message}</div>`;
            }

            statusDiv.innerHTML += logEntry;

            // Keep only last 15 log entries
            const logEntries = statusDiv.querySelectorAll('.log-entry');
            if (logEntries.length > 15) {
                logEntries[0].remove();
            }

            // Scroll to bottom with smooth animation
            statusDiv.scrollTo({
                top: statusDiv.scrollHeight,
                behavior: 'smooth'
            });
        }
    },

    resetScanButton: function (dialog) {
        dialog.set_primary_action(__('🔍 Bắt Đầu Quét'), function (values) {
            // Get finger selection from visual selector
            const fingerSelectionValue = dialog.$wrapper.find('#finger_selection_value').val();

            if (!fingerSelectionValue) {
                frappe.msgprint({
                    title: __('⚠️ Thiếu Thông Tin'),
                    message: __('Vui lòng chọn ngón tay từ hình trên trước khi quét.'),
                    indicator: 'orange'
                });
                return;
            }

            // Parse finger selection (format: "index|name")
            const [fingerIndex, fingerName] = fingerSelectionValue.split('|');

            // Create values object with fixed employee from dialog
            const scanValues = {
                employee: dialog.employee_id,
                finger_selection: fingerName,
                finger_index: parseInt(fingerIndex)
            };

            // Reset attempt counter when starting fresh scan
            if (FingerprintScannerDialog.scan_attempts && scanValues.employee) {
                const attempt_key = `${scanValues.employee}_${scanValues.finger_index}`;
                FingerprintScannerDialog.scan_attempts[attempt_key] = 0;
            }
            FingerprintScannerDialog.startFingerprintCapture(scanValues, dialog);
        });
        dialog.enable_primary_action();
    },

    addScanToHistory: function (employee_id, finger_name, template_size, status) {
        FingerprintScannerDialog.scan_count++;

        // BUGFIX: Use dialog-scoped selector instead of document.getElementById
        let scanList = null;
        if (FingerprintScannerDialog.scan_dialog && FingerprintScannerDialog.scan_dialog.$wrapper) {
            scanList = FingerprintScannerDialog.scan_dialog.$wrapper.find('#scan-list')[0];
        }

        if (scanList) {
            // Clear "No scans yet" message
            if (FingerprintScannerDialog.scan_count === 1) {
                scanList.innerHTML = '';
            }

            const timestamp = new Date().toLocaleTimeString();
            let statusIcon = '';
            let statusClass = '';
            let bgClass = '';

            if (status === 'success') {
                statusIcon = '✅';
                statusClass = 'text-success';
                bgClass = 'alert-success';
            } else if (status === 'warning') {
                statusIcon = '⚠️';
                statusClass = 'text-warning';
                bgClass = 'alert-warning';
            } else {
                statusIcon = '❌';
                statusClass = 'text-danger';
                bgClass = 'alert-danger';
            }

            const scanEntry = `
                <div class="scan-entry ${bgClass} border-0 rounded p-2 mb-2" style="background-color: rgba(var(--bs-${status === 'success' ? 'success' : status === 'warning' ? 'warning' : 'danger'}-rgb), 0.1);">
                    <div class="d-flex justify-content-between align-items-center">
                        <div class="d-flex align-items-center">
                            <span class="badge badge-primary me-2">#${FingerprintScannerDialog.scan_count}</span>
                            <small><strong>${employee_id}</strong> - ${finger_name}</small>
                        </div>
                        <small class="${statusClass}">${statusIcon} ${status.toUpperCase()}</small>
                    </div>
                    <div class="d-flex justify-content-between mt-1">
                        <small class="text-muted">${timestamp}</small>
                        ${template_size > 0 ? `<small class="text-muted">${template_size} bytes</small>` : ''}
                    </div>
                </div>
            `;

            scanList.innerHTML = scanEntry + scanList.innerHTML;

            // Keep only last 8 scans
            const entries = scanList.querySelectorAll('.scan-entry');
            if (entries.length > 8) {
                entries[entries.length - 1].remove();
            }
        }
    },

    // Desktop Bridge API Functions
    checkDesktopBridgeStatus: function (callback) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);  // Optimized for faster response

        fetch(`${FingerprintScannerDialog.DESKTOP_BRIDGE_URL}/test`, {
            method: 'GET',
            signal: controller.signal
        })
            .then(response => {
                clearTimeout(timeoutId);
                return response.json();
            })
            .then(data => {
                callback(data.success);
            })
            .catch(error => {
                clearTimeout(timeoutId);
                console.error('Desktop bridge not available:', error);

                // No popup dialog - error is already shown in Scanner Activity
                callback(false);
            });
    },

    initializeScannerViaBridge: function (callback) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 6000);  // Optimized timeout

        fetch(`${FingerprintScannerDialog.DESKTOP_BRIDGE_URL}/scanner/initialize`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            signal: controller.signal
        })
            .then(response => {
                clearTimeout(timeoutId);
                return response.json();
            })
            .then(data => {
                callback(data.success, data.message);
            })
            .catch(error => {
                clearTimeout(timeoutId);
                console.error('Error initializing scanner:', error);
                callback(false, 'Scanner initialization timeout or network error');
            });
    },

    captureFingerprintViaBridge: function (employee_id, finger_index, callback) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000);  // Increased timeout for reliability

        // Start polling logs for real-time updates BEFORE making the capture request
        const pollInterval = FingerprintScannerDialog.startLogPolling();

        // Very small delay to ensure polling is active before bridge starts logging
        setTimeout(() => {
            fetch(`${FingerprintScannerDialog.DESKTOP_BRIDGE_URL}/fingerprint/capture`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    employee_id: employee_id,
                    finger_index: finger_index
                }),
                signal: controller.signal
            })
                .then(response => {
                    clearTimeout(timeoutId);
                    return response.json();
                })
                .then(data => {
                    // Small delay to catch any final logs before stopping polling
                    setTimeout(() => {
                        FingerprintScannerDialog.stopLogPolling(pollInterval);
                    }, 500);
                    callback(data.success, data, data.message);
                })
                .catch(error => {
                    clearTimeout(timeoutId);
                    console.error('Error capturing fingerprint:', error);
                    // Stop polling on error
                    FingerprintScannerDialog.stopLogPolling(pollInterval);
                    callback(false, null, 'Fingerprint capture timeout or network error');
                });
        }, 50);  // Reduced delay to catch early logs
    },

    startLogPolling: function () {
        // Start polling from 1 second ago to catch early logs
        let startTime = new Date();
        startTime.setSeconds(startTime.getSeconds() - 1);
        let lastTimestamp = startTime.toTimeString().substring(0, 8);

        const pollLogs = () => {
            fetch(`${FingerprintScannerDialog.DESKTOP_BRIDGE_URL}/logs/since?since=${lastTimestamp}`)
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.logs && data.logs.length > 0) {
                        data.logs.forEach(log => {
                            // Display bridge logs in Scanner Activity with Vietnamese translation
                            // Show only essential user-facing messages
                            if (log.message.includes('S1/3:waiting') || log.message.includes('S2/3:waiting') || log.message.includes('S3/3:waiting') ||
                                log.message.includes('MERGE') ||
                                log.message.includes('✅ LẦN') || log.message.includes('QUÉT THÀNH CÔNG') ||
                                log.message.includes('Sẵn sàng') || log.message.includes('nhấc tay') ||
                                (log.message.includes('Starting fingerprint') && log.message === '🔄 Starting fingerprint enrollment process...') ||
                                (log.message.includes('ENROLL:') && log.message.startsWith('ENROLL:') && !log.message.includes('ENROLL:START:') && !log.message.includes('ENROLL:OK:'))) {

                                let logType = 'info';
                                if (log.level === 'success') logType = 'success';
                                else if (log.level === 'error') logType = 'danger';
                                else if (log.level === 'warning') logType = 'warning';
                                else if (log.level === 'in_progress') logType = 'warning';
                                else if (log.level === 'waiting') logType = 'info';

                                // Translate bridge messages to Vietnamese
                                let displayMessage = FingerprintScannerDialog.translateBridgeMessage(log.message);

                                // Style important messages with larger fonts and backgrounds
                                if (displayMessage.includes('LẦN 1') || displayMessage.includes('LẦN 2') || displayMessage.includes('LẦN 3') || displayMessage.includes('ĐỢI QUÉT')) {
                                    displayMessage = `<div style="text-align: center; font-size: 1.8em; font-weight: bold; margin: 15px 0; padding: 10px; background: linear-gradient(135deg, #e3f2fd, #bbdefb); border-radius: 8px; color: #1976d2; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">${displayMessage}</div>`;
                                } else if (displayMessage.includes('THÀNH CÔNG') || displayMessage.includes('HOÀN TẤT')) {
                                    displayMessage = `<div style="text-align: center; font-size: 1.6em; font-weight: bold; margin: 15px 0; padding: 10px; background: linear-gradient(135deg, #e8f5e8, #c8e6c9); border-radius: 8px; color: #388e3c; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">${displayMessage}</div>`;
                                } else if (displayMessage.includes('SẴN SÀNG') || displayMessage.includes('máy quét')) {
                                    displayMessage = `<div style="text-align: center; font-size: 1.5em; font-weight: bold; margin: 12px 0; padding: 8px; background: linear-gradient(135deg, #fff3e0, #ffcc02); border-radius: 8px; color: #f57c00; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">${displayMessage}</div>`;
                                }

                                FingerprintScannerDialog.updateScanStatus(displayMessage, logType);
                            }
                            lastTimestamp = log.timestamp;
                        });
                    }
                })
                .catch(error => {
                    console.warn('Log polling error:', error);
                });
        };

        // Poll every 200ms during scan for more responsive updates
        return setInterval(pollLogs, 200);
    },

    stopLogPolling: function (intervalId) {
        if (intervalId) {
            clearInterval(intervalId);
        }
    },

    disconnectScannerViaBridge: function () {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 2000);

        fetch(`${FingerprintScannerDialog.DESKTOP_BRIDGE_URL}/scanner/disconnect`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            signal: controller.signal
        })
            .then(response => {
                clearTimeout(timeoutId);
                return response.json();
            })
            .then(data => {
                console.log('Scanner disconnected:', data.success);
            })
            .catch(error => {
                clearTimeout(timeoutId);
                console.error('Error disconnecting scanner:', error);
            });
    },

    saveFingerprintToERPNext: function (employee_id, finger_index, template_data, quality_score, callback) {
        // Handle optional quality_score parameter (backward compatibility)
        if (typeof quality_score === 'function') {
            callback = quality_score;
            quality_score = 0;
        }
        quality_score = quality_score || 0;

        console.log('saveFingerprintToERPNext called with:', { employee_id, finger_index, quality_score, template_data: template_data ? 'DATA_PRESENT' : 'NO_DATA' });

        if (!employee_id) {
            console.error('employee_id is missing!');
            frappe.msgprint({
                title: __('Error'),
                message: __('Employee ID is missing. Please refresh the page and try again.'),
                indicator: 'red'
            });
            if (callback) callback(false, null);
            return;
        }

        frappe.call({
            method: 'customize_erpnext.api.utilities.save_fingerprint_data',
            args: {
                employee_id: employee_id,
                finger_index: finger_index,
                template_data: template_data,
                quality_score: quality_score
            },
            callback: function (r) {
                if (r.message && r.message.success) {
                    callback(true, r.message.fingerprint_id);
                } else {
                    callback(false, null);
                }
            },
            error: function (r) {
                callback(false, null);
            }
        });
    },

    // Initialize visual finger selection interface
    initializeFingerSelection: function (dialog, employee_id) {
        const fingerBtns = dialog.$wrapper.find('.finger-btn');
        const selectedDisplay = dialog.$wrapper.find('#selected-finger-display');
        const hiddenInput = dialog.$wrapper.find('#finger_selection_value');

        // Check if already initialized (to avoid duplicate event handlers)
        const alreadyInitialized = fingerBtns.data('initialized');

        // Load enrolled fingers and mark them
        frappe.call({
            method: 'customize_erpnext.api.utilities.get_employee_fingerprints_status',
            args: { employee_id: employee_id },
            callback: function (r) {
                if (r.message && r.message.success) {
                    const enrolled = r.message.existing_fingers || [];
                    // First remove all enrolled classes
                    fingerBtns.removeClass('enrolled');
                    // Then add enrolled class to existing fingers
                    fingerBtns.each(function () {
                        const fingerIndex = parseInt($(this).attr('data-finger'));
                        if (enrolled.includes(fingerIndex)) {
                            $(this).addClass('enrolled');
                        }
                    });
                }
            }
        });

        // Only attach event handlers once
        if (!alreadyInitialized) {
            // Variable to prevent click when double-clicking
            let clickTimer = null;
            let preventClick = false;

            // Handle finger selection (single click with delay to check for double click)
            fingerBtns.on('click', function () {
                const $this = $(this);
                const fingerIndex = parseInt($this.attr('data-finger'));
                const fingerName = $this.attr('data-finger-name');

                // Clear previous timer
                clearTimeout(clickTimer);

                // Wait to see if this is a double click
                clickTimer = setTimeout(function () {
                    if (!preventClick) {
                        // This is a single click
                        // Remove selection from all buttons
                        fingerBtns.removeClass('selected');

                        // Add selection to clicked button
                        $this.addClass('selected');

                        // Update display
                        // ICON ARROW   ➡️➡️
                        // ICON FINGERPRINT
                        selectedDisplay.html(`✅ Đã chọn: <strong>${fingerName}</strong><br><small class="text-muted">Nhấn "Bắt Đầu Quét" để tiếp tục</small><br> <strong>KHI MÀN HÌNH HIỂN THỊ "ĐANG ĐỢI QUÉT VÂN TAY" ➡️ ĐẶT NGÓN TAY LÊN MÁY QUÉT 2S</strong><br> <strong>➡️SAU ĐÓ NHẤC NGÓN TAY LÊN</strong>`);
                        selectedDisplay.css('color', '#28a745');

                        // Store value in hidden input
                        hiddenInput.val(fingerIndex + '|' + fingerName);

                        // Check if finger is already enrolled
                        if ($this.hasClass('enrolled')) {
                            frappe.confirm(
                                `🔄 Ngón tay "${fingerName}" đã có dữ liệu vân tay. Bạn có muốn thay thế không?`,
                                function () {
                                    // User confirmed - keep selection
                                },
                                function () {
                                    // User cancelled - clear selection
                                    fingerBtns.removeClass('selected');
                                    selectedDisplay.html('Vui lòng chọn ngón tay từ hình trên');
                                    selectedDisplay.css('color', '#007bff');
                                    hiddenInput.val('');
                                }
                            );
                        }
                    }
                    preventClick = false;
                }, 250); // 250ms delay to detect double click
            });

            // Handle double click to delete enrolled fingerprint
            fingerBtns.on('dblclick', function (e) {
                e.preventDefault();
                preventClick = true; // Prevent the single click handler
                clearTimeout(clickTimer);

                const fingerIndex = parseInt($(this).attr('data-finger'));
                const fingerName = $(this).attr('data-finger-name');

                // Only allow delete if finger is enrolled
                if ($(this).hasClass('enrolled')) {
                    frappe.confirm(
                        `🗑️ Bạn có chắc chắn muốn xóa dữ liệu vân tay của <strong>${fingerName}</strong> không?<br><br><small class="text-danger">⚠️ Thao tác này không thể hoàn tác!</small>`,
                        function () {
                            // User confirmed - delete fingerprint
                            FingerprintScannerDialog.deleteFingerprint(employee_id, fingerIndex, fingerName, dialog);
                        },
                        function () {
                            // User cancelled - do nothing
                        }
                    );
                }
                // If not enrolled, do nothing (no message)
            });

            // Mark as initialized
            fingerBtns.data('initialized', true);

            // Initialize tooltips
            dialog.$wrapper.find('[title]').tooltip();
        }
    },

    // Delete fingerprint data
    deleteFingerprint: function (employee_id, finger_index, finger_name, dialog) {
        FingerprintScannerDialog.updateScanStatus(`🗑️ Đang xóa dữ liệu vân tay ${finger_name}...`, 'warning');

        frappe.call({
            method: 'customize_erpnext.api.utilities.delete_fingerprint_data',
            args: {
                employee_id: employee_id,
                finger_index: finger_index
            },
            callback: function (r) {
                if (r.message && r.message.success) {
                    FingerprintScannerDialog.updateScanStatus(`✅ Đã xóa dữ liệu vân tay ${finger_name} thành công`, 'success');
                    FingerprintScannerDialog.addScanToHistory(employee_id, finger_name + ' (Deleted)', 0, 'warning');

                    // Clear selection if this finger was selected
                    dialog.$wrapper.find('.finger-btn').removeClass('selected');
                    dialog.$wrapper.find('#selected-finger-display').html('Vui lòng chọn ngón tay từ hình trên').css('color', '#007bff');
                    dialog.$wrapper.find('#finger_selection_value').val('');

                    // Reload finger status to update UI
                    setTimeout(() => {
                        FingerprintScannerDialog.initializeFingerSelection(dialog, employee_id);
                    }, 500);

                    frappe.show_alert({
                        message: __(`✅ Đã xóa dữ liệu vân tay ${finger_name}`),
                        indicator: 'green'
                    }, 5);
                } else {
                    FingerprintScannerDialog.updateScanStatus(`❌ Xóa dữ liệu vân tay ${finger_name} thất bại`, 'danger');
                    frappe.msgprint({
                        title: __('❌ Lỗi'),
                        message: __('Không thể xóa dữ liệu vân tay. Vui lòng thử lại.'),
                        indicator: 'red'
                    });
                }
            },
            error: function (r) {
                FingerprintScannerDialog.updateScanStatus(`❌ Lỗi khi xóa dữ liệu vân tay ${finger_name}`, 'danger');
                frappe.msgprint({
                    title: __('❌ Lỗi'),
                    message: __('Đã xảy ra lỗi khi xóa dữ liệu vân tay.'),
                    indicator: 'red'
                });
            }
        });
    }
};

