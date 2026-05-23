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

public/bg_removal/     # Model @imgly (~211MB, phục vụ local)
├── resources.json
└── <58 chunk files>   # hash-named binary chunks

public/face_api/       # Model face-api.js (vladmandic)
├── face-api.esm.js    # ~1.3MB (bundle TF.js + WebGL)
└── models/
    ├── ssd_mobilenetv1_model-weights_manifest.json
    └── ssd_mobilenetv1_model.bin  # ~5.4MB
```

Script tải model lần đầu:
```
apps/customize_erpnext/customize_erpnext/scripts/download_imgly_models.py
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

### 2.2 Lọc & Hiển thị

```
applyFilters() → displayPhotos()
```

- Filter theo: nhóm (`custom_group`), trạng thái (`status`), tìm kiếm text.
- Tìm kiếm hỗ trợ tiếng Việt có dấu → dùng `removeVietnameseTones()`.
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
  → gán lại sự kiện click cho nút Edit/Delete (addEventListener)
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
  hasImage,      // đã có ảnh chưa
  original,      // ImageData gốc (không đổi)
  origSrc,       // dataURL ảnh gốc — dùng cho split-view "Gốc"
  base,          // ImageData làm việc (sau crop/xóa nền)
  bgRemoved,     // ImageData sau xóa nền (RGBA, alpha = mask)
  hasBg,         // đã xóa nền chưa
  bgColor,       // màu/gradient nền hiện tại (default '#f0f0f0')
  segLoading,    // đang chạy AI không
  cropSrc,       // URL/dataUrl nguồn cho Cropper.js
  ratio,         // tỉ lệ crop (3/4 khi auto)
  autoPending,   // đang chờ user xác nhận crop trong auto pipeline
  _cropSuggest,  // { x, y, width, height } gợi ý crop từ face detection
}
```

### 3.3 Thư viện & Model (load local)

#### @imgly/background-removal v1.4.5
- JS: import qua `esm.sh` (`type="module"`)
- Model files (~211MB): phục vụ từ `/assets/customize_erpnext/bg_removal/`
- `publicPath`: phải là **URL tuyệt đối** → `location.origin + '/assets/customize_erpnext/bg_removal/'`
- Warm-up: model được load ngầm ngay khi trang mở (chạy 1 pixel dummy để kích hoạt)

#### face-api.js v1.7.15 (vladmandic)
- File: `/assets/customize_erpnext/face_api/face-api.esm.js`
- Model: SSD MobileNet v1 (~5.4MB), load từ `/assets/customize_erpnext/face_api/models/`
- Backend: WebGL (không cần WASM)
- Gán vào `window.faceapi` để dùng ngoài module scope

### 3.4 Auto Pipeline — 2 phase

Nút **"Tạo ảnh thẻ tự động"** chạy pipeline chia 2 giai đoạn:

**Phase 1 — `runAutoPipeline()`**
```
1. preprocessResize() — resize ảnh xuống max 1200px
2. detectFace() — SSD MobileNet v1 → lấy bounding box khuôn mặt
3. Tính vùng crop đề xuất:
   cropH = box.height / 0.38   (đầu chiếm 38% chiều cao ảnh thẻ)
   cropY = box.y - box.height * 0.20  (headroom 20%)
   tỉ lệ 3:4
