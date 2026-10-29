# Employee Portal — backend cho Zalo Mini App "Cổng nhân viên"

> Hợp đồng với đội Mini App: [`API_CONTRACT.md`](./API_CONTRACT.md) — **nguồn chính** cho mọi request/response
> (bản 1.9.0, nhật ký thay đổi ở §13).
> Plan + quyết định đã chốt với user: `~/frappe-bench/.claude/plans/` — `zalo_payslip_portal.md` (gốc),
> `employee_portal_payslip_paper_layout.md`, `employee_portal_link_request.md`, `employee_portal_simplify_v3.md`,
> `employee_portal_payslip_layout_link_request_v4.md`, `payslip_structure_by_period.md` (cấu trúc phiếu theo kỳ).
> File này ghi cách cài, cách vận hành và **các bẫy đã vấp** khi code.
> Hướng dẫn cho người dùng (C&B): [`HUONG_DAN_CNB.md`](./HUONG_DAN_CNB.md).

## Trạng thái (24/10/2026)

| Mốc | Nội dung | Trạng thái |
|---|---|---|
| M1 | Đăng nhập Zalo, phiên, phiếu lương (upload → phát hành), thông báo | ✅ production |
| M1.1 | Đăng nhập theo Zalo User ID + SĐT HR gán, `dev_login` simulator | ✅ |
| M2 | Màn chỉ xem: chấm công, tổng hợp, tăng ca, số dư phép | ✅ code, đang **tắt** (giai đoạn chỉ phiếu lương) |
| v2 | Settings chia tab + cờ tính năng; phiếu không bảng con (`sc_<mã>`); thông báo chung 1 bản ghi; chat C&B | ✅ |
| 1.3 | Phiếu lương như bản in giấy (`rows`, STT, ngày/giờ + số tiền) | ✅ |
| 1.4 | Yêu cầu liên kết hồ sơ (NOT_FOUND → mã NV + họ tên → CnB duyệt) | ✅ |
| 1.5 | Gọn ERP (1 field "đã xem", đơn vị ngày/giờ trong Settings), phiếu NV nghỉ việc, report theo kỳ, role CnB, icon Desk | ✅ |
| 1.9 | **Payslip Structure**: khoản lương / nhãn / chữ công thức theo kỳ, phiếu giữ bản chụp riêng (`lines_json`); `content_version`; `get_config.payslip.show_zero_lines` (28/10) | ✅ |
| M3 | Đơn nghỉ, giấy tờ, giải trình, duyệt trên Desk | chưa |
| M4 | Tin OA | chưa |

## Quyền — role `CnB`

**CnB** (Compensation & Benefits) + **System Manager** là 2 role duy nhất vào được portal: trang Payslip Upload,
TIQN Payslip, report Payslip Period Summary, TIQN Portal Notification / Account / Link Request / Session,
Employee Portal Settings. HR Manager **không** xem được lương (quyết định 12/10). Role tạo bằng patch
`create_cnb_role` (pre_model_sync — DocPerm trỏ tới role); **gán người do Admin làm**.
CnB không có quyền trên Employee — người CnB thường đã có HR User. Phiếu lương **không dùng** Salary Component
của HRMS (từ 26/10): nhãn / nhóm / đơn vị đều lấy từ field của TIQN Payslip, sửa là việc của IT.

## Desk

Icon **Employee Portal** (lưới Desktop Icons, chỉ CnB + System Manager thấy) → shell `/desk/employee-portal/…`:
Payslip Upload · Payslip · Payslip Period Summary · Mini App ▸ Notification, Link Request, Zalo Account,
Employee Portal Settings. Sinh bằng `scripts/build_navigation.py` (đừng sửa tay file trong `sidebar/`,
`desktop_icon/`, `dock/` — chạy lại script là mất).

## File

