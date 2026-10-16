# Prompt cho Claude Code — dựng Zalo Mini App "Cổng nhân viên" (TIQN)

> Gửi kèm 2 file:
> 1. `API_CONTRACT.md` — hợp đồng API với backend ERPNext (**nguồn chính, không được tự suy diễn ngoài nó**)
> 2. `Zalo Mini App – Cổng nhân viên ERPNext.html` — thiết kế 21 màn (đánh số 00–20)
>
> Copy toàn bộ phần dưới đường kẻ vào phiên Claude Code của dự án Mini App.

---

## Bối cảnh

Bạn dựng **frontend Zalo Mini App "Cổng nhân viên"** cho công ty TIQN (nhà máy may, ~1.000 công nhân,
dùng điện thoại Android tầm trung, mạng WiFi xưởng). Nhân viên mở app trong Zalo để xem phiếu lương,
chấm công, tăng ca, số dư phép, tạo đơn nghỉ và gửi giải trình chấm công.

Backend là **ERPNext** của công ty, đã có sẵn, do đội khác làm. Bạn **chỉ làm frontend** và **không có
quyền sửa backend**. Mọi request/response nằm trong `API_CONTRACT.md` đính kèm. Thiết kế giao diện nằm
trong file HTML đính kèm.

Đây là một **Mini App mới, riêng** (Zalo App ID riêng). Công ty đã có một Mini App quản lý xe khác —
**đừng tham khảo hay chép cách xác thực của app đó**: app xe dùng API key nhúng trong client, app này thì
**không có API key nào** (contract §1, §2).

## Nguyên tắc bắt buộc

1. **Contract là nguồn chính.** Không tự thêm endpoint, field, tham số hay mã lỗi. Thiếu gì để dựng màn
   hình → ghi vào `QUESTIONS_FOR_BACKEND.md` (mỗi câu: màn nào, cần gì, vì sao) và dựng tạm bằng mock,
   **không** tự chế cách lách.
2. **Thiết kế khác contract → theo contract.** Contract §11 liệt kê các chỗ đã chốt khác thiết kế
   (bỏ "Nửa ngày sáng/chiều", bỏ "Tải PDF", bỏ ô số dư "Nghỉ bù", thêm 4 lý do giải trình cần nhập giờ,
   thêm dòng giờ tăng ca thực tính, mã đơn dạng `LA-YYYY-MM-#####`…).
3. **Không viết cứng dữ liệu nghiệp vụ.** Loại nghỉ, lý do giải trình, nhãn/nhóm khoản lương, giới hạn tệp,
   hotline, link chính sách… đều lấy từ API (`get_config`, `get_leave_form`, `get_explanation_form`,
   `get_payslip`). Mã khoản lương (`code`) chỉ để tra cứu, không dùng để rẽ nhánh hiển thị.
4. **Rẽ nhánh theo `error.code`, không theo `error.message`.** `message` là câu tiếng Việt hiển thị thẳng
   cho người dùng.
5. **Toàn bộ chữ trên giao diện là tiếng Việt**, giọng thân thiện, ngắn gọn như trong thiết kế.

## Kết nối — làm đúng một lần trong một module `api/`

- Base URL lấy từ biến môi trường (`VITE_API_BASE`), mặc định
  `https://erp.tiqn.com.vn:8888/api/method/customize_erpnext.api.employee_portal`.
- **Một hàm `request()` duy nhất** cho mọi lời gọi:
  - `credentials: "omit"` — bắt buộc (contract §1, lý do CSRF).
  - Header `X-Portal-Token` (trừ `get_config`, `login`) và `X-Portal-Client-Version` = version app.
  - **Không bao giờ** gửi header `Authorization`.
  - Đúng HTTP method từng endpoint (bảng trong contract). Endpoint có ghi dữ liệu là `POST` — kể cả
    `get_payslip`. Sai method → backend trả HTTP 403.
  - Đọc `json.message` → phong bì `{ ok, data | error, server_time }` (contract §3.1).
  - HTTP 500 / mất mạng → lỗi chung "Có lỗi, vui lòng thử lại" + nút thử lại.
- **Xử lý mã lỗi tập trung** (contract §4):
  - `SESSION_REQUIRED` / `SESSION_INVALID` → xoá token, về màn 01; riêng `SESSION_INVALID` với
    `details.reason = "STATUS_CHANGED"` → màn theo `details.result` (04/05).
  - `CLIENT_TOO_OLD` → màn yêu cầu cập nhật app.
  - `FEATURE_DISABLED` → ẩn tính năng.
  - `RATE_LIMITED` → chờ `details.retry_after` giây.
  - Các mã còn lại trả về cho màn hình tự hiển thị `message` (tô đỏ ô `error.field` nếu có).
