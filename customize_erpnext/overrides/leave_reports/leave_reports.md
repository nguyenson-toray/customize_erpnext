# Override 2 report số dư phép — lọc theo leave type, tính trong bộ nhớ

> **Mục đích:** Override `Employee Leave Balance` và `Employee Leave Balance Summary` của HRMS.
> **Phạm vi:** Override HRMS/ERPNext
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-21

Override `Employee Leave Balance` và `Employee Leave Balance Summary` của HRMS.

**Ba mục tiêu:** chọn được **một** leave type mỗi lần chạy (mặc định phép năm, **xoá trắng =
xem tất cả**), chỉ chạy cho **nhân viên của mình** theo `Attendance Calculation Setting`, và
**hết chậm**.

---

## Kết quả

| Report | Trước | Sau | |
|---|---:|---:|---|
| Employee Leave Balance | 107 s · 180.000 query | **0,12 s · 5 query** | ~900× |
| Employee Leave Balance Summary | 43 s · 88.000 query | **0,12 s · 5 query** | ~360× |

Đo trên 1.004 nhân viên Active, kỳ 26/12/2025 → 25/12/2026. Trước đây chạy Balance cho **một**
department đã timeout 2 phút.

**Số không đổi:** `test_leave_reports.py` đối chiếu từng cột của bản mới với bản HRMS gốc, cho
**cả loại có phân bổ lẫn loại không phân bổ** — **1.126 assert, 0 lệch** trên 120 nhân viên.

---

## Vì sao nhanh được đến vậy

Profile bản gốc (8 NV, 1,727 s) cho thấy nút thắt **không phải database**:

```
get_leave_balance_on (80 lần)                1,035 s   60%
  ↳ trong đó validate_leave_access             0,259 s   15%   ← thuần overhead
get_allocated_and_expired_leaves               0,377 s   22%
pypika dựng câu SQL (prepare_query + _copy)    ~1,0  s
MySQL thực sự thực thi                         0,187 s   11%   ← chỉ 11%
```

*Dựng* câu SQL tốn ngang *chạy* nó. HRMS gọi lại các hàm con cho **từng cặp (nhân viên × leave
type)** → 977 câu SQL cho 8 nhân viên.

Cách sửa không phải tối ưu SQL mà là **đừng sinh 977 câu SQL**:

1. **Chạy 1 leave type mỗi lần** (filter `Leave Type`, mặc định phép năm) — giảm ngay 10 lần
   khối lượng so với bản gốc luôn quét cả 10 loại. Xoá trắng ô đó thì chạy đủ 10 loại, vẫn nhanh
   (đo: 0,4 s cho 1.046 nhân viên × 10 loại) vì mỗi loại chỉ tốn 3 query.
2. **Nạp toàn bộ ledger của leave type đó một lần** — chỉ ~6.000 dòng — rồi group theo nhân viên
   và tính hết trong Python (`AnnualLeaveEngine`)

Số query là **hằng số**, không phụ thuộc số nhân viên.

---

## Giữ đúng con số — ba chỗ dễ sai

**① `get_leaves_for_period()` không cộng `leaves` trong ledger.** Nó **cắt** entry theo biên kỳ
rồi gọi lại `get_number_of_leave_days()` (xử lý nửa ngày + ngày lễ). Với entry nằm **trọn** trong
kỳ thì `leaves` trong ledger đã đúng bằng con số đó — đã kiểm 60/60 nhân viên khớp tuyệt đối, và
kỳ 2026 có **0** entry vắt biên.

Nhưng vắt biên vẫn có thể xảy ra ở kỳ khác. Nên hễ một nhân viên có entry vắt biên thì
**giao cả nhân viên đó cho hàm gốc HRMS** — chậm nhưng đúng, và chỉ áp cho đúng người đó.

**② Nhánh carry-forward giao lại cho HRMS.** Khi `cf_expiry` và `unused_leaves` đều có, công thức
`get_remaining_leaves()` rẽ nhiều ngoại lệ. TIQN hiện có **0 dòng `is_carry_forward`** (mọi LPA
đều `carry_forward = 0`) nên không đáng tự viết lại — `balance_on()` gọi thẳng
`get_leave_balance_on()` ở nhánh đó.

**③ `get_manually_expired_leaves()` của HRMS lấy DÒNG ĐẦU, không SUM.** `manually_expired()`
sao y hành vi đó, kể cả khi nó trông như bug.

---

## Thay đổi thấy được trên UI

### Cả hai report: thêm filter `Leave Type`

**Mặc định `Phép năm/ Annual leave`** (lấy theo cờ `is_earned_leave = 1`, không hardcode tên).
Mỗi lần chạy xử lý đúng một loại → 1 dòng/nhân viên thay vì 10.

**Xoá trắng ô đó = xem TẤT CẢ leave type**, đúng bố cục bản HRMS gốc: `Employee Leave Balance`
trả 10 dòng/nhân viên, `Summary` trả 10 nhóm cột.