| File | Vai trò |
|---|---|
| `api/employee_portal/core.py` | decorator `portal_api`: xác thực token, phong bì `ok/data/error`, user dịch vụ, rate limit |
| `api/employee_portal/auth.py` | `get_config`, `login`, `dev_login`, `link_employee_request`, `me`, `set_id_by_oa`, `logout`, `set_oa_follow` |
| `api/employee_portal/home.py` | `get_home` (thẻ NV + phiếu mới nhất + thông báo) |
| `api/employee_portal/payslip.py` | `get_payslip_periods`, `get_payslip` (`rows` như bản in; `sections` deprecated) |
| `api/employee_portal/notifications.py` | danh sách / đánh dấu đã xem |
| `employee_portal/demo.py` | **dữ liệu mẫu cho reviewer của Zalo** (Review Mode) — sinh theo ngày hôm nay, phiếu lương mẫu chạy qua đúng `build_payslip_payload` |
| `utils/zalo_graph.py` | gọi `graph.zalo.me` (user id, tên, SĐT) + dịch mã lỗi Zalo |
| `employee_portal/utils.py` | kỳ 26→25, SĐT (9 số cuối, `cell_number` rồi `custom_cell_phone_zalo`), quyền theo trạng thái NV, field khoản lương |
| `employee_portal/payslip_structure.py` | **cấu trúc phiếu theo kỳ** (28/10): chọn structure của kỳ, validate, bản chụp `lines_json`, sinh `rows` / `sections`, chặn số vô lý, Apply Labels |
| `employee_portal/doctype/tiqn_payslip_structure/` | TIQN Payslip Structure (+ bảng con `…_line`): dòng phiếu từ kỳ `valid_from`; nút **Apply Labels to Payslips** |
| `employee_portal/payslip_admin.py` | Desk: file mẫu (tháng / NV nghỉ việc), preview, nhập Draft, phát hành, thu hồi |
| `employee_portal/page/payslip_upload/` | trang Payslip Upload |
| `employee_portal/doctype/tiqn_payslip/tiqn_payslip_list.js` | list TIQN Payslip: màu trạng thái + nút **Download PDF** (import / publish chỉ ở trang Payslip Upload, 27/10) |
| `employee_portal/report/payslip_period_summary/` | 1 kỳ: phát hành / đã xem / chưa xem + bảng các khoản chính (cột `basic_pay`… theo Report Column) |
| `employee_portal/report/payslip_detail/` | 1 kỳ: mọi dòng của mọi phiếu, cột động theo dòng của kỳ (đọc `lines_json`) ; chỉ để xem (không có cột Period → không upload lại được). Filter Pay Period của 2 report = Select từ `payslip_admin.get_report_periods` (kỳ đã có phiếu) |
| `employee_portal/doctype/tiqn_portal_link_request/` | yêu cầu liên kết hồ sơ, nút Approve / Reject |
| `employee_portal/notify.py` | tạo thông báo trong app (không gửi gì ra ngoài) |
| `employee_portal/translation_strings.py` | chuỗi dịch qua biến — liệt kê literal để vào `locale/vi.po` |
| `employee_portal/sidebar/employee_portal/` | shell Desk (sinh bằng script) |
| `www/portal-policy/`, `www/portal-terms/` | trang công khai (Zalo đòi URL chính sách) |
| `Payslip 2026-09 SAMPLE …xlsx`, `Payslip 2026-10 SAMPLE …xlsx` | file mẫu số **giả** (tên NV thật) để thử import — 🔴 **không commit** |

## Cài đặt / cấu hình

1. `sites/erp.tiqn.local/site_config.json`: `zalo_app_employee_portal_secret_key` (App Secret Key của Zalo App
   gắn với Mini App — contract §12), rồi `bench restart`. Không đưa khoá vào code/tài liệu.
2. **Employee Portal Settings** (tab):
   - General: tên công ty, hotline HR, SĐT công ty (logo dùng logo Zalo App, không cấu hình ở đây).
   - Mini App Features: bật/tắt tính năng (giai đoạn này chỉ Payslip + Notifications); ngày trả lương (mặc định 5);
     hiện dòng 0 (trạng thái đầu của nút "Ẩn khoản 0đ", `get_config.payslip.show_zero_lines`, app 1.9.0+).
   - Access: hạn chỉ xem sau nghỉ việc (30 ngày), số ngày phiên, phiên bản Mini App tối thiểu.
   - Zalo OA & Chat: **ID by OA** của người C&B (nút "Chat với C&B"), OA ID.
   - Legal: nội dung chính sách / điều khoản (công khai ở `/portal-policy`, `/portal-terms`).
