# Hướng dẫn sử dụng — Quản lý kho hàng TIQN

> Phạm vi: **Item (danh mục)** · **Stock Entry (nhập/xuất/chuyển kho)** · **2 báo cáo tồn kho custom**
> Áp dụng: ERPNext v16 — app `customize_erpnext`

---

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Tạo Item — danh mục hàng hoá](#2-tạo-item--danh-mục-hàng-hoá)
3. [Tạo Batch (cuộn vải) trước khi nhập kho](#3-tạo-batch-cuộn-vải-trước-khi-nhập-kho)
4. [Nhập kho — Material Receipt](#4-nhập-kho--material-receipt)
5. [Xuất kho — Material Issue](#5-xuất-kho--material-issue)
6. [Chuyển kho — Material Transfer](#6-chuyển-kho--material-transfer)
7. [Báo cáo Stock Ledger Customize](#7-báo-cáo-stock-ledger-customize)
8. [Báo cáo Stock Balance Customize](#8-báo-cáo-stock-balance-customize)
9. [Lưu ý quan trọng & lỗi thường gặp](#9-lưu-ý-quan-trọng--lỗi-thường-gặp)

---

## 1. Tổng quan

### 1.1 Ba loại nghiệp vụ kho

| Nghiệp vụ | Stock Entry Type | Mục đích |
|---|---|---|
| **Nhập kho** | Material Receipt | Nhận hàng vào kho |
| **Xuất kho** | Material Issue | Xuất hàng ra khỏi kho |
| **Chuyển kho** | Material Transfer | Chuyển nội bộ giữa các kho |

Không dùng Purchase Order / Sales Order cho quản lý vải và vật tư may. Mọi nghiệp vụ tồn kho đi qua **Stock Entry**.

### 1.2 Nhóm hàng và quy tắc tự động

| Nhóm hàng | Item Code prefix | UOM | Có variant | Batch (cuộn) |
|---|---|---|---|---|
| **B-Finished Goods** | `B-` | Pcs | ✅ Color/Size/Brand/Season | ❌ |
| **C-Fabric (vải)** | `C-` | Meter | ✅ Color/Size/Brand/Season | ✅ |
| **D-Interlining** | `D-` | Meter | ✅ Color/Size/Brand/Season | ❌ |
| **E-Padding** | `E-` | Meter | ✅ Color/Size/Brand/Season| ❌ |
| **F-Packing** | `F-` | Pcs | ✅ Color/Size/Brand/Season| ❌ |
| **G-Sewing** | `G-` | Pcs | ✅ Color/Size/Brand/Season| ❌ |
| **H-Thread** | `H-` | Cone | ✅ Color/Size/Brand/Season| ❌ |

> Chỉ **C-Fabric** dùng Batch để theo dõi từng cuộn. Các nhóm khác không dùng Batch.

---

## 2. Tạo Item — danh mục hàng hoá

### 2.1 Quy tắc Item Code (tự động sinh)

Hệ thống tự sinh Item Code theo chuẩn **base-36** (ký tự 0–9, A–Z) khi bạn nhập Item Name + Item Group:

- Format: `{prefix}-{3 ký tự}` — ví dụ: `C-001`, `C-00A`, `C-00B`, ..., `C-00Z`, `C-010`
- Prefix theo nhóm: `C-` cho vải, `D-` cho interlining, `B-` cho thành phẩm, v.v.
- Hệ thống tìm item_code lớn nhất trong nhóm rồi tăng lên 1 đơn vị base-36.

**Điều kiện để code tự sinh:**

1. Phải nhập **Item Name trước** khi chọn Item Group.
2. Nếu item đã tồn tại (trùng tên + nhóm), hệ thống báo lỗi và link đến item cũ.
3. Item Code chỉ tự sinh cho các nhóm con của `03 - Materials` và `B-Finished Goods`.

### 2.2 Tạo Item template vải (C-Fabric)

Item vải có 2 cấp: **template** (mã vải gốc) → **variant** (mã màu+khổ cụ thể).

**Bước 1 — Tạo template:**

1. Vào **Item → New**
2. Điền **Item Name** (ví dụ: `Cotton Twill`) — nhập trước khi chọn nhóm
3. Chọn **Item Group** = `C-Fabric`
4. Hệ thống tự động:
   - Sinh **Item Code** (ví dụ: `C-001`)
   - Đặt `Has Variants = Yes`
   - Đặt `Has Batch No = Yes`, `Create New Batch = No`
   - Đặt `Stock UOM = Meter`
   - Đặt `Customer Provided Item = Yes`
   - Thêm 4 attribute: **Color**, **Size**, **Brand**, **Season**
   - Đặt Default Warehouse = `Material - Local - TIQN`
5. **Save**

> **Lưu ý:** Không đặt `Create New Batch = Yes` — batch phải tạo thủ công theo quy ước lot/roll.

**Bước 2 — Tạo variants (màu × khổ):**

1. Trên form template → **Create → Multiple Variants**
2. Chọn các giá trị **Color** (ví dụ: Red, Blue, White) , **Size** (ví dụ: 1.2, 1.5, 1.8), **Brand**, **Season**
3. Click **Create Variants** → hệ thống sinh variant codes: `C-001-Rd-1.2`, `C-001-Rd-1.5`, `C-001-Bl-1.5`, ...
4. Mỗi variant tự kế thừa `Has Batch No = Yes` từ template.

> **Quy tắc Size:** Giá trị khổ vải (1.0, 1.2, 1.5, 1.6, 1.8m) được quản lý trong **Item Attribute → Size**. 

### 2.3 Tạo Item vật tư khác (D/E/F/G/H)

Tương tự C-Fabric nhưng **không có Batch**. Hệ thống tự đặt UOM và defaults phù hợp với từng nhóm.

### 2.4 Tạo Item thành phẩm (B-Finished Goods)

1. **Item Name** → chọn **Item Group** = `B-Finished Goods`
2. Hệ thống đặt `UOM = Pcs`, `Has Variants = Yes`, `Is Sales Item = Yes`
3. Default Warehouse = `Finished Goods - TIQN`
4. Tạo variants theo Color/Size/Brand/Season

### 2.5 Cập nhật Default Warehouse

Nếu cần cập nhật lại Default Warehouse (ví dụ sau khi đổi khách hàng cung cấp):

- Trên form Item → **Actions → Update Default Warehouse**
- Hệ thống tự tra `Customer.custom_default_warehouse` (nếu là Customer Provided Item) hoặc dùng `Material - Local - TIQN`.

---

## 3. Tạo Batch (cuộn vải) trước khi nhập kho

### 3.1 Quy ước batch_id

```
batch_id = {template_item_name}|{color}|{lot}|{roll}
```

| Thành phần | Ví dụ | Ghi chú |
|---|---|---|
| `template_item_name` | `Cotton Twill` | `item_name` của **template** (mã gốc của nhà sản xuất — bất biến) |
| `color` | `Red` | Giá trị attribute **Color** của variant |
| `lot` | `11` | Số lô từ NCC — **giữ nguyên như nhập** (số hoặc text), **không pad** số 0 |
| `roll` | `1` | Số cuộn — **giữ nguyên như nhập** (số hoặc text), **không pad** số 0 |

**Ví dụ thực tế** (cùng lô, cùng cuộn, khác màu):

```
Cotton Twill|Red|11|1     ← Vải đỏ, Lô 11, Cuộn 1
Cotton Twill|Blue|11|1    ← Vải xanh, Lô 11, Cuộn 1
```

→ Hai màu cùng lô cùng cuộn → **unique nhờ color khác nhau** ✅

> **Quy tắc bắt buộc:**
> - Dùng `|` đơn ngăn cách **4 thành phần**: `template|color|lot|roll` (không dùng `||`)
> - Không dùng ký tự `|` trong lot hoặc roll
> - Không đổi tên batch sau khi đã có giao dịch
> - Dùng nút **Generate Batch ID** (xem 3.3) để tránh gõ sai format
> - **lot + roll phải duy nhất trong phạm vi (template + color)**. Vì batch_id không chứa Size (khổ), nếu nhà cung cấp đánh trùng số cuộn cho 2 khổ khác nhau cùng màu cùng lô → batch_id trùng → ERPNext **chặn không cho tạo** (tên Batch là duy nhất toàn hệ thống). Khi đó thêm hậu tố vào roll (ví dụ `1A`, `1B`).

### 3.2 parent_batch (gom theo lô — tuỳ chọn)

```
parent_batch = {template_item_name}|{color}|{lot}
```

Ví dụ: `Cotton Twill|Red|11` — gom tất cả cuộn đỏ của lô 11.

Đặt `parent_batch` khi tạo Batch để có thể lọc báo cáo theo lô thay vì từng cuộn.

### 3.3 Tạo Batch thủ công bằng nút Generate

Với số lượng cuộn nhỏ (< 10), tạo từng Batch trực tiếp trên form:

1. Vào **Batch → New**
2. Chọn **Item** = variant item_code (ví dụ: `C-001-Rd-1.5`)
3. Nhập **Lot Number** (số hoặc text, ví dụ: `11`)
4. Nhập **Roll Number** (số hoặc text, ví dụ: `1`)
5. Click nút **Generate Batch ID** → hệ thống tự điền (lot/roll giữ nguyên như nhập):
   ```
   Cotton Twill|Red|11|1
   ```
6. (Tuỳ chọn) Điền **Initial Quantity** = số mét cuộn (vd `52.5`) — sẽ được điền sẵn vào Quantity khi nhập kho bằng "Add Multiple Batch"
7. Điền thêm **Description** (khổ thực — ví dụ: `khổ 148cm`)
8. **Save**

> **Initial Quantity KHÁC Batch Quantity:** `Initial Quantity` chỉ là số dự kiến để tiện nhập kho — **không** tạo tồn. `Batch Quantity` là tồn thật, read-only, hệ thống tự tính từ Stock Ledger sau khi Submit Stock Entry.
> Nếu Item không có attribute Color (không phải vải), batch_id sẽ có format rút gọn: `{template_name}|{lot}|{roll}`

### 3.4 Tạo Batch hàng loạt bằng Data Import (≥ 10 cuộn)

**Chuẩn bị file Excel/CSV:**

> ✅ **Tự sinh batch_id khi import:** chỉ cần điền `item`, `Lot Number`, `Roll Number` và **để trống `batch_id`** — hệ thống tự sinh `batch_id = template|color|lot|roll` (lot/roll giữ nguyên như nhập, không pad) và tự điền cột **Color** từ thuộc tính của item.

| item | custom_lot_number | custom_roll_number | parent_batch | description |
|---|---|---|---|---|
| `C-001-Rd-1.5` | `11` | `1` | `Cotton Twill\|Red\|11` | 52.5m, khổ thực 148cm |
| `C-001-Rd-1.5` | `11` | `2` | `Cotton Twill\|Red\|11` | 49.0m |
| `C-001-Bl-1.5` | `11` | `1` | `Cotton Twill\|Blue\|11` | 51.0m |

> Nếu muốn **tự kiểm soát** batch_id thì vẫn có thể điền sẵn cột `batch_id` đầy đủ — khi đó hệ thống giữ nguyên giá trị bạn nhập.

**Import:**

1. Vào **Data Import → New**
2. DocType = `Batch`
3. Upload file → **Import**
4. Kiểm tra không có lỗi trước khi submit

> Trường `item` = **variant item_code** (ví dụ `C-001-Rd-1.5`), không phải template. Cột **Color** (`custom_color`) là read-only, tự điền từ thuộc tính Color của item — không cần nhập.
> Khi để trống `batch_id`, hai cột `custom_lot_number` (Lot Number) và `custom_roll_number` (Roll Number) là **bắt buộc** — hệ thống dùng chúng để tự sinh batch_id.

### 3.5 Tạo Batch nhanh trong Serial and Batch Bundle

Khi nhập ít cuộn mà không muốn tạo Batch trước, có thể gõ trực tiếp batch_id trong **Serial and Batch Bundle** lúc tạo Stock Entry — hệ thống tự tạo Batch khi bundle được lưu (xem mục 4.3).

---

## 4. Nhập kho — Material Receipt

### 4.1 Tạo Stock Entry

1. Vào **Stock Entry → New**
2. **Stock Entry Type** = `Material Receipt`
3. Điền các trường header:

| Trường | Ý nghĩa | Bắt buộc |
|---|---|---|
| **No#** (`custom_no`) | Số phiếu nội bộ (ví dụ: `NK-240115-001`) | ✅ |
| **Posting Date/Time** | Ngày giờ nhập kho | ✅ |
| **Invoice Number** (`custom_invoice_number`) | Tổng hợp tự động từ các dòng | Tự động |

> **Lưu ý:** Trường `Invoice Number` ở header được **tự động tổng hợp** từ tất cả dòng khi bạn điền `Invoice Number` ở từng dòng item. Không cần điền thủ công ở header.

### 4.2 Thêm item vào bảng Items

Với **mỗi dòng vật tư** (không phải vải):

| Trường | Ví dụ |
|---|---|
| Item Code | `D-001-Bl-1.5` (chọn variant) |
| Qty | `500` |
| Target Warehouse | Kho nhận |
| **Invoice Number** (`custom_invoice_number`) | `15/01/2024:INV-2024-001` |

→ Khi focus/click vào ô Invoice Number: **Invoice Selector dialog** mở ra, cho phép chọn hoặc gõ số hóa đơn.

### 4.3 Nhập vải có batch (cuộn vải)

Với **mỗi dòng vải** (C-Fabric — `has_batch_no = Yes`):

1. Chọn variant item_code (ví dụ: `C-001-Rd-1.5`)
2. Nhập **Qty** = tổng mét của tất cả cuộn trong dòng
3. Chọn **Target Warehouse**
4. Ô **Invoice Number**: click sẽ mở **Invoice Selector** (mọi item) — hoặc gõ trực tiếp số packing list, ví dụ `PL-2024-001`
5. Click **Serial and Batch Bundle** (biểu tượng trong dòng) → dialog "Add Batch Nos" mở:
   - **Cách nhanh (khuyến nghị):** bấm nút **"Add Multiple Batch"** (ngay sau phần CSV) → dialog liệt kê **tất cả cuộn (Batch) đã tạo cho item**; **lọc** theo Batch/Lot/Roll/Color, tick **1 / nhiều / tất cả** (Select All / Clear All). Cột **Quantity** **tự điền sẵn** từ **Initial Quantity** của Batch (sửa được); dòng nào trống thì lấy **Default Quantity**. Bấm **Add Selected** → các cuộn được thêm vào bảng.
   - Hoặc thêm tay: mỗi cuộn = 1 entry (`Batch No`, `Quantity` = số mét thực). Batch chưa tạo → gõ batch_id đúng format, hệ thống tự tạo khi lưu bundle.
   - Tổng Quantity trong bundle phải = Qty dòng item

> **Quy tắc nhập bundle:**
> - 1 cuộn = 1 dòng trong bundle
> - batch_id phải đúng format: `{template_item_name}|{color}|{lot}|{roll}`
> - Số mét mỗi cuộn lấy từ packing list thực tế

### 4.4 Opening Stock (tồn đầu kỳ)

Khi nhập tồn ban đầu:

1. Tick **Is Opening Stock** (`custom_is_opening_stock`)
2. Hệ thống hiện cảnh báo: phải điền **Receive Date** cho mỗi dòng
3. `custom_receive_date` = ngày nhận hàng thực tế (ảnh hưởng tính tuổi tồn trong báo cáo)
4. Khi submit: hệ thống tự sinh `No#` theo format `Opening Stock DD/MM/YYYY XXX`

### 4.5 Quy trình kiểm tra khi Lưu / Submit

Hệ thống tự kiểm tra:
- **Invoice Number** phải có ở **mọi dòng** — kiểm **ngay khi Lưu (Save)**, không chỉ lúc Submit; nếu thiếu: dialog hỏi Auto Fill hoặc Cancel (không lưu được cho đến khi đủ)
- **Auto Fill**: điền `DD/MM/YYYY:Unknown` cho các dòng trống
- **Warehouse** phải hợp lệ cho từng item

---

## 5. Xuất kho — Material Issue

### 5.1 Tạo Stock Entry

1. **Stock Entry Type** = `Material Issue`
2. Điền **No#**, **Posting Date**
3. Có thể điền thêm: `custom_material_issue_purpose`, `custom_line` (dây chuyền)

### 5.2 Xuất vật tư thường (không batch)

1. Thêm item vào bảng
2. Click vào ô **Invoice Number** → **Invoice Selector dialog** mở:
   - Hiển thị danh sách hóa đơn đang tồn kho cho item đó
   - Chọn hóa đơn → hệ thống điền `Invoice Number` cho dòng
   - Hoặc gõ trực tiếp nếu biết số hóa đơn
3. Điền **Qty** cần xuất

> Invoice Selector mở cho **mọi item** (kể cả vải có batch) khi click vào ô Invoice Number.

### 5.3 Xuất vải theo cuộn (batch)

1. Thêm dòng vải (variant code)
2. Ô **Invoice Number**: click mở **Invoice Selector** hoặc gõ trực tiếp số packing list
3. **Qty** = tổng mét cần xuất
4. Click **Serial and Batch Bundle** → chọn cuộn và số mét:

   **Xuất nguyên cuộn:**
   - Chọn batch_id, nhập qty = toàn bộ số mét còn lại của cuộn
   - Cuộn về tồn = 0

   **Xuất một phần cuộn:**
   - Chọn batch_id, nhập qty < tồn cuộn
   - Cuộn còn lại = tồn hiện tại − qty xuất
   - Cuộn vẫn tiếp tục tồn kho

   **Xuất nhiều cuộn:**
   - Thêm nhiều entry trong bundle (1 entry = 1 cuộn)

> **Không thể xuất quá tồn cuộn** — ERPNext chặn tự động.

---

## 6. Chuyển kho — Material Transfer

### 6.1 Tạo Stock Entry

1. **Stock Entry Type** = `Material Transfer`
2. Điền **No#**, **Posting Date**
3. Mỗi dòng item có cả **Source Warehouse** và **Target Warehouse**

### 6.2 Chuyển vải (giữ nguyên batch_id)

1. Thêm dòng variant vải
2. Ô **Invoice Number**: gõ trực tiếp
3. **Serial and Batch Bundle**: chọn cuộn + số mét cần chuyển
   - Chuyển nguyên cuộn: qty = tồn cuộn → cuộn biến mất ở kho nguồn, xuất hiện ở kho đích
   - Chuyển một phần: cuộn xuất hiện ở **cả hai kho** với số mét tương ứng — **cùng batch_id**

---

## 7. Báo cáo Stock Ledger Customize

**Đường dẫn:** Stock → Reports → Stock Ledger Customize

### 7.1 Mô tả

Hiển thị từng dòng SLE (Stock Ledger Entry) — lịch sử giao dịch chi tiết nhất, không gom nhóm.

### 7.2 Filters

| Filter | Mô tả |
|---|---|
| **Company** | Bắt buộc |
| **From Date / To Date** | Khoảng thời gian |
| **Warehouse** | Lọc theo kho |
| **Item** | Lọc 1 mã item |
| **Item Group** | Lọc theo nhóm (bao gồm nhóm con) |
| **Invoice Number** | Lọc theo số hóa đơn (exact match) |
| **Batch No** | Lọc theo cuộn vải cụ thể — đọc đúng cả batch trong Serial and Batch Bundle (v16). Khi lọc, In/Out Qty và Balance Qty hiển thị **theo riêng cuộn đó** |
| **Stock Entry Type** | Material Receipt / Material Issue |
| **Show Variant Attributes** | Hiện cột Color, Size, Brand, Season |
| **Voucher #** | Lọc theo số phiếu cụ thể |

### 7.3 Cột chính

| Cột | Ý nghĩa |
|---|---|
| Date | Ngày giờ giao dịch |
| Item | Mã item |
| In Qty / Out Qty | Số lượng vào/ra (âm = xuất) |
| Balance Qty | Tồn sau giao dịch |
| Warehouse | Kho |
| **Invoice Number** | Số hóa đơn của dòng |
| **Batch No** | Cuộn vải của giao dịch — nếu 1 phiếu nhập/xuất nhiều cuộn thì hiện danh sách cuộn (cách nhau dấu phẩy). Khi lọc theo 1 Batch No, chỉ hiện đúng cuộn đó |
| Voucher # | Số phiếu Stock Entry |

### 7.4 Use cases

| Tình huống | Cách dùng |
|---|---|
| Xem lịch sử 1 cuộn vải cụ thể | Filter `Batch No = Cotton Twill\|Red\|11\|1` |
| Xem tất cả giao dịch 1 hóa đơn | Filter `Invoice Number = INV-2024-001` |
| Kiểm tra nhập/xuất 1 kho | Filter `Warehouse` + `Stock Entry Type` |

---

## 8. Báo cáo Stock Balance Customize

**Đường dẫn:** Stock → Reports → Stock Balance Customize

### 8.1 Mô tả

Tổng hợp tồn kho: Opening Qty → In Qty → Out Qty → **Balance Qty**. Có thể gom theo hóa đơn hoặc theo cuộn vải.

### 8.2 Filters quan trọng

| Filter | Mô tả |
|---|---|
| **From Date / To Date** | Khoảng kỳ tính tồn |
| **Item Group** | Lọc theo nhóm (khuyến nghị chọn `C-Fabric` khi xem vải) |
| **Item** | **Chọn nhiều** mã item cùng lúc (MultiSelect, giống report gốc) |
| **Warehouse** | **Chọn nhiều** kho cùng lúc (MultiSelect); lọc theo Company + Warehouse Type đang chọn |
| **Group by Invoice Number** | ✅ Mặc định bật — gom theo hóa đơn (mỗi hóa đơn = 1 dòng) |
| **Group by Batch** | Tách từng cuộn vải thành 1 dòng (kèm cột Lot/Roll) |
| **Show Stock Ageing Data** | Hiện thêm cột tuổi tồn theo dải ngày |
| **Ageing Range** | Phân kỳ tuổi tồn (mặc định: 90,180,270...) |
| **Show Variant Attributes** | Hiện cột Color, Size, ... |
| **Include Zero Stock Items** | Hiện cả item hết hàng |

### 8.3 Các cột chính

| Cột | Có khi nào |
|---|---|
| Item / Item Name / Item Group / Warehouse | Luôn có |
| **Invoice Number** | Khi bật `Group by Invoice Number` |
| **Batch No** | Khi bật `Group by Batch` |
| **Lot Number / Roll Number** | Khi bật `Group by Batch` — lấy từ `custom_lot_number`/`custom_roll_number` của Batch |
| Balance Qty / Opening Qty / In Qty / Out Qty | Luôn có |
| Age | Khi bật `Group by Invoice Number` |
| Ageing ranges (0-90, 91-180, ...) | Khi bật `Show Stock Ageing Data` |
| Color / Size / Brand / Season / Info | Khi bật `Show Variant Attributes` (chỉ 5 thuộc tính chuẩn; thuộc tính rác như `Colour` không hiện) |

### 8.4 Use cases vải

| Tình huống | Cài filter |
|---|---|
| **Tồn từng cuộn theo kho** | Item Group = C-Fabric · Group by Batch ✅ · Group by Invoice ❌ → xem cột Batch No + Lot + Roll |
| **Tồn theo lô (invoice) + tuổi tồn** | Item Group = C-Fabric · Group by Invoice ✅ · Show Ageing ✅ |
| **Tồn 1 cuộn cụ thể** | Group by Batch ✅ rồi tìm dòng cuộn đó. *(Stock Balance không còn filter Batch No — muốn lọc đúng 1 cuộn dùng **Stock Ledger Customize → Batch No**)* |
| **Tồn nhiều mã vải / nhiều kho cùng lúc** | Chọn nhiều Item và/hoặc nhiều Warehouse trong filter |
| **Tồn tất cả màu của 1 mã vải** | Item = các variant của template · Group by Batch ✅ |
| **Tổng tồn theo nhóm vải** | Item Group = C-Fabric · Group by Invoice ❌ · Group by Batch ❌ |

### 8.5 Lấy dữ liệu sang Excel / Power Query (không cần đăng nhập)

Có API công khai trả về đúng dữ liệu Stock Balance Customize dạng JSON để nạp vào Excel qua **Power Query**.

**Địa chỉ (GET):**
```
https://erp.tiqn.com.vn:8888/api/method/customize_erpnext.api.stock.stock_balance_api.get_stock_balance
```

**Tham số (đều tuỳ chọn — có mặc định):**

| Tham số | Mặc định |
|---|---|
| `from_date` | đầu năm tài chính **01/04** (tháng 4–12 → năm nay; tháng 1–3 → năm trước) |
| `to_date` | hôm nay |
| `warehouse` | trống = tất cả kho |
| `item_group` | trống = tất cả nhóm |
| `show_variant_attributes` | true |
| `summary_qty_by_invoice_number` (Group by Invoice) | true |
| `group_by_batch` | true |
| `show_stock_ageing_data` | false |
| `include_zero_stock_items` | true |

**Các bước trong Excel:** Data → Get Data → From Web → dán URL (thêm tham số nếu cần) → trong trình soạn Power Query lấy `message` → **To Table** → Expand.

```m
let
    url  = "https://erp.tiqn.com.vn:8888/api/method/customize_erpnext.api.stock.stock_balance_api.get_stock_balance",
    resp = Json.Document(Web.Contents(url)),
    tbl  = Table.FromRecords(resp[message])
in
    tbl
```

> ⚠️ API mở công khai (không xác thực) — chỉ nên dùng trong mạng nội bộ / giới hạn IP để tránh lộ dữ liệu tồn kho.

---

## 9. Lưu ý quan trọng & lỗi thường gặp

### 9.1 Batch ID — nguyên tắc không được vi phạm

| Quy tắc | Hậu quả nếu vi phạm |
|---|---|
| batch_id = `{template_item_name}\|{color}\|{lot}\|{roll}` (4 phần, `\|` đơn) | Báo cáo không thể parse đúng lot/roll |
| Dùng **nút Generate** hoặc copy từ batch đã tạo | Gõ tay sai format gây lỗi tra cứu |
| Lot/roll giữ **nguyên như nhập** (số hoặc text), **không pad** số 0 — vd lot `1`, roll `11` → `...\|1\|11` | Sai batch_id, tra cứu lệch |
| Không chứa ký tự `\|` trong lot, roll, hoặc item_name | Parse lỗi |
| **Không đổi tên** sau khi có SLE | Mất liên kết lịch sử tồn kho |

### 9.2 Invoice Number — nguyên tắc

- **Bắt buộc** điền cho mọi dòng **trước khi Lưu (Save)** — không lưu được nếu còn dòng trống Invoice Number
- Nếu không biết: dùng **Auto Fill** → format `DD/MM/YYYY:Unknown`
- Click vào ô Invoice Number để mở **Invoice Selector** (áp dụng cho **mọi item**, kể cả vải) → chọn hóa đơn từ danh sách tồn kho; hoặc gõ trực tiếp
- Invoice Number ở header = tổng hợp tự động từ các dòng (không cần nhập thủ công)

### 9.3 Trình tự bắt buộc khi tạo Item

```
Item Name → Item Group → (hệ thống sinh Item Code) → Save
```

- **Không** đặt Item Group trước Item Name → hệ thống báo lỗi
- **Không** đổi Item Group sau khi đã Save → hệ thống block

### 9.4 Stock Entry — chỉ dùng 3 loại

Nếu chọn loại khác Material Receipt / Issue / Transfer, hệ thống sẽ báo lỗi và không cho tiếp tục.

### 9.5 Xuất quá tồn cuộn

ERPNext chặn tự động khi bundle qty > batch_qty còn lại. Kiểm tra tồn cuộn trước khi xuất bằng **Stock Balance Customize → Group by Batch** (hoặc **Stock Ledger Customize → filter Batch No** để xem đúng 1 cuộn).

### 9.6 Opening Stock — phải có Receive Date

Khi tick `Is Opening Stock`, **mọi dòng** phải có `custom_receive_date`. Đây là ngày thực tế nhận hàng, ảnh hưởng đến tính tuổi tồn trong Stock Balance Customize.

### 9.7 Item Group C-Fabric — Size là khổ vải

- Attribute **Size** dùng để lưu **khổ vải** (width): 1.0m, 1.2m, 1.5m, 1.6m, 1.8m
- Giá trị Size được quản lý tập trung trong **Item Attribute → Size**
- Khổ thực tế của từng cuộn (có thể lẻ hơn) → ghi vào `description` của Batch

### 9.8 Data Import Batch — thứ tự fields bắt buộc

File import Batch phải có đúng tên cột: `batch_id`, `item`, `parent_batch`, `description`.
Trường `item` = **variant item_code** (ví dụ `C-001-Rd-1.5`), không phải template.
Trường `batch_id` phải theo format: `{template_item_name}|{color}|{lot}|{roll}` (`|` đơn, 4 phần). Lot/roll **giữ nguyên như nhập** (số hoặc text), **không pad** số 0. Khuyến nghị tạo qua nút **Generate Batch ID** trên form để tránh lỗi gõ tay.

### 9.9 ⛔ KHÔNG dùng nút Split / Move trên Batch vải

Bản ghi **Batch** gốc của ERPNext có nút **Split** (chia lô) và **Move** (chuyển kho). **Tuyệt đối không dùng cho vải:**

- **Split** sinh ra batch con với tên hệ thống tự đặt → **phá vỡ** convention `{template}|{color}|{lot}|{roll}`, báo cáo không tra cứu được.
- **Move** tạo Stock Entry ngầm, **bỏ qua** luồng `custom_invoice_number` / `custom_receive_date` → sai dữ liệu báo cáo.

→ Chia/chuyển cuộn vải **luôn** làm qua **Material Transfer thủ công** (mục 6) hoặc xuất một phần trong **Serial and Batch Bundle** (mục 5.3).

### 9.10 Vải KHÔNG tự sinh mã lô (khác mặc định ERPNext)

Mặc định ERPNext cho phép `Automatically Create New Batch` + `Batch Number Series` để tự sinh mã lô. **TIQN tắt hẳn tính năng này** (`create_new_batch = 0`, không có series) để mã lô mang đúng thông tin lot + roll.

→ Bắt buộc tạo Batch **trước** (nút Generate — mục 3.3, hoặc Data Import — mục 3.4) hoặc gõ đúng format trong Bundle (mục 3.5). Hệ thống **không** tự tạo giúp.

### 9.11 Tuổi tồn tính theo Receive Date, không phải Posting Date

Khác FIFO chuẩn của ERPNext (dùng `posting_date`), báo cáo **Stock Balance Customize** ưu tiên **`custom_receive_date`** nếu có. Vì vậy với hàng nhập tồn đầu kỳ (Opening Stock), điền đúng **Receive Date** là bắt buộc để tuổi tồn chính xác (xem 9.6).

### 9.12 Truy xuất nguồn gốc — vẫn dùng được báo cáo gốc

Ngoài 3 báo cáo custom, các báo cáo gốc của ERPNext vẫn hoạt động cho từng lô:
- **Serial No and Batch Traceability** — vòng đời 1 lô (nhập từ đâu, xuất cho ai)
- **Batch-wise Balance History** — tồn chi tiết từng lô tại từng kho

---

*Cập nhật lần cuối: 2026-06-09 — batch_id `|` đơn (4 phần), lot/roll giữ nguyên (không pad); Invoice Selector mở cho mọi item; Batch tự sinh batch_id + cột Color khi import Excel; Stock Balance Customize: fix crash, batch từ Serial and Batch Bundle (+ Lot/Roll), bỏ cột Colour thừa, Item/Warehouse chọn-nhiều; Stock Ledger Customize: Batch No cột/filter chạy đúng v16; gỡ bỏ Stock Ageing Customize (đã gộp vào Stock Balance); Stock Balance: bỏ filter Batch No & Include UOM, thêm API Power Query (guest) | customize_erpnext — ERPNext v16*