- **Kiểu TypeScript** cho mọi request/response, viết đúng theo JSON mẫu trong contract. Key luôn có mặt,
  giá trị có thể `null`; danh sách rỗng là `[]`.

## Mock — để dựng UI khi backend chưa có

Backend đang chạy theo mốc (contract §13):
- **Đã chạy thật (M1):** `get_config`, `login`, `me`, `logout`, `set_oa_follow`, `get_notifications`,
  `mark_notifications_read`, `get_payslip_periods`, `get_payslip`.
- **Code xong, sắp bật (M2):** `get_home`, lịch/chi tiết/tổng hợp chấm công, tăng ca, số dư phép, danh sách
  và chi tiết đơn nghỉ / giải trình, `download_document`.
- **Chưa có (M3):** tạo/hủy đơn nghỉ, upload/xoá giấy tờ, `preview_leave`, `get_leave_form`,
  `get_explanation_form`, tạo/hủy giải trình.

Làm một lớp mock bật/tắt bằng `VITE_USE_MOCK` (bật theo **từng endpoint**, để dùng thật endpoint nào đã có):
- Dữ liệu mock **chép đúng JSON mẫu trong contract**, thêm biến thể cho các trạng thái: rỗng, đang chờ,
  bị từ chối, chế độ chỉ xem, bị chặn (`blocked`), lỗi từng mã.
- Ở chế độ thật, tính năng nào `get_config().features` đang tắt thì ẩn lối vào — đừng gọi endpoint của nó.

## Luồng đăng nhập (contract §2) — làm đúng từng chi tiết

Zalo luôn xác nhận **ai** (User ID từ `access_token`, server tự hỏi Zalo). **Số điện thoại** đến từ Zalo
(`phone_token`) hoặc từ SĐT phòng Nhân sự đã gán cho Zalo User ID đó trên ERP.

1. Mở app → `get_config` (cache tối đa 1 giờ). Có token trong `getStorage` → gọi `me`:
   `ok` → vào màn theo `access.mode`; lỗi phiên → xoá token, về màn 01.
2. Màn 01 → bấm "Đăng nhập bằng số điện thoại" → `getAccessToken()` rồi thử `getPhoneNumber()`.
3. Gọi `login(access_token, phone_token)` **ngay** (token SĐT sống 2 phút, dùng 1 lần).
   Người dùng **từ chối** cấp SĐT → **vẫn gọi `login(access_token)` không kèm `phone_token`**.
   - `ZALO_TOKEN_USED` → gọi lại `getPhoneNumber()` lấy token **mới**. **Không bao giờ** gửi lại token cũ.
   - `ZALO_SERVER_CONFIG` → lỗi phía server: hiện `message`, không tự thử lại.
4. Theo `data.result`: `ACTIVE` → 06 (+ màn 07 nếu `oa.show_invite`), `READ_ONLY` → 10,
   `NO_PHONE` → **03** (nút "Cho phép đọc số điện thoại" chạy lại bước 2–3 + hiện `zalo_user_id`),
   `NOT_FOUND` → 04 (hiện `masked_phone` + `zalo_user_id`), `EXPIRED`/`DISABLED` → 05.
   Ở màn 03/04, `zalo_user_id` hiển thị dạng copy được kèm câu "Gửi mã này cho phòng Nhân sự để được
   kích hoạt" — HR gán SĐT cho mã đó trên ERP, người dùng bấm "Thử lại" là vào được.
5. Lưu `token` bằng `setStorage`. **Không** lưu số điện thoại, không lưu `access_token`/`phone_token`.
6. **Không dùng `getUserID()` làm danh tính khi đăng nhập thật** — server tự lấy ID từ `access_token`.
7. Màn 09 có mục "Cập nhật số điện thoại" = chạy lại bước 2–3 **có** `phone_token`, lưu token mới.

### Simulator — `dev_login` (contract §2.6)

Trên Zalo simulator không lấy được `access_token`/SĐT thật ⇒ dùng `dev_login(zalo_user_id)` với ID của
`getUserInfo()`/`getUserID()`.
- Chỉ có trong **build dev** (ví dụ `VITE_DEV_LOGIN=1`) **và** khi `get_config().dev_login = true`. Bản build
  release **không chứa** code gọi `dev_login` (loại bỏ lúc build, không chỉ ẩn nút).
