# Employee Portal — backend cho Zalo Mini App "Cổng nhân viên"

> Hợp đồng với đội Mini App: [`API_CONTRACT.md`](./API_CONTRACT.md) — **nguồn chính** cho mọi request/response
> (bản 1.5.0, nhật ký thay đổi ở §13).
> Plan + quyết định đã chốt với user: `~/frappe-bench/.claude/plans/` — `zalo_payslip_portal.md` (gốc),
> `employee_portal_payslip_paper_layout.md`, `employee_portal_link_request.md`, `employee_portal_simplify_v3.md`.
> File này ghi cách cài, cách vận hành và **các bẫy đã vấp** khi code.

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
| M3 | Đơn nghỉ, giấy tờ, giải trình, duyệt trên Desk | chưa |
| M4 | Tin OA | chưa |

## Quyền — role `CnB`

**CnB** (Compensation & Benefits) + **System Manager** là 2 role duy nhất vào được portal: trang Payslip Upload,
TIQN Payslip, report Payslip Period Summary, TIQN Portal Notification / Account / Link Request / Session,
Employee Portal Settings. HR Manager **không** xem được lương (quyết định 12/10). Role tạo bằng patch
`create_cnb_role` (pre_model_sync — DocPerm trỏ tới role); **gán người do Admin làm**.
CnB không có quyền trên Salary Component / Employee — người CnB thường đã có HR User; sửa nhãn hiển thị trên
Salary Component (tab Employee Portal) cần HR Manager / System Manager.

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
| `utils/zalo_graph.py` | gọi `graph.zalo.me` (user id, tên, SĐT) + dịch mã lỗi Zalo |
| `employee_portal/utils.py` | kỳ 26→25, SĐT (9 số cuối, `cell_number` rồi `custom_cell_phone_zalo`), quyền theo trạng thái NV, field khoản lương |
| `employee_portal/payslip_admin.py` | Desk: file mẫu (tháng / NV nghỉ việc), preview, nhập Draft, phát hành, thu hồi |
| `employee_portal/page/payslip_upload/` | trang Payslip Upload |
| `employee_portal/doctype/tiqn_payslip/tiqn_payslip_list.js` | nút **Import from Excel** ở list TIQN Payslip (cùng API) |
| `employee_portal/report/payslip_period_summary/` | 1 kỳ: phát hành / đã xem / chưa xem + bảng các khoản chính |
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
     hiện dòng 0; **Check Formulas on Import**; bảng **Day / Hour Columns** (dòng phiếu có số ngày/giờ cạnh số tiền:
     1.2 Day, 2.1–2.3 Hour, 7.4–7.5 Day — mỗi dòng cần field `sc_<mã>_qty` trên TIQN Payslip).
   - Access: hạn chỉ xem sau nghỉ việc (30 ngày), số ngày phiên, phiên bản Mini App tối thiểu.
   - Zalo OA & Chat: **ID by OA** của người C&B (nút "Chat với C&B"), OA ID.
   - Legal: nội dung chính sách / điều khoản (công khai ở `/portal-policy`, `/portal-terms`).
3. Gán role **CnB** cho người C&B.

## Đăng nhập: Zalo User ID + SĐT (contract §2.2, §2.6)

- Zalo **luôn** xác nhận User ID (server gọi `/v2.0/me` bằng `access_token`). SĐT đến từ Zalo (`phone_token`)
  hoặc từ `TIQN Portal Account.phone` (HR gán tay → `phone_source = Manual`; Zalo xác nhận → `Zalo`, luôn thắng).
- SĐT khớp `Employee.cell_number` trước; không ai có số đó mới so `custom_cell_phone_zalo` (SĐT Zalo khác SĐT hồ sơ).
- Không cấp quyền SĐT → app hiện Zalo User ID → CnB mở **TIQN Portal Account** → nhập SĐT. Form chặn số không khớp
  nhân viên nào; đổi số = huỷ mọi phiên của tài khoản.
- **Yêu cầu liên kết** (`NOT_FOUND`): nhân viên gửi mã NV + họ tên → **TIQN Portal Link Request** (Pending). CnB
  **gọi lại SĐT Zalo** trên phiếu để chắc đúng người (mã + tên không bí mật), xem khung cảnh báo, rồi **Approve**
  (ghi SĐT Zalo vào `custom_cell_phone_zalo`, có Version) hoặc **Reject** (lý do hiện trên app). Tối đa 3 yêu cầu/ngày/Zalo.
- **Tự khoá tài khoản mới** (chặn người ngoài + người nghỉ quá hạn): tài khoản mới bắt đầu `disabled = 1` +
  `auto_disabled = 1`, trừ khi SĐT khớp NV `Active` hoặc `Left` còn trong hạn chỉ xem; tự mở khi điều kiện thành
  đúng. Khoá tay (`auto_disabled = 0`) không bao giờ tự mở. `login` vẫn trả `NO_PHONE`/`NOT_FOUND`/`EXPIRED`.
