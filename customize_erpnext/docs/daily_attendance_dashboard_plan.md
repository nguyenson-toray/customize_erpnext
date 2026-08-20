# Daily Attendance — Dashboard + Email

> **Mục đích:** Kế hoạch làm dashboard Daily Attendance cho giám đốc xem trực tiếp, kèm email chấm công hằng ngày.
> **Phạm vi:** Tài liệu
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-14

> **Trạng thái 2026-08-14:** Phase 1 (provider) + Phase 2 (dashboard) **ĐÃ CODE, đã cài vào site,
> chưa test trên UI thật**. Phase 3 (email) + Phase 4 (cron) chưa làm.
> **Mục tiêu:** thêm dashboard `Daily Attendance` cho giám đốc xem trực tiếp, kèm email hằng ngày lấy từ **cùng một nguồn dữ liệu**.
> **KHÔNG thay thế** email 08:15 hiện tại (`report/shift_attendance_customize/scheduler.py`, 1.593 dòng) — email đó giữ nguyên 100%.

---

## 1. Quyết định kiến trúc

### 1.1 Đảo chiều phụ thuộc

Ý tưởng ban đầu là "email fetch data từ chart có sẵn". Khảo sát cho thấy **không khả thi** — phải đảo lại:

```
        customize_erpnext/api/daily_attendance_metrics.py
                    get_daily_metrics(date)          ← single source of truth
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
     Dashboard Chart Source            daily_attendance_email.py
     + Number Card (type=Custom)       (render HTML thuần)
```

### 1.2 Vì sao không fetch từ chart (3 lý do đã kiểm chứng)

**(a) Chart hiện tại trả số LŨY KẾ, không phải số của NGÀY.**

| Nguồn | Kết quả đo được |
|---|---|
| Number Card `HR Overview - Present` | **154.007** (toàn bộ lịch sử) |
| Attendance Present ngày 12/08/2026 | **937** |
| Chart `Absent by Section` → Sewing | **1.830** (toàn bộ lịch sử) |

Nguyên nhân trong core Frappe:
- `frappe/desk/doctype/dashboard_chart/dashboard_chart.py:131` — chart `Group By` gọi thẳng
  `get_group_by_chart_config(chart, filters)`, **không truyền `timespan` / `from_date` / `to_date`**.
  Nên `timespan = "Last Year"` trên 2 chart Absent bị bỏ qua hoàn toàn.
- `frappe/desk/doctype/number_card/number_card.py:122` — `get_result(doc, filters, to_date)`
  chỉ có `to_date`, áp lên `creation`, mà `creation` ≠ `attendance_date`. Không có `from_date`.

**(b) Không có API thống nhất — 3 đường khác nhau** (`chart_widget.js:839-869`):

| `chart_type` | Đường lấy data |
|---|---|
| Count / Sum / Average / Group By | `dashboard_chart.get(chart_name=…)` |
| Custom | method của Dashboard Chart Source |
| Report | `frappe.desk.query_report.run` |

**(c) Email không chạy JS.** `frappe-charts` render SVG bằng JavaScript trong browser;
email client không chạy JS và **Gmail strip luôn thẻ `<svg>` inline**.
Môi trường: **không có matplotlib**; có `wkhtmltoimage` + Pillow 12.2 (đều không dùng — xem 4.2).

### 1.3 Stacked bar — có hỗ trợ, kèm điều kiện

- `frappe-charts` bundled hỗ trợ `barOptions: { stacked: 1 }`
  (xác nhận trong `apps/frappe/node_modules/frappe-charts/dist/frappe-charts.esm.js`).
- Dashboard Chart phơi ra qua field **`custom_options`**, merge vào chart args tại `chart_widget.js:716`.
- **Điều kiện:** stacked cần ≥2 dataset, nhưng `Count`/`Sum`/`Group By` của core chỉ sinh **1 dataset**.
  → Stacked bar **chỉ làm được với `chart_type = "Custom"` + Dashboard Chart Source**.
