# Đơn nghỉ việc — `Resignation Application`

> **Mục đích:** thay việc HR sửa tay trực tiếp trên Employee bằng một lá đơn có vòng đời.
> **Phạm vi:** DocType `Resignation Application` · `Resignation Reason Group` · `Resignation Reason Group 2`
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-21

---

## 1. Vấn đề

Trước đây HR mở hồ sơ Employee rồi sửa thẳng `status`, `relieving_date`, `reason_for_leaving`.
Không có đơn, không biết ai nhận đơn ngày nào, không có chỗ ghi bàn giao, và **không có khái niệm
rút đơn**. 1.389 người đã nghỉ, riêng 2026 là 490 — khoảng 40 đơn/tháng.

## 2. Vì sao không override `Employee Separation` của HRMS

| | |
|---|---|
| Dữ liệu | `Employee Separation` **0 record**, `Employee Separation Template` **0**, `Exit Interview` **0** — không có gì để giữ |
| Nó làm gì khi submit | `EmployeeBoardingController.on_submit` tạo một **Project** rồi một **Task cho mỗi activity**, assign user/role, gửi mail |
| Child table | `Employee Boarding Activity` mang `task_weight`, `begin_on`, `duration`, `role` — nặng hơn nhiều so với "chỉ cần checkbox" |
| Thiếu hẳn | Không đụng `relieving_date`, không đổi `status`, **không có rút đơn**, không có ngày nhận đơn |

Override sẽ phải vô hiệu hoá `on_submit`, `on_cancel`, `create_task_and_notify_user`,
`get_holiday_list`, `get_task_dates` — chỉ còn giữ lại cái vỏ tên.

`Employee Separation` **giữ nguyên**, không đụng tới.

## 3. Vòng đời

```
Draft      HR đang nhập
Submitted  đã duyệt   -> ghi relieving_date + lý do sang Employee
Cancelled  ĐÃ RÚT ĐƠN -> hoàn nguyên Employee (nút Withdraw)
```

Nộp lại sau khi rút: tạo đơn mới bình thường (đơn đã cancel không chặn đơn mới).

## 4. 🔴 `relieving_date` là ngày BẮT ĐẦU nghỉ việc

Ngày **đầu tiên không còn đi làm**, KHÔNG phải ngày làm việc cuối cùng. Toàn bộ code trong app
hiểu như vậy:

- `shift_type_optimized.py:979` — không đánh Absent khi `relieving_date <= ngày đang xét`
- `shift_type_optimized.py:2392` — bước dọn xoá chấm công **từ** `relieving_date` trở đi

Hiểu lệch một ngày ở đây là lệch một công.

## 5. 🔴 Ngày nghỉ ở TƯƠNG LAI thì duyệt đơn KHÔNG đổi `Employee.status`

`Employee.status = 'Left'` là công tắc cả hệ thống đang đọc:

| Đọc nó | Hệ quả nếu đổi sớm |
|---|---|
| `shift_type_optimized.py` | ngừng sinh chấm công |
| `api/biometric_sync.py:585` | xếp vào diện **xoá vân tay khỏi máy** |
| `api/hr_overview_cards.py` | headcount trừ ngay |

Duyệt đơn 01/09 cho ngày nghỉ 30/09 mà đổi status luôn thì 29 ngày còn lại **mất công, mất lương,
mất vân tay** — trong khi người ta vẫn đang đi làm.

Nên:

| Ngày nghỉ | Duyệt đơn làm gì |
|---|---|
| Còn ở tương lai | ghi `relieving_date` + lý do. `status` để job 00:00 đặt đúng vào ngày nghỉ |
| Đã qua / hôm nay | ghi luôn **và chuyển `Left` ngay**, không đợi nửa đêm |

Ngoại lệ thứ hai có vì lý do phải đợi không còn đúng nữa (không còn ngày công nào để mất), và bắt
HR nhập đơn lùi ngày rồi chờ tới hôm sau mới thấy đúng trạng thái là vô nghĩa.

