# Uniform Control — Đặc tả kỹ thuật & Triển khai (ERPNext / HRMS v16)

> Tài liệu này là **prompt triển khai cho Claude Code**. Mục tiêu: xây dựng tính năng quản lý tồn kho & cấp phát đồng phục cho nhân viên, tích hợp module Stock và HRMS, theo đúng các DocType/API/workflow mô tả bên dưới.
> Lưu ý về các yêu cầu chung cho customize erpnext được chỉ ra ở /home/frappe/frappe-bench/.claude/skills/erpnext-frappe

---

## 1. Bối cảnh & ràng buộc

| Mục | Giá trị |
|---|---|
| Nền tảng | ERPNext + HRMS **version 16** |
| App đích | `customize_erpnext` (đã tồn tại — KHÔNG tạo app mới) |
| Module đích | `Uniform Control` (đã tồn tại — mọi DocType mới gán vào module này) |
| Ngôn ngữ field | `fieldname` tiếng Anh, `label` tiếng anh, translatable, update bản dịch vào /home/frappe/frappe-bench/apps/customize_erpnext/customize_erpnext/translations/vi.csv |
| Người dùng chính | HR (không phải nhân viên kho) → thao tác phải **đơn giản**, ẩn sự phức tạp của Stock |
| Quyền truy cập | Chỉ `System Manager` (Administrator) và role mới `Uniform Manager` (gán cho HR) |

### Nguyên tắc tận dụng Stock có sẵn (giữ đơn giản)
- Dùng **Item + Item Variant + Item Attribute** cho danh mục đồng phục.
- Dùng **Stock Entry** chỉ với 2 loại tối giản:
  - **Material Receipt** (nhập kho): chỉ `to_warehouse = Uniform`, **không** yêu cầu kho nguồn.
  - **Material Issue** (xuất/cấp phát): chỉ `from_warehouse = Uniform`, **không** yêu cầu kho đích.
- Dùng **Stock Balance report** sẵn có cho số tồn; HR không cần mở report kho gốc — số liệu được bọc lại qua Dashboard/API.
- Dùng **Reorder Level native** của Item để đặt ngưỡng cảnh báo nhập (không tự code ngưỡng).
- KHÔNG dùng Material Transfer, Purchase Receipt, Delivery Note, Material Request cho luồng này.

---

## 2. Master data (Dev admin sẽ khởi tạo thủ công)

### 2.1 Item Attribute (tạo nếu chưa có)
| Attribute | Giá trị |
|---|---|
| `Uniform Size` | S, M, L, XL, XXL |
| `Uniform Gender` | Nam, Nữ |
| `Hat Type` | Văn phòng, Leader, Sub-leader, Công nhân may, Công nhân cắt |
| `Shoe Size` | 35, 36, 37, 38, 39, 40, 41, 42, 43, 44 *(dải cấu hình được)* |

### 2.2 Item Group
- Nhóm cha: `Uniform`. Mọi item đồng phục thuộc nhóm này (phục vụ lọc/báo cáo).

### 2.3 Item Template (has_variants = 1) & Variants
| Template (item_code) | Tên | Attributes | Ghi chú |
|---|---|---|---|
| `UNI-AOTHUN` | Áo thun | Uniform Size × Uniform Gender | sinh variant theo tổ hợp |
| `UNI-AOSOMI` | Áo sơ mi | Uniform Size × Uniform Gender | |
| `UNI-MU` | Mũ | Hat Type | không có size |
| `UNI-DEP` | Dép | Shoe Size | location quản lý ở Employee Profile, không phải attribute |
| `UNI-BINH` | Bình nước | (không) | **item đơn, không variant** |

Cấu hình chung cho mọi item/variant: `is_stock_item = 1`, `maintain_stock = 1`, không bật serial/batch. Đặt `valuation_rate` khi nhập kho để phục vụ báo cáo chi phí.

### 2.4 Warehouse
- Tạo kho leaf riêng: `Uniform - {company_abbr}`. Toàn bộ tồn đồng phục nằm tại đây.

### 2.5 Reorder Level
- Trên mỗi variant, thêm dòng **Item Reorder** với `warehouse = Uniform`, `warehouse_reorder_level`, `warehouse_reorder_qty`. Weekly check đọc ngưỡng này để cảnh báo (không bật auto Material Request).

---

## 3. Custom Fields trên DocType có sẵn

