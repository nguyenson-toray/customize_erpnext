# Employee Portal — Hợp đồng giao diện với Zalo Mini App "Cổng nhân viên"

> **Phiên bản contract: 1.7.0 (26/10/2026).** Giai đoạn hiện tại **chỉ mở phiếu lương** (+ thông báo) — xem §3.5.
> **Đã chạy thật:** xác thực + phiếu lương + thông báo (M1). **M2** (các màn chỉ xem) code xong, chờ restart.
> Chưa code: tạo/hủy đơn nghỉ, giấy tờ, giải trình (M3) và tin OA (M4). Xem §13. Tài liệu này được viết trước để đội Mini App dựng 21 màn bằng mock
> (dữ liệu mẫu ở mỗi endpoint), góp ý, rồi backend mới code theo đúng bản đã chốt.
> Mọi thay đổi sau khi chốt phải ghi vào [§13 Nhật ký thay đổi](#13-nhật-ký-thay-đổi).
>
> Thiết kế UI: `customize_erpnext/Zalo Mini App – Cổng nhân viên ERPNext.html` (21 màn, đánh số 00–20).
> Plan nội bộ backend: `.claude/plans/zalo_payslip_portal.md`.
> App này **khác hẳn** app quản lý xe (`vehicle_management/API_CONTRACT.md`) ở phần xác thực —
> đọc kỹ §2, đừng chép cách gọi của app xe sang.

---

## Mục lục

1. [Kết nối](#1-kết-nối)
2. [Xác thực](#2-xác-thực)
3. [Quy ước chung](#3-quy-ước-chung)
4. [Mã lỗi](#4-mã-lỗi)
5. [Object dùng chung](#5-object-dùng-chung)
6. [Cấu hình & phiên đăng nhập](#6-cấu-hình--phiên-đăng-nhập) — màn 00–05, 07, 09, 10
7. [Trang chủ & thông báo](#7-trang-chủ--thông-báo) — màn 06, 08
8. [Nghỉ phép](#8-nghỉ-phép) — màn 11, 12, 12b, 13, 13b
9. [Chấm công, giải trình, tăng ca](#9-chấm-công-giải-trình-tăng-ca) — màn 14–18
10. [Phiếu lương](#10-phiếu-lương) — màn 19, 20
11. [Bảng tra màn hình → endpoint](#11-bảng-tra-màn-hình--endpoint)
12. [Hướng dẫn cấu hình Zalo App](#12-hướng-dẫn-cấu-hình-zalo-app)
13. [Nhật ký thay đổi](#13-nhật-ký-thay-đổi)
14. [Câu hỏi còn treo](#14-câu-hỏi-còn-treo)

---

## 1. Kết nối

```
Base     https://erp.tiqn.com.vn:8888/api/method/customize_erpnext.api.employee_portal.<method>
Header   X-Portal-Token: <session token>        (mọi endpoint trừ get_config và login)
Header   X-Portal-Client-Version: <x.y.z>       (khuyến nghị, mọi request — xem CLIENT_TOO_OLD)
Body     GET  → query string
         POST → application/x-www-form-urlencoded hoặc application/json
         Upload → multipart/form-data
Kết quả  HTTP 200, dữ liệu ở  json.message  (Frappe luôn bọc trong "message")
```

🔴 **KHÔNG có API key / API secret nào trong Mini App.** Khác app xe. Không gửi header
`Authorization` dưới bất kỳ dạng nào — Frappe hiểu `Authorization: Bearer …` là OAuth và trả
`401 AuthenticationError` cho token lạ.

🔴 **Gọi `fetch` với `credentials: "omit"`.** Nếu webview tình cờ mang cookie phiên ERP
(`sid`) của ai đó, Frappe sẽ đòi CSRF token cho mọi POST và từ chối. Mini App không bao giờ
cần cookie.

```js
const res = await fetch(`${BASE}/get_home`, {
  method: "GET",
  credentials: "omit",
  headers: { "X-Portal-Token": token, "X-Portal-Client-Version": APP_VERSION },
});
const body = (await res.json()).message;   // { ok, data | error, server_time }
```

**CORS:** server cho phép mọi origin và tự trả lại đúng các header mà preflight xin
(`Access-Control-Request-Headers`), nên `X-Portal-Token` / `X-Portal-Client-Version` dùng được.

**Đúng HTTP method là bắt buộc.** Mỗi endpoint ghi rõ GET hay POST. Sai method → Frappe trả
**HTTP 403** với body của Frappe (không có phong bì `ok` ở §3). Quy tắc: **có ghi gì vào DB là
POST** — kể cả `get_payslip` (ghi log xem phiếu). Frappe rollback mọi request GET, nên một
endpoint ghi mà bị gọi bằng GET sẽ "thành công" mà không lưu gì.

---

## 2. Xác thực

### 2.1 Nguyên tắc

- Mini App **không bao giờ** gửi mã nhân viên, Zalo user ID hay số điện thoại để "nói mình là ai".
  Server tự hỏi Zalo bằng token Zalo cấp, rồi cấp **session token của ERP**.
- Mọi endpoint nghiệp vụ suy ra nhân viên **từ session token**. Không endpoint nào có tham số
  `employee`. Đổi tham số `id`/`period` cũng chỉ đọc được dữ liệu của chính mình
  (dữ liệu người khác → `NOT_FOUND`, không phải `FORBIDDEN`, để không lộ là bản ghi có tồn tại).

### 2.2 Luồng đăng nhập (màn 00 → 02)

**Zalo luôn xác nhận "ai"** (User ID lấy từ `access_token`, server tự hỏi Zalo). **Số điện thoại** đến từ
một trong hai nguồn:
1. **Zalo** — Mini App gửi kèm `phone_token` (người dùng cho phép đọc SĐT). Server lưu số này vào tài khoản.
2. **Tài khoản đã lưu** — không có `phone_token` thì server dùng SĐT đã có trong tài khoản Zalo đó: do
   **phòng Nhân sự gán tay** trên ERP, hoặc lưu từ một lần đăng nhập trước có quyền SĐT.

```
Mini App                                   ERPNext                                Zalo
   │ 1. getAccessToken()                      │                                     │
   │ 2. getPhoneNumber() → { token }  (tuỳ chọn, có thể bị từ chối / không có trên simulator)
   │ 3. POST login(access_token[, phone_token])─▶                                   │
   │                                          │ 4. /v2.0/me        (access_token) ──▶ zalo_user_id
   │                                          │ 5. /v2.0/me/info   (chỉ khi có phone_token) ─▶ SĐT
   │                                          │ 6. SĐT = (5) hoặc SĐT đã lưu trong tài khoản
   │                                          │ 7. khớp 9 số cuối với hồ sơ nhân viên, cấp session token
   │ ◀──────────── { result, token, zalo_user_id, … } ──│
```

- Bước 2 bị từ chối → **vẫn gọi `login` không kèm `phone_token`**. Nếu phòng Nhân sự đã gán SĐT cho tài
  khoản thì vẫn vào được; nếu chưa → `NO_PHONE` (màn 03, xem §2.3).
- 🔴 `phone_token` dùng **một lần**, hết hạn sau **2 phút**. Gọi `login` ngay sau `getPhoneNumber()`.
  Lỗi `ZALO_TOKEN_USED` → xin token mới bằng `getPhoneNumber()`, **đừng** gửi lại token cũ.
- Server so SĐT theo **9 số cuối** (`0905123456`, `84905123456`, `+84 905 123 456` là một).
- SĐT khớp nhiều hồ sơ (nhân viên nghỉ rồi vào lại với mã mới) → server chọn **mã mới nhất**.
- Hồ sơ nhân viên có 2 cột SĐT (từ 1.2.0): **SĐT đăng ký với công ty** được so trước; chỉ khi không ai có
  số đó mới so tiếp **SĐT Zalo** (phòng Nhân sự nhập khi SĐT Zalo của nhân viên khác SĐT đăng ký). Client
  không phải làm gì; màn 04 có thể gợi ý "SĐT Zalo khác SĐT đăng ký với công ty → báo phòng Nhân sự".
- **Tên Zalo** (từ 1.2.0): server tự đọc tên hiển thị từ Zalo (`/v2.0/me`) mỗi lần `login` và lưu vào tài
  khoản để phòng Nhân sự nhận ra người dùng. Zalo chỉ trả tên khi người dùng đã cho Mini App quyền thông
  tin hồ sơ (`scope.userInfo`); không có thì để trống, **không** ảnh hưởng đăng nhập. Client **không** gửi tên.
- **"Cập nhật số điện thoại" từ app** (màn 09): chạy lại bước 1–3 **có** `phone_token`. Số Zalo xác nhận
  luôn thay số đang lưu (kể cả số phòng Nhân sự gán). Lưu token mới server trả về.

### 2.3 Kết quả `login` → màn hình

| `result` | Nghĩa | Có token? | Màn |
|---|---|---|---|
| `ACTIVE` | Đang làm việc | ✅ | 06 (+07 nếu `oa.show_invite`) |
| `READ_ONLY` | Đã nghỉ việc, còn trong hạn chỉ xem (mặc định 30 ngày từ ngày nghỉ) | ✅ | 10, và mọi màn ở chế độ chỉ xem |
| `NO_PHONE` | Không có `phone_token` và tài khoản chưa có SĐT | ❌ | 03: nút "Cho phép đọc SĐT" (thử lại bước 2) + hiện **`zalo_user_id`** để gửi phòng Nhân sự gán SĐT |
| `NOT_FOUND` | SĐT không khớp hồ sơ nào | ❌ | 04 (hiện `masked_phone` **và** `zalo_user_id`; form "Yêu cầu tạo tài khoản" theo `link_request` — §6 `link_employee_request`) |
| `EXPIRED` | Hết hạn chỉ xem, hoặc hồ sơ ngừng hoạt động | ❌ | 05 |
| `DISABLED` | Phòng Nhân sự khoá tài khoản Mini App. (Tài khoản mới không khớp nhân viên được phép dùng — người ngoài, người nghỉ quá hạn — cũng bị server tự khoá, nhưng vẫn trả `NO_PHONE`/`NOT_FOUND`/`EXPIRED`, không trả `DISABLED`.) | ❌ | 05 (dùng `message`) |
| `DEV_NOT_ALLOWED` | *(chỉ `dev_login`)* tài khoản chưa được phép đăng nhập dev | ❌ | màn dev: hiện `zalo_user_id` + `message` |

Các kết quả không có token **không phải lỗi**: `ok: true`, chỉ là không có token.
Nút "Thử lại" ở màn 03/04 = chạy lại cả bước 1–3 (token SĐT cũ đã dùng).

`zalo_user_id` hiển thị cho người dùng dạng chọn/copy được, kèm câu "Gửi mã này cho phòng Nhân sự".
Phòng Nhân sự tìm mã đó trong ERP (TIQN Portal Account), gán SĐT của nhân viên → người dùng bấm "Thử lại"
là vào được.

### 2.4 Session token

- Chuỗi ngẫu nhiên ~43 ký tự, **lưu bằng `setStorage` của Zalo SDK**, gửi trong `X-Portal-Token`.
- Hạn **30 ngày** (`expires_on`). Không có refresh token: hết hạn → đăng nhập lại.
- **Mỗi request** server kiểm lại: token còn hạn và chưa bị thu hồi, SĐT trong tài khoản và trong hồ sơ
  nhân viên vẫn đúng số đã đăng nhập, trạng thái nhân viên vẫn cho phép. Sai bất kỳ điều nào →
  `SESSION_INVALID` (xem §4), token bị thu hồi luôn. Phòng Nhân sự đổi SĐT của tài khoản ⇒ mọi phiên của
  tài khoản đó kết thúc ngay (`reason: PHONE_CHANGED`).
- **Mở lại app** (màn 00, "lần mở sau"): có token → gọi `me()`. `ok` → vào thẳng màn phù hợp với
  `access.mode`. `SESSION_INVALID` / `SESSION_REQUIRED` → xoá token, về màn 01.

### 2.5 Chế độ chỉ xem (`READ_ONLY`)

`access.mode = "READ_ONLY"` ⇒ ẩn ở **mọi màn**: Tạo đơn nghỉ, Hủy đơn, Bổ sung giấy tờ, Gửi giải
trình, Chat với C&B (màn 10). Server **cũng chặn**: mọi endpoint ghi trả `READ_ONLY`. Ẩn nút là để
dễ dùng, chặn ở server mới là bảo mật — đừng dựa vào một phía.

### 2.6 Phát triển trên Zalo simulator — `dev_login`

Trên simulator, `getAccessToken()` / `getPhoneNumber()` không cho token thật nên `login` không dùng được.
Dùng **`dev_login(zalo_user_id)`** với ID lấy từ `getUserInfo()` / `getUserID()` của simulator.

🔴 `dev_login` **không xác minh với Zalo** — nó tin ID client gửi (giống app xe). Vì vậy có **hai lớp rào**,
cả hai do phía ERP bật/tắt, Mini App không tự vượt được:

1. Server phải bật cờ `employee_portal_dev_login` (`get_config().dev_login = true`). Tắt → `FEATURE_DISABLED`.
2. Tài khoản Zalo đó phải được phòng Nhân sự **tick "Allow Dev Login"** và **gán SĐT** của một nhân viên test.
   Chưa → `result: "DEV_NOT_ALLOWED"` (không có token). Lần gọi đầu tiên với một ID lạ sẽ **tự tạo tài
   khoản** để phía ERP tìm thấy ID đó mà tick + gán SĐT.

Phiên `dev_login` chỉ sống **1 ngày**, và kết thúc ngay khi phía ERP tắt cờ hoặc bỏ tick. Mọi endpoint
khác dùng y hệt như phiên thật.

Quy tắc phía Mini App:
- Chỉ hiện nút/luồng `dev_login` khi **build dev** (biến môi trường riêng) **và** `get_config().dev_login = true`.
  Bản build release **không có** code gọi `dev_login`.
- Không dùng `dev_login` như đường dự phòng khi `login` lỗi.

---

## 3. Quy ước chung

### 3.1 Phong bì

Mọi endpoint của module này trả trong `json.message`:

```json
{ "ok": true,  "data": { }, "server_time": "2026-10-12 08:15:00" }
```
```json
{ "ok": false,
  "error": { "code": "NO_APPROVER",
             "message": "Bạn chưa có người duyệt đơn trong hồ sơ. Vui lòng liên hệ phòng Nhân sự.",
             "field": null,
             "details": {} },
  "server_time": "2026-10-12 08:15:00" }
```

- **Lỗi nghiệp vụ = HTTP 200 + `ok: false`.** Rẽ nhánh theo `error.code`, **không** theo `message`.
- `error.message` là câu **tiếng Việt hiển thị được ngay** cho nhân viên.
- `error.field`: tên tham số gây lỗi (để tô đỏ ô nhập), hoặc `null`.
- Chỉ lỗi ngoài dự kiến mới là HTTP 500 (body của Frappe) → hiện câu chung "Có lỗi, vui lòng thử lại".
- HTTP 403 = sai method (lỗi lập trình phía client). HTTP 429 không dùng — giới hạn tần suất trả `RATE_LIMITED`.

### 3.2 Định dạng — cố định

| Kiểu | Định dạng | Ví dụ |
|---|---|---|
| Date | `YYYY-MM-DD` | `2026-09-29` |
| Datetime | `YYYY-MM-DD HH:MM:SS`, giờ Việt Nam | `2026-09-29 10:15:00` |
| Time | `HH:MM` (24h) | `07:52` |
| Kỳ công / kỳ lương | `YYYY-MM` = kỳ **26 tháng trước → 25 tháng này** | `"2026-08"` = 26/07 → 25/08/2026 |
| Tháng dương lịch (chỉ lịch chấm công) | `YYYY-MM` = ngày 01 → cuối tháng | `"2026-09"` |
| Tiền | **số nguyên** VND, không dấu phân cách | `12345678` |
| Ngày công / giờ | số thập phân, tối đa 2 chữ số | `24`, `12.5`, `0.5` |
| SĐT | luôn **đã che**: 2 số đầu + 3 số cuối | `"09•• ••• 123"` |

Không có `T`, không có `Z`, không có milliseconds. Key không có giá trị vẫn có mặt với `null`
(không bao giờ thiếu key). Danh sách rỗng là `[]`, không phải `null`.

Nhãn hiển thị (`label`, `*_label`) server trả sẵn tiếng Việt — Mini App không tự dịch mã.

### 3.3 Chống tạo trùng — `client_request_id`

Mọi endpoint **tạo mới** bắt buộc nhận `client_request_id`: một UUID v4 Mini App sinh **một lần cho
mỗi lần bấm "Gửi"**. Mạng chập chờn gửi lại cùng id → server trả lại **đúng bản ghi đã tạo**, không
tạo bản thứ hai. Sinh id mới khi người dùng sửa form rồi gửi lại.

### 3.4 Phân trang

Tham số `page` (từ 1, mặc định 1), `page_size` (mặc định 20, tối đa 100). Kết quả:

```json
{ "items": [], "page": 1, "page_size": 20, "has_more": false }
```

### 3.5 Phiên bản & bật/tắt tính năng

- `get_config().api_version` = `"1.0"`. Thêm field = không đổi version; đổi/bỏ field = tăng version
  và báo trước.
- `get_config().min_client_version`: client gửi `X-Portal-Client-Version` thấp hơn → mọi endpoint trả
  `CLIENT_TOO_OLD` → hiện màn "Vui lòng cập nhật".
- `get_config().features`: backend tắt một tính năng (vd. tạm khoá tạo đơn khi chốt công) mà không cần
  build lại Mini App. Tính năng tắt → ẩn lối vào; endpoint tương ứng trả `FEATURE_DISABLED`.
- Phòng Nhân sự bật/tắt từng mục trên ERP (Employee Portal Settings → tab *Mini App Features*). Cờ phụ thuộc
  tự tắt theo cờ cha: `attendance = false` ⇒ `overtime`, `explanation_create` cũng `false`;
  `leave_view = false` ⇒ `leave_create = false`.
- **Giai đoạn hiện tại (từ 23/10/2026):** chỉ `payslip` và `notifications` là `true`, mọi cờ khác `false`.
  Mini App phải dựng điều hướng + trang chủ **hoàn toàn theo `features`** (không hard-code) để khi ERP bật
  thêm mục thì hiện ra mà không cần build lại.

### 3.6 Tần suất gọi

- Không có push từ server. Làm mới `get_home` khi app trở lại foreground; **không** poll nhanh hơn 60 giây.
- `get_config` có thể cache 1 giờ.
- **Phiếu lương** (từ 1.5.0): mỗi phiếu chỉ tải **1 lần**, cache theo `(period, published_on)` — xem §10 "Cache".
  Sau khi phát hành, khoảng 1000 người mở app trong vài phút: mỗi lần tải thừa là tải thêm cho server.
- Lỗi mạng / `RATE_LIMITED` / HTTP 5xx: thử lại **giãn cách** (1 s, 2 s, 4 s… + ngẫu nhiên, tối đa 3 lần;
  `RATE_LIMITED` thì chờ đúng `details.retry_after`). Không tự thử lại dồn dập.
- `login` bị giới hạn **10 lần / 10 phút / tài khoản Zalo** → `RATE_LIMITED` (kèm `details.retry_after` giây).

---

## 4. Mã lỗi

Danh sách đóng. Backend thêm mã mới = ghi vào §13 và báo đội Mini App.

| `code` | Khi nào | Mini App làm gì |
|---|---|---|
| `SESSION_REQUIRED` | Thiếu header `X-Portal-Token` | Về màn 01 |
| `SESSION_INVALID` | Token sai/hết hạn/bị thu hồi hoặc hồ sơ thay đổi. `details.reason` ∈ `EXPIRED` · `REVOKED` · `PHONE_CHANGED` (phòng Nhân sự đổi SĐT tài khoản, hoặc SĐT hồ sơ đổi) · `STATUS_CHANGED`; với `STATUS_CHANGED` có thêm `details.result` (`EXPIRED`/`NOT_FOUND`/`DISABLED`) | Xoá token. `STATUS_CHANGED` → màn theo `details.result`; còn lại → màn 01 |
| `CLIENT_TOO_OLD` | `X-Portal-Client-Version` < `min_client_version` | Màn "cập nhật ứng dụng" |
| `FEATURE_DISABLED` | Tính năng đang tắt trong `features` | Ẩn tính năng, hiện `message` |
| `RATE_LIMITED` | Gọi quá nhanh. `details.retry_after` (giây) | Chờ rồi thử lại |
| `ZALO_TOKEN_INVALID` | Zalo báo token rỗng/hỏng (114, 115) hoặc access_token sai | Đăng nhập lại từ bước 1 |
| `ZALO_TOKEN_USED` | Token SĐT đã dùng / quá 2 phút (119) | Gọi lại `getPhoneNumber()`, gửi token **mới** |
| `ZALO_PERMISSION` | Người dùng chưa cấp quyền (−1401) | Màn 03 |
| `ZALO_SERVER_CONFIG` | Khoá Zalo trên server sai/thiếu (116, 117, 118) — **lỗi của server** | Hiện `message`, báo IT. Đừng debug Mini App |
| `ZALO_UNAVAILABLE` | Zalo không trả lời trong 10 giây | Cho thử lại |
| `READ_ONLY` | Endpoint ghi ở chế độ chỉ xem | Không nên xảy ra nếu đã ẩn nút |
| `NO_APPROVER` | Hồ sơ chưa có người duyệt đơn | Hiện `message` (liên hệ HR) |
| `APPROVER_NO_USER` | Người duyệt trong hồ sơ chưa có/bị khoá tài khoản ERP | Hiện `message` (liên hệ HR) |
| `LEAVE_TYPE_NOT_ALLOWED` | Loại nghỉ không được tạo từ Mini App | Lỗi client — chỉ dùng loại từ `get_leave_form` |
| `INSUFFICIENT_BALANCE` | Không đủ phép. `details.available` | Hiện `message` |
| `OVERLAP` | Trùng ngày với đơn/giải trình khác. `details.conflicts[]` = id + khoảng ngày | Hiện `message` |
| `VALIDATION` | Vi phạm quy định nghỉ phép/chấm công của công ty, hoặc tham số sai. `field` nếu xác định được | Hiện `message` nguyên văn |
| `NOT_FOUND` | Bản ghi không tồn tại **hoặc không phải của bạn** | Quay lại danh sách |
| `NOT_ALLOWED_STATE` | Thao tác không hợp trạng thái (vd. hủy đơn đã duyệt) | Làm mới bản ghi, hiện `message` |
| `FILE_TOO_LARGE` | Tệp vượt giới hạn. `details.max_size_mb` | Hiện `message` |
| `FILE_TYPE` | Loại tệp không nhận (kiểm theo nội dung thật, không theo đuôi) | Hiện `message` |
| `TOO_MANY_FILES` | Vượt số tệp/đơn. `details.max_files` | Hiện `message` |
| `LOGIN_AGAIN` | *(chỉ `link_employee_request`)* Tài khoản Zalo chưa từng `login`, hoặc SĐT của tài khoản **đã khớp** hồ sơ | Chạy lại `login` |
| `PENDING` | *(chỉ `link_employee_request`, **không còn trả từ 1.6.0**)* Đã có yêu cầu đang chờ phòng Nhân sự duyệt | Hiện trạng thái chờ |
| `EMPLOYEE_LINKED` | *(chỉ `link_employee_request`, từ 1.6.0)* Mã NV đang được tài khoản Zalo khác dùng | Hiện `message` |
| `REQUEST_LIMIT` | *(chỉ `link_employee_request`, từ 1.6.0)* Đã gửi đủ số lần trong ngày. `details.max_per_day` | Hiện `message`, không tự thử lại |
| `DISABLED` | *(chỉ `link_employee_request`)* Phòng Nhân sự đã khoá tài khoản Mini App | Màn 05, hiện `message` |

---

## 5. Object dùng chung

### 5.1 `Employee`

```json
{
  "employee_id": "TIQN-0231",
  "full_name": "Nguyễn Văn An",
  "initials": "NA",
  "designation": "Công nhân vận hành",
  "department": "Production",
  "section": "Sewing",
  "group": "Sewing 05",
  "date_of_joining": "2021-03-15",
  "relieving_date": null,
  "avatar_url": null
}
```
`avatar_url` = URL tuyệt đối tới ảnh nhân viên trên ERP (đã mã hoá URL, có `?v=` đổi khi ảnh được chụp lại), vd.
`https://erp.tiqn.com.vn:8888/files/employee_photos/TIQN-0148%20Nguy%E1%BB%85n%20Th%C3%A1i%20S%C6%A1n.png?v=1760000000`.
Tải trực tiếp, không cần header. **Đừng tự ghép tên tệp** (`{employee_id} {employee_name}.jpg`): đuôi có thể là
`.png`/`.jpg`. `null` khi nhân viên chưa có ảnh hoặc ảnh không tải công khai được → hiện `initials`; ảnh lỗi khi tải
cũng nên rơi về `initials`. Áp dụng cho `login`, `me`, `get_home`.
`designation` = **chức danh tiếng Việt** (lấy từ danh mục chức danh trên ERP, vd. "Tổ phó IT"); chức danh chưa
có bản tiếng Việt thì trả tên gốc. `group` = tổ/nhóm của nhân viên. `Person.designation` theo cùng quy tắc.
`relieving_date` là **ngày bắt đầu nghỉ việc** (ngày làm việc cuối = hôm trước).

### 5.2 `Access`

```json
{ "mode": "FULL", "read_only_until": null }
{ "mode": "READ_ONLY", "read_only_until": "2026-11-14" }
```

### 5.3 `Person` (người duyệt)

```json
{ "full_name": "Trần Thị Bình", "initials": "TB", "designation": "Trưởng phòng" }
```

### 5.4 `Document` (giấy tờ đính kèm)

```json
{
  "id": "a1b2c3d4e5",
  "file_name": "giay-kham.jpg",
  "mime_type": "image/jpeg",
  "size_bytes": 482113,
  "uploaded_at": "2026-08-25 08:41:10",
  "uploaded_by": "EMPLOYEE",
  "can_delete": true,
  "url": "https://erp.tiqn.com.vn:8888/api/method/customize_erpnext.api.employee_portal.download_document?sig=…",
  "url_expires_at": "2026-08-25 08:51:10"
}
```

- `url` là **link có chữ ký, hạn 10 phút**, dùng thẳng được trong `<img src>` hoặc `openWebview` — vì
  thẻ `<img>` không gửi được header `X-Portal-Token`. Hết hạn → gọi lại endpoint chi tiết để lấy link mới.
- `url` luôn **tuyệt đối**. Đừng ghép đường dẫn tương đối: trong webview Zalo nó resolve theo origin
  của Mini App và ra 404.
- `uploaded_by`: `EMPLOYEE` (nộp từ Mini App) · `HR` (phòng Nhân sự/người duyệt đính kèm trên ERP).

### 5.5 Enum trạng thái đơn (dùng cho đơn nghỉ và giải trình)

| Giá trị | Nhãn | Ghi chú |
|---|---|---|
| `PENDING` | Chờ duyệt | |
| `APPROVED` | Đã duyệt | |
| `REJECTED` | Từ chối | |
| `CANCELLED` | Đã hủy | do nhân viên hoặc HR hủy |

---

## 6. Cấu hình & phiên đăng nhập

### `get_config` — GET, không cần token

Gọi khi mở app, trước mọi màn (01, 03, 04, 05, 09 cần các số liên hệ).

```json
{ "ok": true, "data": {
  "api_version": "1.0",
  "min_client_version": "1.0.0",
  "company": { "name": "Công ty TNHH TIQN", "short_name": "TIQN",
               "logo_url": null },
  "contacts": { "hr_hotline": "0235 xxx xxxx", "company_phone": "0235 xxx xxxx" },
  "legal": { "privacy_policy_url": "https://erp.tiqn.com.vn:8888/portal-policy",
             "terms_url": "https://erp.tiqn.com.vn:8888/portal-terms",
             "version": "2026-10-12" },
  "oa": { "oa_id": "1234567890123456789", "chat_enabled": true },
  "uploads": { "max_files": 5, "max_size_mb": 5,
               "accept": ["image/jpeg", "image/png", "image/webp", "application/pdf"] },
  "read_only_days": 30,
  "dev_login": false,
  "features": {
    "payslip": true, "attendance": true, "overtime": true,
    "leave_view": true, "leave_create": true,
    "explanation_create": true, "notifications": true, "oa_invite": true
  }
}}
```

`legal.*_url` là trang công khai (nội dung do phòng Nhân sự soạn trên ERP) — mở bằng `openWebview`.
Đây cũng là URL khai báo khi nộp Mini App cho Zalo duyệt (§12).

### `login` — POST, không cần token

| Tham số | Bắt buộc | |
|---|---|---|
| `access_token` | ✅ | từ `getAccessToken()` |
| `phone_token` | | `token` từ `getPhoneNumber()`. Bỏ trống → dùng SĐT đã lưu trong tài khoản (§2.2) |

`ACTIVE` / `READ_ONLY`:
```json
{ "ok": true, "data": {
  "result": "ACTIVE",
  "token": "q7mJ0n9vZ4…(43 ký tự)",
  "expires_on": "2026-11-11 08:15:00",
  "zalo_user_id": "4295057266797901281",
  "masked_phone": "09•• ••• 123",
  "employee": { "employee_id": "TIQN-0231", "full_name": "Nguyễn Văn An", "initials": "NA",
                "designation": "Công nhân vận hành", "department": "Production",
                "section": "Sewing", "group": "Sewing 05", "date_of_joining": "2021-03-15",
                "relieving_date": null, "avatar_url": null },
  "access": { "mode": "FULL", "read_only_until": null },
  "oa": { "followed": false, "show_invite": true },
  "expired_on": null,
  "message": null
}}
```

`NO_PHONE` (màn 03):
```json
{ "ok": true, "data": { "result": "NO_PHONE", "token": null, "expires_on": null,
  "zalo_user_id": "4295057266797901281",
  "masked_phone": null, "employee": null, "access": null, "oa": null,
  "expired_on": null, "message": null }}
```

`NOT_FOUND` (màn 04):
```json
{ "ok": true, "data": { "result": "NOT_FOUND", "token": null, "expires_on": null,
  "zalo_user_id": "4295057266797901281",
  "masked_phone": "09•• ••• 123", "employee": null, "access": null, "oa": null,
  "expired_on": null, "message": null,
  "link_request": { "status": "PENDING", "employee_id": "TIQN-0148",
                    "requested_at": "2026-10-24 09:30:00", "created_at": "2026-10-24 09:30:00",
                    "reject_reason": null, "request_count": 1, "requests_today": 1,
                    "max_per_day": 2, "remaining_today": 1, "can_resend": true } }}
```
**`link_request`** (từ 1.4.0) — key có ở **mọi** kết quả `login`, chỉ khác `null` khi `NOT_FOUND`: yêu cầu liên kết hồ sơ
của tài khoản Zalo này (§6 `link_employee_request`). Mỗi tài khoản Zalo chỉ có **một** yêu cầu (từ 1.6.0).

| `link_request` | Màn 04 hiện |
|---|---|
| `null` (chưa gửi yêu cầu nào) | Form "Yêu cầu tạo tài khoản" + dòng nhỏ "Tối đa 2 lần/ngày" |
| `status = PENDING` | "Yêu cầu đã gửi — mã `employee_id`, đang chờ phòng Nhân sự duyệt". `can_resend = true` → thêm nút **"Sửa yêu cầu"** (mở form, điền sẵn mã NV) |
| `status = REJECTED` | "Yêu cầu bị từ chối" + `reject_reason` (nếu có) + form gửi lại khi `can_resend = true` |

Field (từ 1.6.0, trừ `status`, `employee_id`, `reject_reason`):

| Field | |
|---|---|
| `requested_at` | Lần gửi gần nhất (`created_at` = cùng giá trị, giữ cho bản app cũ — sẽ bỏ) |
| `request_count` | Tổng số lần đã gửi — hiện "Đã gửi N lần" |
| `requests_today`, `max_per_day`, `remaining_today` | Hôm nay đã gửi / tối đa (2) / còn lại — hiện "Hôm nay còn X lần" |
| `can_resend` | `remaining_today > 0`. `false` → ẩn form/nút gửi lại, hiện "Bạn đã gửi đủ 2 lần hôm nay, vui lòng thử lại vào ngày mai" |

Được duyệt → SĐT Zalo đã khớp hồ sơ → `login` trả `ACTIVE` luôn, không còn `NOT_FOUND`.

`EXPIRED` (màn 05):
```json
{ "ok": true, "data": { "result": "EXPIRED", "token": null, "expires_on": null,
  "zalo_user_id": "4295057266797901281",
  "masked_phone": "09•• ••• 123", "employee": null, "access": null, "oa": null,
  "expired_on": "2026-11-14",
  "message": null }}
```
`expired_on` = ngày hết hạn chỉ xem (màn 05 "[NGÀY HẾT HẠN]"); `null` nếu hồ sơ bị ngừng vì lý do
khác (không phải nghỉ việc).

`DISABLED`: như `EXPIRED`, `expired_on: null`, `message` = câu phòng Nhân sự soạn.

Lỗi có thể gặp: `ZALO_TOKEN_INVALID`, `ZALO_TOKEN_USED`, `ZALO_PERMISSION`, `ZALO_SERVER_CONFIG`,
`ZALO_UNAVAILABLE`, `RATE_LIMITED`, `CLIENT_TOO_OLD`.

### `link_employee_request` — POST, không cần token *(từ 1.4.0, màn 04)*

Người dùng `NOT_FOUND` tự khai **mã nhân viên + họ tên** để phòng Nhân sự liên kết. Phòng Nhân sự kiểm tra **đúng người**
(gọi lại SĐT Zalo…) rồi duyệt trên ERP: SĐT Zalo được ghi vào hồ sơ nhân viên → lần `login` sau vào thẳng.

| Tham số | Bắt buộc | |
|---|---|---|
| `access_token` | ✅ | từ `getAccessToken()` — server tự hỏi Zalo "ai đang gửi" |
| `employee_id` | ✅ | `TIQN-` + 4 số (không phân biệt hoa thường) |
| `full_name` | ✅ | 2–140 ký tự |

🔴 **Không gửi `zalo_user_id`** — nếu gửi, server bỏ qua. Người gửi luôn là người Zalo xác nhận qua `access_token`.
SĐT được duyệt là SĐT Zalo đã xác nhận ở lần `login` trước (vì vậy phải `login` có `phone_token` trước).

- **Một yêu cầu / tài khoản Zalo** (từ 1.6.0): gửi lại thì nội dung mới **ghi đè** nội dung cũ và yêu cầu quay về `PENDING`
  — được gửi lại cả khi đang chờ (sửa mã/họ tên gõ nhầm) lẫn sau khi bị từ chối.
- Tối đa **2 lần/ngày** (ngày lịch giờ Việt Nam). Chỉ lần gửi **thành công** mới tính; lần bị lỗi (`VALIDATION`,
  `NOT_FOUND`, `EMPLOYEE_LINKED`…) không tính.
- **Mã NV và họ tên phải khớp hồ sơ** (từ 1.6.0; không phân biệt dấu, hoa/thường, khoảng trắng thừa). Không khớp →
  `NOT_FOUND` ngay, hiện lỗi trên form, không tạo yêu cầu.
- Mã NV đang được một tài khoản Zalo khác dùng (chưa bị khoá) → `EMPLOYEE_LINKED`.

```json
{ "ok": true, "data": {
  "status": "PENDING",
  "message": "Yêu cầu đã được gửi. Phòng Nhân sự sẽ kiểm tra.",
  "link_request": { "status": "PENDING", "employee_id": "TIQN-0148",
                    "requested_at": "2026-10-24 09:30:00", "created_at": "2026-10-24 09:30:00",
                    "reject_reason": null, "request_count": 1, "requests_today": 1,
                    "max_per_day": 2, "remaining_today": 1, "can_resend": true }
}}
```
Sai mã hay sai tên đều nhận **cùng một** `NOT_FOUND` "Mã nhân viên hoặc họ tên không đúng…" — server không cho biết sai
ô nào và không bao giờ trả họ tên trong hồ sơ (chống dò mã/tên). Mini App hiện `message` ở đầu form, không gắn vào ô nào.

| Lỗi | Khi nào |
|---|---|
| `VALIDATION` | `employee_id` sai định dạng (`field: employee_id`), `full_name` quá ngắn (`field: full_name`), hoặc tài khoản chưa có SĐT (cho phép đọc SĐT rồi `login` lại) |
| `NOT_FOUND` | Mã NV không có, hồ sơ không còn được dùng Mini App, **hoặc họ tên không khớp mã NV** (từ 1.6.0). `field: null` |
| `EMPLOYEE_LINKED` | *(từ 1.6.0)* Mã NV này đang được một tài khoản Zalo khác dùng (`field: employee_id`). Hiện `message` ("…vui lòng liên hệ phòng Nhân sự") |
| `REQUEST_LIMIT` | *(từ 1.6.0)* Đã gửi đủ **2 lần hôm nay**. `details: { max_per_day, requests_today }`. Hiện `message`, ẩn nút gửi; **không** tự thử lại |
| `LOGIN_AGAIN` | Chưa từng `login`, hoặc SĐT đã khớp hồ sơ → chạy lại `login` |
| `DISABLED` | Phòng Nhân sự khoá tài khoản |
| `RATE_LIMITED` | Thử quá **10 lần / ngày** / tài khoản Zalo, tính cả lần bị lỗi (chống dò mã NV) |
| `ZALO_*` | Như `login` |

`PENDING` không còn trả từ 1.6.0 (đang chờ vẫn gửi lại được — ghi đè).

### `dev_login` — POST, không cần token *(chỉ simulator — đọc §2.6)*

| Tham số | Bắt buộc | |
|---|---|---|
| `zalo_user_id` | ✅ | từ `getUserInfo()` / `getUserID()` trên simulator |

Trả **cùng hình dạng** với `login`. `result` có thể là `ACTIVE`, `READ_ONLY`, `NOT_FOUND`, `EXPIRED`,
`DISABLED` như `login`, hoặc:
```json
{ "ok": true, "data": { "result": "DEV_NOT_ALLOWED", "token": null, "expires_on": null,
  "zalo_user_id": "5432109876543210000",
  "masked_phone": null, "employee": null, "access": null, "oa": null, "expired_on": null,
  "message": "Tài khoản Zalo này chưa được phép đăng nhập dev. Nhờ phòng Nhân sự tick \"Allow Dev Login\" cho tài khoản." }}
```
Lỗi: `FEATURE_DISABLED` (server tắt cờ), `VALIDATION` (thiếu `zalo_user_id`), `RATE_LIMITED`.

### `me` — GET

Dùng khi mở lại app và ở màn 09 (Tài khoản).

```json
{ "ok": true, "data": {
  "employee": { "employee_id": "TIQN-0231", "full_name": "Nguyễn Văn An", "…": "…" },
  "access": { "mode": "FULL", "read_only_until": null },
  "zalo_user_id": "4295057266797901281",
  "login_method": "ZALO_PHONE",
  "masked_phone": "09•• ••• 123",
  "session_expires_on": "2026-11-11 08:15:00",
  "oa": { "followed": false, "show_invite": false },
  "chat": { "type": "user", "id": "7664780689128284452", "name": "Chị Lan - Tiền lương" }
}}
```

`chat` (từ 1.2.0): đích của nút "Chat với C&B" — xem [Chat với C&B](#chat-với-cb-màn-19-20). Cũng có trong `get_home`.

`login_method`: `ZALO_PHONE` (SĐT do Zalo xác nhận lúc đăng nhập) · `STORED_PHONE` (SĐT lấy từ tài khoản) ·
`DEV` (đăng nhập dev). Màn 09 có thể dùng để gợi ý "Cập nhật số điện thoại" khi khác `ZALO_PHONE`.

### `set_id_by_oa` — POST *(từ 1.2.0)*

Gọi **sau mỗi lần đăng nhập thành công**: `getUserInfo()` → gửi `idByOA` (nếu khác rỗng). Server lưu vào tài
khoản Zalo **của chính người gọi**; phòng Nhân sự dùng giá trị này của nhân viên tiền lương để cấu hình nút chat.

| Tham số | |
|---|---|
| `id_by_oa` | `getUserInfo().idByOA` — chỉ chữ số. **Không** gửi `id` (app-scoped) vào đây |

```json
{ "ok": true, "data": { "saved": true } }
```
`idByOA` rỗng (Mini App chưa được OA xác thực, người dùng chưa quan tâm OA) → không cần gọi. Giá trị không
phải số → `VALIDATION`.

### `logout` — POST

Thu hồi token hiện tại. Luôn trả `{ "ok": true, "data": null }`, kể cả token đã hết hạn.

### `set_oa_follow` — POST (màn 07, 09)

| Tham số | Bắt buộc | |
|---|---|---|
| `action` | ✅ | `FOLLOWED` (sau khi `followOA()` thành công) · `DISMISSED` (bấm "Để sau" ở màn 07) · `UNFOLLOWED` |

```json
{ "ok": true, "data": { "followed": true, "show_invite": false } }
```

`show_invite` = chưa quan tâm **và** chưa từng bấm "Để sau". Màn 07 chỉ hiện khi `show_invite: true`.
Server không kiểm chứng được với Zalo là đã quan tâm thật — chỉ dùng để ẩn/hiện lời mời.

---

## 7. Trang chủ & thông báo

### `get_home` — GET (màn 06, 10)

```json
{ "ok": true, "data": {
  "employee": { "employee_id": "TIQN-0231", "full_name": "Nguyễn Văn An", "initials": "NA",
                "designation": "Công nhân vận hành", "department": "Production",
                "section": "Sewing", "group": "Sewing 05", "date_of_joining": "2021-03-15",
                "relieving_date": null, "avatar_url": null },
  "access": { "mode": "FULL", "read_only_until": null },
  "today": {
    "date": "2026-09-29",
    "weekday_label": "Thứ Ba",
    "state": "WORKING",
    "state_label": "Đang làm việc",
    "check_in": "07:52",
    "check_out": null,
    "shift": { "label": "Ca hành chính", "start": "08:00", "end": "17:00" },
    "updated_at": "2026-09-29 10:15:00"
  },
  "annual_leave": { "year": 2026, "remaining": 9, "available": 7 },
  "attendance": {
    "period": "2026-09", "period_label": "Công tháng 09",
    "payable_days": 22, "standard_days": 25,
    "source": "ERP", "provisional": true
  },
  "overtime": { "period": "2026-09", "hours": 12.5, "source": "ERP" },
  "latest_payslip": { "period": "2026-08", "label": "Phiếu lương 08/2026", "published_on": "2026-09-05",
                      "published_at": "2026-09-05 08:00:00" },
  "notifications": {
    "unread": 2,
    "latest": { "id": "PN-2026-00031", "type": "PAYSLIP_PUBLISHED",
                "title": "Phiếu lương tháng 08/2026", "body": "đã phát hành",
                "created_at": "2026-09-05 08:00:00", "is_read": false,
                "target": { "screen": "PAYSLIP", "id": "2026-08" } }
  },
  "oa": { "followed": false, "show_invite": false },
  "chat": { "type": "user", "id": "7664780689128284452", "name": "Chị Lan - Tiền lương" }
}}
```

| Field | Quy tắc |
|---|---|
| `today.state` | `NOT_CHECKED_IN` (Chưa chấm công vào) · `WORKING` (Đang làm việc) · `DONE` (Đã về) · `ON_LEAVE` (Nghỉ phép) · `HOLIDAY` (Ngày lễ) · `DAY_OFF` (Ngày nghỉ) |
| `today.check_in/out` | giờ quẹt thẻ sớm nhất / muộn nhất hôm nay; `null` nếu chưa có |
| `today.shift` | ca theo phân ca của nhân viên; `null` nếu ngày nghỉ |
| `annual_leave` | cùng công thức với màn 11 và với báo cáo số dư phép trên ERP |
| `attendance` | cộng từ **bảng công** của kỳ 26 → 25 (cùng số với `get_attendance_summary`). `source` luôn `ERP` (từ 1.1.4 không còn `PAYSLIP`); `provisional` như `get_attendance_summary` |
| `overtime.hours` | tổng giờ tăng ca **thực tính** trong bảng công của kỳ; `source` luôn `ERP` |
| `latest_payslip` | phiếu đã phát hành gần nhất; `null` nếu chưa có. `published_at` (từ 1.5.0) = khoá cache của phiếu, bằng `published_on` trong `get_payslip_periods` |
| `chat` | đích nút "Chat với C&B" — như `me.chat` (§10 Chat với C&B) |
| khối bị tắt | `today`/`attendance` (tắt `attendance`), `overtime` (tắt `overtime`), `annual_leave` (tắt `leave_view`), `latest_payslip` (tắt `payslip`), `notifications` (tắt `notifications`) → giá trị `null`, key vẫn có |

### `get_notifications` — GET (màn 08)

| Tham số | |
|---|---|
| `page`, `page_size` | §3.4 |
| `unread_only` | `0`/`1`, mặc định `0` |

```json
{ "ok": true, "data": {
  "unread": 2,
  "items": [
    { "id": "PN-2026-00031", "type": "PAYSLIP_PUBLISHED",
      "title": "Phiếu lương tháng 08/2026", "body": "đã phát hành",
      "created_at": "2026-09-05 08:00:00", "is_read": false,
      "target": { "screen": "PAYSLIP", "id": "2026-08" } },
    { "id": "PN-2026-00040", "type": "EXPLANATION_APPROVED",
      "title": "Giải trình ngày 08/09", "body": "đã được duyệt",
      "created_at": "2026-09-10 16:20:00", "is_read": false,
      "target": { "screen": "EXPLANATION", "id": "HR-ARQ-26-09-00012" } },
    { "id": "PN-2026-00022", "type": "LEAVE_REJECTED",
      "title": "Đơn nghỉ không lương 05/07", "body": "bị từ chối",
      "created_at": "2026-07-03 14:12:00", "is_read": true,
      "target": { "screen": "LEAVE", "id": "LA-2026-07-00981" } }
  ],
  "page": 1, "page_size": 20, "has_more": false
}}
```

`title` hiển thị đậm, `body` thường (như thiết kế màn 08). Nhóm "Chưa đọc" / "Trước đó" theo `is_read`.

**Từ 1.2.0 — mỗi thông báo là MỘT bản ghi, không lưu trạng thái đọc từng người:**
- `PAYSLIP_PUBLISHED` = **một** thông báo chung cho cả công ty mỗi kỳ (trước là mỗi người một bản) — chỉ hiện với
  nhân viên có phiếu đã phát hành của kỳ đó. Thông báo khác do phòng Nhân sự gửi cho cả công ty hoặc cho **một
  nhóm người chọn sẵn**.
- `is_read` = thông báo được tạo **trước** lần cuối người dùng gọi `mark_notifications_read` (server chỉ nhớ một
  mốc thời gian cho mỗi tài khoản). Vì vậy: khi người dùng mở màn 08, gọi `mark_notifications_read(all=1)` để
  badge `unread` về 0. Gửi `ids` thì mốc lên tới thông báo mới nhất trong `ids` — các thông báo cũ hơn cũng thành đã đọc.
- Payload giống hệt bản cũ. `id` của một thông báo **giống nhau** giữa mọi người nhận — đừng dùng làm khoá lưu
  cục bộ mà không kèm `employee_id`.

| `type` | `target.screen` | `target.id` |
|---|---|---|
| `PAYSLIP_PUBLISHED` | `PAYSLIP` | kỳ `YYYY-MM` |
| `LEAVE_APPROVED` · `LEAVE_REJECTED` · `LEAVE_CANCELLED` · `LEAVE_NEEDS_DOCUMENTS` | `LEAVE` | mã đơn nghỉ |
| `EXPLANATION_APPROVED` · `EXPLANATION_REJECTED` | `EXPLANATION` | mã giải trình |
| `OVERTIME_APPROVED` | `OVERTIME` | kỳ `YYYY-MM` |
| `GENERAL` | `NONE` | `null` (thông báo chung của HR) |

`type` lạ (bản sau thêm) → hiển thị `title`/`body`, không điều hướng.

### `mark_notifications_read` — POST

| Tham số | |
|---|---|
| `ids` | danh sách id (JSON array hoặc chuỗi phân cách dấu phẩy); bỏ trống + `all=1` = đánh dấu tất cả |
| `all` | `0`/`1` |

```json
{ "ok": true, "data": { "unread": 0 } }
```

---

## 8. Nghỉ phép

Đơn nghỉ tạo từ Mini App vào ERP ở trạng thái **Chờ duyệt**. **Trưởng bộ phận** (người duyệt ghi
trong hồ sơ nhân viên) duyệt trên ERP. Đơn chờ duyệt **không** ảnh hưởng ngày công cho tới khi được
duyệt.

**Loại nghỉ nhân viên tự tạo được** (danh sách thật luôn lấy từ `get_leave_form`, đừng viết cứng):

| `leave_type` (khoá gửi lên server) | `label` | `abbr` | Kiểm số dư | Giấy tờ |
|---|---|---|---|---|
| `Phép năm/ Annual leave` | Phép năm | P | ✅ | — |
| `Nghỉ hưởng BHXH/ Social insurance leave - Ốm đau` | Nghỉ ốm (BHXH) | O | — | ✅ |
| `Nghỉ hưởng BHXH/ Social insurance leave - Con ốm` | Con ốm (BHXH) | CO | — | ✅ |
| `Nghỉ không lương/ Unpaid leave` | Nghỉ không lương | KL | — | — |
| `Nghỉ hưởng lương/ Paid leave - Hỉ sự` | Hỉ sự | HS | — | — |
| `Nghỉ hưởng lương/ Paid leave - Ma chay` | Ma chay | MC | — | — |

Thai sản, dưỡng sức, nghỉ hưởng lương khác, **nghỉ bù**: phòng Nhân sự nhập, nhân viên chỉ **xem**.
**Nửa ngày**: chỉ có "Cả ngày / Nửa ngày" — **không** có sáng/chiều (khác thiết kế màn 12, 12b).

### `get_leave_balances` — GET (màn 11)

| Tham số | |
|---|---|
| `year` | mặc định năm hiện tại |

```json
{ "ok": true, "data": {
  "year": 2026,
  "annual": { "leave_type": "Phép năm/ Annual leave", "label": "Phép năm",
              "allocated": 12, "used": 3, "pending": 2, "remaining": 9, "available": 7 },
  "others": [
    { "leave_type": "Nghỉ hưởng BHXH/ Social insurance leave - Ốm đau", "label": "Nghỉ ốm (BHXH)",
      "balance": null, "note": "Theo chứng từ" }
  ]
}}
```

`remaining = allocated − used`; `available = remaining − pending`. `balance: null` = không quản lý bằng
số dư (hiện `note`).

**Không có ô "Nghỉ bù"** như thiết kế màn 11: nghỉ bù do phòng Nhân sự nhập, ERP không quản lý số dư
nghỉ bù. Bỏ ô đó khỏi màn 11.

### `get_leave_applications` — GET (màn 11 "Đơn của tôi")

| Tham số | |
|---|---|
| `year` | mặc định năm hiện tại |
| `status` | bỏ trống = tất cả; `PENDING` · `APPROVED` · `REJECTED` · `CANCELLED` |
| `page`, `page_size` | §3.4 |

```json
{ "ok": true, "data": {
  "years_available": [2026, 2025],
  "counts": { "ALL": 4, "PENDING": 2, "APPROVED": 2, "REJECTED": 0, "CANCELLED": 0 },
  "items": [
    { "id": "LA-2026-10-00418", "leave_type": "Phép năm/ Annual leave", "leave_type_label": "Phép năm",
      "from_date": "2026-10-02", "to_date": "2026-10-03", "half_day": false, "half_day_date": null,
      "days": 2, "status": "PENDING", "status_label": "Chờ duyệt",
      "needs_documents": false, "document_count": 0,
      "source": "MINI_APP", "created_at": "2026-09-29 09:14:00" },
    { "id": "LA-2026-08-00371", "leave_type": "Nghỉ hưởng BHXH/ Social insurance leave - Ốm đau",
      "leave_type_label": "Nghỉ ốm (BHXH)",
      "from_date": "2026-08-25", "to_date": "2026-08-25", "half_day": false, "half_day_date": null,
      "days": 1, "status": "PENDING", "status_label": "Chờ duyệt",
      "needs_documents": true, "document_count": 2,
      "source": "MINI_APP", "created_at": "2026-08-25 08:40:00" }
  ],
  "page": 1, "page_size": 20, "has_more": false
}}
```

Danh sách gồm **cả đơn phòng Nhân sự nhập** cho nhân viên (`source: "DESK"`), không chỉ đơn tạo từ app.
`needs_documents: true` → nhãn "Cần bổ sung giấy tờ".

### `get_leave_form` — GET (màn 12, 12b)

Gọi khi mở màn tạo đơn. **Luôn `ok: true`**; nếu không được tạo đơn thì `blocked` khác `null` → hiện
`blocked.message` thay cho form.

```json
{ "ok": true, "data": {
  "blocked": null,
  "approver": { "full_name": "Trần Thị Bình", "initials": "TB", "designation": "Trưởng phòng" },
  "leave_types": [
    { "leave_type": "Phép năm/ Annual leave", "label": "Phép năm", "abbr": "P",
      "uses_balance": true, "available": 7, "allows_documents": false },
    { "leave_type": "Nghỉ hưởng BHXH/ Social insurance leave - Ốm đau", "label": "Nghỉ ốm (BHXH)",
      "abbr": "O", "uses_balance": false, "available": null, "allows_documents": true }
  ],
  "half_day_allowed": true,
  "documents": { "max_files": 5, "max_size_mb": 5,
                 "accept": ["image/jpeg", "image/png", "image/webp", "application/pdf"] }
}}
```

Bị chặn:
```json
{ "ok": true, "data": {
  "blocked": { "code": "NO_APPROVER",
               "message": "Bạn chưa có người duyệt đơn trong hồ sơ. Vui lòng liên hệ phòng Nhân sự." },
  "approver": null, "leave_types": [], "half_day_allowed": false, "documents": null
}}
```
`blocked.code` ∈ `NO_APPROVER` · `APPROVER_NO_USER` · `READ_ONLY` · `FEATURE_DISABLED`.

### `preview_leave` — GET (màn 12, khi đổi ngày/loại/thời lượng)

| Tham số | Bắt buộc | |
|---|---|---|
| `leave_type` | ✅ | |
| `from_date`, `to_date` | ✅ | |
| `half_day` | | `0`/`1` |
| `half_day_date` | khi `half_day=1` và nhiều ngày | ngày nghỉ nửa; một ngày thì bỏ trống |

```json
{ "ok": true, "data": {
  "days": 2,
  "excluded_dates": [
    { "date": "2026-10-04", "reason": "WEEKLY_OFF", "label": "Chủ nhật" }
  ],
  "available_before": 9,
  "available_after": 7,
  "note": "Đã trừ Chủ nhật và ngày lễ theo lịch làm việc của bạn."
}}
```

- Số ngày tính **bằng đúng hàm mà ERP dùng khi lưu đơn** — preview khớp kết quả thật.
- Vi phạm quy định (vd. quá ngày, không đủ phép) → `ok: false` với `INSUFFICIENT_BALANCE` /
  `OVERLAP` / `VALIDATION` **ngay ở preview**, để báo trước khi bấm Gửi.
- `available_before/after` = `null` với loại không dùng số dư.

### `create_leave_application` — POST (màn 12, 12b)

| Tham số | Bắt buộc | |
|---|---|---|
| `leave_type` | ✅ | từ `get_leave_form` |
| `from_date`, `to_date` | ✅ | |
| `half_day`, `half_day_date` | | như `preview_leave` |
| `reason` | ✅ | ≤ 500 ký tự |
| `client_request_id` | ✅ | §3.3 |

Trả về **`LeaveApplicationDetail`** (như `get_leave_application`).

**Đơn ốm có giấy tờ (12b)** — 2 bước:
1. `create_leave_application` → nhận `id`.
2. Mỗi tệp gọi `upload_leave_document(leave_application=id, …)`.

Upload lỗi giữa chừng thì đơn **vẫn đã gửi**; hiện "Đơn đã gửi, N tệp chưa tải lên" và cho tải lại ở
màn 13b. Giấy tờ là tuỳ chọn, bổ sung sau được.

Lỗi: `READ_ONLY`, `NO_APPROVER`, `APPROVER_NO_USER`, `LEAVE_TYPE_NOT_ALLOWED`, `INSUFFICIENT_BALANCE`,
`OVERLAP`, `VALIDATION`, `FEATURE_DISABLED`.

### `get_leave_application` — GET (màn 13, 13b)

| Tham số | Bắt buộc |
|---|---|
| `id` | ✅ |

```json
{ "ok": true, "data": {
  "id": "LA-2026-08-00371",
  "leave_type": "Nghỉ hưởng BHXH/ Social insurance leave - Ốm đau",
  "leave_type_label": "Nghỉ ốm (BHXH)",
  "from_date": "2026-08-25", "to_date": "2026-08-25",
  "half_day": false, "half_day_date": null, "days": 1,
  "reason": "Sốt cao, đi khám",
  "status": "PENDING", "status_label": "Đang chờ duyệt",
  "source": "MINI_APP",
  "created_at": "2026-08-25 08:40:00",
  "approver": { "full_name": "Trần Thị Bình", "initials": "TB", "designation": "Trưởng phòng" },
  "needs_documents": true,
  "documents_request_note": "Bổ sung giấy ra viện khi có nhé.",
  "approver_note": null,
  "timeline": [
    { "event": "SUBMITTED", "label": "Đã gửi đơn", "at": "2026-08-25 08:40:00", "by": null, "note": null, "done": true },
    { "event": "DOCUMENTS_REQUESTED", "label": "Yêu cầu bổ sung giấy tờ", "at": "2026-08-25 10:02:00",
      "by": "Trần Thị Bình", "note": "Bổ sung giấy ra viện khi có nhé.", "done": true },
    { "event": "UNDER_REVIEW", "label": "Trưởng phòng đang xem xét", "at": null, "by": "Trần Thị Bình", "note": null, "done": false }
  ],
  "documents": [
    { "id": "a1b2c3d4e5", "file_name": "giay-kham.jpg", "mime_type": "image/jpeg", "size_bytes": 482113,
      "uploaded_at": "2026-08-25 08:41:10", "uploaded_by": "EMPLOYEE", "can_delete": true,
      "url": "https://erp.tiqn.com.vn:8888/api/method/customize_erpnext.api.employee_portal.download_document?sig=…",
      "url_expires_at": "2026-08-25 08:51:10" }
  ],
  "allows_documents": true,
  "can_cancel": true,
  "can_add_documents": true
}}
```

| Field | Quy tắc |
|---|---|
| `timeline[].event` | `SUBMITTED` · `DOCUMENTS_REQUESTED` · `UNDER_REVIEW` · `APPROVED` · `REJECTED` · `CANCELLED` |
| `timeline[].done` | `false` = bước đang chờ (vẽ mờ) |
| `can_cancel` | chỉ `PENDING` và không ở chế độ chỉ xem |
| `can_add_documents` | loại nghỉ có giấy tờ, trạng thái `PENDING` **hoặc** `APPROVED` (bổ sung được sau khi duyệt, vd. giấy ra viện), chưa đủ số tệp, không ở chế độ chỉ xem |
| `documents[].can_delete` | tệp do chính nhân viên nộp **và** đơn còn `PENDING` |
| `approver_note` | lý do từ chối / ghi chú khi duyệt |
| `approver` | **có thể `null`**: đơn do phòng Nhân sự nhập tay trên ERP không có người duyệt (toàn bộ đơn hiện có, 7.311 đơn năm 2026). Khi `null`: ẩn dòng "Người duyệt", trong `timeline` bước duyệt có `by` là người đã xử lý (thường là tài khoản HR) |

Đơn của người khác hoặc không tồn tại → `NOT_FOUND`.

### `cancel_leave_application` — POST (màn 13)

| Tham số | Bắt buộc |
|---|---|
| `id` | ✅ |

Trả `LeaveApplicationDetail` với `status: "CANCELLED"`. Đơn không còn `PENDING` → `NOT_ALLOWED_STATE`.

### `upload_leave_document` — POST multipart (màn 12b, 13b)

| Field | Bắt buộc | |
|---|---|---|
| `leave_application` | ✅ | mã đơn |
| `client_request_id` | ✅ | một id cho mỗi tệp |
| `file` | ✅ | nội dung tệp |

```json
{ "ok": true, "data": {
  "document": { "id": "f6g7h8i9j0", "file_name": "giay-ra-vien.jpg", "…": "…" },
  "document_count": 3
}}
```

Lỗi: `FILE_TOO_LARGE`, `FILE_TYPE`, `TOO_MANY_FILES`, `NOT_ALLOWED_STATE` (đơn bị hủy/từ chối),
`NOT_FOUND`, `READ_ONLY`. Tệp lưu **riêng tư** trên ERP, chỉ nhân viên đó, người duyệt và phòng Nhân
sự xem được.

### `delete_leave_document` — POST (màn 13b)

| Tham số | Bắt buộc |
|---|---|
| `document_id` | ✅ |

```json
{ "ok": true, "data": { "document_count": 2 } }
```
`can_delete: false` → `NOT_ALLOWED_STATE`.

### `download_document` — GET (không dùng trực tiếp)

Đích của `Document.url`. Không gửi token — chữ ký trong `sig` thay cho token, hạn 10 phút. Trả nội
dung tệp với `Content-Type` đúng. Hết hạn / sai chữ ký → HTTP 403.

---

## 9. Chấm công, giải trình, tăng ca

### `get_attendance_calendar` — GET (màn 14 "Chấm công & tăng ca")

| Tham số | |
|---|---|
| `month` | `YYYY-MM` **tháng dương lịch**, mặc định tháng hiện tại |

```json
{ "ok": true, "data": {
  "month": "2026-09",
  "summary": { "present": 22, "leave": 1, "absent": 0, "late_early": 2, "holiday": 1 },
  "overtime_summary": { "actual_hours": 12.5, "approved_hours": 10 },
  "today": { "date": "2026-09-29", "check_in": "07:52", "check_out": null },
  "days": [
    { "date": "2026-09-01", "display": "HOLIDAY", "label": "Quốc khánh",
      "leave_abbr": null, "late": false, "early": false, "has_explanation": false, "overtime_hours": null },
    { "date": "2026-09-08", "display": "LATE_EARLY", "label": "Đi muộn 12 phút",
      "leave_abbr": null, "late": true, "early": false, "has_explanation": true, "overtime_hours": 1.5 },
    { "date": "2026-09-11", "display": "LEAVE", "label": "Phép năm",
      "leave_abbr": "P", "late": false, "early": false, "has_explanation": false, "overtime_hours": null },
    { "date": "2026-09-30", "display": "FUTURE", "label": null,
      "leave_abbr": null, "late": false, "early": false, "has_explanation": false, "overtime_hours": null }
  ]
}}
```

- `overtime_summary` (tháng **dương lịch** của `month`, lấy từ bảng công): `actual_hours` = tổng giờ tăng ca **thực
  tính**, `approved_hours` = tổng giờ tăng ca **được duyệt**. ⚠ Khác `get_attendance_summary.overtime.hours`, vốn
  tính theo **kỳ lương 26 → 25** và lấy từ phiếu lương khi kỳ đã phát hành.
- `days[].overtime_hours` = giờ tăng ca thực tính của ngày; `null` khi không có tăng ca.
- `get_config().features.overtime = false` ⇒ `overtime_summary: null`, mọi `overtime_hours: null`.

`days` có **đủ mọi ngày** trong tháng. `display` do server quyết định — Mini App chỉ tô màu theo bảng:

| `display` | Chú thích lịch |
|---|---|
| `PRESENT` | Có mặt |
| `LATE_EARLY` | Đi muộn / về sớm |
| `LEAVE` | Nghỉ phép (cả ngày) |
| `HALF_LEAVE` | Nghỉ nửa ngày (có `leave_abbr`) |
| `ABSENT` | Vắng |
| `HOLIDAY` | Ngày lễ |
| `DAY_OFF` | Ngày nghỉ (Chủ nhật…) |
| `NO_DATA` | Ngày làm việc đã qua nhưng chưa có công (đang tính / thiếu dữ liệu) |
| `TODAY` | Hôm nay, chưa có công |
| `FUTURE` | Chưa tới |

Đã đi muộn mà có đơn nghỉ được duyệt cùng ngày thì **không** tính là đi muộn (theo quy định công ty).

### `get_attendance_day` — GET (màn 15)

| Tham số | Bắt buộc |
|---|---|
| `date` | ✅ |

```json
{ "ok": true, "data": {
  "date": "2026-09-08",
  "weekday_label": "Thứ Ba",
  "display": "LATE_EARLY",
  "status_label": "Có mặt",
  "late_minutes": 12,
  "early_minutes": 0,
  "check_in": "08:12",
  "check_out": "17:35",
  "shift": { "label": "Hành chính", "start": "08:00", "end": "17:00" },
  "working_hours": 8.38,
  "working_hours_label": "8 giờ 23",
  "overtime_hours": 1.5,
  "approved_overtime_hours": 1.5,
  "overtime_registrations": [
    { "id": "OTR-26-09-08-0003", "date": "2026-09-08", "weekday_label": "T3", "begin": "17:00", "end": "18:30",
      "hours": 1.5, "reason": "Hoàn thành đơn hàng", "status": "REGISTERED", "status_label": "Đã đăng ký" }
  ],
  "leave": null,
  "punches": [
    { "time": "08:12", "direction": "IN",  "device_name": "Machine 7" },
    { "time": "12:01", "direction": "OUT", "device_name": "Machine 3" },
    { "time": "12:58", "direction": "IN",  "device_name": "Machine 3" },
    { "time": "17:35", "direction": "OUT", "device_name": "Machine 7" }
  ],
  "explanations": [
    { "id": "HR-ARQ-26-09-00012", "reason_label": "Đi công tác / làm việc bên ngoài",
      "status": "APPROVED", "status_label": "Đã duyệt" }
  ],
  "can_explain": true,
  "explain_blocked": null
}}
```

| Field | Quy tắc |
|---|---|
| `leave` | `{ "leave_type_label": "Phép năm", "abbr": "P", "half_day": false, "application_id": "LA-…" }` hoặc `null` |
| `overtime_hours` | giờ tăng ca **thực tính** của ngày (0 khi không có) |
| `approved_overtime_hours` | giờ tăng ca **được duyệt** của ngày; `null` khi ngày chưa có bảng công hoặc tính năng tăng ca tắt |
| `overtime_registrations` | các dòng **phiếu đăng ký tăng ca** của ngày, cùng dạng `items` của `get_overtime` (trạng thái xem bảng ở đó); `[]` khi tính năng tăng ca tắt |
| `punches[].direction` | `IN` / `OUT` / `null`. Máy chấm công không ghi chiều, server **suy luận** xen kẽ vào–ra theo thứ tự; lần quẹt bổ sung tay có `"manual": true` |
| `punches[].device_name` | tên máy chấm công như trên hệ thống (`Machine 1`…`Machine 7` — giữ nguyên, đã chốt); `null` với lần bổ sung tay |
| `can_explain` | ngày đã qua, không ở chế độ chỉ xem, có người duyệt, chưa có giải trình `PENDING` cho ngày này |
| `explain_blocked` | `null` hoặc `{ code, message }` (`NO_APPROVER` · `APPROVER_NO_USER` · `READ_ONLY` · `PENDING_EXISTS` · `FUTURE_DATE`) — hiện thay nút "Gửi giải trình" |

### `get_explanation_form` — GET (màn 16)

| Tham số | Bắt buộc |
|---|---|
| `date` | ✅ ngày mở từ màn 15 |

```json
{ "ok": true, "data": {
  "blocked": null,
  "date": "2026-09-08",
  "context_label": "Thứ Ba, 08/09 · Vào 08:12 (muộn 12 phút) · Ra 17:35",
  "existing": { "check_in": "08:12", "check_out": "17:35" },
  "shift": { "label": "Hành chính", "start": "08:00", "end": "17:00" },
  "approver": { "full_name": "Trần Thị Bình", "initials": "TB", "designation": "Trưởng phòng" },
  "reasons": [
    { "value": "On Duty",             "label": "Đi công tác / làm việc bên ngoài", "requires_times": false },
    { "value": "Work From Home",      "label": "Làm việc từ xa",                    "requires_times": false },
    { "value": "Forget Check In/Out", "label": "Quên chấm công",                    "requires_times": true },
    { "value": "Machine Error",       "label": "Máy chấm công lỗi",                 "requires_times": true },
    { "value": "First Working Day",   "label": "Ngày đầu đi làm",                   "requires_times": true },
    { "value": "Other",               "label": "Lý do khác",                        "requires_times": true }
  ],
  "max_days": 31
}}
```

- `requires_times: false` (On Duty, WFH): xác nhận cả ngày làm việc, **không** nhập giờ.
- `requires_times: true`: **bổ sung giờ vào/ra** — mỗi ngày trong khoảng phải có giờ vào và/hoặc giờ ra.
  Duyệt xong ERP tự thêm lần quẹt thẻ và tính lại công.
- `blocked` giống `get_leave_form`.

### `create_attendance_request` — POST (màn 16)

| Tham số | Bắt buộc | |
|---|---|---|
| `from_date`, `to_date` | ✅ | ≤ `max_days` ngày, không có ngày tương lai |
| `reason` | ✅ | `value` từ `reasons` |
| `explanation` | ✅ | ≤ 500 ký tự |
| `times` | khi `requires_times` | JSON array, mỗi ngày trong khoảng một phần tử |
| `client_request_id` | ✅ | §3.3 |

```json
"times": [
  { "date": "2026-09-08", "check_in": "08:00", "check_out": null }
]
```
`check_in` / `check_out`: `HH:MM` hoặc `null`, không được cả hai cùng `null`.

Trả về **`Explanation`** (như `get_attendance_request`).
Lỗi: `READ_ONLY`, `NO_APPROVER`, `APPROVER_NO_USER`, `OVERLAP` (đã có giải trình chờ duyệt trùng ngày),
`VALIDATION` (`field` = `times` / `from_date` …), `FEATURE_DISABLED`.

### `get_attendance_requests` — GET

Danh sách giải trình của tôi (đích điều hướng của thông báo `EXPLANATION_*`, và mục "Giải trình đã gửi").

| Tham số | |
|---|---|
| `status` | như đơn nghỉ |
| `page`, `page_size` | §3.4 |

`items[]` là `Explanation` rút gọn: `id`, `reason_label`, `from_date`, `to_date`, `status`, `status_label`, `created_at`.

### `get_attendance_request` — GET

| Tham số | Bắt buộc |
|---|---|
| `id` | ✅ |

```json
{ "ok": true, "data": {
  "id": "HR-ARQ-26-09-00012",
  "reason": "Forget Check In/Out", "reason_label": "Quên chấm công",
  "from_date": "2026-09-08", "to_date": "2026-09-08",
  "explanation": "Quên quẹt thẻ buổi sáng, vào lúc 08:00.",
  "times": [ { "date": "2026-09-08", "check_in": "08:00", "check_out": null } ],
  "status": "PENDING", "status_label": "Chờ duyệt",
  "approver": { "full_name": "Trần Thị Bình", "initials": "TB", "designation": "Trưởng phòng" },
  "approver_note": null,
  "source": "MINI_APP",
  "created_at": "2026-09-08 18:02:00",
  "decided_at": null,
  "can_cancel": true
}}
```

### `cancel_attendance_request` — POST

| Tham số | Bắt buộc |
|---|---|
| `id` | ✅ |

Chỉ khi `PENDING`. Trả `Explanation` với `status: "CANCELLED"`.

### `get_attendance_summary` — GET (màn 17 "Tổng hợp")

| Tham số | |
|---|---|
| `period` | `YYYY-MM` **kỳ công 26 → 25**, mặc định kỳ hiện tại |

```json
{ "ok": true, "data": {
  "period": "2026-09", "period_label": "Tháng 09/2026",
  "from_date": "2026-08-26", "to_date": "2026-09-25",
  "provisional": true,
  "as_of": "2026-09-28",
  "cutoff_date": "2026-09-25",
  "adjust_until": "2026-10-04",
  "payable_days": { "value": 24, "standard": 25, "source": "ERP" },
  "present_days": 22,
  "paid_leave_days": 1,
  "holiday_days": 1,
  "unpaid_absent_days": 0,
  "late_early": { "count": 2, "minutes": 23 },
  "overtime": { "hours": 12.5, "source": "ERP", "pending_registrations": 1 }
}}
```

- Mọi số **luôn cộng từ bảng công (Attendance) của kỳ**, kể cả khi kỳ đã có phiếu lương — cùng nguồn với lịch
  tháng và chi tiết ngày, nên cộng các ngày trên lịch ra đúng số tổng hợp. Số **được trả lương** nằm trên
  phiếu lương (dòng 1.2 ngày công, 2.1–2.3 giờ tăng ca); hai nơi có thể lệch nếu C&B điều chỉnh khi tính lương.
- `provisional: true` khi C&B **còn được điều chỉnh** công của kỳ (hôm nay ≤ `adjust_until`, tức tới hết mùng 4
  tháng sau) → hiện "Tạm tính đến `as_of`". Hết hạn đó → `false` (đã chốt). **Không** phụ thuộc phiếu lương.
- `payable_days.source` / `overtime.source`: luôn `ERP` (giữ key cho bản app cũ; từ 1.1.4 không còn `PAYSLIP`).
- `cutoff_date` = **ngày cuối kỳ (25)** — chấm công chốt đến hết ngày này. `adjust_until` = **ngày trước
  ngày trả lương** (mùng 4): tới hạn đó C&B vẫn có thể tự tính toán, điều chỉnh công. Câu gợi ý:
  "Số liệu tạm tính, chốt công ngày 25/09; C&B có thể điều chỉnh tới 04/10. Số được trả lương xem ở phiếu lương."

### `get_overtime` — GET (màn 18 "Tăng ca") — ⚠ không còn dùng từ 1.1.3

Mini App đã bỏ tab "Tăng ca": số tổng nằm ở `get_attendance_calendar.overtime_summary`, phiếu đăng ký nằm ở
`get_attendance_day.overtime_registrations`. Endpoint vẫn chạy cho bản app cũ; `items[]` có thêm `id`
(= `registration_id`, giữ lại cho bản cũ).

| Tham số | |
|---|---|
| `period` | `YYYY-MM` kỳ 26 → 25, mặc định kỳ hiện tại |

```json
{ "ok": true, "data": {
  "period": "2026-09", "from_date": "2026-08-26", "to_date": "2026-09-25",
  "registered_approved_hours": 12.5,
  "registered_pending_hours": 2,
  "actual_hours": 12.0,
  "items": [
    { "date": "2026-09-29", "weekday_label": "T3", "begin": "17:30", "end": "19:30", "hours": 2,
      "reason": "Hoàn thành đơn hàng gấp", "status": "PENDING", "status_label": "Chờ duyệt",
      "registration_id": "OTR-26-09-29-0003" },
    { "date": "2026-09-26", "weekday_label": "T7", "begin": "08:00", "end": "12:30", "hours": 4.5,
      "reason": "Kiểm kê kho", "status": "APPROVED", "status_label": "Đã duyệt",
      "registration_id": "OTR-26-09-25-0001" }
  ]
}}
```

- `items` = **phiếu đăng ký tăng ca** (do quản lý tạo trên ERP). `status`:
  `APPROVED` (Đã duyệt) · `PENDING` (Chờ duyệt) · `REGISTERED` (**Đã đăng ký** — phiếu còn ở bản nháp nhưng
  hệ thống chấm công **đang tính** giờ của nó, theo cấu hình hiện tại của TIQN) · `DRAFT` (**Bản nháp** — chỉ khi
  TIQN tắt cấu hình tính phiếu nháp; giờ của nó **không** được tính). Phiếu bị từ chối / đã hủy không hiện.
  ⚠ Đội Mini App đề xuất map `docstatus` của doctype `Overtime Request` — TIQN không dùng doctype đó (0 bản ghi);
  phiếu thật là `Overtime Registration`, và phiếu nháp hiện ra `REGISTERED`, không phải `DRAFT`.
  ⚠ Thực tế 12/10/2026: mọi phiếu từ tháng 8 đều là bản nháp ⇒ gần như toàn bộ là `REGISTERED`.
- Hai ô đầu màn 18: `registered_approved_hours` (= `APPROVED` + `REGISTERED`) / `registered_pending_hours`.
- `actual_hours` = giờ tăng ca **thực tính** (số được trả tiền) — trùng `overtime.hours` của `get_home`
  và `get_attendance_summary`. Nên hiện thêm dòng "Thực tính: 12 giờ" để giải thích chênh lệch với
  giờ đăng ký.
- Màn này chỉ xem: "Phiếu đăng ký tăng ca được tạo và duyệt trên hệ thống ERPNext."

---

## 10. Phiếu lương

Phiếu lương do phòng Nhân sự tính bằng Excel, nhập vào ERP, kiểm rồi bấm **Phát hành**. Chỉ phiếu đã
phát hành mới hiện trên Mini App. Phòng Nhân sự có thể **thu hồi** phiếu để sửa — phiếu biến mất khỏi
app cho tới khi phát hành lại. **Không có tải PDF** (bỏ nút "Tải PDF" ở màn 20 và chữ "tải PDF" ở màn 01).

### `get_payslip_periods` — GET (màn 19)

**Không trả số tiền** — số tiền chỉ có ở `get_payslip`, tải khi người dùng bấm "con mắt" của từng tháng.

| Tham số | |
|---|---|
| `year` | mặc định năm của kỳ hiện tại |

```json
{ "ok": true, "data": {
  "year": 2026,
  "years_available": [2026, 2025],
  "upcoming": { "period": "2026-09", "label": "Tháng 09/2026", "status": "NOT_PUBLISHED",
                "expected_pay_date": "2026-10-05" },
  "items": [
    { "period": "2026-08", "label": "Tháng 08/2026", "status": "PUBLISHED",
      "period_from": "2026-07-26", "period_to": "2026-08-25",
      "pay_date": "2026-09-05", "published_on": "2026-09-05 08:00:00", "is_new": true },
    { "period": "2026-07", "label": "Tháng 07/2026", "status": "PUBLISHED",
      "period_from": "2026-06-26", "period_to": "2026-07-25",
      "pay_date": "2026-08-05", "published_on": "2026-08-05 08:00:00", "is_new": false }
  ]
}}
```

- `upcoming`: kỳ gần nhất **chưa** phát hành (thẻ "Chưa phát hành · dự kiến …" ở đầu màn 19); `null`
  nếu kỳ hiện tại đã phát hành.
- `expected_pay_date` = **mùng 5 tháng sau tháng kết thúc kỳ** (kỳ `2026-09` = 26/08→25/09 → trả 05/10/2026).
  Ngày trả lương do phòng Nhân sự cấu hình trên ERP (mặc định 5); `null` nếu chưa cấu hình.
- `is_new`: phát hành rồi nhưng nhân viên chưa mở lần nào.
- **Trạng thái "đã xem" tính theo `get_payslip`**: lần gọi đầu tiên ghi *ngày xem đầu tiên* trên ERP. Vì vậy
  chỉ gọi `get_payslip` khi người dùng **thực sự mở** phiếu — không prefetch.
- **Cache** (từ 1.5.0): `published_on` của mỗi kỳ là "phiên bản" của phiếu — phòng Nhân sự sửa phiếu phải rút về
  rồi phát hành lại, `published_on` đổi. Mini App lưu kết quả `get_payslip` theo `(period, published_on)` (bộ nhớ +
  storage của Zalo), mở lại phiếu cùng `published_on` thì dùng cache, **không** gọi lại. Xoá cache khi `logout`,
  đổi tài khoản, hoặc nhận `SESSION_INVALID`.
  Khoá luôn là **ngày giờ** `YYYY-MM-DD HH:MM:SS`, giống hệt nhau ở 3 chỗ: `get_payslip_periods.items[].published_on`,
  `get_home.latest_payslip.published_at` và `get_payslip.published_on`. ⚠ `get_home.latest_payslip.published_on` chỉ
  là **ngày** (để hiển thị) — đừng dùng làm khoá. Thiếu khoá (mở từ chỗ khác) → gọi `get_payslip` rồi lưu theo
  `published_on` trong kết quả.
- Nhân viên chế độ chỉ xem vẫn thấy mọi phiếu của mình (gồm phiếu tháng cuối phát hành sau ngày nghỉ).

### `get_payslip` — **POST** (màn 20, và nút "con mắt" màn 19)

POST vì lần mở đầu tiên được ghi lại (ngày xem đầu tiên). Các lần sau không ghi gì.

| Tham số | Bắt buộc | |
|---|---|---|
| `period` | ✅ | `YYYY-MM` |
| `include_zero` | | `0`/`1`; bỏ trống = theo mặc định phòng Nhân sự cấu hình (hiện tại `1`). Từ 1.5.0 **luôn gửi `1`** (hoặc bỏ trống) và để nút "Ẩn khoản 0đ" lọc tại máy: bỏ dòng `is_header = false` có `amount` và `quantity` đều 0/`null` — **không** gọi lại server |

```json
{ "ok": true, "data": {
  "period": "2026-08",
  "label": "Phiếu lương 08/2026",
  "period_from": "2026-07-26", "period_to": "2026-08-25",
  "pay_date": "2026-09-05",
  "published_on": "2026-09-05 08:00:00",
  "currency": "VND",
  "net_pay": 9150000,
  "include_zero": false,
  "employee": { "employee_id": "TIQN-0231", "full_name": "Nguyễn Văn An",
                "department": "Production", "section": "Sewing", "group": "Sewing 05" },
  "rows": [
    { "no": "1",   "label": "Lương cơ bản",   "formula": "a",     "quantity": null, "quantity_unit": null,  "amount": 6000000, "level": 0, "is_header": true },
    { "no": "1.1", "label": "Số ngày làm việc chuẩn trong tháng", "formula": null,    "quantity": 26,   "quantity_unit": "DAY", "amount": null,    "level": 1, "is_header": false },
    { "no": "1.2", "label": "Số ngày công thực tế làm việc", "formula": null,    "quantity": 24,   "quantity_unit": "DAY", "amount": 6000000, "level": 1, "is_header": false },
    { "no": "2",   "label": "Làm việc ngoài giờ", "formula": "b",     "quantity": null, "quantity_unit": null,  "amount": 1400000, "level": 0, "is_header": true },
    { "no": "2.1", "label": "Số giờ làm thêm ngày thường", "formula": null, "quantity": 8.5, "quantity_unit": "HOUR", "amount": 1000000, "level": 1, "is_header": false },
    { "no": "3",   "label": "Lương tháng",    "formula": "c=a+b", "quantity": null, "quantity_unit": null,  "amount": 7400000, "level": 0, "is_header": true },
    { "no": "6",   "label": "Các khoản khấu trừ", "formula": "g",     "quantity": null, "quantity_unit": null,  "amount": 1100000, "level": 0, "is_header": true },
    { "no": "6.1", "label": "BHXH (8%)",      "formula": null,    "quantity": null, "quantity_unit": null,  "amount": 800000,  "level": 1, "is_header": false },
    { "no": "9",   "label": "Thực lĩnh",      "formula": "j=f-g+h+i", "quantity": null, "quantity_unit": null, "amount": 9150000, "level": 0, "is_header": true }
  ],
  "sections": [
    { "key": "EARNINGS", "label": "Thu nhập", "sign": 1, "total": 10200000, "unit": "VND",
      "lines": [
        { "code": "1",   "label": "Lương cơ bản",   "amount": 6000000, "unit": "VND", "is_total": false, "children": [] },
        { "code": "2",   "label": "Làm thêm giờ",   "amount": 1400000, "unit": "VND", "is_total": false, "children": [] },
        { "code": "3",   "label": "Lương tháng",    "amount": 7400000, "unit": "VND", "is_total": true,  "children": [] },
        { "code": "3.1", "label": "Phụ cấp",        "amount": 1800000, "unit": "VND", "is_total": true,
          "children": [
            { "code": "3.2", "label": "Phụ cấp kỹ thuật", "amount": 500000,  "unit": "VND", "is_total": false, "children": [] },
            { "code": "3.5", "label": "Phụ cấp xăng xe",  "amount": 1300000, "unit": "VND", "is_total": false, "children": [] }
          ] },
        { "code": "4",   "label": "Thưởng",         "amount": 1000000, "unit": "VND", "is_total": true,
          "children": [
            { "code": "4.1", "label": "Thưởng chuyên cần", "amount": 1000000, "unit": "VND", "is_total": false, "children": [] }
          ] }
      ] },
    { "key": "DEDUCTIONS", "label": "Khấu trừ", "sign": -1, "total": 1100000, "unit": "VND",
      "lines": [
        { "code": "6.1", "label": "BHXH (8%)",     "amount": 800000, "unit": "VND", "is_total": false, "children": [] },
        { "code": "6.2", "label": "BHYT (1,5%)",   "amount": 150000, "unit": "VND", "is_total": false, "children": [] },
        { "code": "6.3", "label": "BHTN (1%)",     "amount": 100000, "unit": "VND", "is_total": false, "children": [] },
        { "code": "6.4", "label": "Phí công đoàn", "amount": 50000,  "unit": "VND", "is_total": false, "children": [] }
      ] },
    { "key": "OTHERS", "label": "Khoản khác", "sign": 1, "total": 50000, "unit": "VND",
      "lines": [
        { "code": "7.1", "label": "Hỗ trợ tiền cơm", "amount": 50000, "unit": "VND", "is_total": false, "children": [] }
      ] },
    { "key": "ADJUSTMENT", "label": "Điều chỉnh tháng trước", "sign": 1, "total": 0, "unit": "VND", "lines": [] },
    { "key": "ATTENDANCE", "label": "Công & tăng ca", "sign": 0, "total": null, "unit": null,
      "lines": [
        { "code": "1.1", "label": "Công chuẩn",               "amount": 25,  "unit": "DAY",  "is_total": false, "children": [] },
        { "code": "1.2", "label": "Công thực tế",             "amount": 24,  "unit": "DAY",  "is_total": false, "children": [] },
        { "code": "2.1", "label": "Giờ làm thêm ngày thường", "amount": 8.5, "unit": "HOUR", "is_total": false, "children": [] },
        { "code": "2.2", "label": "Giờ làm thêm cuối tuần",   "amount": 4,   "unit": "HOUR", "is_total": false, "children": [] }
      ] }
  ]
}}
```

#### `rows` — phiếu lương như bản in giấy (từ 1.3.0, **dùng cái này**)

Màn 20 hiển thị **giống phiếu lương giấy**: một bảng liền từ 1 tới 9, cột STT, đúng thứ tự trả về
(1, 1.1, 1.2, 2, 2.1, … 3.10, 4, … 9). Ví dụ trên rút gọn; bản thật có đủ mọi khoản.

| Field | |
|---|---|
| `display_label` | *(từ 1.7.0)* **Chữ hiển thị nguyên văn** của dòng, đã gồm số thứ tự và ký hiệu, vd. "1 Lương cơ bản (a)", "9 Thực lĩnh (j=f-g+h+i)" — phòng Nhân sự soạn trên ERP. **Dùng field này**, không ghép thêm `no` / `formula` |
| `no` | Số thứ tự in ở cột STT. Từ 1.7.0 đã có sẵn trong `display_label` — chỉ dùng để tra cứu / làm khoá |
| `label` | *(giữ cho bản app trước 1.7.0)* `display_label` bỏ số thứ tự và ký hiệu. Bản cũ hiển thị `no` + `label` + ` (formula)` → ra cùng chữ với `display_label`. Nhãn có thể dài → cho xuống dòng, đừng cắt |
| `formula` | Ký hiệu của dòng (lấy từ `display_label`), `null` nếu không có. Từ 1.7.0 chỉ để tra cứu |
| `quantity`, `quantity_unit` | Giá trị cột **ĐVT** của phiếu giấy: `DAY` → "24 ngày", `HOUR` → "8,5 giờ". `null` = dòng không có ĐVT. `0` → "–" |
| `amount` | Số tiền VND, **luôn dương như bản in** (khấu trừ không có dấu "−"). `null` = dòng không có số tiền (vd. 1.1 chỉ có số ngày). `0` → "–" |
| `level` | `0` dòng chính, `1` dòng con (thụt vào) |
| `is_header` | Dòng nhóm/tổng (1, 2, 3, 3.1, 4, 5, 6, 7, 8, 9) — in đậm. Dòng `no = "9"` (Thực lĩnh) nên nhấn mạnh |

- Mặc định ERP trả **mọi dòng**, kể cả dòng 0 (`include_zero` mặc định = 1 từ 1.3.0), như bản in.
  Nút "Ẩn khoản 0đ" (từ 1.5.0) lọc **tại máy** trên `rows` đã tải: bỏ dòng con có số tiền và ĐVT đều 0; dòng
  nhóm/tổng vẫn còn. (`include_zero=0` vẫn chạy nhưng đừng dùng — tốn thêm 1 lần gọi.)
- Không tự cộng, không tự sắp lại, không viết cứng nhãn/mã — ERP cấu hình.
- Một dòng có thể có **cả** ĐVT lẫn số tiền (1.2, 2.1–2.3, 7.4, 7.5) — hiện cả hai trên cùng dòng.

#### `sections` — **deprecated từ 1.3.0**

Vẫn trả như cũ để bản Mini App đang chạy không vỡ; sẽ bỏ sau khi Mini App chuyển hẳn sang `rows`.

Quy tắc hiển thị:

| | |
|---|---|
| Thứ tự | `sections` và `lines` đã sắp sẵn — hiển thị đúng thứ tự trả về |
| `sign` | `1` cộng, `-1` hiện dấu "−" trước `total` (số `amount` luôn dương), `0` không phải tiền |
| `is_total` | dòng tổng phụ (vd. "Lương tháng", "Phụ cấp") — có thể in đậm; `children` là chi tiết của nó |
| `unit` | `VND` → định dạng tiền · `DAY` → "24 công" · `HOUR` → "8,5 giờ" |
| `section.total` | tổng của nhóm (Thu nhập = khoản 5, Khấu trừ = khoản 6, …) — **không tự cộng lại ở client** |
| `net_pay` | Thực lĩnh (khoản 9) — **số của phòng Nhân sự**, không tự tính `thu nhập − khấu trừ` |
| `include_zero: false` | dòng chi tiết bằng 0 đã bị bỏ; dòng tổng và nhóm vẫn còn (nhóm rỗng → `lines: []`) |
| `code` | mã khoản trong bảng lương công ty — để tra cứu, không bắt buộc hiển thị |

Nhãn và nhóm do phòng Nhân sự cấu hình trên ERP — **không viết cứng** mã khoản hay nhãn trong Mini App.
Kỳ chưa phát hành / đã thu hồi / không tồn tại → `NOT_FOUND`.

### Chat với C&B (màn 19, 20)

Từ 1.2.0 nút chat mở **chat 1-1 với nhân viên tiền lương** (phòng Nhân sự cấu hình trên ERP), không còn mặc định là OA.
Không có endpoint riêng: đọc `chat` trong `me` / `get_home`, rồi

```js
if (chat) openChat({ type: chat.type, id: chat.id });   // chat.type: "user" | "oa"
```

| `chat` | Nghĩa |
|---|---|
| `{ "type": "user", "id": "<ID by OA>", "name": "Chị Lan - Tiền lương" }` | Chat 1-1 với nhân viên tiền lương. `name` (có thể `null`) dùng làm nhãn nút / dòng phụ |
| `{ "type": "oa", "id": "<OA ID>", "name": "TIQN" }` | Chưa cấu hình người — rơi về chat với OA (nếu ERP bật) |
| `null` | Ẩn nút |

- 🔴 `id` loại `user` là **ID by OA** (`getUserInfo().idByOA`), **không phải** `zalo_user_id` — app quản lý xe đã
  vấp: `zalo_user_id` trông hợp lệ nhưng `openChat` không mở gì. Server không bao giờ trả `zalo_user_id` ở đây.
- Ẩn nút ở chế độ chỉ xem như trước.
- `get_config().oa.chat_enabled` vẫn còn nhưng **đừng** dùng để quyết định nút chat nữa — dùng `chat`.

---

## 11. Bảng tra màn hình → endpoint

| Màn | Endpoint |
|---|---|
| 00 Workflow | `get_config` → (có token) `me` / (không) màn 01 |
| 01 Giới thiệu | `get_config` (`legal.*_url`, `company`) |
| 02 Xin quyền SĐT | `getAccessToken` + `getPhoneNumber` (SDK) → `login` (từ chối cấp SĐT → vẫn `login` không kèm `phone_token`) |
| 03 Từ chối cấp SĐT | `login.result = NO_PHONE` → hiện `zalo_user_id` + nút cho phép SĐT + `get_config.contacts.hr_hotline` |
| 04 Chưa có hồ sơ | `login.result = NOT_FOUND`, `masked_phone`, `zalo_user_id`, `link_request`; "Yêu cầu tạo tài khoản" = `link_employee_request`; "Thử lại" = chạy lại 02 |
| 05 Ngừng hoạt động | `login.result = EXPIRED/DISABLED`, `expired_on`; `contacts.company_phone` |
| 06 Trang chủ | `get_home` |
| 07 Mời quan tâm OA | `get_home.oa.show_invite` → `followOA` (SDK) → `set_oa_follow` |
| 08 Thông báo | `get_notifications`, `mark_notifications_read` |
| 09 Tài khoản | `me`, `get_config`, `set_oa_follow`, `logout`; "Cập nhật số điện thoại" = chạy lại 02 có `phone_token` |
| (dev) Đăng nhập simulator | `dev_login` — chỉ build dev + `get_config.dev_login` (§2.6) |
| 10 Chỉ xem | `get_home` với `access.mode = READ_ONLY` |
| 11 Nghỉ phép | `get_leave_balances`, `get_leave_applications` |
| 12 Tạo đơn | `get_leave_form`, `preview_leave`, `create_leave_application` |
| 12b Đơn ốm + giấy tờ | như 12 + `upload_leave_document` |
| 13 Chi tiết đơn | `get_leave_application`, `cancel_leave_application` |
| 13b Bổ sung giấy tờ | `get_leave_application`, `upload_leave_document`, `delete_leave_document` |
| 14 Chấm công & tăng ca | `get_attendance_calendar` |
| 15 Chi tiết ngày | `get_attendance_day` |
| 16 Gửi giải trình | `get_explanation_form`, `create_attendance_request` |
| 17 Tổng hợp | `get_attendance_summary` |
| 18 Tăng ca *(đã bỏ, gộp vào 14 + 15)* | `get_overtime` (không còn dùng) |
| 19 Phiếu lương | `get_payslip_periods`, `get_payslip` (con mắt) |
| 20 Chi tiết phiếu | `get_payslip` |

**Khác thiết kế (đã chốt với phía ERP):**
- Màn 12/12b: bỏ "Nửa ngày sáng / Nửa ngày chiều", chỉ còn "Cả ngày / Nửa ngày".
- Màn 12: người duyệt luôn là người trong hồ sơ, không đổi được — đúng thiết kế; thiếu người duyệt thì
  không tạo được đơn (`blocked`).
- Màn 01, 20: bỏ "tải PDF".
- Màn 16: thêm 4 lý do bổ sung giờ (Quên chấm công, Máy lỗi, Ngày đầu đi làm, Lý do khác) cần nhập giờ.
- Màn 18: thêm dòng giờ thực tính (`actual_hours`).
- Màn 11: bỏ ô số dư "Nghỉ bù"; nghỉ bù không tạo được từ Mini App.
- Mã đơn nghỉ dạng `LA-YYYY-MM-#####` (thiết kế ghi `HR-LAP-…`).

---

## 12. Hướng dẫn cấu hình Zalo App

> Các bước phía Zalo là theo cấu trúc trang quản trị của Zalo tại thời điểm viết; tên nút/menu có thể
> đổi. Phần **phải làm đúng** là các khoá và quan hệ giữa chúng — đã ghi ⚠/🔴.

### 12.1 Chuẩn bị

- Zalo Official Account (OA) của công ty — để nhân viên "Quan tâm" và chat với C&B.
- Tài khoản Zalo của người quản trị (sẽ là admin của Zalo App và Mini App).
- URL chính sách dữ liệu + điều khoản (đã có sẵn ở `get_config().legal`, phòng Nhân sự sửa nội dung trên
  ERP trước khi nộp duyệt).

### 12.2 Tạo Zalo App (lấy khoá cho server)

1. Vào **developers.zalo.me** → đăng nhập → **Tạo ứng dụng** mới, tên ví dụ "TIQN Cổng nhân viên".
2. Ghi lại **App ID**.
3. Trong trang quản lý ứng dụng, lấy **App Secret Key**.

🔴 Phải là **App Secret Key của chính Zalo App gắn với Mini App này**:
- **KHÔNG** phải secret của OA, **KHÔNG** phải Mini App ID.
- **KHÔNG** dùng lại khoá của Mini App quản lý xe — mỗi Zalo App một khoá. Dùng khoá của app khác,
  Zalo trả lỗi **118** (khoá hợp lệ nhưng sai ứng dụng); app xe từng mất nhiều giờ với lỗi **117** do nhầm khoá.
- ⚠ Zalo user ID là **theo từng app**: cùng một người, ID trong app xe khác ID trong app này. Không thể
  dùng lại ID của app xe.

### 12.3 Tạo Mini App

1. Vào **mini.zalo.me** → **Tạo Mini App** → liên kết với **Zalo App** vừa tạo ở 12.2.
2. Ghi lại **Mini App ID** (dùng ở phía frontend/CLI deploy).
3. **Liên kết OA** của công ty với Mini App — cần cho `followOA()` và `openChat({type:"oa"})`.
   Gửi **OA ID** cho phía ERP để điền vào cấu hình (trả ra ở `get_config().oa.oa_id`).

### 12.4 Xin quyền số điện thoại

1. Trong trang quản lý Mini App → mục **quyền / API** → xin quyền **số điện thoại người dùng**
   (scope `scope.userPhonenumber`, dùng cho `getPhoneNumber()`).
2. Khai báo: mục đích ("xác định nhân viên để xem bảng công, phiếu lương — không có tài khoản/mật khẩu
   riêng"), URL chính sách dữ liệu, ảnh chụp màn 01–03.
3. 🔴 **Zalo xét duyệt thủ công, có thời gian chờ.** Nộp **ngay**, song song với lúc code. Trong lúc chờ,
   kiểm tra xem bản Development có gọi được `getPhoneNumber()` với tài khoản test không.

Quyền người dùng thường cần thêm: `scope.userInfo` (nếu muốn lấy tên/ảnh Zalo — **không bắt buộc** cho
app này, server dùng tên trong hồ sơ nhân viên).

### 12.5 Khai báo domain gọi API

Trong cấu hình Mini App, thêm domain backend vào danh sách được phép gọi:
```
https://erp.tiqn.com.vn:8888
```
(App xe đang gọi được domain + cổng này.) Thiếu bước này: mọi `fetch` bị chặn ngay trong Zalo, không
tới được server — không có log nào phía ERP.

### 12.6 Cấu hình phía server (IT làm)

`sites/erp.tiqn.local/site_config.json`:
```json
{
  "zalo_app_employee_portal_app_id": "<App ID ở 12.2>",
  "zalo_app_employee_portal_secret_key": "<App Secret Key ở 12.2>"
}
```
rồi `bench restart`.

🔴 Khoá **không bao giờ** nằm trong source (repo ở git) hay trong Mini App. Mini App không cần biết khoá này.

**"Bật kiểm tra app secret proof" (trang Zalo App): BẬT.** Server gửi header
`appsecret_proof = HMAC-SHA256(access_token, App Secret Key)` ở **cả hai** lời gọi `graph.zalo.me`
(`/v2.0/me` và `/v2.0/me/info`) — đúng cách SDK PHP chính thức của Zalo tính. Khi bật, một `access_token`
bị lộ không dùng được để gọi Graph API nếu không có secret (secret chỉ nằm trên server). Mini App không phải
làm gì: các hàm `zmp-sdk` không đi qua cơ chế này.
Nếu lần đăng nhập thật đầu tiên lỗi ngay sau khi bật → tắt thử để khoanh vùng, báo phía ERP.

### 12.7 Gọi SDK phía Mini App

```js
import { getAccessToken, getPhoneNumber, followOA, openChat, setStorage, getStorage } from "zmp-sdk";

const accessToken = await getAccessToken();
let phoneToken;
try {
  ({ token: phoneToken } = await getPhoneNumber());
} catch (e) {
  return goTo("03");                     // người dùng từ chối
}
const r = await api.post("login", { access_token: accessToken, phone_token: phoneToken });
// r.ok === false && r.error.code === "ZALO_TOKEN_USED"  → getPhoneNumber() lại, KHÔNG gửi lại token cũ
// r.ok && r.data.token → setStorage({ data: { portal_token: r.data.token } })
```

`getUserID()` **không cần** — server tự lấy ID từ `access_token`, và không tin ID do client gửi.

### 12.8 Bảng mã lỗi Zalo → mã lỗi portal

| Mã Zalo | Zalo nói | Thực chất | `error.code` | Ai sửa |
|---|---|---|---|---|
| 116 | secret_key is empty | thiếu khoá trong site_config | `ZALO_SERVER_CONFIG` | **IT/server** |
| 117 | secret_key is invalid | khoá không hợp lệ | `ZALO_SERVER_CONFIG` | **IT/server** |
| 118 | code is invalid (… different application) | ⚠ khoá **hợp lệ nhưng của SAI Zalo App** | `ZALO_SERVER_CONFIG` | **IT/server** |
| 114 | code is empty | không gửi `phone_token` | `ZALO_TOKEN_INVALID` | Mini App |
| 115 | code is invalid | token hỏng | `ZALO_TOKEN_INVALID` | Mini App |
| 119 | code has already been used | token đã dùng / quá 2 phút | `ZALO_TOKEN_USED` | Mini App, lấy token mới |
| −1401 | User Authentication Required | người dùng chưa cấp quyền | `ZALO_PERMISSION` | người dùng |

⚠ **Không thể kiểm khoá bằng token giả**: Zalo kiểm **phiên trước, khoá sau**, nên token bịa luôn báo
"Session key invalid" dù khoá đúng hay sai. Chỉ một lần đăng nhập thật từ Mini App mới xác nhận được khoá.

### 12.9 Chạy thử

1. Build bản **Development**, thêm tài khoản Zalo của người test vào danh sách tester của Mini App, mở
   bằng QR.
2. **Trên simulator**: dùng `dev_login` (§2.6) — báo phía ERP bật cờ, rồi gọi thử một lần để tài khoản
   simulator hiện trên ERP; phía ERP tick "Allow Dev Login" + gán SĐT nhân viên test cho nó.
   **Trên điện thoại thật (bản Development)**: dùng `login` như bản thật — có quyền SĐT thì đăng nhập
   bằng SĐT Zalo; chưa có quyền SĐT thì phía ERP gán SĐT cho Zalo User ID mà app hiện ra.
3. Phiếu lương test: phía ERP import file mẫu **số giả** (kỳ 09, 10/2026) và phát hành khi cần test — hỏi phía
   ERP kỳ nào đang có. Dữ liệu test được xoá sạch trước khi mở cho toàn công ty.
4. Phát triển giao diện trên trình duyệt (không có token Zalo): dựng mock từ JSON mẫu trong tài liệu này.

### 12.10 Nộp duyệt & phát hành

Khai báo URL chính sách dữ liệu và điều khoản (`get_config().legal`), mô tả việc dùng số điện thoại như
12.4, nộp bản Release.

---

## 13. Nhật ký thay đổi

| Ngày | Phiên bản | Thay đổi |
|---|---|---|
| 12/10/2026 | 1.0-draft | Bản đầu, chờ đội Mini App duyệt. Backend chưa code. |
| 12/10/2026 | 1.0-draft | Chốt: nghỉ bù không tạo được, bỏ ô số dư nghỉ bù (màn 11); ngày trả lương dự kiến = mùng 5 (§10). |
| 12/10/2026 | 1.0-draft | Chốt công hết ngày 25, điều chỉnh tới mùng 4: `get_attendance_summary` thêm `adjust_until`, `cutoff_date` luôn có. Giữ tên máy chấm công. `login` luôn có key `expired_on`. |
| 14/10/2026 | 1.1.1 | Trả lời `QUESTIONS_FOR_BACKEND.md` (Update 02): `designation` giờ là chức danh **tiếng Việt** (mục 17); `approver` của đơn nghỉ **có thể `null`** — đơn HR nhập tay (mục 16); `get_leave_form` thuộc **M3, chưa có** — Mini App chỉ hiện nút "Tạo đơn nghỉ" khi `get_config().features.leave_create = true` (§3.5), hiện đang `false` (mục 15). |
| 14/10/2026 | 1.1.2 | Trả lời Update 02 (mục 18, 19): `employee.avatar_url` giờ là **URL ảnh nhân viên** (§ Employee), `null` khi không có ảnh công khai. Mục 19: simulator không có `access_token` → `login` luôn trả `ZALO_TOKEN_INVALID` "Thiếu mã truy cập Zalo" (không phải `NO_PHONE`); trên simulator dùng `dev_login`. `READ_ONLY` mặc định **30 ngày** (trước 60). Tài khoản mới không khớp nhân viên được dùng bị tự khoá phía ERP — không đổi kết quả trả về. Sửa: request song song sau khi phiên bị thu hồi giờ trả cùng `reason`/`result` (trước đó có thể ra `REVOKED`); `get_payslip_periods.upcoming` không hiện kỳ trước ngày vào làm. |
| 26/10/2026 | 1.7.0 | `get_payslip.rows[]` thêm **`display_label`** — chữ hiển thị nguyên văn, đã gồm số thứ tự và ký hiệu ("9 Thực lĩnh (j=f-g+h+i)"), phòng Nhân sự soạn trên ERP. Mini App hiển thị field này, **không ghép** `no` / `formula` nữa. `label`, `no`, `formula` vẫn trả như cũ (bản app cũ vẫn đúng). |
| 26/10/2026 | 1.6.1 | Không đổi payload. `rows[].label` giờ do phòng Nhân sự sửa trên ERP (Settings ▸ Payslip Lines) — có thể đổi bất cứ lúc nào, Mini App chỉ cần hiển thị đúng chữ server trả, không viết cứng. Text khác (thông báo, lỗi) cũng có thể được ERP đổi mà không cần phát hành bản app mới. |
| 26/10/2026 | 1.6.0 | **Nhãn phiếu lương đúng phiếu giấy:** `rows[].label` (và `sections[].lines[].label`) giờ là phần tiếng Việt nguyên văn trên phiếu giấy, vd. "Công thực tế" → "Số ngày công thực tế làm việc", "Tổng thu nhập" → "Tổng" (§10). Cấu trúc, `no`, `formula`, thứ tự, số liệu **không đổi**. Nhãn dài hơn → cho xuống dòng. Phiếu đã cache vẫn hiện nhãn cũ tới khi phiếu được phát hành lại — chấp nhận được. **Yêu cầu liên kết hồ sơ** (§6): mỗi tài khoản Zalo **1 yêu cầu**, gửi lại = ghi đè (được cả khi đang chờ → không còn lỗi `PENDING`); tối đa **2 lần/ngày** → lỗi mới `REQUEST_LIMIT`; mã NV đang được tài khoản Zalo khác dùng → lỗi mới `EMPLOYEE_LINKED`; `RATE_LIMITED` giờ là quá 10 lần thử/ngày. `link_request` thêm `requested_at`, `request_count`, `requests_today`, `max_per_day`, `remaining_today`, `can_resend` (màn 04 hiện số lần, nút "Sửa yêu cầu"). Mã NV + họ tên phải khớp hồ sơ, không khớp → `NOT_FOUND` ngay (cùng câu với mã không tồn tại, `field: null`). ⚠ Có hiệu lực sau lần migrate + restart tới. |
| 24/10/2026 | 1.5.0 | **Hiệu năng lúc phát hành + gọn ERP:** phiếu lương tải 1 lần, cache theo `(period, published_on)`; "Ẩn khoản 0đ" lọc tại máy, không gọi lại (`include_zero` luôn 1) (§10). Thử lại giãn cách khi lỗi (§3.6). "Đã xem" = chỉ ghi lần mở đầu tiên. `get_config.company.logo_url` luôn `null` (dùng logo Zalo App; key sẽ bỏ ở bản sau). Giới hạn `login` theo IP nâng lên 3000/phút (cả nhà máy dùng chung 1 IP WiFi). Phía ERP: phiếu NV nghỉ việc (thanh toán riêng) có `period_to` = ngày trước ngày nghỉ và `pay_date` riêng — Mini App chỉ cần hiện đúng giá trị server trả; phát hành loại phiếu này **không** tạo thông báo. |
| 24/10/2026 | 1.4.0 | **Yêu cầu liên kết hồ sơ** (màn 04): endpoint mới `link_employee_request` (mã NV + họ tên → phòng Nhân sự duyệt trên ERP, ghi SĐT Zalo vào hồ sơ). `login` thêm key `link_request` (khác `null` khi `NOT_FOUND`: `PENDING` / `REJECTED` + `reject_reason`). Mã lỗi mới `LOGIN_AGAIN`, `PENDING`, `DISABLED` (chỉ endpoint này). Sửa phía ERP: cột SĐT Zalo của hồ sơ trước đây không được so do sai tên field — giờ đã so. ⚠ Có hiệu lực sau lần migrate + restart tới. |
| 24/10/2026 | 1.3.0 | **Phiếu lương như bản in giấy:** `get_payslip` thêm `rows` — một bảng liền 1→9 có STT, mỗi dòng có ĐVT (`quantity`) và số tiền (`amount`), `formula` (a), (c=a+b)…, `level`, `is_header` (§10). `sections` **deprecated** (vẫn trả, ATTENDANCE vẫn ra số ngày/giờ như cũ). Mặc định hiện cả dòng 0 (`include_zero` = 1). |
| 23/10/2026 | 1.2.0 | **Giai đoạn phiếu lương:** `features` chỉ bật `payslip`, `notifications` (§3.5); cờ phụ thuộc tự tắt theo cờ cha. Trang chủ = thẻ nhân viên + phiếu lương mới nhất + thông báo (các khối khác `null`). "Đã xem" của phiếu tính theo `get_payslip` — không prefetch (§10). **Mỗi thông báo = 1 bản ghi** (phiếu lương: 1 thông báo chung/kỳ; HR gửi cả công ty hoặc nhóm người chọn sẵn), không lưu đọc/chưa đọc từng người — `is_read` theo lần `mark_notifications_read` cuối (§7). **Chat với C&B** = chat 1-1 với nhân viên tiền lương: `me.chat` / `get_home.chat`; endpoint mới `set_id_by_oa`. Server lưu **tên Zalo** từ `/v2.0/me` (cần `scope.userInfo`, không bắt buộc) và khớp SĐT thêm cột **SĐT Zalo** của hồ sơ sau SĐT đăng ký (§2.2). **Payload không đổi**; phía ERP đổi cấu trúc lưu phiếu (bỏ bảng con) — Mini App không bị ảnh hưởng. |
| 15/10/2026 | 1.1.4 | **Tổng hợp công luôn lấy từ bảng công** (bỏ D14): `get_attendance_summary`, `get_home.attendance/overtime` cộng Attendance của kỳ kể cả khi đã có phiếu lương; `source` luôn `ERP`. `provisional` = hôm nay ≤ `adjust_until` (mùng 4 tháng sau), không còn phụ thuộc phiếu lương. |
| 15/10/2026 | 1.1.3 | **Gộp tăng ca vào chấm công** (theo yêu cầu Mini App): `get_attendance_calendar` thêm `overtime_summary` + `days[].overtime_hours`; `get_attendance_day` thêm `approved_overtime_hours` + `overtime_registrations[]`; trạng thái OT thêm `DRAFT`; `get_overtime` không còn dùng (vẫn chạy, `items[]` thêm `id`). |
| 12/10/2026 | 1.1 | **Đăng nhập theo Zalo User ID** (§2.2, §2.3, §2.6): `phone_token` thành tuỳ chọn — thiếu thì dùng SĐT phòng Nhân sự gán cho tài khoản; kết quả mới `NO_PHONE`, `DEV_NOT_ALLOWED`; mọi kết quả `login` có `zalo_user_id`; `me` thêm `zalo_user_id`, `login_method`; `get_config` thêm `dev_login`; endpoint mới `dev_login` cho simulator. ⚠ Có hiệu lực qua HTTP sau lần `bench restart` tới. |
| 12/10/2026 | 1.0-M2 | **M2 code xong + 142 test** (chờ `bench restart` mới gọi được qua HTTP): `get_home`, `get_leave_balances`, `get_leave_applications`, `get_leave_application`, `download_document`, `get_attendance_calendar`, `get_attendance_day`, `get_attendance_summary`, `get_overtime`, `get_attendance_requests`, `get_attendance_request`. Thêm trạng thái OT `REGISTERED`. Còn lại (M3): tạo/hủy đơn, giấy tờ, giải trình. |
| 12/10/2026 | 1.0-M1 | **M1 chạy thật trên production**: `get_config`, `login`, `me`, `logout`, `set_oa_follow`, `get_notifications`, `mark_notifications_read`, `get_payslip_periods`, `get_payslip`. Các endpoint còn lại (§7 `get_home`, §8, §9) chưa có — gọi sẽ lỗi "method not found". `features` chỉ bật `payslip`, `notifications`. |

---

## 14. Câu hỏi còn treo

Cho phía ERP / phòng Nhân sự (không chặn việc dựng UI bằng mock):

1. ~~Nghỉ bù~~ — **đã chốt 12/10**: không cho tạo từ Mini App, không hiện số dư.
2. ~~Ngày chốt công~~ — **đã chốt 12/10**: hết ngày 25; C&B điều chỉnh được tới trước mùng 5 tháng sau.
3. ~~Ngày trả lương~~ — **đã chốt 12/10**: mùng 5 hằng tháng.
4. ~~Tên máy chấm công~~ — **đã chốt 12/10**: giữ nguyên `Machine 1`…`Machine 7`.

Cho đội Mini App — vui lòng góp ý trực tiếp trên tài liệu này:

5. Có cần thêm field nào cho màn hình mà payload chưa có không?
6. Phong bì `ok/data/error` (§3.1) có gây khó cho thư viện gọi API đang dùng không? Báo sớm, trước khi backend code.
