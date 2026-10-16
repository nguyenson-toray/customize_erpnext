# Employee Portal — backend cho Zalo Mini App "Cổng nhân viên"

> Hợp đồng với đội Mini App: [`API_CONTRACT.md`](./API_CONTRACT.md) — **nguồn chính** cho mọi request/response.
> Plan + các quyết định đã chốt với user: `~/frappe-bench/.claude/plans/zalo_payslip_portal.md`.
> File này ghi cách cài, cách vận hành và **các bẫy đã vấp** khi code.

## Trạng thái

| Mốc | Nội dung | Trạng thái |
|---|---|---|
| M1 | Đăng nhập Zalo, phiên, phiếu lương (upload → phát hành), thông báo, report Portal Readiness | ✅ chạy trên production 12/10/2026 |
| M1.1 | Đăng nhập theo Zalo User ID + SĐT HR gán, `dev_login` simulator | ✅ code + migrate, chờ restart |
| M2 | Màn chỉ xem: trang chủ, chấm công, tổng hợp, tăng ca, số dư phép | ✅ code, chờ restart — 210 test tổng |
| M3 | Đơn nghỉ, giấy tờ, giải trình, duyệt trên Desk | chưa (cần sửa hooks.py → restart) |
| M4 | Tin OA | chưa |

## File

| File | Vai trò |
|---|---|
| `api/employee_portal/core.py` | decorator `portal_api`: xác thực token, phong bì `ok/data/error`, chạy dưới user dịch vụ |
| `api/employee_portal/auth.py` | `get_config`, `login`, `me`, `logout`, `set_oa_follow` |
| `api/employee_portal/payslip.py` | `get_payslip_periods`, `get_payslip` + dựng nhóm hiển thị |
| `api/employee_portal/notifications.py` | danh sách / đánh dấu đã đọc |
| `utils/zalo_graph.py` | gọi `graph.zalo.me` (user id, SĐT) + dịch mã lỗi Zalo |
| `employee_portal/utils.py` | kỳ 26→25, chuẩn hoá SĐT (9 số cuối), quyền theo trạng thái nhân viên |
| `employee_portal/payslip_admin.py` | Desk: template Excel, preview, nhập Draft, phát hành, thu hồi |
| `employee_portal/page/payslip_upload/` | trang `/app/payslip-upload` (upload + phát hành/thu hồi) |
| `employee_portal/doctype/tiqn_payslip/tiqn_payslip_list.js` | nút **Import from Excel** ở list TIQN Payslip (cùng API preview/import với trang trên) |
| `employee_portal/report/portal_readiness/` | việc HR phải làm sạch: thiếu SĐT, trùng SĐT, thiếu người duyệt… |
| `employee_portal/notify.py` | tạo thông báo trong app (không gửi gì ra ngoài) |
| `employee_portal/seed_test_payslips.py` | phiếu **số giả** cho nhóm test, `purge()` trước khi mở toàn công ty |
| `www/portal-policy/`, `www/portal-terms/` | trang công khai (Zalo đòi URL chính sách) |
| `patches/create_employee_portal_roles.py`, `patches/setup_employee_portal.py` | role, user dịch vụ, Settings, cấu hình Salary Component |

## Cài đặt / cấu hình

1. `sites/erp.tiqn.local/site_config.json`: `zalo_app_employee_portal_secret_key` (App Secret Key của Zalo App
   gắn với Mini App này — xem contract §12), rồi `bench restart`.
2. **Employee Portal Settings**: hotline HR, SĐT công ty, logo (tệp **public**), OA ID, nội dung chính sách/điều
   khoản (đang là bản mẫu), bật/tắt từng tính năng.
3. Gán role **Payroll Officer** cho người C&B được xem/nhập lương. HR Manager **không** có quyền xem lương.
4. Report **Portal Readiness**: sửa SĐT trống/trùng, nhập `leave_approver` (cần trước M3).

## Đăng nhập: Zalo User ID + SĐT (contract §2.2, §2.6)