**Cả hai đường gọi cùng một hàm** `overrides/employee/employee.py::mark_employee_left()`.

## 5b. Sửa ngày nghỉ SAU khi duyệt — đồng bộ MỘT CHIỀU

Hai bên vẫn có thể thoả thuận lại ngày nghỉ sau khi đơn đã duyệt, nên `relieving_date` để
`allow_on_submit` (kèm `notice_days` vì nó là dẫn xuất). Mỗi lần sửa là đẩy thẳng sang Employee.

**Đơn là nguồn, Employee là bản sao. Không có chiều ngược lại** — phải có đơn trước rồi mới có
ngày nghỉ trên hồ sơ. HR sửa tay `Employee.relieving_date` thì đơn **không** đổi theo, và lần sửa
đơn kế tiếp sẽ ghi đè lại. Hiện chưa chặn thao tác sửa tay đó.

⚠ Frappe **không chạy `validate()`** trên đường update-after-submit, chỉ chạy
`before_update_after_submit` / `on_update_after_submit`. Không lặp lại phần kiểm ngày ở
`before_update_after_submit` thì sửa ngày sau khi duyệt sẽ đi thẳng vào DB mà không qua kiểm tra
nào.

### `_reconcile_status()` — bất biến `status = Left` ⟺ ngày nghỉ đã tới

Vì ngày sửa được nên trạng thái phải đối chiếu theo **cả hai hướng**:

| Ngày nghỉ sau khi sửa | Hành động |
|---|---|
| đã tới / đã qua, đang `Active` | chuyển `Left` ngay |
| lùi ra tương lai, đang `Left` | **mở lại `Active`** (kèm mở khoá User) |

Hướng thứ hai là lý do phải có hàm này: người đã bị đánh `Left` rồi hai bên thoả thuận lùi ngày
ra — không mở lại thì những ngày còn đi làm đó **không sinh chấm công** (`shift_type_optimized`
bỏ qua NV `Left`) và họ nằm trong diện xoá vân tay khỏi máy.

### Field trên Employee mà đơn làm chủ

```
resignation_letter_date            <- resignation_letter_date      (field CÓ SẴN của core)
relieving_date                     <- relieving_date
custom_reason_for_leaving_group    <- reason_for_leaving_group
custom_reason_for_leaving_group_2  <- reason_for_leaving_group_2
reason_for_leaving                 <- reason_detail
```

Danh sách này nằm ở `_employee_values()` và được `revert_employee()` dùng lại khi rút đơn — thêm
field vào đó là tự động có cả hai chiều ghi/hoàn nguyên. `resignation_letter_date` map thẳng vào
field core thay vì khai thêm custom field, vì ý nghĩa trùng khít (HRMS `Employee Separation` cũng
dùng đúng tên này).

## 6. Job 00:00 — ba lỗi đã sửa (21/08/2026)

`auto_mark_employees_as_left` đã tồn tại từ trước và là bước thứ hai của luồng này.

1. **Thiếu điều kiện `status = 'Active'`.** Bộ lọc chỉ có `relieving_date <= today` -> 1.388 nhân
   viên khớp và **cả 1.388 đã là `Left`**: mỗi đêm 1.388 câu UPDATE vô ích, kèm
   `update_modified=True` nên **bump `modified` của 1.388 Employee mỗi đêm**. Nặng hơn: HR mở lại
   một người thành `Active` mà `relieving_date` còn đó thì đêm sau bị ép `Left` trở lại, **im
   lặng**.
2. **`frappe.utils.today()`.** Job chạy đúng 00:00 mà `System Settings.time_zone` site này nhiều
   lần tự nhảy về `Asia/Kolkata` -> lệch một ngày so với `CURDATE()` đúng trong khung 00:00-01:30.
   Nay dùng `business_today()`.