3. Gán role **CnB** cho người C&B.
4. **TIQN Payslip Structure**: phải có structure cho kỳ (Valid From ≤ kỳ) trước khi tải template / upload.
   Tên `PSS-01`, `PSS-02`… (series `PSS-.##`, không chứa kỳ: tên cũ `PSS-2026-09` dễ hiểu là của riêng 1 kỳ,
   patch `employee_portal_structure_numbered` đổi tên 29/10/2026). *Valid To Period* = kỳ trước Valid From của bản kế
   tiếp, field dẫn xuất do `payslip_structure.refresh_valid_to()` tính lại sau mỗi lần lưu / xoá.

## Đăng nhập: Zalo User ID + SĐT (contract §2.2, §2.6)

- Zalo **luôn** xác nhận User ID (server gọi `/v2.0/me` bằng `access_token`). SĐT đến từ Zalo (`phone_token`)
  hoặc từ `TIQN Portal Account.phone` (HR gán tay → `phone_source = Manual`; Zalo xác nhận → `Zalo`, luôn thắng).
- SĐT khớp `Employee.cell_number` trước; không ai có số đó mới so `custom_cell_phone_zalo` (SĐT Zalo khác SĐT hồ sơ).
- Không cấp quyền SĐT → app hiện Zalo User ID → CnB mở **TIQN Portal Account** → nhập SĐT. Form chặn số không khớp
  nhân viên nào; đổi số = huỷ mọi phiên của tài khoản.
- **Yêu cầu liên kết** (`NOT_FOUND`): nhân viên gửi mã NV + họ tên → **TIQN Portal Link Request** (Pending). CnB
  **gọi lại SĐT Zalo** trên phiếu để chắc đúng người (mã + tên không bí mật), xem khung cảnh báo, rồi **Approve**
  (ghi SĐT Zalo vào `custom_cell_phone_zalo`, có Version) hoặc **Reject** (lý do hiện trên app).
  - **1 bản ghi / tài khoản Zalo** (`account` unique), **tên bản ghi = SĐT Zalo** (`autoname: field:phone`): gửi lại =
    ghi đè, về Pending, xoá kết quả duyệt cũ; nội dung cũ nằm ở lịch sử (Version). Đang chờ vẫn gửi lại được. SĐT
    của tài khoản đổi → bản ghi được rename sang số mới; bản ghi tài khoản khác bỏ lại dưới số đó bị thay
    (`auth._own_request`).
  - Tên Zalo + **ảnh đại diện Zalo** (`zalo_avatar`, ảnh của form) do server hỏi Zalo (`zalo_graph.get_user_info`,
    `fields=id,name,picture`) lúc gửi yêu cầu, không nhận từ app; trống nếu người dùng chưa chia sẻ hồ sơ Zalo.
  - App chỉ nhận **mã NV + họ tên khớp** hồ sơ (`normalise_name`, bỏ dấu/hoa thường). Sai mã hay sai tên đều trả
    cùng `NOT_FOUND` (không lộ mã nào có thật). CnB vẫn **sửa được Employee khi còn Pending** (đã duyệt/từ chối thì
    khoá, kiểm cả ở server); đổi Employee → Khớp tên + cảnh báo tính lại.
  - ⚠ Index unique của `account` không được model sync tạo khi còn index thường cùng tên → patch
    `employee_portal_link_request_unique_account` (field đã bỏ `search_index`).
  - Tối đa **2 lần/ngày** (ngày lịch), đếm trong bản ghi (`request_count`, `requests_today`, `last_requested_on`) →
    `REQUEST_LIMIT`. Ngoài ra cache 10 lần thử/ngày/Zalo (kể cả lần bị từ chối) để chặn dò mã NV → `RATE_LIMITED`.
  - NV đang được một **TIQN Portal Account chưa khoá** đăng nhập → app trả `EMPLOYEE_LINKED`, nút Approve cũng chặn.
    Gỡ = **Disable** tài khoản cũ (field Employee trên tài khoản là chỉ đọc, do `login` ghi).
