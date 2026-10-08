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
| Dữ liệu demo (mặc định 7 ngày gần nhất) | `vehicle_management/seed_month.py` ← đang dùng |
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

## 21. Dữ liệu demo — `seed_month.py` (mặc định 7 ngày gần nhất)

```bash
# xoá sạch chuyến + yêu cầu rồi dựng lại 7 ngày gần nhất (hôm nay - 6 → hôm nay)
bench --site erp.tiqn.local execute customize_erpnext.vehicle_management.seed_month.execute
# khoảng ngày tuỳ ý (tối đa MAX_DAYS = 366 ngày)
bench --site erp.tiqn.local execute customize_erpnext.vehicle_management.seed_month.execute \
    --kwargs "{'from_date': '2026-10-01', 'to_date': '2026-10-15'}"
# cả một tháng (mặc định CŨ, trước 08/10/2026)
bench --site erp.tiqn.local execute customize_erpnext.vehicle_management.seed_month.execute \
    --kwargs "{'year': 2026, 'month': 9}"
# kiểm tra toàn vẹn (dùng chung với bộ cũ)
bench --site erp.tiqn.local execute customize_erpnext.vehicle_management.seed_test_data.verify
```

**Vì sao mặc định là "7 ngày tính tới hôm nay" chứ không phải một tháng cố định (08/10/2026):**
bộ cũ cứng tháng 9/2026, sang tháng 10 là trang điều hành — mở ra ở ngày HÔM NAY — trống
trơn. Cửa sổ trượt theo lịch luôn rơi đúng vào ngày người ta nhìn. Hệ quả: "7 ngày gần
nhất" chạy hôm nay và chạy ngày mai là HAI bộ dữ liệu khác nhau; muốn tái hiện số liệu
một báo cáo lỗi thì truyền `from_date`/`to_date` cụ thể.
7 ngày đo được **64 chuyến · 27 yêu cầu · ~4s**, đủ mọi trạng thái (kể cả chuyến cố định
bị huỷ, chuyến đang chạy, yêu cầu chờ duyệt / từ chối / tự huỷ / đã duyệt), 0 đoạn KM đè.

Cả tháng: **~274 chuyến · ~114 yêu cầu**, mỗi xe 2 chuyến cố định + 1–2 chuyến phát sinh mỗi ngày
(trung bình 3,45 chuyến/xe/ngày). Trước đây là 2–4 chuyến phát sinh ⇒ tới 6 thẻ trong một
cột và bảng điều hành phải cuộn; dữ liệu demo cần đọc được trong một cái liếc mắt, không
phải mô phỏng ngày bận nhất.
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

Bấm → dialog nói rõ sẽ xoá vĩnh viễn những gì và giữ lại những gì, kèm **Từ ngày / Đến ngày**
(mặc định hôm nay − 6 → hôm nay) → mới chạy. `reset_demo_data(from_date, to_date)` gọi
`seed_month.resolve_days()` **trước khi** xếp job: khoảng ngày sai mà chỉ phát hiện trong
worker thì người dùng chỉ nhận về traceback qua realtime, sau khi trang đã báo "đang tạo lại".
Job nhận ngày ĐÃ GIẢI (không phải tham số thô) để bấm lúc 23:59 mà worker chạy sau nửa đêm
vẫn ra đúng tuần đã bấm.

⚠ **Nút xoá cả chuyến THẬT**: chuyến cố định do scheduler tạo và chuyến Mini App tạo cũng nằm
trong `tabTIQN Vehicle Trip`, `_purge()` không phân biệt. Ngày 08/10/2026 lượt bấm 16:31 đã
xoá 39 chuyến cố định tháng 10 (scheduler) + 1 chuyến của `miniapp@tiqn.com.vn`; còn trong
backup `20261008_120003`.

### Chạy nền, dù chỉ mất ~8,5 giây

Một tháng đo được ~8,5s nên thực ra vẫn sống sót qua một HTTP request. Vẫn đẩy xuống worker
vì: khối lượng **co giãn theo khoảng ngày** (một năm là gấp mười hai), và đây là **thao tác
xoá hàng loạt** — bị SIGKILL ở mốc 120s của gunicorn sẽ để lại đội xe xoá dở, seed dở, không
cách nào biết phần nào đã xong. Việc bắt buộc phải hoàn tất thì không đi nhờ một request.

Kết quả về bằng realtime `tiqn_vehicle_seed_done`, trang tự nạp lại.

### Khoá chống chạy chồng — và khoá phải TỰ HẾT HẠN

`frappe.cache.set_value(SEED_LOCK, 1, expires_in_sec=1800)`. `finally` **không chạy** khi
worker bị SIGKILL, nên nếu chỉ dựa vào `finally` để nhả khoá thì nút sẽ kẹt vĩnh viễn.

---

## 24. Vòng đồng bộ với Mini App 21/09/2026 — `purpose`, `is_leader`, Zalo ID

Đội Mini App gửi 6 yêu cầu. Ba trong số đó hoá ra **đã xong** hoặc **không phải việc của
server** — ghi lại đây vì chúng là kiểu hiểu lầm sẽ lặp lại.

### `purpose` là field thứ ba, không phải đổi tên `notes`

`TIQN Vehicle Trip` giờ có `purpose` (Small Text) bên cạnh `notes` và `dispatcher_note`:

| Field | Ai viết | Đi đâu |
|---|---|---|
| `purpose` | người yêu cầu / dispatcher | **cột Mục đích của báo cáo KM** |
| `notes` | Mini App (tự do) | không lên báo cáo |
| `dispatcher_note` | dispatcher | kênh riêng nhắn tài xế |

Gộp lý do khi ghép yêu cầu nằm ở `_merge_purposes()`: nối `" | "`, **khử trùng không phân
biệt hoa thường**, bỏ rỗng, trả `None` (không phải `""`) khi không có gì. Ba người cùng đi
khám sức khoẻ phải ra **một** cụm — không khử trùng thì cột Mục đích thành một hàng rào lặp.

🔴 **Field mới ⇒ chuyến cũ `purpose = null`.** Không backfill, nên cột Mục đích trống với
toàn bộ dữ liệu tháng 9. Backfill được từ `passengers[].request.purpose`, nhưng đó là sửa dữ
liệu đã có nên phải hỏi trước.

### `combine_requests_to_trip` KHÔNG nhận `passengers`

Prompt của Mini App liệt kê `passengers` trong payload. Cố tình không thêm: dòng hành khách
mang link `request`, và `TIQNVehicleTrip.sync_linked_requests()` đi theo chính link đó để đẩy
yêu cầu sang `assigned` rồi trả về `approved` nếu chuyến bị huỷ. Cho client gửi danh sách
hành khách riêng = cắt link đó, yêu cầu mắc kẹt ở `pending` mà chuyến vẫn tạo thành công —
hỏng im lặng, đúng loại khó truy nhất.

Cũng vậy: prompt viết yêu cầu chuyển sang `approved`. Thực tế là **`assigned`**.
`approved` = "đã duyệt, chưa có xe"; `assigned` = "đã có chuyến". Gộp hai cái làm một thì bảng
điều hành mất khả năng phân biệt "chờ xếp xe" với "xong rồi".

### Cột Excel: đừng viết cứng số cột

Chèn thêm cột *Mục đích* làm **3 assert Excel đứt cùng lúc**, vì chúng viết cứng `14`, cột
`11`, cột `12` và hai chuỗi công thức `"K2:K"` / `"L2:L"`. Giờ mọi vị trí suy từ
`EXCEL_HEADERS`:

