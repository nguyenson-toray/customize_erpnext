# Overtime Registration - Tài liệu

> **Mục đích:** Doctype đăng ký tăng ca: chọn nhân viên hàng loạt theo ngày, kiểm tra thai sản và trùng ca trước khi lưu.
> **Phạm vi:** DocType tự phát triển
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-11-07

> Cập nhật 2026-07-14: redesign dialog "Get Employees" (1 dialog 2 cột + ledger giờ công),
> đổi tên hàm entry để tránh xung đột global scope, fix bug lệch ngày `toISOString()`.

## ⚠ Tắt Submit từ 2026-11-07 (đọc trước khi bật lại Workflow)

Doctype đang **không submittable**: mọi phiếu ở `docstatus = 0`, không có Submit/Cancel/Amend, muốn hủy thì xóa phiếu.
Các phần nói về submit, duyệt và amend trong tài liệu này chỉ áp dụng khi bật lại.

**Hiện trạng**

- `is_submittable` đã bỏ; quyền `submit`/`cancel`/`amend` đã gỡ ở cả DocPerm (JSON) và Custom DocPerm (DB).
- Workflow `Overtime Registration` vẫn còn trong DB, `is_active = 0`. Không lưu được bản ghi này khi doctype chưa submittable, vì có state `doc_status` 1 và 2.
- Giữ nguyên field `amended_from`, `workflow_state` và các hook `on_submit`, `on_cancel` để bật lại.
- 🔴 `Attendance Calculation Setting.include_draft_ot = 1` và đặt `read_only`, vì **tắt cờ này thì phiếu Draft không được tính, toàn bộ OT = 0** ở lần tính công sau.
  `read_only` chỉ chặn trên form; code hoặc API vẫn đổi được.
- Tính công không đổi: engine dùng `get_ot_docstatus_condition`, không đọc `is_submittable`.

**Hệ quả khi đang tắt**

- `on_submit`/`on_cancel` không chạy. Xóa phiếu đi qua `on_trash`; `recalc_attendance_on_ot_change = 0` nên công chỉ cập nhật ở lần Full Update Hours hoặc Bulk Update.
- `recalculate` thủ công ở `overtime_registration_hooks.py:223` luôn báo lỗi vì đòi `docstatus = 1`.
- Kiểm trùng giữa các phiếu ở `overtime_registration.py:491` và `:613` chỉ xét `docstatus = 1`, nên **hiện không phát hiện trùng với phiếu khác**.

**Bật lại để dùng Workflow: làm đúng thứ tự**

1. Thêm `"is_submittable": 1` vào JSON và cấp lại quyền theo bảng dưới, rồi migrate.
2. Submit các phiếu cũ cần giữ OT, khi Workflow **chưa** kích hoạt.
   Submit hàng loạt sẽ chạy `on_submit` trên từng phiếu.
3. Bỏ `read_only` của `include_draft_ot` rồi đổi về `0`.
   Giữ `1` thì phiếu Draft/Pending chưa duyệt vẫn được tính OT. Đổi về `0` trước bước 2 thì phiếu cũ mất OT.
4. Kích hoạt Workflow. Khi lưu, Frappe gán `Draft` cho phiếu `docstatus = 0` còn trống `workflow_state`.
5. Tính lại công một ngày mẫu và đối chiếu số OT trước khi mở cho toàn công ty.

Quyền cần cấp lại (trước khi tắt; các quyền khác không đổi):

| Role | DocPerm (JSON) | Custom DocPerm (DB) |
|---|---|---|
| HR Manager | submit | submit |
| Employee | submit | submit |
| Department Manager | submit, cancel | — |
| TIQN Factory Manager | submit, cancel | — |
| TIQN Staff | submit, cancel, amend | submit, cancel, amend |

## Tổng quan

Doctype đăng ký tăng ca theo lô: tổ trưởng chọn nhóm → tuần → ngày → khung giờ → danh sách
nhân viên, hệ thống sinh các dòng chi tiết vào bảng con `ot_employees`
(Overtime Registration Detail). Trước khi lưu có kiểm tra chế độ thai sản và xung đột
với OT đã duyệt (server-side).

## Dialog "Get Employees" (redesign 2026-07-14)

Nút field **Get Employees** trong form mở **một** dialog duy nhất (trước đây là 2 dialog
lồng nhau; các nút trong menu Actions đã bỏ — chỉ còn inner button **View Summary Table (Xem bảng tổng hợp)**).
Entry point: `show_ot_registration_dialog(frm)` trong `overtime_registration.js`.

