# Uniform Control — Hướng dẫn sử dụng

> **Mục đích:** Module quản lý tồn kho & cấp phát đồng phục cho nhân viên (ERPNext/HRMS v16, app `customize_erpnext`).
> **Phạm vi:** Module Đồng phục
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-11-09 (đơn giản hoá: 1 loại phiếu, size lấy từ Employee, Manual Override, tự đồng bộ)
> **Triển khai bản 09/11:** code đã commit; các bước còn lại ở **§1.10**.

- **Phần 1 — IT Admin**: thiết lập một lần (master data, kho, cấu hình, phân quyền).
- **Phần 2 — HR**: sử dụng hằng ngày (nhập kho, cấp phát, theo dõi).

HR chỉ cần 3 màn hình: **Uniform Dashboard** (ai đến hạn, cần mua gì, nhập kho), **Uniform Allocation** (phiếu cấp phát), **Employee Uniform Profile** (xem từng người).

---

# PHẦN 1 — IT ADMIN

## 1.1 Nguyên tắc thiết kế item

- Mỗi template chỉ dùng **1 variant attribute** (`Size` cho áo/dép, `Color` cho mũ).
- **Giới tính tách thành template riêng** (áo nam / áo nữ). Cấp đúng giới tính do **Rule** quyết định (điều kiện Gender, §2.2).
- **Mỗi màu Mũ gắn 1 vai trò** (vd "Đỏ - Qc", "Xanh Dương Đậm - May") → gán theo Rule.
- Item Group: **`U-Uniform`** — mọi item đồng phục thuộc nhóm này; `name = item_name`.

## 1.2 Item hiện trạng

| Item (template) | Attribute | Giá trị |
|---|---|---|
| `Áo sơ mi nam`, `Áo sơ mi nữ` | Size | S, M, L, Xl |
| `Áo thun nam`, `Áo thun nữ` | Size | S, M, L, Xl |
| `Dép` | Size | `Free Size` (cho NV chưa khai size) + `2-3`, `4-5`, `6-7`, `8-9`, `10-11` (đúng các size trên Employee — tạo khi triển khai, §1.10) |
| `Mũ` | Color | 15 màu, mỗi màu gắn vai trò (Đỏ-Qc, Vàng-Trưởng Phòng, Xanh Lá-Nv Văn Phòng...) |
| `Bình nước` | — (item đơn) | — |

Cấu hình chung: Item Group = `U-Uniform`, `Maintain Stock = 1`, không bật Serial/Batch.

> **Size lấy từ Employee**: `Shirt Size` (`custom_shirt_size`: S/M/L/XL/2XL/3XL) và `Shoe Size` (`custom_shoe_size`: 2-3…10-11) — nhân viên tự khai qua cổng tự cập nhật thông tin, hoặc HR sửa trên form Employee. Code tự map `XL → Xl`, `2XL → 2Xl`. **Nhân viên chưa khai size dép → cấp `Dép Free Size`.** Chưa có variant 2Xl/3Xl cho áo → dòng đó bị bỏ qua kèm cảnh báo.

## 1.3 Thêm size/màu mới sau này

1. Thêm Attribute Value vào attribute `Size` hoặc `Color` (attribute `Size` dùng chung toàn công ty).
2. Mở template → **Create Variants** cho giá trị mới (đặt `name = item_name` cho rõ).
3. Nếu là size mới mà Employee chưa có lựa chọn → thêm vào options field `Shirt Size` / `Shoe Size` của **Employee** (Customize Form) — giá trị phải giống hệt attribute value (áo: theo bảng map ở trên).

## 1.4 Tạo Warehouse

Kho leaf: **`Uniform - TIQN`**. Toàn bộ tồn đồng phục nằm tại kho này.

> 🔴 **Bắt buộc gắn tài khoản kho**: công ty bật perpetual inventory nhưng `Uniform - TIQN` chưa có **Account** và công ty chưa có **Default Inventory Account** → mọi phiếu nhập kho / phiếu cấp phát sẽ báo *"Please set Account in Warehouse Uniform - TIQN"*. Kế toán chọn tài khoản rồi điền vào Warehouse → field **Account**.

## 1.5 Đặt Reorder Level (ngưỡng cảnh báo tồn thấp)

