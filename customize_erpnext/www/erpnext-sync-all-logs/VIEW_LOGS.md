# 📄 ERPNext Sync All Logs

## 🌐 Truy cập

### URL:
```
http://erp.tiqn.local/erpnext-sync-all-logs
```

## ✨ Tính năng

### Log Viewer

Web interface đơn giản để xem các file log từ biometric-attendance-sync-tool.

**Chức năng:**
- **Chọn file log**: Dropdown list hiển thị tất cả file .log trong thư mục logs/
- **Default log**: Tự động chọn và load `logs.log` khi page mở (nếu file tồn tại)
- **Filter theo level:**
  - **Tất cả**: Hiển thị tất cả log lines
  - **Chỉ Error**: Chỉ hiển thị ERROR và CRITICAL
  - **Warning+**: Hiển thị WARNING, ERROR, CRITICAL
  - **Info+**: Hiển thị INFO, WARNING, ERROR, CRITICAL
- **Search**: Tìm kiếm text trong log
- **Stats**: Hiển thị số dòng đang xem / tổng số dòng
- **Auto-load**: Log tự động tải khi chọn file
- **Sắp xếp**: Logs hiển thị mới nhất trước (newest first)

## 📝 Hướng dẫn sử dụng

1. Truy cập: http://erp.tiqn.local/erpnext-sync-all-logs
2. Chọn file log từ dropdown "File"
3. Log sẽ tự động tải và hiển thị
4. Sử dụng Filter để lọc theo level (Error/Warning/Info)
5. Sử dụng Search để tìm kiếm text
6. Xem stats để biết số dòng đang hiển thị

## 🎨 Màu sắc Log

- 🔴 **Red (Error)** - ERROR, CRITICAL
- 🟡 **Yellow (Warning)** - WARNING
- 🔵 **Blue (Info)** - INFO
- ⚪ **Gray (Default)** - Các log khác

## ⚙️ Thông tin kỹ thuật

### Files

**Location:**
```
customize_erpnext/
├── www/erpnext-sync-all-logs/
│   ├── index.py       # Backend (authentication check)
│   └── index.html     # Log viewer UI
└── api/
    └── biometric_log_viewer.py  # API endpoints
```

### API Endpoints

1. **get_log_files()**
   - Method: GET
   - Returns: `{status: 'success', files: [...]}`
   - Lấy danh sách tất cả file .log

2. **get_log_content(log_file)**
   - Method: GET
   - Parameters: `log_file` (tên file)
   - Returns: `{status: 'success', content: '...', file: '...'}`
   - Đọc nội dung file log

### Security

- Chỉ authenticated users mới truy cập được (redirects to login nếu Guest)
- Path traversal protection (không cho phép `..`, `/`, `\` trong tên file)
- Chỉ cho phép đọc file .log
- File path validation để đảm bảo chỉ đọc trong thư mục logs

## 📂 Logs được hỗ trợ

Tất cả các file .log trong thư mục `/home/frappe/frappe-bench/apps/biometric-attendance-sync-tool/logs/`:

- `sync_log_from_mongodb_to_erpnext.log`
- `sync_ot_log_from_mongodb_to_erpnext.log`
- `sync_time_to_devices.log`
- `restart_devices.log`
- `clear_left_employee_templates.log`
- `sync_user_info_to_devices.log`
- Và các log files khác...

## 🔧 Troubleshooting

### Lỗi 404
```bash
bench clear-cache
```

### Không thấy log files
Kiểm tra thư mục logs có tồn tại và có file .log:
```bash
ls -la /home/frappe/frappe-bench/apps/biometric-attendance-sync-tool/logs/
```

### Permission error
Đảm bảo user có quyền đọc file logs:
```bash
chmod 644 /home/frappe/frappe-bench/apps/biometric-attendance-sync-tool/logs/*.log
```

---

**Tạo**: 2025-12-03
**Updated**: 2025-12-04
**URL**: http://erp.tiqn.local/erpnext-sync-all-logs
**Version**: 3.0 (Log Viewer Only)