### Bố cục 2 cột

```
┌───────────────────────────────────────────────────────────────┐
│  Select Employees for Overtime Registration                   │
├──────────────────────────┬────────────────────────────────────┤
│ Group    [Link, reqd]    │ Employee Selection                 │
│ Week     [3 nút tuần]    │ [🔍 tìm theo tên / mã NV]          │
│ Days     [6 ô lịch T2-T7]│ ┌────────────────────────────────┐ │
│ Begin | End Time         │ │ ☐ Select All   Showing N       │ │
│ Reason   [Small Text]    │ │ ☑ TIQN-0148  Nguyễn Văn A      │ │
│                          │ └────────────────────────────────┘ │
│                          │ Selected: 12   [chip ×][chip ×]…   │
├──────────────────────────┴────────────────────────────────────┤
│ 12 employees × 3 days × 2 h/day = 72 man-hours  [Add Selected]│
└───────────────────────────────────────────────────────────────┘
```

- **Đã đăng ký ở phiếu khác** (user chốt 13/11/2026, phương án a): chọn Nhóm/đổi Tuần → API
  `get_ot_registered_elsewhere` nạp OT của NV trong nhóm, 6 ngày của tuần, ở mọi phiếu khác chưa xoá
  (Draft + phiếu Mongo). "Đã đăng ký" = giờ chồng với khung Giờ bắt đầu–kết thúc đang chọn (giờ nối
  tiếp không tính). Ô ngày: dòng chữ "N đã ĐK" ngay trong ô (không dùng tooltip — tablet không rê
  chuột được). Danh sách NV theo các ngày đang chọn: trùng MỌI ngày → mờ + "Đã đăng ký", không tick
  được (đang tick thì tự bỏ); trùng MỘT SỐ ngày → vẫn chọn được. Mỗi NV đúng **1 dòng** (UI tablet):
  giờ đã đăng ký nằm trong nhãn — xám "Đã ĐK 17:00–19:00" (mọi ngày) / cam "Đã ĐK 2/3 ngày ·
  17:00–19:00" (một số ngày; < 576px bỏ phần "2/3 ngày"); nhiều khung giờ → "17:00–19:00 +1". Ngày +
  số phiếu chỉ ở tooltip của nhãn (chuột). **Thêm** bỏ qua mọi (NV, ngày) đã đăng ký ở phiếu khác,
  báo "Bỏ qua N dòng…". Trùng một phần cũng bỏ qua (không tự cắt giờ). Đổi ngày/giờ → tính lại ngay.
  Bước kiểm tra trước khi lưu vẫn là lưới an toàn cho nhập tay/import.
- **NV thai sản** (Maternity Leave / Pregnant + Not Allowed, `get_ot_blocked_employees`): từ 13/11/2026
  vẫn hiện trong danh sách nhưng mờ, nhãn lý do, không tick được ("Chọn tất cả" bỏ qua) — trước đó
  bị ẩn kèm dòng "Đã ẩn N nhân viên".
- **Cột trái (kế hoạch)**: Group (Link) → Week (segmented 3 tuần, kèm khoảng ngày; mặc định **Tuần +1** — `OT_DEFAULT_WEEK_OFFSET`, user chốt 12/11/2026) →
  Day tiles (ô kiểu tờ lịch: thứ + số ngày, chấm đánh dấu hôm nay, nút "Select All") →
  Begin/End Time (nằm cạnh nhau) → Reason (bắt buộc).
- **Cột phải (nhân viên)**: chọn Group là roster **tự tải ngay** (không cần dialog thứ 2);
  ô tìm kiếm lọc realtime có highlight; "Select All" áp dụng theo kết quả đang lọc;
  nhân viên đã chọn hiển thị thành chip có nút × và bộ đếm. Chọn được nhiều nhóm:
  đổi Group thì roster tải lại nhưng danh sách đã chọn (Map) giữ nguyên.
- **Ledger footer** (điểm nhấn): dòng tổng sống
  `{người} × {ngày} × {giờ/ngày} = {tổng giờ công}` cập nhật theo từng click;
  giờ sai (begin ≥ end) báo đỏ ngay tại footer.

### Hành vi quan trọng