```python
_COL = {label: i for i, (label, _w) in enumerate(EXCEL_HEADERS, 1)}
KM_COLUMNS      = (_COL["KM Start"], _COL["KM End"], _COL["Billable KM"])
TOTAL_KM_COLUMN = _COL["Billable KM"]
COST_COLUMN     = _COL["Additional Cost"]
```

Công thức tổng cũng dựng bằng `get_column_letter(column)` thay vì chữ cái gõ tay. Kiểu lỗi né
được ở đây là loại **không báo gì**: cột vẫn có số, chỉ là cộng nhầm cột.

### 🔴 Excel 404: một request GHI dữ liệu qua HTTP **GET** bị Frappe rollback

Đây là bug thật, và tôi đã chẩn đoán SAI ở lượt trước — kết luận "file có thật, chỉ tại client
dùng `url` tương đối" chỉ đúng một nửa. Có **hai** lỗi độc lập; cái nặng là cái này.

`frappe/app.py: sync_database()`:

```python
if frappe.local.request.method in UNSAFE_HTTP_METHODS or frappe.local.flags.commit:
    db.commit(chain=True)
else:
    db.rollback(chain=True)      # ← GET / HEAD / OPTIONS rơi vào đây
```

`download_trip_report_excel` **ghi** (tạo `File`) nhưng được gọi bằng **GET**. Hệ quả dây
chuyền: transaction bị rollback ⇒ `File.on_rollback()` thấy `flags.new_file` ⇒
`_delete_file_on_disk()` **xoá file vừa ghi**. Response đã dựng xong và trả về URL đúng, còn
file thì đã biến mất trước khi response rời server. **Không có dòng log nào.**

Sửa: `frappe.local.flags.commit = True` sau khi lưu `File`. Dùng cờ chứ **không** gọi
`frappe.db.commit()` trong hàm `@whitelist` — commit ở đó xả luôn transaction của người gọi
và làm test rò bản ghi ra DB thật. Ngoài request thì cờ này đơn giản là không ai đọc, nên
console và test không đổi hành vi.

🔴 **Cách nhận ra rollback chứ không phải lỗi đĩa:** bản ghi `File` **cũng không còn trong
DB**. Nếu file mất mà row `tabFile` vẫn còn thì mới là chuyện đĩa. Và đừng đổ cho job dọn dẹp:
nó chỉ xoá file **quá 45 phút** — file user báo mới 80 giây tuổi.

🔴 **Cùng bẫy đó khi tự kiểm trong console:** `frappe.db.rollback()` cũng xoá file vật lý. Thử
rồi rollback sẽ để lại URL 404 và làm ta tưởng chức năng hỏng. Muốn curl thật thì phải
`commit()` rồi dọn tay sau. Chính chỗ này làm tôi kết luận nhầm ở lượt trước: tôi test bằng
console có commit, nên không bao giờ gặp đường GET mà Mini App đang đi.

**Bài học rộng hơn:** bất kỳ endpoint `@frappe.whitelist(methods=["GET", ...])` nào có ghi dữ
liệu đều đang âm thầm mất ghi. Liệt kê được bằng cách soi hàm nào vừa cho GET vừa `insert`/
`save`/`set_value`. Đúng ra endpoint này nên là POST-only; giữ GET là để tương thích ngược.

### Lỗi thứ hai, độc lập: `url` tương đối

Client phải dùng `absolute_url`. `url` là `/files/…`; mở trong webview Zalo thì resolve theo
origin của **Mini App** chứ không phải ERPNext. nginx phía server đã có sẵn
`location ~* ^/files/.*.(xlsx|xls|csv)` và trả 200 không cần đăng nhập.

### `is_leader` và Zalo ID là gợi ý UI, không phải phân quyền

`is_leader` quyết định Mini App có vẽ tab Báo cáo hay không. Ẩn tab **không chặn được gì** —
endpoint báo cáo vẫn đọc được bằng chính API key nằm trong client.

`get_drivers()` **cố tình không trả `zalo_user_id`**: nó liệt kê mọi tài xế cho bất kỳ ai cầm
key. Chat cần id thì lấy qua `driver_zalo_user_id` trong object **chuyến** — chỉ lộ tài xế của
đúng chuyến đang xem. Cùng lý do với việc không trả `password`.

`update_zalo_user_id(role, doc_name, zalo_user_id)` dùng `db_set` chứ không `doc.save()`: lưu
`doc.save()` sẽ chạy lại validate workflow, và một người yêu cầu mở lại app sau khi yêu cầu
đã được duyệt sẽ **không lưu nổi id chat** — không liên quan gì đến việc họ đang làm.
`role` ánh xạ qua `ZALO_ID_TARGETS`, không nhận tên doctype tự do từ client.

`dispatcher_zalo_id` đọc từ `TIQN Zalo Role Map` (`role = dispatcher`), **không hardcode**:
người điều hành sẽ đổi, và một Zalo ID chôn trong source chỉ bị phát hiện sau khi tài xế đã
nhắn cho hư vô cả tuần. Bảng đang rỗng ⇒ trả `null`.

### Seed dùng CHÍNH `_merge_purposes()` của API

`seed_month.py` import `_merge_purposes` từ `api/vehicle_management.py` thay vì chép lại luật
gộp. Seed tự cài lại luật thì không chứng minh được gì về luật thật, và hai bản sẽ trôi khỏi
nhau lặng lẽ. Đổi tên hàm đó thì seed gãy ngay lúc import — đúng ý đồ.

Ghi chú chuyến giờ lấy từ `TRIP_NOTES` (ghi chú thật: "Khách chờ sẵn ở sảnh"), không còn chép
`purpose` sang `notes` như bản cũ — hồi đó chưa có chỗ nào khác để đặt lý do chuyến.
`seed_test_data.py` (kịch bản 14–16/09 riêng) **chưa** điền `purpose`; nó không nối vào nút
"Xoá hết & tạo lại" nên để nguyên.

---

## 25. `decode_phone_token` — đổi token Zalo lấy SĐT (21/09/2026)

`TIQN Zalo Role Map.phone` **đã có sẵn** (kiểu Phone) — mục này không cần đổi DocType, chỉ
thêm code. Khoá `zalo_app_vehicle_management_secret_key` trong `site_config.json` là việc **người quản trị nhập**,
không phải việc code.

### Ba chỗ đề bài gợi ý mà làm theo sẽ hỏng

**1. `frappe.conf.get("zalo_app_vehicle_management_secret_key", "YOUR_ZALO_APP_SECRET_KEY")`** — fallback đó gửi
một chuỗi placeholder sang Zalo, nhận về lỗi chung chung, và đó đúng là **thông điệp lỗi duy
nhất không nói cho ai biết là khoá chưa được cấu hình**. Ở đây không có default: thiếu khoá
thì throw kèm tên khoá và chỗ đặt.

**2. Hardcode secret key.** Repo này ở git, và `app/public/` phục vụ **không cần đăng nhập**
(xem [[reference_public_assets_are_unauthenticated]] — từng lộ 6 email nhân viên qua file .md).

**3. `requests.get(...)` không timeout.** Gunicorn `-t 120`; Zalo chậm là giữ worker tới lúc
SIGKILL, và `finally` **không chạy** khi bị SIGKILL. Đặt `timeout=10`.

### Thông điệp lỗi không được chứa exception của `requests`

`requests` in lại cả request khi lỗi, và request đó mang **secret key trong header**. Nên
lỗi mạng trả message trung tính, traceback đi vào Error Log (chỉ user Desk đọc được).

### POST-only, khác với `download_trip_report_excel`