- Tiền lệ: `hrms/hr/dashboard_chart_source/hiring_vs_attrition_count` trả 2 dataset.

---

## 2. Định nghĩa nghiệp vụ (ĐÃ CHỐT)

### 2.1 Headcount

```
Net Headcount (mẫu số của MỌI phép tính)
    = Employee.status='Active'
    − đang nghỉ thai sản (DISTINCT employee)
    − nhân viên nhận việc TRONG NGÀY (date_of_joining = ngày báo cáo)
```

Cả **thai sản** và **nhận việc trong ngày** đều là **số hiển thị tham khảo** — đếm và show ra,
nhưng **không đưa vào bất kỳ phép tính nào khác**: không vào Present, không vào Absent,
không vào mẫu số tỉ lệ chuyên cần, không vào chart phân nhóm.

- Nhân viên nghỉ thai sản **vẫn giữ `status = 'Active'`** → đếm Active thuần sẽ thổi phồng lực lượng lao động.
- Đếm **DISTINCT employee**, không đếm bản ghi: một NV có thể có nhiều bản ghi `Employee Maternity`.
- Điều kiện: `Employee Maternity.status = 'Maternity Leave'` AND `Employee.status = 'Active'`.
- **Dùng lại** `customize_erpnext/api/hr_overview_cards.py::_maternity_leave_people()` — đừng viết công thức mới.
- Số thai sản **chỉ hiển thị tham khảo**, không bao giờ cộng vào headcount, không bao giờ tính là vắng.
- Số liệu 2026-08-13: Active **1.034** − thai sản **32** = **1.002**.

### 2.2 Present / Absent

| Khoản | Quy tắc |
|---|---|
| **Absent** | Tất cả không đi làm. **Không phân biệt lý do** (có phép / không phép gộp chung) |
| **Half Day** | **Tính là Absent** |
| **New Joiners** | `date_of_joining = ngày báo cáo`. **Chỉ đếm và hiển thị**, loại khỏi Present, Absent, mẫu số và chart — xem 2.6 |
| **Ca chưa bắt đầu** | **Loại khỏi cả Present và Absent** — chưa tới giờ vào ca thì không phải vắng. Hiển thị riêng *"Shift 2 – Not Started"* |

> ⚠ **"Chưa bắt đầu" phải so với ĐỒNG HỒ, không phải mốc cố định.** Bug 2026-08-14: dùng hằng số
> `MORNING_CUTOFF = "12:00:00"` nên mọi ca bắt đầu sau 12h **luôn** bị coi là chưa bắt đầu — mở
> dashboard lúc 14h vẫn thấy "Shift 2 not started" dù ca đã chạy được 1 tiếng.
> `_late_starting_shifts(date)` giờ so `Shift Type.start_time` với `now_datetime()`, và trả về rỗng
> cho ngày quá khứ (ngày đã xong thì không còn gì "chưa bắt đầu"). Kiểm chứng: 06:30 → 4 ca pending,
> 08:20 → chỉ Shift 2, 14:01 → không còn ca nào.
| **Unaccounted** | Dòng đối soát, xem 2.4 |

**Ca làm việc** (`Shift Type`):

| Shift | Giờ | Số người có Shift Assignment |
|---|---|---|
| Shift 1 | 06:00–14:00 | 8 |
| Shift 2 | 14:00–22:00 | **8** |
| Canteen 6:30–15:30 | 06:30–15:30 | 9 |
| Day (fallback) | 08:00–17:00 | ~1.009 |

Shift resolution theo policy đã chốt: `Shift Assignment → default_shift → Day`.
Lưu ý `Shift Assignment` dùng field **`shift_type`**, không phải `shift`.

### 2.3 Ngày nghỉ

**Chắc chắn skip Chủ nhật** + ngày lễ. Dùng lại `scheduler.py::_is_holiday_or_sunday()`.
Không có bước này thì sáng CN giám đốc nhận mail "Absent 1.002".

### 2.3b Chỉ tính nhân viên có prefix ID

