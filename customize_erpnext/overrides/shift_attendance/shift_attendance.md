# Override `Shift Attendance` + mã nghỉ phép trên bảng công

> **Mục đích:** Cho report Shift Attendance của HRMS chạy logic bản Customize, và điền mã nghỉ phép vào sheet Timesheet khi xuất Excel.
> **Phạm vi:** Override HRMS/ERPNext
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-20

Hai việc trong một module:

1. Report `Shift Attendance` của HRMS chạy **100% logic** của `Shift Attendance Customize`
2. Sheet **Timesheet** trong Export Excel điền **mã nghỉ phép** (`P`, `KL`, `O/2`…) vào ngày nghỉ

---

## 1. Override report

`Shift Attendance Customize` được viết lại cho đúng thực tế TIQN và **đang chạy đúng**, nên nó là
nguồn duy nhất. Module này **không chép logic** — chỉ trỏ report của HRMS sang đúng hàm đó.

| Mặt | Cách làm |
|---|---|
| **Python** | `__init__.py` gán đè `hrms…shift_attendance.execute` → `execute` của bản Customize. Frappe phân giải script report bằng `frappe.get_attr("<module>.execute")` **lúc chạy** nên gán đè thuộc tính module là đủ |
| **JS** (filter + 3 nút) | `overrides/report_js.py` đọc **nguyên file** `.js` của bản Customize, đổi đúng **một** chuỗi tên report, rồi phục vụ cho report HRMS |

Chép JS bằng cách thay chuỗi thay vì chép tay 446 dòng — hai bản không thể lệch nhau về sau.

> ⚠ Tên report chỉ xuất hiện **một lần** trong file JS (dòng 4, `frappe.query_reports[...]`).
> Dòng 224 là đường dẫn python
> `…report.shift_attendance_customize.shift_attendance_customize.export_attendance_excel` —
> **KHÔNG được đổi**, vì nút Export Excel phải gọi đúng module đó.
> Nếu sau này thêm chỗ hardcode tên report, phải cập nhật `_cloned_script()`.

**`Shift Attendance Customize` không bị sửa một dòng nào.** Cả hai report cùng tồn tại, cùng chạy
một logic; giữ bản Customize để đối chiếu khi nghi ngờ. Sidebar giữ nguyên cả hai mục.

Đã đối chiếu trên 2.763 dòng dữ liệu thật: **columns, data và report_summary giống hệt nhau**.

---

## 2. Mã nghỉ phép trên sheet Timesheet

Nguồn quy tắc: [`QUY_DINH_NGHI_PHEP_2025.md`](../leave_application/QUY_DINH_NGHI_PHEP_2025.md)
mục 3 (phụ lục quy chế TB-TIQN/2025-0018). Bảng nằm ở
[`timesheet_leave.py`](timesheet_leave.py) — **sửa quy chế thì sửa cả hai chỗ**.

### Ngày công theo mã

| Ngày công | Mã |
|---:|---|
| **1** | `P` `P/2` `MC` `HS` `HL` `HL/2` |
| **0,5** | `O/2` `CO/2` `OP/2` `COP/2` |
| **0,4** | `OL/2` `COL/2` |
| **0** | `KL` `NB` `TS` `DS` `O` `CO` `OCO/2` `OK/2` `COK/2` |
| `giờ làm / 8` | không có mã, hoặc mã lạ chưa có trong bảng |

### Hai chỗ dễ hiểu sai

**① `P/2` (phép năm nửa ngày) vẫn tính công TRỌN 1 NGÀY.** Nửa còn lại đi làm nên đủ lương.
Quy chế mục 3.1 ghi rõ, và đây là quy tắc bị code hiểu sai nhiều nhất.

**② `KL` có hai nghĩa, phân biệt bằng số giờ làm:**

| Trường hợp | Ô hiển thị | Ngày công |
|---|---|---|
| Nghỉ không lương trọn ngày (0 giờ) | `KL` | 0 |
| Đi trễ / về sớm (mục 3.3, mã `<1`) — **có** giờ làm | **số giờ** | `giờ làm / 8` |

### Phạm vi: CHỈ sheet Timesheet

Sheet **Detail** và **Summary** giữ nguyên hoàn toàn cách tính `working_hours / 8`.