3. **Bỏ qua hai việc của core:** kiểm nhân viên còn cấp dưới `Active` (`reports_to`), và khoá
   tài khoản `User`. Nay gọi tường minh cả hai.

### 🔴 Cái giá của điều kiện `status = 'Active'` (26/08/2026)

Lỗi 1 ở trên sửa đúng, nhưng đổi lại: **job này chỉ đánh `Left` cho người đang `Active`.** Ai đang
`Inactive` thì tới ngày nghỉ việc vẫn **không bao giờ** được chuyển sang `Left` — và
`Inactive` chính là trạng thái của **người đang nghỉ thai sản**
(`employee_status_sync.py`). Trên site còn 17 `Intern-000x` `Inactive` + `relieving_date` quá hạn,
nằm đúng vào lỗ này.

**Quyết định 26/08: giữ nguyên `status = 'Active'`, không nới ra cho `Inactive`** — nới ra là mở
lại đúng cái bẫy "HR mở lại người thành `Active`/`Inactive` rồi đêm sau bị ép `Left` trở lại".
Bên nào cần biết "đã nghỉ việc chưa" thì **tự đọc `relieving_date`**, đừng tin `status == 'Left'`:

```python
# customize_erpnext/doctype/employee_maternity/employee_maternity.py
def _has_left(relieving_date, employee_status, on_date): ...
```

⚠ Hệ quả cho mọi code kiểm tra nghỉ việc bằng Python: **`Employee.status` trong DB là `"Left "` —
có dấu cách ở cuối, 1.393 bản ghi.** MySQL so sánh kiểu PAD SPACE nên `WHERE status = 'Left'` vẫn
khớp và không ai phát hiện ra, nhưng `"Left " == "Left"` trong Python là **False**. Phải `.strip()`.
`mark_employee_left()` cũng so trần như vậy — hiện vô hại vì job đã lọc `status='Active'` ở SQL
trước khi tới, nhưng đừng sao chép mẫu đó đi chỗ khác.

### ⚠ Vì sao KHÔNG dùng `doc.save()`

Đường hiển nhiên là `doc.save()` để core tự validate. **Đã thử và phải bỏ**: save một Employee là
validate lại toàn bộ ~200 field cùng mọi child table, kể cả dữ liệu nhập từ nhiều năm trước — và
trên site này dữ liệu đó **không sạch**. Hai ca gặp thật:

```
Driving License cannot be "0". It should be one of "", "Có", "Không"
Row #1: Level cannot be "Graduate". It should be one of "", "THCS", "THPT", ...
```

Đo 21/08/2026: ca `custom_driving_license = '0'` từng dính **1.980 hồ sơ (796 đang Active)**, nay
đã được dọn còn 0. Ca `Employee Education.level` ngoài danh sách vẫn còn **230 hồ sơ**.

Điểm cốt lõi không phải con số cụ thể mà là: `save()` biến "đánh dấu một người đã nghỉ" thành
"phải làm sạch toàn bộ hồ sơ người đó trước đã". Job sẽ **im lặng bỏ sót** đúng những người có hồ
sơ cũ nhất, chỉ để lại Error Log không ai đọc. Một lá đơn nghỉ việc không phải là lúc bắt người ta
dọn dữ liệu 5 năm trước.

### Còn cấp dưới `Active` thì bỏ qua, KHÔNG báo lỗi

Đây là việc HR phải xử lý (chuyển cấp dưới sang người quản lý khác), không phải lỗi kỹ thuật —
nên vào danh sách `skipped`, không ghi Error Log. Job thử lại mỗi đêm.

## 7. Danh mục lý do — HR tự quản

`Resignation Reason Group` + `Resignation Reason Group 2` thay cho
`public/js/custom_scripts/employee_reason_for_leaving.json` (đã xoá) và ~95 dòng JS đọc file đó.

