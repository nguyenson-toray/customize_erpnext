# Uniform Control — Hướng dẫn sử dụng

Module quản lý tồn kho & cấp phát đồng phục cho nhân viên (ERPNext/HRMS v16, app `customize_erpnext`).

- **Phần 1 — IT Admin**: thiết lập một lần (master data, kho, cấu hình, phân quyền).
- **Phần 2 — HR (Uniform Manager)**: sử dụng hàng ngày (nhập kho, cấp phát, theo dõi).

---

# PHẦN 1 — IT ADMIN

## 1.1 Nguyên tắc thiết kế item

- Mỗi template chỉ dùng **1 variant attribute** (`Size` cho áo/dép, `Color` cho mũ).
- **Giới tính tách thành template riêng** (áo nam / áo nữ) — không dùng attribute giới tính. Việc cấp đúng giới tính do **Rule** quyết định (điều kiện Gender, xem §1.6) + áo gán trên hồ sơ.
- **Mỗi màu Mũ gắn 1 vai trò** (vd "Đỏ - Qc", "Xanh Dương Đậm - May") → gán theo Rule.
- Item Group: **`U-Uniform`** — mọi item đồng phục thuộc nhóm này; `name = item_name`.

## 1.2 Item hiện trạng

| Item (template) | Attribute | Giá trị |
|---|---|---|
| `Áo sơ mi nam`, `Áo sơ mi nữ` | Size | S, M, L, Xl |
| `Áo thun nam`, `Áo thun nữ` | Size | S, M, L, Xl |
| `Dép` | Size | 26 – 32 |
| `Mũ` | Color | 15 màu, mỗi màu gắn vai trò (Đỏ-Qc, Vàng-Trưởng Phòng, Xanh Lá-Nv Văn Phòng...) |
| `Bình nước` | — (item đơn) | — |

Cấu hình chung: Item Group = `U-Uniform`, `Maintain Stock = 1`, không bật Serial/Batch.

> ⚠️ Hồ sơ nhân viên chọn size áo `S/M/L/XL` → code tự map sang attribute `S/M/L/Xl`. Nếu tạo size mới (vd `2Xl`) thì báo IT cập nhật options field Shirt Size / Shoe Size trong Employee Uniform Profile.

## 1.3 Thêm size/màu mới sau này

1. Thêm Attribute Value vào attribute `Size` hoặc `Color`.
2. Mở template → **Create Variants** cho giá trị mới (đặt `name = item_name` cho rõ).
3. Cập nhật options field tương ứng trong Employee Uniform Profile (Shirt Size / Shoe Size) nếu giá trị mới chưa có.

## 1.4 Tạo Warehouse

Tạo kho leaf: **`Uniform - TIQN`** (cha: All Warehouses hoặc theo cây kho hiện tại). Toàn bộ tồn đồng phục nằm tại kho này.

## 1.5 Đặt Reorder Level (ngưỡng cảnh báo tồn thấp)

Trên **từng variant** (không phải template): mở Item → tab Inventory → bảng **Reorder level**, thêm dòng:
- `Check in (warehouse)` = Uniform - TIQN
- `Reorder Level` = ngưỡng cảnh báo (ví dụ 10)
- `Reorder Qty` = số lượng đề nghị nhập (ví dụ 50)

Email cảnh báo hàng tuần sẽ liệt kê variant có `tồn ≤ Reorder Level`. **Không** bật auto Material Request.

## 1.6 Cấu hình Uniform Setting

Vào **Uniform Setting** (DocType Single):

Chỉ còn cấu hình chung (Rules đã tách sang DocType riêng — xem dưới):

| Field | Giá trị khuyến nghị |
|---|---|
| Uniform Warehouse | Uniform - TIQN |
| Uniform Item Group | U-Uniform — quyết định bộ lọc item trên Hồ sơ đồng phục (Áo được gán, Uniform Type) và trên Uniform Rule |
| Employee ID Prefix | `TIQN` — chỉ quản lý NV có mã bắt đầu bằng prefix này |
| Reminder Days Before | 30 (cảnh báo trước hạn 30 ngày) |
| Enable Weekly Alert | ✅ |
| Alert Recipients | email HR, phân tách dấu phẩy: `hr@tiqn.com.vn, it@tiqn.com.vn` |

Nút trên form Setting: **Manage Uniform Rules** (mở danh sách Uniform Rule), **Send Alert Now** (gửi email cảnh báo ngay).

