/**
 * Converts a string to Proper Case (like Excel PROPER function)
 * Capitalizes first letter of each word, preserves spaces
 * Special handling: first non-number character is uppercase (e.g., "26ss" → "26Ss")
 * @param {String} str - The string to convert
 * @returns {String} The proper case string
 */
function toProperCase(str) {
  if (!str) return str;

  let result = str.trim().toLowerCase();
  
  // First, handle regular word boundaries (spaces, punctuation)
  result = result.replace(/\b\w/g, function (char) {
    return char.toUpperCase();
  });
  
  // Special handling: ensure first non-number character is uppercase
  // This handles cases like "26ss" → "26Ss"
  result = result.replace(/^(\d*)([a-z])/, function(_, numbers, firstLetter) {
    return numbers + firstLetter.toUpperCase();
  });
  
  return result;
}

frappe.ui.form.on('Item Attribute', {
  refresh: function (frm) {
    // Thêm nút import trực tiếp
    addImportButton(frm);
  },
  onload: function (frm) {
    // Thêm cả khi form được tải lần đầu
    addImportButton(frm);
  },
  onload_post_render: function (frm) {
    // Thêm sau khi form đã render xong
    addImportButton(frm);
  },
  after_save: function (frm) {
    // Thêm sau khi lưu form
    addImportButton(frm);
  }
});

// Tách hàm thêm nút ra để tái sử dụng
function addImportButton(frm) {
  setTimeout(function () {
    // Xóa nút cũ nếu đã tồn tại để tránh trùng lặp
    frm.remove_custom_button('Import Values');
    // Thêm nút mới
    frm.add_custom_button(__('Import Values'), function () {
      showImportDialog(frm);
    });
  }, 300); // Đợi một chút để đảm bảo UI đã render xong
}

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
        description: __(`Each line will be imported as a new ${attributeName} value with auto-generated abbreviation. Values will be converted to Proper Case format (e.g., "red color" → "Red Color").`)
      },
      {
        fieldtype: 'HTML',
        fieldname: 'preview_area',
        options: `
          <div id="preview-container" style="margin-top: 15px; display: none;">
            <h6><strong>Preview (Proper Case format):</strong></h6>
            <div id="preview-content" style="max-height: 150px; overflow-y: auto; padding: 10px; border: 1px solid #ddd; border-radius: 4px; background: #f9f9f9; font-family: monospace; font-size: 12px;"></div>
          </div>
        `
      }
    ],
    primary_action_label: __('Import'),
    primary_action: function () {
      // Lấy giá trị đã nhập và loại bỏ dòng trống
      const rawValues = d.get_value('values').split('\n');
      const allValues = rawValues.filter(v => v.trim() !== '');

      if (allValues.length === 0) {
        frappe.msgprint(__('No values to import.'));
        return;
      }

      // Convert tất cả values sang Proper Case và xử lý trùng lặp
      const properCaseValues = allValues.map(v => toProperCase(v.trim()));

      // Xử lý trùng lặp trong giá trị đã nhập (so sánh case-insensitive)
      const uniqueValues = [];
      const internalDuplicates = [];
      const valueSet = new Set();

      // Tìm giá trị trùng lặp trong input
      properCaseValues.forEach((properValue, index) => {
        const originalValue = allValues[index].trim();
        const lowercaseValue = properValue.toLowerCase();

        if (valueSet.has(lowercaseValue)) {
          internalDuplicates.push(originalValue);
        } else {
          valueSet.add(lowercaseValue);
          uniqueValues.push(properValue);
        }
      });

      d.hide();

      // Kiểm tra giá trị trùng lặp với giá trị hiện có (case-insensitive)
      const existingValues = frm.doc.item_attribute_values || [];
      const existingValueSet = new Set(existingValues.map(v => v.attribute_value.toLowerCase()));
      const duplicatesWithExisting = uniqueValues.filter(v => existingValueSet.has(v.toLowerCase()));
      const newValues = uniqueValues.filter(v => !existingValueSet.has(v.toLowerCase()));

      // Hiển thị thông báo về các giá trị trùng lặp và conversion
      let duplicateMessage = '';

      // Show conversion info
      const convertedCount = allValues.filter((original, index) =>
        original.trim() !== properCaseValues[index]
      ).length;

      if (convertedCount > 0) {
        duplicateMessage += `<p><strong>Format Conversion:</strong> ${convertedCount} values were converted to Proper Case format.</p>`;
      }

      if (internalDuplicates.length > 0) {
        duplicateMessage += `<p><strong>Internal Duplicates:</strong> ${internalDuplicates.length} duplicate values within your input were removed.</p>`;
        if (internalDuplicates.length <= 10) {
          duplicateMessage += `<p style="font-family: monospace; font-size: 11px; color: #666;">Duplicates: ${internalDuplicates.join(', ')}</p>`;
        }
      }

      if (duplicatesWithExisting.length > 0) {
        duplicateMessage += `<p><strong>Existing Values:</strong> ${duplicatesWithExisting.length} values already exist in the attribute and will be skipped.</p>`;
        if (duplicatesWithExisting.length <= 10) {
          duplicateMessage += `<p style="font-family: monospace; font-size: 11px; color: #666;">Existing: ${duplicatesWithExisting.join(', ')}</p>`;
        }
      }

      if (duplicateMessage) {
        frappe.msgprint({
          title: __('Import Summary'),
          indicator: convertedCount > 0 ? 'blue' : 'orange',
          message: duplicateMessage
        });
      }

      if (newValues.length === 0) {
        frappe.msgprint({
          title: __('No New Values'),
          indicator: 'orange',
          message: __('No unique values to import. All values either already exist or are duplicates.')
        });
        return;
      }

      // Bắt đầu nhập dữ liệu với timeout để tránh treo UI
      setTimeout(() => {
        importValuesWithProgress(frm, newValues);
      }, 300);
    }
  });

  // Thêm real-time preview khi user nhập
  d.$wrapper.on('input', 'textarea[data-fieldname="values"]', function () {
    const inputValues = $(this).val().split('\n').filter(v => v.trim() !== '');
    const previewContainer = d.$wrapper.find('#preview-container');
    const previewContent = d.$wrapper.find('#preview-content');

    if (inputValues.length > 0) {
      // Show preview với Proper Case format
      const previewItems = inputValues.slice(0, 20).map(value => {
        const original = value.trim();
        const properCase = toProperCase(original);

        if (original !== properCase) {
          return `<span style="color: #666;">${original}</span> → <span style="color: #2e7d32; font-weight: bold;">${properCase}</span>`;
        } else {
          return `<span style="color: #2e7d32;">${properCase}</span>`;
        }
      });

      let previewHtml = previewItems.join('<br>');

      if (inputValues.length > 20) {
        previewHtml += `<br><span style="color: #666; font-style: italic;">... and ${inputValues.length - 20} more values</span>`;
      }

      previewContent.html(previewHtml);
      previewContainer.show();
    } else {
      previewContainer.hide();
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
      title: __('Importing Values (Proper Case Format)'),
      indicator: 'blue',
      message: `<div class="progress">
              <div class="progress-bar" role="progressbar" 
                  style="width: 0%;" aria-valuenow="0" 
                  aria-valuemin="0" aria-valuemax="100">0%</div>
            </div>
            <p style="margin-top: 10px; font-size: 12px; color: #666;">
              All values are being saved in Proper Case format...
            </p>`,
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
            message: __(`Successfully imported ${importedCount} values in Proper Case format.`)
          });
          frm.save();
        }, 500);
        return;
      }

      const value = values[index]; // Value đã được convert sang Proper Case
      if (!value || value.trim() === '') {
        processNext(index + 1);
        return;
      }

      // Tạo mã viết tắt mới
      lastAbbr = get_next_code(lastAbbr);

      // Thêm giá trị mới (đã ở dạng Proper Case)
      const child = frappe.model.add_child(frm.doc, 'Item Attribute Value', 'item_attribute_values');
      child.attribute_value = value; // Giá trị đã được format
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