### 3.1 Employee (HRMS)
| fieldname | label | type | options / ghi chú |
|---|---|---|---|
| `uniform_section` | Đồng phục | Section Break | tab/section mới (đã tạo)|
| `uniform_profile` | Hồ sơ đồng phục | Link | `Employee Uniform Profile`; dùng để auto-điền item variant đúng khi cấp phát |

> Tự động tạo `Employee Uniform Profile` khi tạo Employee mới (xem §7.1). `uniform_profile` được set link ngược lại.

### 3.2 Stock Entry Detail (tùy chọn, để truy vết)
| fieldname | label | type | options |
|---|---|---|---|
| `uniform_employee` | Nhân viên | Link | `Employee`, read-only — ghi khi sinh từ Allocation |
| `uniform_allocation` | Chứng từ cấp phát | Link | `Uniform Allocation`, read-only |

---

## 4. DocType mới (module: Uniform Control)

### 4.1 `Uniform Setting` — Single
Cấu hình hệ thống + bảng quy định cấp phát.

| fieldname | label | type | options / ghi chú |
|---|---|---|---|
| `uniform_warehouse` | Kho đồng phục | Link | `Warehouse` (mặc định kho Uniform) |
| `reminder_days_before` | Số ngày cảnh báo trước hạn | Int | mặc định 30 |
| `enable_weekly_alert` | Bật cảnh báo hàng tuần | Check | mặc định 1 |
| `alert_recipients` | Người nhận email | Small Text | danh sách email, phân tách dấu phẩy |
| `auto_create_onboarding_allocation` | Tự sinh cấp phát khi onboarding | Check | mặc định 1 |
| `low_stock_use_reorder` | Dùng Reorder Level làm ngưỡng | Check | mặc định 1 |
| `policies` | Quy định cấp phát | Table | → `Uniform Policy` |
| `notes` | Ghi chú | Text Editor | |

### 4.2 `Uniform Policy` — Child Table (của Uniform Setting)
Mỗi dòng = quy định cho 1 loại đồng phục áp dụng cho 1 nhóm đối tượng.

| fieldname | label | type | options / ghi chú |
|---|---|---|---|
| `item_template` | Loại đồng phục | Link | `Item` (chỉ template has_variants, hoặc UNI-BINH) |
| `applies_to` | Áp dụng cho | Select | `Tất cả` / `Phòng ban` / `Chức danh` / `Giới tính` |
| `department` | Phòng ban | Link | `Department`, hiện khi applies_to=Phòng ban |
| `group` | Nhóm | Link | `custom_group`, hiện khi applies_to=Phòng ban |
| `designation` | Chức danh | Link | `Designation`, hiện khi applies_to=Chức danh |
| `gender` | Giới tính | Select | `Nam` / `Nữ`, hiện khi applies_to=Giới tính |
| `first_issue_qty` | SL cấp lần đầu | Int | |
| `eligible_after_days` | Đủ ĐK sau (ngày làm việc) | Int | tính từ date_of_joining |
| `reissue_cycle_months` | Chu kỳ cấp bổ sung (tháng) | Int | 0 = không cấp bổ sung |
| `reissue_qty` | SL mỗi lần bổ sung | Int | |
| `is_active` | Kích hoạt | Check | mặc định 1 |

### 4.3 `Employee Uniform Profile` — 1 record / nhân viên
Lưu thông số đồng phục để auto-điền + theo dõi hạn cấp.

| fieldname | label | type | options / ghi chú |
|---|---|---|---|
| `employee` | Nhân viên | Link | `Employee`, **unique**, bắt buộc |
| `employee_name` | Tên | Data | fetch từ employee, read-only |
| `department` | Phòng ban | Link | fetch, read-only |
| `designation` | Chức danh | Link | fetch, read-only |
| `employment_status` | Trạng thái | Select | fetch `Employee.status` (Active/Left...), read-only |
| `relieving_date` | Ngày nghỉ | Date | fetch, read-only — dùng cho điều kiện cấp |
| `uniform_gender` | Giới tính đồng phục | Select | `Nam` / `Nữ` |
| `shirt_size` | Size áo | Select | S/M/L/XL/XXL |
| `hat_type` | Loại mũ | Select | theo Hat Type |
| `shoe_size` | Size dép | Select | theo Shoe Size |
| `shoe_rack_location` | Vị trí để dép | Data | mã rack, ví dụ `0001`, `J1`, `J2` |
| `has_water_bottle` | Cấp bình nước | Check | |
| `items` | Theo dõi cấp phát | Table | → `Employee Uniform Item` |
| `notes` | Ghi chú | Small Text | |

