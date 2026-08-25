# Employee Promotion / Employee Transfer — override

Hai doctype này dùng chung `hrms/hr/employee_property_update.js`. Override ở đây làm 2 việc:

1. **Giới hạn field** — dialog "Add Employee Property" chỉ còn 6 field tổ chức thay vì
   ~80 field của Employee.
2. **Cho phép nhập/import dữ liệu quá khứ** — bỏ các chốt chặn của HRMS và dựng lại
   `Employee.internal_work_history` thay vì append vào nó.

## File

| File | Việc |
|---|---|
| `public/js/custom_scripts/employee_property_update_override.js` | allow-list 6 field + nới `set_query` employee |
| `work_history.py` | allow-list phía server, autofill, dựng lại timeline, `audit()`, `repair_missing_fieldnames()` |
| `employee_promotion.py` / `employee_transfer.py` | `override_doctype_class` |
| `test_regression.py` | 35 assert, chạy tay, tự rollback |
| `customize_erpnext/report/employee_transfer_and_promotion/` | Report gộp 2 doctype |
| `overrides/employee/employee.py::sync_fetch_from_fields()` | đồng bộ field `fetch_from` toàn site |
| `template_employee_{transfer,promotion}.csv` | file mẫu Data Import |

## 6 field được phép đổi

`department`, `custom_section`, `custom_group`, `designation`, `reports_to`, `employment_type`

Danh sách nằm ở 2 chỗ và **phải khớp nhau**: `ALLOWED_FIELDS` (work_history.py) và
`ALLOWED_PROPERTY_FIELDS` (file JS). Server chặn thật, JS chỉ lọc dropdown.

`grade` **không** nằm trong danh sách vì nó là field read-only dẫn xuất từ
`designation.custom_grade`. Nó được `_apply_fetch_from()` tính lại mỗi lần rebuild, cùng
với `custom_designation_vietnamese` — xem mục Bẫy về `fetch_if_empty`.

## Cờ `ENFORCE_EFFECTIVE_DATE_NOT_FUTURE` (work_history.py)

Điều khiển thời điểm được gửi hồ sơ:

| Giá trị | Hành vi |
|---|---|
| `True` (mặc định) | Luật HRMS gốc: chỉ Submit được vào **đúng ngày hoặc sau** Transfer Date / Promotion Date. Phiếu ghi ngày tương lai bị chặn. |
| `False` | Submit được cả phiếu ghi **ngày tương lai** — dùng khi cần lên phiếu trước. |

Cài đặt bằng cách gọi `super().before_submit()` hay không, nên khi bật là **đúng y
nguyên** code HRMS, không phải bản chép lại.

⚠ Đặt `False` thì phiếu ngày tương lai **ăn vào Employee master ngay lúc submit**, chứ
không đợi tới ngày ghi trên phiếu: rebuild luôn lấy giá trị của sự kiện có ngày mới nhất.

⚠ Nhập dữ liệu **quá khứ không cần đụng tới cờ này** — HRMS vốn chỉ chặn ngày tương lai.

## Vì sao phải dựng lại timeline thay vì append

`hrms/hr/utils.py`:

- `update_employee_work_history` (dòng 84) làm `setattr(employee, fieldname, item.new)`
  vô điều kiện → import 1 lệnh thuyên chuyển năm 2023 sẽ **ghi đè phòng ban hiện tại**
  bằng giá trị 3 năm trước. Chỉ import đúng thứ tự thời gian mới sống sót.
- Dòng seed (utils.py:65-74) đóng dấu giá trị của employee **tại thời điểm submit đầu
  tiên** cộng với `date_of_joining` → backfill sẽ mở đầu timeline bằng phòng ban mới
  nhất gán cho ngày vào làm.
- `delete_employee_work_history` (utils.py:129) huỷ bằng `frappe.db.delete` với dict
  filter dựng lỏng → có thể xoá nhầm dòng của doc khác.

Override tính lại toàn bộ từ **mọi doc đã submit**, sắp theo ngày. Kết quả không phụ
thuộc thứ tự import và chạy lại bao nhiêu lần cũng ra một kết quả.

## Import dữ liệu quá khứ

Dùng **Data Import** chuẩn của Frappe. File chỉ cần 4 cột:

```csv
employee,transfer_date,transfer_details.fieldname,transfer_details.new
TIQN-0001,2023-04-01,department,Sewing - TIQN
,,custom_group,Line 3
TIQN-0001,2024-07-15,designation,Team Leader
TIQN-0002,2024-01-10,department,Cutting - TIQN
```

- 1 nhân viên đổi nhiều field trong **cùng một lần** → dòng thứ 2 trở đi **để trống**
  `employee` và `transfer_date`.
