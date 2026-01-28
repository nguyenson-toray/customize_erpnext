# Tính năng Chụp & Upload Ảnh Nhân viên

## Mô tả
Tính năng cho phép chụp ảnh hoặc upload ảnh cho nhân viên với các chức năng:
- Chụp ảnh trực tiếp từ camera (ưu tiên camera sau trên mobile)
- Upload ảnh từ thư viện
- Crop ảnh theo tỷ lệ 3:4
- Tùy chọn xóa phông nền (AI)
- Tự động resize về 450x600px
- Lưu vào thư mục cố định: `public/files/employee_photos/`
- Tự động xóa ảnh cũ khi upload ảnh mới

## Cài đặt

### 1. Cài đặt thư viện Python
```bash
# Di chuyển vào thư mục bench
cd /home/frappe/frappe-bench

# Cài đặt rembg (xóa phông nền)
source env/bin/activate
pip install rembg

# Cài đặt onnxruntime (dependency cho rembg)
pip install onnxruntime

# Nếu gặp lỗi coverage, upgrade:
pip install --upgrade coverage
```

### 2. Tạo thư mục lưu ảnh
```bash
mkdir -p apps/customize_erpnext/customize_erpnext/public/files/employee_photos
```

### 3. Bật Cropper.js trong hooks.py
Uncomment các dòng sau trong file `customize_erpnext/hooks.py`:
```python
app_include_css = [
    "https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.css"
]
app_include_js = [
    "https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.js"
]
```

### 4. Build và khởi động lại
```bash
bench build --app customize_erpnext
bench restart
# Hoặc nếu restart lỗi:
bench clear-cache
# Sau đó hard refresh browser: Ctrl+Shift+R
```

## Luồng hoạt động

### A. Chụp ảnh (Take Photo)
1. **Mở camera dialog**
   - User click button "📷 Take Photo" trong form Employee
   - Check browser hỗ trợ `getUserMedia` API
   - Nếu HTTP: hiển thị lỗi yêu cầu HTTPS hoặc allow permission

2. **Khởi tạo camera**
   - Request quyền truy cập camera
   - Ưu tiên camera sau (`facingMode: 'environment'`)
   - Hiển thị preview camera trong dialog
   - Resolution: 1280x1280 (ideal)

3. **Chụp ảnh**
   - User click nút "Capture"
   - Vẽ frame hiện tại từ video lên canvas
   - Stop camera stream
   - Convert canvas thành base64 (JPEG, quality 95%)
   - Chuyển sang bước Crop

