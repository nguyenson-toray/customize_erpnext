# Employee Photos — Tài liệu kỹ thuật

## Cấu trúc file

```
www/employee-photos/
├── index.py           # Access control (Python/Frappe)
├── index.html         # Trang thư viện ảnh chính
├── photo_editor.html  # Trình sửa ảnh (chạy trong iframe)
└── readme.md

api/employee/
└── employee_utils.py  # Backend API (process_employee_photo)
```

---

## 1. index.py — Kiểm soát truy cập

Chạy trước khi render `index.html`.

- Nếu chưa đăng nhập → redirect `/login?redirect-to=/employee-photos`
- Kiểm tra role: role phải chứa một trong các keyword `admin`, `hr`, `manager`, `ga` (không phân biệt hoa thường)
- Inject `csrf_token` vào context để dùng trong JS: `window.csrf_token = "{{ csrf_token }}"`

---

## 2. index.html — Thư viện ảnh

### 2.1 Tải dữ liệu & Cache

```
loadGroups() → API get_employee_groups → lưu localStorage
loadPhotos() → API get_employee_photos → lưu localStorage
```

- Cache lưu bằng `localStorage` với thời hạn (CACHE_CONFIG).
- Mỗi entry cache gồm `{ data, expiry }`. Hết hạn → xóa và tải lại.
- `refreshData()`: xóa cache, gọi lại cả 2 API, re-render gallery.
- `updateTimestamp()`: ghi thời điểm cập nhật lần cuối vào localStorage.

### 2.2 Lọc & Hiển thị

```
applyFilters() → displayPhotos()
```

- Filter theo: nhóm (`custom_group`), trạng thái (`status`), tìm kiếm text.
- Tìm kiếm hỗ trợ tiếng Việt có dấu → dùng `removeVietnameseTones()` để so sánh.
- `displayPhotos()`: tạo `.photo-card` cho mỗi nhân viên, hiển thị ảnh + tên + mã.
- `updateStats()`: cập nhật số liệu tổng/đã có ảnh/chưa có ảnh.

### 2.3 Gọi API Frappe (www context)

Trang www **không có** `frappe` JS object → dùng `fetch` thủ công:

```javascript
async function callFrappeMethod(method, args)
```

**Quan trọng:** Frappe validate CSRF từ **form body**, không phải từ header.

```
FormData { csrf_token, ...args }
POST /api/method/{method}
→ response: { message: ... }   // thành công
→ response: { exc, exc_type }  // lỗi (frappe.throw)
```

Nếu HTTP 403 → session hết hạn → `location.reload()`.

### 2.4 Upload ảnh mới

Có 3 đường vào:

**A. Upload từng người (nút Upload trên card)**
```
openUploadDialog(photo)
  ├── startCameraModal() → captureFrame() → openCropModal(dataUrl)
  └── triggerFileInput() → FileReader → openCropModal(dataUrl)
       └── saveCrop() → uploadEmployeePhoto(employeeId, dataUrl)
               └── callFrappeMethod(process_employee_photo)
```

- Camera dùng `navigator.mediaDevices.getUserMedia` (cần HTTPS).
- Crop dùng **Cropper.js**, tỉ lệ 3:4.

**B. Upload hàng loạt (global upload)**
```
handleGlobalPhotoUpload(files)
  → mỗi file: lấy mã TIQN-XXXX từ tên file
  → uploadEmployeePhoto(employeeId, dataUrl)
```

Tên file phải có format: `TIQN-0001 Nguyen Van A.jpg`

**C. Qua Photo Editor (nút Edit)**
```
openPhotoEditor(photo) → sendToEditor() [postMessage INIT_EDITOR]
  → (editor xử lý) → postMessage SAVE_PHOTO
  → uploadToFrappe(employeeId, dataUrl)
        └── callFrappeMethod(process_employee_photo)
```

### 2.5 Sau khi lưu ảnh thành công

```
refreshPhotoCardImage(employeeId, newUrl)
  → cập nhật <img> trên card ngay (không reload trang)
  → thêm ?t=timestamp để tránh browser cache ảnh cũ
  → cập nhật allPhotos[] trong memory
  → setCache(PHOTOS_KEY, allPhotos) — lưu lại cache mới
```

---

## 3. photo_editor.html — Trình sửa ảnh

Chạy trong `<iframe>` bên trong `index.html`. Giao tiếp qua **postMessage**.

### 3.1 postMessage bridge

| Chiều | Message type | Nội dung |
|-------|-------------|---------|
| iframe → parent | `EDITOR_READY` | Editor đã load xong |
| parent → iframe | `INIT_EDITOR` | `{ imageUrl, employeeId, employeeName }` |
| parent → iframe | `CLOSE_EDITOR` | Reset editor, thoát ERPNext mode |
| iframe → parent | `SAVE_PHOTO` | `{ dataUrl, employeeId }` |

