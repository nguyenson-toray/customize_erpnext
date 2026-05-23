# Kế hoạch tích hợp PaddleOCR + VietOCR để đọc ảnh CCCD

> Repo tham khảo: https://github.com/thigiacmaytinh/Vietnamese-CitizenID-Recognition
> Bài hướng dẫn: https://thigiacmaytinh.com/huong-dan-su-dung-api-doc-cccd-bang-ocr/

---

## 1. Tổng quan hệ thống OCR

Hệ thống dùng 2 model kết hợp:
- **PaddleOCR** (Paddle AI): Phát hiện và định vị vùng văn bản trên ảnh (detection)
- **VietOCR** (seq2seq): Nhận dạng nội dung từng vùng text tiếng Việt (recognition)
- Chạy local server (Django REST), nhận ảnh upload → trả JSON

**Các trường OCR đang trích xuất được (từ MẶT TRƯỚC CCCD):**

| Trường JSON | Nội dung | Ghi chú |
|---|---|---|
| `ID_number` | Số CCCD 12 số | Regex detect số |
| `Name` | Họ tên | ✅ |
| `Date_of_birth` | Ngày sinh DD/MM/YYYY | ✅ |
| `Gender` | Giới tính Nam/Nữ | ✅ |
| `Nationality` | Quốc tịch | Việt Nam |
| `Place_of_origin` | **Quê quán** | ✅ đây là dòng "Quê quán" mặt trước |
| `Place_of_residence` | **Nơi thường trú** | ✅ địa chỉ hộ khẩu |

---

## 2. Đánh giá 3 trường cần đọc thêm

### 2a. Địa chỉ nguyên quán (`Place_of_origin`) — **ĐỌC ĐƯỢC ✅**

- Dòng "Quê quán" in trên mặt TRƯỚC của CCCD chip
- OCR đã có logic parse: tìm keyword `Quê|origin|ongin`
- Kết quả trả về dạng text thuần, ví dụ: `"Xã Bình Nguyên, Bình Sơn, Quảng Ngãi"`
- **Áp dụng được** → có thể dùng `search_address_by_text` API hiện có để convert sang mã mới 2025

### 2b. Ngày hết hạn (`expiry_date`) — **CHƯA CÓ trong repo, nhưng KHẢ THI ⚠️**

- Ngày hết hạn nằm mặt TRƯỚC CCCD, dòng cuối: `"Có giá trị đến: DD/MM/YYYY"`
- Repo hiện tại **KHÔNG parse** trường này (không có regex cho "Có giá trị đến" hay "Valid until")
- Nhìn vào `Extractor.py`: regex `regex_dob = r'[0-9][0-9]/[0-9][0-9]'` chỉ bắt ngày sinh
- **Cần thêm**: một regex/logic riêng detect keyword `giá trị|valid|đến ngày` để bắt ngày hết hạn
- Nếu tự triển khai server OCR thì hoàn toàn **có thể thêm** được

### 2c. Nơi cấp (`Place_of_issue`) — **KHÔNG ĐỌC ĐƯỢC ❌**

- Nơi cấp in ở **MẶT SAU** CCCD chip
- Mặt sau ghi: "Cục Cảnh sát quản lý hành chính về trật tự xã hội" (cố định với chip CCCD mới)
- Repo này **chỉ xử lý mặt trước** — không có flow nào cho back image
- Với CCCD mới (chip), nơi cấp luôn là `"Cục cảnh sát QLHC về TTXH"` → **có thể hardcode** dựa trên số CCCD bắt đầu bằng 0

> **Lưu ý:** Với QR code hiện tại, nơi cấp đã được tự động set khi quét QR (logic trong `_fillFromCCCD`). OCR không cần thiết cho trường này.

---

## 3. So sánh QR code vs OCR Image