### Uniform Rule (Quy tắc cấp phát — DocType riêng)

Từ nay **mỗi quy tắc là một record** trong DocType **Uniform Rule** (danh sách riêng, không còn nằm trong Uniform Setting). Vào **Uniform Setting → nút "Manage Uniform Rules"** hoặc sidebar **Uniform Rule**.

Mỗi rule trả lời: AI (Grade/Designation/Group/Section/Gender) nhận **MÓN GÌ**, **MẤY CÁI**, **CHU KỲ** nào. Mỗi **Category** (Shirt/Cap/Shoe/Bottle) chỉ cấp 1 món/người — rule cụ thể thắng rule chung.

| Field | Ý nghĩa |
|---|---|
| **Category** | Shirt / Cap / Shoe / Bottle — "khe" đồng phục (1 món/người/category) |
| **Item** | Kết quả: Shirt/Shoe → **template**; Cap → **variant Mũ cụ thể**; Bottle → item đơn |
| **Grades** / **Designations** | **Chọn nhiều** (popup) — rule áp dụng cho mọi grade/chức danh trong danh sách. **Để trống = tất cả**. (Vd 1 rule áo sơ mi nữ chọn cả Staff/Leader/Sub Leader/Manager/Factory Manager thay vì 5 rule.) |
| Group / Section / Gender | Điều kiện đơn. **Để trống = áp dụng tất cả**. Group = `custom_group` (tổ, vd Line 01); Section = `custom_section` (bộ phận, chứa nhiều Group) |
| First Issue Qty / Eligible After (Days) | SL cấp lần đầu / đủ ĐK sau N ngày làm việc |
| Reissue Cycle (Months) / Reissue Qty | chu kỳ + SL cấp bổ sung (**0 = không cấp bổ sung**) |
| One-Time Issue | ✅ = cấp 1 lần (mũ/dép/bình nước): không cấp bổ sung định kỳ; cấp lại qua Replacement |
| Priority / Active | ưu tiên khi hoà / bật-tắt |

#### Cách chọn rule khi nhân viên khớp nhiều dòng (cùng Category)

Mỗi điều kiện **được điền VÀ khớp** với nhân viên cộng một "điểm cụ thể"; điều kiện để trống = áp dụng mọi người (không tính điểm). **Grades/Designations là danh sách** → khớp nếu grade/chức danh của NV **nằm trong** danh sách (vẫn tính đủ điểm như khớp 1 giá trị):

| Điều kiện | Điểm |
|---|---|
| Designations | 16 |
| Grades | 8 |
| Group | 4 |
| Section | 2 |
| Gender | 1 |

- `rank` của 1 rule = **tổng điểm** các điều kiện khớp. Trong cùng 1 Category, rule có **rank cao nhất thắng** (cụ thể hơn → thắng), và mỗi nhân viên chỉ nhận **1 món/Category**.
- **Designation nặng nhất (16)** — nặng hơn cả Grade+Group+Section+Gender cộng lại (8+4+2+1 = 15). Nên rule theo Designation luôn thắng các rule theo tầng tổ chức.
- **Grade (8) cao hơn Group (4) và Section (2)**: vai trò (Leader/Manager…) quan trọng hơn tổ/bộ phận → **Leader luôn đội mũ Leader** dù ở QC hay bộ phận nào (trừ khi có rule theo Designation riêng).
- Vì là **tổng điểm**: rule khớp `Designation+Gender` (16+1=17) thắng rule khớp `Grade+Group+Section` (8+4+2=14).
- Field **Priority chỉ phá hoà** khi 2 rule có **cùng rank** (hiếm, vd 2 rule cùng theo Designation) — **KHÔNG đè** được rule cụ thể hơn. Muốn một rule "thắng tuyệt đối" → thêm điều kiện Designation hoặc tách rule riêng cho nhóm hẹp đó.

> **Ví dụ 1 — Designation thắng** (Category = Cap): Rule X `Designation = QC Worker` (rank 16) vs Rule Y `Group = Line 03, Gender = Female` (rank 4+1=5). Nhân viên QC Worker ở Line 03 nữ → nhận **Rule X** (Mũ QC) vì 16 > 5.
>
> **Ví dụ 2 — Grade thắng Section** (Category = Cap): một **Tổ trưởng QC** khớp cả `Grade = Leader` (rank 8, Mũ Tổ Trưởng) và `Section = QC` (rank 2, Mũ QC) → nhận **Mũ Tổ Trưởng** vì 8 > 2. Vai trò (Leader) quan trọng hơn bộ phận. Nhưng **QC Worker thường** (không phải Leader) vẫn nhận **Mũ QC** (chỉ khớp Section).