**Phép năm luôn đứng đầu.** HRMS sắp thuần theo tên, mà tên tiếng Việt bắt đầu bằng "P" nên phép
năm rơi xuống **cuối cùng trong 10 loại** — đúng loại HR tra nhiều nhất lại nằm xa nhất: ở
`Employee Leave Balance` phải cuộn qua 9 nhóm, ở `Summary` thì 3 cột của nó nằm tận cột 31→33 sau
27 cột nghỉ phát sinh. `get_all_leave_types()` đẩy nó lên đầu, phần còn lại vẫn theo tên. Chỉ đổi
**thứ tự hiển thị**, không đổi tập hợp.

⚠ Filter **cố tình không đặt `reqd`**. Ô bắt buộc thì giao diện không cho xoá và đường "xem tất
cả" bị chặn cứng. Cũng vì thế `resolve_leave_types()` phải trả **mọi** loại khi rỗng chứ không
rơi về phép năm: mặc định phép năm là việc của `default` trong `report_js.py`. Nếu cả hai chỗ
cùng mặc định, người dùng xoá ô chọn vẫn chỉ thấy phép năm và không hiểu vì sao.

Engine dùng được cho **mọi** leave type. Chọn một trong 9 loại nghỉ phát sinh (không phân bổ) thì
Allocated = 0 và Balance = −(đã nghỉ) — đúng y bản HRMS.

### Cả hai report: chỉ chạy cho nhân viên của mình

Lọc thêm theo `Attendance Calculation Setting`:

| Field | Tác dụng |
|---|---|
| `Employee ID Prefix` | chỉ nhận `Employee.name LIKE '<prefix>%'` (hiện `TIQN` — loại 17 mã `Intern-*`) |
| `Exclude Employee IDs` | loại hẳn các mã liệt kê (hiện `TIQN-1080`, `TIQN-2039`, `Test-9999`) |

Đây không phải tuỳ chọn hiển thị. `exclude_employee_ids` là nhân sự của **công ty khác** làm việc
tại nhà máy — quẹt thẻ như mọi người nhưng không thuộc mình để quản lý — cộng vài bản ghi test còn
sót. Report nào bỏ qua hai field này sẽ cho danh sách khác bảng công và khác headcount, mà HR
không có cách nào biết vì sao lệch.

Định nghĩa nằm ở **`overrides/employee_scope.py`**, dùng chung với `Leave Control Panel`. Đo trên
site: 2.437 Employee → **2.417** trong phạm vi.

### `Employee Leave Balance`
Giữ nguyên 8 cột và công thức.

**`Consolidate Leave Types` — giữ, nhưng chỉ áp khi có nhiều leave type.** Filter đó gom dòng
theo leave type và chèn một dòng tiêu đề cho mỗi nhóm. Bản gốc để `default: 1` và chỉ chặn bằng
`len(active_employees) > 1`, nên khi report chạy **một** leave type (mặc định ở TIQN) nó sinh đúng
một dòng tiêu đề vô nghĩa rồi thụt lề toàn bộ phần còn lại.

Thêm điều kiện `len(leave_types) > 1`: chạy một loại thì bảng phẳng, xoá ô Leave Type thì gom nhóm
y bản gốc. Ô chọn từng bị gỡ khỏi giao diện (hồi report bị khoá cứng ở một leave type) và nay đã
được **trả lại**.

**Nới hai cột định danh:** `Employee` 100 → **150**, `Employee Name` 100 → **300**. Bản gốc để
cả hai 100px. Đo trên dữ liệu thật: tên dài nhất 26 ký tự ("Huỳnh Nguyễn Thị Kim Trang"), trung
bình 20,5.

### `Employee Leave Balance Summary` — sửa cả một điểm mù
Bản gốc đọc `get_leave_details()["leave_allocation"]`, mà dict đó **chỉ chứa leave type có
Leave Allocation**. TIQN chỉ cấp allocation cho phép năm → 9 loại còn lại luôn hiện **0** dù đã
nghỉ thật:

```
kỳ 26/12/2025 → 25/12/2026, số ngày bản gốc báo 0:
  Ốm đau              1.832,0    Thai sản            361,0
  Nghỉ không lương      935,0    Nghỉ dưỡng sức      142,0
  Con ốm                463,5    Nghỉ bù/Hỉ sự/...   110,0
                                              ─────────────
                                        tổng   3.843,5 ngày
```

> Không phải bug số âm: `TIQN-0882` phép năm allocated 1,0 / taken 10,0 → **cả hai report đều ra
> −9,0**. Chỉ leave type **không** có allocation mới bị báo 0.

Nay report chạy theo leave type đã chọn và **thêm 2 cột** để đọc được ngay con số từ đâu ra:

```
Employee · Employee Name · Department · <Leave Type> - Allocated · - Taken · - Balance
```