| Hành vi | Chi tiết |
|---|---|
| Batch mode | "Add Selected" ghi rows nhưng dialog **không đóng**: giữ group + giờ + lý do, reset ngày + bỏ chọn NV; footer cộng dồn `N lô · M dòng · X giờ công` + nút "Undo last batch" (chỉ gỡ dòng của lô cuối, **không** khôi phục dòng bị thay thế); nút "Close" để đóng |
| Trùng khi Add | Trùng **NV + ngày + giờ trùng/giao nhau** với dòng đã có → confirm Yes/No: Yes = xóa dòng cũ lấy dòng mới, No = giữ dòng cũ bỏ qua dòng mới; giờ kề nhau không tính trùng; dòng sạch luôn được thêm |
| Đổi tuần | **Xóa toàn bộ ngày đã chọn** (quyết định 2026-07-14, tránh đăng ký nhầm tuần); bấm lại tuần đang chọn thì không làm gì |
| Group bị khóa | `filter_employee_by = 'custom_group'` + `request_by_group` → Group pre-fill, khóa query, tự tải roster |
| Phân quyền | `get_user_filter_value()` đọc `filter_employee_by` (custom field, không nằm trong JSON doctype); sai nhóm → chặn kèm alert |
| Ngày của dòng con | Format local `ot_format_ymd()` — **không dùng** `toISOString()` (UTC làm lệch ngày trước 07:00 giờ VN) |
| Dòng con | Set đủ `employee`, `employee_name`, `group` (từ `custom_group`), `date`, `begin_time`, `end_time`, `reason` |
| State | `frm._ot_dialog_state` (Map nhân viên, Set ngày, weekOffset…); reset mỗi lần mở dialog |
| Giới hạn | Roster tải tối đa 500 nhân viên/nhóm (limit_page_length) |

### Kỹ thuật UI

- CSS inject 1 lần qua `<style id="ot-reg-dialog-css">`, scope class `.ot-reg-modal`.
- Màu lấy từ theme vars của desk (tự động light/dark qua `html[data-theme="dark"]`);
  1 màu nhấn hổ phách `#b45309` (light) / `#f5b83d` (dark) cho trạng thái chọn + số tổng.
- Số liệu (ngày, giờ, đếm, ledger) dùng font mono (`--ot-mono`).
- A11y: day tiles là `<button>` có `aria-pressed`, ledger `aria-live="polite"`,
  focus-visible outline, transition tôn trọng `prefers-reduced-motion`.
- **UI English-first** + dịch qua `translations/vi.csv`
  (mục "# Overtime Registration dialog (redesign 2026-07-14)").

### ⚠ Global scope của doctype JS

Doctype JS được eval vào **global scope** của desk. `overtime_request.js` có hàm
`show_employee_selection_dialog` riêng, nên hàm của Overtime Registration được đổi tên thành
`show_ot_registration_dialog` (2026-07-14) để 2 form không ghi đè lẫn nhau khi mở trong cùng
phiên. **Quy tắc**: hàm global mới trong file này phải có prefix `ot_` hoặc tên riêng biệt.

## View Summary Table (Xem bảng tổng hợp)

Nút **In phiếu** (`.ot-inline-print`, ngay sau "Xem bảng tổng hợp", user thêm 12/11/2026): `frm.print_doc()` →
trang in chuẩn với mẫu mặc định (Overtime Registration V2). Ẩn khi phiếu mới chưa lưu; phiếu có sửa
chưa lưu → báo "Vui lòng lưu phiếu trước khi in."

Inner button **View Summary Table (Xem bảng tổng hợp)** mở bảng chỉ-đọc từ bảng con hiện tại (kể cả dòng chưa lưu):

- Cột: `No.` (sticky, 40px) | `Employee` (sticky) | `Group` | `Note` | các ngày (thứ + dd/MM) | `Total (h)`.
- Ô = khung giờ `HH:MM-HH:MM` (nhiều dòng cùng ngày thì xếp chồng, hover hiện lý do); ô trống = "–".
- Tổng 3 chiều: theo NV (cột cuối), theo ngày (dòng cuối, sticky bottom), tổng cả phiếu.
- **Note**: icon NV được **hết ca sớm** (giảm giờ) vào ít nhất 1 ngày OT trong bảng — 🤰 Mang thai,
  🤱 Nghỉ thai sản, 👶 Con nhỏ; tooltip "… — Hết ca sớm N giờ". API `get_ot_maternity_benefits`
  (cùng quy tắc `pick_maternity_phase` với hộp thoại kiểm tra trước khi lưu; mang thai không tick
  giảm giờ → không icon). Tải async; lỗi → cột trống, không báo lỗi.

