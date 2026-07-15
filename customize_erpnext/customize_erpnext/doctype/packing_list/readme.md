# Packing List — Module Documentation

Chức năng **độc lập** (không link DocType ERPNext có sẵn) để lập **Packing List** xuất hàng
thành phẩm. Mỗi mặt hàng phân rã theo **màu × size**; hệ thống tự xếp thùng carton, tính
khối lượng/CBM/số container, cho **chụp ảnh mỗi thùng** và **đọc số cân (OCR)**.

Module: `Customize Erpnext`. Code: `customize_erpnext/customize_erpnext/doctype/packing_list/`.

---

## 1. DocTypes

### Packing List (master, `autoname: format:{no}`)
- **Header:** `no` (ID = No, tự đổi tên khi sửa No — xem §9), `date`, `contract_no`, `style`,
  `destination`, `customer` (Data, không link), `description_of_goods`.
- **Carton config:** `carton_types` (child *Packing List Carton Type*), `container_type`
  (20GP/40GP/42GP/40HC/45HC), `combine_mode`, `small_carton_threshold`,
  `max_size_per_mixed_carton` (2/3/4), `weight_mode` (Net to Gross / Gross to Net).
- **Input:** `items_text` (Code), `weight_text` (Code).
- **Totals (read-only):** `total_quantity`, `total_carton`, `total_containers`,
  `total_net_weight`, `total_gross_weight`, `total_cbm`.
- **HTML ảo:** `total_carton_detail` (thùng nguyên/mix), `size_color_summary` (bảng qty size×màu).
- **Child:** `details` → *Packing List Detail*.

### Packing List Detail (child, 1 dòng = 1 thùng)
`carton_no`, `color`, `size`, `contents`, `pcs`, `net_weight` (read-only),
`gross_weight` (sửa tay được — từ cân), `empty_weight` (tare của thùng, read-only),
`cbm`, `carton_type` (nhãn `L*W*H`), `sku`, `upc` (Small Text — đa dòng), `photo` (Attach Image).

### Packing List Carton Type (child)
`length`, `width`, `height` (cm), `max_items` (sức chứa/thùng), `empty_weight` (tare kg),
`cbm` (read-only, tự tính). Dòng **đầu tiên** = loại thùng lớn/mặc định (theo thể tích).

---

## 2. Nhập liệu (copy-paste từ Excel, cột cách nhau bằng Tab)

**1. Items** (`items_text`) — mỗi dòng = 1 (màu + size):
```
Color   Size   Quantity   SKU            UPC
Boundary Black   SM   39   200333-116-SM   196926047493
```
- SKU/UPC tùy chọn. Dòng header tự bỏ qua. Trùng (màu,size) → cộng dồn.
- Thứ tự size/màu = theo lần xuất hiện đầu tiên.

**2. Net Weight per Piece** (`weight_text`) — khối lượng 1 cái theo size:
```
Size   Weight
SM   0.4
```
- Thiếu size đang dùng → **Generate báo lỗi** (tránh Net = 0 âm thầm).

Parser: `_parse_items()` → `(qty_map, sizes, colors, sku_map)`; `_parse_weight()` → `{size: kg}`.

---

## 3. Thuật toán xếp thùng (`build_cartons`)

1. **Thùng nguyên (đầy):** mỗi (màu,size,qty) → `qty // cap` thùng đầy `cap` cái
   (`cap` = max_items của thùng lớn). Phần dư `qty % cap` → hàng lẻ.
2. **Ghép hàng lẻ** theo `combine_mode` (`_combine_leftovers`):
   - **No Combine:** mỗi phần lẻ 1 thùng riêng.
   - **By Color:** ghép các size cùng màu.
   - **By Size:** ghép các màu cùng size.
   - **By Color & Size:** ghép tất cả.
   - Dùng **First-Fit-Decreasing** — **không bao giờ xé lẻ 1 (màu,size) ra 2 thùng**.
   - Mỗi thùng ghép chứa **tối đa `max_size_per_mixed_carton`** size khác nhau.