🔴 **Loại không có allocation cần mốc đầu kỳ riêng.** Không có allocation thì không có `from_date`
để tính "đã nghỉ bao nhiêu" — `_period_start()` lấy **Leave Period đang chứa ngày xem**.
Thiếu bước này thì cột `Taken` của 9 loại nghỉ phát sinh **luôn bằng 0**, tức tái tạo đúng điểm
mù mà report này sinh ra để sửa. Đã đối chiếu: tổng `Taken` của Summary khớp tuyệt đối với report
`Employee Leave Balance` cho cả 3 loại đã thử (phép năm 3.528,5 · ốm đau 1.272,5 · không lương
514,0), và `Balance` khớp `closing_balance` từng người, 0 lệch.

### Vẫn cần một report riêng cho 9 loại nghỉ phát sinh
Filter mới cho phép **xem từng loại một**. Nhưng HR cần bảng tổng hợp **tất cả** các loại phát
sinh cùng lúc theo số ngày đã dùng (`DS` còn để đối chiếu BHYT chi trả) — việc đó làm sau.

---

## File liên quan

```
overrides/leave_reports/
├── __init__.py                        # monkey patch, giữ bản gốc ở _tiqn_original_execute
├── leave_report_core.py               # LeaveBalanceEngine — nạp 1 lần, tính trong bộ nhớ
├── employee_leave_balance.py          # execute + columns + get_data thay thế
├── employee_leave_balance_summary.py  # execute + columns + get_data thay thế
├── test_leave_reports.py              # đối chiếu mới vs gốc (1.141 assert, 6 phần)
└── leave_reports.md

overrides/report_js.py                 # dùng chung — ĐÃ CHUYỂN RA NGOÀI (xem bên dưới)
overrides/employee_scope.py            # dùng chung — "ai là nhân viên của mình"
```

> ⚠ `report_js.py` **không còn nằm trong thư mục này**. Nó đã chuyển lên `overrides/report_js.py`
> vì nay phục vụ cả report không liên quan nghỉ phép (`Shift Attendance` — xem
> [`../shift_attendance/shift_attendance.md`](../shift_attendance/shift_attendance.md)). `patch()` được gọi **một lần**
> từ `overrides/__init__.py`, không gọi từ module này nữa.

Nạp qua `overrides/__init__.py`. **Sửa Python phải `bench restart`.**

---

## Bẫy khi sửa

1. **Đừng hardcode tên "Phép năm/ Annual leave"** — giá trị mặc định của filter lấy từ
   `get_annual_leave_types()` (`is_earned_leave = 1`), kể cả trong JS chèn thêm (dựng ở server).
2. **Chạy `test_leave_reports.py` sau mỗi thay đổi.** Bản gốc vẫn còn ở
   `_tiqn_original_execute`, nên luôn đối chiếu được. Tăng tốc mà lệch số là vô nghĩa.
3. **Đừng bỏ nhánh fallback vắt biên và nhánh carry-forward.** Hiện tại dữ liệu TIQN không chạm
   vào chúng, nên bỏ đi sẽ **không có test nào đỏ** — rồi cắn khi sang kỳ 2027 có carry forward.
4. `balance_on()` cố tình **bỏ `validate_leave_access()`** (15% thời gian bản gốc): report đã
   lọc nhân viên bằng `frappe.get_list` nên đã qua phân quyền. Đừng thêm lại trong vòng lặp.
5. **Sửa filter/JS của report HRMS chỉ có một đường: `overrides/report_js.py`.** Frappe **không có hook**
   nào cho JS của report (không có `report_js` như `doctype_js`), và
   `query_report.get_script()` chỉ đọc `Report.javascript` **khi file `.js` không có trên đĩa**
   (`query_report.py:199`) — file HRMS thì luôn có. Nên phải gán đè `get_script` rồi nối thêm JS.
   ⚠ Nhớ bọc `frappe.whitelist()` khi gán đè, và nhớ hàm đó chạy cho **mọi** report nên phần nối
   thêm phải bọc try/except riêng.
6. **Danh sách nhân viên trong test phải nằm TRONG phạm vi.** Bản mới trả rỗng cho người ngoài
   phạm vi, nên nếu `emps` chứa họ thì vòng so sánh chạy 0 lần mà test **vẫn xanh** — mất sạch giá
   trị đối chiếu. `test_leave_reports.py` lấy `emps` qua `scope_filters()` chính vì vậy.
7. **Đừng lọc phạm vi *sau* khi đã lấy dữ liệu.** `custom_get_employees()` đưa điều kiện vào thẳng
   query: lọc sau vẫn kéo về cả nghìn dòng thừa, và `emp_names` truyền cho engine phải là danh
   sách **đã** lọc thì mới giảm được khối lượng ledger.
8. `cf_expiry()` dùng `frappe.utils.nowdate()` để sao y HRMS. Biết là
   `System Settings.time_zone` từng tự nhảy về Asia/Kolkata — chỗ này vô hại vì TIQN có 0 dòng
   CF, nhưng nếu bật carry forward thì xem lại.