Trên **từng variant** (không phải template): Item → tab Inventory → bảng **Reorder level**: `Check in (warehouse)` = Uniform - TIQN, `Reorder Level` = ngưỡng (vd 10), `Reorder Qty` = số đề nghị nhập. Thẻ **Low Stock** và email tuần dùng ngưỡng này. **Không** bật auto Material Request.

## 1.6 Cấu hình Uniform Setting

| Field | Giá trị khuyến nghị |
|---|---|
| Uniform Warehouse | Uniform - TIQN |
| Uniform Item Group | U-Uniform — bộ lọc item trên Hồ sơ, Rule, Phiếu cấp phát |
| Default Shirt Item | `Áo thun nữ M` — áo dùng trong Dự toán khi chức danh mới chưa có ai để suy |
| Deduct Attrition / Attrition Window (Months) | cột **Est. for Leavers** (Dashboard + Dự toán), xem §2.8 |
| Employee ID Prefix | `TIQN` — chỉ quản lý NV có mã bắt đầu bằng prefix này |
| Remind Days Before Due | 30 — "sắp đến hạn" và mặc định của ô *Due On or Before* trên phiếu |
| Enable Weekly Alert / Alert Recipients | email thứ Hai 08:30 (người nhận phân tách dấu phẩy) |

Nút trên form Setting: **Manage Uniform Rules**, **Send Alert Now**.

## 1.7 Phân quyền

| Role | Quyền |
|---|---|
| **HR Manager** | Phiếu cấp phát (tạo/submit/cancel), Hồ sơ, Dashboard, nhập kho, Dự toán, **sửa Uniform Rule + Uniform Setting** |
| **HR User** | Như HR Manager nhưng **chỉ xem** Uniform Rule và Uniform Setting |
| Uniform Manager | Giữ như cũ (không bắt buộc gán) |

Nhập kho đồng phục làm trên Dashboard (§2.4) — **không cần quyền Stock Entry**; hệ thống tự tạo phiếu Material Receipt / Material Issue.

## 1.8 Các tự động hóa đã cài (không cần thao tác)

| Khi | Hệ thống làm |
|---|---|
| Bấm Get Employees / mỗi đêm 00:30 | Tự tạo **Employee Uniform Profile** còn thiếu cho NV Active (không dùng hook khi tạo Employee) |
| Mỗi đêm 00:30 | Cập nhật các ô chép từ Employee trên hồ sơ (tên, bộ phận, chức danh, tổ, trạng thái, ngày nghỉ, giới tính, size, vị trí dép); Áo/Mũ theo Rule (hồ sơ không tick Manual Override); **hạn cấp lại + trạng thái** |
| Lưu / xoá một **Uniform Rule** | Chạy nền (vài giây) đúng việc trên cho toàn bộ hồ sơ — **không còn nút Recompute** |
| Submit Uniform Allocation | Sinh 1 Stock Entry Material Issue (bỏ qua dòng *Reuse Old Item*), cập nhật lịch sử cấp từng người |
| Cancel Uniform Allocation | Cancel Stock Entry, tính lại lịch sử từ các phiếu còn lại **+ khôi phục lịch sử import trước ERP** |
| Thứ Hai 08:30 | Email cảnh báo (tồn thiếu + NV đến hạn) — bật/tắt ở Uniform Setting và Scheduled Job Type |

## 1.9 Xử lý sự cố thường gặp

| Triệu chứng | Nguyên nhân / cách xử lý |
|---|---|
| Get Employees bỏ qua dòng: `Employee has no Shirt Size` | NV chưa khai size áo → điền **Shirt Size trên Employee** (Dashboard có link danh sách NV thiếu size) |
| `No variant for X with size/color Y` | Chưa có variant cho size đó → tạo variant (§1.3) |
| `Please set Account in Warehouse Uniform - TIQN…` | Kho chưa gắn tài khoản (§1.4) |
| Submit báo "Insufficient stock" | Tổng SL theo variant (cộng dồn nhiều dòng) vượt tồn → nhập kho trước (dòng *Reuse Old Item* không tính) |
| Error Log "Uniform Profile name conflict" | Mã NV từng bị đổi, hồ sơ cũ còn mang mã cũ trùng NV khác → mở hồ sơ cũ → ⋯ **Rename** thành mã NV hiện tại của nó |
| Email tuần không gửi | Enable Weekly Alert + Alert Recipients; Scheduled Job Type của `send_weekly_uniform_alert` không bị Stopped; Error Log "Uniform Weekly Alert Error" |
| Dự toán báo "chưa đủ đồ" (cam) | Thiếu Grade trên NV/dòng tuyển, thiếu Rule, hoặc size chưa có variant → bổ sung rồi Forecast lại |