> 🔴 **Hệ quả đã được chấp nhận:** cột `Total` của Timesheet sẽ **khác** tổng của Summary.
> Một nhân viên nghỉ 3 ngày `P`: Timesheet +3 ngày công (đúng quy chế), Summary +0 (0 giờ làm).
>
> Đã cân nhắc đổi tiêu đề cột thành `Total (quy chế)` để HR khỏi nhầm, nhưng **không làm**:
> `standard_export.py` là bản sao trung thành từng ô của app Flutter (`timesheetFunctions.dart`),
> đổi tiêu đề là phá tính tương thích đó. Khi nào cần thống nhất, hãy áp quy chế cho **cả ba**
> sheet thay vì đổi nhãn.

---

## 3. Chặn `working_hours` theo đơn nghỉ phép

Quy tắc TIQN chốt 18/08/2026. Code: [`../shift_type/leave_hour_cap.py`](../shift_type/leave_hour_cap.py).
Chi tiết đầy đủ ở [`OPTIMIZATION_GUIDE.md`](../shift_type/OPTIMIZATION_GUIDE.md); đây là phần
liên quan tới report và Excel.

**Ba field, đừng nhầm:**

| Field | Nghĩa |
|---|---|
| `standard_working_hours` | độ dài danh nghĩa của **ca** (8,0 ở mọi bản ghi). Không đụng |
| `custom_actual_working_hours` | giờ **thực tế** theo check in/out — **không bao giờ** bị chặn |
| `working_hours` | **cơ sở chốt lương** — bị chặn |

| Loại đơn | `working_hours` |
|---|---|
| `KL` | giữ nguyên giờ thực tế |
| Đơn TRỌN ngày (≠ KL) | **0** |
| Đơn NỬA ngày | **min(thực tế, 4)** |
| Hai đơn nửa ngày cùng ngày | **0** |

Nghỉ đã duyệt cũng **không bị đánh** `late_entry` / `early_exit` (trừ `KL`) — quy chế mục 3.3 trừ
100.000đ mỗi lần, gắn nhầm là mất tiền thật.

### Hiện ra ở đâu trong Excel

| Sheet | Nội dung |
|---|---|
| **Detail** — cột `Actual (hour)` | giờ thực tế, cạnh `Working (hour)` đã bị chặn |
| **Detail** — cột `Note Checkin` | `Nghỉ nửa ngày nhưng làm 8.00h - chặn còn 4h ; → XEM HUỶ ĐƠN NGHỈ` |
| **Important Note** | `[Nghỉ phép + đi làm] 15/06/2026 TIQN-0940 — đơn P/2 nhưng làm 8.00h (tính công 4.00h · 07:02–19:05) → xem huỷ HR-LAP-2026-11647` |

### Sheet Important Note

Định dạng **Excel Table** (`TableImportantNote`) như các sheet khác, **8 cột**, sắp xếp tăng dần
theo **Type → Date → Employee**:

| Cột | Nội dung |
|---|---|
| `Type` | `[Nghỉ phép + đi làm]` · `[Ra 16-17h]` · `[Resigned + Att]` |
| `Info` | `01/04/2026 · TIQN-1643 Đào Thị Hiền · 11:26–17:05` |
| `Working Hour` · `Working Hour Actual` | số thật, `number_format 0.00` — lọc/sắp xếp được |
| `Leave Application Abbreviation` | `P/2`, `KL`… lấy từ Attendance |
| `Attendance` · `Leave Application` | tên bản ghi để tra thẳng |
| `Note` | ngữ cảnh riêng của từng loại; `[Nghỉ phép + đi làm]` để **trống** — các cột số và mã đơn đã nói đủ, HR tự quyết xử lý |

Cả ba loại anomaly đều điền đủ cột.

> ⚠ `_add_excel_table` neo `ref` từ **A1**, nên tiêu đề cột phải ở **dòng 1** — không đặt được
> dòng "Important Note — generated …" phía trên như bản cũ. Thời điểm xuất đã có trong **tên
> file** nên không mất thông tin.

> ⚠ Muốn sắp xếp được thì anomaly phải mang `date` / `employee` thành **trường riêng**; nhét vào
> chuỗi mô tả thì không sort theo Type/Date/Employee được.

### Độ rộng cột ngày

