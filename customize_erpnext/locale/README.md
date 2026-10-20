# Bản dịch tiếng Việt — `locale/vi.po`

Từ 21/10/2026 toàn bộ tiếng Việt của site đi qua **một file**: `customize_erpnext/locale/vi.po`.
`translations/vi.csv` không còn dùng (đã đổi tên `vi.csv.old`).

## File gồm 2 lớp (đánh dấu bằng comment `#.` trên từng entry)

| Tag | Nội dung | Thắng khi trùng |
|---|---|---|
| `#. source: erpnext2vi` | Tiếng Việt cho frappe / erpnext / hrms / insights / lms / payments, lấy từ [n8n2erpnext/erpnext2vi](https://github.com/n8n2erpnext/erpnext2vi) (cộng đồng, public), ghim commit trong `scripts/vi_po.py` (`ERPNEXT2VI_SHA`) | Thắng bản dịch gốc của các app đó |
| `#. source: tiqn` | Text **riêng** của customize_erpnext (chỉ app này / chỉ DB customisation dùng) + `TIQN_KEEP` (Section, Relieving Date, Submit, Submitted, Delivery Note, Purchase Receipt) | Thắng erpnext2vi |

Quy tắc chọn (user chốt 21/10/2026): **ưu tiên erpnext2vi**; chỉ text riêng của app và danh sách `TIQN_KEEP` mới dùng bản TIQN. Một chữ chung mà code của mình cũng dùng (`Employee`, `Status`…) là chữ của core → theo erpnext2vi.

## Vì sao file này thắng

Frappe ghép bản dịch: mỗi app `translations/vi.csv` rồi `.mo`; các app theo thứ tự cài: frappe → erpnext → hrms → insights → **customize_erpnext** → lms → payments; **app sau thắng**. `.mo` của app này nằm sau frappe/erpnext/hrms/insights nên đè được bản dịch gốc của chúng.

## 🔴 Quy tắc

1. **KHÔNG chạy `bench update-po-files --app customize_erpnext`**, **KHÔNG** dùng "Update from POT" của Poedit, **KHÔNG** `bench migrate-csv-to-po`. Các lệnh này chỉ giữ chuỗi có trong code của app → xoá sạch ~19k dòng erpnext2vi (không báo lỗi).
2. **Sửa `vi.po` xong phải biên dịch**: `bench compile-po-to-mo --app customize_erpnext` (hoặc `bench build`). `.mo` nằm ở `sites/assets/locale/vi/LC_MESSAGES/customize_erpnext.mo` — không có trong git; máy mới/deploy mới phải build. Sau đó `bench --site <site> clear-cache`.
3. **Không tạo lại `translations/vi.csv`**: trong cùng app `.csv` nạp TRƯỚC `.mo` → dòng trong csv luôn thua erpnext2vi.
4. **Chuỗi mới trong code của app** (UI English-first, bọc `__()` / `_()`):
   ```bash
   bench --site erp.tiqn.local execute customize_erpnext.scripts.vi_po.add_new_strings
   ```
   → thêm msgid còn thiếu (msgstr rỗng, tag `tiqn`), không xoá gì. Dịch các dòng đó trong `vi.po` (giữ nguyên `{0}`, `%s`, thẻ HTML), rồi biên dịch (bước 2).
5. Muốn một chữ của core hiện theo nghĩa TIQN: thêm vào `TIQN_KEEP` trong `scripts/vi_po.py` rồi `build` lại — sửa tay trong `vi.po` thì lần `build` sau sẽ mất nếu chữ đó không thuộc text riêng.
6. Kiểm tra: `bench --site erp.tiqn.local execute customize_erpnext.scripts.vi_po.check` (số dòng không tụt dưới ngưỡng, placeholder đúng).

## Cập nhật erpnext2vi

1. Đổi `ERPNEXT2VI_SHA` trong `scripts/vi_po.py`.
2. Chạy thử, chỉ báo cáo: `... vi_po.build --kwargs "{'write': 0}"` → đọc file báo cáo JSON (số chữ đổi / Anh→Việt / Việt→Anh, từng key).
3. Ổn thì `... vi_po.build` (ghi `vi.po`, giữ mọi entry `source: tiqn`), biên dịch, clear-cache, commit `vi.po`.

## Ngoại lệ

Trang làm bài `www/quiz/` viết cứng tiếng Việt, không qua bản dịch (user chốt 20/10/2026).
