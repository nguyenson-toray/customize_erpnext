# Uniform Control — Hướng dẫn sử dụng

Module quản lý tồn kho & cấp phát đồng phục cho nhân viên (ERPNext/HRMS v16, app `customize_erpnext`).

- **Phần 1 — IT Admin**: thiết lập một lần (master data, kho, cấu hình, phân quyền).
- **Phần 2 — HR (Uniform Manager)**: sử dụng hàng ngày (nhập kho, cấp phát, theo dõi).

---

# PHẦN 1 — IT ADMIN

## 1.1 Nguyên tắc thiết kế item (đã đơn giản hóa)

- Mỗi template chỉ dùng **1 variant attribute** (attribute `Size` hoặc `Color` sẵn có của hệ thống).
- **Giới tính tách thành template riêng** (T-Shirt Male / T-Shirt Female...), không dùng attribute giới tính. Việc cấp đúng giới tính cấu hình qua policy `Applies To = Gender` (xem §1.6).
- Item Group: **`U-Uniform`** — mọi item đồng phục thuộc nhóm này.

## 1.2 Item đã tạo (hiện trạng)

| Item Code | Variants | Attribute | Giá trị đang có |
|---|---|---|---|
| `Uniform T-Shirt Male` | ✅ | Size | S, M, L, Xl, 2Xl, 3Xl |
| `Uniform T-Shirt Female` | ✅ | Size | S, M, L, Xl, 2Xl, 3Xl |
| `Uniform Shirt Male` | ✅ |  Size | S, M, L, Xl, 2Xl, 3Xl |
| `Uniform Shirt Female` | ✅ |  Size | S, M, L, Xl, 2Xl, 3Xl |
| `Cap` | ✅ | Color | Blue, Green, Red |
| `Shoe` | ✅ | Color | 29, 30, 31 |
| `Bottle` | ❌ item đơn | — | — |

Cấu hình chung: Item Group = `U-Uniform`, `Maintain Stock = 1`, không bật Serial/Batch.

> ⚠️ Giá trị attribute Size được hệ thống chuẩn hóa title-case (`Xl`, `2Xl`, `3Xl`). Hồ sơ nhân viên chọn `XL/2XL/3XL` và code tự map sang `Xl/2Xl/3Xl` — không cần làm gì thêm, nhưng nếu tạo size mới (vd `4Xl`) thì cần báo IT cập nhật options trong Employee Uniform Profile.

## 1.3 Thêm size/màu mới sau này

1. Thêm Attribute Value vào attribute `Size` hoặc `Color` (nếu chưa có).
2. Mở template → **Create Variants** cho giá trị mới.
3. Cập nhật options của field tương ứng trong Employee Uniform Profile (Shirt Size / Cap Color / Shoe Size) nếu giá trị mới chưa nằm trong danh sách chọn.

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

| Field | Giá trị khuyến nghị |
|---|---|
| Uniform Warehouse | Uniform - TIQN |
| Uniform Item Group | U-Uniform — quyết định bộ lọc item trên Hồ sơ đồng phục (Áo được gán, Uniform Type) và bảng Policies |
| Reminder Days Before | 30 (cảnh báo trước hạn 30 ngày) |
| Enable Weekly Alert | ✅ |
| Alert Recipients | email HR, phân tách dấu phẩy: `hr@tiqn.com.vn, it@tiqn.com.vn` |
| Auto Create Onboarding Allocation | ✅ (tự sinh draft cấp phát khi có nhân viên mới đủ điều kiện) |
| Low Stock Use Reorder | ✅ |

### Bảng Policies (Quy định cấp phát)

Mỗi dòng = quy định cho 1 loại đồng phục × 1 nhóm đối tượng:

| Field | Ý nghĩa |
|---|---|
| Uniform Type | Item template (Uniform T-Shirt Male, Cap, Shoe, ...) |
| **Variant Source** | Field nào trong hồ sơ NV quyết định variant: **Shirt Size** (áo) / **Cap Color** (mũ) / **Shoe Size** (giày). **Bắt buộc** với item có variant; bỏ trống với item đơn |
| **One-Time Issue** | ✅ = cấp một lần (bình nước): không cấp bổ sung, không có hạn cấp lại, chỉ tự đề xuất cho NV có tick "Issued Bottle" |
| Applies To | All / Department / Designation / Gender |
| Department + Group | điền khi Applies To = Department |
| Designation | điền khi Applies To = Designation |
| Gender | điền khi Applies To = Gender |
| First Issue Qty | SL cấp lần đầu |
| Eligible After (Days) | đủ điều kiện sau N ngày làm việc (tính từ ngày vào) |
| Reissue Cycle (Months) | chu kỳ cấp bổ sung; **0 = không cấp bổ sung** |
| Reissue Qty per Cycle | SL mỗi lần bổ sung |
| Active | bật/tắt dòng quy định |

