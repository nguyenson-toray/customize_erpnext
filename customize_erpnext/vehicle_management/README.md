# Vehicle Management (TIQN) — ERPNext backend cho Zalo Mini App

Triển khai theo `customize_erpnext/vehicle_management/README.md`.
**File này là nguồn chính.** Đọc hết trước khi sửa bất cứ thứ gì trong module.

**Tài liệu của module — chỉ có hai file, không còn prompt nào ở thư mục gốc app:**

| File | Dùng khi |
|---|---|
| `README.md` (file này) | Cài đặt, kiến trúc, **các bẫy đã vấp**. Đọc trước khi sửa code. |
| [`API_CONTRACT.md`](./API_CONTRACT.md) | Giao diện với Zalo Mini App: endpoint, định dạng, trạng thái, quyết định đã chốt. Đọc khi nối thêm client. |

Chín file `ERPNEXT_*.md` ở thư mục gốc app (spec ban đầu, hợp đồng API, trả lời của đội Mini
App, kịch bản dữ liệu test, spec trang, prompt Excel) **đã xoá** — nội dung còn giá trị đã
gom hết vào hai file trên.

Module Frappe: `Vehicle Management` (đã khai trong `modules.txt`).
Trang điều hành: **`/app/vehicle-dispatch`**.
API: `customize_erpnext/api/vehicle_management.py`.

---

## 0. 🔴 Mô hình nghiệp vụ — đọc trước, nó quyết định mọi luật KM

**Xe và tài xế là của công ty đối tác.** TIQN **trả tiền theo SỐ KM THỰC TẾ TỪNG CHUYẾN**,
không quan tâm nhiên liệu, không quản lý tài sản xe.

Hệ quả, và đây là chỗ dễ làm sai nhất:

| Kiểu lệch KM giữa 2 chuyến liên tiếp cùng xe | Nghĩa | Xử lý |
|---|---|---|
| **HỤT** — `km_start` > `km_end` chuyến trước | Đối tác chạy việc riêng giữa hai chuyến | **Vô hại.** TIQN không trả cho đoạn đó. Chỉ in ra cho biết, đừng báo lỗi. |
| **ĐÈ** — `km_start` < `km_end` chuyến trước | Hai chuyến khai trùng một đoạn đường | 🔴 **TRẢ TIỀN HAI LẦN.** Đây mới là cái phải bắt. |

Server chặn "đè" **trong cùng một ngày** (`validate_odometer_continuity`). Qua ngày thì cố ý
**không chặn** — chặn sẽ cản việc nhập bù chuyến cũ — nhưng `seed_test_data.verify()` có
kiểm và báo FAIL nếu phát hiện.

Đơn vị tính tiền là `total_km` của từng chuyến (`km_end - km_start`), đúng thứ báo cáo KM và
file Excel đang cộng.

---

## 1. Đã có gì

| Thành phần | Vị trí |
|---|---|
| 8 DocType `TIQN *` | `vehicle_management/doctype/` |
| 32 REST endpoint | `api/vehicle_management.py` |
| Trang điều hành | `vehicle_management/page/vehicle_dispatch/` → `/app/vehicle-dispatch` |
| Role `Vehicle Manager` | patch `create_vehicle_manager_role` (pre_model_sync) |
| Dữ liệu mồi 3 xe / 3 tài xế / 6 lịch cố định | patch `seed_vehicle_management_data` (post_model_sync) |
| ZNS (Phase 2, **đang TẮT**) | `utils/zns.py` |
| Test đầu-cuối 230 assert |
| Report KM chuẩn Frappe | `vehicle_management/report/tiqn_vehicle_km/` |
| Sidebar module | `workspace_sidebar/vehicle_management.json` |
| Desktop icon | `desktop_icon/vehicle_management.json` + `public/images/vehicle_dispatch.svg` | `vehicle_management/test_vehicle_management.py` |
| Dữ liệu demo CẢ THÁNG | `vehicle_management/seed_month.py` ← đang dùng |
| Dữ liệu demo 14–16/09 (bộ cũ) | `vehicle_management/seed_test_data.py` |

### DocType

```
TIQN Vehicle              TIQN-VEH-###
TIQN Driver               TIQN-DRV-###
TIQN Zalo Role Map        name = zalo_user_id
TIQN Vehicle Request      TIQN-REQ-YYYY-####
TIQN Vehicle Trip         TIQN-TRIP-YYYY-####
  └ TIQN Trip Passenger   (child)
  └ TIQN Trip Stop        (child)
TIQN Fixed Trip Schedule  TIQN-FST-###
```

Không DocType nào link tới `Employee` hay `User` — đúng nguyên tắc thiết kế của spec:
tài xế là người của nhà xe thuê ngoài, người yêu cầu không có tài khoản ERPNext.

> ⚠ `Vehicle List` / `Vehicle Trip` (không có tiền tố TIQN) là **hệ cũ**, vẫn còn dữ liệu
> thật và **không bị đụng tới**. Đừng nhầm hai hệ. Biển số/xe trong patch mồi được chép
> từ hệ cũ sang.

---

## 2. Việc admin PHẢI làm trước khi Mini App chạy thật

Patch mồi cố tình **không** điền những thứ dưới đây — không ai cung cấp số liệu, và một
số điện thoại bịa trong hệ điều xe còn tệ hơn ô trống.

1. **SĐT tài xế** — `TIQN Driver.phone` đang rỗng cả 3 bản ghi.
2. **Zalo User ID tài xế** — `TIQN Driver.zalo_user_id` đang rỗng.
3. **`TIQN Zalo Role Map`** — đang **0 bản ghi**. Phải nhập cho mỗi tài xế (`role=driver`,
   trỏ `driver_ref`) và mỗi Dispatcher/Manager (`role=dispatcher`). Không có bản ghi này
   thì `get_user_by_zalo_id` trả `null` và Mini App không nhận diện được ai cả.
4. **Gán role `Vehicle Manager`** cho các tài khoản Dispatcher/Manager hiện có
   (User → Roles). Patch chỉ *tạo* role, cố ý không gán cho ai.
5. ~~**API user dùng chung cho Mini App**~~ — ✅ ĐÃ TẠO: `miniapp@tiqn.com.vn`
   (System User, **chỉ** role `Vehicle Manager`, không đặt mật khẩu nên không đăng nhập
   Desk được, chỉ dùng API Key). Mini App gửi `Authorization: token <key>:<secret>`.
   Key/secret đưa riêng cho admin, **không** ghi vào repo.

   🔴 **ĐỪNG dùng API key của `Administrator` cho Mini App.** Key nhúng trong client
   bundle là key công khai — ai giải nén app ra cũng đọc được. Key Administrator lộ =
   mất toàn bộ ERP (lương, HR, kho). Key `miniapp@` lộ thì chỉ chạm được dữ liệu xe;
   đã kiểm chứng: `has_permission("Salary Slip")` và `("Employee")` đều **False**.
6. ~~**CORS**~~ — ✅ `common_site_config.json` đã có sẵn `allow_cors: "*"` (đặt từ
   29/07/2026, trước module này). Preflight đã kiểm chứng: trả đúng
   `Access-Control-Allow-Origin` + `Allow-Credentials`.

   ⚠ `"*"` nghĩa là **mọi website** đều gọi được API kèm cookie phiên của user đang
   đăng nhập ERP. User đã quyết định GIỮ NGUYÊN (15/09/2026). Muốn siết lại thì đổi
   `allow_cors` thành danh sách domain cụ thể — nhớ đây là config CHUNG cho mọi site
   trên bench và cần `bench restart`.

---

## 3. Quy tắc nghiệp vụ nằm ở CONTROLLER, không chỉ ở API

Đây là điểm dễ hiểu sai nhất. Dispatcher sửa trực tiếp trên form Desk cũng phải chịu
đúng luật như Mini App gọi API, nên các quy tắc dưới đây nằm trong `validate` /
`on_update` của DocType:

| Quy tắc | Ở đâu |
|---|---|
| Chuyển trạng thái chuyến chỉ đi 1 chiều (`scheduled → confirmed → in_progress → completed`) | `tiqn_vehicle_trip.py: ALLOWED_TRANSITIONS` |
| Chuyển trạng thái yêu cầu (`pending → approved → assigned` \| `rejected`) | `tiqn_vehicle_request.py: ALLOWED_TRANSITIONS` |
| `km_end > km_start`, `total_km` tự tính | `tiqn_vehicle_trip.py: validate_km / set_total_km` |
| Xe tự đổi `available` ↔ `in_trip` theo chuyến | `tiqn_vehicle_trip.py: sync_vehicle_status` |
| Yêu cầu đi theo chuyến (hủy chuyến → yêu cầu quay về `approved`) | `tiqn_vehicle_trip.py: sync_linked_requests` |

🔴 **`sync_vehicle_status` KHÔNG đụng vào xe đang `maintenance` / `broken`.** Manager đặt
xe vào hai trạng thái đó là có chủ đích; để check-in tự kéo về `available` là mất cảnh báo
hỏng hóc.

🔴 **`in_trip` không đặt tay được.** `update_vehicle_status` chỉ nhận
`available` / `maintenance` / `broken`, và từ chối đổi trạng thái khi xe đang có chuyến
`in_progress`.

---

## 4. Các bẫy đã gặp (đừng gặp lại)