Mọi truy vấn attendance **chỉ lấy nhân viên có `name LIKE '<prefix>%'`**, với prefix đọc từ
`Attendance Calculation Setting.employee_id_prefix` (hiện là `TIQN`). Dùng lại
`scheduler.py::_get_employee_prefix()` — giống hệt cách email 08:15 đang làm.

Bản ghi rác/test (`Test-9999`…) nằm ngoài prefix nên tự động biến mất; trước khi có filter này
chúng hiện lên thành `Unaccounted = 1` vĩnh viễn.

### 2.4 Dòng đối soát (Unaccounted)

```
Present + Absent + Shift2_pending + Unaccounted = Net Headcount
```

(`New_joiners` và `Maternity` **không** xuất hiện trong phương trình vì đã bị trừ khỏi Net Headcount ở 2.1.)

Nếu `Unaccounted ≠ 0` → có nhân viên không sinh được bản ghi Attendance = **lỗi dữ liệu**.

`Unaccounted` **không có number card** (user bỏ) nhưng vẫn nằm trong dict trả về của
`get_daily_metrics()` để dùng khi debug và để đối soát trong email. Hiện `= 0` mọi ngày đã test.

### 2.5 "As of HH:MM" — bắt buộc

Email gửi 08:20, ca Day bắt đầu 08:00 → mới vào ca **20 phút**. Người đến muộn 08:25 bị đếm Absent
tại thời điểm gửi. Số liệu **bản chất là tạm thời** → phải đóng dấu
**"As of 08:20 · Provisional"** thật nổi bật, nếu không giám đốc hiểu nhầm là số chốt.

### 2.6 ⚠ Nhân viên nhận việc trong ngày — vì sao BẮT BUỘC phải loại

Đây không phải chi tiết nhỏ. Nhân viên ngày đầu nhận việc **gần như luôn được ghi `Half Day`**
(243/335 bản ghi trong 3 tháng gần nhất), mà theo 2.2 thì **Half Day = Absent**.
Không loại ra thì họ bị đếm là VẮNG.

Tác động đo được:

| Ngày | Half Day | trong đó là NV nhận việc hôm đó | Absent nếu KHÔNG loại | Absent sau khi loại |
|---|---|---|---|---|
| 11/08/2026 | 28 | **21** (75%) | 94 | **73** |
| 04/08/2026 | 22 | **14** (64%) | 66 | **52** |
| 12/08/2026 | 12 | 0 | 66 | 66 |

Ngày 11/08 sẽ báo sai **+29%**. Công ty tuyển theo đợt, ngày tuyển thường **10–21 người**
(cao nhất 60 ngày qua: 21 người ngày 11/08).

**Cách làm:**
- Trừ khỏi Net Headcount (2.1) → tự động biến mất khỏi mọi tỉ lệ.
- Loại khỏi query Present/Absent và khỏi cả 2 chart phân nhóm.
- Hiển thị thành **một Number Card riêng: `New Joiners Today`** — thuần thông tin.

---

## 3. Quy tắc phân nhóm (ĐÃ CHỐT — data-driven, KHÔNG hardcode)

> **2026-08-14:** user đã thêm field **`Group.group_attendance`** (Select). Toàn bộ quy tắc
> hardcode theo department/section/`LIKE 'Line%'` trước đây **bị bỏ** — bucket giờ đọc thẳng từ field này.
> Muốn đổi cách nhóm thì sửa dữ liệu trong doctype `Group`, **không sửa code**.

```
bucket = Group.group_attendance   (join Employee.custom_group → Group.name)

Nếu group_attendance rỗng / NULL / '0'  → 'Pro-Other'
Nếu Employee.custom_group rỗng          → 'Pro-Other'
Nếu group_attendance = 'Other'          → 'Pro-Other'
```

### ⚠ Danh sách bucket KHÔNG hardcode trong code