**Bộ policies mẫu cho item hiện tại** (quy định thời gian **không phân biệt giới tính** — Applies To = All):

| Uniform Type | Variant Source | One-Time | Assigned per Employee | Applies To |
|---|---|---|---|---|
| Uniform T-Shirt Male | Shirt Size | | ✅ | All |
| Uniform T-Shirt Female | Shirt Size | | ✅ | All |
| Uniform Shirt Male | Shirt Size | | ✅ | All |
| Uniform Shirt Female | Shirt Size | | ✅ | All |
| Cap | Cap Color | | | All |
| Shoe | Shoe Size | | | All |
| Bottle | *(trống — item đơn)* | ✅ | | All |

> **Áo gán thủ công theo nhân viên**: 4 template áo đều tick `Assigned per Employee` — nhân viên chỉ được đề xuất đúng template đã chọn ở field **Áo được gán (Assigned Shirt Item)** trong hồ sơ. HR có thể gán áo nữ cho nhân viên nam và ngược lại. 4 dòng policy áo nên có cùng thông số thời gian (chu kỳ, SL) vì quy định không phân biệt giới tính.

**Độ ưu tiên khi 1 nhân viên khớp nhiều dòng** (không phụ thuộc thứ tự trong bảng):

```
Department + Group  >  Department  >  Designation  >  Gender  >  All
```

Ví dụ: có dòng "All: polo 2 cái" và dòng "Department Sewing: polo 3 cái" → công nhân may được áp dòng 3 cái.

## 1.7 Phân quyền

- Gán role **`Uniform Manager`** cho user HR (User → Roles).
- Role này có quyền read/write/create/submit/cancel trên: Uniform Setting, Uniform Allocation, Employee Uniform Profile (không có quyền delete).
- HR cần thêm quyền tạo **Stock Entry** nếu nhập kho qua Desk (hoặc dùng API `receive_stock`).

## 1.8 Các tự động hóa đã cài (không cần thao tác)

| Sự kiện | Hành vi |
|---|---|
| Tạo Employee mới | Tự tạo **Employee Uniform Profile** (link 2 chiều qua field Uniform Profile trên Employee), tự điền giới tính từ Employee |
| Lưu Employee (Active, đủ ngày, chưa cấp mới) | Nếu bật Auto Create Onboarding Allocation → tự sinh **draft** Uniform Allocation loại New Issue để HR review & submit |
| Thứ Hai 08:30 hàng tuần | Gửi email tới Alert Recipients: bảng tồn thấp + bảng nhân viên đến hạn cấp bổ sung |
| Submit Uniform Allocation | Sinh 1 Stock Entry Material Issue, cập nhật hồ sơ từng nhân viên |
| Cancel Uniform Allocation | Cancel Stock Entry liên quan, tính lại hồ sơ từ các đợt cấp còn lại |

## 1.9 Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân / cách xử lý |
|---|---|
| `Variant Source is not set in Uniform Policy for X` | Policy của template X chưa chọn Variant Source → IT bổ sung trong Uniform Setting |
| `Profile missing value for 'Shirt Size'` (hoặc Cap Color / Shoe Size) | Hồ sơ nhân viên chưa điền thông số đó → HR bổ sung profile |
| `No variant found for X with Size = Y` | Variant chưa được tạo cho giá trị đó → tạo thêm variant (§1.3) |
| Submit Allocation báo "Insufficient stock" | Tổng SL theo từng variant (cộng dồn nhiều dòng) vượt tồn kho Uniform → nhập kho trước |
| Email weekly không gửi | Kiểm tra Enable Weekly Alert + Alert Recipients trong Uniform Setting; xem Error Log với title "Uniform Weekly Alert Error" |
| Onboarding không sinh draft allocation | Xem Error Log "Create Onboarding Allocation Error"; kiểm tra policy Active, Eligible After Days, và profile đã đủ size chưa |

Lỗi nền được ghi vào **Error Log** (Desk → Error Log).

---

# PHẦN 2 — HR (UNIFORM MANAGER)

## 2.1 Khái niệm nhanh

- **Employee Uniform Profile** (Hồ sơ đồng phục): 1 hồ sơ / nhân viên — lưu size áo, giới tính, loại mũ, size dép, vị trí để dép, cờ cấp bình nước; kèm bảng theo dõi đã cấp gì, khi nào đến hạn.
- **Uniform Allocation** (Chứng từ cấp phát): 1 chứng từ cấp cho **nhiều nhân viên** cùng lúc. Submit xong hệ thống tự trừ kho và cập nhật hồ sơ — HR không cần thao tác kho.