| Trường | QR Code (hiện tại) | OCR Image (repo này) |
|---|---|---|
| Số CCCD | ✅ chính xác 100% | ⚠️ có thể nhầm O/0 |
| Họ tên | ✅ | ✅ |
| Ngày sinh | ✅ ISO format | ✅ DD/MM/YYYY |
| Địa chỉ thường trú | ✅ + convert 2025 | ✅ text thuần, cần convert |
| **Quê quán** | ❌ không có | ✅ **ĐỌC ĐƯỢC** |
| **Ngày hết hạn** | ❌ không có | ⚠️ cần thêm code |
| Nơi cấp | ⚠️ auto từ logic | ❌ không đọc được (mặt sau) |
| Tốc độ | ⚡ tức thì | 🐢 2-5 giây (CPU inference) |
| Phụ thuộc | Không cần server | Cần deploy thêm service |

---

## 4. Kiến trúc tích hợp đề xuất

```
Browser (nhân viên)
  │
  ├─ [Camera QR scan]  ──→ _parseVnCCCDQR() → fill CCCD, DOB, địa chỉ hộ khẩu (hiện tại)
  │
  └─ [Upload ảnh CCCD] ──→ POST /api/ocr_cccd (Frappe)
                                 │
                                 └─→ requests.post(OCR_SERVICE_URL, files=...)
                                           │
                                     OCR Service (Python/Django)
                                     PaddleOCR + VietOCR
                                           │
                                     JSON response:
                                     Place_of_origin, Date_of_birth, ...
                                           │
                                     Frappe API trả về frontend
                                           │
                                  → _fillFromOCR(data)
                                    fill: quê quán, ngày hết hạn (nếu thêm)
```

**2 service riêng biệt:**
- **Frappe app** (hiện tại, port 8000): Web form, API, ERPNext
- **OCR service** (mới, port 8001): Django + PaddleOCR + VietOCR

---

## 5. Các bước triển khai

### Bước 1: Deploy OCR service

```bash
git clone https://github.com/thigiacmaytinh/Vietnamese-CitizenID-Recognition.git
cd Vietnamese-CitizenID-Recognition
pip install -r requirements.txt
# Download seq2seqocr.pth (~300MB) vào server/module/CCCD/
cd server && start.bat  # hoặc python manage.py runserver 8001
```

### Bước 2: Thêm parse ngày hết hạn vào Extractor.py

Thêm vào `GetInformationAndSave()` trong `Extractor.py`:

```python
result['Expiry_date'] = ''

# Sau vòng lặp hiện có, thêm:
if re.search(r'giá trị|valid|đến ngày|hết hạn', s, re.IGNORECASE):
    expiry_match = re.search(r'\d{2}/\d{2}/\d{4}', s)
    if not expiry_match and i+1 < len(_results):
        expiry_match = re.search(r'\d{2}/\d{2}/\d{4}', _results[i+1][0])
    if expiry_match:
        result['Expiry_date'] = expiry_match.group()
```

### Bước 3: Frappe proxy API (`self_update_api.py`)

```python
@frappe.whitelist(allow_guest=True)
def ocr_cccd_image(image_base64):
    """Proxy call to local OCR service."""
    import base64, requests, tempfile, os

    OCR_SERVICE_URL = frappe.db.get_single_value(
        "Employee Self Update Setting", "ocr_service_url"
    ) or "http://localhost:8001"

    img_data = base64.b64decode(image_base64)
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp.write(img_data)
        tmp_path = tmp.name

    try:
        with open(tmp_path, "rb") as f:
            resp = requests.post(
                f"{OCR_SERVICE_URL}/api/idcard/extract/",
                files={"image": f},
                timeout=30
            )
        resp.raise_for_status()
        return resp.json()
    finally:
        os.unlink(tmp_path)
```

### Bước 4: Frontend — nút "Chụp/Upload ảnh CCCD"

Thêm vào `renderCCCDSection()` trong `index.html`:

```html
<div style="margin-top:10px">
  <label style="font-size:13px;font-weight:600;color:var(--gray-600)">
    Hoặc chụp ảnh CCCD để đọc thêm thông tin (quê quán, ngày hết hạn):
  </label>
  <input type="file" id="cccd_image_upload" accept="image/*" capture="environment"
    onchange="onCCCDImageUpload(this)" style="margin-top:6px">
  <div id="ocr_status" style="display:none;font-size:12px;color:#64748b;margin-top:4px"></div>
</div>
```

```javascript
async function onCCCDImageUpload(input) {
  if (!input.files[0]) return;
  const statusEl = document.getElementById("ocr_status");
  statusEl.textContent = "⏳ Đang đọc ảnh CCCD..."; statusEl.style.display = "";
  try {
    const base64 = await fileToBase64(input.files[0]);
    const result = await api(
      "customize_erpnext.api.self_update.self_update_api.ocr_cccd_image",
      { image_base64: base64.split(",")[1] }
    );
    _fillFromOCR(result);
    statusEl.textContent = "✅ Đọc ảnh thành công.";
  } catch (e) {
    statusEl.textContent = "❌ Không đọc được ảnh. Thử lại hoặc nhập tay.";
    console.error(e);
  }
}

function _fillFromOCR(data) {
  // Quê quán → fill origin_address village (text thuần, chờ user chọn tỉnh/xã)
  if (data.Place_of_origin) {
    sv("addr_ori_village", data.Place_of_origin);
    // Thử convert địa chỉ quê quán sang province/commune
    const parts = data.Place_of_origin.split(",").map(s => s.trim()).filter(Boolean);
    if (parts.length >= 2) {
      const prov = parts[parts.length - 1];
      const dist = parts.length >= 3 ? parts[parts.length - 2] : "";
      const ward = parts.length >= 4 ? parts[parts.length - 3] : "";
      _convertAddressForSection(ward, dist, prov, parts.slice(0,-3).join(", "), "ori");
    }
  }
  // Ngày hết hạn (nếu có)
  if (data.Expiry_date) {
    // Convert DD/MM/YYYY → YYYY-MM-DD
    const [d, m, y] = data.Expiry_date.split("/");
    sv("id_card_expiry_date", `${y}-${m}-${d}`);
  }
}
```

### Bước 5: Thêm field `ocr_service_url` vào Employee Self Update Setting

```json
{
  "fieldname": "ocr_service_url",
  "fieldtype": "Data",
  "label": "OCR Service URL",
  "description": "URL của OCR service (mặc định: http://localhost:8001)"
}
```

---

## 6. Yêu cầu tài nguyên

| Thành phần | Yêu cầu |
|---|---|
| Python | 3.8.x (64-bit) |
| RAM | ~2GB (PaddleOCR + VietOCR load vào memory) |
| Disk | ~500MB (model files) |
| CPU | Khả dụng (không cần GPU) |
| Thời gian xử lý | 2-5 giây/ảnh trên CPU |
| OS | Windows / Linux |

> Lưu ý: PaddleOCR tại thời điểm repo này dùng version `>=2.0.1`, cần `PyMuPDF==1.21.1` để tránh conflict.

---

## 7. Kết luận & Ưu tiên

| Mục tiêu | Khả thi | Mức độ ưu tiên |
|---|---|---|
| Đọc quê quán từ ảnh CCCD | ✅ Có sẵn trong repo | Trung bình — QR không có trường này |
| Đọc ngày hết hạn | ✅ Thêm ~10 dòng code | Thấp — ít dùng trong HR |
| Đọc nơi cấp từ ảnh | ❌ Cần mặt sau + thêm nhiều code | Không cần — đã có logic tự động |
| Fallback khi QR không quét được | ✅ OCR đọc được hầu hết trường | Cao nếu nhiều CCCD cũ/hỏng QR |

**Khuyến nghị:** Chỉ triển khai nếu có nhu cầu cụ thể đọc **quê quán** (hiện QR không có) hoặc làm fallback cho CCCD không có QR. Với dự án hiện tại, QR code đã đủ cho 90% use case.
