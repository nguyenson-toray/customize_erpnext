frappe.ui.form.on('Item Attribute', {
  refresh: function (frm) {
    // Thêm nút import trực tiếp
    frm.add_custom_button(__('Import Values'), function () {
      showImportDialog(frm);
    });
  }
});

// Hiển thị dialog để import các giá trị
function showImportDialog(frm) {
  const attributeName = frm.doc.attribute_name;

  const d = new frappe.ui.Dialog({
    title: __(`Import ${attributeName} Values`),
    fields: [
      {
        label: __('Paste Values (one per line)'),
        fieldname: 'values',
        fieldtype: 'Text',
        reqd: 1,
        description: __(`Each line will be imported as a new ${attributeName} value with auto-generated abbreviation.`)
      }
    ],
    primary_action_label: __('Import'),
    primary_action: function () {
      const values = d.get_value('values').split('\n').filter(v => v.trim() !== '');
      if (values.length === 0) {
        frappe.msgprint(__('No values to import.'));
        return;
      }
      d.hide();

      // Kiểm tra giá trị trùng lặp trước
      const existingValues = frm.doc.item_attribute_values || [];
      const existingValueSet = new Set(existingValues.map(v => v.attribute_value.toLowerCase()));
      const duplicates = values.filter(v => existingValueSet.has(v.trim().toLowerCase()));
      const newValues = values.filter(v => !existingValueSet.has(v.trim().toLowerCase()));

      if (duplicates.length > 0) {
        // Thông báo về giá trị trùng lặp
        frappe.show_alert({
          message: __(`${duplicates.length} duplicate values will be skipped.`),
          indicator: 'orange'
        }, 5);
      }

      if (newValues.length === 0) {
        frappe.msgprint({
          title: __('No New Values'),
          indicator: 'orange',
          message: __('All values already exist in the attribute.')
        });
        return;
      }

      // Bắt đầu nhập dữ liệu với timeout để tránh treo UI
      setTimeout(() => {
        importValuesWithProgress(frm, newValues);
      }, 300);
    }
  });

  d.show();
}

// Nhập dữ liệu với thanh tiến trình
function importValuesWithProgress(frm, values) {
  // Xác định mã viết tắt cuối cùng
  let lastAbbr = getLastAbbreviation(frm);

  // Hiển thị thanh tiến trình
  let importDialog = null;

  try {
    importDialog = frappe.msgprint({
      title: __('Importing Values'),
      indicator: 'blue',
      message: `<div class="progress">
              <div class="progress-bar" role="progressbar" 
                  style="width: 0%;" aria-valuenow="0" 
                  aria-valuemin="0" aria-valuemax="100">0%</div>
            </div>`,
      wide: true
    });

    // Xử lý từng giá trị
    let importedCount = 0;

    function processNext(index) {
      if (index >= values.length) {
        // Hoàn thành
        updateProgressBar(100);
        setTimeout(() => {
          if (importDialog) {
            importDialog.hide();
          }
          frappe.msgprint({
            title: __('Import Complete'),
            indicator: 'green',
            message: __(`Successfully imported ${importedCount} values.`)
          });
          frm.save();
        }, 500);
        return;
      }

      const value = values[index].trim();
      if (value === '') {
        processNext(index + 1);
        return;
      }

      // Tạo mã viết tắt mới
      lastAbbr = get_next_code(lastAbbr);

      // Thêm giá trị mới
      const child = frappe.model.add_child(frm.doc, 'Item Attribute Value', 'item_attribute_values');
      child.attribute_value = value;
      child.abbr = lastAbbr;

      importedCount++;
      frm.refresh_field('item_attribute_values');

      // Cập nhật thanh tiến trình
      const progress = Math.round(((index + 1) / values.length) * 100);
      updateProgressBar(progress);

      // Xử lý giá trị tiếp theo với timeout nhỏ
      setTimeout(() => {
        processNext(index + 1);
      }, 50);
    }

    // Bắt đầu xử lý
    processNext(0);

  } catch (error) {
    console.error("Import error:", error);
    if (importDialog) {
      importDialog.hide();
    }
    frappe.msgprint({
      title: __('Import Error'),
      indicator: 'red',
      message: __('An error occurred during import. Please try again.')
    });
  }

  // Hàm cập nhật thanh tiến trình
  function updateProgressBar(percent) {
    if (!importDialog) return;

    const bar = importDialog.$body.find('.progress-bar');
    if (bar.length) {
      bar.css('width', `${percent}%`);
      bar.attr('aria-valuenow', percent);
      bar.text(`${percent}%`);
    }
  }
}