## 2.2 Bước 1 — Hoàn thiện hồ sơ đồng phục

Hồ sơ được tạo tự động khi nhân viên mới vào. HR mở **Employee Uniform Profile** (hoặc từ form Employee → field Uniform Profile) và điền:

| Field | Ghi chú |
|---|---|
| **Assigned Shirt Item (Áo được gán)** | Chọn template áo nhân viên này nhận (T-Shirt Male / T-Shirt Female / Shirt Male / Shirt Female). **Gán tự do, không phụ thuộc giới tính** — có thể gán áo nữ cho nhân viên nam và ngược lại |
| Uniform Gender | Male / Female (thông tin tham khảo) |
| Shirt Size | S / M / L / XL / 2XL / 3XL — dùng chung cho polo & sơ mi |
| Cap Color | Blue / Green / Red |
| Shoe Size | 29 → 44 (chỉ chọn size đã có variant trong kho; thêm size mới xem §1.3) |
| Shoe Rack Location | **read-only, tự động** lấy Rack Name từ DocType Shoe Rack (mỗi rack chứa 1–2 nhân viên). Muốn đổi vị trí → sửa phân bổ trong Shoe Rack, profile tự cập nhật |
| Issued Bottle | ✅ nếu nhân viên thuộc diện được cấp bình nước |

**Đổi áo cho nhân viên**: chỉ cần đổi Assigned Shirt Item rồi Save. Template mới chưa từng cấp → nhân viên sẽ xuất hiện ở danh sách *Cấp mới* cho template đó. Lịch sử được giữ nguyên ở 2 nơi: bảng Issuance Tracking (mỗi loại đã cấp một dòng riêng) và nhật ký thay đổi hồ sơ (menu ⋯ → **History** trên form).

> ⚠️ Hồ sơ thiếu thông số nào thì khi cấp phát hệ thống không tự điền được variant tương ứng — dòng đó sẽ báo lỗi thiếu thông tin.

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
4. Thêm từng dòng: chọn **variant cụ thể** (ví dụ `Uniform T-Shirt Male-08F` — size Xl), số lượng, và **Basic Rate** = đơn giá (phục vụ báo cáo chi phí).
5. Save → Submit. Tồn kho Uniform tăng ngay.

## 2.4 Bước 3 — Cấp phát theo lô

1. Vào **Uniform Allocation → New**.
2. Chọn **Allocation Type** — mỗi loại có quy tắc lọc và chặn riêng:

   | Loại | Ai được liệt kê | Chặn khi Submit |
   |---|---|---|
   | **New Issue** (Cấp mới) | Chưa từng được cấp loại đó **và** đủ ngày làm việc theo quy định | ❌ Chặn dòng của người **đã** được cấp loại đó (báo ngày cấp gần nhất, gợi ý dùng Supplement/Replacement) |
   | **Supplement** (Cấp bổ sung) | Đã được cấp **và** đến hạn hoặc **sắp đến hạn trong N ngày tới** (N = Reminder Days Before trong Setting, mặc định 30 — để HR chuẩn bị trước) | ❌ Chặn dòng của người **chưa từng** được cấp loại đó (gợi ý dùng New Issue) |
   | **Replacement** (Thay thế) | Chỉ người **đã được cấp** loại đó — hỏng / đổi size / mất; chọn thủ công, bắt buộc có filter thu hẹp | Không chặn thêm (van thủ công có kiểm soát) |
3. Kho xuất và Company tự điền; khoanh vùng bằng các filter: **Loại đồng phục**, **Phòng ban**, **Ngày nhận việc từ/đến** (lọc theo date_of_joining).
4. Bấm nút **Get Employees (Lấy danh sách nhân viên)** → hệ thống tự đổ vào bảng Items các nhân viên đủ điều kiện kèm variant đúng size, SL theo policy, tồn kho từng dòng. Dòng nào thiếu thông số (chưa điền size, chưa gán áo...) sẽ được liệt kê để HR bổ sung hồ sơ rồi bấm lại. Vẫn có thể thêm/sửa/xóa dòng thủ công sau khi đổ.
5. **Save** (Draft) → kiểm tra lại → **Submit**.

Khi Submit, hệ thống tự động:
- Chặn nếu có nhân viên không còn Active hoặc đã có ngày nghỉ việc.
- Chặn dòng **không khớp Loại cấp phát** (xem bảng ở bước 2) — áp dụng cả với dòng thêm tay.
- Chặn nếu **tổng** SL theo từng variant vượt tồn kho (liệt kê rõ thiếu bao nhiêu) → đi nhập kho rồi submit lại.
- Sinh 1 phiếu xuất kho (Material Issue) — xem được qua field **Stock Entry**.
- Cập nhật hồ sơ từng nhân viên: ngày cấp, tổng đã cấp, hạn cấp kế tiếp.