- `result = "DEV_NOT_ALLOWED"` → hiện `zalo_user_id` + `message`: phía ERP cần tick "Allow Dev Login" và gán SĐT
  nhân viên test cho ID đó. Lần gọi đầu với ID lạ tự tạo tài khoản trên ERP để phía ERP tìm thấy.
- Phiên dev sống 1 ngày; hết thì `dev_login` lại. Không dùng `dev_login` làm đường dự phòng khi `login` lỗi.

## Chế độ chỉ xem (`access.mode = "READ_ONLY"`)

Ẩn ở **mọi** màn: Tạo đơn nghỉ, Hủy đơn, Bổ sung giấy tờ, Gửi giải trình, Chat với C&B; hiện băng
"Chế độ chỉ xem đến <read_only_until>" như màn 10. Server cũng chặn, nhưng client phải ẩn để không ai bấm
phải nút vô dụng.

## Bảo mật phía client

- Danh sách phiếu lương (màn 19) **không có số tiền** — chỉ khi bấm "con mắt" mới gọi `get_payslip` của
  đúng tháng đó. Mặc định số tiền **ẩn** (`•••••••`).
- **Không** cache số tiền lương vào `setStorage`/localStorage; chỉ giữ trong bộ nhớ khi màn đang mở.
- Không log token, SĐT, số tiền ra console ở bản build release.
- Ảnh/PDF giấy tờ dùng thẳng `Document.url` (link tuyệt đối, có chữ ký, hạn 10 phút) trong `<img>` hoặc
  `openWebview`. Hết hạn → gọi lại endpoint chi tiết để lấy link mới. **Không** tự ghép đường dẫn tương đối.

## Quy tắc hiển thị quan trọng

- Định dạng ngày hiển thị `dd/MM/yyyy`, giờ `HH:mm`; tiền `9.150.000 đ` (dấu chấm ngăn nghìn); công
  "24 công", giờ "8,5 giờ" (dấu phẩy thập phân).
- **Phiếu lương (màn 20):** hiển thị đúng thứ tự `sections` → `lines` → `children` server trả. Nhóm
  `sign = -1` hiện dấu "−" trước tổng; `is_total` in đậm; `unit` quyết định định dạng (VND/DAY/HOUR).
  **Không tự cộng** tổng nhóm hay tự tính thực lĩnh — dùng `section.total` và `net_pay`. Có công tắc
  "Hiện cả khoản 0đ" → gọi lại với `include_zero=1`.
- **Lịch chấm công (màn 14):** tô màu theo `display` (bảng contract §9); hôm nay viền đậm; bấm ngày → màn 15.
- **Tổng hợp công (màn 17):** `payable_days.source = "PAYSLIP"` nghĩa là số đã chốt theo phiếu lương;
  `provisional = true` → câu "Số liệu tạm tính, chốt công ngày <cutoff_date>; C&B có thể điều chỉnh tới
  <adjust_until>."
- **Tăng ca (màn 18):** trạng thái `REGISTERED` hiển thị "Đã đăng ký" (phần lớn phiếu hiện ở trạng thái này);
  thêm dòng "Thực tính: <actual_hours> giờ" dưới hai ô tổng.
- **Đơn nghỉ (màn 12):** gọi `get_leave_form` khi mở; `blocked` khác `null` → hiện `blocked.message` thay cho
  form. Đổi loại/ngày/thời lượng → gọi `preview_leave` (debounce ~400ms) để hiện số ngày và phép còn lại.
  Nút "Gửi đơn" sinh `client_request_id` (UUID v4) **một lần mỗi lần bấm**; mạng lỗi thì gửi lại **cùng** id.
- **Đơn ốm có giấy tờ (12b):** tạo đơn trước → upload từng tệp với `leave_application = id`. Upload lỗi thì
  đơn vẫn đã gửi: báo "Đơn đã gửi, N tệp chưa tải lên" và cho tải lại ở màn 13b. Kiểm loại/dung lượng/số
  tệp phía client theo `get_config().uploads` trước khi gửi (server vẫn kiểm lại).
- **Thông báo (màn 08):** `title` đậm + `body` thường; điều hướng theo `target.screen`/`target.id`;
  `type` lạ → chỉ hiển thị, không điều hướng. Làm mới khi app trở lại foreground, **không poll** nhanh hơn
  60 giây.