3. **Chọn loại thùng** (`_pick_box`, khi có ≥2 loại): thùng **đầy → thùng lớn**;
   thùng **chưa đầy → thùng nhỏ** nếu tổng pcs ≤ `small_carton_threshold`
   (0 = mọi thùng chưa đầy dùng thùng nhỏ), và ≤ sức chứa thùng nhỏ.
4. **Sắp xếp:** thùng nguyên (theo màu→size) trước → thùng ghép sau, gom theo loại thùng.
   Đánh số `carton_no` tuần tự.
5. Mỗi thùng: `net = Σ(pcs_size × weight_size)`, `gross = net + empty` (tare),
   `cbm = L×W×H/1.000.000`. `total_containers = ceil(total_cbm / dung_tích_container)`
   (20GP≈28, 40GP≈58, 42GP≈58, 40HC≈68, 45HC≈86 — hằng số trong code).

---

## 4. Bảng chi tiết & hiển thị

- **Thùng nguyên:** 1 màu + 1 size; `contents` **để trống**; `sku`/`upc` là giá trị đơn.
- **Thùng ghép:** `color`/`size` liệt kê các giá trị cách nhau `, `;
  `contents`/`sku`/`upc` **đa dòng** (mỗi item 1 dòng, `\n`), Contents dạng `Color-Size: qty Pcs`.
  (Small Text → in ra `<br>`; CSV export dùng `:` không dùng `×`.)
- `validate` (`_recalc_totals`): cộng lại tổng; xóa Contents ở dòng không phải mix;
  nếu `weight_mode = Gross to Net` → `net = gross − empty` (xem §6).
- **Size/Color Summary** (`get_size_color_summary_html` + JS): bảng pivot qty size×màu, có Total.
- **Total Carton Detail** (JS): số thùng nguyên vs thùng ghép.

---

## 5. Edit Mix (chỉnh tay thùng ghép)

Dialog ma trận (thùng ghép × mảnh lẻ). `apply_mix_edit`:
- Giữ thùng nguyên (dựng lại từ color/size/pcs); pool = pieces trong các thùng mix hiện tại.
- Bắt buộc **bảo toàn** (tổng pieces đã xếp = pool) và mỗi thùng ≤ sức chứa loại thùng.

---

## 6. Khối lượng: Net ↔ Gross (`weight_mode`)

- **Net to Gross (mặc định):** Net = Σ(pcs × net/size) từ bảng cân nặng; Gross = Net + tare.
  Gross **chỉ được set lúc Generate** — không chỗ nào tính lại (để user sửa tay được).
- **Gross to Net:** nhập **Gross** (từ cân) → **Net = Gross − tare** (`empty_weight`).
  Tính live khi gõ Gross trong lưới, và khi lưu (`_recalc_totals`).
- **Guard:** `Gross ≤ 0` → **Net = 0** (không trừ tare thành **số âm**). Ở cả server
  (`_recalc_totals`) lẫn client (sự kiện `gross_weight`).

> ⚠️ **Đổi `weight_mode` là thao tác PHÁ DỮ LIỆU.** Chuyển sang *Gross to Net* khi chưa cân
> (Gross = 0) → `net = gross − tare` **ghi đè Net lý thuyết thành 0**, mất vĩnh viễn. Sau đó
> quay lại *Net to Gross* thì `Gross = Net + tare = 0 + tare` = chỉ còn tare. Đã gặp thật.
> **Cứu bằng `recalc_weights`** (nút *🧹 Tính lại Gross từ Net*) — tính Net lại **từ bảng cân
> nặng × pcs**, nguồn sự thật duy nhất không bị phá; **giữ nguyên ảnh & số thùng** (khác
> Generate — Generate **xoá sạch ảnh**). Đây cũng là cách áp bảng cân nặng đã sửa lên một
> list đã chụp ảnh xong.

**Nút reset (theo mode):**