- **Tự khoá tài khoản mới** (chặn người ngoài + người nghỉ quá hạn): tài khoản mới bắt đầu `disabled = 1` +
  `auto_disabled = 1`, trừ khi SĐT khớp NV `Active` hoặc `Left` còn trong hạn chỉ xem; tự mở khi điều kiện thành
  đúng. Khoá tay (`auto_disabled = 0`) không bao giờ tự mở. `login` vẫn trả `NO_PHONE`/`NOT_FOUND`/`EXPIRED`.
- **Simulator** (`dev_login`): tin User ID client gửi → rào 2 lớp: `bench --site erp.tiqn.local set-config
  employee_portal_dev_login 1` **và** tick "Allow Dev Login" + gán SĐT. Phiên dev 1 ngày. ⚠ Chỉ gán SĐT nhân viên
  test. Tắt khi không dev: `set-config employee_portal_dev_login 0`.
- **Zalo App Review** (27/10/2026 — Zalo từ chối duyệt vì reviewer không xem được gì): Settings → Access →
  tick **Enable Review Mode** + **Reviewer Phones** (mỗi dòng 1 SĐT Zalo đưa). SĐT do **Zalo xác nhận**
  (`phone_source = Zalo`), không khớp NV nào → `login` trả `ACTIVE` + NV mẫu `DEMO-0001`, phiên
  `login_method = REVIEW` không có employee, account `last_result = REVIEW`. `portal_api` thấy phiên REVIEW là trả
  từ `demo.respond()` — **không bao giờ chạy endpoint thật**; endpoint chưa có handler mẫu → `NOT_FOUND`
  (thêm endpoint có token mới thì PHẢI thêm handler vào `demo.HANDLERS`, test sẽ báo). Chỉ ghi vào chính account
  của reviewer (theo dõi OA, đã xem thông báo). SĐT của NV thật luôn đăng nhập là NV đó. Tắt mode / xoá SĐT /
  SĐT về tay NV thật → phiên REVIEW bị từ chối ngay (`REVOKED`). Không có ngày hết hạn (user chốt 27/10: chỉ thấy
  dữ liệu mẫu). Tính năng tắt trong Settings thì reviewer cũng không thấy, như nhân viên. Phiếu mẫu: **3 kỳ đã kết thúc gần nhất** (`demo.DEMO_PERIODS`, tự lùi theo ngày; 28/10 = 10, 09, 08/2026), bộ dòng riêng `demo.DEMO_LINES`. 🔴 Zalo kiểm lại **mỗi lần release** → đổi gì ở portal cũng phải giữ demo chạy (test so key demo với response thật).
- Giới hạn `login`: 3000/phút/IP (cả nhà máy chung 1 IP WiFi) + 10 lần/10 phút/Zalo ID.

## Vận hành phiếu lương

1. **Payslip Upload → Download Template**:
   - *Hằng tháng* — chọn kỳ: NV còn làm tới cuối kỳ. **Không** gồm: nghỉ trước/trong kỳ, thai sản phủ cả kỳ
     (`Employee Maternity`), **Exclude Employees** của Attendance Calculation Setting. Vào giữa kỳ → Period From = ngày vào.
   - *Resigned Employees Only* — chọn **kỳ** + khoảng ngày nghỉ **trong kỳ đó** (mặc định cả kỳ; server chặn khoảng
     ra ngoài kỳ), mọi dòng thuộc kỳ đã chọn, Period To = ngày nghỉ − 1,
     Pay Date = ngày nghỉ + 14 (trả riêng, HR tự tính). **Không** gồm người nghỉ đúng ngày 26 (ngày làm cuối = ngày 25
     cuối kỳ): họ làm đủ kỳ nên nằm ở file tháng, trả ngày 5 vẫn trong hạn 14 ngày — tránh 2 phiếu cùng kỳ.
2. Điền số → **Upload Excel** → xem lỗi/cảnh báo → **Import as Draft**.
3. Bảng "2. Publish" → **Publish** kỳ. Phiếu tháng: tạo **1 thông báo chung** cho kỳ. Chỉ toàn phiếu NV nghỉ việc
   (`final_settlement`, tự suy từ `relieving_date` trong kỳ): **không** thông báo — HR tự nhắn họ.
