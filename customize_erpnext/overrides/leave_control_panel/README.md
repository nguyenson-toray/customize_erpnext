# Leave Control Panel — chọn nhân viên nào để cấp phép?

Hướng dẫn cho HR. Trả lời một câu hỏi: **bấm `Select Employees` thì danh sách hiện ra dựa vào đâu?**

---

## Ba thứ quyết định danh sách

1. **`Dates Based On`** → chốt kỳ cấp phép (`From Date` / `To Date`)
2. **Checkbox `Include employees who left during the period`** → có kéo người đã nghỉ việc vào hay không
3. **`Attendance Calculation Setting`** → giới hạn "ai là nhân viên của mình" (luôn áp, không tắt được)

---

## 1. `Dates Based On` — ba lựa chọn

| Lựa chọn | Bạn điền gì | Kỳ cấp phép lấy từ |
|---|---|---|
| **Leave Period** | chọn 1 Leave Period | `from_date` + `to_date` của Leave Period đó |
| **Custom Range** | tự điền From Date + To Date | đúng hai ngày bạn điền |
| **Joining Date** | chỉ điền To Date | mỗi người một mốc: **ngày vào làm của chính họ** → To Date |

Thiếu `To Date` → danh sách rỗng, không báo lỗi.

**Cả ba lựa chọn lọc nhân viên giống nhau** — chúng chỉ khác chỗ lấy ngày. Nên:

> 👉 **Dùng `Leave Period`** cho việc cấp phép năm định kỳ: lấy ngày từ một nơi duy nhất, không sợ điền sai.
> `Custom Range` khi cần khoảng đặc biệt. `Joining Date` khi muốn mỗi người tính từ ngày vào làm riêng.

---

## 2. Checkbox `Include employees who left during the period`

Nằm ở mục **Allocate Leaves**, cột phải, ngay dưới `Allocate Based On Leave Policy`.
**Mặc định TẮT.**

### TẮT (bình thường, dùng hằng ngày)

```
Hiện ra nếu:   status = Active
```

Đây là hành vi chuẩn của HRMS. **Hầu hết trường hợp bạn để nguyên như vậy** — phép năm được cấp
lúc đầu kỳ hoặc lúc nhân viên vào làm, khi đó ai cũng còn đang làm việc. Hệ thống tự cộng phép
mỗi tháng vào bản phân bổ đã có, và tự dừng khi người đó nghỉ việc.

### BẬT (chỉ khi cấp phép cho một kỳ đã qua)

```
Hiện ra nếu:   vào làm  ≤  To Date
        VÀ    ( chưa nghỉ việc  HOẶC  ngày nghỉ việc ≥ From Date )
```

Tức là **ai có thời gian làm việc giao với kỳ cấp phép**, kể cả đã `Left` / `Inactive`.

Dùng khi nào: dựng lại phép cho một kỳ đã trôi qua (ví dụ dựng kỳ 2026 vào tháng 8/2026), lúc đó
trong kỳ đã có mấy trăm người nghỉ việc giữa kỳ. Họ **vẫn được hưởng** phép năm cho những tháng
đã làm (Điều 66 NĐ 145/2020 — xem
[QUY_DINH_NGHI_PHEP_2025.md](../leave_application/QUY_DINH_NGHI_PHEP_2025.md)).

**Cấp cho người đã nghỉ là an toàn**, không sợ cấp thừa: hệ thống tính theo đúng số tháng họ
thực làm. Người nghỉ ngày 05/01 nhận **0,0 ngày**; người nghỉ tháng 6 nhận phần của 6 tháng.

### Số thật đo trên hệ thống (17/08/2026, kỳ 26/12/2025 → 25/12/2026)

| Checkbox | Số NV hiện ra | Trong đó |
|---|---:|---|
| TẮT | **1.002** | Active 1.002 |
| BẬT | **1.496** | Active 1.002 · Left 462 · Inactive 32 |

Chênh **494 người** = những người đã nghỉ **trong** kỳ. Ngoài ra **895 người nghỉ trước kỳ**
luôn bị loại ở cả hai chế độ.

---

## 3. Giới hạn theo `Attendance Calculation Setting`

Panel dùng lại **đúng phạm vi nhân viên mà engine chấm công dùng**, lấy từ
`Attendance Calculation Setting`. Luôn áp, ở cả hai trạng thái checkbox, không tắt được:

| Field trong setting | Tác dụng | Giá trị hiện tại |
|---|---|---|
| `Employee ID Prefix` | chỉ nhận nhân viên có mã bắt đầu bằng tiền tố này | `TIQN` |
| `Exclude Employee IDs` | loại hẳn các mã liệt kê | `TIQN-1080, TIQN-2039, Test-9999` |

Vì sao: `Exclude Employee IDs` là nhân sự **công ty khác làm tại nhà máy** — họ quẹt thẻ như mọi
người nhưng không thuộc mình để quản lý — cộng với các record test còn sót.

**Đang bị loại vì tiền tố `TIQN`:** 17 thực tập sinh `Intern-0001` → `Intern-0017`
(vào 25/05/2026, nghỉ 11/07/2026). Họ có **0 Attendance và 0 Leave Application**, tức engine
chấm công vốn đã không xử lý họ — nay panel nhất quán với engine.