`DATE_COL_WIDTH_PIVOT = 6.6` \(Timesheet · Overtime\) và `DATE_COL_WIDTH_SHIFT = 8.8` \(Shift\) —
nới **+10%** so với bản gốc 6 và 8. Cột `Date` / `Joining Date` / `Resign Date` cũng 10 → 11.

### `Only employees who resigned in this period` — số dòng mỗi sheet khác nhau là ĐÚNG

Bộ lọc áp cho **mọi sheet**, đã kiểm qua đường thật \(dialog → file `.xlsx`\): không sheet nào lẫn
người ngoài danh sách. Nhưng số lượng khác nhau vì quy tắc riêng của từng sheet:

| Sheet | Ví dụ kỳ 06/2026 | Vì sao |
|---|---:|---|
| Detail · Summary · Timesheet | 57/59 | 2 người nghỉ đúng ngày đầu kỳ không có ngày chấm công nào \(`relieving_date` là ngày làm cuối\) |
| Overtime | 22 | `skip_zero_rows=True` — bỏ người không có tăng ca |
| Shift | 3 | chỉ liệt kê người thuộc ca xoay `Shift 1`/`Shift 2` |

User đã chốt **giữ nguyên** hành vi này \(20/08/2026\) — đừng "sửa" thành ép đủ danh sách ở mọi sheet.

> Anomaly là tuple **2 hoặc 3 phần tử**: `(type, detail)` hoặc `(type, detail, dict cột phụ)`.
> Giữ dạng 2 phần tử để anomaly mới thêm không bắt buộc phải có cột phụ.

**Báo MỌI ca bị chặn giờ, không dùng ngưỡng giờ.** Ngưỡng cũ \(nửa ngày ≥7h\) giấu mất 298/312 ca —
`attendance/0ad5308fc1` nghỉ `P/2` làm 6,33h đã bị chặn, đã có note, nhưng không lên Important Note.
Lọc nhiễu chuyển sang **ngưỡng phút** trong dialog thay vì ngưỡng giờ trong code.

### Option của dialog Export Excel

| Option | Mặc định | Tác dụng |
|---|---|---|
| Only employees who resigned in this period | tắt | chỉ NV có `relieving_date` **trong kỳ** — dùng khi chốt lương người thôi việc |
| Report leave-but-worked from \(minutes\) | **15** | dưới ngưỡng coi là nhiễu làm tròn \(4,01h vs 4,00h = 36 giây\); `0` = báo tất |
| 6 ô chọn sheet | tất cả bật | xuất bớt sheet cho nhẹ file |

⚠ `only_resigned` **THAY THẾ** điều kiện trạng thái chứ không AND thêm — điều kiện gốc dùng
`relieving_date > from_date` nên AND thêm sẽ rơi mất người nghỉ đúng ngày đầu kỳ \(đo tháng 6:
57/59\).

⚠ Bỏ sheet "Important Note" thì phải `wb.remove(wb.active)`, nếu không file có tab rỗng tên "Sheet".

> ⚠ Cột `Actual (hour)` được **CHÈN ở vị trí 13** nên mọi cột sau đó của sheet Detail dịch phải 1.
> Test đọc theo chỉ số cột phải cập nhật theo.

> 🔴 `standard_export._build_notes()` **chỉ dịch những chuỗi tiếng Anh đã khai sẵn**. Thêm note
> mới ở engine mà quên khai ở đó thì note **biến mất khỏi cột Note Checkin mà không báo lỗi**.
> Đã cắn một lần 18/08/2026.

### Cố ý KHÔNG làm

Đã cân nhắc thêm ô Check `Leave but worked` và cột `Actual Working Hours` **lên report** —
**bỏ cả hai**: note trong Excel đủ cho quy trình HR. `test_leave_hour_cap.py` có assert ngược
(`report KHÔNG có cột Actual Working Hours`) để lần sau ai thêm lại thì test đỏ ngay.

## File liên quan

```
overrides/shift_attendance/
├── __init__.py                          # monkey patch execute (giữ bản gốc ở _tiqn_original_execute)
├── timesheet_leave.py                   # bảng mục 3 quy chế: mã → ngày công, mã → ô hiển thị
├── test_shift_attendance_override.py    # 48 assert, 7 phần
└── shift_attendance.md

overrides/report_js.py                   # dùng chung: nối/clone JS của report (xem mục 1)
overrides/shift_type/leave_hour_cap.py   # quy tắc chặn giờ (mục 3)
overrides/shift_type/test_leave_hour_cap.py   # 62 assert, 8 phần
```

