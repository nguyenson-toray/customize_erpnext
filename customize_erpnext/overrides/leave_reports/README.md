# Override 2 report số dư phép — chỉ phép năm, tính trong bộ nhớ

Override `Employee Leave Balance` và `Employee Leave Balance Summary` của HRMS.

**Hai mục tiêu:** chọn được **một** leave type mỗi lần chạy (mặc định phép năm), và **hết chậm**.

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
   khối lượng so với bản gốc luôn quét cả 10 loại
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

Bắt buộc chọn, **mặc định `Phép năm/ Annual leave`** (lấy theo cờ `is_earned_leave = 1`, không
hardcode tên). Mỗi lần chạy xử lý đúng một loại → 1 dòng/nhân viên thay vì 10.

Engine dùng được cho **mọi** leave type. Chọn một trong 9 loại nghỉ phát sinh (không phân bổ) thì
Allocated = 0 và Balance = −(đã nghỉ) — đúng y bản HRMS.

### `Employee Leave Balance`
Giữ nguyên 8 cột và công thức.

**Bỏ filter `Consolidate Leave Types`.** Filter đó gom dòng theo leave type và chèn một dòng tiêu
đề cho mỗi nhóm — chỉ có nghĩa khi report trả **nhiều** leave type. Nay chỉ còn phép năm nên nó
luôn sinh đúng một dòng tiêu đề thừa rồi thụt lề toàn bộ phần còn lại, mà bản gốc còn để
`default: 1` (bật sẵn). Python bỏ qua giá trị filter; ô chọn được gỡ khỏi giao diện trong
`report_js.py`.

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

## File

```
overrides/leave_reports/
├── __init__.py                        # monkey patch, giữ bản gốc ở _tiqn_original_execute
├── leave_report_core.py               # LeaveBalanceEngine — nạp 1 lần, tính trong bộ nhớ
├── employee_leave_balance.py          # execute + columns + get_data thay thế
├── employee_leave_balance_summary.py  # execute + columns + get_data thay thế
├── report_js.py                       # nối JS vào script report (thêm Leave Type, gỡ filter thừa)
├── test_leave_reports.py              # đối chiếu mới vs gốc (1.126 assert, 5 phần)
└── README.md
```

Nạp qua `overrides/__init__.py`. **Sửa Python phải `bench restart`.**

---

## Lưu ý khi sửa tiếp

1. **Đừng hardcode tên "Phép năm/ Annual leave"** — giá trị mặc định của filter lấy từ
   `get_annual_leave_types()` (`is_earned_leave = 1`), kể cả trong JS chèn thêm (dựng ở server).
2. **Chạy `test_leave_reports.py` sau mỗi thay đổi.** Bản gốc vẫn còn ở
   `_tiqn_original_execute`, nên luôn đối chiếu được. Tăng tốc mà lệch số là vô nghĩa.
3. **Đừng bỏ nhánh fallback vắt biên và nhánh carry-forward.** Hiện tại dữ liệu TIQN không chạm
   vào chúng, nên bỏ đi sẽ **không có test nào đỏ** — rồi cắn khi sang kỳ 2027 có carry forward.
4. `balance_on()` cố tình **bỏ `validate_leave_access()`** (15% thời gian bản gốc): report đã
   lọc nhân viên bằng `frappe.get_list` nên đã qua phân quyền. Đừng thêm lại trong vòng lặp.
5. **Sửa filter/JS của report HRMS chỉ có một đường: `report_js.py`.** Frappe **không có hook**
   nào cho JS của report (không có `report_js` như `doctype_js`), và
   `query_report.get_script()` chỉ đọc `Report.javascript` **khi file `.js` không có trên đĩa**
   (`query_report.py:199`) — file HRMS thì luôn có. Nên phải gán đè `get_script` rồi nối thêm JS.
   ⚠ Nhớ bọc `frappe.whitelist()` khi gán đè, và nhớ hàm đó chạy cho **mọi** report nên phần nối
   thêm phải bọc try/except riêng.
6. `cf_expiry()` dùng `frappe.utils.nowdate()` để sao y HRMS. Biết là
   `System Settings.time_zone` từng tự nhảy về Asia/Kolkata — chỗ này vô hại vì TIQN có 0 dòng
   CF, nhưng nếu bật carry forward thì xem lại.