## Luồng lưu (before_save)

1. `before_save`: nếu `validate` đã báo lỗi (`frappe.validated === false`) → dừng, KHÔNG mở
   hộp thoại kiểm tra. Nếu chưa check → chặn save, gọi `check_all_before_save(frm)`.
   Cờ `pre_save_check_done` dùng 1 lần: vào `before_save` là đặt lại false, nên server báo lỗi
   thì lần lưu sau vẫn kiểm tra lại.
2. Gọi song song 2 API server (gửi `idx` = vị trí trong danh sách gửi đi, KHÔNG phải idx của
   lưới — kết quả được gắn lại vào đúng đối tượng dòng `_row`, vì Frappe đánh số lại idx khi
   xoá dòng; lỗi lệch dòng OTR-261112-0002 ngày 12/11/2026):
   - `check_employees_with_maternity_benefits` — NV được hết ca sớm (mang thai có tick giảm
     giờ / nghỉ thai sản / con nhỏ) mà dòng OT bắt đầu đúng giờ hết ca bình thường.
   - `check_overtime_conflicts` — dòng trùng giờ (cùng NV, cùng ngày) với phiếu KHÁC chưa xoá
     (`docstatus < 2`, kể cả Draft; user chốt 12/11/2026 phương án A). Chỉ là kiểm tra mềm trong
     hộp thoại (ô "Xóa các dòng bị trùng khỏi phiếu này" tick sẵn); `validate()` của server KHÔNG
     chặn vì job Mongo 18:00 insert qua validate và dữ liệu cũ đã có dòng trùng giữa phiếu.
3. Có kết quả → hộp thoại **Kiểm tra trước khi lưu**, tối đa 2 bước, phiếu chỉ lưu 1 lần
   (`show_ot_precheck_dialog`; user chốt 12/11/2026):
   - **Bước 1 – trùng phiếu khác** (`show_ot_conflict_step`, chỉ khi có): mỗi dòng 1 thẻ, phân loại
     bằng `ot_conflict_plan` (lấy phần giờ CHƯA nằm trong các dòng đã đăng ký):
     *Trùng hoàn toàn* / *Đã đăng ký đủ giờ* → mặc định **Xóa dòng này**; *Trùng một phần* →
     mặc định **Sửa thành** phần còn trống (nhiều mảnh thì giữ mảnh dài nhất). Luôn có **Giữ nguyên**.
     Nút **Tiếp tục** (còn bước 2) hoặc **Lưu**.
     **Hơn 10 dòng trùng** (`OT_CONFLICT_LIST_MAX`, user chốt 13/11/2026) → không liệt kê thẻ mà hiện
     thông báo tóm tắt (`show_ot_conflict_summary`): số dòng theo loại, bảng "Trùng với" phiếu nào /
     số dòng, số dòng không trùng sẽ giữ. 2 nút: **Xóa N dòng trùng & tiếp tục/lưu** và **Xóa hết
     bảng (N dòng)** (đỏ, có hỏi xác nhận, không lưu). Nếu mọi dòng đều trùng → chỉ còn nút Xóa hết
     bảng (bảng con bắt buộc nên không lưu được phiếu rỗng) + nhắc "có thể phiếu này đã đăng ký rồi".
   - **Bước 2 – lùi giờ thai sản** (`show_ot_maternity_step`): chỉ các dòng còn lại sau bước 1 và
     vẫn bắt đầu đúng giờ hết ca bình thường. 2 thẻ có dải thời gian minh hoạ: **Chỉ lùi giờ bắt
     đầu** (mặc định, 17:00–19:00 → 16:00–19:00) / **Lùi cả giờ bắt đầu và giờ kết thúc**
     (→ 16:00–18:00). Không có "giữ nguyên": NV này luôn hết ca sớm. Bảng Dòng | Nhân viên |
     "Đang nhập" → "Sau khi lưu".
   - Mỗi bước có nút **Quay lại sửa** (đóng, không lưu).
4. Không có gì → save thẳng. Lỗi server → vẫn cho save (không chặn người dùng).
5. Dòng trống được xoá **đồng bộ** trong `validate` (`frappe.model.clear_doc`), không dùng
   `grid_row.remove()` (chạy trễ, đánh số lại idx sau khi bước 2 đã đọc).

## Các hàm xác thực client (event `validate`)