- Cột khoá là `transfer_details.fieldname`. Nếu file chỉ có cột `Property` (label) thì
  override tự map ngược về fieldname — xem mục Bẫy.
- **Không cần** cột `property` và `current` — override tự điền: `property` lấy label của
  field, `current` lấy giá trị field đó **ngay trước ngày của doc**, suy ra từ các doc
  khác đã submit (không phải giá trị hôm nay).
- **Không cần** import đúng thứ tự thời gian.
- Bật **Submit After Import** trên Data Import, nếu không doc nằm ở Draft và
  `internal_work_history` chưa được dựng.
- File mẫu: `template_employee_transfer.csv`, `template_employee_promotion.csv`.

Promotion dùng `promotion_date` + `promotion_details.*`, cột `current_ctc` /
`revised_ctc` là tuỳ chọn.

### Import lớn (script)

Mỗi lần submit đều rebuild lại timeline của nhân viên đó (2 query + 1 lần save
Employee). Với vài nghìn dòng qua Data Import UI thì chấp nhận được. Nếu import bằng
script thì tắt rebuild rồi chạy một lượt cuối:

```python
frappe.flags.skip_work_history_rebuild = True
# ... tạo và submit toàn bộ doc ...
frappe.flags.skip_work_history_rebuild = False
```

```bash
bench --site erp.tiqn.local execute \
    customize_erpnext.overrides.employee_property.work_history.rebuild_all
```

`rebuild_all` commit từng nhân viên và in ra danh sách lỗi ở cuối, không dừng giữa chừng.

## Rà soát dữ liệu

```bash
bench --site erp.tiqn.local execute \
    customize_erpnext.overrides.employee_property.work_history.audit
# chỉ 1 doctype:  --kwargs "{'doctype': 'Employee Promotion'}"
# chỉ 1 nhân viên: --kwargs "{'employee': 'TIQN-0037'}"
```

Chỉ ĐỌC, không ghi. Bắt 6 loại lệch:

| Loại | Nghĩa |
|---|---|
| `no_property` | phiếu submit nhưng không dòng nào có `fieldname` → đổi 0 field |
| `master_mismatch` | giá trị hiện tại của Employee khác `new` của sự kiện mới nhất |
| `missing_row` | có đổi field thuộc work history nhưng không có dòng bắt đầu đúng ngày đó |
| `row_value` | dòng work history tại ngày đó mang giá trị khác `new` |
| `stale_current` | `current` trên phiếu mâu thuẫn với giá trị đang có hiệu lực lúc đó → 2 phiếu đá nhau |
| `timeline` | `to_date` không liền mạch, hoặc dòng cuối không khớp `relieving_date - 1` |

⚠ Mọi so sánh giá trị đi qua `same_value()` (bỏ qua hoa/thường). Đừng dùng `!=` trần:
MySQL đối chiếu không phân biệt hoa thường và Frappe nắn Link về tên canonical khi lưu,
nên file ghi `'Sub leader'` mà DB lưu `'Sub Leader'` là bình thường. Bản audit đầu tiên
dùng `!=` và báo nhầm 47/51 điểm.

## Report

**Employee Transfer and Promotion** (`customize_erpnext/report/employee_transfer_and_promotion/`)
— gộp cả 2 doctype, 1 dòng cho mỗi property thay đổi.

- Lọc: From/To Date (mặc định từ đầu năm tới hôm nay), Type (rỗng = cả hai), Employee, Status.
- Status rỗng = ẩn Cancelled nhưng **vẫn hiện Draft** — quan trọng khi đang import dở.
- Cột `Property` lấy nhãn chuẩn từ meta Employee theo `fieldname`, **không** đọc cột
  `property` của phiếu (nhãn do người import gõ tay, file cũ ghi sai `Desination`).
- `LEFT JOIN` cố ý: phiếu không có dòng con nào vẫn hiện, tô đỏ `no property`, thay vì
  biến mất khỏi report.

## Bẫy

- **`bench restart` bắt buộc.** Override nằm ở `hooks.py` (`doctype_js` +
  `override_doctype_class`); `bench build` / `clear-cache` không đủ. Chú ý: chạy bằng
  `bench execute` hay script python thì hooks được nạp mới nên override có hiệu lực
  ngay — dễ tưởng nhầm là web đã nhận.
- **1.386 nhân viên có `status = "Left "` (thừa 1 dấu cách).** Giá trị này rớt
  `validate_status()` của erpnext (chỉ nhận đúng `"Left"`), nên `rebuild_work_history`
  lưu Employee với `flags.ignore_validate = True`. `NestedSet.on_update` vẫn chạy nên
  đổi `reports_to` không làm hỏng `lft`/`rgt`. Đổi lại, `fetch_from` bị bỏ qua → `grade`
  được set tay trong `rebuild_work_history`. **Thêm field vào `ALLOWED_FIELDS` mà field
  đó có `fetch_from` thì phải xử lý tương tự.**