**`order` là từ khóa SQL.** Spec ghi field `order` cho 2 bảng con; ở đây đổi thành
`pickup_order` và `stop_order`. Bảng mapping camelCase ở mục 6 của spec không có `order`
nên không phá hợp đồng với Mini App. Đừng "sửa lại cho đúng spec".

**Sửa `modules.txt` xong phải `bench clear-cache` TRƯỚC khi migrate.** Frappe cache map
module trong redis (`setup_module_map` → key `app_modules`). Lần migrate đầu tiên của
module này im lặng bỏ qua toàn bộ 8 DocType vì cache còn cũ, rồi patch mồi chết với
`Table 'tabTIQN Vehicle' doesn't exist`.

**Role phải tồn tại TRƯỚC model sync.** Mỗi DocType mang sẵn dòng DocPerm trỏ
`Vehicle Manager`, mà `DocPerm.role` là Link. Vì thế `create_vehicle_manager_role` nằm ở
`[pre_model_sync]`. Đừng chuyển nó xuống `[post_model_sync]`.

**v16 cấm hàm SQL dạng chuỗi trong `fields`.** `fields=["count(name) as cnt"]` ném
`ValidationError`. `get_today_stats` đếm trong Python thay vì `group_by` ở DB.

**`**kwargs` trong hàm `@whitelist` nhận NGUYÊN `form_dict`.** `frappe.get_newargs` đẩy
hết mọi key qua khi hàm khai báo `**kwargs`, kể cả `cmd`/`csrf_token`. `update_trip` lọc
bằng `FRAMEWORK_ARGS` + whitelist field `TRIP_EDITABLE_FIELDS`, nếu không `doc.set("cmd", …)`
sẽ ghi rác vào document.

**Ngày trên trang Desk** lấy bằng `frappe.datetime.get_today()`. `Date.toISOString()` đổi
sang UTC và lệch 1 ngày ở GMT+7.

---

## 5. Danh sách endpoint

Base: `https://erp.tiqn.com.vn:8888/api/method/customize_erpnext.api.vehicle_management`

| Method | Endpoint | HTTP |
|---|---|---|
| Auth | `get_user_by_zalo_id` | GET |
| Request | `get_requests` · `get_my_requests` · `get_request` | GET |
| | `create_request` | POST |
| | `approve_request` · `reject_request` · `assign_request_to_trip` · `combine_requests_to_trip` | POST/PUT |
| Trip | `get_trips` · `get_trip` · `get_today_trips_by_driver` · `get_last_completed_trip_by_vehicle` · `get_fixed_templates_for_driver` | GET |
| | `create_trip` · `create_trip_from_template` | POST |
| | `update_trip` · `confirm_trip` · `cancel_trip` · `update_trip_route` · `checkin_trip` · `checkout_trip` · `acknowledge_route_change` | POST/PUT |
| Vehicle | `get_vehicles` · `get_drivers` | GET |
| CRUD chung | `update_request` · `update_trip` · `update_vehicle` | POST/PUT |
| Auth (Phase 1) | `verify_driver_login` | POST |
| | `update_vehicle_status` | POST/PUT |
| Report | `get_trip_report` · `get_today_stats` · `get_dispatch_overview` | GET |

Ba endpoint **ngoài spec**, thêm vì trang Dispatcher cần: `get_drivers`,
`get_dispatch_overview` (gộp toàn bộ 4 panel vào 1 request) và field `total_km` trên Trip
(spec mục 3.5 đòi tổng KM nhưng data model không có chỗ chứa).

`create_trip_from_template` **idempotent**: gọi lại trong cùng ngày trả về đúng chuyến cũ,
không tạo trùng. Tài xế bấm 2 lần vì mạng chậm cũng không sinh chuyến ma.

---

## 6. Realtime

Mọi endpoint thay đổi dữ liệu bắn `tiqn_vehicle_dispatch_update` (after_commit) →
trang Dispatcher tự nạp lại. Ngoài ra `update_trip_route` bắn thêm
`tiqn_trip_route_changed` kèm `driver` để Mini App của tài xế hiện cảnh báo.

Trang vẫn giữ timer 30 giây làm phương án dự phòng khi socket chết, nhưng chỉ chạy khi
trang đang hiển thị (`is_visible()`).

---

## 7. ZNS — ĐANG TẮT, đừng tự bật

`utils/zns.py` viết sẵn nhưng **không có chỗ nào trong app gọi nó**. `send_zns()` mặc định
`dry_run=True`: chỉ ghi log, không gửi. Muốn gửi thật phải đủ 3 điều kiện trong
`site_config.json`: `zalo_zns_enabled`, `zalo_oa_access_token`, và template id của sự kiện.

Trước khi bật, hỏi user 3 câu: (1) nội dung tin nhắn đã chốt chưa, (2) chính xác ai nhận,
(3) chạy bulk thì bao nhiêu tin sẽ bay đi. Đây là hệ gửi tin tới **số điện thoại cá nhân**
của tài xế và nhân viên — gửi nhầm không thu hồi được.

---

## 8. Test

```bash
cd ~/frappe-bench/sites && ../env/bin/python -c "
import frappe; frappe.init('erp.tiqn.local'); frappe.connect(); frappe.set_user('Administrator')
exec(open('../apps/customize_erpnext/customize_erpnext/vehicle_management/test_vehicle_management.py').read())"
```

230 assert, kết thúc bằng `frappe.db.rollback()`.

⚠ Teardown **chỉ** được rollback. Đừng thêm đoạn xóa `tabSeries` — mất dòng series là
không ai tạo được chứng từ mới nữa (sự cố Leave Application 21/08/2026).

---

## 9. Sai khác so với spec (có chủ đích)

| Spec | Thực tế | Lý do |
|---|---|---|
| Field `order` ở 2 bảng con | `pickup_order` / `stop_order` | `order` là từ khóa SQL |
| Preset "Xe 01 Innova Crysta / Xe 02 Ford Transit / Xe 03 KIA" | Bus 1 (43B-043.95) · Bus 2 (76F-000.52) · Kia (76H-058.34) | Spec ghi "biển số thực tế"; đây là đội xe thật, lấy từ `Vehicle List` |
| Giờ template 06:30 / 17:15 | Giữ đúng 06:30 / 17:15 | **Cần user xác nhận**: scheduler hệ cũ dùng 05:30 / 17:00 |
| Preset tên tài xế A/B/C | Mồi từ `Vehicle List`, admin đã sửa lại đúng tên trong UI | Patch key theo **xe**, không theo tên, nên đổi tên không sinh bản ghi trùng |
| SĐT + Zalo ID trong preset | Để trống | Không ai cung cấp số liệu |

---

## 10. Phase 1 — Đăng nhập tài xế bằng mật khẩu

Theo `vehicle_management/API_CONTRACT.md mục 7`. Đây là cơ chế **tạm**; Phase 2 chuyển sang Zalo
User ID thì phải **gỡ** field `password` và endpoint `verify_driver_login`, đừng để lại.

| Thứ | Vị trí |
|---|---|
| Field `password` (fieldtype `Password`) | `TIQN Driver` |
| `get_drivers()` — danh sách chọn tài xế | `api/vehicle_management.py` |
| `verify_driver_login(driver_name, password)` | `api/vehicle_management.py` |
| Mật khẩu mồi `driver01/02/03` | patch `seed_vehicle_driver_passwords` |

### 🔴 `Password` fieldtype MÃ HÓA, KHÔNG băm

Spec ghi "Frappe's Password fieldtype tự động hash khi lưu" — **sai**. Frappe lưu vào bảng
`__Auth` với `encrypted=1` (Fernet, giải mã ngược được bằng encryption key của site).
Hệ quả thực tế:

1. **`check_password()` KHÔNG BAO GIỜ verify được field này.** Hàm đó chỉ truy vấn dòng
   `encrypted = 0` (mật khẩu User, băm bằng passlib). Nhánh chính trong spec chạy là sai;
   phải dùng `doc.get_password("password")` (hoặc `get_decrypted_password`).
2. **Ai có DB + encryption key đọc được mật khẩu tài xế.** Đừng dùng lại mật khẩu này ở
   bất cứ đâu khác.
3. **Cột `tabTIQN Driver.password` chứa `"*" * len(mật khẩu)`** → lộ ĐỘ DÀI mật khẩu.
   Vì thế `get_drivers()` tuyệt đối không được `select` field `password`.

### Chống dò mật khẩu

`driver01` là 8 ký tự trong từ điển — script dò ra trong vài giây. `verify_driver_login`
khóa tài xế **15 phút sau 5 lần sai** (`MAX_LOGIN_ATTEMPTS` / `LOCKOUT_SECONDS`, đếm trong
redis cache). Thông báo lỗi cho tên tài xế sai và mật khẩu sai là **giống hệt nhau**, để
không xác nhận docname nào tồn tại.

### Mật khẩu hiện tại

Patch `seed_vehicle_driver_passwords` **chỉ đặt cho tài xế CHƯA có mật khẩu**, không bao
giờ ghi đè. Admin đã tự đặt mật khẩu trong UI thì giữ nguyên qua mọi lần `bench migrate`.
Đổi mật khẩu = mở record `TIQN Driver` trong Desk, gõ vào field *Mini App Password*, lưu.

### Login Manager