**Bộ Rules mẫu (đã cài sẵn):**

| Category | Item | Grade | Designation | Gender | Qty | Cycle | One-Time |
|---|---|---|---|---|---|---|---|
| Shirt | Áo sơ mi nam | Staff/Leader/Sub Leader/Manager | | Male | 2 | 6 | |
| Shirt | Áo sơ mi nữ | Staff/Leader/Sub Leader/Manager | | Female | 2 | 6 | |
| Shirt | Áo thun nam | Worker | | Male | 2 | 6 | |
| Shirt | Áo thun nữ | Worker | | Female | 2 | 6 | |
| Cap | Mũ Xanh Lá (Nv VP) | Staff | | | 1 | 0 | ✅ |
| Cap | Mũ Xanh Dương Đậm (May) | | Sewing Worker | | 1 | 0 | ✅ |
| Cap | Mũ Đỏ (QC) | | QC Worker | | 1 | 0 | ✅ |
| Shoe | Dép | | | | 1 | 0 | ✅ |
| Bottle | Bình nước | | | | 1 | 0 | ✅ |

> **Áo & Mũ** lưu trên hồ sơ ở field **Áo được gán** / **Mũ được gán** — Rules chỉ điền mặc định, HR sửa tay được (lớp override). **Size áo/giày** là số đo cá nhân → nhập ở hồ sơ. **Dép/Bình nước** không cần gán trước — Rule (điều kiện) quyết định ai được cấp.

**Áp dụng:**
- Nút **Apply Defaults to All** (**danh sách Uniform Rule**) → điền Áo/Mũ **còn trống** cho mọi hồ sơ chưa khoá (giữ nguyên dữ liệu đã có). *(Nút "Hướng dẫn cài đặt" cạnh đó mở dialog giải thích cách viết rule.)*
- Nút **Apply Defaults** (từng hồ sơ) → ghi đè theo rule cho riêng người đó.
- Tự điền field còn trống khi lưu hồ sơ (onboarding).
- Tick **Manual Override** ở hồ sơ → bỏ qua khi Apply hàng loạt.

**⚠️ Sau khi đổi Rule — điều gì cập nhật ngay, điều gì cần chạy lại:**
- **First Issue Qty / Eligible After (Days) / Reissue Qty**: áp dụng **ngay** cho tính mới (Get Employees, Forecast, Dashboard, email tuần). Không đụng dữ liệu đã cấp.
- **Reissue Cycle (Months)**: dùng để tính **hạn kế tiếp (next_due) + trạng thái**, và giá trị này **lưu sẵn** trên hồ sơ. Đổi chu kỳ → báo cáo Tracking / thẻ KPI **vẫn dùng chu kỳ cũ** cho đến khi tính lại. → bấm **"Tính lại hạn cấp"** (danh sách Employee Uniform Profile) để cập nhật toàn bộ.

## 1.7 Phân quyền

- Gán role **`Uniform Manager`** cho user HR (User → Roles).
- Role này có quyền read/write/create/submit/cancel trên: Uniform Setting, Uniform Allocation, Employee Uniform Profile (không có quyền delete).
- HR cần thêm quyền tạo **Stock Entry** nếu nhập kho qua Desk (hoặc dùng API `receive_stock`).

## 1.8 Các tự động hóa đã cài (không cần thao tác)

| Sự kiện | Hành vi |
|---|---|
| Tạo Employee mới | Tự tạo **Employee Uniform Profile** (link 2 chiều qua field Uniform Profile trên Employee), tự điền giới tính từ Employee. **Không** tự tạo Uniform Allocation — HR tạo thủ công (gộp nhiều người) khi cần |
| Thứ Hai 08:30 hàng tuần | Gửi email tới Alert Recipients: bảng tồn thấp + bảng nhân viên đến hạn cấp bổ sung |
| Submit Uniform Allocation | Sinh 1 Stock Entry Material Issue (bỏ qua dòng **Tái sử dụng đồ cũ**), cập nhật hồ sơ từng nhân viên |
| Cancel Uniform Allocation | Cancel Stock Entry liên quan, tính lại hồ sơ từ các đợt cấp còn lại |
| Lưu hồ sơ đồng phục | Tự tính lại **hạn kế tiếp (next_due) + trạng thái** theo Chu kỳ trong Rule (single source of truth) |