4. Sai → **Withdraw** → sửa → upload lại → Publish. **Delete Payslips** (28/10, `delete_period`) xoá **mọi** phiếu
   Draft + Withdrawn của kỳ (Published không bao giờ bị xoá — Withdraw trước); hộp xác nhận nêu số phiếu Withdrawn và
   số đã được NV mở. Bản xoá nằm ở Deleted Document (System Manager khôi phục được). > 150 phiếu chạy nền
   (`payslip_delete_done` realtime). Trước 28/10 nút là "Delete Drafts", chỉ xoá nháp chưa từng phát hành.
5. Theo dõi: report **Payslip Period Summary** (Published / Viewed / Not Viewed, lương cơ bản / tăng ca / tổng /
   khấu trừ / thực lĩnh theo Report Column, ngày xem đầu); **Payslip Detail** = mọi dòng của kỳ (xuất Excel).
6. **In phiếu** (27/10, `payslip_print.py` + `payslip_print.html`): nút **Download PDF** trên form và trên list. Chỉ **A4** (khổ A5 thì C&B chọn trên máy in). 1 phiếu → PDF; nhiều
   phiếu → ZIP mỗi phiếu 1 PDF, tên `{Period}_{section}_{group}_{employee}_{employee_name}.pdf` (bỏ ký tự cấm, bỏ
   phần rỗng). Bố cục = phiếu giấy (`phiếu lương.png`): song ngữ English/label Mini App, đủ 44 dòng (0 = "-"), dưới
   bảng 2 dòng "Transfer deadline/Hạn chuyển khoản" (Pay Date) + "Remark/Ghi chú" (= Note; không có cột Remark từng dòng), Dept = Section - Group, Draft/Withdrawn có chữ chìm "BẢN NHÁP / DRAFT". Đầu trang: logo (tên công ty đã bỏ, 28/10). Số kiểu Việt Nam
   (`17.214.001`, `24,5`); dòng có Report Column = Net ghi "VNĐ" ở cột ĐVT, các dòng khác không ghi đơn vị tiền. Lề trên/dưới 7 mm, phải khai bằng CSS `.print-format`
   (`get_pdf` ép 15 mm khi không có header/footer html, bỏ qua option) → Note tới ~400 ký tự vẫn 1 trang, dài hơn tràn trang 2.
   Print Format **TIQN Payslip** (mặc định qua Property Setter `TIQN Payslip-main-default_print_format` trong fixtures — DocType chuẩn không được đặt `default_print_format` trong JSON, nếu đặt thì không lưu được DocType) gọi cùng template qua jinja method `payslip_print_html`
   (hooks.py) → nút Print / Ctrl+P ra đúng mẫu. Engine **wkhtmltopdf** (Chrome PDF của v16 cần gói hệ thống
   `libasound2` chưa cài — user chọn không cài 27/10). Nhiều phiếu: render 1 lần rồi tách trang bằng pypdf; số trang ≠
   số phiếu (phiếu tràn trang vì Note dài) → render lại từng phiếu. PDF/ZIP trả thẳng, **không** lưu File (chứa
   lương); mỗi phiếu được ghi Comment "Printed PDF". Thứ tự: period → section → group → employee.
   **List** chỉ 1 nút **Download PDF** (27/10): phiếu đã tick (mặc định khi có tick) hoặc **theo bộ lọc**: Period và/hoặc
   **Employees** (nhiều NV; bỏ trống Period = mọi kỳ của các NV đó) **hoặc Sections** (nhiều) **hoặc Group** — chỉ 1
   trong 3 (chọn cái này JS xoá 2 cái kia, server cũng chặn) — + Status, mặc định Published; `get_list` = theo quyền. Ô
   Employees gợi ý qua `search_pdf_employees`: bỏ Exclude Employees (Attendance Calculation Setting), có Period thì bỏ
   người nghỉ trước kỳ (`relieving_date <= ngày 26`) / vào sau kỳ. Tên file `{period}_{section}_{group}_{employee}_{employee_name}_{n} payslips` (bỏ phần không
   chọn; nhiều NV = `{n} employees`, nhiều Section = `{n} sections`). ~1.000 phiếu ≈ 2 phút > timeout 120 s → `start_pdf_job`
   → job queue `long` `build_pdf_job` (render 50 phiếu/lần) → list poll `pdf_job_status` 2 s/lần → `download_pdf_job`.
   Output **ZIP** từng PDF (mặc định, kỳ 10/2026: 134 s, 64 MB) hoặc **1 PDF gộp** (127 s, 9,4 MB); 1 phiếu → luôn là
   PDF. Kết quả nằm ở **Redis cache** (không persistence) 30 phút, chỉ user đã bấm mới tải được, tải 1 lần rồi xoá —
   không lưu File; mỗi user 1 job một lúc; tối đa 3.000 phiếu. Comment "Printed PDF" ghi lúc tải về.