### 4.4 `Employee Uniform Item` — Child Table (của Employee Uniform Profile)
Mỗi dòng = tình trạng cấp phát theo 1 loại đồng phục.

| fieldname | label | type | options / ghi chú |
|---|---|---|---|
| `item_template` | Loại đồng phục | Link | `Item` |
| `last_issue_date` | Ngày cấp gần nhất | Date | |
| `last_issue_qty` | SL lần gần nhất | Int | |
| `total_issued_qty` | Tổng đã cấp | Int | |
| `next_due_date` | Hạn cấp kế tiếp | Date | = last_issue_date + reissue_cycle_months |
| `status` | Trạng thái | Select | `Chưa cấp` / `Còn hạn` / `Sắp đến hạn` / `Quá hạn` |

### 4.5 `Uniform Allocation` — Transaction (Submittable)
Chứng từ cấp phát **theo lô** (nhiều nhân viên / 1 chứng từ). Submit → sinh Stock Entry Material Issue.

| fieldname | label | type | options / ghi chú |
|---|---|---|---|
| `naming_series` | Số chứng từ | Select | `UNI-ALLOC-.YYYY.-` |
| `posting_date` | Ngày cấp | Date | mặc định hôm nay |
| `allocation_type` | Loại cấp phát | Select | `Cấp mới` / `Cấp bổ sung` / `Thay thế` |
| `company` | Công ty | Link | `Company` |
| `set_warehouse` | Kho xuất | Link | `Warehouse`, mặc định kho Uniform |
| `uniform_type_filter` | Lọc loại đồng phục | Link | `Item` template, optional (dùng khi build danh sách) |
| `department_filter` | Lọc phòng ban | Link | `Department`, optional |
| `items` | Chi tiết cấp phát | Table | → `Uniform Allocation Item` |
| `total_qty` | Tổng số lượng | Int | tính tự động, read-only |
| `stock_entry` | Phiếu xuất kho | Link | `Stock Entry`, read-only (set sau submit) |
| `status` | Trạng thái | Select | `Draft` / `Submitted` / `Cancelled` (đồng bộ docstatus) |
| `amended_from` | Sửa từ | Link | `Uniform Allocation` |

### 4.6 `Uniform Allocation Item` — Child Table (của Uniform Allocation)
| fieldname | label | type | options / ghi chú |
|---|---|---|---|
| `employee` | Nhân viên | Link | `Employee` |
| `employee_name` | Tên | Data | fetch, read-only |
| `department` | Phòng ban | Link | fetch, read-only |
| `item_code` | Item (variant) | Link | `Item` — variant cụ thể (đã auto theo size/giới tính) |
| `item_name` | Tên item | Data | fetch, read-only |
| `qty` | Số lượng | Int | |
| `available_qty` | Tồn hiện có | Float | read-only, fetch tồn kho Uniform của item_code |
| `issue_reason` | Lý do cấp | Select | `Cấp mới` / `Bổ sung định kỳ` / `Hỏng` / `Đổi size` |
| `shoe_rack_location` | Vị trí để dép | Data | fetch từ profile khi item là Dép |
| `remark` | Ghi chú | Data | |

---

## 5. Business rules (BẮT BUỘC)

1. **Chỉ cấp cho nhân viên Active.** Điều kiện đủ: `Employee.status == "Active"` **và** `relieving_date` rỗng. Nếu nhân viên đã có `relieving_date` (sắp nghỉ) → coi như **Left**, KHÔNG đưa vào danh sách cấp phát.
2. **Lọc đủ điều kiện theo `allocation_type`:**
   - `Cấp mới`: nhân viên chưa từng được cấp loại đó **và** `số ngày làm việc ≥ eligible_after_days`.
   - `Cấp bổ sung`: đã qua `reissue_cycle_months` kể từ `last_issue_date` của loại đó (tức `today ≥ next_due_date`).
   - `Thay thế`: chọn thủ công (lý do `Hỏng`/`Đổi size`).