Dùng thẳng `POST /api/method/login` của Frappe (`{"usr", "pwd"}`) — không cần code thêm.

---

## 11. Phase 1 — 3 setter chung (`update_request` / `update_trip` / `update_vehicle`)

Theo `vehicle_management/API_CONTRACT.md mục 6`. Mini App đẩy thẳng field qua 3 endpoint này thay vì
gọi từng endpoint chuyên biệt.

### Vì sao setter chung mà VẪN an toàn

Vì **luật nghiệp vụ nằm trong controller, không nằm trong endpoint** (xem mục 3). Setter
chỉ `doc.set(...)` rồi `doc.save()`, nên vẫn chạy qua đủ:
`ALLOWED_TRANSITIONS` · `km_end > km_start` · liên tục công tơ mét ·
`total_km` · `sync_vehicle_status` · `sync_linked_requests`.

Nếu trước đây tôi nhét luật vào endpoint thì `update_trip` bây giờ đã là một lỗ thủng.

### 3 chỗ CỐ Ý làm khác đoạn code mẫu trong spec

| Spec mẫu | Ở đây | Lý do |
|---|---|---|
| `doc.save(ignore_permissions=True)` | `doc.save()` + `_guard()` | `ignore_permissions` cho **mọi** tài khoản ERPNext sửa được chuyến xe. Phân quyền là thứ duy nhất chặn nhân viên bất kỳ. User `miniapp@` có role `Vehicle Manager` nên không ảnh hưởng gì. |
| `frappe.db.commit()` cuối hàm | Không commit | Frappe tự commit cuối request. Commit trong hàm `@whitelist` phá transaction và làm **test rò dữ liệu vào DB thật**. |
| `passengers` = `Long Text` JSON | Giữ **child table** `TIQN Trip Passenger` | Bảng con đã có, đã test, và trang Dispatcher + `combine_requests_to_trip` + `sync_linked_requests` đều bám vào nó. Đổi sang Long Text là đập 3 thứ đang chạy. Spec cũng tự nói *"Hoặc dùng Child Table nếu muốn chuẩn hơn"* — ta đã chuẩn sẵn. |

`update_trip` **vẫn nhận** JSON array kiểu Mini App và tự map sang bảng con, chấp nhận cả
2 cách viết: `{requestId, name, fromLocation, order}` hoặc
`{request, passenger_name, pickup_location, pickup_order}`. Mỗi lần đẩy là **thay thế**
toàn bộ danh sách, không cộng dồn.

### Field được phép ghi

`TRIP_EDITABLE_FIELDS` / `REQUEST_EDITABLE_FIELDS` / `VEHICLE_EDITABLE_FIELDS` ở đầu
`api/vehicle_management.py`. Field **dẫn xuất** (`total_km`, `confirmed_at`, `template_id`)
cố ý nằm ngoài danh sách → gửi lên sẽ bị từ chối kèm tên field.

`notes` và `current_trip` spec có liệt kê nhưng **không tồn tại** trên DocType
(`current_trip` do `get_vehicles()` tính ra, không lưu) → nhận rồi bỏ qua, không ném lỗi,
để bản Mini App cũ còn gửi vẫn chạy.

### 🔴 `**kwargs` trong hàm `@whitelist` nhận NGUYÊN `form_dict`

`frappe.get_newargs` đẩy hết mọi key qua khi hàm khai báo `**kwargs` — kể cả `cmd`,
`csrf_token`. Không lọc thì `doc.set("cmd", "...")` ghi rác vào document. Cả 3 setter đi
qua `_clean_kwargs()`.

### Luồng mới: xếp xe = duyệt

`pending → assigned` giờ là bước hợp lệ (trước kia bắt buộc qua `approved`). `approved`
vẫn giữ trong options cho Desk nhưng Mini App không sinh ra nữa. Controller vẫn chặn:
`assigned` mà không có `assigned_trip` → lỗi; `rejected` mà không có lý do → lỗi.

### Dấu ngày giờ tự đóng trong controller

Đổi `status` sang `confirmed` / `in_progress` / `completed` mà chưa có
`confirmed_at` / `checkin_time` / `checkout_time` thì controller tự đóng dấu `now()`. Nhờ
vậy 2 đường (`checkin_trip()` chuyên biệt và `update_trip(status=...)`) cho ra **cùng một
bản ghi**.

### ⚠ Kiểm tra liên tục công tơ mét phải được GIỚI HẠN PHẠM VI

`validate_odometer_continuity()` chỉ chạy khi `km_start` **vừa đổi** trên chuyến **chưa
kết thúc**. Nếu chạy ở mọi lần save thì sửa ghi chú một chuyến sáng đã hoàn thành sẽ bị
từ chối chỉ vì chuyến chiều đã ghi KM cao hơn — một lỗi rất khó truy.

---

## 12. Phase 1 — Sửa nội dung yêu cầu + trạng thái `cancelled`

Bổ sung 15/09/2026 theo yêu cầu mới trên `vehicle_management/API_CONTRACT.md mục 6`.

### 2 field MỚI trên `TIQN Vehicle Request`

| Field | Kiểu | Ghi chú |
|---|---|---|
| `return_time` | Datetime | Giờ xe quay về. Để trống = đi một chiều. Controller chặn `return_time <= request_time`. |
| `notes` | Small Text | Ghi chú tự do của người yêu cầu, **khác** `purpose`. |

Cả hai trước đó **không tồn tại** — yêu cầu mới có liệt kê nên phải tạo, không chỉ mở
danh sách field cho ghi. `create_request()` cũng nhận thêm 2 tham số này.

### `status` thêm `cancelled`

`cancelled` = **người yêu cầu tự hủy**, khác hẳn `rejected` = **điều hành từ chối**. Giữ
2 trạng thái riêng để báo cáo phân biệt được, đừng gộp.

```
pending  → approved | assigned | rejected | cancelled
approved → assigned | rejected | cancelled
assigned → cancelled          ← kế hoạch đổi sau khi đã xếp xe là chuyện thường
rejected → (kết thúc)
cancelled→ (kết thúc)
```

`sync_linked_requests()` chỉ kéo yêu cầu đang `pending`/`approved` sang `assigned`, nên
yêu cầu đã hủy **không bị hồi sinh** khi chuyến được lưu lại. Có test riêng cho ca này.

> ⚠ Hủy một yêu cầu đã `assigned` **không** tự gỡ dòng hành khách khỏi chuyến — tài xế vẫn
> thấy tên đó. Điều hành phải tự xóa dòng trong chuyến. Cố ý để vậy (ngoài phạm vi yêu cầu),
> nhưng nếu thấy vướng thì đây là chỗ cần sửa.

### 🔴 Guard: nội dung chỉ sửa được khi còn `pending`

10 field nội dung (`CONTENT_FIELDS` trong `tiqn_vehicle_request.py`) chỉ ghi được qua
`update_request()` khi yêu cầu **còn `pending`**. Sau khi điều hành đã xử lý, âm thầm đổi
điểm đón hoặc giờ đi là đưa tài xế tới sai chỗ mà không có gì trên màn hình báo.

Field **workflow** (`status`, `rejection_reason`, `assigned_trip`) vẫn ghi được ở mọi trạng
thái — nếu không thì không hủy được chuyến đã xếp.

Guard đọc `doc.status` **trước** khi áp thay đổi, nên *sửa nội dung + hủy trong cùng một
lệnh* trên yêu cầu đang pending là hợp lệ.

**Guard nằm ở tầng API, CỐ Ý không đưa vào controller.** Admin sửa lỗi chính tả trên một
yêu cầu đã xếp qua Desk là việc chính đáng, mà Desk thì đi qua controller.

### 🔴 Danh sách "field bỏ qua" phải TÁCH THEO DOCTYPE

Trước đây có một `IGNORED_LEGACY_ARGS = {"notes", "current_trip"}` dùng chung. Giờ `notes`
là field **thật** của Request → nếu vẫn dùng chung thì ghi chú người dùng gõ sẽ bị **nuốt
im lặng**. Đã tách: `IGNORED_TRIP_ARGS` (`notes` — Trip không có field này) ·
`IGNORED_VEHICLE_ARGS` (`current_trip` — do `get_vehicles()` tính) · `IGNORED_REQUEST_ARGS`
(rỗng).

---

## 13. 🔴 Tên key của hành khách — sửa ở MỘT chỗ duy nhất

Mini App đã từng gửi **cả 2 kiểu**: camelCase (`requestId` / `fromLocation`) và snake_case
(`request_id` / `from_location`). Bản đầu chỉ nhận camelCase → `request_id` và
`from_location` bị **vứt trong im lặng**: không lỗi, không cảnh báo, chỉ là điểm đón trống
và hành khách không liên kết được về yêu cầu gốc.

Toàn bộ tên key gom vào `PASSENGER_ALIASES` trong `api/vehicle_management.py`. Thêm cách
viết mới thì **thêm vào đó**, đừng thêm ở chỗ gọi.

| Cột trong bảng con | Chấp nhận |
|---|---|
| `request` | `request` · `request_id` · `requestId` |
| `passenger_name` | `passenger_name` · `passengerName` · `name` (xem bẫy dưới) |
| `pickup_location` | `pickup_location` · `pickupLocation` · `from_location` · `fromLocation` |
| `pickup_order` | `pickup_order` · `pickupOrder` · `order` |

