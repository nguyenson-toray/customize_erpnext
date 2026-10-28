# Hướng dẫn sử dụng Cổng nhân viên — dành cho C&B

> Dành cho người có role **CnB** trên ERP. Cổng nhân viên là Zalo Mini App, nơi nhân viên xem **phiếu lương** và
> **thông báo** trên điện thoại. C&B làm mọi việc trên ERP: nhập phiếu lương, phát hành, gửi thông báo, duyệt
> tài khoản.
> Tên nút trong tài liệu ghi theo giao diện tiếng Việt, kèm tên tiếng Anh trong ngoặc khi cần.

---

## 1. Vào chức năng

Trang chủ ERP → icon **Cổng nhân viên** (Employee Portal). Không thấy icon nghĩa là tài khoản chưa có role **CnB**,
báo IT. Menu bên trái:

| Menu | Dùng để |
|---|---|
| **Tải phiếu lương** (Payslip Upload) | Tải file mẫu, nhập file lương, phát hành / thu hồi theo kỳ — **dùng hằng tháng** |
| **Phiếu lương** (Payslip) | Danh sách từng phiếu, mở xem chi tiết |
| **Tổng hợp phiếu lương theo kỳ** | Kỳ lương: bao nhiêu phiếu đã phát hành, bao nhiêu người đã xem |
| **Chi tiết phiếu lương** (Payslip Detail) | Mọi khoản của mọi phiếu trong kỳ, mỗi khoản một cột — xem/xuất Excel |
| **Cấu trúc phiếu lương** (Payslip Structure) | Các khoản lương của phiếu (tên, mã, công thức in) theo từng kỳ — xem mục 2a |
| Mini App ▸ **Thông báo** | Gửi thông báo cho cả công ty hoặc một số nhân viên |
| Mini App ▸ **Yêu cầu liên kết** | Duyệt nhân viên chưa vào được app (SĐT Zalo không khớp hồ sơ) |
| Mini App ▸ **Tài khoản Zalo** | Gán SĐT, khoá / mở tài khoản Mini App |
| Mini App ▸ **Cài đặt Cổng nhân viên** | Cấu hình chung (ít khi sửa) |

Kỳ lương **tháng M** = từ ngày **26 tháng M−1** đến ngày **25 tháng M** (ví dụ kỳ 09/2026 = 26/08 → 25/09/2026).
Ngày trả lương mặc định: ngày **5 tháng sau** (05/10/2026).

---

## 2. Quy trình hằng tháng

### Bước 0 — Tháng này có đổi khoản lương không?
Không đổi gì → bỏ qua. Có thêm / bớt / đổi tên khoản hay đổi công thức in → làm **mục 2a** trước khi tải file mẫu.

### Bước 1 — Tải file mẫu
**Tải phiếu lương** → **Tải xuống mẫu** (Download Template) → để trống ô *Chỉ nhân viên nghỉ việc* → chọn **Kỳ lương**
→ **Download**.

File có sẵn mỗi nhân viên một dòng (STT, kỳ, từ ngày – đến ngày, mã NV, họ tên, chức danh, bộ phận…). File mẫu
**tự bỏ** những người sau:
- Nghỉ việc trước kỳ hoặc **trong kỳ**: người nghỉ trong kỳ được tính riêng, xem mục 3.
- Nghỉ thai sản trọn kỳ.
- Nhân viên trong danh sách *Exclude Employees* của Attendance Calculation Setting.

Nhân viên vào làm giữa kỳ: cột *Từ ngày* là ngày vào làm.

### Bước 2 — Điền số
- Mỗi khoản lương là **một cột**, đúng các khoản trong **Cấu trúc phiếu lương** của kỳ. Tiêu đề bắt đầu bằng **mã
  khoản** (`1.2 …`, `3.2 …`), giống phiếu giấy. Luôn tải file mẫu **của đúng kỳ** để có đúng cột.
