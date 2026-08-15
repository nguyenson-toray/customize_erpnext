# Attendance Request — bổ sung giờ check in/out

Doctype `Attendance Request` của HRMS ở TIQN phục vụ **hai** mục đích. Chế độ được suy ra
từ field `reason`, không có field "Request Type" riêng.

| `reason` | Chế độ | Hành vi |
|---|---|---|
| `Work From Home`, `On Duty` | HRMS gốc | `super()` — không đụng gì |
| `Forget Check In/Out`, `Machine Error`, `First Working Day`, `Other` | **Bổ sung giờ công** | Tạo `Employee Checkin` + chạy lại engine tính công |

4 lý do mới **trùng khít** options của `Employee Checkin.custom_reason_for_manual_check_in`
nên copy thẳng sang checkin, không cần bảng ánh xạ. Sửa danh sách ở **3 nơi cùng lúc**:

- `SUPPLEMENT_REASONS` trong `attendance_request.py`
- `SUPPLEMENT_REASONS` trong `public/js/custom_scripts/attendance_request.js`
- `REASON_OPTIONS` + `SUPPLEMENT_DEPENDS_ON` trong `patches/setup_attendance_request_supplement.py`

## Luồng

```
validate   → sync_checkin_rows()        1 dòng con / 1 ngày trong from_date..to_date
           → refresh_existing_times()   đổ giờ in/out của Attendance đã có vào cột read-only
           → validate_supplement_rows() thứ tự giờ, trùng checkin, lý do Other cần explanation
           → validate_supplement_overlap()

on_submit  → create_supplement_checkins()   Employee Checkin mang custom_attendance_request
           → recalculate_attendance()       _core_process_attendance_logic_optimized

on_cancel  → delete_supplement_checkins()   xoá checkin + chuẩn hoá lại log_type của phần còn lại
           → recalculate_attendance()       Attendance quay về trạng thái trước khi bù
```

## Phân quyền — `frappe.get_all` KHÔNG kiểm tra quyền

Ba API whitelisted đều nhận tham số tự do (mã nhân viên, khoảng ngày, tên phiếu) nên phải tự
chốt chặn. `frappe.get_all` **bỏ qua hoàn toàn phân quyền** (`frappe/__init__.py`: *"Will **not**
check for permissions"*), khác `frappe.get_list`.

| API | Chốt chặn | Lý do |
|---|---|---|
| `get_existing_attendance_info` | `Attendance Request` + `Attendance` read, **và** query chạy qua `get_list` | Nhận mã nhân viên bất kỳ. Dùng `get_all` thì người có role `Employee` đọc được giờ công của đồng nghiệp. `get_list` áp cả role lẫn User Permission nên nhân viên chỉ thấy của mình, HR vẫn thấy tất cả |
| `get_incomplete_candidates`, `bulk_create_requests` | `Attendance` **write** | Quét toàn công ty, trả tên/tổ/chức vụ/giờ công của người khác. Chỉ HR User / HR Manager / System Manager có `Attendance` write — role `Employee` chỉ có read nên bị chặn |
| `download_confirmation_forms` | lọc lại `names` qua `get_list` | Nhận danh sách tên phiếu bất kỳ; lọc lại để nhân viên chỉ in được phiếu của mình |

⚠ `frappe.get_list` gọi từ Python **không** bị giới hạn 20 dòng (`limit_page_length=None` → không
sinh `LIMIT`) — đã đo: cùng trả 2295 bản ghi như `get_all`. Đừng thêm `limit_page_length` "cho chắc".

## Ba điểm dễ sai — đọc trước khi sửa

1. **Ba validate của HRMS bị bỏ qua có chủ đích** trong chế độ bổ sung. Đặc biệt
   `validate_no_attendance_to_create()`: ngày cần bù gần như luôn đã có Attendance nên nó
   throw *"Attendance status unchanged"* và sẽ **chặn 100% phiếu bổ sung**. Xem comment
   trong `validate()`.

2. **Gọi thẳng `_core_process_attendance_logic_optimized`**, KHÔNG dùng
   `_recalculate_attendance()` của checkin override — wrapper đó bị chặn bởi `is_peak_time()`
   và bởi setting `recalc_attendance_on_checkin_change` (mặc định **OFF**), nên bấm Submit
   xong ngày công sẽ không đổi mà chẳng báo lỗi gì.

3. **Cảnh báo "Attendance Already Complete" phải xét KHOẢNG CÁCH giờ, không phải "cả hai cột đã
   có giá trị".** Quẹt đúp trên máy (ca thật đo được: TIQN-1331 ngày 14/08 quẹt 19:03:41 rồi
   19:03:43) làm engine ghi cả `in_time` lẫn `out_time`, mà cả hai đều format ra "19:03". Ngày đó
   `working_hours = 0.0`, status `Absent`, note `No check-IN` — tức là vẫn thiếu giờ vào. Dùng
   `_has_real_span()`: hai dấu cách nhau dưới `DUPLICATE_TOLERANCE_MINUTES` là **một** lần quẹt,
   không phải một ngày công.