File Excel: `No. | Period | Period From | Period To | Pay Date | Employee | Employee Name | Designation |
Department | Section | Group | Note | <khoản>`.
- **Note** (27/10): field `note` (Small Text) = ghi chú tự do cho **cả phiếu**, không phải từng dòng. Cột không bắt
  buộc (file cũ vẫn nhập được); ô trống / không có cột = xoá ghi chú cũ (như khoản tiền); > 1.000 ký tự = lỗi dòng;
  ghi đè phiếu Draft/Withdrawn mà Note khác → cảnh báo cũ/mới. Bị khoá khi Published như số tiền. Payload `note`
  (contract 1.8.0), in thành khung dưới bảng.
- `No.` và `Designation` chỉ để HR nhìn, không đọc lại. Tiêu đề cũ (`Kỳ lương | MSNV | Họ tên | …`) vẫn đọc được.
- Cột khoản = dòng của **Payslip Structure của kỳ**, nhận theo **mã số đầu tiêu đề** (`3.2 …`); `<mã> Days` /
  `<mã> Hours` (cũ: `… - Days`, `Unit/ĐVT`) = số ĐVT. Cùng 1 file các kỳ phải chung structure. Cột thiếu = 0 (liệt kê
  cho HR), cột có mã không thuộc structure = lỗi.
- `Period From/To` phải nằm trong kỳ 26→25; trống = tự tính. `Pay Date` trống = ngày trả lương tháng (hoặc nghỉ + 14).
- Lỗi (chặn): MSNV không có, trùng dòng, ô không phải số/ngày, cột lạ, ngày ngoài kỳ, kỳ đã phát hành, kỳ chưa có
  structure; **số vô lý** (`payslip_structure.absurd_errors`, 28/10): ngày/giờ âm (mọi dòng); chỉ dòng khối
  **Attendance**: số ngày > số ngày của kỳ, số giờ > 24 × số ngày của kỳ (7.4 thanh toán phép khi nghỉ việc có thể > 31);
  |số tiền| ≥ 100 tỷ. Controller TIQN Payslip kiểm lại cùng điều đó khi lưu. Thiếu cột Kỳ / kỳ chưa có structure / file
  trộn structure → chỉ báo 1 lỗi đó (không liệt kê từng cột "lạ").
- Cảnh báo (xác nhận rồi vẫn nhập): tên khác ERP, NV nghỉ trước kỳ, **NV nghỉ giữa kỳ mà Period To trong file ≥
  `relieving_date`** (file tháng tải trước khi nhập ngày nghỉ — controller giữ Period To của file, không tự cắt về
  ngày nghỉ − 1; Period To trống thì không cảnh báo vì tự tính; từ 26/10), **ghi đè phiếu Draft/Withdrawn đang có** (lô + giờ
  lưu cũ; Period From/To, Pay Date khác thì hiện cũ/mới — trước 26/10 ghi đè im lặng), thực lĩnh âm.
  **Không kiểm công thức** (user chốt 28/10: 100% số liệu do HR quyết) và **không bao giờ tự sửa số của HR.**