Endpoint này ghi ⇒ `methods=["POST"]`. Cho GET là dính đúng bẫy rollback ở mục 24. Excel vẫn
để GET vì tương thích ngược nên phải bù bằng `flags.commit`; cái mới thì làm đúng ngay từ
đầu. Test chốt cả hai lựa chọn qua `frappe.allowed_http_methods_for_whitelisted_func`.

### Hai định dạng số, và lý do

`_format_zalo_phone("84962200089")` → `("+84-962200089", "0962200089")`.

`phone` là định dạng Mini App yêu cầu. `phone_local` tồn tại vì **`TIQN Driver.phone` lưu
`"0905…"`** — đối chiếu bằng dạng `+84` sẽ không bao giờ khớp, và lỗi lộ ra rất muộn dưới
dạng "không tìm thấy tài xế". Chỉ tin chữ số: Zalo trả cả `"84…"` lẫn số nội địa có số 0.

### Server tự lưu, không bắt client ghi lại

Đề bài định để client nhận số rồi gọi REST API ghi vào Role Map. Truyền `zalo_user_id` vào
là server ghi luôn — một SĐT đã giải mã không cần đi ra client rồi quay vào chỉ để được lưu.
Bản ghi Role Map phải **có trước**; server không tự tạo, vì `role` là quyết định của quản trị
chứ không phải của client.

---

## 26. Đổi tên tài xế làm chết 6 lịch cố định (21/09/2026)

Tài xế được đổi tên từ `TIQN-DRV-001/002/003` sang `Mr. Lương` / `Mr. Long` / `Mr. Duy`.
Sau đó **cả 6 bản ghi `TIQN Fixed Trip Schedule` trỏ tới `TIQN-DRV-001-old`,
`TIQN-DRV-002-old`, `TIQN-DRV-003-olf`** — những tài xế không còn tồn tại. Chuyến xe,
`TIQN Zalo Role Map` và mọi link khác thì đúng; chỉ lịch cố định bị bỏ lại.

Hậu quả nếu không ai để ý: `create_scheduled_trips` (cron 06:30 và 17:00) tạo chuyến với
`driver` là link chết ⇒ `LinkValidationError: Could not find Driver: TIQN-DRV-001-old`. Vòng
lặp **không bắt lỗi**, nên dòng đầu ném ra ngoài và **không chuyến cố định nào được tạo cho
cả đội xe** — một traceback trong log, ba xe không có lịch sáng, các lịch còn lành thậm chí
chưa được thử.

🔴 **`set_default_driver()` KHÔNG tự chữa được.** Nó chỉ điền khi `driver` **rỗng**, cố ý như
vậy để không đè tài xế thay ca mà người dùng đã gõ. Một `driver` *sai* thì khác một `driver`
*trống*, và đây đúng là chỗ khác biệt đó cắn.

### Sửa dữ liệu

Ánh xạ suy được chắc chắn: mỗi lịch có `vehicle`, mỗi tài xế có `assigned_vehicle`, ba xe ba
tài xế. Đã sửa cả 6 lịch, còn 0 link chết.

### Sửa code: một dòng hỏng không được kéo cả đội xe theo

```python
save_point = f"fixed_trip_{schedule.name}".replace("-", "_")
frappe.db.savepoint(save_point)
try:
    created.append(_create_trip_from_schedule(schedule, on_date))
except Exception:
    frappe.db.rollback(save_point=save_point)
    failed.append(schedule.name)
    frappe.log_error(title=f"Fixed trip not created: {schedule.name}", ...)
```

🔴 **Savepoint, KHÔNG phải `rollback()` trần.** Bản vá đầu tiên của tôi dùng `rollback()`
trần — nó xoá luôn những chuyến đã tạo thành công **trước đó trong cùng vòng lặp**, tức là
biến một lịch hỏng thành một buổi sáng trống rỗng y như cũ, chỉ khác là im lặng hơn.

`summary` giờ có thêm khoá `failed`.

### Bài học chung

Đổi tên (`rename_doc`) cập nhật link ở những chỗ Frappe biết, nhưng **hãy luôn quét lại link
chết sau khi đổi tên hàng loạt**:

```sql
SELECT DISTINCT s.driver FROM `tabTIQN Fixed Trip Schedule` s
LEFT JOIN `tabTIQN Driver` d ON d.name = s.driver
WHERE s.driver IS NOT NULL AND s.driver != '' AND d.name IS NULL
```

Và: **docname tài xế giờ CHÍNH LÀ tên hiển thị.** Mọi chỗ trong tài liệu còn ví dụ
`TIQN-DRV-001` đã lỗi thời; Mini App nào hardcode mã đó sẽ hỏng.

### Phụ: Error Log đang bị rác vì Mini App dò bằng `/api/resource/`

10 bản ghi `TIQN Zalo Role Map <id> not found`. Mini App gọi
`GET /api/resource/TIQN Zalo Role Map/<zalo id>` để hỏi "tôi đã được map chưa" — chưa map thì
Frappe **ném lỗi và ghi Error Log**. Dùng `get_user_by_zalo_id(zalo_user_id)`: nó trả `None`
gọn gàng, không ném, không ghi log.

---

## 27. Zalo `error 117` — và một lần tôi báo "đã thông" khi chưa thông

Sau khi cấu hình `zalo_app_vehicle_management_secret_key`, tôi gọi `decode_phone_token` bằng token **bịa** và
nhận `"Session key invalid"`. Tôi kết luận chuỗi đã thông. **Sai.**

🔴 **Zalo xác thực SESSION trước, SECRET KEY sau.** Một `access_token` bịa bị chặn ở bước
đầu, nên câu trả lời đó **không nói gì** về việc khoá đúng hay sai. Chỉ khi Mini App gửi
token thật, Zalo mới đi tới bước hai và trả:

```json
{"error": 117, "message": "secret_key is invalid"}
```

**Bài học:** khi kiểm một chuỗi xác thực nhiều bước bằng dữ liệu giả, hãy hỏi *bước nào đã
thực sự được chạy tới*. Một phản hồi có vẻ "đúng kiểu" chỉ chứng minh mọi thứ **trước** chỗ
nó dừng lại, không chứng minh gì về phần sau.

### Message lỗi từng đổ oan cho client

Bản đầu trả `"Zalo refused the phone token: secret_key is invalid"` — đẩy người đọc đi lùng
Mini App trong khi lỗi nằm ở `site_config.json` của server. Giờ error 117 (hoặc message có
chữ `secret_key`) trả riêng một câu nói rõ là **khoá của server sai, token của người gọi
không có vấn đề gì**.

### Khoá nào mới đúng

Zalo có nhiều thứ gọi là "secret": secret của **OA**, **Mini App ID**, và **App Secret Key**
của ứng dụng ở `developers.zalo.me`. `graph.zalo.me/v2.0/me/info` cần **App Secret Key của
đúng ứng dụng Zalo mà Mini App thuộc về**. Khoá hiện tại đúng hình dạng (32 hex) nên nhìn
không ra — chỉ Zalo mới phân biệt được.

### Frappe che `secret_key`, KHÔNG che `phone_token`

`_get_traceback_sanitizer()` có blocklist `password/passwd/secret/token/key/pwd`. Với **biến
rời** thì khớp theo chuỗi con nên `secret_key` bị che thành `********` — đã kiểm: **0 bản ghi
Error Log chứa nguyên văn khoá**. Nhưng `dict_printer` chỉ che khi **khớp CHÍNH XÁC** key của
dict (`if key in v`), nên `kwargs = {'phone_token': '...'}` **lọt nguyên văn** vào Error Log.
Không sửa được từ phía mình (token nằm trong khung `frappe.call`). Token này dùng một lần và
hết hạn nhanh, nhưng đừng dán Error Log ra ngoài.

