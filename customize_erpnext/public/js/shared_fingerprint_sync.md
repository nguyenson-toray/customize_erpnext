# Tài Liệu Sync Fingerprint - Đồng Bộ Vân Tay

## 📋 Tổng Quan

Hệ thống đồng bộ vân tay từ ERP đến các máy chấm công với tính năng **đa luồng** (multi-threading) để tăng tốc độ xử lý.

## 🚀 Cách Thức Hoạt Động

### 1. **Sync 1 Nhân Viên** (Từ Form Employee)
```
Mở Employee → Click nút sync → Dialog hiện ra → Start Sync
```

### 2. **Sync Nhiều Nhân Viên** (Từ Danh Sách Employee)
```
Employee List → Chọn nhiều nhân viên → Actions → "Sync Fingerprint From ERP To Attendance Machines"
```

## ⚡ Tối Ưu Đa Luồng

### Trước Khi Tối Ưu:
```
Máy 1: ████████ (10 giây)
Máy 2:         ████████ (10 giây)
Máy 3:                 ████████ (10 giây)
Tổng: 30 giây
```

### Sau Khi Tối Ưu:
```
Máy 1: ████████ (10 giây)
Máy 2: ████████ (10 giây)  // Cùng lúc
Máy 3: ████████ (10 giây)  // Cùng lúc
Tổng: 10 giây (nhanh gấp 3 lần!)
```

## 🔧 Cấu Hình Hiện Tại

### Trong File `shared_fingerprint_sync.js`:
```javascript
const CONFIG = {
    CONCURRENT_MACHINES: 7,    // Tối đa 7 máy sync cùng lúc
    MACHINE_TIMEOUT: 10000,    // 10 giây timeout cho mỗi máy
    RETRY_ATTEMPTS: 2,         // Thử lại 2 lần nếu lỗi
    RETRY_DELAY: 1000         // Đợi 1 giây giữa các lần thử
};
```

## 🎯 Cách Sync Hoạt Động

### **Bước 1: Kiểm Tra Máy Chấm Công**
- ✅ Máy online: có thể sync
- ❌ Máy offline: bỏ qua
- 🟡 Máy chậm: vẫn sync nhưng lâu hơn

### **Bước 2: Xử Lý Từng Nhân Viên**
```
Nhân viên 1 → Sync đến TẤT CẢ máy cùng lúc → Xong
Nhân viên 2 → Sync đến TẤT CẢ máy cùng lúc → Xong
Nhân viên 3 → Sync đến TẤT CẢ máy cùng lúc → Xong
```

### **Bước 3: Chia Nhóm Máy (Batch Processing)**
Nếu có quá nhiều máy:
```
Nhóm 1: 7 máy đầu → Sync cùng lúc
Nhóm 2: 7 máy tiếp → Sync cùng lúc
Nhóm 3: Máy còn lại → Sync cùng lúc
```

## 🖥️ Giao Diện Người Dùng

### **Progress Bar:**
- 📊 Thanh tiến trình tổng thể
- 🖥️ Trạng thái từng máy riêng biệt
- 📝 Log chi tiết theo thời gian thực

### **Nút Điều Khiển:**
- **🚀 Start Sync**: Bắt đầu đồng bộ
- **🛑 Abort Sync**: Dừng giữa chừng (trong lúc sync)
- **🔄 Refresh Machines**: Làm mới danh sách máy

### **Trạng Thái Máy:**
- 🟢 **Online**: Sẵn sàng sync
- 🔴 **Offline**: Không thể kết nối
- 🟡 **Syncing**: Đang sync
- ✅ **Complete**: Sync xong
- ❌ **Failed**: Sync lỗi

## 🔒 Bảo Vệ Chống Đóng Dialog

### **Khi Đang Sync:**
- ❌ Không cho đóng dialog
- ⚠️ Hiện cảnh báo: "Sync đang chạy, bạn có chắc muốn đóng?"
- 🛑 Có nút "Abort Sync" để dừng an toàn

### **Khi Không Sync:**
- ✅ Cho phép đóng bình thường
- 🔄 Nút "Refresh Machines" hoạt động bình thường

## 📊 Hiệu Suất Thực Tế

### **Ví Dụ Với 5 Nhân Viên, 3 Máy:**