Hai field trên Employee đổi từ `Select` (options rỗng, bơm bằng JS) sang `Link`:

```
custom_reason_for_leaving_group    -> Resignation Reason Group
custom_reason_for_leaving_group_2  -> Resignation Reason Group 2   (depends_on nhóm)
```

- Tên bản ghi **chính là** giá trị (`autoname: field:reason_for_leaving_group_2`), vì giá trị này
  ghi thẳng vào Employee. Hệ quả: `reason_for_leaving_group_2` phải duy nhất **toàn danh mục**, hai nhóm không thể cùng có "Vấn đề
  khác". Đánh đổi có chủ ý — tên bản ghi đọc được bằng tiếng Việt đáng giá hơn.
- `is_active` để **ẩn khỏi ô chọn** trên bản ghi mới mà không mất dữ liệu cũ. Đó là lý do có cờ
  này thay vì xoá bản ghi; `on_trash` cũng chặn xoá lý do đang được dùng.

## 7b. 🚧 `Notice Days` — tạm ẩn, chờ Labor Contract

Field vẫn được tính và lưu, nhưng **ẩn trên form** và **cảnh báo đã tắt** (`NOTICE_CHECK_ENABLED
= False`).

Lý do: BLLĐ 2019 Điều 35 đặt **hai** ngưỡng — 30 ngày với HĐ xác định thời hạn, 45 ngày với HĐ
không xác định thời hạn. Biết áp ngưỡng nào thì phải đọc loại hợp đồng đang hiệu lực, mà đó là
việc của module `Labor Contract` (hook tạo hợp đồng đầu tiên hiện còn tắt trong `hooks.py`).

Cảnh báo bằng một ngưỡng cứng 30 ngày sẽ **báo sai cho toàn bộ người ký HĐ không xác định thời
hạn** — dạy HR bỏ qua cảnh báo, tệ hơn là không cảnh báo.

Vẫn tính và lưu giá trị để khi bật lại không có khoảng trống dữ liệu trên các đơn nhập trong thời
gian này.

**Khi bật lại:** bỏ cờ, và thay `MIN_NOTICE_DAYS` cứng bằng ngưỡng tra từ
`Labor Contract.contract_type`.

## 7c. Link ngược trên Employee — `custom_resignation_application`

Custom Field **virtual** (`is_virtual = 1`, không có cột trong DB) kiểu `Link` trỏ tới đơn nghỉ
việc **đã duyệt**. Giá trị do property `CustomEmployee.custom_resignation_application` trả về
(`overrides/employee/employee_override.py`).

Frappe ưu tiên `@property` trên class controller trước khi thử `safe_eval` trên `options`
(`frappe/model/base_document.py:541`). Với field kiểu `Link` thì `options` đã dùng để chỉ doctype
đích, nên **bắt buộc** phải đi đường property.

| Trạng thái đơn | Employee thấy gì |
|---|---|
| chưa có đơn | trống |
| Draft | trống — chưa duyệt thì chưa có gì để hiện |
| Submitted | tên đơn |
| Cancelled (đã rút) | trống trở lại |

Vì sao virtual chứ không phải cột thật ghi lúc submit:

1. **Không bao giờ lệch.** Rút đơn / xoá đơn / amend — link tự đúng theo `docstatus`. Cột thật thì
   mỗi đường thoát là một chỗ phải nhớ dọn.
2. **Không đụng vào Employee.** Cột thật nghĩa là mỗi lần submit/cancel lại `set_value` lên hồ sơ
   nhân viên, kéo theo `modified` và cache — trong khi thông tin này vốn suy được.

⚠ Đánh đổi: **không lọc / không sắp xếp / không đưa vào report được**, vì không có cột. Cần lọc
theo đơn thì query thẳng `Resignation Application`.

### 🔴 Field này CHỈ hoạt động sau `bench restart` — trước đó nó làm 500 cả form Employee