- File upload bị xoá khỏi `File` ngay sau khi nhập/huỷ (chứa lương cả kỳ).
- **Cấu trúc phiếu = TIQN Payslip Structure theo kỳ** (28/10/2026, `payslip_structure.py`; plan
  `payslip_structure_by_period.md`). Trước đó (v4–v5) là 50 field `sc_*` + Settings ▸ Payslip Lines — **đã xoá**
  (phase 2, 28/10: patch `employee_portal_drop_sc_fields` drop cột + DocType TIQN Portal Payslip Line; các patch cũ
  v2…payslip_structure gỡ khỏi patches.txt vì đã chạy xong):
  - structure áp từ `valid_from` tới structure kế tiếp (`structure_for_period`: `valid_from` lớn nhất ≤ kỳ, so chuỗi
    YYYY-MM). Mỗi dòng: `code`, `label_en`, `label_vi` (= chữ Mini App + phần tiếng Việt bản in), `formula_display`
    (**C&B gõ tay**, chỉ để in trong ngoặc, ERP không kiểm/tính; gõ "(c=a+b)" thì tự bỏ ngoặc), `unit` (VND/Day/Hour),
    `quantity_unit` (cột ĐVT của dòng tiền), `parent_code` (khai rõ, JS gợi ý theo mã — vì 3.2–3.10 thuộc 3.1 chứ
    không thuộc 3), `row_type`, `section` (khối của `sections` deprecated — app hiện tại **còn đọc**), `report_key`
    (→ cột `basic_pay`, `overtime_pay`, `gross_pay`, `total_deductions`, `net_pay`, `standard_days`, `actual_days`,
    `ot_hours`; OT Hours cộng dồn);
  - validate chỉ chặn chuyện vô lý: mã sai dạng/trùng, Under Line không có hoặc vòng lặp, thiếu nhãn, 0 hoặc 2 dòng
    Net, Day/Hour có cột ĐVT, 2 Section Total trong 1 khối;
  - **bản chụp** `TIQN Payslip.lines_json` (Long Text ẩn) = dòng + số HR nhập, ghi lúc import (`make_snapshot`;
    phiếu tạo tay = dòng của structure, số 0). `rows`, `sections`, PDF, report đọc **chỉ** bản chụp → structure sau
    không đổi phiếu đã nhập. Controller dựng lại level / is_header, chặn số vô lý, ghi `content_version`
    (sha1 bản chụp) + các cột report. Phiếu Draft/Withdrawn sửa số ngay trên tab Detail (bảng HTML), Published thì chặn;
  - **khoá**: structure đã có phiếu (mọi trạng thái) chỉ sửa được 3 field nhãn + description; sửa mã / thêm-bớt dòng /
    đơn vị / loại dòng / khối / report_key / valid_from → chặn (Duplicate với kỳ mới, hoặc xoá phiếu nháp). Structure
    mới không được "chiếm" kỳ đã có phiếu của structure khác (`block_periods_taken`). Publish kiểm lại phiếu đúng
    structure của kỳ;
  - **Apply Labels to Payslips** (nút trên structure): chép nhãn mới vào bản chụp mọi phiếu của structure (kể cả
    Published) — **không** đổi số, `published_on`, `modified`, không thông báo; `content_version` đổi; > 150 phiếu chạy
    nền; ghi Comment. App hiện tại cache theo `(period, published_on)` → máy đã mở phiếu vẫn thấy nhãn cũ tới khi
    xoá cache (như 1.6.0); app 1.9.0+ thêm `content_version` vào khoá cache;
  - Data Import TIQN Payslip **tắt** (`allow_import = 0`): chỉ nhập qua trang Payslip Upload;
  - demo (Review Mode) có bộ dòng riêng `demo.DEMO_LINES`, không đọc structure thật;
  - text khác trả về app (`_()` + vi.po): System Manager đè bằng DocType **Translation** (`/app/translation`, Language
    vi, Source Text = chuỗi tiếng Anh trong code / msgid vi.po) — không cần sửa code.
- "Đã xem" = `first_viewed_on` (lần `get_payslip` đầu tiên; các lần sau không ghi DB).

## Test