3. **Auto-điền variant** từ `Employee Uniform Profile`: ghép `item_template` với `shirt_size`/`uniform_gender` (áo), `hat_type` (mũ), `shoe_size` (dép); bình nước dùng item đơn. Nếu profile thiếu thông số cần thiết → cảnh báo dòng đó, không auto qty.
4. **Kiểm tra tồn kho** trước submit: với mỗi dòng `qty ≤ available_qty` của item tại kho Uniform. Nếu thiếu → chặn submit và liệt kê dòng thiếu (HR đi nhập kho trước).
5. **Khi Submit Allocation:**
   - Tạo **một** Stock Entry `Material Issue` (gom theo `item_code`, cộng dồn qty) từ kho Uniform; ghi `uniform_allocation` (+`uniform_employee` nếu tách dòng) vào Stock Entry Detail.
   - Link `stock_entry` ngược về Allocation.
   - Cập nhật `Employee Uniform Profile.items` của từng nhân viên: `last_issue_date`, `last_issue_qty`, cộng `total_issued_qty`, tính lại `next_due_date` và `status`.
6. **Khi Cancel Allocation:** cancel Stock Entry liên quan; hoàn lại số liệu theo dõi trong profile.
7. **Nhập kho (Material Receipt):** form rút gọn cho HR (chọn item variant + qty [+ valuation_rate]); tạo Stock Entry `Material Receipt` vào kho Uniform. KHÔNG yêu cầu kho nguồn.

---

## 6. Workflow (mô tả sơ đồ)

**4 vùng:** Thiết lập → Kho (hub) → Pipeline cấp phát (7 bước) → Giám sát & quyền.

### 6.1 Luồng nhập kho
```
HR mở "Nhập kho đồng phục" → chọn item variant + qty (+ valuation)
   → tạo Stock Entry Material Receipt (chỉ kho đích = Uniform)
   → tồn kho Uniform tăng
```

### 6.2 Luồng cấp phát theo lô (pipeline chính)
```
1. Chọn tiêu chí        : allocation_type + uniform_type_filter + department_filter
2. Lọc nhân viên đủ ĐK   : Active & không relieving; mới/bổ sung theo chu kỳ (§5.1, §5.2)
3. Tự điền item & SL     : ghép variant theo profile; qty theo policy (§5.3)
4. Kiểm tra tồn kho      : qty ≤ available_qty tại kho Uniform (§5.4)
5. Submit Allocation     : 1 chứng từ cho nhiều nhân viên
6. Tạo Material Issue     : xuất kho Uniform, không kho đích (§5.5)
7. Cập nhật hồ sơ & lịch sử: last_issue_date, next_due_date; Allocation + Stock Entry = lịch sử
```

### 6.3 Quan hệ tồn kho (đường nét đứt trên sơ đồ)
- `Uniform Setting` → bước 2 (quy định lọc).
- Kho Uniform → bước 4 (đọc tồn).
- Bước 6 → Kho Uniform (ghi giảm tồn).

### 6.4 Dashboard (HR)
Workspace/Page hiển thị: số tồn mỗi variant; cảnh báo nhân viên sắp/đã đến hạn (vàng/đỏ); nút **Cấp phát**, **Nhập kho**, **Lịch sử**; biểu đồ tiêu thụ theo tháng/phòng ban. Mọi số liệu lấy qua API (§9), HR không mở report kho gốc.

---

## 7. Tích hợp & tự động hóa

### 7.1 Onboarding (HRMS)
- Hook `Employee` (after_insert / validate): tự tạo `Employee Uniform Profile` (link 2 chiều với `uniform_profile`).
- Khi nhân viên Active và đủ `eligible_after_days`: nếu `auto_create_onboarding_allocation` bật → sinh **draft** `Uniform Allocation` loại `Cấp mới`, auto-điền dòng theo policy `first_issue_qty` + size trong profile. HR review rồi submit.

### 7.2 Weekly check (Frappe Scheduler — `scheduler_events` weekly)
Hàm quét và gửi email tới `alert_recipients`:
- **Tồn thấp:** variant có `actual_qty ≤ warehouse_reorder_level` (kho Uniform).
- **Đến hạn:** `Employee Uniform Item.next_due_date` nằm trong `reminder_days_before` ngày tới, nhân viên Active.
- Email gồm 2 bảng tóm tắt + link Dashboard.

### 7.3 Theo dõi chi phí
- `valuation_rate` đặt khi Material Receipt; Material Issue tiêu hao theo valuation.
- Báo cáo (Query Report + API): chi phí đồng phục theo **nhân viên / phòng ban / kỳ**, dựa trên dòng Allocation × valuation tại thời điểm xuất.

---