Đã xảy ra thật 21/08/2026. Nhánh dự phòng của Frappe khi **không tìm thấy property** là đem
`options` đi `safe_eval` như mã Python (`base_document.py:545`). Với field `Link` thì `options` là
tên doctype, nên nó đi `ast.parse("Resignation Application")`:

```
File "<unknown>", line 1
    Resignation Application
                ^^^^^^^^^^^
SyntaxError: invalid syntax
```

Lỗi này bung ra ngay trong lúc **serialise document**, tức là trước khi Frappe kịp dựng JSON —
trình duyệt nhận một trang HTML 500 và báo `SyntaxError: Unexpected token '<'`. Mọi thao tác
đọc/ghi Employee đều chết, không riêng gì phần nghỉ việc.

Vì sao xảy ra: worker đang chạy vẫn giữ bản `employee_override.py` nạp từ **trước** khi có
property, trong khi Custom Field đã được tạo bằng `bench migrate` (migrate **không** restart
worker). Tạo field và nạp property là hai việc phải xảy ra cùng lúc.

### ⚠ `doc.get("custom_resignation_application")` LUÔN trả `None`

`Document.get()` đọc `self.__dict__`, không chạm tới property — nên với field ảo nó luôn rỗng.
Đọc đúng cách:

```python
getattr(emp, "custom_resignation_application")   # property
emp.as_dict()["custom_resignation_application"]  # đường form desk / savedocs đi qua
emp.get("custom_resignation_application")        # ❌ luôn None
```

Không phải lỗi — chỉ là đừng dùng `.get()` rồi kết luận field hỏng.

**Quy tắc: tạo Custom Field virtual xong thì `bench restart` NGAY.** Nếu chưa restart được thì
đừng tạo field — gỡ nó ra đã (`patches/add_employee_resignation_link.py` chạy lại là có lại,
idempotent).

Cùng lý do: **đừng `bench migrate` trước khi restart** sau khi kéo code mới về — fixture sẽ dựng
lại field trong khi worker vẫn chạy code cũ.

## 7g. Nghỉ đúng ngày vào làm — cho phép

`relieving_date == date_of_joining` là **hợp lệ**: người vào làm rồi bỏ ngay hôm đó. Chỉ chặn khi
ngày nghỉ **trước** ngày vào làm.

Bản đầu dùng `<=` nên chặn cả ca này — 3 hồ sơ trong file import thật của HR (TIQN-1502,
TIQN-1531, TIQN-1997). Cũng khớp với core: `Employee.validate_date` dùng `validate_from_to_dates`
vốn cho phép hai ngày bằng nhau.

Sau khi nới cả hai luật, thử nạp lại toàn bộ 1.387 dòng: **1.385 lưu được, còn 2** — và 2 dòng đó
là dữ liệu sai thật (ngày nghỉ trước ngày vào làm cả tháng).

## 7f. Ngày nhận đơn có thể SAU ngày nghỉ

`resignation_letter_date > relieving_date` là **hợp lệ**, chỉ cảnh báo. Quá
`MAX_LATE_LETTER_DAYS = 30` ngày thì mới chặn.

Vì sao: nghỉ ngang là chuyện thường ở xưởng — người ta thôi đến làm, HR chờ một hai hôm rồi mới
ra quyết định. Ngày nghỉ có trước, giấy tờ có sau.

Đo trên file import thật của HR (`Resignation Application.xlsx`, 1.387 dòng):

| Đơn lập sau ngày nghỉ | Số dòng |
|---|---|
| 1 ngày | 68 |
| 2 ngày | 33 |
| 3 ngày | 11 |
| 4–14 ngày | 13 |
| **tổng** | **125** |

Nhóm này lệch hẳn về lý do so với phần còn lại: dẫn đầu là "Không phù hợp với môi trường làm
việc" (31%) và "Lý do cá nhân" (23%), có cả "Tự ý bỏ việc" và "Nghỉ quá 5 ngày không phép" —
đúng chân dung nghỉ ngang.