---

## 28. `zalo_user_id` không mở được chat — hai loại ID của Zalo (21/09/2026)

Đính chính cho mục 24. Vòng trước tôi nối `zalo_user_id` khắp nơi "để openChat": trên yêu cầu,
trên chuyến, và `dispatcher_zalo_id`. **Sai loại id.**

`getUserInfo()` trả hai thứ:

| Zalo | Field | openChat? |
|---|---|---|
| `id` | `TIQN Zalo Role Map.zalo_user_id` (cũng là docname) | **KHÔNG** — app-scoped |
| `idByOA` | `TIQN Zalo Role Map.id_by_oa` ← **mới** | **CÓ** — theo Official Account |

Kiểu lỗi tệ nhất: id app-scoped **trông hợp lệ**, **là** hợp lệ, chỉ không dùng được cho việc
này. Không có exception, không có log — chỉ là một nút chat bấm không ra gì.

### Không có fallback, cố ý

`get_dispatcher_zalo_id()` giờ lọc `{"role": "dispatcher", "id_by_oa": ("is", "set")}` và trả
`None` nếu chưa có. Không rơi về `zalo_user_id`:

> Nút chat **biến mất** là thành thật. Nút chat **bấm không ra gì** là một báo cáo lỗi không
> ai tái hiện nổi.

`driver_zalo_id_by_oa` trên chuyến cũng vậy — tài xế chưa map thì `null`.

### ID theo OA sống ở Role Map, không phải ở TIQN Driver

`TIQN Driver` đã có `zalo_user_id`, nên chỗ tự nhiên cho `id_by_oa` *có vẻ* là cạnh nó. Không:
danh tính Zalo có **một nhà** là `TIQN Zalo Role Map`, nối tới tài xế qua `driver_ref`. Tài xế
chưa mở Mini App thì đơn giản là chưa có dòng — không cần cột rỗng trên bảng tài xế, và không
có hai nguồn sự thật để lệch nhau.

`_driver_lookup()` join thêm một truy vấn Role Map (một lần cho cả danh sách, không phải mỗi
chuyến một lần).

### `update_zalo_id_by_oa` tách riêng khỏi `update_zalo_user_id`

`update_zalo_user_id` ghi lên **ba** doctype theo `role`. `id_by_oa` chỉ tồn tại trên Role Map.
Gộp vào nghĩa là một tham số `role` mà với hai trong ba giá trị thì field này **bị bỏ qua
lặng lẽ**. Tách ra thì mỗi hàm có đúng một việc.

---

## 29. Đối chiếu với tài liệu chính thức Zalo (22/09/2026)

`docs.zaloplatforms.com/docs/MA/api/user/user-information/getPhoneNumber#token-to-phone`

Phần request khớp đúng từng chi tiết với code đang chạy: **GET** `graph.zalo.me/v2.0/me/info`,
ba header `access_token` / `code` / `secret_key`, response `{data:{number}, error, message}`,
số dạng `"849123456789"`. Không phải sửa gì ở đó.

### Hai dữ kiện tài liệu nói mà đề bài không

**Token dùng MỘT lần, hết hạn sau 2 PHÚT.** Nghĩa là một lần gọi hỏng là **đốt luôn token** —
thử lại cùng token chỉ ra lỗi 119. Điều này đổi cách viết message lỗi: phải bảo người ta gọi
lại `getPhoneNumber()`, không phải "thử lại".

**Khoá lấy ở `developers.zalo.me` → Quản lý ứng dụng** của Zalo App — xác nhận chẩn đoán
error 117 hôm qua.

### Bảng mã lỗi: điều Zalo KHÔNG nói là lỗi của ai

`docs.zaloplatforms.com/docs/MA/api/errorCode`. Lời gốc của Zalo là bốn chữ tiếng Anh cộc lốc
và **không nói bên nào phải sửa**, mà khác biệt đó là tất cả: 116/117/118 thì mò trong Mini
App bao lâu cũng vô ích, 114/115/119 thì đổi khoá bao nhiêu lần cũng vô ích.

🔴 **118 = "code is invalid" nhưng thực chất là khoá ĐÚNG của SAI ỨNG DỤNG.** Đọc nguyên văn
thì ai cũng đi lùng token của Mini App. Đây là mã rất dễ gặp ngay sau khi thay khoá: nếu thay
xong mà ra 118 thì Mini App và Zalo App không phải cùng một app.

`ZALO_SERVER_CONFIG_ERRORS` / `ZALO_CALLER_ERRORS` dịch mã thành câu nói rõ ai sửa, **giữ
nguyên mã và lời gốc trong ngoặc** để còn tra tài liệu.

### 🔴 Bảng thông điệp phải là chuỗi thường, KHÔNG phải `_()` ở cấp module

Bản đầu tôi viết `116: _("...")` ngay trong dict ở cấp module. Sai: `_()` chạy **một lần lúc
import** và đóng băng ngôn ngữ mà worker tình cờ khởi động cùng — mọi request sau đó đều nhận
đúng ngôn ngữ đó, bất kể user là ai. Dict lưu chuỗi thường, `_()` gọi lúc throw. Có assert
chốt rằng mọi giá trị trong hai dict đều là `str`.

---

## 30. `vi.csv` — Frappe KHÔNG có cú pháp comment (22/09/2026)

Error Log `Error in translation file`:

```
Bad translation in 'customize_erpnext' for language 'vi':
['# Overtime Registration — list Help dialog (2026-07-21)']
```

`frappe/translate.py` đọc file dịch như sau:

```python
if len(item) in [2, 3]:      # -> nạp làm bản dịch
elif item:                   # -> frappe.log_error("Bad translation ...")
```

Dòng rỗng bị bỏ qua im lặng, nhưng **một dòng chỉ có 1 cột thì ghi Error Log mỗi lần
translation được build lại** (clear-cache, migrate, đổi ngôn ngữ). Dòng `# ...` (không có
dấu phẩy) rơi đúng vào đó. Đã xoá; ghi chú phân nhóm phải để ngoài file.

🔴 **Nguy hiểm hơn: comment CÓ dấu phẩy sẽ thành bản dịch thật, không báo gì.**
`# Ghi chú, gì đó` parse ra 2 cột và được nạp thẳng vào bảng dịch.
(Đã quét: `# In Stock` / `# Req'd Items` ở dòng 12258–12259 **không** phải comment — đó là
nhãn cột thật của ERPNext, `#` nghĩa là "số lượng". Giữ nguyên.)

### Cột thứ 3 = context, dùng để khoanh vùng bản dịch

```python
if len(item) == 3 and item[2]:
    key = item[0] + ":" + item[2]
```

Đây là cơ chế đúng để một module dịch riêng một từ mà không đè lên toàn hệ thống.

### ⚠ 26 khoá đang có bản dịch MÂU THUẪN — bản ở dòng SAU thắng

Chưa sửa: chọn từ nào là quyết định nghiệp vụ, và sửa cho đúng phải thêm **context** ở cả
chỗ gọi `_()`. Những cái đáng lo nhất là từ của một module đè lên thuật ngữ lõi ERPNext:

| Khoá | Đang dùng | Bị đè mất | Ảnh hưởng |
|---|---|---|---|
| `Posting Date` | Ngày cấp | Ngày hạch toán | **toàn bộ Kế toán / Kho** |
| `Submit` | Gửi đơn | Xác nhận | **mọi nút Submit** |
| `Submitted` | Đã hoàn thành | Đã xác nhận | mọi chứng từ |
| `New Issue` | Cấp mới | Vấn đề mới | Support / Helpdesk |
| `Stock` | Tồn | Hàng tồn kho | menu Kho |
| `Reload` | Tải lại | Nạp tiền | (dòng cũ vốn đã sai) |
| `Mode` | Chế độ | Mốt | (dòng cũ vốn đã sai) |