4. **Khi Cancel phải CLEAR `created_checkin_in/out` TRƯỚC khi xoá checkin.** Hai field đó là Link
   trỏ tới Employee Checkin, nên `frappe.delete_doc("Employee Checkin", …)` sẽ ném
   *"Cannot delete or cancel because Employee Checkin X is linked with Attendance Request Y"*
   nếu child row còn giữ tên. Clear sau khi xoá là quá muộn.
   ⚠ Đọc kỹ thông báo lỗi: `doc` trong câu đó là **Employee Checkin** chứ không phải phiếu — lỗi
   bật ra ở bước xoá checkin, không phải ở bước cancel. `on_cancel` **có** chạy trước
   `check_no_back_links_exist()` (`document.py:run_post_save_methods`), nên đừng đi tìm ở đó.

5. **`created_checkin_in` / `created_checkin_out` phải giữ `no_copy: 1`.** Khi Amend một phiếu
   đã cancel, child rows được copy sang phiếu mới; thiếu `no_copy` thì phiếu mới trỏ vào
   checkin đã bị xoá.

Engine có `frappe.db.commit()` bên trong ⇒ **không test submit bằng script rollback**, nó sẽ
ghi thật vào dữ liệu chấm công.

## Tạo hàng loạt từ Attendance Request List

Nút **"Bulk Create from Missing Check-ins"** trên list → dialog chọn khoảng ngày (mặc định **hôm
qua**) → hệ thống tìm người thiếu checkin, **đề xuất giờ**, HR sửa tay → tạo **DRAFT** một phiếu/
nhân viên → tải **1 file PDF** form ký, mỗi `custom_group` một trang A4.

```
bulk_create.get_incomplete_candidates()   tìm + đề xuất giờ + gắn cờ cảnh báo
bulk_create.bulk_create_requests()        tạo draft, 1 phiếu / nhân viên / nhiều ngày
confirmation_form.download_confirmation_forms()   PDF gom theo custom_group
```

In lại bất cứ lúc nào: tick vài bản ghi trên list → nút **"Print Confirmation Forms"** (nằm cạnh
nút Bulk Create, không giấu trong menu Actions). Dùng chung `download_confirmation_forms` với nút
trong dialog, nên chỉ có một đường dựng PDF duy nhất.

### Quy tắc đề xuất giờ

Xác định thiếu đầu nào bằng **mốc giữa ca**: lần quẹt nằm ở nửa đầu ca → đó là giờ VÀO ⇒ thiếu RA;
nửa sau ca → đó là giờ RA ⇒ thiếu VÀO. Giờ đề xuất = đầu ca / cuối ca, và nếu có Overtime
Registration **cùng phía** thì lấy giờ OT thay thế (OT sau ca → dời giờ RA; OT trước ca → dời giờ VÀO).

> Đã đối chiếu với 5 ngày HR tự nhập tay hôm 14/08/2026 — **khớp 5/5**. Đừng đổi quy tắc này mà
> không đo lại tương tự.

### 5 bẫy đã trả giá

1. **`get_incomplete_checkins` KHÔNG loại người đã bổ sung tay.** Nó chỉ đếm checkin có
   `device_id IS NOT NULL`. Ngày 14/08 có 9 case thì **5 case đã được HR nhập tay** vẫn nằm trong
   danh sách. Cách xử lý: `_missing_side()` chạy lại **đúng 3 quy tắc của hàm đó** nhưng trên
   **toàn bộ** checkin (`_get_all_checkin_times`, kể cả nhập tay). Nếu các lần quẹt đã phủ hết ca
   → `missing_side = None`, `resolved = True`, **không đề xuất giờ**, dòng bỏ tick + tô xanh
   ("Complete"). Ngày 14/08: 9 dòng → chỉ còn **4 dòng thật sự thiếu**.
   Hai cờ `already_manual` / `already_requested` giữ lại để hiển thị, cũng bỏ tick sẵn.

2. **`tabShift Name` thiếu ca.** `get_incomplete_checkins` đọc giờ ca từ bảng này, mà nó chỉ có 4
   dòng (Canteen, Day, Shift 1, Shift 2) — không có `Canteen 6:30 - 15:30` đang dùng thật ⇒ trả
   `begin_time=None, end_time=None`. Phần đề xuất giờ **phải đọc `Shift Type`** (doctype thật, đủ 5
   ca). Chỉ dùng `get_incomplete_checkins` để **tìm** case, không lấy giờ của nó.