// Lấy mã viết tắt cuối cùng dựa trên loại thuộc tính
function getLastAbbreviation(frm) {
  const existingValues = frm.doc.item_attribute_values || [];
  if (existingValues.length > 0) {
    return existingValues[existingValues.length - 1].abbr;
  }

  // Mã mặc định dựa trên loại thuộc tính
  const attributeName = frm.doc.attribute_name;

  if (attributeName === "Color" || attributeName === "Size" || attributeName === "Info") {
    return "000"; // 3-character code
  } else if (attributeName === "Brand" || attributeName === "Season") {
    return "00";  // 2-character code
  } else {
    return "000"; // Default 3-character code
  }
}

// Hàm tạo mã code tiếp theo
function get_next_code(max_code) {
  try {
    // Xác định độ dài mã
    const codeLength = max_code ? max_code.length : 3;

    // Nếu max_code rỗng hoặc không hợp lệ, trả về mã mặc định
    if (!max_code || (codeLength !== 2 && codeLength !== 3)) {
      return codeLength === 2 ? '00' : '000';
    }

    // Định nghĩa ký tự hợp lệ (0-9 và A-Z)
    const validChars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';

    // Chuyển đổi mã hiện tại thành mảng ký tự
    const codeChars = max_code.split('');

    // Bắt đầu từ ký tự ngoài cùng bên phải
    let position = codeLength - 1;
    let carry = true;

    // Xử lý từng ký tự từ phải sang trái
    while (position >= 0 && carry) {
      // Lấy ký tự hiện tại tại vị trí này
      const currentChar = codeChars[position];

      // Tìm index của nó trong chuỗi validChars
      const currentIndex = validChars.indexOf(currentChar);

      if (currentIndex === validChars.length - 1) {
        // Nếu là ký tự cuối cùng (Z), reset về đầu tiên (0) và nhớ
        codeChars[position] = '0';
        carry = true;
      } else {
        // Ngược lại, tăng lên ký tự tiếp theo và dừng nhớ
        codeChars[position] = validChars[currentIndex + 1];
        carry = false;
      }

      // Di chuyển đến vị trí bên trái tiếp theo
      position--;
    }

    // Nếu vẫn còn nhớ sau khi xử lý tất cả các vị trí,
    // chúng ta đã vượt quá mã tối đa có thể (ZZ hoặc ZZZ)
    if (carry) {
      console.warn('Warning: Code sequence overflow, returning to ' + '0'.repeat(codeLength));
      return '0'.repeat(codeLength);
    }

    // Nối các ký tự lại thành một chuỗi
    return codeChars.join('');
  } catch (error) {
    console.error('Error generating next code:', error);
    // Fallback là mã mặc định trong trường hợp lỗi
    return max_code && max_code.length === 2 ? '00' : '000';
  }
}

// Thêm hàm để hỗ trợ import CSV
frappe.ui.form.on('Data Import', {
  refresh: function (frm) {
    // Chỉ áp dụng cho Item Attribute imports
    if (frm.doc.reference_doctype === "Item Attribute") {
      // Thêm thông báo để thông báo về tự động tạo abbreviations
      frm.add_custom_button(__('How Abbreviations Work'), function () {
        frappe.msgprint({
          title: __('Auto-generate Abbreviations'),
          indicator: 'green',
          message: __(`
                      <p>Khi nhập dữ liệu Item Attribute từ CSV:</p>
                      <ul>
                          <li>CSV chỉ cần chứa: <strong>Attribute Name</strong> (Color, Size...) và <strong>Attribute Value</strong> (giá trị)</li>
                          <li>Mã viết tắt (Abbreviation) sẽ tự động được tạo</li>
                          <li>Định dạng mã: 3 ký tự cho Color, Size, Info và 2 ký tự cho Brand, Season</li>
                          <li>Hệ thống sẽ tiếp tục từ mã cuối cùng hiện có</li>
                      </ul>
                  `)
        });
      }, __("Import"));
    }
  }
});