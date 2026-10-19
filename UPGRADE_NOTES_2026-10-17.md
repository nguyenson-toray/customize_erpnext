# Nâng cấp Frappe / ERPNext / HRMS — 17/10/2026

Ghi chú cho đợt nâng cấp trên site `erp.tiqn.local`: có gì mới, cái gì đổi hành vi, ảnh hưởng tới
`customize_erpnext`, và việc còn tồn đọng.

Nguồn: lịch sử git giữa bản cũ và bản mới của từng app (commit `feat` / `perf` / `fix`, các patch
migrate), hướng dẫn chính thức
[Migrating to the new navigation](https://docs.frappe.io/framework/user/en/desk/navigation/migrating-to-the-new-navigation),
và các kiểm tra chạy thật trên site sau khi update.

---

## 1. Phiên bản

| App | Trước | Sau | Số commit (không tính merge) | feat | fix | perf |
|---|---|---|---|---|---|---|
| frappe | v16.33.0 | **v16.52.0** | ~1.100 | 154 | 655 | 10 |
| erpnext | v16.32.1 | **v16.51.1** | ~1.000 | 38 | 767 | 11 |
| hrms | v16.16.0 | **v16.51.0** | ~210 | 21 | 119 | 3 |
| lms | develop `d61e9a3` | nhánh **`version-16`** `4f73d8691` (2.63.0) | 443 | | | |
| insights | `3cc444e6a` | `ce7fd17e1` (ghim) | 316 | | | |
| payments | `781c21c` | `e0de51e` | 4 | | | |

Lưu ý về số version:

- **HRMS không có bản 16.21 → 16.48.** `v16.20.1` và `v16.49.0` là **cùng một commit** (01/10), chỉ
  được đánh số lại cho khớp với frappe/erpnext. Từ v16.50, HRMS bắt buộc frappe ≥ 16.50 và erpnext ≥ 16.50.
- **Nhánh `develop` của lms, insights, payments giờ đều đòi frappe ≥ 17.0.0-dev.** Vì vậy:
  - lms chuyển sang nhánh `version-16`;
  - insights ghim ở commit cuối cùng còn khai `frappe >= 15` (trước `552ec6194`, 13/10);
  - payments chưa cài vào site nên không ảnh hưởng.

Backup trước update: thư mục `update_backup_20261017/` ở gốc bench (SHA cũ, diff các file sửa tay,
file untracked, log migrate/build) và bản backup DB `20261017_105309-erp_tiqn_local-database.sql.gz`.

---

## 2. Thay đổi lớn mà người dùng sẽ thấy

### 2.1 Điều hướng mới: Sidebar + Dock (frappe v16.50)

Đây là thay đổi lớn nhất. Frappe đưa hệ điều hướng của v17 vào v16:

- **Sidebar** giờ thuộc về **module**: mỗi module một sidebar. App đóng gói ở
  `<app>/<module>/sidebar/<tên>/<tên>.json`.
- File cũ `<app>/workspace_sidebar/*.json` **không còn được nạp**. Bảng `Workspace Sidebar` chỉ còn là
  archive cho các patch chuyển đổi.
- **Dock**: một dải module theo từng app, ở bên trái.
- **Custom Sidebar**: lớp tuỳ biến của site ("For everyone") và của từng người ("Just for me"), chồng
  lên sidebar của app. Sửa "For everyone" và **Manage Dock** cần role **Workspace Manager**
  (System Manager không tự có role này).
- Có 2 chế độ màn hình chính, chọn ở **Desktop Settings → Desktop Page**. Đổi chế độ là đổi
  **cho toàn site**:
  - **Desktop Icons**: lưới icon như cũ. Site TIQN đang dùng chế độ này.
  - **Apps**: mỗi app một icon, vào trong có dock và sidebar. Upstream sẽ **bỏ hẳn** chế độ
    Desktop Icons ở một bản sau (chưa có ngày).
- Đường dẫn `/app/...` đổi thành `/desk/...`. Link cũ vẫn chạy nhờ redirect 301.

Patch migrate đã tự chuyển dữ liệu: gộp các sidebar trong cùng một module, chuyển sidebar do site tạo
thành module custom (`ERPNext Integrations (Custom)`, `Tools`, `Wiki`), và giữ nguyên bản ghi cũ
làm archive.

### 2.2 HRMS tách module HR thành 9 module điều hướng

`HR Setup`, `Tenure`, `Recruitment`, `Shift and Attendance`, `Leaves`, `Expenses`, `Performance`,
`Payroll`, `Tax and Benefits`. Mỗi module có sidebar, workspace và onboarding riêng.

- **DocType không đổi module**: vẫn ở `HR` / `Payroll`. Các module mới chỉ dùng để điều hướng.
- Workspace của HRMS được **thiết kế lại hoàn toàn**: chỉ còn chart, number card và onboarding,
  **không còn card link**. Link chuyển hết vào sidebar.
- Sidebar HR Setup: nhóm "Setup" đổi tên thành "Masters", và HR Setup thành trang mở mặc định trên
  site chỉ dùng HR.
- Có icon mới (Lucide, dual-tone, "soft module icons") và link tài liệu cho từng DocType/report.

### 2.3 Giao diện Desk (frappe)

- Theme mới **Espresso** (đang làm dở, nhãn "wip"), bộ component UI mới. Dropdown và nút ở footer
  modal chuyển sang Espresso.
- **Data Import** mới: chọn kiểu import, mẫu import có sẵn field mặc định cho Address, Contact, User
  và nhiều DocType của ERPNext.
- Kanban board mới, tree view gọn hơn, trình soạn email mới (kéo người nhận giữa To/CC/BCC, lưới
  file đính kèm), editor văn bản mới.
- **List Filter layouts**: lưu và khôi phục bộ lọc, cột, thứ tự sắp xếp của list view. App cũng có
  thể đóng gói sẵn layout mặc định.
- **Report view**: có chế độ split view và dropdown "related reports".
- **DocType Settings** (gồm cả User Permission theo DocType) và hộp thoại User Settings mới. Avatar
  người dùng thành nút dropdown.
- Banner chỉ-đọc và banner impersonation dễ thấy hơn. Có widget thông báo cố định (Announcement)
  với màu tuỳ chỉnh.
- Workspace: có onboarding, card nhẹ hơn, chart có trạng thái trống. Có thể **khôi phục bản sửa
  trước khi upgrade từ version history**, và lấy lại widget mà bản app mới đã bỏ.

### 2.4 In ấn

- **Print Format Builder** mới được backport. Renderer weasyprint của v16 bị "đóng băng" và đánh dấu
  deprecated.
- ERPNext: site mới mặc định dùng print format **Classic**. Patch đã thay một số print format chuẩn
  cũ (`… Standard`, `… with Item Image`) bằng bản Classic. HRMS thay 3 print format phiếu lương chuẩn
  (Standard / with Year to Date / based on Timesheet) bằng Classic / Detailed.
  Print format riêng của TIQN (TIQN Payslip, Phiếu xuất kho…) **không bị đụng**.
- Site vẫn dùng `pdf_generator = wkhtmltopdf`. Mình đã render lại phiếu xác nhận công sau update và
  kết quả giống hệt bản trước.

---

## 3. Tính năng mới theo app

### 3.1 Frappe

- **Automation**: bộ dựng luồng tự động hoá mới, chiếm khoảng 60 commit feat.
  - Trigger: theo sự kiện của document, theo ngày (Date Based), theo cron, hoặc theo sự kiện custom.
  - Bước xử lý: If/Else, Wait (chờ sự kiện), Server Script, Webhook.
  - Hành động có sẵn: CreateDocument, SendNotification, AssignToUser, SetFieldValue.
  - Có canvas kéo thả, **trial run** (chạy thử rồi rollback), log từng lần chạy, cơ chế circuit
    breaker, và hàng đợi outbox có retry.
  - ⚠ **Có thể gửi email/thông báo.** Áp dụng đúng quy tắc của TIQN: không tự bật luồng gửi mail,
    test luôn gửi về `son.nt@tiqn.com.vn`.
- **Notification**: gửi được nội dung lấy từ Email Template, chọn người nhận theo token
  (owner, assignee).
- Hook mới cho người viết app:
  - `never_skip_patches`: migrate dừng hẳn khi patch lỗi, thay vì bỏ qua.
  - `after_app_build`: chạy thêm bước sau khi build một app khác.
- Email gửi đi: đọc `use_ssl` từ site config.
- Hiệu năng: lazy-load bundle leaflet, đọc stream PDF của Chrome theo khối lớn, tăng tốc kiểm tra
  doctype mồ côi.

### 3.2 ERPNext

**Kho (Stock):**
- Cờ **định giá theo từng Serial No** (`use_serial_no_wise_valuation`). Patch đã bật sẵn cho mọi
  Item có serial.
- **Truy vết nguyên liệu → thành phẩm**: map Serial/Batch của nguyên liệu sang Serial/Batch của
  thành phẩm.
- Report mới:
  - **Stock Valuation Comparison** (định giá thực tế so với kỳ vọng);
  - report tìm và sửa SLE chưa huỷ của chứng từ đã huỷ.
- Repost chỉ phần GL từ report Stock and Account Value Comparison.
- Filter chọn nhiều: Item/Warehouse trong Warehouse Wise Item Balance, Brand trong Stock Ledger.
- Production Plan cho phép dùng warehouse nhóm khi kiểm nguyên liệu.
- **Kho mặc định chuyển từ Stock Settings sang Company.** Patch `move_warehouse_defaults_to_company`
  đã chuyển `Stores - TIQN` vào `Company.default_warehouse`, rồi **xoá** field `default_warehouse`
  khỏi Stock Settings.
- Hiệu năng:
  - tìm Item trong ô link bằng index FTS5 trigram;
  - repost tốn ít bộ nhớ hơn;
  - bỏ quét batch âm khi không có số âm;
  - gom các lookup của Material Request, Putaway Rule, Sales Forecast.

**Bán / Mua / Sản xuất:**
- Sửa hàng loạt (bulk edit) bảng con của Sales Order, Purchase Order, Purchase Invoice.
- List layout chuẩn cho các DocType hay dùng.
- Blanket Order đa tiền tệ. BOM có loại định giá cho secondary item.
- Purchase Receipt dùng tỷ giá theo ngày giao dịch. Purchase Invoice kiểm tỷ giá khớp với Purchase
  Receipt.
- Sales Order Analysis nhóm theo item. Supplier Quotation Comparison có filter status.
- Party Import Tool tích hợp vào Data Import.

**Kế toán:**
- Báo cáo tài chính nhóm theo dimension. General Ledger có filter "Consider Accounting Dimension".
- Bank Reconciliation mở rộng được loại chứng từ.
- Period Closing Voucher cho submit khi chênh lệch giá trị kho đã xác nhận nằm trong 1%.
- Có thêm hệ thống tài khoản của Bỉ và Mỹ.

**Khác:** setup wizard mới, onboarding "first transaction", trang Setup làm trang chủ.

### 3.3 HRMS

- **Holiday List**:
  - truy vấn ngày nghỉ theo **lô** (batch), nhanh hơn;
  - resolve Holiday List theo **Holiday List Assignment** cho đúng kỳ của chứng từ;
  - hỗ trợ **ngày nghỉ nửa ngày** (`Holiday.is_half_day`): phiếu lương tính nửa ngày công, vắng
    nguyên ngày vào ngày nghỉ nửa ngày thì trừ nửa;
  - tab Connections của Holiday List hiện các Holiday List Assignment.
- **Phiếu lương**:
  - thêm 3 print format Classic / Detailed / Compact;
  - hiện khoản đóng góp của người sử dụng lao động (employer contribution), có Journal Entry riêng;
  - hiện thành phần có điều kiện như Leave Without Pay;
  - sửa nhiều lỗi của Salary Register.
- **Nghỉ phép**:
  - lịch phép tích luỹ (earned leave) bị **chặn trần theo số phép năm**;
  - cấp nốt phần phép còn lại trong hạn mức năm thay vì bỏ qua;
  - **không còn bắt buộc Leave Approver / Expense Approver** mặc định;
  - report Employee Leave Balance **giới hạn theo nhân viên được phép xem**, mặc định lọc về chính
    mình, chạy nhanh hơn và **ẩn dòng toàn số 0**.
- **Chấm công**:
  - Attendance Request chặn đơn nửa ngày rơi vào ngày đã nghỉ trọn ngày;
  - Shift Type kiểm quyền **write** trước khi đánh dấu chấm công;
  - không chốt chấm công nửa ngày khi ca chưa kết thúc;
  - đánh dấu vắng khi Shift Assignment chồng nhau;
  - filter **Employment Type** cho các report chấm công;
  - Monthly Attendance Sheet có filter status và tính lại nửa ngày theo `half_day_status`.
- Job Applicant chép dữ liệu sang Employee khi tạo nhân viên. Expense Claim có status "Partially Paid".
- Cho phép Data Import với nhiều DocType của HRMS.

---

## 4. Thay đổi phá vỡ tương thích / cần chú ý

| # | Thay đổi | Ảnh hưởng tới TIQN |
|---|---|---|
| 1 | HRMS v16.20 xoá `get_assigned_holiday_lists_to_employee_and_company` (commit `c20e8deda`) | 🔴 Làm sập import của `shift_type_optimized.py`. Kéo theo cả **11 override** không nạp, và cron chấm công chạy logic gốc của HRMS. **Đã sửa.** |
| 2 | HRMS v16.50 đổi chữ ký `SalarySlip.calculate_lwp_ppl_and_absent_days_based_on_attendance` (thêm `half_day_holidays`) | 🔴 Override salary slip sẽ ra `TypeError`, không tính được phiếu lương. **Đã sửa.** |
| 3 | Frappe v16.50 bỏ hệ Workspace Sidebar (mục 2.1) | 🔴 Mất link custom ở Stock/HRMS, mất 8 desktop icon của TIQN, mất icon HR Setup và Shift & Attendance. **Đã sửa ở DB** (mục 5). |
| 4 | ERPNext siết quyền cho whitelisted method (`48635ee6b5`, `2cc72d5470`), có patch `mirror_*_perms_to_custom_docperm` | customize_erpnext chỉ gọi đúng 1 method ERPNext qua đường dẫn, và method đó không bị đụng. Người dùng thiếu DocPerm có thể gặp "Not permitted" ở vài nút của ERPNext. Cần theo dõi. |
| 5 | Xoá field `Stock Settings.default_warehouse` (chuyển sang Company) | 🔴 Report **BOM Balance Sheet** (`bom_balance_sheet.py:351`) ném `Field default_warehouse does not exist`. **Chưa sửa.** |
| 6 | HRMS ẩn dòng toàn số 0 trong Employee Leave Balance | Bản tăng tốc của TIQN vẫn hiện các dòng 0. Số liệu khớp 100%; mình đã sửa 2 assert trong `test_leave_reports.py`. |
| 7 | Frappe `get_single_value` giờ **throw** khi đọc field không tồn tại (trước đây trả `None`) | Mình đã quét 33 chỗ đọc Single trong customize_erpnext, chỉ có lỗi ở mục 5. |
| 8 | `/app/...` → `/desk/...` | Redirect 301 vẫn chạy. Link cứng `/app/...` trong email, trang www, Zalo Mini App không cần sửa gấp. |

---

## 5. Đã xử lý trong đợt update

### Code `customize_erpnext` (chưa commit)

- `overrides/shift_type/shift_type_optimized.py`:
  - tra ngày nghỉ theo **nhân viên** qua `get_holiday_list_ranges_for_employees` (bản HRMS mới), có
    nhánh dự phòng cho HRMS cũ;
  - import đặt **trong hàm**, nên không còn làm sập cả module;
  - gom thành 1 query `Holiday`.
- `overrides/__init__.py`: mỗi module override một `try` riêng. Một module lỗi không kéo các module
  khác tắt theo, và Error Log ghi rõ tên module.
- `overrides/salary_slip/salary_slip.py`: nhận chữ ký mới bằng `*args`, chạy được cả 2 bản HRMS.
- `public/js/sidebar_resolution_fix.bundle.js`: tự tắt khi chạy trên hệ sidebar mới.
- `fixtures/workspace.json`: đổi `module` của 2 workspace **HR Setup** và **Shift & Attendance** từ
  `HR` sang module mới. Trước đó fixture đè ngược 2 workspace về module HR làm mất icon.
- Test mới `overrides/shift_type/test_holiday_resolution.py`. Sửa 2 assert trong
  `overrides/leave_reports/test_leave_reports.py`.

### Dữ liệu (DB)

- Thêm lại link custom vào **lớp site** của sidebar (qua `add_site_sidebar_item`):
  - Stock: Packing List, Stock Balance Customize;
  - Shift and Attendance: Daily Attendance (dashboard), Overtime Registration;
  - HR Setup: HR Overview (dashboard) + 15 link từng nằm trong card của workspace HR Setup cũ.
  - Gỡ được bằng `reset_site_sidebar(module)`.
- Tạo lại 8 `Sidebar` (standard = 0) đúng tên cũ để desktop icon hiện lại: New Joiners,
  Door Control, Biometric Sync, Employee Photos, Shoe Rack, QR Code Generator, Job Portal, Dev Tool.
  Hiện 12/13 icon của TIQN đã có lại. System Mindmap vốn không có sidebar từ trước update.
- Đổi module 2 workspace HR Setup và Shift & Attendance cho khớp fixture. Frappe HR giờ đủ 9/9 icon con.
- Sửa lỗi **sidebar bị dính**: mở icon Health Check Up nhưng bên trái vẫn là sidebar Door Control.
  Có 2 nguyên nhân cộng lại:
  - Shell "Health Check Up" trùng slug với DocType "Health Check-Up", nên router không ghi shell vào URL.
  - Shell TIQN có `app = NULL`, nên `crosses_app()` không bao giờ cho là vượt app, và desk giữ
    nguyên sidebar đang hiện.

  Cách sửa: đổi tên shell thành "Health Checkup", gán `app = customize_erpnext` cho 13 shell TIQN,
  và sửa 7 item URL mà patch chuyển đổi để URL trong `link_to` thay vì `url`.
  Debug trên trình duyệt: gõ `frappe.app.sidebar.explain()` trong console.
- `Desktop Settings.desktop_page` đặt lại về `Desktop Icons`, sau khi chế độ Apps bị bật nhầm lúc
  11:18–11:25. Banner "Try the new navigation" không hiện lại nữa.

### File sửa tay trong app upstream (đã merge 3 chiều, vẫn để ngoài git)

- frappe: `data_import.json` (quyền HR User), `page.json`.
- hrms:
  - `shift_type.json` (`allow_bulk_edit`, `allow_rename`);
  - 2 report số dư phép (`disable_prepared_report_automation = 1`);
  - `shift_attendance.json` (bỏ role Employee Self Service).
  - Bỏ các file `workspace_sidebar/*.json` đã sửa và workspace `hr/workspace/hr_setup` cũ. Bản cũ
    nằm trong `update_backup_20261017/`.
- erpnext: bỏ `workspace_sidebar/stock.json` đã sửa. 2 print format VN untracked vẫn còn.
- lms: giữ `hooks.py` (bỏ fixture Custom Field) và `course_lesson.json` (`Long Text` +
  `ignore_xss_filter` của upstream).

### Kết quả kiểm tra

| Kiểm tra | Kết quả |
|---|---|
| Ngày nghỉ của engine chấm công (5 kỳ, 1.043 NV, có cả 2 kỳ vắt năm) | 15/15 trên HRMS cũ **và** mới |
| Phiếu lương tạm dựng lại trước/sau update (72 phiếu) | giống hệt 72/72 |
| Phép năm theo BLLĐ 2019 | 47/47 |
| Report số dư phép (bản tăng tốc so với bản gốc) | 1139/0 |
| Đơn nghỉ Draft | 10/0 (2 bỏ qua vì dữ liệu không còn ca mẫu) |
| Bootinfo desk của user HR | chạy được; icon đủ |
| Phiếu xác nhận công (PDF) | render y như trước |
| Error Log sau restart | chỉ có 27 "Session Stopped" trong lúc bảo trì, sau đó không còn lỗi |

---

## 6. Tồn đọng — cần quyết định / cần làm

| Ưu tiên | Việc | Ghi chú |
|---|---|---|
| 🔴 | **Employee Leave Balance để lộ số dư phép của toàn bộ nhân viên** | Report có role `Employee`. Bản override `custom_get_employees` (`overrides/leave_reports/employee_leave_balance.py:70`) dùng `frappe.qb`, không kiểm quyền. Upstream đã đổi sang `frappe.get_list` ở bản này. Có **32 user desk không phải HR** mở được report. Bản Summary thì an toàn. |
| 🔴 | **BOM Balance Sheet lỗi** khi tìm kho mặc định | Sửa 1 dòng: đọc `Company.default_warehouse` thay vì Stock Settings. |
| 🟠 | `ShiftType.process_auto_attendance` bản override không kiểm quyền write | Upstream đã thêm `self.check_permission("write")`. Bản override (`overrides/shift_type/shift_type.py:263`) vẫn `@frappe.whitelist()` mà không kiểm quyền. |
| 🟠 | Điều hướng mới mới chỉ được lưu ở DB | 8 sidebar + 23 item lớp site chưa nằm trong code. `customize_erpnext/workspace_sidebar/*.json` giờ là file chết. Muốn bền thì chạy `bench --site <site> convert-sidebar-fixtures --app customize_erpnext` trên site dev, rồi commit thư mục `<module>/sidebar/`. |
| 🟠 | Chế độ **Apps** chưa dùng được | Dock chỉ có erpnext/hrms/frappe. customize_erpnext, lms, insights không có dock, nên không vào được các trang TIQN. Cần đóng gói `customize_erpnext/dock/customize_erpnext/` trước khi chuyển. |
| 🟡 | Sidebar "HR" (118 mục, standard = 0) do patch gộp từ 9 sidebar HRMS cũ | Trùng với các sidebar module mới. Xoá hay giữ thì chờ bạn xem UI. |
| 🟡 | `bench build` luôn exit 1 ở bước `build:islands` của Insights | Island cần `frappe/ui/src/vite/island` của v17. App chính của Insights vẫn build và chạy được. Lưu ý thêm: build dừng ở Insights thì **lms frontend không được build**, nên phải chạy `bench build --app lms` riêng. |
| 🟡 | Lỗi lương có từ trước update: kỳ Tết mọi phiếu ra `absent_days = 9` | Có thể do ngày lễ không có Attendance nên bị tính là "unmarked = Absent". Nên xem trước khi chạy lương thật. |
| 🟡 | Production Plan: hàm custom `get_material_request_items` lệch chữ ký từ trước update | Site có 0 Production Plan. Hiện hàm âm thầm quay về bản gốc. |
| ⚪ | Bản override earned leave không có phần "chặn trần theo phép năm" mới của upstream | Thiết kế của TIQN làm tròn trên tổng phép năm, 47 test vẫn đạt. Chỉ cần lưu ý nếu có ngoại lệ. |

---

## 7. Quy trình update — rút kinh nghiệm

1. **Trước khi merge**, quét các import của customize_erpnext và các hàm upstream mà mình override
   (đổi chữ ký, đổi body). Lần này bắt được 2 lỗi thật: mục 4 #1 và #2.
2. Đọc `patches.txt` mới, nhất là các patch có tên `sidebar` / `print_format` / `perms` / `move_*`.
3. Lưu SHA cũ, `git diff`, file untracked (dùng `git -c core.quotepath=off` vì có tên file tiếng
   Việt), và `bench backup`.
4. Tắt scheduler và bật maintenance mode.
5. Với mỗi app: `git stash` → `merge --ff-only <tag>` → `stash pop`, rồi gỡ conflict.
   - Frappe nạp DocType/Report theo **hash file**, nên lấy `modified` của upstream cũng được.
   - File `yarn.lock` thì bỏ, để yarn sinh lại.
6. Chạy `bench setup requirements`.
7. **`clear-cache` TRƯỚC migrate** khi `modules.txt` đổi. Lần này HRMS thêm 9 module, nên phải
   migrate 2 lần.
8. Chạy `bench build`; nếu dừng giữa chừng thì build riêng các app phía sau (lms).
9. Tắt maintenance → bật scheduler → **sau đó mới `bench restart`**. Restart trước khi tắt
   maintenance thì worker cache trạng thái bảo trì và trả 503.
10. Kiểm tra sau update:
    - ping, `/login` qua nginx;
    - bootinfo của user HR;
    - `time_zone` của System Settings;
    - index `attendance_index`;
    - Error Log;
    - các bộ test của customize_erpnext.
