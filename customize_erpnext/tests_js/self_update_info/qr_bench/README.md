# Đo bộ giải mã QR CCCD (28/10/2026)

So **jsQR 1.4.0 + 3 vùng cắt thu 900px** (cách cũ của trang www) với **ZXing-WASM** (bộ giải mã đang dùng, qua
`barcode-detector`) trên 240 khung hình camera GIẢ 1920×1080 — họ tên / số / địa chỉ bịa, không dùng ảnh CCCD thật.
Biến thiên: cỡ ô QR 1,5–4px, mờ Gauss 0 / 0,8 / 1,5px, vệt lóa, nghiêng 15°, sửa lỗi L / M, nhiễu, JPEG 80.

```bash
cd apps/customize_erpnext/customize_erpnext/tests_js/self_update_info/qr_bench
npm install
../../../../../../env/bin/python gen.py        # cần Pillow, numpy, qrcode (có sẵn trong env của bench) → cases/ (~300MB)
node run.mjs                                    # bảng tỷ lệ đọc được + thời gian; ghi results.json
rm -rf cases                                    # ảnh sinh lại được, đừng commit
```

Kết quả 28/10/2026 (`hiện tại / ZXing khung ngắm / ZXing mọi vùng`, %):

| cỡ ô | nét | mờ 0,8px | mờ 1,5px |
|---|---|---|---|
| 1,5px | 31 / 56 / 69 | 0 / 0 / 0 | 0 / 0 / 0 |
| 2px | 100 / 100 / 100 | 25 / 31 / 56 | 0 / 0 / 0 |
| 2,5–3px | 100 / 100 / 100 | 100 / 100 / 100 | 0 / 0 / 0 |
| 4px | 100 / 100 / 100 | 100 / 100 / 100 | 94 / 100 / 100 |

Thời gian 1 lần giải mã (CPU máy chủ): jsQR + tăng tương phản ~58ms, ZXing ~5ms. Kết luận: ảnh đủ to + nét thì thư
viện nào cũng đọc; ZXing hơn ở mã nhỏ / hơi mờ và nhanh ~10x (nhiều khung / giây hơn). Chất lượng ảnh quyết định →
trang dùng zoom ~2x + lấy nét liên tục khi camera hỗ trợ, và nút "Chụp / chọn ảnh CCCD".
Đã kiểm thêm trên Chromium thật: thư viện + `zxing_reader-3.1.3.wasm` tự lưu đọc đúng mã (7–32ms / lần).
Khi nâng phiên bản `barcode-detector` / `zxing-wasm`: chạy lại, so bảng này.

## Độ giật của máy quét trên trang thật (perf.mjs, 28/10/2026)

Chromium headless thật (`chromium/chrome-linux/headless_shell` của bench), camera giả từ `.y4m`, mở trang
`/employee-self-update-info` qua nginx (form.js, thư viện, WASM thật; chỉ giả lập API dữ liệu), hãm CPU luồng chính.

```bash
../../../../../../env/bin/python make_video.py           # noread.y4m / read.y4m (~90MB mỗi file, đừng commit)
node perf.mjs $PWD/noread.y4m 4 6                         # CPU /4, quét liên tục 6 giây
node perf.mjs $PWD/read.y4m 4 4                           # thời gian tới khi điền được field
DRAFT=/đường/dẫn/bản-nháp node perf.mjs …                 # thay form.js + qr_worker.js bằng bản nháp
# headless_shell thiếu libasound.so.2 → tải gói libasound2t64 (.deb), giải nén, đặt LD_LIBRARY_PATH
```

| CPU /4, quét liên tục | khung hình/s | khung chậm nhất | luồng chính bị khoá |
|---|---|---|---|
| giải mã trên luồng chính (trước) | 32 | 200ms | 422ms mỗi giây |
| giải mã trong Web Worker (qr_worker.js) | 60 | 33ms | 0ms |

Lưu ý: Chromium chỉ hãm CPU luồng chính, không hãm worker → trên điện thoại thật worker vẫn ~150–200ms / lần
(~5 lần / giây) nhưng hình camera không giật.