`bucket_order()` đọc thẳng options của field `Group.group_attendance` bằng
`frappe.get_meta("Group").get_field("group_attendance").options`. Thêm / bớt / đổi tên / **đổi thứ tự**
một option trên doctype là dashboard và email đổi theo, **không sửa dòng code nào**.
Thứ tự cột chart = đúng thứ tự options.

Options hiện tại: `Office`, `Engineering`, `Canteen`, `Pro-Sewing`, `Pro-Preparation`, `Pro-QAQC`,
`Pro-Other` — 7 cột. `Other` **đã gỡ khỏi options** ngày 2026-08-14; muốn gộp một bucket vào cái khác
thì xoá option đó chứ đừng thêm luật gộp trong code.

Chỉ **2 tên** còn nằm trong code, vì field không diễn đạt được ý nghĩa của chúng:

| Hằng số | Ý nghĩa | Nếu tên đó biến mất khỏi options |
|---|---|---|
| `SEWING_BUCKET` | bucket được vẽ chart chi tiết theo từng line | chart Sewing rỗng |
| `FALLBACK_BUCKET` | nơi chứa NV mà field không xếp được | tự dùng option **cuối cùng** + ghi log cảnh báo |

`FALLBACK_BUCKET` hứng 3 trường hợp: `group_attendance` rỗng/`'0'`, `Employee.custom_group` rỗng, và
giá trị cũ không còn trong options. Nhờ vậy gỡ một option không bao giờ làm mất người khỏi tổng.

- `Employee.custom_group` là **Link → `Group`**; `Group.parrent` (typo, đúng tên field) là Link → `Section`.
- Chart chi tiết (`by_line`) = các Group có `group_attendance = 'Pro-Sewing'` (hiện 20 Line).
  **Không dùng `LIKE 'Line%'`** — nếu sau này đổi tên line thì field vẫn đúng.

### Đối chiếu Active 2026-08-14

| Bucket | Active |
|---|---|
| Pro-Sewing | 581 |
| **Pro-Other** | **227** |
| Pro-Preparation | 109 |
| Pro-QAQC | 72 |
| Office | 30 |
| Engineering | 18 |
| Canteen | 9 |
| **Tổng** | **1.046 ✓** |

`Pro-Other` (227) = 154 thuộc Group đã set `Pro-Other` + 60 nhân viên có `custom_group` rỗng
(56 trong đó thuộc Sewing — phần lớn là NV mới chưa gán line) + 13 nhân viên thuộc Group chưa set
`group_attendance` (`Control`, `Technical A/B`…).

### ⚠ Bẫy khi code

1. **`Group` có một record tên literal `'0'`** (`group_attendance = 'Office'`), trong khi `'0'` cũng là
   giá trị **chưa set** của field Select. Phân biệt bằng `Group.group_attendance`, đừng bằng `Group.name`.
2. **Không hardcode tên department** (`'Production - TIQN'` có hậu tố abbr công ty). Sau thay đổi này
   thì không còn cần đọc department/section nữa — hết bẫy.
3. Join `Employee` live, **không** đọc snapshot `custom_section`/`custom_group` trên `Attendance`
   (có bẫy stale-meta). Chỉ báo cáo ngày hiện tại nên join live an toàn hơn.
4. Kiểm tra định kỳ có Group mới nào chưa set `group_attendance` không — chúng âm thầm rơi vào `Other`.

---

## 4. Thiết kế hiển thị

### 4.1 Dashboard `Daily Attendance`

| Widget | Loại | Nội dung |
|---|---|---|
| Donut tổng quan | Donut | Lát = **Present / Absent**; **Net headcount đặt ở tâm** |
| Chart A | Stacked bar, `custom_options: {"barOptions":{"stacked":1}}` | 6 bucket cấp cao (Sewing gộp thành 1 cột) |
| Chart B | Stacked bar | Riêng Sewing theo **Line 01–20** (Sewing = 69% nhân sự nên tách riêng) |
| Chart C | Line, **2 series** | Present và Absent qua **7 ngày làm việc** gần nhất |
| Chart D | Pie | Headcount theo ca (Day / Shift 1 / Shift 2 / Canteen) |
| Number Cards | Custom | Net Headcount · Present · Absent · Attendance Rate % · **Shift 2 Not Started** · New Joiners Today (ref) · Maternity (ref) |