- Cột **"1.2 Days"**, **"2.1 Hours"**… là **số ngày / số giờ** (công thực tế, giờ tăng ca…). Cột liền sau là **số tiền**.
- Ô trống = 0. Số tiền ghi số nguyên, không ghi "đ".
- **Không** đổi mã đầu tiêu đề. Phần chữ phía sau, thứ tự cột hay độ rộng cột thì sửa thoải mái.
- Cột **Pay Date** để trống = ngày 5 tháng sau.
- Cột **Note** (Ghi chú): ghi tùy ý cho cả phiếu, ví dụ lý do điều chỉnh lương tháng trước. Nhân viên thấy ghi chú
  ở cuối phiếu trên Mini App, và ở dòng *Remark/Ghi chú* cuối phiếu in. Để trống = không có ghi chú (tải file lên lại sẽ
  **xoá** ghi chú cũ nếu ô trống). Tối đa 1.000 ký tự.
- Cột *STT* và *Chức danh* chỉ để dễ nhìn, ERP không đọc lại.

### Bước 3 — Tải file lên và kiểm tra
**Tải lên Excel** (Upload Excel) → chọn file. ERP kiểm tra rồi hiện kết quả:
- **Lỗi** (đỏ): phải sửa trong Excel rồi tải lên lại. Ví dụ:
  - mã NV không có, một người xuất hiện 2 dòng, ô không phải số, ngày ngoài kỳ, kỳ đã phát hành;
  - thiếu cột *Kỳ lương*, kỳ chưa có **Cấu trúc phiếu lương**, cột có mã khoản không thuộc cấu trúc của kỳ (thường là
    nhầm file tháng khác), một file gồm nhiều kỳ thuộc các cấu trúc khác nhau;
  - **số vô lý**: số ngày / số giờ **âm** (mọi khoản); ở các khoản **công và tăng ca** (khối *Attendance*: 1.1, 1.2,
    2.1–2.3…) số ngày lớn hơn số ngày của kỳ hoặc số giờ lớn hơn 24 giờ × số ngày của kỳ; số tiền từ **100 tỷ** trở lên
    (gõ thừa chữ số). Số ngày của khoản khác (ví dụ 7.4 thanh toán phép năm khi nghỉ việc) được phép lớn hơn số ngày của kỳ.
- **Cảnh báo** (cam): vẫn nhập được sau khi tick *Tôi đã kiểm tra các cảnh báo ở trên*. Ví dụ: tên trong file khác ERP, thực lĩnh âm,
  nhân viên **đã nghỉ trước kỳ**, nhân viên **nghỉ giữa kỳ mà *Đến ngày* trong file trùng hoặc sau ngày nghỉ việc** (xem mục 3),
  và **"Sẽ ghi đè phiếu … đang có"**: nhân viên + kỳ đó đã có phiếu nháp / đã thu hồi (kèm lô và giờ nhập cũ; nếu Từ ngày /
  Đến ngày / Ngày trả lương khác thì hiện cả ngày cũ và ngày trong file). Đọc kỹ để không nhập nhầm file đè lên file khác.
- ⚠ Kiểm tra **số dòng** (ô "… rows") đúng bằng số nhân viên. Lỡ chọn **file mẫu chưa điền số** thì vẫn nhập được
  nhưng mọi phiếu sẽ = 0.

ERP **không kiểm công thức** và **không bao giờ tự sửa số** của C&B: số liệu do C&B quyết, ERP chỉ chặn những số
không thể đúng ở trên.

### Bước 4 — Nhập dạng Nháp
**Nhập dạng Nháp** (Import as Draft). Phiếu nháp **chưa** hiện cho nhân viên. File Excel tải lên được ERP xoá ngay sau
khi nhập, vì file chứa lương cả kỳ.

Kiểm tra lại trước khi phát hành:
- **Phiếu lương** → mở vài phiếu. Tab *General*: thực lĩnh, công chuẩn, công thực tế, giờ tăng ca, lương cơ bản, tổng,
  khấu trừ. Tab *Detail*: bảng toàn bộ khoản, giống phiếu giấy (phiếu nháp sửa số ngay trong bảng được, xem mục 4).
- **Tổng hợp phiếu lương theo kỳ** → chọn kỳ, lọc *Trạng thái = Bản nháp*.