## 1.9 Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân / cách xử lý |
|---|---|
| `Profile missing Shirt Size` (hoặc Shoe Size) | Hồ sơ nhân viên chưa điền thông số đó → HR bổ sung profile |
| `No variant for X with size/color Y` | Variant chưa được tạo cho giá trị đó → tạo thêm variant (§1.3) |
| Submit Allocation báo "Insufficient stock" | Tổng SL theo từng variant (cộng dồn nhiều dòng) vượt tồn kho Uniform → nhập kho trước (dòng **Tái sử dụng đồ cũ** không tính vào) |
| Email weekly không gửi | Kiểm tra Enable Weekly Alert + Alert Recipients trong Uniform Setting; xem Error Log với title "Uniform Weekly Alert Error" |
| Forecast báo "chưa đủ đồ" (cam) cho một số người | Thường do **thiếu Grade** trên NV/dòng tuyển, **thiếu Rule** cho tổ hợp Grade×Gender, hoặc **size chưa có variant** → xem cảnh báo (ghi rõ ai/bao nhiêu) rồi bổ sung, Forecast lại |
| Đổi **Chu kỳ cấp lại (tháng)** nhưng Tracking/hạn không đổi | `next_due` lưu sẵn trên hồ sơ → bấm **Tính lại hạn cấp** (danh sách Employee Uniform Profile) |
| Dashboard: chọn Forecast mà tổng bị lệch | Forecast kiểu Re-issue/Both đã gồm cấp lại → dashboard tự ẩn cột Cần re-issue (có ghi chú cam). Đúng, không phải lỗi |

Lỗi nền được ghi vào **Error Log** (Desk → Error Log).

---

# PHẦN 2 — HR (UNIFORM MANAGER)

## 2.1 Khái niệm nhanh

- **Uniform Allocation** (Chứng từ cấp phát) = **nguồn sự thật** của lịch sử cấp: 1 chứng từ cho nhiều NV, có Stock Entry, audit đầy đủ. Submit → tự trừ kho & cập nhật hồ sơ.
- **Employee Uniform Profile → Issuance Tracking** = **bảng tổng hợp tự động (read-only)** suy ra từ các Allocation: loại đã cấp, ngày gần nhất, **hạn kế tiếp + trạng thái** — phục vụ tính điều kiện cấp & nhắc hạn. Không sửa tay; nếu nghi lệch, bấm **Rebuild Tracking** trên hồ sơ để dựng lại từ Allocation.
  - Tracking chia làm **2 bảng** cho dễ nhìn: **Shirts (Áo)** = các item category *Shirt*; **Other Items** = mũ, dép, bình nước… Việc phân loại tự động theo category của Uniform Rule; báo cáo/dashboard/email vẫn gộp chung tất cả item.
- **Employee Uniform Profile** còn lưu: size áo, giới tính, áo/mũ được gán, vị trí để dép.

## 2.2 Bước 1 — Hoàn thiện hồ sơ đồng phục

Hồ sơ được tạo tự động khi nhân viên mới vào. HR mở **Employee Uniform Profile** (hoặc từ form Employee → field Uniform Profile) và điền:

| Field | Ghi chú |
|---|---|
| **Assigned Shirt Item (Áo được gán)** | Template áo nhân viên nhận. **Tự điền từ Quy tắc gán mặc định** (§1.6b); sửa tay được, gán tự do không phụ thuộc giới tính |
| **Assigned Cap Item (Mũ được gán)** | Variant Mũ cụ thể (theo màu/vai trò). **Tự điền từ Quy tắc gán mặc định**; sửa tay được |
| **Manual Override (Khoá thủ công)** | Tick = giữ nguyên áo/mũ đã sửa tay, bỏ qua khi chạy Apply Defaults hàng loạt |
| Uniform Gender | Male / Female (thông tin tham khảo) |
| Shirt Size | S / M / L / XL — size áo |
| Shoe Size | size dép (chỉ chọn size đã có variant trong kho; thêm size mới xem §1.3) |
| Shoe Rack Location | **read-only, tự động** lấy Rack Name từ DocType Shoe Rack (mỗi rack chứa 1–2 nhân viên). Muốn đổi vị trí → sửa phân bổ trong Shoe Rack, profile tự cập nhật |