Danh sách đầy đủ 26 khoá: quét lại bằng đoạn ở mục này (đọc `vi.csv` bằng `csv.reader`, gom
theo cột 0, lọc những khoá có nhiều hơn một giá trị ở cột 1).

---

## 31. Rà soát REST vs custom API (22/09/2026) — đo, không đoán

Câu hỏi của đội Mini App: endpoint nào bỏ được để dùng thẳng `/api/resource/`?

Câu trả lời không nằm ở "tiện hơn" mà ở chỗ **luật nghiệp vụ sống ở đâu**. Đo bằng chính
API key của Mini App trên site thật:

| Thử | Kết quả |
|---|---|
| `PUT` ghi đè `total_km = 99999` | ✅ chặn — `set_total_km()` tính lại trong `validate()` |
| `PUT` nhảy `scheduled → completed` | ✅ chặn — `ALLOWED_TRANSITIONS` |
| Đọc `TIQN Driver` qua REST | ✅ không lộ `password` (Frappe cắt field Password) |
| `POST` tạo chuyến **đã `completed`**, 999.998 km, 50 triệu | 🔴 **TẠO ĐƯỢC** |
| `PUT` đổi `from_location` của yêu cầu **đã xếp xe** | 🔴 **ĐỔI ĐƯỢC** |
| `DELETE` một chuyến | 🔴 **XOÁ ĐƯỢC** (HTTP 202) |

### Vì sao hai lỗ đầu tồn tại: luật nằm ở endpoint, không nằm ở controller

`ALLOWED_TRANSITIONS` chỉ gác **UPDATE** — lúc `is_new()` không có dòng cũ để so, nên tạo
thẳng ở trạng thái cuối thì bảng đó không thấy gì. `create_trip()` có chặn, nhưng REST đi
vòng qua nó. Tương tự, luật "chỉ sửa nội dung khi còn `pending`" trước đây chỉ có trong
`update_request()`.

**Một luật chỉ sống ở một endpoint thì không phải là luật** — DocType luôn với tới được qua
REST, và key thì nằm sẵn trong file client. Đã chuyển cả hai vào controller:

* `TIQNVehicleTrip.validate_status_transition()` → chặn tạo mới ở trạng thái cuối, trừ khi
  `flags.allow_backdated_status` (cờ của **code server** khi ghi lịch sử: seeder, backfill —
  client chỉ gửi field, không gửi flags).
* `TIQNVehicleRequest.freeze_content_once_acted_on()` → đóng băng `CONTENT_FIELDS` khi trạng
  thái **trước khi lưu** đã qua `pending`.

⚠ Đọc trạng thái **trước khi lưu**, không phải trạng thái mới: người yêu cầu đổi ý gửi
"notes + status=cancelled" trong MỘT lần gọi; đọc trạng thái mới là từ chối chính cái huỷ đó.
Bản đầu tôi viết sai chỗ này và làm đỏ một assert đã có từ trước.

### Kết luận từng endpoint

**Giữ custom** (REST không làm được, hoặc làm sai):

* `get_trips` / `get_trip` / `get_today_trips_by_driver` — ghép `vehicle_name`,
  `license_plate`, `driver_name`, `driver_zalo_id_by_oa` (2 truy vấn gộp, không phải N+1) và
  **chuẩn hoá định dạng dây**. REST trả `depart_time` thô là `"6:30:00"` — thiếu số 0, và đó
  đúng là thứ đã phá sắp xếp theo giờ **hai lần** trong dự án này.
* `get_trip` — hành khách trả theo tên khoá của hợp đồng (`request_id`, `from_location`,
  `order`), không phải tên cột DB (`request`, `pickup_location`, `pickup_order`).
* `create_trip` / `update_trip` — `TRIP_EDITABLE_FIELDS` (REST cho ghi `template_id`,
  `confirmed_at`, GPS), `PASSENGER_ALIASES`, chuẩn hoá datetime, bắn realtime.
* `update_request` — `REQUEST_EDITABLE_FIELDS`.
* `get_vehicles` / `get_vehicle` — `current_trip` là giá trị **tính**, không lưu.
* `combine_requests_to_trip`, `verify_driver_login`, `get_today_stats`, `get_trip_report`,
  `download_trip_report_excel`, `decode_phone_token` — đội Mini App đã tự xếp đúng.

**Bỏ được** nếu Mini App chịu tự format: `get_requests` / `get_request` (chỉ thêm định dạng
datetime), `cancel_trip` / `acknowledge_route_change` (bọc mỏng quanh một field). Giữ lại vì
đổi sang REST thì client phải tự lo chuẩn hoá — đúng chỗ dễ lệch nhất giữa hai bên.

### `site_config["rate_limit"]` KHÔNG phải cái anh nghĩ

```python
self.limit = int(limit * 1000000)
self.key   = frappe.cache.make_key(f"rate-limit-counter-{self.window_number}")
...
frappe.cache.incrby(self.key, self.duration)   # duration = MICRO-GIÂY
```

Khoá **không có danh tính** và giá trị cộng vào là **thời gian xử lý**. Nên nó là **ngân sách
CPU cho TOÀN SITE mỗi cửa sổ**, không phải bộ đếm request và không theo IP. Bật nó nghĩa là
khi cả công ty cộng lại tiêu hết N giây xử lý thì **mọi người cùng nhận 429**, kể cả 9 điều
hành đang dùng Desk. Sai công cụ hoàn toàn.

Đúng công cụ là decorator `@rate_limit(...)` — theo IP, theo từng endpoint. Đã gắn cho 3 chỗ
đáng bị lạm dụng: `verify_driver_login` (30/giờ/IP), `decode_phone_token` (60/giờ/IP),
`download_trip_report_excel` (20/giờ/IP — mỗi lần gọi ghi một file xuống đĩa).

⚠ Hạn mức rộng tay có lý do: Mini App chạy trong webview điện thoại, **cả một cell 4G có thể
ra cùng một địa chỉ NAT của nhà mạng**. Siết chặt là khoá nhầm cả nhóm người dùng thật.
(nginx đã `proxy_set_header X-Forwarded-For $remote_addr` và Frappe đọc đúng header đó, nên
IP thấy được là IP thật của client, không phải của proxy.)

---

## 32. `id_by_oa = "34"` — giá trị xấu trong DỮ LIỆU tái tạo đúng cái hỏng đã chặn ở CODE

Mục 28 bỏ fallback `zalo_user_id` để nút chat **ẩn** thay vì **bấm không ra gì**. Ngày 22/09
dòng dispatcher được lưu với `id_by_oa = "34"` — một giá trị đặt tạm. Không null, nên
`get_dispatcher_zalo_id()` trả nó ra, Mini App **hiện** nút chat, và bấm không ra gì.

Đúng y hệt cái hỏng cũ, chỉ khác là lần này giá trị xấu đến từ **dữ liệu** chứ không từ code.
Bỏ fallback ở code là cần, nhưng chưa đủ.

`TIQNZaloRoleMap.validate_id_by_oa()`: chỉ chữ số, tối thiểu `MIN_ID_BY_OA_DIGITS = 10`.
ID thật trên site này là 19 chữ số (`4295057266797901281`), nên sàn 10 không bao giờ chạm
tới ID thật — nó chỉ để bắt giá trị gõ tay. **Cố ý là kiểm tra HÌNH DẠNG, không phải đặc tả
định dạng**: Zalo không công bố độ dài ID.