### Bước 5 — Phát hành
**Tải phiếu lương** → bảng **2. Phát hành lên Mini App** → dòng của kỳ → **Phát hành** (Publish).
- Nhân viên **thấy phiếu ngay** trên Mini App.
- ERP tạo **1 thông báo** "Phiếu lương MM/YYYY đã được phát hành" cho các nhân viên có phiếu kỳ đó.

### Bước 6 — Theo dõi
**Tổng hợp phiếu lương theo kỳ** → ô **Kỳ lương** là danh sách chọn, chỉ có các kỳ **đã có phiếu**, mở report là tự chọn
kỳ mới nhất. Report hiện số **đã phát hành / đã xem / chưa xem / % đã xem** và tổng thực lĩnh. Bộ lọc *Đã xem* (Viewed)
chọn *Chưa xem* (Not Viewed) để biết ai chưa mở phiếu. Bảng hiện các khoản chính (lương cơ bản, tăng ca, tổng, khấu
trừ, thực lĩnh) và lúc xem lần đầu.

Cần **toàn bộ khoản** → report **Chi tiết phiếu lương** (Payslip Detail): chọn kỳ (cũng là danh sách chọn), lọc thêm
Trạng thái / Section / Group nếu cần → menu **⋯ → Export** → Excel. Mỗi khoản một cột theo cấu trúc của kỳ, dòng cuối là
tổng. File này **chỉ để kiểm tra**, không tải lên lại trang *Tải phiếu lương* được (thiếu cột Kỳ lương, có thêm cột
Payslip / Status).

---

## 2a. Tháng có thay đổi khoản lương — Cấu trúc phiếu lương

Các khoản trên phiếu (mã, tên tiếng Anh, tên tiếng Việt, chữ công thức in trong ngoặc) nằm ở **Cấu trúc phiếu lương**
(Payslip Structure). Mỗi bản áp dụng **từ kỳ** ghi ở *Valid From Period* cho tới bản kế tiếp. File mẫu, Mini App và
phiếu in đều theo bản của kỳ.

**Đổi từ kỳ 11/2026** (ví dụ):
1. Mở bản đang dùng (ví dụ `PSS-2026-09`) → menu **…** → **Duplicate**.
2. *Valid From Period* = **2026-11** (ô này để trống khi Duplicate, phải điền). ERP không cho chọn kỳ đã có phiếu của
   cấu trúc khác.
3. Sửa bảng *Lines*:
   - **Thêm khoản**: thêm dòng, điền *No.* (mã, ví dụ `3.11`), tên tiếng Anh, tên tiếng Việt; *Under Line* = dòng nhóm
     (ví dụ `3.1`, gõ mã là ERP tự gợi ý); khoản có số ngày/giờ thì chọn *Unit/ĐVT Column*.
   - **Bỏ khoản**: xoá dòng.
   - **Đổi tên**: sửa *English Label* / *Vietnamese Label*.
   - **Đổi công thức in**: sửa *Formula* (ví dụ `j=f-g+h+i+k`). Chữ này **chỉ để in**, ERP không tính hay kiểm.
4. **Lưu** → tải file mẫu kỳ 11 sẽ có đúng các cột mới.

- Phiếu các kỳ trước **giữ nguyên** khoản và tên cũ, cả trên app lẫn khi in lại.
- Một bản **đã có phiếu** (nháp, đã phát hành hay đã thu hồi) thì chỉ sửa được tên, chữ công thức và mô tả. Thêm / xoá
  dòng, đổi mã, đơn vị, *Under Line*, *Row Type*, *Block*, *Report Column*, *Valid From Period* → bấm Lưu sẽ bị báo lỗi.
  Cách làm:
  - đổi **từ kỳ sau**: Duplicate thành bản mới như trên;
  - đổi **ngay ở kỳ đã có phiếu**: **Thu hồi** kỳ → **Xoá phiếu** (Delete Payslips) của **mọi kỳ** đang dùng bản này →
    sửa bản → Lưu → tải file mẫu mới, nhập lại → Phát hành.