## 8. Phân quyền
- Tạo role `Uniform Manager`, gán cho HR.
- Mọi DocType Uniform (`Uniform Setting`, `Uniform Allocation`, `Employee Uniform Profile`) + form Nhập kho: chỉ `System Manager` và `Uniform Manager` có quyền read/write/create/submit.
- Mọi API whitelisted kiểm tra `frappe.has_permission` / role tương ứng trước khi xử lý.

---

## 9. Roadmap API (whitelisted)

> Quy ước: API phục vụ **Excel Power Query** dùng suffix `_excel` (theo chuẩn report-api của dự án); API phục vụ frontend JS không có suffix. Tất cả nhận `filters` dạng dict và kiểm tra quyền.

### Phase A — Read / báo cáo (ưu tiên 1)
| API | Mục đích | Tham số chính |
|---|---|---|
| `get_uniform_stock_excel` | Tồn theo variant + reorder + cờ tồn thấp | company, item_template |
| `get_due_employees_excel` | NV đến hạn cấp mới / bổ sung | allocation_type, department, uniform_type |
| `get_allocation_history_excel` | Lịch sử cấp phát | from_date, to_date, employee, department |
| `get_uniform_cost_excel` | Chi phí đồng phục | group_by (employee/department/period), from_date, to_date |

### Phase B — Hành động cấp phát (frontend, ưu tiên 1)
| API | Mục đích | Tham số chính |
|---|---|---|
| `get_eligible_employees` | Danh sách NV đủ ĐK + đề xuất qty + variant + available_qty | allocation_type, uniform_type, department |
| `create_allocation` | Tạo draft Uniform Allocation từ payload | header + items[] |
| `submit_allocation` | Submit + tạo Material Issue | name |
| `receive_stock` | Nhập kho rút gọn (Material Receipt) | items[] (item_code, qty, valuation_rate) |

### Phase C — Dashboard & tiện ích (ưu tiên 2)
| API | Mục đích |
|---|---|
| `get_dashboard_summary` | Số liệu tổng hợp cho Dashboard (tồn, cảnh báo, đếm theo loại) |
| `get_employee_uniform_profile` | Lấy hồ sơ + lịch sử của 1 nhân viên |

---

## 10. Lộ trình triển khai

| Phase | Hạng mục |
|---|---|
| **1 — Core** | Item Attributes/Templates/Variants + kho Uniform + `Uniform Setting`/`Uniform Policy` + `Employee Uniform Profile`/`Employee Uniform Item` + custom field Employee + role & quyền |
| **2 — Giao dịch** | `Uniform Allocation`/`Uniform Allocation Item` + logic lọc đủ ĐK (§5) + form Nhập kho + sinh Stock Entry + cập nhật profile/lịch sử |
| **3 — Tự động & báo cáo** | API Phase A/B + Dashboard + Reorder Level + Weekly check email + tích hợp Onboarding + báo cáo chi phí |
| **4 — Hoàn thiện** | API Phase C, tinh chỉnh UX cho HR, tài liệu hướng dẫn |

---

## 11. Ngoài phạm vi (KHÔNG triển khai)
- Tích hợp Offboarding / thu hồi / khấu trừ đồng phục khi nghỉ việc.
- QR / Barcode quét khi cấp phát.
- Employee Self-Service / portal nhân viên tự yêu cầu.
- Workflow phê duyệt nhiều cấp cho Allocation (Draft → chờ duyệt → ...). Allocation chỉ Draft → Submit.
- Tính năng đổi size gộp (thu hồi + cấp mới trong 1 thao tác) — xử lý thủ công bằng Material Receipt + Allocation riêng nếu cần.

---

## 12. Checklist nghiệm thu
- [ ] Tạo được variant đầy đủ cho áo/mũ/dép; bình nước là item đơn.
- [ ] Nhập kho bằng Material Receipt (không kho nguồn) làm tăng tồn Uniform.
- [ ] Lọc cấp phát loại Active, loại trừ NV có relieving_date.
- [ ] Auto-điền đúng variant theo profile; dép kèm `shoe_rack_location`.
- [ ] Chặn submit khi qty > tồn.
- [ ] Submit sinh đúng 1 Material Issue (không kho đích) + cập nhật profile/next_due_date.
- [ ] Cancel hoàn tác đúng tồn & theo dõi.
- [ ] Onboarding sinh draft allocation cấp mới.
- [ ] Weekly email báo tồn thấp + NV đến hạn.
- [ ] Chỉ Admin & Uniform Manager truy cập được.
- [ ] API `_excel` gọi được từ Power Query.