Bản đầu `throw` thẳng nên chặn cả 125 dòng đó, **và** chặn luôn ca hai bên thoả thuận lùi ngày
nghỉ về trước hôm nhận đơn.

⚠ Vẫn giữ mốc 30 ngày chứ không bỏ hẳn: bỏ hẳn là mất khả năng bắt gõ nhầm năm (nhận đơn 2026,
nghỉ 2025). 30 ngày phủ trọn dữ liệu thật (xa nhất 14 ngày) mà vẫn bắt được loại sai đó.

`notice_days` khi đó **âm** — đúng nghĩa: không có ngày báo trước nào.

## 7e. Mục Bàn giao

6 checkbox + ghi chú + **file đính kèm** (`handover_attachment`, kiểu `Attach`) cho biên bản bàn
giao đã ký hoặc ảnh chụp. Cần nhiều hơn một file thì dùng mục **Attachments** ở thanh bên —
doctype không giới hạn số lượng.

⚠ **Mọi field trong mục này phải `allow_on_submit`**, kể cả file đính kèm: việc trả thẻ / trả
đồng phục / ký biên bản diễn ra vào những ngày làm việc cuối, tức là **sau** khi đơn đã duyệt.
Thêm field mới vào mục này mà quên cờ đó thì HR không nhập được — test có assert quét toàn bộ
field bắt đầu bằng `handover`.

`handover_progress` ("4/6") do `set_handover_progress()` tính lại mỗi lần lưu, kể cả trên đường
update-after-submit.

## 7c-bis. Danh mục cũng dùng CHUNG bộ tên

Sau đợt rename 21/08, **mọi nơi giữ một giá trị từ `Resignation Reason Group` đều tên
`reason_for_leaving_group`**, và từ `Resignation Reason Group 2` đều tên
`reason_for_leaving_group_2`:

| Bảng | Field nhóm | Field lý do |
|---|---|---|
| `Employee` | `custom_reason_for_leaving_group` | `custom_reason_for_leaving_group_2` |
| `Resignation Application` | `reason_for_leaving_group` | `reason_for_leaving_group_2` |
| `Resignation Reason Group 2` | `reason_for_leaving_group` | `reason_for_leaving_group_2` |

Không chỉ cho đẹp: trước đây khoá filter (`reason_group`, field của danh mục) **khác tên** với vế
phải (`reason_for_leaving_group`, field của đơn), nên tìm-thay hàng loạt đổi nhầm **hai lần liền**
và sinh `Unknown column ... in 'WHERE'`. Cùng tên thì cái bẫy đó biến mất — `set_query` giờ đọc là
`{reason_for_leaving_group: frm.doc.reason_for_leaving_group}`.

Qua `patches/rename_resignation_reason_fields.py`, cùng khuôn với patch rename của đơn.

## 7d. Tên field khớp với Employee

Đổi tên 21/08/2026 để HR đọc hai màn hình thấy cùng một thứ tiếng:

| Trước | Nay | Đối chiếu trên Employee |
|---|---|---|
| `posting_date` | `resignation_letter_date` | `resignation_letter_date` (field core) |
| `reason_group` | `reason_for_leaving_group` | `custom_reason_for_leaving_group` |
| `reason` | `reason_for_leaving_group_2` | `custom_reason_for_leaving_group_2` |

Bỏ tiền tố `custom_` vì đây là doctype của chính app — `custom_` chỉ dành cho Custom Field cắm
vào doctype lõi.

⚠ **`reason_group` vẫn tồn tại** — đó là field của doctype **danh mục** `Resignation Reason Group 2`
(nhóm mà một lý do thuộc về), không phải field của đơn. Hai cái trùng ý nghĩa nhưng khác bảng.
Tìm-thay hàng loạt là đổi nhầm ngay: `frm.set_query('reason_for_leaving_group_2', {filters:
{reason_group: ...}})` — khoá filter là field của danh mục, vế phải mới là field của đơn.