Sửa trong report được bảo vệ — `report/shift_attendance_customize/standard_export.py`, toàn bộ
logic mới nằm ở `timesheet_leave.py` và `leave_hour_cap.py`:

1. `build_export_rows` — thêm `leave_abbr` + `actual_hours` vào row dict
2. `build_standard_workbook` — dựng thêm `ts_display` song song `ts_pivot`
3. `_add_pivot_sheet` — thêm tham số **tuỳ chọn** `display_values`; sheet Overtime không truyền
   nên hành vi giữ nguyên tuyệt đối
4. `add_detail_sheet` — chèn cột `Actual (hour)` ở vị trí 13
5. `_build_notes` — khai thêm 2 chuỗi note của quy tắc chặn giờ
6. anomaly `[Nghỉ phép + đi làm]` cho sheet Important Note

Nạp qua `overrides/__init__.py`. **Sửa Python phải `bench restart`.**

---

## Kiểm thử

`test_shift_attendance_override.py` — **48 assert / 0 lỗi**, 7 phần:

```
1  bảng mục 3: 21 mã → ngày công
2  P/2 vẫn tính công trọn ngày
3  KL hai nghĩa tuỳ số giờ
4  ngày không có mã: giữ hành vi cũ
5  hai report trả kết quả giống hệt (2.763 dòng thật)
6  workbook: 6 sheet, mã in ra đúng bảng, Total khớp tổng ngày công
7  Overtime không lẫn chữ · Detail vẫn tính giờ/8 · cột Actual (hour) đúng vị trí
```

`../shift_type/test_leave_hour_cap.py` — **62 assert / 0 lỗi**, 8 phần: bảng quy tắc · note ·
bỏ cờ trễ/sớm · `apply_to_attendance()` · bản ghi thật + **OT bất biến** + idempotent ·
note hiện trong Excel · report.

> ⚠ Test dùng khoảng **01–10/06/2026**, không dùng tháng 8: **tháng 8/2026 có 0 mã** vì 183 đơn
> nghỉ tháng đó còn ở trạng thái **draft** nên chưa ghi abbreviation lên Attendance. Đây là trạng
> thái dữ liệu, không phải lỗi code — submit đơn là mã hiện ra.

Phân bố mã thật theo tháng (kỳ 2026): T12 208 · T1 1.240 · T2 796 · T3 1.134 · T4 1.225 ·
T5 1.167 · T6 2.061 · T7 1.065 · **T8 0**.

---

## Bẫy khi sửa

1. **Đừng sửa `shift_attendance_customize.py` / `.js` / `.json` / `scheduler.py`** — đang chạy
   đúng, được yêu cầu giữ nguyên cho tới khi có yêu cầu thay đổi.
2. Trong `shift_attendance_customize.py` có 3 hàm **code chết** không ai gọi:
   `calculate_working_day_for_excel` · `get_excel_cell_display` · `populate_single_employee_row`.
   Hàm đầu hiện thực đúng mục 3 nhưng **không** phải đường chạy thật — đường thật đi qua
   `standard_export.py`. Đừng nhầm hai chỗ khi sửa quy tắc.
3. `report_js.py` chạy cho **mọi** report của site. Hỏng là hỏng toàn bộ phần Report, nên phần
   nối thêm đã bọc try/except riêng — đừng bỏ.
4. Thêm mã nghỉ mới: sửa `LEAVE_WORKING_DAYS` **và** mục 3 của file quy chế, rồi chạy lại test.
   Mã lạ không có trong bảng sẽ **không bị đoán bừa** — nó quay về `giờ làm / 8`.
5. **Nếu clone JS hỏng** (file `.js` bị đổi tên/di chuyển), `custom_get_script` nuốt lỗi và phục
   vụ JS gốc của HRMS. Report vẫn mở được nhưng mang **bộ filter của HRMS**
   (`company`, `consider_grace_period`, `include_attendance_without_checkins`) — `execute` của
   bản Customize bỏ qua filter lạ và coi các filter thiếu là rỗng, nên chỉ *khác giao diện*,
   không vỡ. Dấu hiệu nhận biết: mất 3 nút bấm. Xem `Error Log` → "Report JS Clone Error".