- **🔴 `fetch_if_empty` làm field dẫn xuất KHÔNG BAO GIỜ tự làm mới.** 3/4 field
  `fetch_from` trên Employee để cờ này, nên **kể cả Frappe bản gốc** cũng chỉ điền khi
  đang trống — thăng chức `QC Worker` → `QC Sub Leader` mà `custom_designation_vietnamese`
  vẫn đứng ở "Công nhân Kiểm hàng". `_apply_fetch_from()` cố ý bỏ qua cờ đó và tính lại
  mọi field có nguồn nằm trong `ALLOWED_FIELDS`:

  ```
  grade                         <- designation.custom_grade           (fetch_if_empty)
  custom_designation_vietnamese <- designation.custom_designation_vn  (fetch_if_empty)
  custom_probation_days         <- designation.custom_probation_days
  payroll_cost_center           <- department.payroll_cost_center     (fetch_if_empty)
  ```

  Hàm đọc thẳng từ meta nên thêm field dẫn xuất mới không phải sửa gì. **Nguồn rỗng thì
  giữ nguyên, không xoá trắng** — 16/115 Designation chưa điền `custom_designation_vn`,
  ép theo nguồn sẽ thổi bay tên tiếng Việt của người đang mang các chức danh đó.
- **`set_only_once` = chốt một lần, `_apply_fetch_from()` bỏ qua hẳn.**
  `custom_probation_days` để cờ này vì một người chỉ thử việc đúng một lần lúc vào làm —
  thăng chức về sau không được kéo số ngày thử việc của chức danh mới sang.
  ⚠ `set_only_once` **phải đi kèm `fetch_if_empty = 1`**: `_validate_links()` áp
  `fetch_from` ở `document.py:591`, **trước** `validate_set_only_once` (596). Thiếu nó
  thì mỗi lần đổi Designation, fetch ghi đè giá trị mới rồi `set_only_once` throw
  `CannotChangeConstantError` — Employee không lưu được nữa.
- **`Employee Internal Work History` cần 2 custom field** `custom_section` +
  `custom_group` (fixture `custom_field.json`). Thiếu chúng thì timeline mất 2 cấp tổ
  chức mà không báo lỗi.
- **Employee Transfer liên công ty giữ nguyên HRMS.** `create_new_employee_id = 1` hoặc
  `new_company != company` → gọi `super()`. Hai nhánh đó clone/relieve nhân viên và ghi
  lại `date_of_joining`, override không đụng vào.
- **`validate_active_employee` đã bị bỏ** ở Employee Promotion — cố ý, để ghi được bản
  ghi quá khứ cho người đang nghỉ thai sản (Inactive) hoặc đã nghỉ việc.
- **🔴 Cột `Property` KHÔNG phải khoá — `Field Name` mới là khoá.** Template Data Import
  xuất từ UI có cột `Property (Employee Transfer Detail)` và **không** có cột field name,
  nên mọi dòng nó tạo ra đều có `fieldname` rỗng: doc submit trót lọt mà **không đổi gì
  cả**, không một dòng lỗi. Sự cố 2026-08-25: 242 doc / 210 NV / 258 dòng đều rỗng
  `fieldname`. Nay `resolve_fieldname()` map label -> fieldname (không phân biệt hoa
  thường), và dòng nào không map được thì **throw** thay vì im lặng. Dữ liệu cũ sửa bằng:

  ```bash
  bench --site erp.tiqn.local execute \
      customize_erpnext.overrides.employee_property.work_history.repair_missing_fieldnames
  # thêm --kwargs "{'apply': True}" để ghi thật
  ```

  File import đó còn viết sai chính tả `Desination` (25 dòng) — đã ghi vào
  `PROPERTY_ALIASES`. Gặp label sai chính tả mới thì thêm vào đó.
- **`relieving_date` là ngày BẮT ĐẦU nghỉ việc, không phải ngày làm cuối.** `to_date`
  của dòng cuối = `relieving_date - 1`. Đo trên site: chỉ 6 NV có Attendance khác
  `Absent` đúng ngày `relieving_date`, so với 281 NV ở ngày trước đó. ⚠ HRMS gốc hiểu
  ngược (`salary_slip.py:141` tính trọn ngày `relieving_date`) — đừng bê sang đây.
- **`frappe.get_all` trên child table dùng `parent_doctype=`**, không phải `parent=`
  (frappe v16 đổi sang `qb_query.DatabaseQuery`).