Lỗi nền ghi vào **Error Log** ("Uniform Daily Refresh Error", "Uniform Tracking Refresh Error"...).

## 1.10 Triển khai bản đơn giản hoá (09/11/2026)

| | Việc | Ghi chú |
|---|---|---|
| ✅ | Code đã commit | |
| ✅ | Nạp cấu trúc 5 DocType + 2 báo cáo (`reload_doc`) | chưa gồm quyền HR |
| ✅ | Tạo 130 hồ sơ còn thiếu, đổi tên 7 hồ sơ mã cũ, điền link trên Employee | |
| ⬜ | **Kế toán chọn tài khoản cho kho `Uniform - TIQN`** (§1.4) | bắt buộc trước khi nhập kho / cấp phát |
| ⬜ | Tạo variant `Dép 2-3`, `Dép 4-5`, `Dép 6-7`, `Dép 8-9`, `Dép 10-11` (attribute `Size`, tên item = "Dép" + size); disable `Dép 26`…`Dép 32` (chưa từng nhập/cấp) | NV đã khai size dép mới nhận đúng size |
| ⬜ | Nạp quyền HR Manager/HR User, chạy patch `uniform_manual_override_from_assignments`, đăng ký job đêm → `bench migrate` rồi `bench restart` | ⚠️ lần `bench migrate` kế tiếp (do bất kỳ ai chạy) sẽ tự làm bước này |
| ⬜ | Dịch vi.po các chuỗi mới (sau khi test giao diện) | |

---

# PHẦN 2 — HR

## 2.1 Khái niệm nhanh

- **Uniform Allocation** (phiếu cấp phát) = **nguồn sự thật** của lịch sử cấp: 1 phiếu cho nhiều NV, có Stock Entry. Submit → trừ kho & cập nhật hồ sơ.
- **Employee Uniform Profile** (hồ sơ đồng phục, 1 NV 1 hồ sơ):
  - **Size và giới tính**: chỉ hiển thị, lấy từ Employee.
  - **Áo / Mũ** được cấp: theo Rule; tick **Manual Override** để chọn tay.
  - **What This Employee Gets**: bảng tóm tắt mỗi loại sẽ cấp món gì, size nào, chu kỳ.
  - **Issuance Tracking** (lịch sử cấp, chỉ đọc): 2 bảng *Shirts* và *Other Items* — loại đã cấp, ngày gần nhất, tổng SL, **hạn kế tiếp + trạng thái**.
- Hồ sơ của NV đã nghỉ vẫn giữ (lưu lịch sử); danh sách hồ sơ mặc định chỉ hiện NV đang làm.

## 2.2 Quy tắc cấp phát (Uniform Rule)

HR Manager thiết lập. **Mỗi quy tắc là một record** Uniform Rule (sidebar hoặc Uniform Setting → *Manage Uniform Rules*).

Mỗi rule trả lời: AI (Grade/Designation/Group/Section/Gender) nhận **MÓN GÌ**, **MẤY CÁI**, **CHU KỲ** nào. Mỗi **Category** (Shirt/Cap/Shoe/Bottle) chỉ cấp 1 món/người — rule cụ thể thắng rule chung.

| Field | Ý nghĩa |
|---|---|
| **Category** | Shirt / Cap / Shoe / Bottle |
| **Item** | Shirt/Shoe → **template** (size tự chọn theo Employee); Cap → **variant mũ cụ thể**; Bottle → item đơn |
| **Grades** / **Designations** | **Chọn nhiều**. Để trống = tất cả |
| Group / Section / Gender | Điều kiện đơn. Để trống = tất cả. Group = tổ (`custom_group`), Section = bộ phận (`custom_section`) |
| First Issue Qty / Eligible After (Days) | SL cấp lần đầu / đủ điều kiện sau N ngày làm việc |
| Reissue Cycle (Months) / Reissue Qty | chu kỳ + SL cấp lại (**0 = không cấp lại**) |
| One-Time Issue | ✅ = cấp 1 lần (mũ/dép/bình nước) — không cấp lại định kỳ; hỏng/mất thì thêm tay trên phiếu |
| Active | bật/tắt mà không cần xoá |