```bash
cd ~/frappe-bench/sites && ../env/bin/python -c "
import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
exec(open('../apps/customize_erpnext/customize_erpnext/employee_portal/test_employee_portal.py').read())"
```
Rollback toàn bộ; dùng zalo id `unit-<uuid>` và kỳ 2030-xx. ⚠ Biến `refused` bị gán lại thành list ở đoạn
"signed document links" — test viết sau đoạn đó dùng `refused_fn`.

## 🔴 Bẫy đã vấp

1. **`bench migrate` nạp fixtures SAU patch `post_model_sync`.** Patch cần custom field phải tự tạo
   (`setup_employee_portal.ensure_portal_custom_fields()`, `employee_portal_payslip_paper_layout`).
2. **Trang www có dấu `-` phải là thư mục `ten-trang/index.html + index.py`.**
3. **`frappe.set_user()` ghi đè `session.sid` và xoá `form_dict`.** Endpoint chạy dưới `portal@` phải trả về
   Guest trong `finally` (`_restore_guest`).
4. **`frappe.get_request_header()` ném `RuntimeError` ngoài HTTP request** → dùng `core.request_header()`.
5. **Single DocType trả ngày dạng chuỗi** → `fmt_date()` đi qua `getdate()`.
6. **Thông báo lưu sẵn chữ → dịch tiếng Việt LÚC LƯU** (`notify()` dùng `_(…, lang="vi")`).
7. **Frappe rollback mọi request GET.** `get_payslip` là POST (ghi lần xem đầu). `last_seen` trong GET commit riêng.
8. **Lỗi nghiệp vụ = `frappe.db.rollback()` trong decorator** → test vá rollback/commit thành no-op.
9. **Không dùng `Authorization: Bearer` cho token portal** — Frappe coi là OAuth → 401.
10. **SĐT so theo 9 số cuối**: ~1.140 hồ sơ mất số 0 đầu (Excel). Trùng số → mã NV mới nhất thắng.
11. **`Employee.status` có giá trị `"Left "` (dấu cách)** → luôn `strip()`.
12. **Thêm/sửa hàm trong .py worker đã nạp = cần `bench restart`.** Worker có thể tự nạp code mới khi recycle
    (`--max-requests`) TRƯỚC migrate → code đọc bảng mới phải kiểm `table_exists` (xem `link_request_payload`).
13. **Không cấp role `Leave Approver` cho trưởng bộ phận** (M3): role đó đọc MỌI đơn nghỉ.
14. **Phiên bị huỷ phải báo đúng lý do đã lưu** (`revoked_reason`, dạng `STATUS_CHANGED:EXPIRED`).
15. **Upload lại phiếu Withdrawn phải giữ Withdrawn** — Publish nhận cả Draft lẫn Withdrawn; trang Upload vẫn thấy
    phiếu đó từng phát hành (Delete Payslips cảnh báo trước khi xoá).
16. **Field SĐT Zalo trên Employee tên `custom_cell_phone_zalo`** (không phải `…_number_…`). Code cũ đọc nhầm tên →
    cột bị bỏ qua im lặng (`has_field` = False) tới 24/10.
17. **`frappe.call` mặc định POST** → endpoint `@frappe.whitelist(methods=["GET"])` phải gọi với `type: 'GET'`,
    không thì 403 "Not permitted" (bảng kỳ lương Payslip Upload trống tới 24/10).
18. **File mẫu trống vẫn import trót lọt** (toàn 0 thì công thức vẫn "đúng") — kiểm số dòng ở màn xem trước.
19. **`scripts/build_navigation.py` ghi đè toàn bộ file sidebar/icon** — link thêm tay vào JSON (Quiz trong New
    Joiners) phải đưa vào script, không thì lần chạy sau mất. Sidebar đổi item sau lần nạp đầu cần `modified` mới
    (`SIDEBAR_STAMPS`), không thì migrate bỏ qua file.
20. **Filter `between` của Frappe coi giá trị là NGÀY** → kỳ `YYYY-MM` phải lọc bằng `>=` / `<` (block_periods_taken).
21. **Đổi cấu trúc phiếu ≠ đổi phiếu đã nhập**: phiếu giữ bản chụp. Muốn nhãn mới trên phiếu cũ → Apply Labels;
    muốn số mới → Withdraw + upload lại.