| `weight_mode` | Nhãn nút | Hành vi |
|---|---|---|
| Gross to Net | **🧹 Xoá toàn bộ Gross** | Gross = 0, Net = 0 → cân lại. Ảnh giữ nguyên |
| Net to Gross | **🧹 Tính lại Gross từ Net** | `recalc_weights`: Net = bảng × pcs, Gross = Net + tare |

---

## 7. Ảnh thùng + OCR số cân

**Chụp/Cân (JS):** một nút gộp *📷 Chụp / Cân* → **tích 1 dòng thùng** (hoặc **chưa tích →
nhập số thùng bắt đầu**, mặc định = thùng đầu chưa có ảnh) → mở dialog với:
- **Chế độ** (nhớ `localStorage.pl_capture_mode`): *Chụp ảnh + Cân* / *Chỉ chụp ảnh* /
  *Chỉ cân* (chỉ hiện *Chỉ cân* khi có cân — xem §7b).
- **Liên tiếp (tự sang thùng kế)** (nhớ `localStorage.pl_capture_cont`): làm cả loạt **không
  phải chọn từng thùng**. *Chỉ cân* + Liên tiếp = cân cả lô bằng **Enter** (Esc thoát);
  *Chụp…* + Liên tiếp = lưu xong tự mở thùng kế.

Chụp: camera (getUserMedia; fallback camera thiết bị trên HTTP; có dropdown chọn webcam) →
crop khung thùng → resize ≤1600px, JPEG 0.88. Panel cân live ngay trong dialog (cân trước,
chụp & lưu sau; số ST tự điền, sửa tay được). Camera được **tắt sạch khi đóng dialog** (có cờ
`closed` chặn race `getUserMedia` resolve sau khi đóng). Save gom qua `pl_save()` tránh đua nhau.

**Crop (`PL_CROP_RATIO = 3/4`):** khung **3:4 dọc** (chuẩn 600×800), `autoCropArea: 0.85`.
> Trước dùng `autoCropArea: 1` → khung crop **phủ kín ảnh** → bấm Lưu mà không kéo khung thì
> "vùng crop" = cả ảnh → **lưu y hệt ảnh gốc**. Đúng lỗi user báo *"ko lưu đúng vùng crop"*.

**Nút 🔄 Chụp lại** ở **cả 2** dialog — ảnh mờ / thiếu mặt cân / OCR sai thì chụp lại ngay,
khỏi đóng rồi bắt đầu lại:
- Dialog **cắt ảnh**: `set_secondary_action` (Frappe `.off("click")` trước khi gắn nên thay hẳn
  nút đóng; vẫn đóng được bằng ✕ ở header).
- Dialog **đọc kg**: nút cạnh *Đọc lại số cân*. Phân biệt rõ: **🔄 Đọc lại** = OCR lại **cùng ảnh**
  (rẻ); **📷 Chụp lại** = chụp **ảnh mới** (ghi đè ảnh cũ theo prefix, không sinh file rác).

**Cropper.js:** hooks.py **đã bỏ include toàn cục**, và `ensure_cropperjs()` chỉ có trong
`employee.js` (chỉ nạp ở DocType Employee) → Packing List báo *"Cropper.js chưa được tải"*.
Đã có `pl_ensure_cropper()` tự nạp bản self-host `/assets/customize_erpnext/cropperjs/`.

**Độ phân giải camera (`PL_CAM_RES`)** — quyết định OCR đọc được hay không:
- Xin `{width:{ideal:3840}, height:{ideal:2160}}`. **`ideal` = xin cái gần nhất**, không phải trần
  → để số thấp là **tự bó chân**. Webcam 1080p vẫn trả 1920×1080; điện thoại 4K thì cho 4K.
- Không set gì → trình duyệt hay trả **640×480** → chữ số cân chỉ 12–30px → **OCR ra rác**.
- `getUserMedia` chỉ lấy được **luồng video** (≤1080p/4K), **không phải full cảm biến 12–48MP**
  — ảnh full sensor chỉ có qua app camera gốc (nhánh `carton_file_input`).