Đặt ở controller nên cả `update_zalo_id_by_oa`, REST PUT lẫn form Desk đều dính — cùng
nguyên tắc với hai lỗ ở mục 31.

⚠ Validator chỉ chạy lúc **save**; giá trị xấu đã nằm sẵn trong DB thì phải xoá tay. Đã xoá
`'34'`, `dispatcher_zalo_id` trở lại `None`.

⚠ Test cũ dùng ID giả kiểu `"oa-999"` bị chính validator này chặn — đã đổi sang chuỗi 19 chữ
số thật. Dữ liệu giả mà không giống dữ liệu thật thì không kiểm được luật áp lên dữ liệu thật.

### Đổi tên khoá cấu hình

`zalo_app_secret_key` → **`zalo_app_vehicle_management_secret_key`**, để sau này còn Zalo app
khác không lẫn. Đổi ở 5 file (code, test, 2 tài liệu, `vi.csv`) + `site_config.json`, giữ
nguyên giá trị. Không để fallback về tên cũ: hai nguồn cho một giá trị là cách chúng bắt đầu
lệch nhau.

---

## 33. Chuyến cố định: so khớp HH:MM chính xác = 3 chuyến chiều CHƯA TỪNG được tạo

Yêu cầu: *"chỉ nên tạo trip trước giờ khởi hành 15 phút, không tạo trước cho cả ngày"*. Đi
sửa thì phát hiện luật cũ còn hỏng nặng hơn thế.

### Luật cũ

```python
depart = _fmt_time(schedule.depart_time)
if not force_all and depart != now_hhmm:      # so CHUỖI, chính xác từng phút
    not_due.append(schedule.name); continue
```

cộng với `hooks.py`:

```python
"30 6 * * *": [...create_scheduled_trips],
"0 17 * * *": [...create_scheduled_trips],
```

Lịch cố định đi lúc **06:30** và **17:15**. Cron chạy lúc **06:30** và **17:00**.

| Giờ đi | Cron có tick không | Kết quả |
|---|---|---|
| 06:30 | có | tạo được |
| 17:15 | **không** | 🔴 **KHÔNG BAO GIỜ được tạo** |

Ba chuyến chiều, mỗi ngày làm việc, **chưa từng** do scheduler sinh ra. Và không có gì trong
log: lịch không khớp chỉ bị đếm vào `not_due`, đúng như lịch chủ nhật hay lịch đã tắt. Trên
màn hình thì vẫn thấy đủ chuyến chiều — vì **seeder tạo chúng**, không phải scheduler. Đúng
kiểu bug mà dữ liệu demo che mất.

### Luật mới

```python
SCHEDULE_LEAD_MINUTES = 15

minutes_away = (get_datetime(f"{on_date} {depart}") - now).total_seconds() / 60
if not (0 <= minutes_away <= SCHEDULE_LEAD_MINUTES):
    not_due.append(schedule.name); continue
```

cộng `"*/5 * * * *"` — một mục cron duy nhất.

🔴 **Đừng quay lại tick giờ cố định.** Làm thế là bắt `cron time` và `depart_time` phải khớp
tay **mãi mãi**: đổi giờ shuttle trong Desk mà quên sửa `hooks.py` là mất chuyến, im lặng.
Cửa sổ 15 phút + tick 5 phút cho mỗi lịch **ba lần** cơ hội, và cũng sống sót qua một tick
cron chạy trễ vài giây — thứ mà so khớp từng phút không làm được.

Có assert chốt rằng cron của `create_scheduled_trips` chỉ còn **một** mục và nó bắt đầu bằng
`*/`, để không ai vô tình đặt lại giờ cố định.

### Điều này đổi gì trên UI

`get_fixed_templates_for_driver()` gọi lúc 8 giờ sáng trả lịch chiều với `trip = null`. Đó là
**đúng**, không phải thiếu dữ liệu. Tài xế muốn đi sớm vẫn bấm được —
`create_trip_from_template()` idempotent, tạo ngay và lần cron sau sẽ bỏ qua.

### 🔴🔴 `bench restart` KHÔNG đồng bộ lịch cron — và một method chỉ có MỘT job

Đây là tầng sâu hơn, tìm ra sau khi đã sửa code và restart. Lịch cron **không đọc từ
`hooks.py` lúc chạy**; nó nằm trong bảng `Scheduled Job Type`, và bảng đó chỉ được đồng bộ
bởi **`bench migrate`**. Sau restart, DB vẫn ghi `cron_format = "0 17 * * *"` trong khi
`hooks.py` đã là `*/5 * * * *`.

```python
# frappe/core/doctype/scheduled_job_type/scheduled_job_type.py: insert_single_event()
if job_name := frappe.db.exists("Scheduled Job Type", {"method": event}):
    ...
```

🔴 **Khoá theo `method`, KHÔNG phải theo `(method, cron)`.** Khai một method dưới **hai**
biểu thức cron thì chỉ **một** bản ghi tồn tại — cái xử lý sau ghi đè cái trước, không lỗi,
không cảnh báo.

Nên sự thật đầy đủ tệ hơn mục trên: `"30 6"` bị `"0 17"` **nuốt** ngay từ đầu. Chỉ còn một
job duy nhất chạy lúc 17:00, mà không lịch nào đi lúc 17:00 ⇒ **scheduler CHƯA TỪNG tạo một
chuyến cố định nào**, cả sáng lẫn chiều, từ ngày dựng module. Bằng chứng: bản ghi duy nhất có
`last_execution = 2026-09-22 17:00:06` — nó vẫn chạy đều, chỉ là chẳng tạo gì.

**Sửa hooks cron thì trình tự bắt buộc là `bench migrate` (không phải chỉ restart).**

Hai assert chốt lại, áp cho toàn bộ hooks chứ không riêng module này:
* không method nào khai dưới nhiều cron
* `Scheduled Job Type` trong DB khớp `hooks.py`

Đã quét cả app: 22 cron entry / 22 method riêng biệt, DB khớp hết — chỗ này là ca duy nhất.

### Click thẻ xe: Desk lọc, Mini App mở chi tiết

Khác biệt **có chủ ý**, đừng "sửa" cho giống nhau nếu không có yêu cầu:

| | Click xe đang bận | Click xe rảnh |
|---|---|---|
| Trang Desk | **lọc danh sách chuyến** theo xe (bấm lần nữa bỏ lọc) | không làm gì |
| Mini App | mở **chi tiết chuyến** | không làm gì |

Bảng Desk rộng, xem cả đội xe cùng lúc nên lọc hợp lý hơn; Mini App là màn điện thoại nên đi
thẳng vào chi tiết hợp lý hơn.

Cả hai đều **không** gắn `cursor: pointer` cho xe rảnh. Một thẻ trông bấm được mà không phản
hồi cũng tệ ngang một thẻ bấm không ra gì — nửa còn lại của vấn đề mà dễ quên.

⚠ `hooks.py` đổi ⇒ **`bench migrate`** (restart thôi không đủ, xem ngay dưới).

---

## 34. Tên chuyến: chỉ lộ trình

`TIQNVehicleTrip.build_trip_name()` trước đây sinh ra:

```
Toray VSIP Quảng Ngãi - Sân bay Chu Lai | Ga Quảng Ngãi 12:23 2026-09-23
```

Giờ và ngày **đã có cột riêng** (`depart_time`, `trip_date`) và luôn hiện ngay cạnh tên ở mọi
chỗ — thẻ chuyến trên trang Desk, danh sách Mini App, báo cáo KM. Nhét vào tên chỉ làm tiêu
đề dài tới mức bị cắt trên điện thoại, mà không thêm thông tin nào.