**Đổi áo cho nhân viên**: đổi Assigned Shirt Item (tick Manual Override nếu là ngoại lệ) rồi Save. Template mới chưa từng cấp → nhân viên sẽ xuất hiện ở danh sách *Cấp mới* cho template đó. Lịch sử được giữ nguyên ở 2 nơi: bảng Issuance Tracking (mỗi loại đã cấp một dòng riêng) và nhật ký thay đổi hồ sơ (menu ⋯ → **History** trên form).

> ⚠️ Hồ sơ thiếu thông số nào thì khi cấp phát hệ thống không tự điền được variant tương ứng — dòng đó sẽ báo lỗi thiếu thông tin.

> ⚠️ **Cấp bậc (Grade) trên Employee** quyết định **áo sơ mi vs áo thun** (rule áo theo Grade×Gender). Nhân viên thiếu Grade → không khớp rule áo → bị bỏ qua khi cấp/dự toán. Nên đảm bảo Employee có Grade.

**Công cụ hàng loạt (nút trên danh sách Employee Uniform Profile):**
- **Create Missing Profiles** — tạo hồ sơ cho mọi NV Active còn thiếu.
- **Recompute Due Dates** — tính lại hạn kế tiếp + trạng thái toàn bộ (chạy **sau khi đổi Chu kỳ cấp lại** trong Rule).
- **Sync Shoe Rack Locations** — đồng bộ vị trí để dép từ Shoe Rack.

**Ý nghĩa trạng thái** trong bảng theo dõi:

| Trạng thái | Ý nghĩa |
|---|---|
| Not Issued (Chưa cấp) | chưa từng được cấp loại này |
| Active (Còn hạn) | đã cấp, chưa tới kỳ bổ sung |
| Due Soon (Sắp đến hạn) | đến hạn trong vòng 30 ngày tới |
| Overdue (Quá hạn) | đã quá hạn cấp bổ sung |

## 2.3 Bước 2 — Nhập kho đồng phục

Khi nhận hàng từ nhà cung cấp:

1. Vào **Stock Entry → New**.
2. Stock Entry Type = **Material Receipt**.
3. Target Warehouse = **kho Uniform** (không cần kho nguồn).
4. Thêm từng dòng: chọn **variant cụ thể** (ví dụ `Áo sơ mi nam Xl`), số lượng, và **Basic Rate** = đơn giá (phục vụ báo cáo chi phí).
5. Save → Submit. Tồn kho Uniform tăng ngay.

## 2.4 Bước 3 — Cấp phát theo lô

1. Vào **Uniform Allocation → New**.
2. Chọn **Allocation Type** — mỗi loại có quy tắc lọc và chặn riêng:

   | Loại | Ai được liệt kê | Chặn khi Submit |
   |---|---|---|
   | **New Issue** (Cấp mới) | Chưa từng được cấp loại đó **và** đủ ngày làm việc theo quy định | ❌ Chặn dòng của người **đã** được cấp loại đó (báo ngày cấp gần nhất, gợi ý dùng Supplement/Replacement) |
   | **Supplement** (Cấp bổ sung) | Đã được cấp **và** đến hạn hoặc **sắp đến hạn trong N ngày tới** (N = Reminder Days Before trong Setting, mặc định 30 — để HR chuẩn bị trước) | ❌ Chặn dòng của người **chưa từng** được cấp loại đó (gợi ý dùng New Issue) |
   | **Replacement** (Thay thế) | Hỏng / đổi size / mất — **HR thêm từng người thủ công** (không lọc, không Get Employees) | Không chặn thêm (van thủ công có kiểm soát) |
3. **Bộ lọc hiện theo Allocation Type:**
   - **New Issue**: Loại đồng phục, Phòng ban/Nhóm/Giới tính, **Ngày nhận việc từ/đến**.
   - **Supplement**: Loại đồng phục, Phòng ban/Nhóm/Giới tính, **Hạn cấp từ/đến** + **Chỉ quá hạn** (lọc theo `next_due`; bỏ trống = đến hạn trong N ngày nhắc + quá hạn). *(Ẩn ngày nhận việc.)*
   - **Replacement**: ẩn toàn bộ filter — thêm tay từng người.