### Rule nào thắng khi NV khớp nhiều rule (cùng Category)

Mỗi điều kiện **được điền VÀ khớp** cộng điểm; rule **tổng điểm cao nhất thắng**:

| Điều kiện | Điểm |
|---|---|
| Designations | 16 |
| Grades | 8 |
| Group | 4 |
| Section | 2 |
| Gender | 1 |

- Designation (16) nặng hơn cả Grade+Group+Section+Gender cộng lại (15) → rule theo chức danh luôn thắng.
- Grade (8) > Group/Section: **Tổ trưởng luôn đội mũ Tổ trưởng** dù ở bộ phận nào (trừ khi có rule theo Designation).
- Hai rule **cùng điểm**: rule có mã (UNI-RULE-…) lớn hơn thắng — nên tránh, thêm điều kiện để tách.

> **Ví dụ** (Category = Cap): Tổ trưởng QC khớp `Grade = Leader` (8, Mũ Tổ Trưởng) và `Section = QC` (2, Mũ QC) → nhận **Mũ Tổ Trưởng**. QC Worker thường chỉ khớp Section → **Mũ QC**.

**Bộ Rules mẫu (đã cài sẵn):**

| Category | Item | Grade | Designation | Gender | Qty | Cycle | One-Time |
|---|---|---|---|---|---|---|---|
| Shirt | Áo sơ mi nam / nữ | Staff/Leader/Sub Leader/Manager/Factory Manager | | Male / Female | 4 | 12 | |
| Shirt | Áo thun nam / nữ | (mọi grade) | | Male / Female | 2 | 6 | |
| Cap | 15 mũ theo vai trò | theo grade / section / designation | | | 1 | 0 | ✅ |
| Shoe | Dép | | | | 1 | 0 | ✅ |
| Bottle | Bình nước | | | | 1 | 0 | ✅ |

**Kiểm tra kết quả**: danh sách Uniform Rule → nút **Preview Assignments** (báo cáo *Uniform Assignment Preview*): mỗi NV sẽ nhận áo/mũ/dép/bình nào, size gì, và **Problems** (không có rule, thiếu size, chưa có variant). Tick *Only Problems* để xem người cần xử lý; *Only Manual Override* để rà các ngoại lệ.

**Sau khi sửa Rule**: lưu xong là hệ thống tự cập nhật Áo/Mũ và hạn cấp lại cho mọi hồ sơ (chạy nền vài giây). Không có gì cần bấm thêm.

## 2.3 Hồ sơ đồng phục và ngoại lệ (Manual Override)

Hồ sơ tự có (không cần tạo tay). Trên hồ sơ:

| Field | Ghi chú |
|---|---|
| Gender / Shirt Size / Shoe Size | **Chỉ đọc**, lấy từ Employee. Muốn đổi → nút **Edit Sizes on Employee** |
| **Manual Override** | **Bỏ tick** = Áo/Mũ luôn theo Rule (tự cập nhật). **Tick** = HR chọn Áo/Mũ bằng tay; Rule không đổi nữa (ô để trống vẫn theo Rule) |
| Shirt / Cap | Chỉ sửa được khi tick Manual Override |
| Shoe Rack Location | Tự lấy từ Shoe Rack |

> Khi triển khai, patch `uniform_manual_override_from_assignments` **tick Manual Override** cho các hồ sơ có Áo/Mũ khác kết quả Rule (áo từ file lịch sử, mũ gán trước khi có rule mới… — đo 09/11/2026: 185 hồ sơ) để giữ nguyên như cũ. Sau đó rà bằng *Preview Assignments → Only Manual Override*; bỏ tick những người nên theo Rule.

> ⚠️ **Cấp bậc (Grade) trên Employee** quyết định áo sơ mi vs áo thun. NV thiếu Grade → không khớp rule áo sơ mi.

**Ý nghĩa trạng thái** trong lịch sử cấp:

| Trạng thái | Ý nghĩa |
|---|---|
| Not Issued | chưa từng được cấp loại này |
| Active | đã cấp, chưa tới kỳ cấp lại |
| Due Soon | đến hạn trong N ngày tới (Remind Days Before Due) |
| Overdue | đã quá hạn cấp lại |

## 2.4 Nhập kho đồng phục