`create_trip` trước đây nhận **ít key hơn** `update_trip` — giờ cả hai dùng chung
`_build_passenger_rows()`, không còn lệch.

### `passenger_name` đang `reqd = 1`

Gửi lên mà thiếu tên thì Frappe ném `MandatoryError` khô khốc, không nói dòng nào. Thứ tự
lấy tên hiện tại:

1. `passenger_name` / `passengerName`
2. `name` — **chỉ khi** dict không hề có key `passenger_name`
3. `employee_name` của yêu cầu được link (`request`) ← ca phổ biến nhất
4. hết cách → báo lỗi **có số thứ tự dòng**: *"Passenger row 3 has no name…"*

Vẫn giữ `reqd = 1` vì dòng hành khách không tên thì tài xế cũng không dùng được. Muốn cho
phép trống thì hạ `reqd` trong `tiqn_trip_passenger.json` — nhưng nên cân nhắc.

### ⚠ Bẫy `name` khi đọc rồi đẩy ngược lại

`_serialise_trip()` trả về `name` = **docname của dòng con** (ví dụ `64la1mshho`), còn tên
người nằm ở `passenger_name`. Nếu code lấy `p.get('passenger_name') or p.get('name')` mà
`passenger_name` rỗng thì sẽ **ghi docname vào ô tên người**. Vì vậy quy tắc 2 ở trên chỉ
dùng `name` khi dict **không có** key `passenger_name` — tức là dòng do Mini App tự soạn,
không phải dòng vừa đọc về. Có test khoá ca này.

---

## 14. API Contract (vehicle_management/API_CONTRACT.md) — định dạng trên dây

### Định dạng BẮT BUỘC, không để Frappe tự serialise

| Kiểu | Frappe trả mặc định | Contract yêu cầu | Xử lý |
|---|---|---|---|
| Datetime | `2026-09-15 09:28:40.123456` | `2026-09-15 09:28:40` | `_fmt_datetime()` — cắt microsecond |
| Time | `6:30:00` (là `timedelta`!) | `06:30` | `_fmt_time()` |
| Date | `2026-09-15` | như cũ | `_fmt_date()` |

🔴 Cột Time của Frappe trả về **`datetime.timedelta`**, không phải `time` — `str()` ra
`6:30:00`, thiếu số 0 đầu. Mọi endpoint trả chuyến đều đi qua `_decorate_trips()`.

### `vehicle_name` / `license_plate` / `driver_name` là BẮT BUỘC

Contract đòi 3 field này có mặt mọi lúc. `_decorate_trips()` tra **1 câu query cho cả
danh sách**, không phải N+1. Trước đó chỉ trang Dispatcher tự ghép tên, `get_trips` trả
null → Mini App hiện ô trống.

### Key hành khách TRẢ VỀ theo contract

```json
{"passenger_name": "...", "from_location": "...", "request_id": "...", "order": 1, "row_name": "<docname dòng con>"}
```
Cột trong DB vẫn là `pickup_location` / `pickup_order` / `request`. `row_name` là tên dòng
con, tách hẳn khỏi `name` để không ai nhầm docname thành tên người (xem mục 13).

### GPS = Phase 2

`start_gps_*` / `end_gps_*` **đã gỡ khỏi `TRIP_EDITABLE_FIELDS`** theo contract. Cột và
tham số của `checkin_trip()` / `checkout_trip()` vẫn còn, sẵn cho Phase 2 — chỉ đóng cửa
`update_trip`.

### `TIQN Fixed Trip Template` → `TIQN Fixed Trip Schedule`

Đổi tên DocType + `template_name` → `schedule_name`, docname `TIQN-FTT-00x` →
`TIQN-FST-00x`, thêm `trip_name_template` và `days_of_week`. 2 patch:

- `rename_fixed_trip_template_to_schedule` (**pre**_model_sync) — phải chạy TRƯỚC sync, vì
  thư mục app giờ chỉ còn `tiqn_fixed_trip_schedule`; sync chạy trước sẽ coi DocType cũ là
  mồ côi và **xoá luôn 6 bản ghi**.
- `rename_fixed_trip_schedule_fields` (post_model_sync) — chuyển dữ liệu, drop cột mồ côi,
  đổi số docname, **và đẩy `tabSeries`**.

### 🔴 3 bẫy của đợt này

**1. `MultiSelect` KHÔNG tạo cột DB.** Contract ghi `days_of_week` kiểu MultiSelect. Fieldtype
đó nằm trong `no_value_fields` của Frappe: hiện widget nhưng **không có cột**, giá trị bay
sạch. Đã dùng `Data` chứa chuỗi phân cách bằng dấu phẩy — đúng như payload mẫu của chính
contract.

**2. Đổi tên document KHÔNG đẩy `tabSeries`.** Sau khi đổi 6 docname sang `TIQN-FST-00x`,
bộ đếm của prefix mới vẫn là 0 → bản ghi kế tiếp lại tên `TIQN-FST-001` và chết vì trùng
khoá chính. `_advance_series()` chỉ **nâng** bộ đếm, không bao giờ hạ hay xoá dòng
`tabSeries` (xem sự cố Leave Application 21/08).

**3. `frappe.rename_doc()` (wrapper ở `frappe/__init__.py`) KHÔNG nhận `ignore_permissions`.**
Chỉ `frappe.model.rename_doc.rename_doc` mới có.

### ⚠ Scheduler — `create_scheduled_trips()`

Cron trong `hooks.py`: `30 6 * * *` và `0 17 * * *`.

**Timezone:** Frappe chấm cron bằng `now_datetime()` = **giờ SITE**, không phải UTC. Đã
kiểm: `System Settings.time_zone = Asia/Ho_Chi_Minh` và đồng hồ máy chủ khớp → `30 6 * * *`
đúng là 06:30 giờ VN. Ghi chú "Frappe scheduler mặc định dùng UTC" trong contract **không
đúng** với bench này.
🔴 Nhưng cờ đó **hay tự lật về `Asia/Kolkata`** (xem `project_timezone_kolkata_bug`) — chuyến
cố định tự nhiên trễ ~1,5 tiếng thì kiểm chỗ đó TRƯỚC.

**Không `@frappe.whitelist()`** — hàm ghi bản ghi cho cả đội xe, không có lý do gì để gọi
được qua HTTP. Chạy tay:
```bash
bench --site erp.tiqn.local execute customize_erpnext.api.vehicle_management.create_scheduled_trips
```

**Idempotent** trên `(vehicle, trip_date, depart_time, trip_type=fixed)` — scheduler chạy
lại, chạy tay, hay tài xế bấm `create_trip_from_template()` trước đều không sinh trùng.

### 🔴 Test KHÔNG ĐƯỢC phép commit

`create_scheduled_trips()` gọi `frappe.db.commit()` vì nó là scheduler task — đúng ở
production, **chết người** trong test: một lần commit là flush TOÀN BỘ transaction đang mở,
`rollback()` cuối file không còn gì để hoàn tác.

Đã xảy ra thật: 25 chuyến, 7 yêu cầu, 3 tài xế, 1 xe test nằm lại DB thật, phải xoá tay.
`test_vehicle_management.py` giờ **vá `frappe.db.commit` thành no-op ngay đầu file**, trả lại
ngay trước `rollback()`, và có assert cuối cùng kiểm tra không còn bản ghi TEST nào sót.

---

## 15. Dung sai với client + dữ liệu demo

### Tha thứ cho client, nhưng chỉ ở chỗ vô hại

| Client gửi | Trước | Giờ |
|---|---|---|
| `"2026-09-15T07:28:40.415Z"` | MySQL ném `Incorrect datetime value` | `_normalise_dt_in()` cắt `T`/`Z`/ms |
| `start_g_p_s`, `startGPS`, … | Ném *"These fields cannot be updated"* | Nhận rồi **bỏ qua** (GPS là Phase 2) |

🔴 `_normalise_dt_in` **vứt chữ `Z`, KHÔNG quy đổi múi giờ**. Mini App dựng chuỗi từ giờ
VN rồi gắn thêm `Z` cho có; coi nó là UTC thật sẽ lệch mọi lần check-in **7 tiếng**.

🔴 `start_g_p_s` là `scrub()` của `startGPS` — Frappe tách từng chữ hoa. Đừng sửa thành
`start_gps` rồi tưởng đã xong; danh sách `IGNORED_TRIP_ARGS` giữ đủ mọi cách viết.

### 🔴 Xoá chuyến KHÔNG tự nhả xe (đã sửa)

Frappe **không** gọi `on_update()` khi xoá, nên xoá một chuyến đang `in_progress` để lại xe
kẹt `in_trip` vĩnh viễn, trên bảng điều hành không có gì giải thích. Gặp thật: Kia bận mà
không có chuyến nào. Đã thêm `TIQNVehicleTrip.on_trash()` gọi
`sync_vehicle_status(excluding_self=True)`.

### Dữ liệu demo — `seed_test_data.py`

```bash
# thêm vào, không xoá gì
bench --site erp.tiqn.local execute customize_erpnext.vehicle_management.seed_test_data.execute
# xoá sạch chuyến + yêu cầu rồi dựng lại
bench --site erp.tiqn.local execute customize_erpnext.vehicle_management.seed_test_data.execute --kwargs "{'purge': True}"
# đối chiếu toàn bộ check của PHẦN 3 + PHẦN 5
bench --site erp.tiqn.local execute customize_erpnext.vehicle_management.seed_test_data.verify
```