- Dialog hiện **độ phân giải thực nhận được**; cạnh ngắn < 1000px → cảnh báo đỏ.
- Giá phải trả: OCR upload nguyên khung base64 (1080p ≈ 0.3–0.5MB; 4K ≈ 2–4MB). Ảnh *lưu*
  không ảnh hưởng (đã crop + cap 1600px).

**Lưu (`save_carton_photo`):** File tại `/private/files/packing_list/`, tên
**`{No}_{CartonNo}_{kg}kg_{Color}_{Size}.jpg`** (vd `PL01_12_9.43kg_Redrock_XXL.jpg`) —
**số kg đứng ngay sau số thùng**, 2 chữ số thập phân (`_photo_name()`).
Chụp lại cùng thùng → **xóa ảnh cũ + kg cũ** (dọn theo prefix `{No}_{CartonNo}_`, không phụ
thuộc kg nên đổi cân vẫn khớp). Sau khi lưu: **clear checkbox + tự tích thùng kế** (`select_next_carton`).

**kg trong tên file — luôn khớp Gross, bất kể kg đến từ đâu:**
- `_sync_photo_names()` chạy trong **`on_update`**: mỗi lần lưu, so tên mong muốn với tên trong
  URL sẵn có trên dòng; **lệch mới** gọi `rename_carton_photo`. Khớp rồi thì **tốn 0 query**.
- Vì sao cần: luồng **OCR lưu ảnh TRƯỚC khi biết kg**, nên file mang `gross_weight` tại thời
  điểm đó = **Gross lý thuyết** từ Generate. `rename_carton_photo` chỉ chạy khi bấm *Áp dụng
  vào Gross* → OCR bị từ chối / gõ tay ở lưới thì **tên file giữ số lý thuyết = nói dối**.
  Gặp thật: file `..._8_12.20kg_...` trong khi cân hiển thị **12.53**.
- `download_all_photos` vẫn đặt tên entry từ `gross_weight` **hiện tại** → zip luôn đúng.

**OCR (`read_scale_ocr`, ssocr):** ngay sau lưu, dialog tự đọc số cân trên **cùng ảnh**.
Thư viện OCR = **`ssocr` v2.23.1** (binary `/usr/bin/ssocr`, chuyên LED 7 đoạn, chỉ đọc `0-9`).
numpy/scipy/Pillow lo tiền xử lý — **phần lớn độ chính xác nằm ở code ta, không ở ssocr**.

1. **Mặt nạ đỏ** `R−(G+B)/2 > 100` (`_red_mask` — **chỗ DUY NHẤT** biết tới màu; đổi cân LED
   màu khác chỉ sửa 2 dòng ở đây, xem §7c).
2. **Nhiều cụm ứng viên** (`_digit_regions`, tối đa 6, lớn→nhỏ). **KHÔNG cược vào cụm lớn nhất**
   — trong kho cụm đỏ lớn nhất thường là **thùng PCCC / bình chữa cháy** (đo: ảnh có PCCC =
   **15.308 px đỏ**, gấp **5×** ảnh thường ~3.000). Thử lần lượt tới khi có cụm đọc ra số.
   ⚠️ **Dilation phải theo TỈ LỆ ảnh** (`iters = min(shape)/100`, tối thiểu 6): khe giữa các chữ số
   giãn theo độ phân giải, nên mức cố định 10px **âm thầm hết bắc cầu** trên ảnh nét → dãy số
   **vỡ thành nhiều cụm** → lấy cụm lớn nhất = số **cụt**. Đo được: cùng 1 ảnh, 900×1600 thấy
   **4 ô**, phóng lên 2250×4000 chỉ còn **3 ô** → `12.53` đọc thành **`1.25`**.
3. **Cổng chặn hình dạng** cho từng cụm: `too_small` (chữ số < `MIN_DIGIT_PX` = 40px) ·
   `not_a_display` (rộng < 1.2× cao — dãy số 7 đoạn luôn rộng hơn cao).