> ⚠ **Card `Shift 2 Not Started` là bắt buộc, đừng bỏ.** `Present + Absent` **không** cộng ra
> Net Headcount — thiếu đúng số người ca 2 (14:00), vốn không phải Present cũng không phải Absent.
> Bỏ card này đi thì `928 + 65 ≠ 1001` và người xem tưởng dashboard tính sai. Đã bỏ một lần rồi
> thêm lại vì lý do đó.

**Shift resolution:** Shift Assignment đang hiệu lực → nếu không có thì **`Day`**.
`Employee.default_shift` **cố tình không đọc** — nó là `Day` cho tất cả trừ 9 người, mà 9 người đó
đã có Shift Assignment rồi; đọc thêm chỉ tạo thêm một nguồn để hai bên mâu thuẫn.
Pie đếm trên đúng universe net headcount nên các lát cộng lại = 1.001, không phải một tổng khác.

> ⚠ **Không chỉnh được mật độ vạch trục y của Bar chart.** Đây là giới hạn cứng của `frappe-charts`,
> đừng mất công tìm option:
> - `AxisChart.js:67` → `calcYAxisParameters(values, this.type === 'line')`, tức `withMinimum`
>   **chỉ true với Line**. Bar luôn bắt đầu trục y từ 0.
> - `utils/intervals.js:getChartRangeIntervals()` lấy mantissa/exponent của max. Max trong khoảng
>   10–99 → bước nhảy **luôn là 10**. Sewing Lines max ≈ 39 → vạch `10, 20, 30, 40`.
> - `axisOptions.yAxisRange` chỉ nới rộng min/max, **không** chia nhỏ được.
>
> Cách đọc số chi tiết: `show_values_over_chart = 1` (đã bật, in số thật lên từng cột). Nếu sau này
> cần trục y mịn cho số vắng, tách riêng một chart chỉ có Absent — max ≈ 5 → exponent 0 → vạch
> `0,1,2,3,4,5`.

> ⚠ **Chart D — pie bị lệch tỉ lệ nặng.** `Day` chiếm 976/1.001 = **97,5%**; ba lát còn lại
> (Canteen 9, Shift 1 8, Shift 2 8) mỗi lát <1% nên chỉ là sợi chỉ, hover gần như không trúng.
> Nếu cần đọc được số ca nhỏ thì đổi `"type"` sang `Bar` trong
> `dashboard_chart/daily_attendance___headcount_by_shift/*.json` — dữ liệu giữ nguyên, không sửa code.

> ⚠ **Chart C — cảnh báo chênh lệch thang đo.** Present ≈ 900, Absent ≈ 65 trên cùng một trục y.
> Biến động thật của Absent (60→84, tức **+40%**) chỉ chiếm ~2,5% chiều cao biểu đồ nên nhìn gần
> như đường thẳng. **Không** giải quyết bằng trục y thứ hai — hai thang đo cạnh nhau khiến 60 người
> vắng trông như khủng hoảng. Nếu đọc không rõ, chuyển sang **1 line Absent** (Present suy ra được
> = net − absent) hoặc quay lại line tỉ lệ chuyên cần %.

**Chart A và B hiển thị SỐ TUYỆT ĐỐI, không hiển thị %** — mỗi nhóm thường chỉ vắng 1–2 người,
% sẽ thành nhiễu (1/3 người = 33%).

> ⚠ **Không dùng Pie cho `net headcount / present / absent`.** Pie thể hiện các phần của một tổng,
> mà `net headcount = present + absent`. Đưa cả 3 vào pie thì tổng thành 2× thực tế và lát
> "net headcount" luôn chiếm đúng 50% — vô nghĩa. Dùng Donut + số ở tâm.