19 bản ghi cho 14–16/09/2026: CN không có chuyến cố định, T2 đủ mọi trạng thái, T3 là "hôm
nay" chưa chạy. **Không tạo và không đổi tên** xe/tài xế — đó là dữ liệu thật, tên tài xế
(Mr. Lương / Mr. Long / Mr. Duy) do admin đặt, tên mẫu trong prompt bị bỏ qua có chủ đích.

⚠ Bảng "Kết quả mong đợi" ở PHẦN 5 của prompt **tự mâu thuẫn** với bảng dữ liệu PHẦN 2 ở
3 con số. `verify()` in ra cả hai bên, không im lặng chỉnh số:

| | Bảng PHẦN 5 | Dữ liệu thực tế | Vì sao |
|---|---|---|---|
| 15/09 hoàn thành | 5 | **4** | PHẦN 2 chỉ liệt kê 4 chuyến completed (T03–T06) |
| 15/09 đã xếp xe | 1 | **2** | PHẦN 2 cho cả REQ02 và REQ03 = `assigned` |
| 16/09 chờ duyệt | 2 | **3** | REQ_15_04 vẫn chưa ai trả lời; KPI đếm mọi yêu cầu còn treo, không lọc theo ngày |

---

## 16. Xuất Excel + KPI đã chốt với Mini App

### `download_trip_report_excel(start_date, end_date, vehicle?, driver?)`

Trả `{url, filename, row_count, expires_in_minutes}`. Cột KM/Chi phí là **Number** đúng
kiểu (không phải text), dòng TỔNG CỘNG là **công thức `=SUM()` thật** nên lọc trong Excel
là tổng tự đổi theo.

**3 điểm quan trọng khi sửa hàm này:**

1. **Tên file PHẢI có hậu tố `YYMMDD_HHMMSS`.** Không có thì hai người xuất cùng khoảng
   ngày sẽ ghi đè file của nhau, và trong Downloads không ai biết file nào mới. Dùng `_`
   chứ **không dùng dấu cách** như quy ước chung của app — tên này đi vào URL cho
   `window.open()`, dấu cách ở đó là tự chuốc lỗi.
2. **Lưu qua DocType `File`, đừng `wb.save(path)` thẳng vào `public/files/`.** File ghi
   thẳng không có bản ghi nào quản lý, không ai dọn, không hiện ở đâu trong Desk.
3. **`cleanup_trip_report_exports` chạy `hourly`** dọn file cũ hơn 45 phút, đúng cách app
   đang dọn file export chấm công. Response trả `expires_in_minutes` để client biết link
   chỉ là tạm.

⚠ File là **public** — ai có URL đều tải được trong 45 phút. Chấp nhận được với báo cáo KM
nội bộ; muốn chặt hơn thì `private/files` + signed URL.

### 4 KPI — định nghĩa đã chốt (vehicle_management/API_CONTRACT.md mục 9)

| KPI | Công thức |
|---|---|
| Chờ duyệt | yêu cầu `pending`, **không lọc ngày** |
| Đã xếp xe | chuyến `scheduled` + `confirmed`, lọc theo ngày |
| Đang chạy | chuyến `in_progress`, lọc theo ngày |
| Hoàn thành | chuyến `completed` **chỉ** |

Trang `/app/vehicle-dispatch` và Mini App dùng **cùng một công thức và cùng màu**, để điều
hành cầm điện thoại và điều hành ngồi máy không bao giờ thấy hai con số khác nhau. Sửa một
bên thì sửa cả hai.

Ô "Đã hủy" cố ý đặt cạnh "Hoàn thành": nó là lý do hai số kia không cộng lại thành tổng
chuyến trong ngày, giấu đi là mời người ta đi hỏi.

### 🔴 KHÔNG tạo trang `vehicle-dashboard` thứ hai

Bên Mini App có đề nghị tạo `/app/vehicle-dashboard`. Trang `/app/vehicle-dispatch` **đã
có sẵn đủ** mọi panel họ mô tả. Tạo thêm là hai trang gần y hệt, mỗi lần đổi logic phải
sửa hai nơi. Đã mở rộng trang cũ thay vì nhân đôi.

### ⚠ `verify()` phải phân biệt "lỗi" và "dữ liệu đã đổi"

Dữ liệu demo sinh ra để **được dùng** — bên Mini App test endpoint là check-in, duyệt, hủy
thật, và mọi con số đổi theo. Neo test vào số tuyệt đối thì một người test xong là 4 ô
xanh hoá đỏ, rồi lỗi thật chìm trong đống báo động giả.

`seed_test_data.verify()` chia 3 nhóm:

| Nhóm | Ý nghĩa khi đỏ |
|---|---|
| **INVARIANT** | Lỗi code thật. Luôn phải đúng bất kể ai làm gì. |
| **DỮ LIỆU** | Cảnh báo cho người đọc (ví dụ gãy chuỗi KM qua ngày), không phải lỗi. |
| **BỘ SEED** | Con số tuyệt đối. `seed_drift()` phát hiện dữ liệu đã bị dùng thì **bỏ qua** nhóm này và in ra đã đổi những gì. |

Nguyên tắc tương tự áp cho `test_vehicle_management.py`: mọi assert đếm số đều phải giới
hạn theo **xe TEST** của chính nó, không bao giờ đếm cả đội xe.

---

## 17. Trang `/vehicle` — dashboard đồng bộ UI với Mini App

Thay hẳn `vehicle-dispatch` cũ (đã xoá). **Chỉ có một trang điều hành**, đừng tạo thêm.

```
vehicle_management/page/vehicle_dispatch/
    vehicle_dispatch.json · .html · .css · .js     → /app/vehicle-dispatch
```

### ⚠ Desk Page KHÔNG phục vụ ở URL trần

Frappe chỉ phục vụ Desk Page ở `/app/<name>`; một URL trần như `/vehicle` trả **404**.

Từng có `www/vehicle/index.py` chỉ để redirect `/vehicle` → `/app/vehicle-dispatch`, theo
yêu cầu của prompt cũ. **Đã xoá**: không lối vào nào dùng tới nó (desktop icon và sidebar
đều trỏ thẳng `/app/vehicle-dispatch`), mà nó lại **chép cứng danh sách role** của Page —
thêm `Vehicle Dispatcher` vào Page sau này thì `/vehicle` vẫn lặng lẽ từ chối người đó.
Một lối vào, một nơi khai quyền.

Nếu sau này thật sự cần URL ngắn: **không** viết lại thành portal page thật, vì trang
`www/` **không có object `frappe` JS** — mất sạch `frappe.call`, `frappe.ui.Dialog`,
`frappe.datetime`. Xem [[reference_frappe_www_page_csrf]].

### Frappe tự nạp `.html` và `.css` của Page

`core/doctype/page/page.py` đọc `<page>.html` rồi đăng ký làm **JS template** theo tên file
(`html_to_js_template`) **theo TÊN FILE**, và nhồi `<page>.css` vào `Page.style`. Nên trong JS gọi thẳng
`frappe.render_template('vehicle_dispatch', {})` — không cần `bench build`, không cần import gì.

### 🔴 Đừng dùng `onclick=` nội tuyến trong HTML sinh ra từ dữ liệu

Bản mẫu trong prompt nhồi thẳng `${vName}`, `${route}`, `${r.employee_name}` vào chuỗi HTML
và vào thuộc tính `onclick="...('${vid}')"`. Tên nhân viên và địa điểm là **do người dùng gõ
trong Mini App**: một dấu nháy đơn là hỏng handler, một chuỗi dàn dựng là chạy được script.

Trang này dùng **event delegation** (`data-act` / `data-kpi` / `data-trip-cancel`…) và mọi
giá trị đi qua `esc()` → `frappe.utils.escape_html`.

### KPI "Đang chạy" phải đếm CHUYẾN, không đếm XE

Bản mẫu đếm `allVehicles.filter(v => v.status === 'in_trip')`. Sai: xe có thể còn cờ
`in_trip` do chuyến của **ngày khác**, và con số sẽ lệch với Mini App. Dùng
`stats.in_progress` (đã lọc theo ngày đang xem).

### Trạng thái thứ ba của xe: "Đã xếp chuyến"

Xe `available` mà hôm đó đã có chuyến `scheduled`/`confirmed` thì không phải "đang đỗ"
cũng không phải "đang chạy". Mini App hiện trạng thái thứ ba này (xanh dương + giờ khởi
hành), trang này hiện y hệt — lệch là hai bên cãi nhau trên màn hình.

### Dark mode

Màu thương hiệu (header cam, màu KPI, màu trạng thái) để nguyên vì chúng **mang nghĩa**.
Còn nền/chữ/viền đi qua token của Frappe (`--card-bg`, `--text-color`, `--border-color`)
kèm fallback sáng — nếu không, cả trang trắng nằm trong Desk tối và chữ biến mất.

### Giữ lại từ trang cũ (prompt không nhắc, nhưng mất thì tiếc)

Nằm trong menu ⋯ để không phá layout mới: **Báo cáo KM** · **Gom yêu cầu vào một chuyến**
(kèm badge 🔗 trên card yêu cầu) · **Đổi trạng thái xe** · **Xuất Excel** (nút phụ ở header).