- Zalo **luôn** xác nhận User ID (server gọi `/v2.0/me` bằng `access_token`). SĐT đến từ Zalo (`phone_token`)
  hoặc từ `TIQN Portal Account.phone` (HR gán tay → `phone_source = Manual`; Zalo xác nhận → `Zalo`, luôn thắng).
- Nhân viên không cấp quyền SĐT → app hiện Zalo User ID → HR mở **TIQN Portal Account** (hoặc report
  Portal Readiness → "Waiting for Phone") → nhập SĐT. Form chặn số không khớp nhân viên nào; đổi số = huỷ mọi
  phiên của tài khoản.
- **Tự khoá tài khoản mới** (chặn người ngoài công ty + người nghỉ quá hạn): tài khoản mới (do `login`, `dev_login`
  hay HR tạo) bắt đầu với `disabled = 1` + `auto_disabled = 1`, **trừ khi** SĐT khớp nhân viên `Active` hoặc `Left`
  còn trong `read_only_days` (30 ngày từ `relieving_date`). Khi điều kiện đó thành đúng (HR gán SĐT, Zalo trả SĐT,
  người cũ vào lại có mã mới) tài khoản **tự mở khoá**. HR khoá tay (`auto_disabled = 0`) thì không bao giờ tự mở.
  `login` vẫn trả `NO_PHONE`/`NOT_FOUND`/`EXPIRED` cho tài khoản tự khoá (không trả `DISABLED`) để app hiện đúng màn.
- **Simulator** (`dev_login`): tin User ID client gửi → rào 2 lớp: `bench --site erp.tiqn.local set-config
  employee_portal_dev_login 1` **và** tick "Allow Dev Login" + gán SĐT trên tài khoản. Phiên dev 1 ngày, chết
  ngay khi tắt cờ/bỏ tick. ⚠ Người cầm ID simulator đã tick thấy dữ liệu THẬT của nhân viên được gán — chỉ gán
  SĐT nhân viên test. Tắt cờ khi không dev: `set-config employee_portal_dev_login 0`.

## Vận hành phiếu lương

List **TIQN Payslip → Import from Excel** (hoặc `/app/payslip-upload`) → Tải template → điền Excel
(`Period | Period From | Period To | Employee | Employee Name | Department | Section | Group | 44 khoản`) →
Upload → xem lỗi/cảnh báo → Nhập dạng Draft → `/app/payslip-upload` → **Phát hành** kỳ.
Sai thì **Thu hồi** → sửa → upload lại → phát hành lại.
- Không dùng Data Import chuẩn của Frappe: phiếu có bảng con 44 dòng, HR không nhập nổi.
- Tiêu đề cũ (`Kỳ lương | MSNV | Họ tên | dept | custom_section | custom_group`) vẫn đọc được.
- `Period` nhận `YYYY-MM`, `MM-YYYY` hoặc ô ngày. `Period From/To` không bắt buộc; có thì phải đúng 26→25 của kỳ,
  lệch là **lỗi** (phiếu luôn lưu ngày chuẩn, không lưu ngày trong file).
- Cột khoản lương nhận theo **mã số đầu tiêu đề** (`3.2 …`), không theo toàn bộ tên.
- Lỗi (chặn): MSNV không có, trùng dòng, ô không phải số, cột lạ, kỳ đã phát hành.
- Cảnh báo (xác nhận rồi vẫn nhập): `3=1+2`, `5=3+3.1+4`, `9=5−6+7+8`, tổng nhóm = tổng dòng con, tên khác ERP,
  NV nghỉ trước kỳ, thực lĩnh âm. **Không bao giờ tự sửa số của HR.**
- File Excel upload bị xoá khỏi `File` ngay sau khi nhập (chứa lương cả kỳ).
- Nhóm/nhãn/thứ tự hiển thị: tab **Employee Portal** trên form Salary Component (`custom_portal_*`).

## Test

```bash
cd ~/frappe-bench/sites && ../env/bin/python -c "
import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
exec(open('../apps/customize_erpnext/customize_erpnext/employee_portal/test_employee_portal.py').read())"
```
Rollback toàn bộ; dùng zalo id `unit-<uuid>` và kỳ 2030-xx để không đụng dữ liệu nhóm test.

