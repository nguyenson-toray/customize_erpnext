# docs/flowchart

Sơ đồ luồng chứng từ, để người quản lý nhìn ra hệ thống chạy thế nào.

| File | Nội dung |
| --- | --- |
| [erpnext.md](erpnext.md) + `erpnext.drawio` | ERPNext v16: bán hàng, kho, mua hàng, sản xuất, tài sản, kế toán |
| [hrms.md](hrms.md) + `hrms.drawio` | HRMS v16: tuyển dụng, hồ sơ, chấm công, nghỉ phép, lương, tạm ứng |
| [attendance.md](attendance.md) | Chấm công TIQN: từ checkin đến Attendance và các báo cáo đọc từ Attendance (không gồm lương) |
| `employee.md`, `payroll.md` | ghi chú nghiệp vụ rời, không phải sơ đồ |

Hai file `.drawio` do script sinh ra, mở bằng [draw.io](https://app.diagrams.net)
hoặc extension Draw.io Integration của VS Code:

```
python3 scripts/build_erpnext_flowchart.py          # sinh lại erpnext.drawio + erpnext.md
python3 scripts/build_hrms_flowchart.py             # sinh lại hrms.drawio + hrms.md
python3 scripts/build_<app>_flowchart.py --check    # chỉ grep đối chiếu source, không ghi đè
```

Mỗi mũi tên đều kèm một chỗ trong source ERPNext / HRMS đang cài để chứng minh;
`--check` grep lại toàn bộ và báo cái nào mất bằng chứng (chạy sau mỗi lần nâng
version app). Script từ chối ghi đè file `.drawio` đã sửa tay — muốn ghi đè thì
thêm `--force`.

Phần chức năng đã custom riêng cho TIQN không nằm ở đây, xem `docs/mindmap/`.