### ⚠ Role `Vehicle Dispatcher` — CHƯA tạo

Prompt liệt kê role này. Chưa tạo, vì role trống sẽ cho người ta **mở được trang rồi mọi
lệnh gọi API fail** — tệ hơn là không có. Muốn tách vai Dispatcher thì phải thêm DocPerm
cho cả 8 DocType; nói là làm.

---

## 18. Sidebar module · Report KM · quy ước ngôn ngữ

### 🔴 "Workspace Sidebar <Module> not found" khi bấm sửa sidebar

Frappe **không lưu** sidebar auto-generate. `auto_generate_sidebar_from_module()`
(`workspace_sidebar.py:239`) dựng doc bằng `frappe.new_doc()` rồi **trả về luôn, không
`insert()`** — nó chỉ tồn tại trong bootinfo. Bấm "sửa" gọi
`add_sidebar_items()` → `frappe.get_doc("Workspace Sidebar", <module>)` → **DoesNotExistError**.
Đúng 25 module trên site này đang ở tình trạng đó.

Cách chữa cho module của mình: ship một bản ghi thật ở
`customize_erpnext/workspace_sidebar/vehicle_management.json`.

**Hai cờ bắt buộc, sai là hỏng âm thầm:**

| Cờ | Sai thành | Hậu quả |
|---|---|---|
| `for_user` | `""` | Frappe kiểm bằng `{"for_user": None}` → `IS NULL`, chuỗi rỗng **không khớp** ⇒ vẫn sinh thêm bản auto **trùng tên**, sidebar hiện 2 mục giống hệt |
| `standard` | `0` | `before_save` → `export_sidebar()` bỏ qua ⇒ sửa trong UI **chỉ nằm ở DB**, `bench migrate` kế tiếp nạp lại file và **xoá mất** thay đổi, không báo gì |

Với `standard=1` + `app` đúng, sửa sidebar trong UI sẽ **ghi ngược vào chính file repo này**
(đã kiểm round-trip). `export_sidebar()` dùng `as_dict(no_nulls=True)` nên `for_user=None`
bị bỏ khỏi file — đúng cái ta cần.

### Report `TIQN Vehicle KM`

Script Report chuẩn Frappe ⇒ có sẵn bộ lọc, chọn cột, biểu đồ, và **nút Export của
ERPNext tự xuất Excel đúng kiểu dữ liệu** — không cần code thêm.

Lọc: `from_date` · `to_date` (bắt buộc) · `vehicle` · `driver` · `status`
(**mặc định `completed`** — đó là những chuyến TIQN thực sự trả tiền).

⚠ **`skip_total_row=1`.** `add_total_row()` của Frappe cộng **mọi** cột số và **không có
cách loại trừ từng cột** — nó sẽ in ra tổng của `km_start`/`km_end`, tức cộng chỉ số
công-tơ-mét lại với nhau: một con số vô nghĩa nhưng trông như thật. Số liệu cộng được nằm ở
4 thẻ `report_summary` (Trips · Completed · **Billable KM** · Additional Cost).

`billable_km` **tính lại** từ `km_end - km_start` chứ không tin `total_km` — đây là con số
đi vào hoá đơn.

### Quy ước ngôn ngữ

Mọi thứ theo rule chung của app: **source string tiếng Anh + `_()` / `__()`**, tiếng Việt
nằm ở `translations/vi.csv`. **Ngoại lệ duy nhất: nội dung trang `page/vehicle_dispatch/`**
— để tiếng Việt vì nó soi gương màn hình điều hành của Mini App.

Nghĩa là header Excel, nhãn sidebar, cột report đều là tiếng Anh cho tới khi bổ sung
`vi.csv` (làm sau khi test xong).

### ⚠ Thêm field vào DocType chưa đủ để API trả về

Ảnh xe không hiện trên trang dù đã đính kèm: field `image` có trong DocType nhưng **thiếu
trong `VEHICLE_FIELDS`** của `api/vehicle_management.py`. Field vắng khỏi danh sách đó thì
không bao giờ được gửi đi, và card xe lặng lẽ rơi về emoji 🚌 — không lỗi, không cảnh báo.
Thêm field hiển thị thì phải sửa **cả hai chỗ**.

---

## 19. Bố cục trang + 3 quy ước nhỏ nhưng dễ sai

### Một hàng cho cả KPI và xe

KPI chip và card xe nằm **chung một hàng** (`.vd-stats-row`). Xếp chồng hai hàng ngốn
~240px chiều cao trước khi thấy chuyến đầu tiên; gộp lại còn ~90px, phần đó trả về cho
danh sách chuyến. Card xe vì vậy là **ngang** (ảnh 46px bên trái, chữ bên phải) chứ không
phải banner ảnh 90px phía trên. Hẹp màn hình thì hai nửa tự xuống dòng riêng.

### Date picker: dùng control của Frappe, không dùng `<input type="date">`

`frappe.ui.form.make_control({df: {fieldtype: 'Date'}, only_input: true})` gắn vào một
`<div>` mount. Lý do không phải thẩm mỹ: `get_value()` của control **luôn** trả
`YYYY-MM-DD` bất kể định dạng ngày của người dùng và locale của trình duyệt, còn
`<input type="date">` thì tuỳ trình duyệt. CSS chỉ khoác lại lớp vỏ cho hợp thanh cam.

### 🔴 Chọn xe là đủ — tài xế điền ở CONTROLLER, không ở giao diện

Luật nằm trong `TIQNVehicleTrip.set_default_driver()`, chạy trong `validate()`. Đặt ở đó
để đúng cho **mọi đường vào**: trang điều hành · form Desk · Mini App · scheduler 06:30 và
17:00 · import. Nhét vào dialog thì mỗi đường mới lại phải nhớ chép lại luật.

`driver` là `reqd` trên DocType, và Frappe chạy `validate()` **trước** khi kiểm mandatory
(`document.py:486-487`), nên điền ở đây là vừa đủ.

- Chỉ điền khi **đang trống** — tài xế chạy thay do người dùng gõ không bao giờ bị ghi đè.
- Chỉ lấy tài xế **`is_active`** — nếu không, chuyến sẽ được giao cho người đã nghỉ.
- Xe không có tài xế active nào thì `MandatoryError` vẫn chặn, đúng như trước.

`create_trip()` và `combine_requests_to_trip()` có `driver=None`; truyền vào chỉ khi muốn
đè. Trên giao diện, ô Tài xế **không còn chặn** thao tác, kèm mô tả *"Tự điền theo xe"*.

Phần JS (`vehicle_and_driver_fields`) và `tiqn_vehicle_trip.js` chỉ là **hiển thị sớm** để
người dùng thấy ai lái *trước khi* lưu, không phải nơi giữ luật.

`get_dialog` là **getter**, không phải dialog: các field được dựng *trước* khi dialog tồn
tại. (Lấy dialog qua nội bộ control của Frappe cũng chạy, nhưng hỏng vào ngày Frappe đổi
nội bộ.)

🔴 **`get_drivers()` phải trả `is_active`.** Trang lọc `d.is_active` trước khi điền; field
vắng mặt trong payload đọc ra `undefined` ⇒ falsy ⇒ **không bao giờ điền tài xế**, mà
không có lỗi nào. Cùng một loại bẫy với `image` ở mục 18: thêm field vào DocType chưa đủ,
phải thêm vào cả danh sách field của endpoint.

### Danh sách chuyến: một cột cho mỗi xe

`trip_columns_html()` gom chuyến theo `vehicle` và dựng **một cột cho mỗi xe**, theo đúng
thứ tự trái-phải của dải card xe phía trên. Đọc dọc một cột trả lời đúng câu điều hành hay
hỏi — *"hôm nay xe này chạy gì"* — điều mà một danh sách trộn chung không bao giờ trả lời được.

Ba điểm cố ý:

- **`auto-fit`, không phải cứng 3 cột.** Số cột chạy theo số xe thực có; thêm xe thứ tư
  không phải sửa CSS, và màn hình hẹp thì tự gấp xuống 2 hoặc 1 cột.
- **Xe không có chuyến vẫn giữ cột** (hiện "Không có chuyến"), để thứ tự cột không nhảy
  giữa các ngày.
- **Cột "Chưa rõ xe"** hứng chuyến có `vehicle` không nằm trong danh sách xe (xe đã xoá).
  Không có nó thì chuyến đó **biến mất khỏi bảng mà không dấu vết**.

Card chuyến rút gọn cho vừa cột ~250px: giờ + badge trạng thái trên một dòng, rồi tuyến,
tài xế, KM, nút. Tên xe bỏ khỏi card vì đã nằm ở đầu cột.

### Nút, không phải menu

Chức năng còn lại — **🛠 Đổi trạng thái xe** — là button hiện rõ **ngay trên thanh tiêu
đề**, cạnh chữ "Điều hành xe". Không có hàng toolbar riêng: bớt được một dải ngang nữa
giữa người dùng và danh sách chuyến, và không có gì nấp trong menu ⋯.

**🔗 Gom yêu cầu đã bỏ khỏi thanh tiêu đề** — nó trở thành *chế độ thứ hai* của nút
**+ Tạo chuyến** (xem dưới). Nút cũ chỉ cho gom đúng những nhóm máy tự phát hiện; chế độ
mới cho chọn bất kỳ yêu cầu nào, làm được nhiều hơn mà ít hơn một nút.