Data test (số giả, TIQN-0148 + TIQN-1405, kỳ 07–09/2026):
`bench --site erp.tiqn.local execute customize_erpnext.employee_portal.seed_test_payslips.execute` · `.verify` · `.purge`

## 🔴 Bẫy đã vấp

1. **`bench migrate` nạp fixtures SAU patch `post_model_sync`.** Patch cấu hình Salary Component ghi vào cột
   `custom_portal_*` chưa tồn tại → `setup_employee_portal.ensure_portal_custom_fields()` tự tạo đúng các field đó
   từ `fixtures/custom_field.json` trước.
2. **Trang www có dấu `-` phải là thư mục `ten-trang/index.html + index.py`.** `portal-policy.py` đặt cạnh
   `portal-policy.html` không bao giờ được gọi; Jinja `DebugUndefined` in nguyên `{{ page_title }}` ra trang,
   không lỗi gì.
3. **`frappe.set_user()` ghi đè `session.sid` và xoá `form_dict`.** Endpoint chạy dưới `portal@` rồi phải trả về
   Guest trong `finally` (`_restore_guest`), nếu không `Session.update()` cuối request ghi session rác cho user dịch vụ.
4. **`frappe.get_request_header()` ném `RuntimeError` ngoài HTTP request** (bench execute, test) → dùng
   `core.request_header()`.
5. **Single DocType trả ngày dạng chuỗi** → `fmt_date()` đi qua `getdate()`.
6. **Thông báo lưu sẵn chữ → phải dịch sang tiếng Việt LÚC LƯU** (`notify()` dùng `_(…, lang="vi")`). Dịch theo
   ngôn ngữ người bấm Phát hành (Desk tiếng Anh) là gửi "Payslip 09/2026" cho cả công ty.
7. **Frappe rollback mọi request GET.** `get_payslip` là POST (ghi log xem). `last_seen`/thu hồi phiên trong GET
   được commit riêng (`commit_if_get`) — lúc đó chưa ghi gì khác.
8. **Lỗi nghiệp vụ = `frappe.db.rollback()` trong decorator** — đúng ở production, nhưng sẽ xoá dữ liệu test giữa
   chừng → test vá rollback/commit thành no-op. Riêng thu hồi phiên phải sống qua rollback đó → `_invalid()` commit trước.
9. **Không dùng `Authorization: Bearer` cho token portal** — Frappe coi là OAuth, token lạ → 401 trước khi tới code.
10. **SĐT so theo 9 số cuối**: ~1.140 hồ sơ mất số 0 đầu (Excel). Trùng số → mã NV mới nhất thắng
    (`date_of_joining DESC, name DESC`); 2 cặp NV đang làm trùng số thật — xem report Portal Readiness.
11. **`Employee.status` có giá trị `"Left "` (dấu cách)** → luôn `strip()`.
12. **Thêm hàm/tham số mới vào file .py worker đã nạp = cần `bench restart`.** Lần đầu module mới thì không cần
    (worker chưa từng import) — đã kiểm bằng HTTP thật 12/10.
14. **Phiên bị huỷ phải báo đúng lý do đã lưu** (`revoked_reason`): HR đổi SĐT huỷ phiên ở `on_update`, request
    sau thấy `revoked=1` — trả `REVOKED` chung chung là Mini App không biết hiện màn nào. Lý do lưu dạng
    `STATUS_CHANGED:EXPIRED` để các request chạy song song (app mở gọi `me` + `get_home` cùng lúc) trả cùng một màn.
15. **Upload lại phiếu Withdrawn phải giữ Withdrawn**, đừng đưa về Draft: phiếu đã phát hành một lần có View Log +
    thông báo trỏ tới → "Delete Drafts" xoá sẽ vấp LinkExistsError. Publish nhận cả Draft lẫn Withdrawn.
13. **Không cấp role `Leave Approver` cho trưởng bộ phận** (M3): role đó đọc MỌI đơn nghỉ công ty. Họ thấy đơn nhờ
    DocShare — HRMS tự share khi người duyệt chưa có quyền submit.