- **Simulator** (`dev_login`): tin User ID client gửi → rào 2 lớp: `bench --site erp.tiqn.local set-config
  employee_portal_dev_login 1` **và** tick "Allow Dev Login" + gán SĐT. Phiên dev 1 ngày. ⚠ Chỉ gán SĐT nhân viên
  test. Tắt khi không dev: `set-config employee_portal_dev_login 0`.
- Giới hạn `login`: 3000/phút/IP (cả nhà máy chung 1 IP WiFi) + 10 lần/10 phút/Zalo ID.

## Vận hành phiếu lương

1. **Payslip Upload → Download Template**:
   - *Hằng tháng* — chọn kỳ: NV còn làm tới cuối kỳ. **Không** gồm: nghỉ trước/trong kỳ, thai sản phủ cả kỳ
     (`Employee Maternity`), **Exclude Employees** của Attendance Calculation Setting. Vào giữa kỳ → Period From = ngày vào.
   - *Resigned Employees Only* — chọn khoảng ngày nghỉ: mỗi NV ở kỳ chứa ngày làm cuối, Period To = ngày nghỉ − 1,
     Pay Date = ngày nghỉ + 14 (trả riêng, HR tự tính).
2. Điền số → **Upload Excel** → xem lỗi/cảnh báo → **Import as Draft**.
3. Bảng "2. Publish" → **Publish** kỳ. Phiếu tháng: tạo **1 thông báo chung** cho kỳ. Chỉ toàn phiếu NV nghỉ việc
   (`final_settlement`, tự suy từ `relieving_date` trong kỳ): **không** thông báo — HR tự nhắn họ.
4. Sai → **Withdraw** → sửa → upload lại → Publish. **Delete Drafts** xoá phiếu nháp chưa từng phát hành.
5. Theo dõi: report **Payslip Period Summary** (Published / Viewed / Not Viewed, các khoản 1, 2, 5, 6, 9, ngày xem đầu).

File Excel: `No. | Period | Period From | Period To | Pay Date | Employee | Employee Name | Designation |
Department | Section | Group | <khoản>`.
- `No.` và `Designation` chỉ để HR nhìn, không đọc lại. Tiêu đề cũ (`Kỳ lương | MSNV | Họ tên | …`) vẫn đọc được.
- Cột khoản nhận theo **mã số đầu tiêu đề** (`3.2 …`); cột `… - Days` / `… - Hours` (cũ: `Unit/ĐVT`) = số ngày/giờ.
- `Period From/To` phải nằm trong kỳ 26→25; trống = tự tính. `Pay Date` trống = ngày trả lương tháng (hoặc nghỉ + 14).
- Lỗi (chặn): MSNV không có, trùng dòng, ô không phải số/ngày, cột lạ, ngày ngoài kỳ, kỳ đã phát hành.
- Cảnh báo (xác nhận rồi vẫn nhập): tên khác ERP, NV nghỉ trước kỳ; nếu bật **Check Formulas on Import**: `3=1+2`,
  `5=3+3.1+4`, `9=5−6+7+8`, tổng nhóm = tổng dòng con, thực lĩnh âm. **Không bao giờ tự sửa số của HR.**
- File upload bị xoá khỏi `File` ngay sau khi nhập/huỷ (chứa lương cả kỳ).
- Khoản lương = field `sc_<mã>` trên TIQN Payslip (`3.2` → `sc_3_2`), số ngày/giờ = `sc_<mã>_qty`. Nhãn / nhóm /
  cha–con / thứ tự hiển thị: tab **Employee Portal** trên Salary Component (`custom_portal_*`). Thiếu field cho một
  khoản → trang Payslip Upload hiện cảnh báo đỏ.
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
15. **Upload lại phiếu Withdrawn phải giữ Withdrawn** — Publish nhận cả Draft lẫn Withdrawn; Delete Drafts không đụng.
16. **Field SĐT Zalo trên Employee tên `custom_cell_phone_zalo`** (không phải `…_number_…`). Code cũ đọc nhầm tên →
    cột bị bỏ qua im lặng (`has_field` = False) tới 24/10.
17. **`frappe.call` mặc định POST** → endpoint `@frappe.whitelist(methods=["GET"])` phải gọi với `type: 'GET'`,
    không thì 403 "Not permitted" (bảng kỳ lương Payslip Upload trống tới 24/10).
18. **File mẫu trống vẫn import trót lọt** (toàn 0 thì công thức vẫn "đúng") — kiểm số dòng ở màn xem trước.
19. **`scripts/build_navigation.py` ghi đè toàn bộ file sidebar/icon** — link thêm tay vào JSON (Quiz trong New
    Joiners) phải đưa vào script, không thì lần chạy sau mất.