// Thêm hàm để hỗ trợ import CSV với Proper Case
frappe.ui.form.on('Data Import', {
  refresh: function (frm) {
    // Chỉ áp dụng cho Item Attribute imports
    if (frm.doc.reference_doctype === "Item Attribute") {
      // Thêm thông báo để thông báo về tự động tạo abbreviations và Proper Case
      frm.add_custom_button(__('Import Guidelines'), function () {
        frappe.msgprint({
          title: __('Item Attribute Import Guidelines'),
          indicator: 'green',
          message: __(`
                      <h6><strong>CSV Import Requirements:</strong></h6>
                      <ul>
                          <li>CSV chỉ cần chứa: <strong>Attribute Name</strong> (Color, Size...) và <strong>Attribute Value</strong> (giá trị)</li>
                          <li>Mã viết tắt (Abbreviation) sẽ tự động được tạo</li>
                          <li>Định dạng mã: 3 ký tự cho Color, Size, Info và 2 ký tự cho Brand, Season</li>
                          <li>Hệ thống sẽ tiếp tục từ mã cuối cùng hiện có</li>
                      </ul>
                      
                      <h6><strong>Proper Case Formatting:</strong></h6>
                      <ul>
                          <li>Tất cả attribute values sẽ được tự động chuyển sang <strong>Proper Case</strong></li>
                          <li>Ví dụ: "red color" → "Red Color", "blue1" → "Blue1"</li>
                          <li>Khoảng trắng được giữ nguyên giữa các từ</li>
                          <li>Chữ cái đầu mỗi từ sẽ được viết hoa</li>
                      </ul>
                      
                      <h6><strong>Duplicate Detection:</strong></h6>
                      <ul>
                          <li>Hệ thống tự động phát hiện và bỏ qua giá trị trùng lặp</li>
                          <li>So sánh không phân biệt hoa thường</li>
                          <li>Báo cáo chi tiết sau khi import</li>
                      </ul>
                  `)
        });
      }, __("Import"));
    }
  }
});