- **Chỉ đổi tên khoản** thì file Excel đã điền **vẫn nhập được**, không cần tải lại file mẫu: ERP nhận cột theo **mã**
  đầu tiêu đề, còn tên trên phiếu lấy từ cấu trúc. Chỉ khi **thêm / bớt khoản hoặc đổi mã** mới phải tải file mẫu mới.
- *Report Column*: dòng nào là lương cơ bản, tăng ca, tổng, khấu trừ, **thực lĩnh** (bắt buộc đúng 1 dòng), công chuẩn,
  công thực tế, giờ tăng ca — dùng cho danh sách phiếu và report. Duplicate thì đã có sẵn, chỉ cần giữ khi đổi mã.

**Sửa lỗi chính tả tên khoản của phiếu đã phát hành** (không đổi số):
1. Mở cấu trúc của kỳ đó → sửa tên → **Lưu**.
2. Bấm **Apply Labels to Payslips** → xem danh sách thay đổi → **Yes**.
- Số tiền, ngày phát hành **không đổi**, **không** gửi thông báo. Phiếu in lại sẽ có tên mới.
- Điện thoại nào đã mở phiếu trước đó có thể vẫn hiện tên cũ cho tới khi app được cập nhật.

---

## 3. Nhân viên nghỉ việc — tính và trả riêng

Nhân viên nghỉ việc được thanh toán **trong 14 ngày kể từ ngày nghỉ**, không chờ ngày 5 tháng sau.
1. **Tải xuống mẫu** → tick **Chỉ nhân viên nghỉ việc** → chọn **Kỳ lương** → ô **Ngày nghỉ việc từ – đến** tự điền cả kỳ,
   thu hẹp lại nếu cần (phải nằm trong kỳ đã chọn) → Download.
   - Mọi người trong file đều thuộc kỳ đã chọn.
   - *Đến ngày* = ngày trước ngày nghỉ việc.
   - *Pay Date* điền sẵn = ngày nghỉ + 14, sửa được.
   - Người nghỉ **đúng ngày 26** (làm tới hết ngày 25, đủ kỳ) **không** có trong file này: họ nằm ở file lương tháng và
     nhận lương cùng đợt ngày 5 (vẫn trong hạn 14 ngày).
2. Điền số → tải lên → nhập nháp như hằng tháng.
3. **Phát hành** kỳ đó: phiếu nghỉ việc (cột *Thanh toán nghỉ việc*) phát hành **không có thông báo**. C&B tự nhắn
   cho người nghỉ. Họ vẫn xem được phiếu trên Mini App trong **30 ngày** sau ngày nghỉ.

Khi phát hành phiếu tháng của cùng kỳ sau đó, thông báo chung vẫn được tạo như bình thường.

⚠ **Tải file tháng trước khi nhập ngày nghỉ việc**: người nghỉ giữa kỳ vẫn nằm trong file tháng với *Đến ngày* = 25.
Khi tải lên, ERP cảnh báo *"Employee left on … (last working day …), but Period To in the file is …"*. Đừng tick bỏ qua:
xoá dòng đó khỏi file tháng và tính cho người này bằng file **Chỉ nhân viên nghỉ việc**. Nếu vẫn muốn để trong file tháng thì
sửa *Đến ngày* thành ngày trước ngày nghỉ việc, hoặc để trống ô này (ERP tự điền).

---

## 4. Sửa phiếu sai

| Tình huống | Làm gì |
|---|---|
| Phiếu **nháp** sai | Sửa Excel → tải lên lại: phiếu nháp cùng nhân viên + kỳ được **ghi đè** (ERP cảnh báo từng dòng, tick xác nhận rồi mới nhập) |
| Nhập nhầm cả kỳ, hoặc muốn làm lại cả kỳ đã thu hồi | **Xoá phiếu** (Delete Payslips) ở dòng kỳ đó: xoá **mọi** phiếu nháp và phiếu đã thu hồi của kỳ, rồi nhập lại. Phiếu đang phát hành không bị xoá — thu hồi trước. ERP báo trước số phiếu đã thu hồi và số nhân viên đã từng xem |
| Phiếu **đã phát hành** sai | **Thu hồi** (Withdraw) kỳ → nhân viên không thấy nữa → sửa Excel, tải lên lại (ghi đè) → **Phát hành** lại. Muốn làm lại sạch từ đầu: Thu hồi → **Xoá phiếu** → nhập lại |

