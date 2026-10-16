# Prompt cập nhật 01 — Đăng nhập theo Zalo User ID + `dev_login` cho simulator

> Gửi kèm `API_CONTRACT.md` **bản 1.1**. Chỉ cần gửi file này nếu đội Mini App đã nhận
> `PROMPT_MINIAPP_CLAUDE_CODE.md` bản cũ; nếu chưa thì gửi bản prompt chính mới nhất là đủ.
> Copy toàn bộ phần dưới đường kẻ vào phiên Claude Code của dự án Mini App.

---

## Thay đổi backend (contract 1.0 → 1.1)

Backend đổi cách đăng nhập để chạy được trên **Zalo simulator** (không lấy được số điện thoại) và để
nhân viên **từ chối cấp SĐT vẫn dùng được** nếu phòng Nhân sự đã gán SĐT cho họ. Đọc lại contract §2.2,
§2.3, §2.6, `login`, `dev_login`, `me`, `get_config` (mục 6) và bảng màn hình §11.

Tóm tắt:
1. **`login`: `phone_token` thành TUỲ CHỌN.** Zalo vẫn luôn xác nhận User ID qua `access_token`. Thiếu
   `phone_token` → server dùng SĐT đã lưu trong tài khoản Zalo đó (phòng Nhân sự gán tay trên ERP, hoặc lưu
   từ lần đăng nhập trước có quyền SĐT).
2. **Kết quả mới `NO_PHONE`**: không có `phone_token` và tài khoản chưa có SĐT → không có token.
3. **Mọi kết quả `login` có `zalo_user_id`** (User ID của chính người dùng trong Mini App này).
4. **`me` thêm `zalo_user_id`, `login_method`** (`ZALO_PHONE` · `STORED_PHONE` · `DEV`).
5. **`get_config` thêm `dev_login`** (boolean).
6. **Endpoint mới `dev_login(zalo_user_id)`** — chỉ cho simulator, kết quả thêm `DEV_NOT_ALLOWED`.
7. `SESSION_INVALID` có thể mang `reason: "PHONE_CHANGED"` khi phòng Nhân sự đổi SĐT của tài khoản.

## Việc cần làm ở Mini App

### A. Luồng đăng nhập thật (màn 01–04)
- `getPhoneNumber()` bị từ chối → **đừng dừng ở màn 03 nữa**: gọi `login(access_token)` **không kèm**
  `phone_token`. Có token → vào app như thường.
- `result = "NO_PHONE"` → màn 03 mới:
  - nút "Cho phép đọc số điện thoại" → chạy lại `getAccessToken()` + `getPhoneNumber()` + `login`;
  - hiện **`zalo_user_id`** (chọn/copy được, có nút Copy) + câu "Gửi mã này cho phòng Nhân sự để được kích
    hoạt" + hotline `get_config().contacts.hr_hotline`;
  - nút "Thử lại" (sau khi phòng Nhân sự báo đã gán) → chạy lại `login` (có thể không kèm `phone_token`).
- `result = "NOT_FOUND"` → màn 04 hiện thêm `zalo_user_id` như trên.
- Thêm `NO_PHONE`, `DEV_NOT_ALLOWED` vào kiểu `LoginResult`; thêm `zalo_user_id` vào kiểu response `login`/`me`,
  `login_method` vào `me`, `dev_login` vào `get_config`.

### B. Màn 09 — "Cập nhật số điện thoại"
Thêm mục này: chạy lại `getAccessToken()` + `getPhoneNumber()` + `login` **có** `phone_token`, thay token đang
lưu bằng token mới. Có thể làm nổi mục này khi `me().login_method !== "ZALO_PHONE"`.

### C. Simulator — `dev_login`
- Chỉ build dev (biến môi trường riêng, ví dụ `VITE_DEV_LOGIN=1`) **và** `get_config().dev_login === true`
  mới hiện luồng này. **Bản build release không chứa code gọi `dev_login`** — loại bỏ lúc build (dead-code
  elimination theo biến môi trường), không chỉ ẩn nút.
- Luồng: lấy ID bằng `getUserInfo()` (hoặc `getUserID()`) → `dev_login(zalo_user_id)` → xử lý `result`
  giống `login`.
- `DEV_NOT_ALLOWED` → hiện `zalo_user_id` + `message`. Gửi ID đó cho phía ERP: phía ERP tick
  "Allow Dev Login" + gán SĐT nhân viên test (TIQN-0148 / TIQN-1405 đang có phiếu lương số giả) → gọi lại.
- Phiên dev sống **1 ngày**; hết hạn (`SESSION_INVALID`) → `dev_login` lại.
- **Không** dùng `dev_login` làm đường dự phòng khi `login` lỗi.

### D. Xử lý `SESSION_INVALID`
`reason: "PHONE_CHANGED"` → xoá token, về màn 01 với câu "Số điện thoại của tài khoản vừa được cập nhật,
vui lòng đăng nhập lại."

### E. Mock
Thêm biến thể mock: `login` → `NO_PHONE` / `NOT_FOUND` có `zalo_user_id`; `dev_login` → `ACTIVE` /
`DEV_NOT_ALLOWED` / `FEATURE_DISABLED`; `me` có `login_method`.

## Không đổi

Mọi endpoint khác, phong bì `ok/data/error`, header `X-Portal-Token`, `credentials: "omit"`, quy tắc
không gửi `employee`/`phone`. Ngoại lệ duy nhất được gửi `zalo_user_id` là `dev_login` trong build dev.

## Trạng thái server

Phần thay đổi này **đã code + test ở backend**, có hiệu lực qua HTTP sau lần `bench restart` tới (phía ERP
sẽ báo). Trước đó: dựng UI bằng mock theo contract 1.1. Cờ `dev_login` trên server do phía ERP bật khi đội
Mini App cần.

Sau khi làm xong: liệt kê thay đổi, và ghi mọi thắc mắc vào `QUESTIONS_FOR_BACKEND.md`.
