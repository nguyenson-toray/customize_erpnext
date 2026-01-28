# Print Format Split Tool

## Mục đích

Tool để tách file `print_format.json` thành các file riêng biệt cho từng print format, tạo file HTML/CSS dễ đọc để copy vào Web UI.

## Cách sử dụng

### Bước 1: Export fixtures như bình thường
```bash
bench --site erp-sonnt.tiqn.local export-fixtures
```

### Bước 2: Chạy tool tách print formats
```bash
cd /home/sonnt/frappe-bench/apps/customize_erpnext/customize_erpnext/fixtures
python3 split_print_format.py
```

## Kết quả

Tool sẽ tạo:

### 1. Thư mục `print_formats/`
- Chứa các file JSON riêng cho từng print format
- Format: `[Print_Format_Name].json`
- Ví dụ: `Custom_Overtime_Request.json`, `Shift_Registration.json`

### 2. Thư mục `print_formats/templates/`
- Chứa file HTML/CSS dễ đọc để copy vào Web UI
- Format: `[Print_Format_Name].html`, `[Print_Format_Name].css`
- HTML được format với indentation đẹp
- CSS được format với indentation đẹp

## Ví dụ Output

```
📂 fixtures/
├── print_format.json (file gốc)
└── print_formats/
    ├── Custom_Overtime_Request.json
    ├── Overtime_Registration.json
    ├── Shift_Registration.json
    ├── Stock_Entry_Customize.json
    └── templates/
        ├── Custom_Overtime_Request.html
        ├── Custom_Overtime_Request.css
        ├── Overtime_Registration.html
        ├── Shift_Registration.html
        ├── Shift_Registration.css
        └── Stock_Entry_Customize.html
```

## Workflow thực tế

1. **Developer chỉnh sửa Print Format trên Web UI**
2. **Export fixtures**: `bench --site [site] export-fixtures`
3. **Tách file**: `python3 split_print_format.py`
4. **Copy HTML/CSS từ templates/** để chỉnh sửa
5. **Paste HTML/CSS trở lại Web UI khi cần thiết**

## Lợi ích

- ✅ **File dễ đọc**: HTML/CSS được format đẹp với indentation
- ✅ **Quản lý riêng biệt**: Mỗi print format một file JSON riêng
- ✅ **Version control**: Dễ track changes cho từng print format
- ✅ **Copy-paste friendly**: File HTML/CSS sẵn sàng để copy vào Web UI
- ✅ **Không phụ thuộc hook**: Chạy độc lập, không cần cấu hình phức tạp

## Lưu ý

- Tool không tự động import lại vào database
- Dùng để tách và xem nội dung, copy vào Web UI thủ công
- File `print_format.json` gốc vẫn được giữ nguyên