4. Bấm **Get Employees** (New Issue/Supplement) → **cộng dồn** NV đủ điều kiện vào bảng Items (bấm nhiều lần với bộ lọc khác nhau để gộp; **dòng trùng tự bỏ qua**). Dòng thiếu size/variant được liệt kê để HR bổ sung hồ sơ rồi bấm lại. Vẫn thêm/sửa/xóa tay được. Lưu sẽ **tự loại dòng trùng** (cùng NV + item) kèm cảnh báo.
5. **Save** (Draft) → kiểm tra lại → **Submit**.

Khi Submit, hệ thống tự động:
- Chặn nếu có nhân viên không còn Active hoặc đã có ngày nghỉ việc.
- Chặn dòng **không khớp Loại cấp phát** (xem bảng ở bước 2) — áp dụng cả với dòng thêm tay.
- Chặn nếu **tổng** SL theo từng variant vượt tồn kho (liệt kê rõ thiếu bao nhiêu) → đi nhập kho rồi submit lại. *(Dòng tick **Tái sử dụng đồ cũ** được bỏ qua khi kiểm tra tồn.)*
- Sinh 1 phiếu xuất kho (Material Issue) — xem được qua field **Stock Entry**. **Dòng tick "Tái sử dụng đồ cũ (không xuất kho)" không bị trừ kho**; nếu cả phiếu đều là đồ tái sử dụng thì không tạo phiếu xuất kho.
- Cập nhật hồ sơ từng nhân viên: ngày cấp, tổng đã cấp, hạn cấp kế tiếp (kể cả dòng tái sử dụng — nhân viên vẫn được ghi nhận đã nhận đồ).

**Nhân viên mới**: hệ thống chỉ tự tạo **Employee Uniform Profile**, **không** tự tạo Uniform Allocation. Khi cần cấp, HR tự tạo 1 Allocation và dùng **Get Employees** để gộp nhiều người vào cùng một chứng từ (tránh tạo nhiều phiếu rời rạc mỗi người một cái).

**Hủy chứng từ**: mở Allocation đã submit → Cancel. Phiếu xuất kho bị hủy theo, tồn kho hoàn lại, hồ sơ nhân viên được tính lại theo các đợt cấp còn lại.

## 2.5 Item "Cấp một lần" (Mũ / Dép / Bình nước)

- Ai được cấp do **điều kiện trong Rule** quyết định (Grade/Designation/Group/Section).
- Cấp **một lần** (Rule đánh dấu One-Time Issue) — không xuất hiện trong Cấp bổ sung, không có hạn cấp lại.
- Hỏng/mất/đổi → tạo Allocation loại **Replacement**, thêm dòng thủ công.

## 2.6 Nhập lịch sử cấp phát cũ (trước khi dùng ERP) — chỉ làm 1 lần

> Issuance Tracking trên form là **read-only** (không sửa tay). Việc nhập lịch sử cũ chỉ làm **một lần ban đầu** qua **Data Import** (chạy server-side, bỏ qua read-only). Từ khi dùng ERP, mọi cấp phát đi qua **Uniform Allocation** và Tracking tự cập nhật.

**Nhập hàng loạt (Data Import)** trên DocType Employee Uniform Profile (Update Existing Records), cột:
`ID` (= mã nhân viên), `Item (Uniform Items)` = **variant cụ thể** đã cấp (vd `Áo thun nữ S`, `Mũ Đỏ - Qc`, `Dép 27`), `Last Issue Date (Uniform Items)`, `Last Issue Qty (Uniform Items)`, `Total Issued Qty (Uniform Items)`.
→ Next Due Date và Status **không cần nhập** — tự tính khi import (từ chu kỳ trong Rule).

Từ đó NV tự xuất hiện trong danh sách *Cấp bổ sung* khi đến hạn; các đợt sau làm bằng Uniform Allocation.

> **Nút Rebuild Tracking** (trên từng hồ sơ): dựng lại Tracking từ các Allocation đã submit khi nghi dữ liệu lệch. Dòng lịch sử cũ (nhập tay, không có Allocation) được **giữ nguyên**.

> Hồ sơ của toàn bộ nhân viên Active đã được tạo sẵn (973 hồ sơ). Nếu sau này cần tạo lại hàng loạt: `bench --site erp.tiqn.local execute customize_erpnext.uniform_control.api.onboarding.backfill_uniform_profiles`