- Phiếu **nháp** sai vài số: mở phiếu → tab *Detail* → sửa số trong bảng → Lưu (ERP vẫn chặn số vô lý).
- Phiếu đã phát hành **không sửa trực tiếp** được: phải thu hồi trước, để tránh nhân viên đã xem một số rồi số bị đổi.
  Chỉ **tên khoản** sai chính tả thì dùng *Apply Labels to Payslips* (mục 2a), không cần thu hồi.
- Thu hồi sẽ xoá luôn thông báo của kỳ. Phát hành lại sẽ tạo thông báo mới.
- Kỳ nhiều phiếu (trên 150) thì **Xoá phiếu** chạy nền, xong ERP báo và tự làm mới bảng. Phiếu đã xoá vẫn được ERP giữ
  bản sao (*Deleted Document*) — lỡ xoá nhầm thì báo IT khôi phục.

---

## 5. In phiếu lương ra giấy

Khi cần đưa phiếu giấy cho người lao động:
- **Một phiếu**: mở phiếu → nút **Download PDF** → tải về file PDF khổ A4.
- **Nhiều phiếu / cả kỳ lương**: danh sách **Phiếu lương** → nút **Download PDF** → hộp thoại:
  - **Payslips**: *Ticked payslips* = các phiếu đã tick (mặc định khi có tick), hoặc *By pay period / employee* = theo bộ lọc:
    - **Pay Period**: kỳ lương. Bỏ trống thì lấy **mọi kỳ** của các nhân viên chọn ở ô dưới (ví dụ in toàn bộ phiếu của
      một người khi họ cần).
    - Lọc theo **một trong ba** (chọn ô này thì hai ô kia tự xoá; bỏ trống cả ba = mọi người):
      - **Employees**: một hoặc nhiều nhân viên. Danh sách gợi ý **không có** người trong *Exclude Employees* (Attendance
        Calculation Setting) và người **nghỉ trước kỳ** đã chọn.
      - **Sections**: một hoặc nhiều bộ phận.
      - **Group**: một tổ.
    - Phải chọn ít nhất Pay Period hoặc Employees.
    - **Status**: mặc định *Published* = phiếu đã phát hành.
  - **Output**: **ZIP - one PDF per payslip** (mặc định, mỗi người một file PDF) hoặc **One combined PDF** (tất cả phiếu
    trong **một file PDF**, mỗi người một trang — mở ra bấm in một lần là xong). Chỉ 1 phiếu thì luôn ra 1 file PDF.

  Cả kỳ (khoảng 1.000 phiếu) mất khoảng **2 phút** (có thanh tiến độ), xong thì tự tải về; trong lúc chờ đừng đóng trang.
  Phiếu được xếp theo **Section → Group → Mã NV** để in xong phát theo bộ phận cho tiện.
- Tên file: `Kỳ_Section_Group_Mã NV_Họ tên.pdf`, ví dụ `2026-09_HR-GA_IT_TIQN-0148_Nguyễn Thái Sơn.pdf`.
- Số trên phiếu in theo kiểu Việt Nam: dấu chấm ngăn hàng nghìn, dấu phẩy ngăn số lẻ (`17.214.001`, `24,5` giờ). Chỉ
  dòng **Thực lĩnh** ghi đơn vị "VNĐ" ở cột ĐVT; các dòng tiền khác không ghi đơn vị.
- Muốn in khổ **A5**: chọn khổ A5 trong hộp thoại in của máy in (tự thu nhỏ vừa trang).
- Phiếu **chưa phát hành** (nháp / đã thu hồi) in ra có chữ chìm **"BẢN NHÁP / DRAFT"**, chỉ để kiểm tra, **không**
  phát cho người lao động.
- Mỗi lần in được ghi lại ở phần lịch sử cuối phiếu ("Printed PDF").

## 6. Gửi thông báo khác