### B. Upload ảnh (Upload Photo)
1. **Chọn file**
   - User click button "📁 Upload Photo"
   - Mở file picker (accept: image/*)
   - Check kích thước file (max 5MB)

2. **Đọc file**
   - Sử dụng FileReader API
   - Convert file thành base64 data URL
   - Chuyển sang bước Crop

### C. Crop & xử lý ảnh
1. **Hiển thị Cropper dialog**
   - Khởi tạo Cropper.js với tỷ lệ 3:4 cố định
   - Cho phép zoom (pinch, wheel) và di chuyển ảnh
   - Hiển thị checkbox "Remove Background"

2. **Save Photo**
   - User click "Save Photo"
   - Lấy cropped canvas từ Cropper.js (max 2400x3200)
   - Convert canvas → blob → base64
   - Hiển thị message "Processing photo..."

3. **Gửi lên server**
   - API: `customize_erpnext.api.employee.employee_utils.process_employee_photo`
   - Args:
     - `employee_id`: Mã nhân viên
     - `employee_name`: Tên đầy đủ
     - `image_data`: Base64 string
     - `remove_bg`: 0 hoặc 1

### D. Xử lý server-side (Python)
1. **Decode và validate**
   - Decode base64 → binary data
   - Mở ảnh bằng PIL/Pillow
   - Convert về RGB (xóa alpha channel)

2. **Resize**
   - Resize chính xác về 450x600px
   - Sử dụng LANCZOS resampling (chất lượng cao)

3. **Xóa phông nền (nếu chọn)**
   - Sử dụng thư viện `rembg` (AI model)
   - Convert PIL → bytes → rembg → PIL
   - Paste lên nền trắng
   - Nếu lỗi: dùng ảnh gốc, hiển thị warning

4. **Xóa file cũ**
   - Query tất cả File documents gắn với Employee.image
   - Xóa physical files và File documents
   - **Bổ sung**: Dùng glob tìm và xóa các file orphan trong:
     - `/files/`
     - `/files/employee_photos/`
   - Pattern: `{employee_id} *.jpg`

5. **Lưu file mới**
   - Tên file: `{employee_id} {employee_name}.jpg`
   - Vị trí: `sites/{site}/public/files/employee_photos/`
   - Compress JPEG (quality 85, optimize=True)
   - Tạo/update File document trong database
   - Link với Employee.image field

6. **Update database**
   - Set Employee.image = `/files/employee_photos/{filename}`
   - Commit transaction
   - Return success + file_url

### E. Refresh UI
1. **Reload form**
   - Sau khi save thành công, đợi 500ms
   - Gọi `frm.reload_doc()` để reload toàn bộ form
   - Ảnh mới sẽ hiển thị từ database
   - Hiển thị alert "Photo saved successfully. Refreshing..."

## Files liên quan

### Frontend
- `customize_erpnext/public/js/custom_scripts/employee.js` (dòng 450-750)
  - `open_camera_dialog()`: Mở camera
  - `open_file_upload_dialog()`: Chọn file
  - `show_crop_dialog()`: Crop ảnh với Cropper.js
  - `stop_camera_stream()`: Dừng camera

### Backend
- `customize_erpnext/api/employee/employee_utils.py` (dòng 1098-1280)
  - `process_employee_photo()`: Xử lý và lưu ảnh

### Config
- `customize_erpnext/hooks.py` (dòng 339-345)
  - Include Cropper.js CSS/JS từ CDN

## Lưu ý

### Camera trên HTTP
- Browser chặn camera API trên HTTP (chỉ cho phép HTTPS)
- **Giải pháp**:
  1. Dùng HTTPS
  2. Hoặc allow permission trong browser settings
  3. Localhost được exempt (có thể dùng camera)

### File cleanup
- Code tự động xóa **TẤT CẢ** file cũ trước khi lưu file mới
- Bao gồm: file trong File doctype + orphan files trên disk
- Tìm kiếm trong 2 thư mục:
  - `/files/` (file cũ/upload tạm)
  - `/files/employee_photos/` (file đúng vị trí)

### Định dạng file
- Tên file: `{employee_id} {employee_name}.jpg`
- Ví dụ: `TIQN-0148 Nguyễn Thái Sơn.jpg`
- Kích thước: 450x600px (3:4 ratio)
- Format: JPEG, quality 85%

### Thư mục .gitkeep
- File `/apps/customize_erpnext/customize_erpnext/public/files/employee_photos/.gitkeep`
- Mục đích: Cho git track thư mục rỗng
- Không có tác dụng runtime, có thể xóa sau khi có file ảnh

## Troubleshooting

### Lỗi "Camera not available"
- Check browser hỗ trợ: Chrome, Firefox, Safari, Edge (bản mới)
- Check HTTPS hoặc allow permission
- Check device có camera

### Lỗi "rembg library not installed"
- Chạy: `pip install rembg onnxruntime`
- Restart bench

### Ảnh không refresh sau upload
- Hard refresh browser: Ctrl+Shift+R
- Check console log xem có lỗi không
- Check file đã được tạo: `ls -lah sites/{site}/public/files/employee_photos/`

### Tồn tại 2 file trùng tên
- File cũ từ trước khi có thư mục employee_photos
- Code mới đã xử lý: tự động xóa file orphan trong cả 2 thư mục
- Hoặc xóa thủ công: `rm sites/{site}/public/files/{employee_id}*.jpg`