| Hàm | Mục đích |
|---|---|
| `remove_empty_overtime_rows` | Tự xóa dòng không có employee (silent khi validate) |
| `validate_required_fields` | Bắt buộc employee, date, begin_time, end_time từng dòng |
| `validate_time_order` | `begin_time < end_time` |
| `validate_duplicate_rows` | Cùng NV + ngày không được chồng chéo giờ (dùng `times_overlap`, O(n²)) |
| `validate_single_post_shift_entry` | Cùng NV + ngày chỉ nên 1 dòng OT liên tục; nhiều dòng → cảnh báo gộp |
| `calculate_totals_and_apply_reason` | Đếm NV riêng biệt (`total_employees`), tổng giờ (`total_hours`); đồng bộ `reason_general` ↔ reason dòng con |
| `update_registered_groups` | Gom các `group` riêng biệt của dòng con vào `registered_groups` |

### times_overlap(from1, to1, from2, to2)

```javascript
// Chồng chéo khi: start1 < end2 && start2 < end1
// Khoảng kề nhau (16:00-18:00 và 18:00-20:00) KHÔNG tính là chồng chéo
```

| Khoảng 1 | Khoảng 2 | Chồng chéo |
|----------|----------|------------|
| 16:00-18:00 | 18:00-20:00 | ❌ kề nhau |
| 16:00-18:00 | 17:00-19:00 | ✔ |
| 16:00-18:00 | 14:00-16:00 | ❌ kề nhau |
| 16:00-18:00 | 17:00-17:30 | ✔ chứa nhau |

## Cấu trúc dữ liệu

### Overtime Registration (parent)
> Tối giản cho mobile (2026-09-24): form chỉ còn hiện **Group**, **Approver**, **Remarks of
> Approver** (ẩn khi tạo mới), nút **Add Employees** và bảng `ot_employees`.

- **ĐÃ XOÁ (2026-09-24):** `requested_by`, `requested_by_full_name`, `reason_general`, `registered_groups`
  (cột DB vẫn còn, Frappe không drop). Người đăng ký = Employee của `owner`
  (`get_requester_employee()`); bản in "Prepared by" và email cũng đọc theo `owner`.
  🔴 Khoá chống trùng của đồng bộ MongoDB giờ là `Overtime Registration Detail.reason`
  ("Sync from MongoDB: Request number: …") — sửa ở `api/biometric_resync.py`, tool
  `apps/biometric-attendance-sync-tool/05.*` (REST filter bảng con) và `bulk_import_overtime.py`.
  4.455/4.455 phiếu sync cũ đã có request number ở dòng con.
- `approver`: read-only, server tự điền ở mỗi lần save khi còn draft =
  `get_employee_leave_approver()` của HRMS (Employee.leave_approver, không có thì Leave
  Approver đầu tiên của Department).
- `approver_full_name`, `total_employees`, `total_hours`, `request_date`: ẩn, server tự tính
  (dùng trong email duyệt). Print format V2 tự tính SL NV / Số giờ từ bảng con.
- `request_by_group`: server điền từ custom_group của Employee người tạo (không còn fetch_from).
- ⚠ Jinja (print format / notification): dùng `frappe.get_fullname`, KHÔNG có `frappe.utils.get_fullname`
  (= None → "NoneType is not callable", mail không gửi, chỉ có Error Log).
- `request_by_group`, `filter_employee_by` (custom field): khóa/lọc phạm vi chọn nhân viên

### Workflow "Overtime Registration" — 1 cấp duyệt (2026-09-24)
Workflow chỉ nằm trong DB (không có trong fixtures/repo). 4 transition:

| Từ | Action | Tới | Allowed | Condition |
|---|---|---|---|---|
| Draft (0) | Submit | Pending (0) | All | — |
| Pending | Approve | Approved (1) | All | `doc.approver == frappe.session.user` |
| Pending | Reject | Rejected (1) | All | `doc.approver == frappe.session.user` |
| Approved | Cancel | Cancelled (2) | Department Manager | — (cần quyền cancel theo role; share không cấp cancel) |

- Cấp 2 sẽ thêm sau: chèn state giữa Pending → Approved.
- `validate_approver_for_workflow()`: chặn chuyển sang Pending khi `approver` rỗng.
- `share_with_approver()` (on_update): khi Pending thì share read/write/submit cho người duyệt, vì người duyệt
  có thể chỉ có role Employee (if_owner), không share thì không thấy phiếu và không duyệt được.