"Báo cáo KM" và "Xuất Excel" **đã bỏ khỏi trang** — report chuẩn `TIQN Vehicle KM` đã có
sẵn bộ lọc và nút Export của ERPNext, giữ thêm hai nút nữa là hai đường làm cùng một việc.
Report được gắn vào **sidebar module** (mục Reports) để vẫn tìm ra được.
`download_trip_report_excel` **vẫn còn ở server** vì Mini App gọi nó.

#### Nút "+ Tạo chuyến" — 2 chế độ

| Chế độ | Khi nào | Phải nhập gì |
|---|---|---|
| **Chuyến mới hoàn toàn** (mặc định) | chuyến phát sinh không ai yêu cầu trước | xe · điểm đi/đến · ngày giờ |
| **Từ yêu cầu chờ duyệt** | 1 hoặc nhiều yêu cầu đi chung một xe | **chỉ cần chọn xe** |

Chế độ 2 dùng `MultiCheck` liệt kê mọi yêu cầu `pending`; yêu cầu nào server đã phát hiện
có thể đi chung (cùng tuyến, lệch ≤30 phút) được đánh dấu **🔗**. Tick xong thì **điểm đi,
điểm đến, ngày, giờ tự điền** theo yêu cầu sớm nhất trong nhóm, tài xế tự điền theo xe —
còn lại chỉ chọn xe.

Ghi đè chứ không chỉ điền vào ô trống: bỏ tick yêu cầu này, tick yêu cầu khác thì tuyến
phải đi theo, không được giữ lại tuyến cũ.

Gửi đi bằng `combine_requests_to_trip` — nó tạo chuyến **và** chuyển mọi yêu cầu đã chọn
sang `assigned` trong **một transaction**. Làm hai bước thì bước hai hỏng là yêu cầu mắc
kẹt lơ lửng. Hủy chuyến đó sẽ nhả **tất cả** yêu cầu trở lại, không chỉ cái đầu tiên (có test).

#### Cảnh báo quá giờ trên danh sách chờ duyệt

Card yêu cầu gọn còn **5 dòng**, hàng đợi vốn được đọc bằng cách *lướt*:

```
CÒN 3 GIỜ 58 PHÚT                      18:29     ← thời gian + giờ, 1 dòng
🔗 Nguyễn Văn An  EMP001  👤 3                   ← ai, mấy người
Toray VSIP → Sân bay Chu Lai                     ← đi đâu
Họp với UBND                                     ← để làm gì
[ Xếp xe ] [ Từ chối ]
```

**Mục đích và số người phải hiện ra**, không nhét vào tooltip: đó chính là hai thứ quyết
định xếp xe nào — Kia 7 chỗ không chở nổi 10 người, và "đi sân bay" khác "ghé ngân hàng
15 phút". Số người hiện **luôn luôn**, kể cả khi bằng 1, để cột số không nhảy chỗ giữa các
card. `notes` vẫn ở tooltip — đó là chi tiết, không phải tiêu chí.

Số người cũng nằm trong danh sách chọn của dialog "Tạo chuyến → Từ yêu cầu chờ duyệt", vì
chọn xe ở đó mà không thấy số người là chọn mò.

- **Số thời gian tương đối đứng ĐẦU card**, trên cả tên, tô màu theo trạng thái: hổ phách
  `#FFA500` (bình thường) · cam `#FF8800` (sắp tới giờ) · đỏ `#FF4444` (quá giờ). Đó là
  thứ đầu tiên người điều hành cần khi lướt; chỉ ghi giờ đồng hồ là bắt người đọc tự trừ
  nhẩm — con số đó chính là thứ họ định tính ra.
- Dòng này **nói bằng chữ** chứ không chỉ đổi màu, nên đã bỏ nhãn "Quá giờ N" cạnh tên:
  hai chỗ nói cùng một điều là thừa. Hổ phách trùng với chip KPI "Chờ duyệt" để hai thứ
  đọc ra cùng một ý.
- **Giờ rút gọn**: `18:29` nếu trùng ngày đang xem, `17/09 08:00` nếu khác. Năm và giây
  không nói lên điều gì mà chiếm một phần ba dòng.
- **Mục đích và ghi chú chuyển thành tooltip** của card. Chúng là ngữ cảnh, không phải thứ
  để lướt — giữ chúng thành 2 dòng riêng làm card cao gấp rưỡi mà không ai đọc.
- Mã nhân viên, số khách, badge 🔗 gom chung xe đều nằm **cùng dòng với tên**.

| Trạng thái | Điều kiện | Hiển thị |
|---|---|---|
| Quá giờ | `minutes_until < 0` | viền đỏ + nhãn **"Quá giờ N phút/giờ/ngày"** |
| Sắp tới giờ | `0 ≤ minutes_until ≤ 10` | viền cam + nhãn **"Còn N phút"** |
| Bình thường | còn lại | viền hổ phách + số thời gian màu xám |

🔴 **`minutes_until` tính ở SERVER** (`_flag_overdue`), không tính trong trình duyệt. Trừ
ở client là đem chuỗi `"YYYY-MM-DD HH:MM:SS"` giờ-của-site so với đồng hồ máy người xem —
đúng chừng nào mọi người còn ngồi cùng múi giờ với server, và sai lặng lẽ ngay ngày có
người mở bảng từ nơi khác.

Nhãn chữ là **bắt buộc**, không chỉ đổi màu: hai sắc cam cách nhau vài độ, và màu không
phải tín hiệu ai cũng đọc được. Thiếu `request_time` thì `minutes_until = None` và không
tô gì — không đoán bừa là quá giờ.

Ngưỡng 10 phút nằm ở `DUE_SOON_MINUTES`, khai **hai nơi** (`api/vehicle_management.py` và
`vehicle_dispatch.js`) — sửa thì sửa cả hai.

#### Picker "Từ yêu cầu chờ duyệt"

Mỗi dòng mang đủ thứ cần để quyết định, khỏi phải đóng dialog đi tra:
`🔗 · <b>giờ cần xe</b> · tên người yêu cầu · điểm đi → điểm đến`, tooltip là mục đích.

Dùng luôn cờ **`danger` / `warning` có sẵn của `MultiCheck`** để tô đỏ/cam dòng quá giờ và
sắp tới giờ — không dựng thêm hệ màu thứ hai.

⚠ `sort_options: false`. `MultiCheck` mặc định **tự sắp theo label**, sẽ đảo lộn danh sách
theo ký tự đầu tiên; ta muốn giữ thứ tự server trả về (`request_time` tăng dần).

⚠ Label của `MultiCheck` được nhét vào DOM dạng **HTML thô** (`${option.label}` trong
`get_checkbox_element`) — mọi giá trị người dùng nhập phải qua `esc()`.

🔴 **`MultiCheck` gọi `df.on_change`, KHÔNG phải `df.onchange`.** Nó tự bind handler cho
checkbox (`multicheck.js: bind_checkboxes`) và gọi `this.df.on_change &&
this.df.on_change()`. Mọi control khác của Frappe dùng `onchange`. Viết đúng chính tả
thông thường ở đây là **handler không bao giờ chạy — không lỗi, không cảnh báo, chỉ là
không có gì xảy ra** (đã vấp: tick yêu cầu mà điểm đi/đến không tự điền). Có assert ghim
lại trong `test_vehicle_management.py`.

#### Dialog "Xếp xe" — một cú bấm là xong

Mặc định là **Tạo chuyến mới**, vì đó là việc xảy ra gần như mọi lần; *Ghép vào chuyến đã
có* (đi chung xe) là ngoại lệ nên xếp thứ hai.

Điều hành **chỉ cần chọn xe**:
- **tài xế** tự điền từ `assigned_vehicle` của xe;
- **ngày + giờ** lấy từ `request_time` của chính yêu cầu;
- **điểm đi/đến** không cần nhập — `combine_requests_to_trip` lấy từ yêu cầu.

Tất cả vẫn sửa được (tài xế chạy thay, giờ đã thương lượng lại). Chỉ khi xe **chưa có tài
xế mặc định** mới phải chọn tài xế, và thông báo nói đúng lý do đó thay vì "bắt buộc chọn".

⚠ `request_time` là chuỗi `"YYYY-MM-DD HH:MM:SS"`, tách bằng **vị trí** chứ không dựng
`new Date()` — đẩy qua múi giờ trình duyệt là chuyến rơi sang ngày khác.

Card yêu cầu chỉ có **2 nút**:
**Xếp xe** (mở dialog ghép vào chuyến có sẵn / tạo chuyến mới — cả hai đưa yêu cầu thẳng
sang `assigned`, tức **xếp xe = duyệt**) và **Từ chối**. Không còn nút "Duyệt" riêng.

---

## 20. Chiều cao chart của report

`options.height = 280` bị **gán cứng** trong `get_chart_options()` của Frappe
(`query_report.js:1205`), **đè lên** mọi giá trị `execute()` trả về — trả `height` trong
dict chart là vô ích.

CSS cũng không cứu được: frappe-charts ghi `width`/`height` thành **thuộc tính** trên
`<svg>` và không có `viewBox`, nên đặt `height` bằng CSS là **cắt cụt** hình chứ không
co lại.