## 2.7 Dashboard

Vào **/app/uniform-dashboard** (tìm "Uniform Dashboard" trong thanh tìm kiếm). Gồm:

- **5 thẻ số liệu**: variant có tồn, tồn thấp, sắp đến hạn, quá hạn, số đợt cấp 30 ngày. Bấm thẻ **Due Soon/Overdue** mở thẳng báo cáo **Uniform Tracking** đã lọc sẵn.
- **Bảng "Stock Plan" (Kế hoạch nhập kho)** (trọng tâm) — mỗi variant một dòng: `Loại | Item | Tồn | Cần re-issue | Cần forecast | Tổng cần | Thiếu`. **Thiếu = Tổng cần − Tồn**, tô đỏ khi > 0 → biết ngay cần mua bao nhiêu.
  - **Cần re-issue**: nhu cầu cấp lại của NV hiện tại đến mốc **"Đến hạn vào/trước"** — **mặc định hôm nay** (chỉ tính món đang đến hạn). **Đếm đủ số chu kỳ** trong khoảng (item chu kỳ 6 tháng, mốc xa 1 năm → tính 2 lần).
  - **Cần forecast**: bấm **"Cộng nhu cầu dự toán…"** chọn 1+ Uniform Demand Forecast → cộng số lượng dự toán vào cột này.
    - Forecast kiểu **New Hires** → cộng bình thường; **không** đổi mốc "Đến hạn vào/trước" (giữ mốc bạn đang chọn).
    - Forecast kiểu **Re-issue / Both** (đã bao gồm nhu cầu cấp lại) → tự đặt mốc theo **To Date của forecast**, đồng thời **ẩn cột Cần re-issue** để **tránh tính lặp** (có ghi chú cam cảnh báo).
  - Bảng dùng lưới chuẩn Frappe: **sắp xếp/lọc từng cột** ngay trên đầu cột.
- **Bảng "Employees Due for Issue"** (thu gọn, bấm mở): mỗi NV/item kèm **SL/chu kỳ · Số chu kỳ · Tổng SL** trong khoảng lọc; click mã NV mở hồ sơ.
- **2 biểu đồ**: số lượng cấp theo tháng và theo nhóm (Group).
- **Nút thao tác**: Cấp phát, Nhập kho, Lịch sử, Hồ sơ, **Uniform Tracking**, **Demand Forecast** (dự toán), **Xuất Excel** (2 sheet: Kế hoạch nhập kho + NV đến hạn — theo đúng mốc lọc & forecast đang chọn).

## 2.8 Theo dõi & cảnh báo

- **Email thứ Hai 08:30 hàng tuần** gồm 2 bảng: variant tồn thấp cần nhập thêm, và nhân viên sắp/đã đến hạn cấp bổ sung.
- Danh sách nhân viên đến hạn cũng xem được bằng Excel (mục 2.7).

## 2.9 Báo cáo qua Excel (Power Query)

Excel → Data → Get Data → From Web, dán URL (đăng nhập ERPNext trên trình duyệt cùng máy hoặc dùng API key):

| Báo cáo | URL |
|---|---|
| Tồn kho + cờ tồn thấp | `https://<server>/api/method/customize_erpnext.uniform_control.api.uniform_excel_api.get_uniform_stock_excel` |
| NV đến hạn cấp | `.../uniform_excel_api.get_due_employees_excel?allocation_type=Supplement` |
| Lịch sử cấp phát | `.../uniform_excel_api.get_allocation_history_excel?from_date=2026-01-01&to_date=2026-12-31` |
| Chi phí đồng phục | `.../uniform_excel_api.get_uniform_cost_excel?group_by=department` (`group_by`: employee / department / period) |

Tham số lọc thêm: `department=`, `uniform_type=`, `employee=` (nối bằng `&`).

## 2.10 Dự toán nhu cầu đồng phục (Uniform Demand Forecast)

Dùng để **chuẩn bị/nhập kho trước**. Vào Dashboard → **Demand Forecast** → New.