4. **Đếm ô chữ số bằng hình học** (`_count_digit_cells` → `_digit_runs`) rồi ép **`ssocr -d N`**
   và **bắt buộc `len(digits) == N`**. Đây là thứ duy nhất bắt được lỗi **thiếu hẳn 1 chữ số**
   (đọc-sạch không thể thấy ký tự *bị mất*).
   ⚠️ Phải xét theo **CHIỀU CAO**, không đếm pixel: số **"1" chỉ sáng 2 đoạn** → rất ít pixel →
   lọc kiểu `sum > peak*0.2` **cắt oan số 1 đầu** → `11.79` thành `179` = **1.79**. Chữ số dù
   mảnh vẫn **cao bằng** nhau; đốm nhiễu & dấu chấm thì thấp.
5. `_read_strip`: resize chữ số ~150px + **ensemble** (closing / ±3° / `-t` 30·50·70) → bỏ phiếu.
   **Chỉ nhận bản đọc sạch** — `'9y2'` KHÔNG được rút thành `'92'` (=0.92 thay vì 9.43).
6. **Chia 10^decimals** (luôn **2** → `586` = 5.86 kg).

> **KHÔNG dùng mỏ neo Gross dự kiến làm chỗ dựa.** Đa số nhập **Gross rồi suy Net**, nên
> `weight_text` thường vắng hoặc chỉ áng chừng → mỏ neo không đáng tin. Mọi cổng chặn ở trên
> đều **tự thân** (hình học ảnh), không cần biết thùng nặng bao nhiêu.

**Lỗi OCR còn lại (chưa xử lý):** sai **giá trị** 1 chữ số mà **đúng số ô** — vd `9` → `0`
(khác nhau đúng **1 đoạn giữa**; đoạn mờ là thành 0). Cell-count không bắt được. Gặp khi
**chụp lại màn hình máy tính** (ảnh của ảnh: moiré + 2 lần nén). Chụp cân thật thì chưa gặp.

**Kết quả đo trên ảnh thật (ground truth):**

| Ảnh | Chữ số | px đỏ | Kết quả |
|---|---|---|---|
| Nền carton, 1920×2560 | 63px | 3.040 | **5.83** ✅ |
| Nền carton, 1920×2560 | 59px | 2.706 | **5.84** ✅ |
| **Nền có thùng PCCC** | 184px* | 15.308 | **5.86** ✅ (bỏ qua cụm PCCC) |
| 900×1600, 3 chữ số | 45px | 1.858 | **3.94** ✅ (45px vẫn đọc được → ngưỡng 40 hợp lý) |
| 900×1600, 4 chữ số | 37–38px | — | ⚪ từ chối (`too_small`) — đúng mực |
| ↑ ảnh đó phóng ×2.5 | ~95px | — | **12.53** ✅ (trước khi sửa dilation: **1.25** ❌) |
| Ảnh cũ 480×640 | 10–31px | — | ⚪ từ chối — trước đây trả **số rác kèm `confident=True`** |

\* cụm lớn nhất là PCCC (168×184, cao hơn rộng) → bị loại, tìm tiếp ra mặt cân.

**Từng đọc sai như thế nào** (đều đã sửa, giữ đây để không tái phạm):

| Triệu chứng | Nguyên nhân thật |
|---|---|
| `9.43` → `0.92` | `re.sub(r"\D","")` **vứt ký tự lỗi** rồi vẫn tính (`'9y2'`→`'92'`) |
| `12.53` → `1.25` | **dilation cố định 10px** không bắc cầu nổi trên ảnh nét → dãy số vỡ cụm |
| `11.79` → `1.79` | `_trim_columns` lọc theo **tổng pixel** → **cắt oan số "1"** (ít pixel, vẫn cao) |
| chữ 12–13px → `8.88` "chắc chắn" | thiếu cổng `MIN_DIGIT_PX` |
| **lá cờ đỏ** → `8` | thiếu cổng `not_a_display` |