- **Chat với C&B:** `openChat({ type: "oa", id: get_config().oa.oa_id })`; ẩn khi `oa.chat_enabled = false`.
- **Quan tâm OA (màn 07):** sau `followOA()` thành công gọi `set_oa_follow("FOLLOWED")`; bấm "Để sau" gọi
  `set_oa_follow("DISMISSED")`.

Mọi màn có đủ trạng thái: đang tải (skeleton), rỗng, lỗi + thử lại, chỉ xem.

## Đọc file thiết kế

File HTML là bản đóng gói tự giải nén: mở bằng trình duyệt để xem. Nếu cần đọc chữ của từng màn bằng
code (không mở được trình duyệt), file chứa `<script type="__bundler/manifest">` (JSON: mỗi tài nguyên là
base64, có thể gzip) và `<script type="__bundler/template">`; **mỗi màn là một trang lồng** có manifest +
template riêng. Đoạn Python sau in chữ của từng màn:

```python
import re, json, base64, gzip, html, sys
src = open(sys.argv[1], encoding="utf-8").read()
def blk(h, t):
    m = re.search(r'<script type="__bundler/%s">(.*?)</script>' % t, h, re.S)
    return json.loads(m.group(1)) if m else None
man, tpl = blk(src, "manifest"), blk(src, "template")
pages = {}
for uid, e in man.items():
    b = base64.b64decode(e["data"])
    if e.get("compressed"): b = gzip.decompress(b)
    if e["mime"] == "text/html": pages[uid] = b.decode("utf-8", "replace")
for title, uid in re.findall(r'<h2>(.*?)</h2><iframe src="about:blank#([0-9a-f-]+)"', tpl):
    inner = blk(pages[uid], "template") or ""
    text = re.sub(r"<(style|script)[^>]*>.*?</\1>|<svg.*?</svg>", "", inner, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", "\n", text))
    print("=====", html.unescape(title)); print(" | ".join(l.strip() for l in text.splitlines() if l.strip())[:3000])
```

Màn 00 là sơ đồ luồng đăng nhập (không phải màn của app).

## Thứ tự làm

1. Khung dự án (template chính thức mới nhất của `zmp-cli`, React + TypeScript + ZaUI), module `api/`
   + kiểu dữ liệu + lớp mock.
2. Màn 01–05, 09, 10 + luồng đăng nhập **với backend thật** (M1 đã chạy).
3. Màn 19, 20 phiếu lương **với backend thật**.
4. Màn 06, 07, 08.
5. Màn 11, 13, 13b (phần xem), 14, 15, 17, 18 — mock, chuyển sang thật khi M2 bật.
6. Màn 12, 12b, 13 (hủy), 13b (bổ sung), 16 — mock theo contract, chờ M3.

Sau mỗi bước: liệt kê màn đã xong, endpoint đang thật/mock, và cập nhật `QUESTIONS_FOR_BACKEND.md`.

## Chạy thử thật

- Cấu hình Mini App (contract §12): App ID, liên kết OA, xin quyền số điện thoại, khai báo domain
  `https://erp.tiqn.com.vn:8888`. Thiếu khai báo domain thì mọi `fetch` bị Zalo chặn, server không thấy gì.
- Simulator: `dev_login` (ở trên). Điện thoại thật (bản Development + tài khoản tester): `login` như bản thật.
  Hiện có phiếu lương **số giả** kỳ 07, 08, 09/2026 cho 2 người test **TIQN-0148** và **TIQN-1405** — tài khoản
  simulator / Zalo test được phía ERP gán SĐT của hai người này để xem.

## Không được làm

- Không gửi tham số `employee`, `zalo_user_id`, `phone` để "chọn nhân viên" — server tự biết từ token.
  (Ngoại lệ duy nhất: `dev_login(zalo_user_id)` trong build dev.)
- Không gửi header `Authorization`, không nhúng API key/secret nào vào bundle.
- Không gọi `GET` cho endpoint ghi.
- Không gửi lại `phone_token` đã dùng.
- Không tự tính lương, tổng nhóm, số ngày nghỉ hay số dư phép ở client.
- Không viết cứng loại nghỉ, lý do giải trình, nhãn khoản lương, hotline, giới hạn tệp.
- Không lưu SĐT hay số tiền lương xuống bộ nhớ máy.
- Không sửa `API_CONTRACT.md` — thắc mắc ghi vào `QUESTIONS_FOR_BACKEND.md`.