Mini App ▸ **Thông báo** → **Thêm mới**:
- **Đối tượng**: *Tất cả* (cả công ty), hoặc *Nhân viên* rồi chọn từng người ở ô bên dưới.
- **Loại** *GENERAL*, nhập **Tiêu đề** và **Nội dung** → Lưu. Nhân viên thấy ngay trên Mini App.
- Xoá thông báo = nhân viên không thấy nữa. Thông báo **không** gửi qua Zalo / email, chỉ hiện trong app.

---

## 7. Nhân viên chưa vào được app

App so **SĐT Zalo** của nhân viên với ô **Mobile Phone** trên hồ sơ nhân viên, không khớp thì so tiếp ô **Mobile Zalo Phone**.

### 7.1 Yêu cầu liên kết (cách thường gặp)
Nhân viên bị báo "chưa tìm thấy hồ sơ" sẽ nhập **mã NV + họ tên** trên app → hiện ở Mini App ▸ **Yêu cầu liên kết**.
1. Mở yêu cầu, xem khung cam **Kiểm tra trước khi duyệt** và ô **Khớp tên**.
2. 🔴 **Gọi lại số ở ô SĐT Zalo** để chắc đúng là nhân viên đó. Mã NV và họ tên ai cũng biết, nên người khác có thể
   giả để xem trộm lương.
3. **Phê duyệt** (Approve): SĐT Zalo được ghi vào ô *Mobile Zalo Phone* của hồ sơ, nhân viên mở lại app là vào được.
   **Từ chối** (Reject): nhập lý do, nhân viên thấy lý do trên app và gửi lại được.
- Không duyệt được nếu SĐT đó đang là SĐT của nhân viên khác. Nhân viên đã có SĐT Zalo cũ thì duyệt sẽ thay số cũ.
- App chỉ nhận yêu cầu khi **mã NV và họ tên khớp** hồ sơ (không phân biệt dấu, hoa/thường). Vì vậy ô **Khớp tên**
  gần như luôn được tick, nhưng **vẫn phải gọi lại SĐT Zalo**, vì mã và tên của đồng nghiệp ai cũng có thể biết.
- **Mã yêu cầu chính là SĐT Zalo** của người gửi, nên có thể tìm theo SĐT ở danh sách.
- Phiếu hiện **tên và ảnh đại diện Zalo** của người gửi (lấy thẳng từ Zalo) để đối chiếu thêm. Trống nếu người đó chưa
  cho app xem hồ sơ Zalo.
- Nhân viên gõ nhầm mã sang người khác thì C&B **sửa ô Nhân viên** ngay trên yêu cầu (chỉ khi còn *Chờ duyệt*) → Lưu,
  rồi xem lại khung cảnh báo trước khi duyệt.
- Mỗi tài khoản Zalo chỉ có **1 yêu cầu**. Nhân viên gửi lại (kể cả khi đang chờ duyệt, để sửa chỗ gõ nhầm) thì
  nội dung mới **ghi đè** nội dung cũ và yêu cầu quay về *Chờ duyệt*. Nội dung cũ xem ở phần lịch sử cuối phiếu.
- Tối đa **2 lần/ngày**. Ô **Số lần yêu cầu** (tổng), **Yêu cầu hôm nay** và **Lần yêu cầu gần nhất** hiện trên phiếu;
  nhân viên cũng thấy số lần còn lại trên app.
- Nhân viên **đã có tài khoản Zalo đang dùng** thì app không cho gửi yêu cầu cho mã đó, và nút Phê duyệt cũng bị chặn.
  Nếu tài khoản cũ không còn dùng (đổi điện thoại, đổi Zalo): mở **Tài khoản Zalo** cũ → tick **Đã tắt** → Lưu, rồi
  mới duyệt.

### 7.2 Nhân viên không cho app đọc SĐT
App hiện **Zalo User ID**, nhân viên gửi mã này cho C&B. Mini App ▸ **Tài khoản Zalo** → tìm theo *Zalo User ID* →
nhập SĐT có trong hồ sơ của nhân viên → Lưu. ERP chặn số không khớp nhân viên nào.