3. **Bản in phải sắp xếp giờ, không map thẳng cột.** Khi ngày chỉ có 1 lần quẹt, engine luôn lưu
   nó vào `Attendance.in_time` **kể cả khi đó thực chất là giờ RA**. In `existing_in_time` vào cột
   "Giờ vào" sẽ làm mất giờ thật duy nhất của nhân viên ngay trên tờ họ phải ký. `_in_out_cells()`
   gộp mọi giờ đã biết rồi lấy sớm nhất → "Giờ vào", muộn nhất → "Giờ ra".

4. **Phải append child row TRƯỚC `insert()`.** `validate()` throw *"Nothing to Supplement"* khi bảng
   con rỗng, nên không thể insert rồi mới điền giờ.

5. **Phải set `doc.shift` tường minh.** HRMS `validate_shifts()` throw khi khoảng ngày trải qua hai
   Shift Assignment khác nhau — chuyện rất dễ xảy ra khi HR chọn nhiều ngày.

### Form in

`confirmation_form.html` dựng theo form giấy `2. De nghi xac nhan cong.pdf`: logo ở góc trên trái,
tiêu đề song ngữ, bảng 8 cột (STT · MSNV · Họ tên · Chức vụ · Ngày · Giờ vào · Giờ ra · Ghi chú —
in **đúng số dòng thực tế**, không chừa dòng trống), 3 ô tick lý do, đoạn ghi chú hạn 3 ngày /
trước ngày 26, 5 ô ký. Giờ **được bổ sung** in đậm + gạch chân để người ký thấy ngay.

**4 chi tiết trình bày đã xử lý, đừng phá:**

- **Font Times New Roman.** Server không cài font này; stack rơi xuống **Liberation Serif** (cùng
  metric, đủ dấu tiếng Việt). PDF xuất ra vẫn khai tên `TimesNewRomanPSMT` — đã kiểm bằng cách đọc
  bảng font trong file.
- **Dấu tick `✓` (U+2713) phải mượn DejaVu Sans** (class `.acr-tick`) — Liberation Serif không có
  glyph này, để font serif thì ra ô vuông. Form giấy gốc ghi "đánh dấu P" là vì bản Word dùng
  Wingdings; ở đây in thẳng dấu tick thật.
- **Logo nhúng base64 trong CSS** (`_logo_base64()`, cache `lru_cache`). wkhtmltopdf chạy ngoài
  request nên URL `/assets/...` không với tới được và `file://` bị chặn. Khai trong stylesheet để
  không lặp lại chuỗi base64 ở từng trang.
- **`.role` trong ô ký phải có `height` cố định (13mm).** Ô "Xác nhận bởi quản lý trực tiếp, tổ
  trưởng" xuống 4 dòng, không ghim chiều cao thì dòng `…./..../…..` của nó bị đẩy thấp hơn 4 ô kia.
  Đã kiểm bằng toạ độ: cả 5 dòng ngày nằm đúng cùng một mức y.

Ánh xạ lý do sang ô tick giấy — `PAPER_REASON_INDEX`: `Forget Check In/Out`→1,
`Machine Error`→2 (giấy ghi rõ "cần xác nhận bởi IT"), `First Working Day`/`Other`→3.
Một tờ có nhiều lý do khác nhau thì tick ô 3.

### Lưu bản scan đã ký

Custom Field **`custom_signed_form`** (fieldtype `Attach`, nằm ngay dưới bảng giờ, cùng
`depends_on` với section bổ sung) để HR đính kèm ảnh/PDF giấy đã có đủ chữ ký — khép kín vòng
`tạo draft → in → ký → scan đính kèm → submit`.

- **`allow_on_submit: 1`**: chữ ký thường thu được *sau* khi phiếu đã submit, không bật cờ này thì
  không đính kèm được nữa. An toàn vì **cả HRMS lẫn override đều không định nghĩa
  `on_update_after_submit`** — đã kiểm tra, nên bật cờ không kích hoạt hook nào.
- **`no_copy: 1`**: Amend một phiếu đã cancel không được kéo theo giấy ký của phiếu cũ.
- Hiện **không bắt buộc** phải có file mới cho submit. Muốn siết quy trình thì thêm điều kiện ở
  `validate()`, nhưng đó là quyết định nghiệp vụ — hỏi HR trước.

## TODO — đưa chức năng lên HRMS PWA mobile (chưa làm, khảo sát 2026-08-15)

**Tự chạy sẵn, không cần làm gì:** `hrms.api.get_doctype_fields` trả về `frappe.get_meta().fields`
nên Custom Field của mình **tự có mặt** trên mobile — `custom_checkin_details` (fieldtype `Table`
nằm trong `SUPPORTED_FIELD_TYPES`) và 4 lý do mới trong Select `reason`. Controller override dùng
chung nên validate/submit/cancel trên PWA chạy đúng logic đã viết.