Dashboard → nút **Receive Stock**: chọn ngày, thêm dòng **Item (size/màu cụ thể)**, **Qty**, **Unit Price** (bắt buộc — dùng cho giá trị tồn kho) → **Receive**. Hệ thống tạo + submit phiếu Material Receipt vào kho Uniform. Chỉ nhận item thuộc nhóm đồng phục, loại variant cụ thể (không nhận template).

## 2.5 Cấp phát (Uniform Allocation)

**Cách nhanh nhất**: Dashboard → **Create Allocation for Due** → phiếu mới đã có sẵn mọi món đến hạn đến ngày đang lọc trên dashboard.

Hoặc **Uniform Allocation → New**:

1. (Tuỳ chọn) lọc: **Department**, **Group**, **Uniform Type**, **Due On or Before** (để trống = hôm nay + Remind Days Before Due), **Include** (All / chỉ New Issue / chỉ Periodic Supplement).
2. Bấm **Get Employees** → thêm mọi món đến hạn, mỗi dòng ghi sẵn **Issue Reason**:
   - **New Issue**: NV chưa từng nhận loại đó (thường là NV mới) và đã đủ *Eligible After (Days)*.
   - **Periodic Supplement**: đã nhận, không phải món cấp 1 lần, hạn cấp lại ≤ *Due On or Before*.
   Bấm nhiều lần với bộ lọc khác để gộp; dòng trùng tự bỏ qua. Dòng không tìm được size/variant được liệt kê để xử lý (thường là thiếu size trên Employee).
3. **Thêm tay** khi đồ **hỏng / mất / đổi size**: chọn NV, item (variant), SL, Issue Reason **Damaged / Lost / Size Change**.
4. Tick **Reuse Old Item** nếu cấp lại đồ cũ thu hồi (không trừ kho).
5. **Save** → kiểm tra → **Submit**.

Submit bị chặn khi: NV không còn Active / có ngày nghỉ việc · thiếu tồn (cộng dồn theo variant, trừ dòng Reuse) · dòng chưa có Issue Reason. Dòng *New Issue* cho người đã từng nhận loại đó chỉ **cảnh báo** (không chặn).

Khi Submit: tạo 1 phiếu xuất kho (Material Issue, trừ dòng Reuse), cập nhật lịch sử + hạn cấp lại từng người.

**Cấp nhầm**: Cancel phiếu → phiếu xuất kho bị hủy, tồn hoàn lại, lịch sử từng người được tính lại (kể cả lịch sử import trước khi dùng ERP được khôi phục). Sửa rồi dùng **Amend**.

## 2.6 Món cấp một lần (Mũ / Dép / Bình nước)

- Ai được cấp do **điều kiện trong Rule**; cấp **một lần** (One-Time Issue) — không xuất hiện trong cấp lại định kỳ.
- Hỏng / mất / đổi → thêm tay một dòng trên phiếu với lý do **Damaged / Lost / Size Change**.

## 2.7 Lịch sử cấp phát cũ (trước khi dùng ERP)

Đã import 10–11/07/2026 (9.207 dòng, ngày cấp từ 2010). Ngày 09/11/2026 đã tạo hồ sơ cho 130 NV Active còn thiếu và đổi tên 7 hồ sơ còn mang mã NV cũ (TIQN-2349…2355 → 2347…2353) — mọi NV Active đều có hồ sơ. Nếu cần nhập thêm: **Data Import** trên Employee Uniform Profile (Update Existing Records), cột `ID` (= mã NV), `Item (Uniform Items)` = **variant cụ thể** (vd `Áo thun nữ S`, `Mũ Đỏ - Qc`, `Dép Free Size`), `Last Issue Date`, `Last Issue Qty`, `Total Issued Qty`. Hạn kế tiếp + trạng thái tự tính.

Lần cấp ERP đầu tiên trên một dòng lịch sử cũ sẽ lưu lại giá trị cũ (ẩn, "Before ERP"); hủy phiếu sẽ khôi phục giá trị đó. **Rebuild Tracking** (System Manager, trên hồ sơ) dựng lại lịch sử từ các phiếu đã submit + giá trị trước ERP.

## 2.8 Dashboard

**/app/uniform-dashboard** (sidebar Uniform Control → Dashboard):