- 🔴 **Rejected = docstatus 1** → mọi truy vấn "OT được tính" phải loại `workflow_state = 'Rejected'`:
  `get_ot_docstatus_condition()` (engine chấm công), `overrides/attendance/attendance.py`,
  `api/daily_attendance_metrics.py`, 2 query kiểm tra trùng trong `overtime_registration.py`, 3 report OT.
  Query mới đọc OT thì dùng `get_ot_docstatus_condition()`, đừng viết `docstatus = 1` trần.
- Email của chính Workflow: vì allowed = `All` (role ảo, không có dòng Has Role) và điều kiện được tính
  theo user đang thao tác, nên workflow của Frappe **không gửi mail cho ai**.
- Mail cho người duyệt đi qua Notification **"Overtime Registration Pending Approval"** (standard, thư mục
  `customize_erpnext/notification/`): Value Change `workflow_state` → Pending, gửi cho field `approver`.
  Draft/Reject/Approve không gửi. Test 2026-09-24: 1 mail đến son.nt (Leave Approver của Office + Production).
  ⚠ Khai thêm Leave Approver cho phòng nào là người đó bắt đầu nhận mail thật.

### Phân quyền xem (2026-09-28)
- Quyền thật nằm ở **Custom DocPerm** (DB, không có trong fixtures) — file JSON của DocType KHÔNG có hiệu lực.
- `TIQN Staff` và `Employee`: `if_owner = 1` → chỉ thấy phiếu mình tạo + phiếu được share (người duyệt).
  Các role khác (HR Manager, TIQN Manager, Department Manager, TIQN Factory Manager…) thấy tất cả.
  Frappe **cộng dồn** role: user có TIQN Staff + HR/TIQN Manager vẫn thấy tất cả (user chọn "role quản lý thắng").
- Report SQL thô không đi qua phân quyền → report "Overtime Registration" (chi tiết từng dòng) dùng
  `get_owner_only_condition()` trong `overtime_registration.py`. 2 report tổng hợp (Quantity, By Time Slot)
  chỉ ra số theo nhóm/khung giờ, không lọc. Report chi tiết mới nào cũng phải gọi hàm này.

### Hướng dẫn (Form Tour) — 2026-09-24
- Form Tour **"Overtime Registration"** (standard, file `customize_erpnext/form_tour/overtime_registration/`),
  7 bước tiếng Việt cho công nhân: Thêm người tăng ca (dialog) → Kiểm tra lại → Thêm 1 người lẻ (nút
  **Thêm hàng** của bảng, chọn được người nhóm khác) → Người duyệt → Xem bảng tổng hợp → Lưu phiếu → Gửi duyệt.
  Nội dung tiếng Việt nằm trong dữ liệu tour, không nằm trong JS.
- Workflow **tắt** (`frappe.model.has_workflow` = false) → `drop_ot_tour_approval_steps()` bỏ bước Người duyệt
  và Gửi duyệt, đánh số lại "Bước N:" ⇒ còn 5 bước. File JSON luôn giữ đủ 7 bước.
- Sửa file JSON xong phải nạp vào DB (tour đọc từ DB): đổi `modified` rồi
  `bench --site <site> execute frappe.modules.import_file.import_file_by_path --kwargs '{"path":"<đường dẫn tuyệt đối>","force":1}'`
  (hoặc `bench migrate`).
- Thanh **Help** màu cam ở đầu form (chỉ khi phiếu Draft/mới). Không dùng inner button vì trên mobile
  Frappe dồn inner button vào menu "⋯". Tour tự chạy 1 lần/trình duyệt ở phiếu mới đầu tiên
  (localStorage `ot_registration_tour_seen`).
- Các bước Thêm 1 người lẻ, Xem bảng tổng hợp, Lưu, Gửi đơn trỏ vào nút ngoài field: step có
  `element_selector` (`.grid-add-row`, `.ot-inline-pivot`, toolbar; fieldname giả vì Form Tour không phải
  UI tour thì bắt buộc có fieldname); `apply_ot_tour_element_selectors()` đổi element, `a || b` = phần
  tử đầu tiên đang hiện.
- Dialog đánh số ①–⑦ (Nhóm, Tuần, Ngày, Giờ, Lý do, Nhân viên, nút Add Selected) khớp danh sách ở bước 1
  của tour — đổi thứ tự trong dialog thì sửa cả tour.