**Chọn Mode (Chế độ):**
- **New Hires** — nhu cầu cho **nhân viên sẽ tuyển mới**, nhập trong bảng **Chức danh cần tuyển** (Designation + Số cần tuyển). Cơ cấu **cấp bậc/giới tính/nhóm/bộ phận** + tỷ lệ size **suy từ nhân viên hiện tại** cùng chức danh (nên nên đảm bảo NV hiện tại có Grade đúng). Chức danh hoàn toàn mới (chưa có ai) → hiện cảnh báo để nhập tay.
- **Re-issue** — nhu cầu **cấp lại** của NV hiện tại, **đếm đủ số chu kỳ** đến **To Date** (mặc định hôm nay + 1 năm).
- **Both** — cộng cả hai.

**Các bước:**
1. Chọn **Mode**. Với New Hires: điền bảng **Chức danh cần tuyển** (chức danh + số lượng). Với Re-issue: đặt **To Date**. (Warehouse mặc định kho đồng phục.) **Save**.
2. Bấm nút **Forecast** (góc trên phải). Hệ thống tính nhu cầu theo từng **variant** (áo nam/nữ theo size, mũ theo bộ phận, dép, bình nước…) + **tồn hiện tại**.
3. Có thể **sửa tay** cột **SL dự toán** rồi Save (tổng tự tính lại). Bấm **Tải Excel** để xuất toàn bộ phiếu — 5 sheet: **Info** (mode, ngày, kho, tổng, ghi chú), **Recruitment Plan** (bảng chức danh cần tuyển), **Forecast** (kết quả), **Current Ratio (Recruited)** và **Current Ratio (Company)**.

**Cách tính New Hires:** với mỗi chức danh, số lượng tuyển được chia theo cơ cấu **Cấp bậc / Giới tính / Nhóm / Bộ phận** của nhân viên hiện hữu cùng chức danh. Áp **Rules**: **Giới tính** → áo Nam/Nữ; **Cấp bậc** → áo sơ mi (theo grade); **Nhóm/Bộ phận** → màu mũ. Riêng **áo** chia tiếp theo **tỷ lệ size** — **làm tròn theo NGƯỜI, mỗi người 1 size**, rồi ×`first_qty` (nên SL mỗi size là bội của first_qty, không có "nửa người"). Chức danh mới kiểu `…-Trainee` chưa có ai sẽ **tự dùng chức danh gốc** (vd `Sewing Worker-Trainee` → `Sewing Worker`); chức danh hoàn toàn mới (không có nhân viên để suy) sẽ **hiện cảnh báo** để HR nhập tay.

**Hai bảng tham chiếu (chỉ để xem, KHÔNG ảnh hưởng kết quả):**
- **Tỉ lệ áo hiện tại**: phân bố áo của NV hiện tại (theo Giới tính × Size), tính đến **ngày tạo** phiếu. Có 2 nút chọn phạm vi: **"Chức danh tuyển"** (mặc định — đúng cơ sở tính của Forecast) và **"Toàn công ty"** (tham khảo chung). Forecast Items **luôn tính theo từng chức danh**, không đổi khi bấm 2 nút này.
- **Phân tích áo dự toán**: kết quả áo (Forecast Items) theo loại × giới tính × size.

> Có thể đưa nhu cầu một/nhiều forecast vào **bảng Kế hoạch nhập kho** trên Dashboard (nút "Cộng nhu cầu dự toán…") để gộp với nhu cầu cấp lại.

**Nếu hiện cảnh báo cam "Vui lòng rà soát":** một số người chưa đủ đồ — thường do **thiếu Grade** trên nhân viên/dòng tuyển, **thiếu Rule**, hoặc **size chưa có sản phẩm**. Cảnh báo ghi rõ ai/bao nhiêu người → bổ sung rồi bấm **Forecast** lại.

## 2.11 Câu hỏi thường gặp

**Nhân viên sắp nghỉ việc có cấp được không?**
Không. Nhân viên có ngày nghỉ việc (relieving date) bị loại khỏi danh sách và bị chặn khi submit.

**Submit báo thiếu hàng nhưng từng dòng đều ≤ tồn?**
Hệ thống cộng dồn theo variant: 2 nhân viên cùng nhận áo size M Nam 3 cái/người = cần 6 cái. Nhập kho thêm rồi submit lại.

**Cấp nhầm thì sửa thế nào?**
Cancel chứng từ (tồn kho và hồ sơ tự hoàn lại) → tạo chứng từ mới hoặc dùng Amend.

**Đổi size cho nhân viên?**
Cập nhật size trong hồ sơ → tạo Allocation loại Replacement, lý do "Size Change". (Thu hồi đồ cũ xử lý ngoài hệ thống.)