**Cách Cũ (Tuần Tự):**
```
NV1 → Máy1(10s) → Máy2(10s) → Máy3(10s) = 30s
NV2 → Máy1(10s) → Máy2(10s) → Máy3(10s) = 30s
NV3 → Máy1(10s) → Máy2(10s) → Máy3(10s) = 30s
NV4 → Máy1(10s) → Máy2(10s) → Máy3(10s) = 30s
NV5 → Máy1(10s) → Máy2(10s) → Máy3(10s) = 30s
TỔNG: 150 giây (2.5 phút)
```

**Cách Mới (Đa Luồng):**
```
NV1 → Máy1+Máy2+Máy3 cùng lúc = 10s
NV2 → Máy1+Máy2+Máy3 cùng lúc = 10s
NV3 → Máy1+Máy2+Máy3 cùng lúc = 10s
NV4 → Máy1+Máy2+Máy3 cùng lúc = 10s
NV5 → Máy1+Máy2+Máy3 cùng lúc = 10s
TỔNG: 50 giây (50 giây)
```

**🎯 Kết Quả: Nhanh gấp 3 lần!**

## 🛠️ Cài Đặt & Triển Khai

### **Các File Liên Quan:**
```
📁 public/js/
├── shared_fingerprint_sync.js     ← Logic chính
├── custom_scripts/
│   ├── employee.js                ← Form đơn lẻ
│   └── employee_list.js           ← Danh sách nhiều NV
└── fingerprint_scanner_dialog.js  ← Dialog scan vân tay
```

### **File Cấu Hình:**
```python
# hooks.py
doctype_js = {
    "Employee": [
        "public/js/fingerprint_scanner_dialog.js",
        "public/js/shared_fingerprint_sync.js",    ← Thêm dòng này
        "public/js/custom_scripts/employee.js"
    ]
}

doctype_list_js = {
    "Employee": [
        "public/js/fingerprint_scanner_dialog.js",
        "public/js/shared_fingerprint_sync.js",    ← Thêm dòng này
        "public/js/custom_scripts/employee_list.js"
    ]
}
```

### **Lệnh Deploy:**
```bash
# Xóa cache
bench --site erp-sonnt.tiqn.local clear-cache

# Build lại assets
bench build

# Migrate database
bench --site erp-sonnt.tiqn.local migrate

# Restart server
bench restart
```

## 🐛 Xử Lý Lỗi

### **Lỗi Thường Gặp:**

**1. "Function not found":**
```bash
# Giải pháp: Build lại
bench build
```

**2. "Machine offline":**
- ✅ Hệ thống tự động bỏ qua máy offline
- 🔄 Sync tiếp với máy online

**3. "Timeout":**
- 🔄 Tự động retry 2 lần
- ⚠️ Báo lỗi nếu vẫn fail

**4. "Sync bị gián đoạn":**
- 🛑 Dùng nút "Abort Sync"
- 📝 Check log để biết trạng thái

### **Debug Mode:**
```javascript
// Trong browser console:
window.FingerprintSyncManager.CONFIG.DEBUG = true;

// Check function có tồn tại:
console.log('Sync function:', typeof window.showSharedSyncDialog);
```

## 📈 Tối Ưu Thêm (Tương Lai)

### **Có Thể Làm:**
1. **Auto-detect CPU cores** → Điều chỉnh CONCURRENT_MACHINES
2. **Machine health scoring** → Ưu tiên máy nhanh trước
3. **Background sync** → Sync không cần mở dialog
4. **WebSocket real-time** → Cập nhật tiến trình từ server
5. **Sync scheduling** → Tự động sync theo lịch

### **Hiện Tại Đủ Dùng:**
- ✅ Nhanh gấp 3-7 lần so với trước
- ✅ Giao diện trực quan, dễ dùng
- ✅ Xử lý lỗi tốt
- ✅ Có thể dừng giữa chừng
- ✅ Hỗ trợ cả đơn lẻ và batch

## 🎯 Kết Luận

Hệ thống sync vân tay hiện tại đã được tối ưu với **đa luồng**, giúp:

- ⚡ **Tăng tốc 3-7 lần** so với cách cũ
- 👥 **Hỗ trợ sync nhiều nhân viên** cùng lúc
- 🎮 **Giao diện thân thiện** với progress bar
- 🛡️ **An toàn** với tính năng abort
- 🔧 **Dễ bảo trì** với code sạch, có document

**Sẵn sàng sử dụng trong production!** 🚀