**Hướng dẫn chụp cho user** (hiện trong dialog chụp + khi OCR fail + nút Hướng dẫn):
**nền phía sau càng đơn giản càng tốt** — tránh vật đỏ (PCCC, bình chữa cháy, biển báo đỏ,
ống đỏ, áo đỏ); đứng **đủ gần** (chữ số ≥ 40px); chụp **thẳng**, không loá đèn.
- **Yêu cầu:** cài `ssocr` trên server (`sudo apt-get install ssocr`). ssocr hơi yếu với số **7**.
- **Dialog OCR chỉ hiện 1 nhắc nhở**: *"Đối chiếu số này với số đang hiển thị trên cân trước khi
  Áp dụng"* — không hiện raw/độ tin cậy/kg dự kiến. Đọc sai → **user tự sửa kg**.
- **Không có chức năng chụp cận** (đã bỏ): ảnh quá xa thì báo lý do và để user nhập tay.

**Tải tất cả (`download_all_photos`):** nén zip toàn bộ ảnh, tên file trong zip đúng chuẩn.
Nút bị chặn nếu chưa có ảnh nào.

**Xoá tất cả (`delete_all_photos`):** nút **🗑 Xoá tất cả ảnh** (có confirm, không hoàn tác):
1. Xoá **File records** attach vào Packing List → Frappe tự xoá **file trên đĩa** (`File.on_trash`).
2. Xoá **link `photo`** trên từng dòng thùng (`db.set_value`, `update_modified=False`).
3. **Quét dọn file mồ côi** còn sót trong `/private/files/packing_list/` theo prefix `{No}_`.
Client `frm.reload_doc()` sau khi xoá vì link được xoá thẳng dưới DB.

**Chọn webcam:** dialog camera có dropdown chọn nguồn (ưu tiên webcam USB ngoài); lưu
`deviceId` vào `localStorage.pl_camera_id`, lần sau tự dùng lại. Rút webcam → fallback
camera mặc định + báo nhẹ. Label camera chỉ hiện sau khi đã cấp quyền camera.

---

## 7b. Đọc cân trực tiếp (Web Serial API)

Lấy `gross_weight` **thẳng từ đầu cân Jadever** (JIK/JWI) qua cáp USB–RS232 (cổng COM),
**không cần app/bridge** cài trên máy — toàn bộ nằm trong JS của form (`navigator.serial`).
Chỉ chạy trên **Chrome/Edge + HTTPS**; Firefox/Safari không hỗ trợ → nút cân **tự ẩn**,
OCR (§7) vẫn dùng bình thường.

**Cấu hình (per-máy, lưu `localStorage.pl_scale_cfg` — KHÔNG lưu vào DocType):**
nút **⚙️ Scale Settings** → baudRate (mặc định **9600**), dataBits 8, parity none, stopBits 1;
`regex` parse dòng (4 nhóm: cờ ST/US · mode GS/NT · số · đơn vị). Mặc định:
`(ST|US)\s*,\s*(GS|NT)\s*,?\s*([+-]?\s*\d+(?:\.\d+)?)\s*(kg|g|lb)?`. Đơn vị `g` → tự ÷1000 về kg.
Nút **Test** hiện raw + kết quả parse live để chỉnh regex theo model đầu cân.

**Ổn định:** `plScale.readStableWeight({timeoutMs:8000, needConsecutive:3})` — chỉ chốt khi
nhận đủ **3 dòng ST liên tiếp cùng giá trị**; quá hạn → reject kèm 3 dòng raw gần nhất.
Trạng thái hiển thị badge trên form (đã kết nối / chưa kết nối / đang đọc); rút cáp →
đổi trạng thái, nối lại 1 chạm; F5/đóng tab → đóng cổng sạch (không lock COM).

**Field `weight_source`** (chỉ khi `weight_mode = Gross to Net`) — **2 lựa chọn, cả 2 đều
cho nhập kg tay:**