- View Summary Table (Xem bảng tổng hợp) mobile: ẩn cột No./Group, mã + tên xuống 2 dòng, giờ bắt đầu/kết thúc xếp chồng; hàng tổng
  không dùng colspan (cột bị ẩn sẽ làm lệch).
- **Thiết bị mục tiêu = TABLET** (2026-09-28). CSS chia 2 lớp: `(max-width:767px), (pointer:coarse)` = vùng chạm
  ≥44px, input 16px, footer dialog dính đáy (áp cả tablet); `(max-width:767px)` = full màn hình, xếp 1 cột, pivot ẩn cột.
  Dialog mở với `no_focus` trên màn cảm ứng, nếu không bàn phím ảo sẽ bật lên che dialog.
  ⚠ Frappe ẩn inner toolbar ở màn md (768–991, tablet dọc) và xs (`page.html`: `custom-actions hidden-xs hidden-md`)
  → nút View Summary Table (Xem bảng tổng hợp) CHỈ nằm cạnh "Add Employees" (`.ot-inline-pivot`, mọi màn hình); đã bỏ inner button trên toolbar.
- Hàng gộp (2026-09-28): `arrange_ot_dialog_rows()` gom DOM thành hàng flex: Nhóm + Tuần, Giờ bắt đầu + Giờ kết thúc
  (không dùng Section Break lồng vì sẽ phá bố cục 2 cột). ≤991px (tablet dọc) xếp 2 cột chồng lên nhau để mỗi hàng
  đủ rộng; ≥992px giữ 2 cột. CSS `inline-block 50%` cũ bị rớt dòng do khoảng trắng giữa phần tử → đã bỏ.
- Mobile (≤767px): dialog full màn hình, footer dính đáy, vùng bấm ≥44px, font input 16px (tránh iOS zoom).

### Overtime Registration Detail (child `ot_employees`)
- `employee`, `employee_name`, `group`, `date`, `begin_time`, `end_time`, `reason`

## Validate server-side (Python, method `validate()` khi save/submit)

> Gộp từ `overtime_registration_validate.MD` (đã xóa 2026-07-16) và đối chiếu lại code.

| Hàm | Quy tắc |
|---|---|
| `validate_time_order` | begin < end từng dòng |
| `validate_ot_outside_working_hours` | OT phải nằm **ngoài giờ làm việc** của ca: trước ca / trong giờ nghỉ trưa / sau ca (NV thai sản: mốc sau ca = shift_end − 1h); ca không cho phép OT (Shift 1/2) → chặn |
| `validate_duplicate_employees` | Trùng/overlap giờ cùng NV + ngày trong form (bản server của check client) |
| `validate_conflicting_ot_requests` | So với OT đã **submit** ở phiếu khác: (a) không được overlap; (b) phải **liên tục** — bắt đầu ngay sau OT cũ kết thúc, kết thúc ngay trước OT cũ bắt đầu, hoặc bắt đầu đúng giờ tan ca nếu là OT đầu tiên; lỗi kèm link phiếu xung đột |
| `validate_ot_continuity_same_day` | Nhiều dòng cùng NV cùng ngày trong form phải liên tục, dòng đầu bắt đầu đúng giờ tan ca |

Helpers: `validate_ot_continuity_with_shift`, `validate_ot_entries_continuity` (strict_mode).

Cấu hình ca tham chiếu:

| Ca | Giờ | Nghỉ trưa | Cho phép OT |
|----|-----|-----------|-------------|
| Day | 08:00–17:00 | 12:00–13:00 | Có |
| Canteen | 07:00–16:00 | 11:00–12:00 | Có |
| Shift 1 | 06:00–14:00 | – | Không |
| Shift 2 | 14:00–22:00 | – | Không |

Ví dụ liên tục với OT đã submit `16:00-18:00`: mới `18:00-20:00` ✓; `19:00-20:00` ✗ (hở giờ);
chưa có OT nào → `17:00-19:00` ✓ (bắt đầu đúng giờ tan ca Day).

## Kiến trúc hybrid

- **JavaScript (client)**: phản hồi tức thì — validate trong form, tính tổng, dialog chọn nhân viên.
- **Python (server)**: kiểm tra cần quyền đọc DB đầy đủ — xung đột với phiếu đã submit,
  chế độ thai sản, validate khi submit.
- Thông báo lỗi đa ngôn ngữ (`__()`), kèm số dòng và link tới document xung đột.