**3 rào cản phải xử lý (đều nằm trong `apps/hrms/frontend/src`):**

1. **Table field bị nuốt im lặng.** `components/FormField.vue` có
   `showField = props.fieldtype !== "Table" && !props.hidden` → bảng không render, không báo lỗi.
   Muốn hiện phải truyền qua **named slot** + tự viết component. Tiền lệ duy nhất: Expense Claim
   (`ExpensesTable.vue` / `ExpenseTaxesTable.vue` / `ExpenseAdvancesTable.vue`).
2. **Slot cho Table chỉ tồn tại trong nhánh `v-if="tabbedView"` của `FormView.vue`.** Nhánh `v-else`
   chỉ render `FormField`, không có slot. `tabbedView` là prop **mặc định `false`** và mảng `tabs`
   phải viết tay ở view cha ⇒ phải chuyển `views/attendance/AttendanceRequestForm.vue` sang dạng tab.
3. **Fieldtype `Time` không có renderer.** `Time` có trong `SUPPORTED_FIELD_TYPES` nhưng
   `FormField.vue` chỉ có nhánh cho Select/Link/Text Editor/Small Text/Check/Data/Currency/Int/Float/
   Section Break/Date/Datetime — **không có `Time`**. `new_in_time`/`new_out_time` sẽ chỉ hiện label,
   không nhập được. Né bằng cách tự render `<input type="time">` trong component của mình.

**Khối lượng:** component mới `AttendanceRequestCheckinTable.vue` (~150–200 dòng, mẫu theo
`ExpensesTable.vue`) · sửa `AttendanceRequestForm.vue` (bật tab + slot + gọi
`get_existing_attendance_info`) · `bench build --app hrms`.

**⚠ Cái giá:** tất cả đều sửa trực tiếp trong `apps/hrms` (app này đã có 2 file sửa tay) ⇒ conflict
mỗi lần update hrms. Vue app đã compile nên **không có cách nào inject từ app custom** — không hook,
không slot cho bên thứ ba. Hướng thay thế: trang mobile riêng trong `customize_erpnext/www/`
(kiểu `/employee-photos`), dùng lại API hiện có, không đụng hrms — đổi lại nằm ngoài menu PWA.

**⚠ Quyền:** role `Employee` hiện **không có submit** trên Attendance Request ⇒ trên mobile nhân
viên chỉ tạo được draft, HR submit trên Desk. Mở quyền submit cho nhân viên = họ tự sửa ngày công
của chính mình, chỉ nên làm kèm workflow duyệt.

## File liên quan

| File | Vai trò |
|---|---|
| `attendance_request.py` | controller override (`override_doctype_class`) |
| `bulk_create.py` | tìm case thiếu checkin + đề xuất giờ + tạo hàng loạt draft |
| `confirmation_form.py` + `.html` | dựng PDF form ký, gom theo `custom_group` |
| `2. De nghi xac nhan cong.pdf` | form giấy gốc đang dùng — nguồn của bố cục bản in |
| `../../public/js/custom_scripts/attendance_request_list.js` | nút + dialog trên list view |
| `test_regression.py` | 40 assert chạy tay, có rollback — chạy lại sau mỗi lần sửa |

## Chạy hồi quy

```bash
cd ~/frappe-bench/sites
../env/bin/python -c "import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect(); \
    exec(open('../apps/customize_erpnext/customize_erpnext/overrides/attendance_request/test_regression.py').read())"
```

Phủ 7 nhóm: API đọc · dò ca thiếu công · tạo hàng loạt · 5 nhánh validate bị chặn · chế độ HRMS
gốc không bị đụng · dọn dẹp khi cancel · dựng PDF. Kết thúc bằng `frappe.db.rollback()`.

⚠ **Không** test được `on_submit`/`on_cancel` đầy đủ bằng rollback: engine tính công có
`frappe.db.commit()` bên trong (5 chỗ trong `shift_type_optimized.py`) nên nó ghi thật vào bảng
Attendance. Nhánh dọn dẹp được test riêng qua `delete_supplement_checkins()` (không gọi engine).

⚠ Một số assert bám số liệu thật ngày 2026-08-14. Dữ liệu ngày đó đổi thì chỉnh hằng số trong
test, **đừng** sửa code nghiệp vụ cho khớp test.
| `../../public/js/custom_scripts/attendance_request.js` | ẩn/hiện field theo reason, sinh dòng ngày, bảng dashboard "Existing Attendance & Check-ins" |
| `../../customize_erpnext/doctype/attendance_request_checkin_detail/` | child table |
| `../../patches/setup_attendance_request_supplement.py` | Custom Field + Property Setter `reason.options` |
| `../../01_docs/attendance_request_supplement_plan.md` | thiết kế đầy đủ + checklist test |