Giờ chỉ còn lộ trình, nối bằng `→` (thống nhất với `seed_month.py` và cách trang Desk vẽ lộ
trình):

```
Toray VSIP Quảng Ngãi → Sân bay Chu Lai
```

Hàm chỉ chạy khi `trip_name` **rỗng**. Tên người dùng tự đặt, và
`schedule.trip_name_template` của chuyến cố định, không bị dựng lại.

⚠ **`trip_name` là cột `Data` = 140 ký tự.** Thêm chặn cắt vì chuyến gộp giờ có thể mang
nhiều điểm đến nối lại trong `to_location` — vượt 140 thì **INSERT gãy**, Frappe không tự cắt
hộ.

### Dấu `|` trong `to_location` là do CLIENT, không phải server

Chuyến `TIQN-TRIP-2026-0662` có `to_location = "Sân bay Chu Lai | Ga Quảng Ngãi"`, `owner =
miniapp@tiqn.com.vn`. Khi gộp hai yêu cầu đi hai nơi khác nhau, Mini App nối hai điểm đến vào
**một** chuỗi.

`combine_requests_to_trip` phía server chỉ lấy `first.to_location` — một giá trị. Trang Desk
cũng vậy (`dialog.set_value('to_location', first.to_location)`).

⚠ Model đã có **bảng con `stops`** (`location`, `landmark`, `stop_order`) đúng cho việc nhiều
điểm dừng. Nối vào `to_location` thì báo cáo, bộ lọc và tìm kiếm đều coi
`"Sân bay Chu Lai | Ga Quảng Ngãi"` là **một địa điểm** không tồn tại. Cần thống nhất lại với
đội Mini App.

---

## 35. Đơn giản hoá chuyến: bỏ `stops`, điểm đến phụ vào Dispatcher Note (23/09)

Mô hình cũ có ba chỗ chứa địa điểm: `to_location`, bảng con `stops`, và
`passengers[].pickup_location`. Ba nguồn cho một khái niệm là ba cơ hội để chúng lệch nhau.

**`stops` bị bỏ hẳn** — `TIQN Trip Stop` + field `stops` + khoá `stops` trong payload.
Kiểm trước khi xoá: **0 bản ghi**, chưa từng dùng.

Không mất thông tin gì:

| Cần biết | Lấy ở đâu |
|---|---|
| Đón ai, ở đâu | `passengers[].from_location` — đã có sẵn, lấy từ chính yêu cầu |
| Chuyến đi đâu | `to_location` — một giá trị |
| Còn ghé đâu nữa | `dispatcher_note` — cùng chỗ với mọi chỉ dẫn khác cho tài xế |

### 🔴 Bảng con bị xoá để lại BẢNG MỒ CÔI trong DB

`bench migrate` in `Orphaned DocType(s) found: TIQN Trip Stop` và xoá bản ghi DocType, nhưng
**`tabTIQN Trip Stop` vẫn còn nguyên trên đĩa**. Cùng họ với bẫy "xoá field khỏi JSON không
drop cột". Phải dọn tay:

```python
frappe.db.sql_ddl("DROP TABLE `tabTIQN Trip Stop`")
```

⚠ Đếm số dòng trước khi drop. Ở đây là 0 nên an toàn; khác 0 thì đó là dữ liệu thật.

### `_extra_destinations()` + `_build_dispatch_note()`

Chuyến gộp lấy `to_location` của **yêu cầu đầu tiên**. Các điểm đến khác, khử trùng không
phân biệt hoa thường, bỏ rỗng, nối thành `"Ghé thêm: A, B"` và đặt **trước** ghi chú
dispatcher tự gõ — chỗ ghé là thứ tài xế phải hành động, đẩy nó xuống dưới còn tệ hơn không
có.

🔴 **Tuyệt đối không nối nhiều nơi vào `to_location`.** Mini App từng gửi
`"Sân bay Chu Lai | Ga Quảng Ngãi"`. Field đó bị so khớp, lọc và gom nhóm trong báo cáo KM ⇒
chuỗi nối lại thành **một địa điểm không tồn tại**, mọi thống kê theo điểm đến đều sai.

### ⚠ `EXTRA_STOPS_PREFIX` cố ý KHÔNG bọc `_()`

Nó được **ghi vào dữ liệu** (`dispatcher_note`), không phải nhãn UI. Dịch lúc ghi sẽ đóng
băng ngôn ngữ mà người gọi tình cờ có, rồi tài xế Việt đọc lại sau đó hàng tháng. Cùng loại
ngoại lệ với nội dung trang `vehicle-dispatch`.

**Ranh giới chung: nhãn/thông điệp UI → `_()` + `vi.csv`. Giá trị lưu vào field → một ngôn
ngữ cố định.**

### Hệ quả cho Mini App

`dispatcher_note` từ nay mang **thông tin bắt buộc đọc**, không còn là ghi chú tuỳ ý — thẻ
chuyến phải hiển thị nó.

---

## 36. Bỏ DocType `TIQN Driver` — tài xế LÀ một tài khoản Zalo (23/09)

Trước đây một người có **hai** bản ghi: một `TIQN Driver` và một dòng `TIQN Zalo Role Map`
trỏ về nó qua `driver_ref`. Hai bản ghi cho một người là hai cơ hội để chúng lệch nhau, và
chúng đã lệch thật: **ba tài khoản Zalo khác nhau cùng trỏ `driver_ref` về một tài xế**.

Giờ chỉ còn `TIQN Zalo Role Map`. Tài xế = tài khoản Zalo có `role = driver` và một `vehicle`
được gán.

| Field cũ trên `TIQN Driver` | Về đâu |
|---|---|
| `driver_name` | `display_name` |
| `phone` | `phone` |
| `zalo_user_id` | **chính là docname** |
| `assigned_vehicle` | `vehicle` (thay luôn `driver_ref`) |
| `is_active` | `disabled` (đảo nghĩa) |
| `is_leader`, `notes` | cùng tên |
| `password` | 🔴 **bỏ hẳn** |

### Ai vào app cũng là `requester` trước

`role` mặc định `requester`. Quản lý nâng lên `driver` (kèm xe) hoặc `dispatcher`. Đây là lý
do một patch khởi tạo **không thể** tạo tài xế: nó không biết trước Zalo ID của ai.

`disabled` chặn một tài khoản dùng app mà **không xoá bản ghi** — lịch sử chuyến và yêu cầu
vẫn trỏ tới đó. `get_user_by_zalo_id()` trả `None` cho người bị chặn, **không** trả vai trò
kèm cờ: mọi chỗ gọi đã biết xử lý `None`, còn một cờ phụ thì chỉ cần sót MỘT chỗ kiểm là lọt.

### 🔴 Đăng nhập bằng mật khẩu đã xoá

`verify_driver_login()`, field `password`, bốn hàm khoá chống dò, hằng số `RATE_LOGIN` /
`MAX_LOGIN_ATTEMPTS` / `LOCKOUT_SECONDS` — xoá hết.

Nó ra đời vì lúc đó chưa nối được danh tính Zalo. Giờ đã nối: vai trò trả về từ
`get_user_by_zalo_id()` **chính là** đăng nhập. Giữ thêm một đường đăng nhập thứ hai bằng tên
+ mật khẩu dùng chung, trên một DocType không còn tồn tại, là giữ một cánh cửa mà không ai
nhớ ra để khoá.

### Lịch cố định KHÔNG còn bắt buộc ghi tài xế

`TIQN Fixed Trip Schedule.driver` giờ tuỳ chọn. Lịch nói **xe nào chạy ca nào**; ai lái thì
tra tại thời điểm tạo chuyến qua `set_default_driver()`.