| weight_source | Luồng lấy Gross |
|---|---|
| **OCR** (mặc định) | Chụp → lưu ảnh → OCR đọc số cân trên **ảnh** (§7). Luôn nhắc **đối chiếu với mặt cân**; đọc sai/không đọc được → **nhập kg tay** |
| **Scale** | **Cân trước, chụp sau:** dialog chụp có panel cân live (ST/US), số ổn định tự điền, **sửa tay được** / 🔄 Cân lại → **📷 Chụp & Lưu** lưu ảnh + áp Gross cùng lúc. Chưa kết nối cân → nhập tay |

> Với **Scale**, việc đọc cân **gộp thẳng vào dialog chụp** (cân trước — chụp & lưu sau) khi chọn
> chế độ *Chụp ảnh + Cân*; hoặc chọn **Chỉ cân** (± Liên tiếp) để cân không cần ảnh.

**Đọc cân không cần ảnh** (đã gộp vào nút *📷 Chụp / Cân*, chế độ **Chỉ cân**):
- Không Liên tiếp: đặt thùng → số ST tự điền → **Ghi số cân** → ghi Gross + tự tích thùng kế.
- **Liên tiếp**: dialog giữ mở; đặt thùng → **Enter** = ghi + nhảy thùng kế, **Esc** = thoát —
  cân cả lô chục thùng không rời bàn phím. (Có busy-guard 350ms chống nhảy 2 thùng do double-Enter.)

**Kết nối:** lần đầu **⚙️ Scale Settings → Kết nối cổng COM** (cần user click chọn cổng).
Sau đó `getPorts()` tự nối lại cổng đã cấp quyền (không cần chọn lại). Áp Gross xong,
nếu Gross to Net → Net = Gross − tare (như §6).

**Cấu hình đầu cân Jadever:** vào menu đầu cân đặt chế độ in ra cổng RS232 là
**continuous / stream** (in liên tục), đúng baud (mặc định 9600, 8-N-1) để form nhận data
liên tiếp. Nếu đầu cân chỉ in khi bấm Print → mỗi lần cân phải bấm Print trên đầu cân.

**Khi nào Scale vs OCR:**

| | Scale (Web Serial) | OCR (ssocr) |
|---|---|---|
| Độ chính xác | Cao (số thật từ đầu cân) | Phụ thuộc ảnh; yếu số 7, ảnh xa |
| Phần cứng | Laptop + cáp USB-RS232 tới đầu cân | Chỉ cần ảnh có màn hình cân |
| Trình duyệt | Chỉ Chrome/Edge + HTTPS | Mọi trình duyệt |
| Dùng khi | Có bàn cân cố định nối cáp | Chụp bằng điện thoại / không nối cáp |

Module cân: `public/js/packing_list_scale.js` (nạp qua `hooks.doctype_js["Packing List"]`),
export `window.plScale`. **Client-side thuần — không thêm method Python.**

---

## 8. Chốt cartons trước khi chụp

- **Generate khi đã có ảnh:** client hiện **confirm Yes/No**; Yes → `generate_detail(force=1)`
  **xóa toàn bộ File ảnh cũ** rồi tạo lại. Không confirm/không force → server `throw`.
- Lý do: Generate lại đánh số/đổi cấu trúc thùng → ảnh & kg cũ không còn khớp.

---

## 9. Đặt tên & Print Format

- **Tên document = No** (`autoname: format:{no}`). Sửa No → `on_update` gọi `rename_doc`
  đổi tên theo (khác `field:no` vốn khóa field).
- **Print Format "Packing List":** A4 **ngang** (`orientation: landscape` trong `.print-format`),
  label căn trái + value sát label (CSS `.data-field` inline-block — chạy cả wkhtmltopdf),
  cuối trang có bảng **Quantity Summary (size×màu)** render server-side qua Jinja
  `{{ doc.get_size_color_summary_html() | safe }}`.

---

## 10. Server methods (whitelisted)