> ⚠ **Trend phải là 7 *ngày làm việc*, không phải 7 ngày lịch.** Theo lịch thì line chart có một điểm
> rớt xuống 0 mỗi Chủ nhật, nhìn như sự cố.

> ⚠ **Không dùng `Employee.custom_group` (51 giá trị) hay `custom_section` (16) làm nhóm chính** —
> đã thay bằng quy tắc bucket ở mục 3.

### 4.2 Email

- **100% tiếng Anh.** Không đính kèm file, không danh sách nhân viên (giám đốc xem, không đi vào chi tiết).
- **Không nhúng chart.** Dùng bảng HTML + thanh bar bằng CSS `div width:%`
  → chạy được mọi email client kể cả Gmail. Không SVG, không ảnh, không headless browser.
- Layout: dải KPI → Donut thay bằng 3 số → bảng 6 bucket → bảng Line 01–20 → footer *"As of 08:20 · Provisional"*.
- **Giả định cần xác nhận:** cột `%` bỏ khỏi chart chi tiết, nhưng **giữ ở bảng 6 bucket cấp cao**
  trong email (mẫu số 41/18/582/104/73/216 đủ lớn để % có nghĩa). Nếu không muốn thì bỏ luôn.

---

## 5. Các bước triển khai

### Phase 1 — Data provider

**File mới:** `customize_erpnext/api/daily_attendance_metrics.py`

```python
get_daily_metrics(date=None) -> {
  "as_of":  "08:20",
  "date":   "2026-08-14",
  "is_holiday": False,
  "headcount": {"active": 1034, "maternity": 32,      # ref only
                "new_joiners": 0,                      # ref only
                "net": 1002},                          # = active − maternity − new_joiners
  "status": {"present": …, "absent": …, "shift2_pending": …, "unaccounted": …},
  "attendance_rate": 0.0,
  "by_bucket":  [{"bucket": "Office", "present": …, "absent": …}, …],   # 6 dòng
  "by_line":    [{"line": "Line 01", "present": …, "absent": …}, …],    # 20 dòng
  "trend_7wd":  [{"date": …, "rate": …}, …],                            # 7 ngày làm việc
}
```

- Thuần SQL, không side effect, cache 5 phút.
- Dùng lại `hr_overview_cards._maternity_leave_people()`.
- Join `Department.department_name`.

### Phase 2 — Dashboard

Module file trong `customize_erpnext/customize_erpnext/` (versioned, không để config trôi trong DB —
bộ `HR Overview` hiện tại đã theo pattern này).

- **Dashboard Chart Source** (mỗi cái = folder `.js` khai báo method+filters, `.py` chứa `get_data`):
  - `daily_attendance_by_bucket`  → 2 dataset (Present/Absent), stacked
  - `daily_attendance_by_line`    → 2 dataset, stacked
  - `daily_attendance_trend`      → 1 dataset, line
  - `daily_attendance_overview`   → donut Present/Absent
- **Number Card** `type = "Custom"` + `method = …` (đúng pattern `hr_overview_cards` đang dùng cho
  `HR Overview - Headcount` và `Maternity Leave`).
- **Dashboard** doctype tên `Daily Attendance`.

### Người nhận & nút gửi tay

Cả hai báo cáo lấy người nhận từ **`Attendance Calculation Setting`** (Single):

| Field | Dùng cho |
|---|---|
| `manager_recipients` | **Summary** — bản một trang cho giám đốc (`api/daily_attendance_email.py`) |
| `hr_recipients` | **Detail** — báo cáo 08:15 đầy đủ kèm Excel (`report/shift_attendance_customize/scheduler.py`) |

Nút **Send Daily Attendance Report** nằm trên form `Attendance Calculation Setting` — cùng chỗ với
2 field người nhận, nên sửa danh sách và bắn thử ở một nơi. Dialog có select `Summary / Detail`,
tự đổi endpoint + prefill đúng danh sách, cho sửa trước khi gửi.