**Flow:**
1. iframe load xong → gửi `EDITOR_READY`
2. parent nhận → gọi `sendToEditor()` → gửi `INIT_EDITOR`
3. iframe nhận → `loadImageFromUrl(url)` → hiện ảnh
4. User nhấn Lưu → `saveAction()` → gửi `SAVE_PHOTO`
5. parent nhận → `uploadToFrappe(employeeId, dataUrl)`

### 3.2 Trạng thái toàn cục (object G)

```javascript
G = {
  hasImage,    // đã có ảnh chưa
  original,    // ImageData gốc (không đổi)
  base,        // ImageData làm việc (sau crop)
  bgRemoved,   // ImageData sau khi xóa nền (RGBA)
  hasBg,       // đã xóa nền chưa
  bgColor,     // màu nền hiện tại
  segmenter,   // MediaPipe segmenter (lazy init)
  segLoading,  // đang chạy AI không
  cropSrc,     // URL/dataUrl nguồn cho Cropper.js
}
```

### 3.3 Xóa nền AI — `doRemoveBg()`

Dùng **TensorFlow.js + MediaPipe Selfie Segmentation** (chạy hoàn toàn trên browser):

```
1. Lazy init: tf.setBackend('webgl') → bodySegmentation.createSegmenter()
2. segmentPeople(workCanvas) → binary mask (trắng=người, đen=nền)
3. Pipeline làm mịn viền mask:
   erodeMask(r=1) → dilate(r=1) → gaussianBlur × 3 → smoothstep
4. Áp alpha từ mask lên ảnh gốc → G.bgRemoved (RGBA)
5. applyBgColor() → vẽ nền màu tùy chọn lên cvAfter
```

**Fallback:** nếu AI lỗi → `fallbackBg()` (xóa nền đơn giản hơn).

Model tải lần đầu ~15s, các lần sau dùng lại `G.segmenter`.

### 3.4 Crop — `activateCropper()` / `applyCrop()`

- Dùng **Cropper.js** trên `cvBefore`.
- `applyCrop()`: lấy vùng crop → vẽ lên `cvAfter` → cập nhật `G.base`.
- Sau crop, nếu đã có `G.bgRemoved` → chạy lại xóa nền trên vùng mới.

### 3.5 Chỉnh màu — `applyFilters()`

Các bộ lọc pixel-level (duyệt từng pixel trên ImageData):

| Slider | Thuật toán |
|--------|-----------|
| Brightness | cộng/trừ giá trị RGB |
| Contrast | scale quanh trung điểm 128 |
| Saturation | convert HSL, scale S |
| Warmth | tăng R, giảm B |
| Highlights/Shadows | `shadowsHighlights()` — scale theo độ sáng |
| Smooth | `skinSmooth()` — làm mịn vùng da |
| Sharpness | `unsharpMask()` — làm nét |

Sau các bộ lọc: thêm `vignette()` (tối góc ảnh).

### 3.6 Smart Beautify — `smartBeautify()`

Tự động phân tích ảnh và đề xuất thông số:

```
analyzeDeep(imageData)
  → tính: độ sáng trung bình, tỉ lệ pixel da, histogram
  → trả về: { brightness, contrast, saturation, smooth, sharpness, warmth, ... }
applySliders(params) → applyFilters()
```

Phát hiện da qua `isSkin(r, g, b)`: kiểm tra khoảng RGB đặc trưng của da người.

### 3.7 Canvas architecture

```
cvBefore  ← ảnh gốc (chỉ đọc, hiện split-view trái)
cvAfter   ← kết quả sau chỉnh sửa (hiện split-view phải)
workCv    ← canvas tạm cho AI segmentation
segCv     ← canvas tạm cho mask
```

Split-view: kéo thanh ngang chia đôi để so sánh before/after.

---

## 4. employee_utils.py — Backend API

### `process_employee_photo(employee_id, employee_name, image_data)`

```
1. Decode base64 → PIL Image
2. Convert sang RGB (bỏ alpha nếu có)
3. Resize → 600×800px (LANCZOS)
4. Lưu JPEG quality=85 vào:
   {site}/public/files/employee_photos/{employee_id} {employee_name}.jpg
5. Xóa file cũ + File documents cũ trong DB
6. Tạo File document mới trong Frappe
7. Cập nhật field `image` trên Employee record
8. Return { status: 'success', file_url: '...', file_name: '...' }
```

---

## 5. Debug nhanh

| Vấn đề | Kiểm tra |
|--------|---------|
| CSRF error 403 | Đảm bảo dùng FormData (không phải JSON header) |
| Ảnh không cập nhật sau lưu | Xem `refreshPhotoCardImage`, cache `?t=timestamp` |
| AI xóa nền chậm/lỗi | Console → `G.segmenter`, network tab model download |
| Upload hàng loạt bỏ qua file | Tên file phải bắt đầu bằng `TIQN-XXXX` |
| Camera không hoạt động | Cần HTTPS, kiểm tra `navigator.mediaDevices` |
| postMessage không nhận | Kiểm tra `EDITOR_READY` → `sendToEditor()` flow |