4. Lưu G._cropSuggest, G.ratio = 3/4
5. Kích hoạt Cropper.js với vùng đề xuất (user có thể điều chỉnh)
6. G.autoPending = true → chờ user nhấn "Áp dụng cắt"
```

**Phase 2 — `continueAutoPipeline()`** (gọi từ `applyCrop()` khi `G.autoPending`)
```
1. _removeBgCore()     — xóa nền AI (@imgly)
2. applyBgColor()      — đặt màu nền (default #f0f0f0)
3. analyzeDeep()       — phân tích ảnh
4. p.smooth = max(p.smooth, 3)  — minimum smooth vừa phải
5. applySliders(p) + applyFilters()  — làm đẹp
6. Khôi phục nền sạch:  — (quan trọng, xem mục 3.7)
   copy màu pixel đã enhance + restore alpha gốc từ G.bgRemoved
   → G.bgRemoved = newFg
   → applyBgColor() lại để composite sạch
```

### 3.5 Xóa nền AI — `_removeBgCore()`

```
1. Lấy blob từ G.base (canvas → Blob)
2. removeBackground(blob, {
     publicPath: location.origin + '/assets/customize_erpnext/bg_removal/',
     model: 'medium',
     output: { format: 'image/png', quality: 1 }
   })
3. Kết quả: PNG transparent → vẽ lên workCv → getImageData → G.bgRemoved
4. applyBgColor(G.bgColor) — composite người lên nền
```

### 3.6 Nhận diện khuôn mặt — `detectFace()`

```javascript
await _ensureFaceApi()  // lazy load + load model lần đầu
const detection = await window.faceapi.detectSingleFace(
  workCv,
  new window.faceapi.SsdMobilenetv1Options({ minConfidence: 0.3 })
)
→ trả về { box: { x, y, width, height }, score }
```

`_ensureFaceApi()`: chờ `window.faceapi` tối đa 8 giây (module load async), sau đó load model một lần duy nhất (`_faceApiModelLoaded` flag).

### 3.7 Crop — `activateCropper()` / `applyCrop()`

- Dùng **Cropper.js** trên `cvBefore`.
- `activateCropper()`: khởi tạo Cropper, lắng nghe event `ready` để áp `G._cropSuggest`.
- `applyCrop()`:
  1. Lấy vùng crop → vẽ lên `cvAfter` → cập nhật `G.base`
  2. Nếu `G.autoPending = true` → gọi `continueAutoPipeline()` (phase 2)

### 3.8 Chỉnh màu — `applyFilters()`

Các bộ lọc pixel-level (duyệt từng pixel trên ImageData), thứ tự:

| Bước | Hàm | Thuật toán |
|------|-----|-----------|
| 1 | `skinSmooth(id, Sm)` | Frequency separation: box blur + blend theo `str = Sm/18`; micro skin lift |
| 2 | `shadowsHighlights(id, Sh2, Hi)` | Luminance mask → scale shadow/highlight vùng riêng |
| 3 | Warmth | `R += W*1.6`, `B -= W*1.1` |
| 4 | Brightness | Soft-power curve (blend toward white/black) |
| 5 | Contrast | Scale quanh midpoint 0.45 (bảo vệ midtone chân dung) |
| 6 | Saturation | Luma-preserving saturation scale |
| 7 | `unsharpMask(id, Sh)` | Unsharp mask trên skin pixels |
| 8 | `vignette(id, 0.08)` | Tối nhẹ góc ảnh (portrait feel) |

**Lưu ý:** `applyFilters()` áp dụng lên toàn bộ pixel kể cả vùng nền. Sau khi enhance trong auto pipeline, cần **khôi phục nền sạch** (xem mục 3.4 Phase 2).

### 3.9 Smart Beautify — `smartBeautify()`

```
analyzeDeep(G.base)
  → zone definitions: face zone (25-75% W, 8-62% H), skin zone (20-80% W, 5-80% H)
  → histogram p5/p95 → contrast range
  → isSkin(r,g,b) → skin ratio, skin lum std-dev
  → bạch đàn neutral pixels → warmth correction
  → trả về: { brightness, contrast, saturation, smooth, sharpness, warmth, highlights, shadows }

p.smooth = Math.max(p.smooth, 3)  // tối thiểu smooth vừa phải cho ảnh thẻ
applySliders(p) → applyFilters()
```

**Công thức smooth:**
- `sStd > 22` (da thô) → smooth = 3 + (sStd-22)*0.18
- `sStd > 14` (bình thường) → smooth = 1 + (sStd-14)*0.18
- `skinRatio > 0.04` → tối thiểu 2 (sau đó clamped lên 3 bởi pipeline)
- Hard cap: `[0, 8]`

Hiển thị stat badges sau khi áp: Sáng, Mịn, Sắc nét, Tông, Da lum, Vùng mặt.

### 3.10 Split-view — `updateMini()`

```
cvBefore  ← luôn hiển thị G.origSrc (ảnh gốc khi load, không đổi)
cvAfter   ← kết quả hiện tại
miniImg   ← thumbnail cvAfter (50% quality)
```

`G.origSrc` được set **một lần duy nhất** khi ảnh được load (`loadImg()` / `loadImageFromUrl()`). `updateMini()` dùng cache `_origImgEl` để tránh tạo lại Image object mỗi lần.

### 3.11 Canvas architecture

```
cvBefore  ← split-view trái (ảnh gốc)
cvAfter   ← split-view phải (kết quả)
workCv    ← canvas tạm cho AI (@imgly, face-api)
segCv     ← canvas tạm (không dùng sau khi chuyển sang @imgly)
```

---

## 4. employee_utils.py — Backend API

### `process_employee_photo(employee_id, employee_name, image_data, remove_bg)`

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

Response key là `file_url` (không phải `new_file_url`).

---

## 5. rembg — Background Removal (server-side)

Chạy trên server Python (CPU only, không cần GPU), gọi qua Frappe API.

```
POST /api/method/customize_erpnext.api.employee.employee_utils.remove_bg_rembg
Args: image_data (base64 JPEG dataUrl), model_name
Returns: base64 PNG dataUrl với alpha channel
```

### Models đã cache (`~/.u2net/`)

| Model | File size | RAM/worker (thực đo) | Chất lượng tóc | Tốc độ |
|-------|-----------|----------------------|----------------|--------|
| `u2net` | 168 MB | ~500 MB | Tốt | Nhanh |
| `birefnet-portrait` | 928 MB | **~20 GB** ⚠️ | Rất tốt (huấn luyện riêng cho chân dung) | Chậm hơn |

> birefnet-portrait tiêu tốn ~20 GB RAM/worker khi inference (intermediate activation tensors) — không phải ~1-2 GB như ước tính từ file size.

### Session cache & CPU threads

Model được cache trong process memory (`_rembg_sessions` dict) — chỉ load lần đầu mỗi worker.

```python
_REMBG_ORT_THREADS = {
    'birefnet-portrait': max(1, CPU_CORES // 2),  # 8 threads × 2 workers
    'u2net':             max(1, CPU_CORES // 4),  # 4 threads × 10 workers
}
```

### Multi-client safety

3 cơ chế bảo vệ đồng thời:

1. **Batch lock** (`_REMBG_LOCK_KEY`): chỉ cho phép **1 batch** chạy tại một thời điểm — user thứ 2 nhận cảnh báo và phải chờ.
2. **Single-edit guard** (`_REMBG_ACTIVE_KEY`): nếu ai đang dùng photo editor (có rembg inference trong vòng 120s), **batch mới bị chặn** để tránh OOM.
3. **Cleanup guard**: `cleanup_rembg_worker` không evict session nếu có inference trong 2 phút qua — tránh evict khi user đang dùng.

| Tình huống | Kết quả |
|-----------|---------|
| Batch vs Batch | Batch thứ 2 bị chặn |
| Single vs Single | Cho phép (mỗi request độc lập) |
| Single → Batch | Batch bị chặn nếu single dùng rembg < 120s trước |

```
POST batch_rembg_acquire_lock  →  { acquired: true/false, holder: { user, started_at } }
POST batch_rembg_release_lock  →  { ok: true }
```

Lock tự hết hạn sau 10 phút nếu client bị crash không release.

### RAM Management

- **Dynamic RAM guard**: sau mỗi inference birefnet, nếu RAM > 70% → evict session ngay lập tức.
- **Post-batch eviction**: `batch_rembg_release_lock` xóa session + set `_REMBG_EVICT_KEY` để tất cả workers evict lazy.
- **Manual eviction**: nút **Làm mới** (refresh) gọi `cleanup_rembg_worker()` × (worker_count × 2) lần — đảm bảo hit tất cả workers theo round-robin.
- **Idle eviction**: sau 15 phút không có inference → scheduler set evict flag, workers evict khi nhận request tiếp theo.

### Warm-up birefnet-portrait

```bash
cd /home/frappe/frappe-bench
./env/bin/python -c "from rembg import new_session; new_session('birefnet-portrait'); print('done')"
```

---

## 6. Debug nhanh

| Vấn đề | Kiểm tra |
|--------|---------|
| CSRF error 403 | Đảm bảo dùng FormData (không phải JSON header) |
| Session hết hạn | HTTP 403 → `location.reload()` tự động |
| Ảnh không cập nhật sau lưu | `refreshPhotoCardImage`, cache `?t=timestamp` |
| @imgly model không load | Network tab → `/assets/customize_erpnext/bg_removal/` phải 200 |
| `Invalid base URL` | `publicPath` phải là URL tuyệt đối (`location.origin + ...`) |
| Face detect thất bại | Console `[runAutoPipeline] face detect failed` → crop thủ công |
| Nút Edit/Delete không hiện sau upload | `refreshPhotoCardImage` dùng `addEventListener` (không phải setAttribute) |
| Nền bị màu drift sau enhance | Kiểm tra logic restore alpha trong `continueAutoPipeline` |
| Upload hàng loạt bỏ qua file | Tên file phải bắt đầu bằng `TIQN-XXXX` |
| Camera không hoạt động | Cần HTTPS, kiểm tra `navigator.mediaDevices` |
| postMessage không nhận | Kiểm tra `EDITOR_READY` → `sendToEditor()` flow |

---

## 7. Multi-select & Batch ID Photo (thêm trong session này)

### 7.1 Multi-select

Bật/tắt chế độ chọn nhiều ảnh:
```
btnMultiSelect → enterMultiSelect()
  → gallery thêm class .multi-select-active
  → ẩn .edit-btn / .upload-btn / .delete-btn (tránh overlap với checkbox)
  → hiện .bulk-toolbar (bottom bar)
```

Chọn card: `onCardClick(empId)` → `toggleCardSelect(empId)` → `updateBulkToolbar()`

Hành động hàng loạt:
- **Tải về thiết bị**: `downloadSelectedPhotos()` → fetch ảnh → blob → `<a download>`
- **Tạo ảnh thẻ**: `startBatchIdPhoto()` → mở batch modal 2 bước

### 7.2 Batch Modal — 2 bước

**Bước 1 — Chọn vùng cắt:**
- Hiển thị ảnh gốc + overlay crop box có thể kéo + resize
- Crop box mặc định: `computeDefaultCrop()` — ZOOM=0.58, faceY=srcH*0.25, sy=faceY-sh*0.22
- Kéo box: `batchCropDragStart/Move/End` — mouse & touch
- Resize box: 4 corner handles (nw/ne/sw/se), giữ tỉ lệ 3:4 khi resize
- Nút ✂️ Chỉnh: mở Cropper.js modal cho điều chỉnh chính xác từng ảnh
- Nút "Tiến hành xử lý": `confirmCropZones()` → bước 2

Footer bước 1 gồm:

- **Màu nền** (áp dụng khi composite):

| Swatch | Màu |
|--------|-----|
| Xám mặc định | `#f0f0f0` |
| Trắng | `#ffffff` |
| Xám nhạt | `#E8E8E8` |
| Xanh đậm | `#4A90D9` |

- **Engine xóa nền:**

| Button | Mô tả |
|--------|-------|
| `🖥 rembg (server)` | Server-side — mặc định |
| `JS (@imgly)` | Client-side (ẩn model selector) |

- **Model** (chỉ hiện khi chọn rembg):

| Button | Mô tả |
|--------|-------|
| `birefnet-portrait (928MB)` | Mặc định — chất lượng tóc tốt nhất |
| `u2net (168MB)` | Nhẹ, nhanh, ít RAM |

- **Concurrency** (tự động theo model, không hiển thị UI):
  - `birefnet-portrait` → **2** (2 × 20 GB ≈ 40 GB, safe trên 64 GB)
  - `u2net` → **10** (10 × 500 MB ≈ 5 GB)

- **Giới hạn**: tối đa **10 ảnh** mỗi lần batch.

> **Lý do giới hạn 10 ảnh**: Giới hạn 10 ảnh + concurrent=2 kiểm soát số workers bị load birefnet. OOM thực tế xảy ra với 12 ảnh (3 workers × 20 GB = 60 GB > 64 GB).

**Bước 2 — Duyệt kết quả:**
- Mỗi ảnh được xử lý: canvas crop → remove bg (AI) → white bg → beautify
- Concurrency = 3 workers song song
- Kết quả hiển thị dạng grid, có Duyệt / Bỏ qua per card
- "Cập nhật thư viện": `saveBatchApproved()` → cập nhật gallery UI (file đã lưu trong bước xử lý)

### 7.3 Pipeline xử lý ảnh (client-side, batch)

```
applyCropToPhoto(url, sx, sy, sw, sh)
  → canvas drawImage → 600×800 JPEG (croppedDataUrl)

processPhotoFull(croppedDataUrl)
  → batchRemoveBg(imageData)   — @imgly, publicPath local CDN
  → composite on #f0f0f0 background
  → _batchAnalyzeDeep(imageData) → params
  → _batchApplyFilters(imageData, params)
  → return JPEG dataUrl

callFrappeMethod(process_employee_photo, { image_data: processedDataUrl, remove_bg: 0 })
  → save to server → return file_url
```

Các hàm xử lý ảnh trong batch (`_batch*`) là port trực tiếp từ `photo_editor.html`:
- `_batchCv`, `_batchClamp`, `_batchIsSkin`
- `_batchBoxBlur`, `_batchSkinSmooth`, `_batchUnsharpMask`
- `_batchShadowsHighlights`, `_batchAnalyzeDeep`, `_batchApplyFilters`

@imgly được warm-up ngầm sau 3 giây khi trang load (module loader riêng `__batchImglyLoader`).

### 7.4 Crop Box Overlay — `updateCropBoxOverlay(empId)`

Ảnh hiển thị bằng `object-fit: contain` → có letterbox. Hàm tính offset letterbox:
```javascript
scale = min(wrapW / imgNW, wrapH / imgNH)
letterX = (wrapW - imgNW * scale) / 2
letterY = (wrapH - imgNH * scale) / 2
// Từ source coords (sx,sy,sw,sh) → CSS px:
left   = letterX + sx * scale
top    = letterY + sy * scale
width  = sw * scale
height = sh * scale
```

### 7.5 Lỗi thường gặp

| Vấn đề | Nguyên nhân | Fix |
|--------|-------------|-----|
| Vùng crop quá lớn | ZOOM=0.75 cũ | Đã sửa → ZOOM=0.58 |
| Crop quá thấp (thấy vai không thấy mặt) | faceY=0.35 cũ | Đã sửa → faceY=0.25, sy=faceY-sh*0.22 |
| Nền trắng thay vì xám | fillStyle='#ffffff' | Đã sửa → '#f0f0f0' |
| Batch không xóa nền | backend không có remove_bg | Dùng @imgly client-side trong processPhotoFull |
| Count sai (914/916 cho 29 ảnh) | Object.keys().length tăng dần | Dùng _batchTotal = photos.length cố định |
| Modal không scroll | flex:1 thiếu min-height:0 | Thêm min-height:0 trên .batch-grid |

---

## 6. Cài đặt ban đầu (lần đầu deploy)

```bash
# 1. Tải model @imgly (~211MB)
python3 apps/customize_erpnext/customize_erpnext/scripts/download_imgly_models.py

# 2. Build assets
bench build --app customize_erpnext

# 3. Tải face-api.js và model SSD MobileNet v1
#    Đặt vào: apps/customize_erpnext/customize_erpnext/public/face_api/
#    - face-api.esm.js  (từ vladmandic/face-api github releases)
#    - models/ssd_mobilenetv1_model-weights_manifest.json
#    - models/ssd_mobilenetv1_model.bin
bench build --app customize_erpnext
```

---

## Requirements

- Python: `rembg>=2.0.0`, `Pillow`
- rembg models: tự download vào `~/.u2net/` lần đầu sử dụng
- RAM khuyến nghị: **64 GB**

```
RAM peak = concurrent × RAM_per_worker + base (~1.5 GB)
# u2net:              10 × ~500 MB + 1.5 GB ≈  6.5 GB
# birefnet-portrait:  2 × ~20 GB  + 1.5 GB ≈ 41.5 GB  ← safe
# birefnet-portrait:  3 × ~20 GB  + 1.5 GB ≈ 61.5 GB  ← OOM (đã xảy ra thực tế với 12 ảnh)
```

- Server: CPU only (không cần GPU)
- Frappe CSRF: dùng FormData (không dùng JSON + header)