> ⚠ **Đừng đọc recipient qua `get_attendance_settings()`** — helper đó chỉ trả các key có trong
> `DEFAULTS` của nó nên field recipient bị lọc mất (trả về rỗng, không báo lỗi). Dùng
> `frappe.db.get_single_value(...)`. Mở rộng `DEFAULTS` thì đụng vào cấu hình mà report 08:15 đang chạy.

> ⚠ Nếu `manager_recipients` rỗng, hàm trả `{"status": "skipped"}` chứ **không** tự rơi về địa chỉ
> test — tránh âm thầm gửi nhầm khi ai đó xoá cấu hình.

### ⚠ 2026-08-14: cron 08:15 ĐÃ BỊ XOÁ, chỉ còn 08:20

Trước đây có 2 cron gửi 2 mail cho HR, kèm **cùng một file Excel dựng 2 lần**. Đã gộp:

```
"20 8 * * *" -> api.daily_attendance_email.send_daily_attendance_email_scheduled
                  ├─ recalculate_attendance(today)   ← MỘT lần, trước khi gửi
                  ├─ manager_recipients -> summary
                  └─ hr_recipients      -> summary + Excel
```

- Cron **luôn** recalculate attendance (chạy 08:20, ngay sau giờ vào ca nên checkin vừa mới về).
  Gọi **một lần** ở đầu job, không phải mỗi audience một lần — đó là bước tốn thời gian nhất, và
  chạy 2 lần còn khiến 2 mail có thể lệch số.
- Danh sách rỗng ⇒ **bỏ qua audience đó**, không fallback sang địa chỉ khác.
- Chủ nhật / ngày lễ ⇒ bỏ qua toàn bộ, không recalculate.

**Đã xoá 783 dòng code chết** khỏi `scheduler.py` (1.681 → 898 dòng):
`send_daily_attendance_report`, `_send_daily_attendance_report_job`, `generate_email_content` (636
dòng), `get_current_frappe_site_name`, `send_daily_attendance_report_scheduled`,
`get_last_employee_checkin_time`, import `only_for_sites`.

**Excel giờ có 4 sheet.** Sheet 3-4 là 2 danh sách trước đây CHỈ có trong body mail 08:15 —
không đưa vào workbook thì mất hẳn:

| # | Sheet | Nội dung |
|---|---|---|
| 1 | Absent-OnLeave-Present | toàn bộ chấm công trong ngày |
| 2 | Missing … | thiếu chấm công từ 26 tháng trước |
| 3 | **Left with check-ins** | NV đã nghỉ việc nhưng vẫn có checkin |
| 4 | **Early checkout day shift** | về sớm ca ngày — nghi thai sản chưa đăng ký |

> Tên sheet 2 bị cắt còn 31 ký tự: Excel từ chối tên dài hơn.

### Nút gửi tay

Có ở **2 chỗ**, cùng gọi `send_daily_attendance_email`:
- report `Shift Attendance Customize` → nút `📩2. Send Report`
- form `Attendance Calculation Setting` → nút `Send Daily Attendance Report`

Dialog có checkbox **`Attach file detail`** (không còn select Summary/Detail).

> ⚠ **`Force Update Attendance` độc lập với `Attach file detail`** — đừng nối chúng bằng `depends_on`
> nữa. Recalculate dựng lại bảng Attendance, mà **mọi con số trong mail đều đọc từ đó**, không riêng
> file Excel. Bug 2026-08-14: cờ này từng chỉ được truyền vào `_detail_workbook()` nên tick
> Force Update mà không tick Attach detail thì **bị bỏ qua im lặng**.
**Recipients phải gõ tay, mỗi email một dòng** — cố tình KHÔNG prefill từ `manager_recipients` /
`hr_recipients`, để một lần bấm thử không bao giờ chạm tới người nhận thật. Hai field đó chỉ phục vụ
cron.

### Một layout cho cả Summary lẫn Detail

`send_daily_attendance_email(report_type=...)` là endpoint **duy nhất** cho cả hai:

| | Summary | Detail |
|---|---|---|
| Nội dung | trang tổng quan | trang tổng quan **+** khối detail gập lại |
| Đính kèm | không | `Attendance_Report_<date>.xlsx` |
| Recipients | `manager_recipients` | `hr_recipients` |

Phần detail dùng lại **nguyên** nội dung email 08:15: `scheduler.collect_daily_report_context()`
(tách ra từ `_send_daily_attendance_report_job` để hai bên dùng chung — một chỗ định nghĩa
"detail là gì", không thể lệch nhau) → `generate_email_content()` → bóc `<style>` + trong `<body>`
ra rồi nhúng lại (nested `<html>` sẽ bị mọi client vứt).

> ⚠ **Công ty dùng MS 365 → `<details>` KHÔNG gập được.** Outlook desktop (engine Word) và OWA đều
> bỏ thẻ `<details>` nhưng **giữ nội dung con**, nên khối detail luôn mở sẵn. Đọc trên **iPhone/iPad
> Mail** (WebKit) thì gập thật. Không có JS trong email nên không có cách nào gập được ở mọi nơi.
> Degradation an toàn: không bao giờ mất nội dung.

> Bù lại, Outlook **không cắt** mail dài như Gmail (Gmail cắt >102KB). Bản Detail ~311KB HTML nên
> nếu sau này có người nhận dùng Gmail thì họ sẽ thấy "View entire message" — bản 08:15 cũ (~276KB)
> vốn đã bị vậy, không phải lỗi mới.

> Outlook engine Word bỏ qua `border-radius` (card vuông góc) và `max-width` — đã thêm thuộc tính
> `width="1040"` để Outlook lấy đúng bề rộng.

### Phase 3 — Email

**File mới:** `customize_erpnext/api/daily_attendance_email.py`
Gọi `get_daily_metrics()` → render HTML → `frappe.sendmail`. Skip CN/lễ.

### Phase 4 — Cron & test

- Cron mới trong `hooks.py`: `"20 8 * * *"`. **KHÔNG đụng** entry `"15 8 * * *"` hiện có.
- ⚠ Sửa `hooks.py` → **bắt buộc restart web**; `bench console` cho false positive khi verify hooks.
  **Hỏi user trước khi restart** (production, giờ làm việc).
- ⚠ **Recipient khi test LUÔN LUÔN là `son.nt@tiqn.com.vn`.** Không bao giờ test với danh sách thật.
  Danh sách production chỉ điền sau khi user xác nhận đã test xong.
- Đối chiếu số của `get_daily_metrics()` với email 08:15 hiện tại.
- Xác nhận `Unaccounted = 0`.
- **Chỉ commit sau khi user test OK trên UI thật.** Commit thẳng vào `main`, không tạo nhánh.

### Ước lượng

| Phase | Effort |
|---|---|
| 1 — provider | ~250 dòng, 2–3h |
| 2 — dashboard | ~200 dòng + ~12 file JSON, 2h |
| 3 — email | ~200 dòng, 1–2h |
| 4 — cron/test | 1h |

---

## 6. Việc còn treo

- [x] ~~Điều tra lệch 1.003 Attendance / 1.002 net headcount~~ → 12/13 là nhân viên join **sau** ngày
      báo cáo (đã trừ bằng `_not_yet_employed()`); 1 còn lại là bản ghi rác `Test-9999`, đã tự loại
      nhờ filter prefix (2.3b). **`Unaccounted` = 0** ở cả 14/08, 12/08, 11/08.
- [ ] ⚠ `bench migrate` đang **gãy sẵn** (không do việc này): app `DuckDB Sync` thiếu `pyarrow`.
      Fixtures của Daily Attendance đã import tay bằng `import_file_by_path`. Cần fix trước khi
      deploy bình thường.
- [ ] Xác nhận giả định ở 4.2: giữ hay bỏ cột `%` trong bảng 6 bucket của email.
- [ ] Chốt danh sách recipient production (sau khi test xong).