> ⚠ Nếu công ty muốn thực tập sinh **có** phép năm, đừng sửa code — hãy đổi
> `Employee ID Prefix` trong setting, hoặc đổi mã nhân viên của họ sang tiền tố `TIQN`.
> Nhưng nhớ là đổi tiền tố sẽ ảnh hưởng **cả engine chấm công**, không chỉ panel này.

---

## 4. Các bộ lọc còn lại

Áp **thêm** (AND) vào điều kiện ở trên. Bỏ trống = không lọc.

| Loại | Field |
|---|---|
| Quick Filters | Company · Branch · Department · Employment Type · Designation · Employee Grade |
| Advanced Filters | tự chọn field bất kỳ trên Employee |

Và một bộ lọc **tự động luôn chạy, không tắt được**:

> **Đã có Leave Allocation trong kỳ này thì không hiện ra nữa.**

Nó xét allocation đã `Submitted`, có thời gian giao với kỳ, thuộc các Leave Type của Leave Policy
bạn chọn. Nhờ vậy bấm `Allocate Leave` nhiều lần **không** tạo phép trùng.

*(Thấy một người vẫn hiện ra dù nghĩ đã cấp phép cho họ? Kiểm tra allocation đó còn `Submitted`
không, hay đã bị Cancel/Delete.)*

---

## 5. Khi `Allocate Leave` báo lỗi hàng loạt

```
Leave Policy: HR-LPOL-... already assigned for Employee ... for period ... to ...
```

Nghĩa là **đã có `Leave Policy Assignment`** cho người đó trong kỳ này.

Bộ lọc tự động ở mục 4 chỉ loại người đã có **Leave Allocation**, nó **không** biết tới
`Leave Policy Assignment`. Nên nếu allocation đã bị xoá mà LPA còn sót lại thì panel vẫn hiện
đủ người, và bấm `Allocate Leave` là lỗi toàn bộ.

**Cách xử lý:** xoá các `Leave Policy Assignment` của kỳ đó rồi làm lại. Có script sẵn:
`scripts/reset_leave_allocation.sql`.

> Sự cố thật 17/08/2026: xoá allocation nhưng giữ 1.518 LPA → 1.496 dòng Error Log
> *"Leave Policy Assignment failed for employee ..."*, không tạo được bản phân bổ nào.

---

## 6. Nhân viên bị thiếu trong danh sách?

| Triệu chứng | Nguyên nhân thường gặp |
|---|---|
| Người đã nghỉ việc không hiện | chưa tick checkbox ở mục 2 |
| Đã tick mà vẫn không hiện | `status = Left` nhưng **thiếu `Relieving Date`** → không biết họ có làm trong kỳ hay không nên bị loại. Điền `Relieving Date` là xong |
| Người còn làm việc không hiện | đã có Leave Allocation trong kỳ (mục 4), hoặc bị Quick/Advanced Filters lọc mất |
| Cả một nhóm không hiện | mã nhân viên không bắt đầu bằng `Employee ID Prefix`, hoặc nằm trong `Exclude Employee IDs` (mục 3) |

---

## Dành cho người sửa code

- Code override: [`leave_control_panel.py`](leave_control_panel.py) — thay
  `LeaveControlPanel.get_employees` + `get_filters`, thêm helper `_get_period_start_for_left_filter`
- Monkey patch: [`__init__.py`](__init__.py) — phải giữ `frappe.whitelist()` khi gán đè
  `get_employees`, nếu không client gọi `run_doc_method` sẽ lỗi
- Custom field: `patches/add_leave_control_panel_include_left.py`
- JS: `public/js/custom_scripts/leave_control_panel.js` (đăng ký ở `hooks.py` → `doctype_js`)
- **Sửa Python hoặc `hooks.py` phải `bench restart`**, clear-cache không đủ

Năm điểm dễ sai:

1. `get_filters()` **phải để `include_left` là tham số có default `False`** — HRMS gọi nó ở chỗ
   khác mà không truyền tham số, và default `False` = giữ `status = Active` (hành vi gốc).
2. `filters` chỉ AND được, nên điều kiện *"chưa nghỉ HOẶC nghỉ sau From Date"* phải dùng
   `or_filters` (được AND với `filters`, OR lẫn nhau).
3. Chế độ `Joining Date` **không có `from_date`** → phải lấy `Leave Period.from_date` làm mốc cho
   bộ lọc `relieving_date`, nếu không mọi nhân viên từng tồn tại đều hiện ra (đo được **2.411**
   thay vì 1.496).
4. So sánh `status` phải `.strip()` — dữ liệu có bản ghi mang `"Left "` (dấu cách cuối) và so
   chuỗi tuyệt đối sẽ để nó lọt lưới.
5. HRMS khai handler JS cho **từng** field lọc để gọi `frm.trigger("get_employees")`. Custom
   field mới **phải** có handler riêng, nếu không tick vào mà danh sách không đổi — HR sẽ tưởng
   checkbox không có tác dụng.

Bộ lọc theo `Attendance Calculation Setting` (`_attendance_setting_filters()`) dùng lại
`get_attendance_settings()` + `get_excluded_employee_ids()` — **đừng tự viết tiêu chí mới**,
để panel và engine chấm công không bao giờ lệch phạm vi nhân viên.

Phần loại người đã có allocation (`get_employees_without_allocations`) là của HRMS,
**không override** — đừng viết lại.