Cách dùng được: hook **`after_refresh(report)`** (`query_report.js:880`, chạy sau khi chart
đã vẽ) → sửa `report.chart_options.height` rồi `report.render_chart(...)`. Chạy mỗi lần
refresh chứ không phải một lần, vì Frappe dựng lại `chart_options` mỗi lần và reset về 280.
`render_chart()` không bắn `after_refresh` nên không có vòng lặp.

---

## 21. Dữ liệu demo cả tháng — `seed_month.py`

```bash
# xoá sạch chuyến + yêu cầu rồi dựng lại cả tháng 9/2026
bench --site erp.tiqn.local execute customize_erpnext.vehicle_management.seed_month.execute
# tháng khác
bench --site erp.tiqn.local execute customize_erpnext.vehicle_management.seed_month.execute \
    --kwargs "{'year': 2026, 'month': 10}"
# kiểm tra toàn vẹn (dùng chung với bộ cũ)
bench --site erp.tiqn.local execute customize_erpnext.vehicle_management.seed_test_data.verify
```

**~408 chuyến · ~225 yêu cầu**, mỗi xe 2 chuyến cố định + 2–4 chuyến phát sinh mỗi ngày
làm việc. Deterministic (`SEED` cố định) nên chạy lại ra đúng bộ số cũ — con số trong một
báo cáo lỗi tái hiện được.

Trạng thái đi theo **lịch**, không rắc ngẫu nhiên: quá khứ đã xong, hôm nay đang dở, mai
chưa chạy. Đó là thứ làm KPI và báo cáo KM ra số có nghĩa.

### 🔴 Odometer phải cấp theo GIỜ KHỞI HÀNH, không theo thứ tự tạo

Bản đầu tạo 2 chuyến cố định trước rồi mới tới chuyến phát sinh, nên một chuyến rời bến
lúc 07:00 nhận chỉ số công-tơ-mét của chuyến 17:15 — **mọi cặp như vậy đều khai trùng KM,
tức TIQN trả tiền hai lần cho cùng một đoạn đường**. Phải **lập kế hoạch cả ngày, sắp theo
giờ, rồi mới cấp KM**.

### 🔴 Và sắp theo giờ thì KHÔNG được so chuỗi thô

Lần sửa đầu vẫn sai: `depart_time` là `timedelta`, `str()` ra `"6:30:00"` — **thiếu số 0**
— nên `"6:30:00" > "07:00:00"` và chuyến sáng lại bị xếp cuối ngày. Phải chuẩn hoá qua
`_clock()` trước khi sort. Cùng một bẫy với control Time ở mục 19.

### Các ca đã phủ

⚠ **Không dựng bản ghi giả** kiểu *"Chờ duyệt — quá giờ nhiều ngày"*. Hàng đợi
"Chờ duyệt" đến từ dữ liệu thật: ~30% yêu cầu của những ngày còn ở phía trước chưa được
xếp xe, đúng như một tồn đọng thật. Mọi bản ghi đều mang tên nhân viên thật, để bảng đọc
ra như một ngày làm việc chứ không như một bộ fixture.

Logic cảnh báo quá giờ / sắp tới giờ **vẫn còn nguyên** trong code và vẫn có test — chỉ là
bộ dữ liệu này không cố tình tạo ra ca đó nữa.

Chuyến: `completed` · `in_progress` (kèm *đổi lộ trình chưa xác nhận*) · `scheduled` ·
`confirmed` · `cancelled` · cố định · phát sinh · có/không hành khách · chở 2 khách ·
có chi phí phát sinh · Chủ nhật không có chuyến cố định.

Yêu cầu: `pending` (bình thường / **sắp tới giờ** / **quá giờ**) · `assigned` · `rejected` ·
`cancelled` · `approved` (trạng thái chỉ Desk sinh ra) · có giờ về · 2 yêu cầu **gom chung xe**.

Xe: `in_trip` · `available` · `maintenance` — ba xe, ba trạng thái, để bảng điều hành hiện
đủ cả ba kiểu card.

⚠ Yêu cầu gắn với chuyến bị hủy sẽ **kẹt ở `pending`** (`sync_linked_requests` chỉ trả về
`approved` cho cái đã `assigned`). Đúng về nghiệp vụ nhưng để nguyên thì bảng đầy hàng đỏ
từ ba tuần trước và cảnh báo quá giờ mất hết ý nghĩa — `_close_stale_requests()` đóng chúng
lại thành `rejected`, chừa đúng mấy ca quá giờ cố ý.

### ⚠ 14/09/2026 KHÔNG phải Chủ nhật

`kịch bản kiểm tra gốc (đã gộp vào README)` ghi "14/09/2026 (Chủ nhật)" — sai, đó là **thứ Hai**. Chủ
nhật tháng 9/2026 là **06, 13, 20, 27**. `verify()` trước đây viết cứng ngày 14 theo tài
liệu nên báo lỗi giả; giờ nó **tự tính** ngày Chủ nhật từ dữ liệu.

---

## 22. Desktop icon

```
desktop_icon/vehicle_management.json        → /app/vehicle-dispatch
public/images/vehicle_dispatch.svg          → /assets/customize_erpnext/images/…
```

Chỉ hiện với `Vehicle Manager` / `System Manager`.

### 🔴 `label` PHẢI trùng tiêu đề của Workspace Sidebar, nếu không icon không hiện

Icon `icon_type = "Link"` được lọc bằng (`desktop_icon.py: get_desktop_icons`):

```python
sidebar = bootinfo.workspace_sidebar_item.get(s.label.lower())
permitted = bool(sidebar and sidebar["items"])
```

Tức là **không có Workspace Sidebar cùng tên (và có item) thì icon bị loại thẳng** — bản
ghi vẫn nằm trong DB, không lỗi, chỉ là Desk không vẽ nó ra. Đã vấp: đặt label
"Vehicle Dispatch" (tên trang) trong khi sidebar tên "Vehicle Management" ⇒ icon im lặng
biến mất. Kiểm nhanh cả app:

```python
icons = frappe.get_all("Desktop Icon", filters={"app": "customize_erpnext"}, fields=["label"])
sidebars = {s.title.lower() for s in frappe.get_all("Workspace Sidebar", fields=["title"])}
[i.label for i in icons if i.label.lower() not in sidebars]   # → những icon sẽ KHÔNG hiện
```

⚠ `System Mindmap` của app cũng đang rơi vào trường hợp này (không có sidebar cùng tên) —
có sẵn từ trước, chưa xử lý.

### Cache theo từng user

`get_desktop_icons()` cache vào `frappe.cache.hset("desktop_icons", user, …)`. Đổi icon mà
không `frappe.cache.delete_key("desktop_icons")` thì người đang đăng nhập vẫn thấy bản cũ.

### 🔴 Tên bản ghi PHẢI khớp tên file, nếu không migrate tự xoá nó

`remove_orphan_entities()` gọi `check_if_record_exists()`
(`frappe/model/sync.py:298`), so **`frappe.scrub(name)`** với tên file
`<app>/desktop_icon/<tên>.json`. Không khớp là Desktop Icon bị **xoá ngay trong chính lần
`bench migrate` vừa tạo ra nó** — log chỉ in `Deleting entity Desktop Icon …`, không có lỗi.

Đã vấp: đặt `name = "Điều hành xe"` thì scrub ra `điều_hành_xe`, không đời nào khớp
`vehicle_dispatch.json`. Đặt tên **tiếng Anh** vừa hết lỗi vừa đúng rule English-first của
app (tiếng Việt lấy từ `vi.csv`). Quy tắc này áp cho cả `workspace_sidebar/`.

SVG tự vẽ, dùng đúng dải cam của module (`#FF8800 → #E65100`) để icon, header trang và chip
KPI cùng một bảng màu. Đã kiểm phục vụ được qua HTTPS (200, `image/svg+xml`) và icon còn
nguyên sau lần `bench migrate` thứ hai.

---

## 23. Nút "Xoá hết & tạo lại dữ liệu mẫu"

Chỉ hiện với **`Administrator`** — không phải `System Manager`, vì vai đó có nhiều người
thật đang giữ. Ẩn/hiện do `get_page_context().is_administrator` quyết định, và
`reset_demo_data()` **kiểm lại ở server** chứ không tin cái ẩn của giao diện.

Bấm → `frappe.warn` nói rõ sẽ xoá vĩnh viễn những gì và giữ lại những gì → mới chạy.

### Chạy nền, dù chỉ mất ~8,5 giây

Một tháng đo được ~8,5s nên thực ra vẫn sống sót qua một HTTP request. Vẫn đẩy xuống worker
vì: khối lượng **co giãn theo khoảng ngày** (một năm là gấp mười hai), và đây là **thao tác
xoá hàng loạt** — bị SIGKILL ở mốc 120s của gunicorn sẽ để lại đội xe xoá dở, seed dở, không
cách nào biết phần nào đã xong. Việc bắt buộc phải hoàn tất thì không đi nhờ một request.

Kết quả về bằng realtime `tiqn_vehicle_seed_done`, trang tự nạp lại.

### Khoá chống chạy chồng — và khoá phải TỰ HẾT HẠN

`frappe.cache.set_value(SEED_LOCK, 1, expires_in_sec=1800)`. `finally` **không chạy** khi
worker bị SIGKILL, nên nếu chỉ dựa vào `finally` để nhả khoá thì nút sẽ kẹt vĩnh viễn.