⚠ Đổi `fieldname` trong JSON rồi `migrate` suông thì schema sync **tạo cột mới rỗng và bỏ lại dữ
liệu ở cột cũ**, im lặng. Phải qua `patches/rename_resignation_application_fields.py`
(`frappe.model.rename_field`, chạy ở **post_model_sync** vì nó cần field mới đã có trong meta và
cột cũ còn trong bảng). `rename_field` **không xoá** cột cũ — patch tự xoá, và chỉ xoá sau khi đối
chiếu số dòng khớp.

⚠ File Data Import cũ dùng tiêu đề cột **Posting Date** sẽ không còn khớp — đổi thành
**Resignation Letter Date**.

## 8. Bẫy khi sửa

1. **Frappe chặn đổi fieldtype `Select` -> `Link`** (`custom_field.py:198`,
   `ALLOWED_FIELDTYPE_CHANGE` không có cặp này). Patch ghi thẳng bằng `db.set_value`. An toàn có
   kiểm chứng: hai kiểu **cùng cột `varchar(140)`**, và mọi giá trị đang có đều đã được tạo thành
   bản ghi danh mục **trước** khi đổi. Không chọn đường xoá rồi tạo lại Custom Field vì `on_trash`
   xoá luôn mọi Property Setter của field.
2. **fixtures nạp SAU patch và thắng.** Đã xảy ra thật khi làm việc này: patch đổi xong hai field
   sang `Link`, rồi `fixtures/custom_field.json` (còn ghi `Select`) lật ngược lại ngay trong cùng
   một lần `migrate`. Sửa xong **phải** `bench export-fixtures --app customize_erpnext`.
3. **Workspace: đừng `doc.save()`.** Site đang `developer_mode = 1`, save Workspace `HR Setup`
   (module `HR`) sẽ ghi đè file JSON trong repo `apps/hrms`. Chèn thẳng vào `tabWorkspace Link`.
4. **Bộ đếm `tabSeries` tiền tố `RA-YYYY-MM-`.** Mất dòng đó là đơn mới phát lại từ `00001` và
   đụng tên đã tồn tại (`DuplicateEntryError`) — đúng sự cố đã xảy ra với Leave Application. Xem
   `scripts/repair_leave_application_series.sql`. **Đừng bao giờ** dọn test bằng
   `delete from tabSeries`.
5. **Số đơn phát ra ở lần lưu ĐẦU TIÊN.** Sửa `resignation_letter_date` sau đó không đổi tên bản ghi. Field
   có description nhắc, JS cũng cảnh báo khi sửa trên bản đã lưu.
6. **`validate_reason` là chốt chặn thật.** JS chỉ lọc hiển thị; Data Import và API không đi qua JS.
7. **Rút đơn chỉ xoá field còn đúng giá trị đơn đó đã ghi.** HR sửa tay sau khi duyệt, hoặc một
   đơn mới hơn đã ghi đè, thì xoá mù sẽ thổi bay dữ liệu của người khác.
8. **Đơn cho người đã `Left` bị chặn** (`validate_employee_state`). Muốn nhập bù hồ sơ cũ cho
   1.389 người đã nghỉ thì phải nới điều kiện này — chưa làm.

## 9. File

```
customize_erpnext/doctype/resignation_application/
├── resignation_application.json / .py / .js / _list.js
├── test_resignation_application.py      # 39 assert, 8 phần
└── resignation_application.md
customize_erpnext/doctype/resignation_reason_group/
customize_erpnext/doctype/resignation_reason/
patches/add_resignation_reason_catalogue.py
overrides/employee/employee.py           # mark_employee_left · restore_employee_active · job 00:00
```

⚠ Sửa Python -> **`bench restart`**. Sửa doctype/fixture -> **`bench migrate`**.