### 7.3 Khoá tài khoản
**Tài khoản Zalo** → tick **Đã tắt** (Disabled), nhập lời nhắn → Lưu: nhân viên bị đăng xuất ngay. Người nghỉ việc quá
30 ngày, hoặc người ngoài công ty, bị ERP tự khoá, không cần làm gì.

---

## 8. Cài đặt Cổng nhân viên

Thường **không cần sửa**. Các mục C&B hay dùng:

| Tab | Mục | Ý nghĩa |
|---|---|---|
| Tính năng Mini App | **Ngày trả lương trong tháng** | Mặc định 5 |
| | **Mặc định hiện dòng 0đ** | Tick = khi mở phiếu, app hiện cả khoản 0đ như phiếu giấy; bỏ tick = ẩn khoản 0đ. Nhân viên vẫn bấm "Ẩn khoản 0đ" để đổi. Có hiệu lực từ bản Mini App cập nhật sau (bản hiện tại luôn hiện đủ) |
| Zalo OA & Chat | **ID chat C&B (ID by OA)** + tên | Nút "Chat với C&B" trên app mở chat Zalo với người này. Lấy ID ở *Tài khoản Zalo* của người đó (sau khi họ mở app) |
| Access | Hạn chỉ xem sau nghỉ việc | Mặc định 30 ngày |
| | **Zalo App Review** | Tick **Enable Review Mode**, điền SĐT reviewer Zalo đưa (mỗi dòng 1 số). Reviewer chỉ thấy **dữ liệu mẫu**: NV "Nguyễn Văn Mẫu", **3 phiếu lương mẫu** của 3 kỳ gần nhất (tự cập nhật theo tháng), thông báo mẫu — không bao giờ thấy dữ liệu thật. 🔴 Zalo **kiểm tra lại mỗi lần phát hành bản app mới**, nên **giữ bật** (không ảnh hưởng nhân viên). SĐT của nhân viên thật luôn vào bằng hồ sơ thật dù có trong danh sách |

### Tên từng khoản trên app
Từ 28/10/2026 tên khoản (tiếng Việt trên app, tiếng Anh trên phiếu in) sửa ở **Cấu trúc phiếu lương** (mục 2a), không
còn ở Cài đặt.

---

## 9. Câu hỏi thường gặp

**Nhân viên báo không thấy phiếu?** Kiểm tra theo thứ tự:
- phiếu đã **Phát hành** chưa (nháp thì nhân viên không thấy);
- đúng kỳ chưa;
- nhân viên vào được app chưa (mục 7).

**Biết ai đã xem phiếu?** Report *Tổng hợp phiếu lương theo kỳ*, hoặc cột *Xem lần đầu lúc* trên từng phiếu.

**Lỡ phát hành nhầm?** **Thu hồi** ngay (mục 4). Nhân viên đã xem thì vẫn còn ghi *Xem lần đầu lúc*.

**Cảnh báo đỏ "No Payslip Structure covers period…" ở trang Tải phiếu lương?** Kỳ sắp tính chưa có cấu trúc phiếu
lương áp dụng → tạo theo mục 2a.

**Có cần dùng Data Import của ERP không?** Không (đã tắt). Luôn nhập qua **Tải phiếu lương**, vì ở đó ERP kiểm tra lỗi
và gắn đúng cấu trúc của kỳ.

**Muốn kiểm tra lại số đã nhập?** Report **Chi tiết phiếu lương** → chọn kỳ → Export Excel (mục 2, bước 6). Sửa số thì
sửa trên file gốc rồi tải lên lại (phiếu nháp / đã thu hồi được ghi đè), hoặc sửa từng phiếu nháp ở tab *Detail*.

**Đổi tên khoản trong Cấu trúc phiếu lương có phải tải lại file Excel?** Không — ERP nhận cột theo mã (mục 2a). Phiếu
đã nhập trước đó vẫn giữ tên cũ cho tới khi bấm **Apply Labels to Payslips**.

---

## 10. Lưu ý bảo mật

- Chỉ phê duyệt *Yêu cầu liên kết* sau khi **đã gọi xác nhận** đúng người.
- Đừng chia sẻ tài khoản ERP có role CnB.