- **Cảnh báo dữ liệu** (khung cam): NV chưa có hồ sơ (nút **Create Profiles**), NV thiếu size áo (link danh sách Employee — áo của họ bị bỏ qua), NV chưa khai size dép (sẽ cấp Free Size).
- **3 thẻ**: Low Stock, Due Soon, Overdue (số món). Bấm Due Soon / Overdue → báo cáo **Uniform Tracking** đã lọc — **cùng số với thẻ**.
- Ô **Reissue due on/before** (mặc định hôm nay) điều khiển cả 2 bảng và nút *Create Allocation for Due*.
- **Stock Plan** (kế hoạch nhập kho, chỉ nhu cầu cấp lại): `Loại | Item | Tồn | Cần re-issue | Est. for Leavers | Tổng | Thiếu`.
  - **Cần re-issue**: theo lịch sử cấp, đếm đủ số chu kỳ đến mốc lọc.
  - **Est. for Leavers** (số âm, đỏ): ĐO từ thực tế — N tháng gần nhất (Attrition Window), số suất cấp lại đến hạn nhưng người nhận đã nghỉ trước → TB/tháng × số tháng tới mốc lọc, làm tròn lên. Bật/tắt trong Uniform Setting.
  - **Tổng** = Cần re-issue + Est.; **Thiếu** = Tổng − Tồn (đỏ khi > 0).
- **Employees Due for Issue**: mỗi NV/món — SL/chu kỳ · số chu kỳ · tổng SL.
- **2 biểu đồ**: SL cấp theo tháng và theo tổ.
- Nút: **Create Allocation for Due**, **Receive Stock**, **Assignment Preview**, **Shoe Rack Dashboard**, **Export Excel** (2 sheet theo đúng mốc lọc), **Refresh**.

## 2.9 Theo dõi & cảnh báo

- Báo cáo **Uniform Tracking**: lịch sử cấp từng NV/món, trạng thái tính theo ngày; mặc định NV đang làm (tick *Include Left Employees* để xem cả người đã nghỉ).
- **Email thứ Hai 08:30** (nếu bật): variant thiếu cho đợt cấp tới + NV sắp/đã đến hạn.

## 2.10 Dự toán nhu cầu đồng phục (Uniform Demand Forecast)

Dùng để **chuẩn bị/nhập kho trước**. Sidebar → **Uniform Demand Forecast** → New.

**Mode:**
- **New Hires** — nhu cầu cho NV sẽ tuyển: bảng **Designations to Recruit** (chức danh + số lượng). Cơ cấu cấp bậc/giới tính/tổ/bộ phận và **tỷ lệ size suy từ NV hiện tại (Active) cùng chức danh** — size và giới tính đọc từ **Employee**; size dép: NV chưa khai được tính là Free Size.
- **Re-issue** — nhu cầu cấp lại của NV hiện tại, đếm đủ số chu kỳ đến **Reissue To Date**.
- **Both** — cộng cả hai.

**Các bước:** chọn Mode, điền bảng tuyển / ngày → **Save** → nút **Forecast** → (tuỳ chọn) sửa tay cột Forecast Qty → Save → **Download Excel** (sheet Info, Recruitment Plan, Attrition, Forecast, Current Ratio).

- **Est. for Leavers** (số âm) cùng cách đo với Dashboard; **Total = Forecast Qty + Est.**; Thiếu tính theo Total.
- Chức danh `…-Trainee` chưa có ai → dùng chức danh gốc; chức danh hoàn toàn mới → dùng **Default Shirt Item** (Uniform Setting) kèm cảnh báo.
- Cảnh báo cam "Vui lòng rà soát": thiếu Grade / thiếu Rule / size chưa có variant → bổ sung rồi Forecast lại.

## 2.11 Câu hỏi thường gặp

**Nhân viên sắp nghỉ việc có cấp được không?** Không. NV có ngày nghỉ việc bị loại khỏi Get Employees và bị chặn khi submit.

**Submit báo thiếu hàng nhưng từng dòng đều ≤ tồn?** Hệ thống cộng dồn theo variant: 2 NV cùng nhận áo M nam 3 cái/người = cần 6 cái.

**Cấp nhầm thì sửa thế nào?** Cancel phiếu (tồn kho và lịch sử tự hoàn lại) → Amend.

**Đổi size cho nhân viên?** Sửa Shirt Size / Shoe Size trên Employee → thêm tay 1 dòng trên phiếu với lý do **Size Change**.

**Một người cần áo/mũ khác quy định?** Mở hồ sơ → tick **Manual Override** → chọn Áo/Mũ.