🔴 Chính bản sao thứ hai của "ai lái xe này" là thứ đã mục nát khi tài xế được đổi tên
(22/09) và làm chết cả sáu lịch. Bỏ nó đi thì lỗi đó không lặp lại được nữa.

Hệ quả: `get_fixed_templates_for_driver()` phải suy "lịch của tài xế này" **qua XE**, không
qua `schedule.driver`. Lịch có ghi đích danh vẫn được tính — đó là trường hợp cố tình giao
cho người khác với tài xế mặc định.

### Nhiều tài khoản Zalo cùng một xe: CHO PHÉP

Tài xế thay ca là chuyện thật. `set_default_driver()` chọn bản ghi tạo sớm nhất (bỏ qua
`disabled`) để kết quả ổn định giữa các lần chạy; ai lái thật thì dispatcher gõ đè.

### ⚠ `Role Map.phone` là fieldtype `Phone`, khác `Data` của Driver cũ

Nó **bắt buộc mã quốc gia**: `"0900000000"` bị từ chối, phải `"+84-900000000"`. Điều này đổi
lý do tồn tại của `phone_local` trong `decode_phone_token`: trước đây để đối chiếu với số nội
địa đã lưu, giờ chỉ để **hiển thị và bấm gọi** — vì dạng nội địa không lưu được nữa.

### Dọn dẹp bắt buộc sau khi xoá DocType

`bench migrate` xoá bản ghi DocType nhưng **để lại**:

```python
frappe.db.sql_ddl("DROP TABLE IF EXISTS `tabTIQN Driver`")                       # bảng mồ côi
frappe.db.sql_ddl("ALTER TABLE `tabTIQN Zalo Role Map` DROP COLUMN `driver_ref`")  # cột mồ côi
frappe.db.sql("DELETE FROM `__Auth` WHERE doctype='TIQN Driver'")                  # mật khẩu mồ côi
```

⚠ `__Auth` là chỗ thứ ba dễ quên nhất: nó giữ mật khẩu đã mã hoá của một DocType không còn
tồn tại, và không có gì trong `migrate` dọn hộ.

⚠ Link chết không tự sạch: 6 lịch cố định vẫn giữ tên tài xế cũ sau khi bảng bị xoá. **Luôn
quét lại bằng LEFT JOIN sau mỗi lần đổi đích của một Link field.**

---

## 37. Chuyến gán theo XE, không gán cho người (23/09)

Field `driver` **không còn tồn tại** trên `TIQN Vehicle Trip` lẫn `TIQN Fixed Trip Schedule`.

Xe là đơn vị. Tài xế xe nào thì thấy chuyến của xe đó. `driver`, `driver_name`,
`driver_phone`, `driver_zalo_user_id`, `driver_zalo_id_by_oa` vẫn có trong payload — nhưng là
**giá trị suy ra lúc đọc** từ `_driver_lookup(vehicle)`, không phải cột lưu.

### Vì sao không lưu

Lưu `driver` trên chuyến = giữ một bản sao thứ hai của "ai lái xe này". Bản sao đó đã mục nát
**hai lần** trong chính dự án này:

* đổi tên tài xế (22/09) làm chết cả 6 lịch cố định, cron im lặng không tạo chuyến nào;
* ba tài khoản Zalo cùng trỏ `driver_ref` về một tài xế.

Không lưu thì không mục nát được. Đổi tài xế của một xe là mọi chuyến của xe đó — kể cả chuyến
đã tạo từ trước — hiển thị đúng người ngay, không cần backfill.

### 🔴 Cái mất: không còn thống kê km theo tài xế

`summary.km_by_driver` và cột **Driver** trong report KM đã bỏ.

Suy tài xế từ xe trả lời đúng câu hỏi **BÂY GIỜ** ("gọi ai về chuyến này"), nhưng **sai** câu
hỏi **LÚC ĐÓ** ("tháng 9 ai chạy bao nhiêu km"): tài xế đổi xe là lịch sử bị viết lại, âm
thầm, không ai biết.

**Thà không có con số còn hơn có một con số lặng lẽ đổi nghĩa.** Nếu sau này thật sự cần quy
trách nhiệm theo người thì phải lưu tài xế **tại thời điểm chạy** như một snapshot bất biến,
không phải một Link.

Đơn vị tính tiền vẫn nguyên: `total_km` theo **xe**, đúng thứ TIQN trả tiền.

### `confirmed_at` đã bỏ — field chỉ ghi, không ai đọc

Nó được ghi ở 4 chỗ (`stamp_status_timestamps`, `confirm_trip`, `create_trip_from_template`,
seed) và **không đọc ở đâu cả**: không có trong report, không hiện trên trang, không có logic
nào rẽ nhánh theo nó. Trạng thái `confirmed` vẫn còn; chỉ cái dấu thời gian là dư.

⚠ Cách phát hiện loại field này: grep tên field rồi phân loại từng chỗ là **ghi** hay **đọc**.
Toàn ghi = xoá được.

### Trang Desk: ô Tài xế thành dòng chữ

Dialog Tạo chuyến / Xếp xe giờ **chỉ chọn xe**. Tài xế hiện ra dưới dạng HTML tĩnh
(`driver_hint`) để dispatcher xác nhận đang chọn đúng xe — không còn là ô Link sửa được, vì
không còn chỗ nào để lưu giá trị đã sửa.

### 🔴 Lại là bảy cột mồ côi

`bench migrate` xoá field khỏi meta nhưng **không drop cột**. Sau đợt này phải dọn tay:

```python
ALTER TABLE `tabTIQN Vehicle Trip`        DROP COLUMN `driver`
ALTER TABLE `tabTIQN Vehicle Trip`        DROP COLUMN `confirmed_at`
ALTER TABLE `tabTIQN Fixed Trip Schedule` DROP COLUMN `driver`
```

Không drop thì `frappe.get_all(..., fields=["driver"])` vẫn chạy được trên cột rác và ta không
bao giờ phát hiện còn sót chỗ nào đọc nó. Drop xong, chỗ sót **gãy ngay** với
`Unknown column 'driver' in 'SELECT'` — đó là tính năng, không phải phiền toái.

---

## 38. `TIQN Vehicle.status`: bốn giá trị còn ba (23/09)

```
available · in_trip · maintenance · broken   →   available · in_trip · not_available
```

**Xe là của công ty đối tác.** TIQN không quản lý bảo dưỡng, không theo dõi hư hỏng, không
sở hữu tài sản — chỉ trả tiền theo km thực tế từng chuyến. Phân biệt "đang bảo trì" với
"đang hỏng" là thông tin của bên đối tác, không phải của hệ thống này. Điều duy nhất bảng
điều hành cần biết là **xếp được xe này hay không**.

`MANUAL_STATUSES = ("available", "not_available")` — `in_trip` vẫn do hệ thống tự đặt qua
`sync_vehicle_status()`, người dùng không gõ tay được.

`sync_vehicle_status()` bỏ qua xe `not_available` y như trước bỏ qua `maintenance`/`broken`:
có người cố ý đặt như vậy, một chuyến kết thúc không được tự kéo xe về `available`.

⚠ Dữ liệu cũ phải UPDATE trước khi migrate, nếu không bản ghi mang giá trị không còn trong
`options` và Frappe sẽ báo lỗi ở lần lưu kế tiếp:

```sql
UPDATE `tabTIQN Vehicle` SET status='not_available' WHERE status IN ('maintenance','broken')
```

`vi.csv`: hai dòng `maintenance` / `broken` gộp thành `not_available,Không sẵn sàng`.