| Method | Vai trò |
|---|---|
| `generate_detail(doc, force=0)` | Xếp thùng + tổng; chặn/force khi đã có ảnh |
| `apply_mix(doc, cartons)` | Áp dụng chỉnh tay thùng ghép (bảo toàn) |
| `save_carton_photo(packing_list, carton_no, color, size, image, gross=0)` | Lưu ảnh thùng (tên có kg) |
| `rename_carton_photo(packing_list, carton_no, color, size, gross)` | Đổi tên ảnh theo Gross mới |
| `download_all_photos(packing_list)` | Zip tải tất cả ảnh (tên theo Gross hiện tại) |
| `delete_all_photos(packing_list)` | Xoá toàn bộ ảnh: File + file trên đĩa + link trong bảng |
| `read_scale_ocr(image, decimals=2, roi=None, packing_list=None, carton_no=None)` | OCR số cân (ssocr) |
| `recalc_weights(doc)` | Tính lại Net từ bảng cân nặng × pcs, Gross = Net + tare (giữ ảnh) |

> ⚠️ Thêm/đổi **method Python** → cần **`bench restart`** (web worker gunicorn `--preload`
> không tự nạp lại code; `clear-cache` chỉ xóa redis). Sửa JS/JSON → `clear-cache` + refresh.

---

## 11. Test OCR (ảnh thật)

```
doctype/packing_list/test_images/           PHẢI đọc đúng — tên file = kg thật trên mặt cân
    3.94_900x1600_45px.jpg
    5.83_nen-carton.jpg
    5.84_nen-carton.jpg
    5.86_nen-pccc-nhieu-vat-do.jpg          ← cụm đỏ lớn nhất là thùng PCCC
doctype/packing_list/test_images/too_far/   PHẢI từ chối — chữ số < 40px, không được đoán
    12.53_900x1600_37px_dep-croc-xanh.jpg
    12.53_900x1600_38px.jpg
doctype/packing_list/test_packing_list.py   → class TestScaleOCR
```

> ⚠️ **Tên file do app lưu KHÔNG phải ground truth.** `{No}_{CartonNo}_{kg}kg_...` mang Gross
> *tại thời điểm lưu* — có thể là Gross **lý thuyết** (xem §7). Ground truth phải **mở ảnh ra
> nhìn mặt cân**. Đã suýt encode kỳ vọng SAI vào test vì tin tên file (`..._8_12.20kg_...`
> trong khi cân hiện **12.53**).

- **Thêm ca test = thả thêm 1 ảnh** vào `test_images/` đặt tên `<kg>_<mô tả>.jpg` — kỳ vọng lấy
  từ chính tên file, **không cần sửa code**. Nên giữ lại các ảnh từng làm OCR sai.
- 2 test: (1) đọc đúng kg mọi ảnh mẫu; (2) ảnh bị thu nhỏ ×4 (~480×640 như ảnh cũ) **phải bị
  từ chối**, không được đoán bừa.
- Chạy: site production đang tắt test (`allow_tests`), chạy trực tiếp:
  ```bash
  cd sites && ../env/bin/python -c "
  import frappe, unittest
  frappe.init(site='erp.tiqn.local'); frappe.connect()
  from customize_erpnext.customize_erpnext.doctype.packing_list.test_packing_list import TestScaleOCR
  unittest.TextTestRunner(verbosity=2).run(unittest.TestLoader().loadTestsFromTestCase(TestScaleOCR))"
  ```
  Tự `skip` nếu máy chưa cài `ssocr`.

---

## 12. Files
```
doctype/packing_list/               packing_list.{json,py,js}, readme.md
                                    test_packing_list.py, test_images/*.jpg
doctype/packing_list_detail/        packing_list_detail.{json,py}
doctype/packing_list_carton_type/   packing_list_carton_type.{json,py}
print_format/packing_list/          packing_list.json
public/js/packing_list_scale.js     module đọc cân Web Serial (window.plScale)
```
Phụ thuộc: `ssocr` (system), `numpy`/`scipy`/`Pillow` (env), Cropper.js (CDN, `app_include_js`).