**Draft tự sinh khi có nhân viên mới**: nếu IT bật tự động hóa, mỗi nhân viên mới đủ điều kiện sẽ có sẵn 1 Uniform Allocation ở trạng thái Draft — HR chỉ cần mở, kiểm tra, Submit.

**Hủy chứng từ**: mở Allocation đã submit → Cancel. Phiếu xuất kho bị hủy theo, tồn kho hoàn lại, hồ sơ nhân viên được tính lại theo các đợt cấp còn lại.

## 2.5 Quy tắc riêng cho bình nước (item "Cấp một lần")

- Chỉ cấp cho nhân viên có tick **Issued Bottle** trong hồ sơ.
- Cấp **một lần duy nhất** (policy đánh dấu One-Time Issue) — không bao giờ xuất hiện trong danh sách Cấp bổ sung, không có hạn cấp lại.
- Nhân viên làm hỏng/mất → tạo Allocation loại **Replacement**, thêm dòng thủ công.

## 2.6 Nhập lịch sử cấp phát cũ (trước khi dùng ERP)

Nếu đã cấp đồng phục/trừ kho ngoài hệ thống, **nhập tay lịch sử vào hồ sơ** để hệ thống tự tính hạn cấp tiếp theo — không cần tạo chứng từ giả:

1. Mở **Employee Uniform Profile** của nhân viên → bảng **Issuance Tracking**, thêm dòng:
   - `Uniform Type` = template (Uniform T-Shirt Male, Hat, Shoe, ...)
   - `Last Issue Date` = ngày cấp thực tế gần nhất
   - `Last Issue Qty` và `Total Issued Qty` = số lượng đã cấp (Total > 0 để hệ thống biết "đã cấp", không đưa vào danh sách Cấp mới nữa)
2. **Save** → hệ thống **tự tính** `Next Due Date` (= Last Issue Date + chu kỳ trong policy) và `Status` (Còn hạn / Sắp đến hạn / Quá hạn).

Từ đó trở đi, nhân viên tự xuất hiện trong danh sách *Cấp bổ sung* khi đến hạn, và đợt cấp tiếp theo làm trên ERP bình thường.

**Nhập hàng loạt**: dùng **Data Import** trên DocType Employee Uniform Profile (Update Existing Records), cột: `ID` (= mã nhân viên), `Uniform Type (Uniform Items)`, `Last Issue Date (Uniform Items)`, `Last Issue Qty (Uniform Items)`, `Total Issued Qty (Uniform Items)`. Next Due Date và Status không cần nhập — tự tính khi import.

> Hồ sơ của toàn bộ nhân viên Active đã được tạo sẵn (973 hồ sơ). Nếu sau này cần tạo lại hàng loạt: `bench --site erp.tiqn.local execute customize_erpnext.uniform_control.api.onboarding.backfill_uniform_profiles`

## 2.7 Dashboard

Vào **/app/uniform-dashboard** (tìm "Uniform Dashboard" trong thanh tìm kiếm). Gồm:

- **5 thẻ số liệu**: variant có tồn, tồn thấp (đỏ), sắp đến hạn (vàng), quá hạn (đỏ), số đợt cấp 30 ngày.
- **2 biểu đồ**: số lượng cấp theo tháng và theo phòng ban.
- **Bảng NV đến hạn** (vàng = sắp đến hạn, đỏ = quá hạn) — click mã NV mở thẳng hồ sơ.
- **Bảng tồn kho** — dòng đỏ là variant dưới ngưỡng cần nhập thêm; click mở Item.
- **Nút thao tác**: Cấp phát (tạo Uniform Allocation), Nhập kho (tạo Material Receipt), Lịch sử, Hồ sơ đồng phục.

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

## 2.10 Câu hỏi thường gặp

**Nhân viên sắp nghỉ việc có cấp được không?**
Không. Nhân viên có ngày nghỉ việc (relieving date) bị loại khỏi danh sách và bị chặn khi submit.

**Submit báo thiếu hàng nhưng từng dòng đều ≤ tồn?**
Hệ thống cộng dồn theo variant: 2 nhân viên cùng nhận áo size M Nam 3 cái/người = cần 6 cái. Nhập kho thêm rồi submit lại.

**Cấp nhầm thì sửa thế nào?**
Cancel chứng từ (tồn kho và hồ sơ tự hoàn lại) → tạo chứng từ mới hoặc dùng Amend.

**Đổi size cho nhân viên?**
Cập nhật size trong hồ sơ → tạo Allocation loại Replacement, lý do "Size Change". (Thu hồi đồ cũ xử lý ngoài hệ thống.)
