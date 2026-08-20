# Mục lục tài liệu toàn app

> **Mục đích:** Danh sách mọi tài liệu .md của app, chia theo chủ đề, để duyệt tìm tài liệu cần đọc.
> **Phạm vi:** Tài liệu cho developer
> **Trạng thái:** Đang chạy · **Cập nhật:** 2026-08-20


Bài này là **file chỉ mục**: nó chỉ chứa đường dẫn tới tài liệu nằm rải rác trong app. Trang tự
đọc từng đường dẫn, lấy tiêu đề thật trong file, hiện thành danh sách bấm được ở panel trái —
mỗi đường dẫn in trong bài cũng bấm thẳng được để mở nội dung.

Ô tìm kiếm ở panel trái quét **toàn bộ** `.md` của app theo tên, tiêu đề và nội dung (gõ không
dấu vẫn ra), nên không cần file có mặt trong bài này mới tìm được. Bài này để **duyệt theo chủ
đề**; tìm kiếm để **tra nhanh**.

Thêm tài liệu: viết đường dẫn `.md` vào bài, tương đối từ thư mục app
(`apps/customize_erpnext/customize_erpnext/`) hoặc đường dẫn tuyệt đối. Chỉ đọc được file nằm
trong app này.


## Chấm công, ca làm việc

- `overrides/shift_type/OPTIMIZATION_GUIDE.md` — Bulk Attendance Processing — Architecture & Logic Guide
- `overrides/shift_type/QUICK_REFERENCE.md` — Bulk Attendance — Quick Reference
- `overrides/employee_checkin/employee_checkin.md` — Employee Checkin Override — tính giờ công và giờ tăng ca
- `overrides/shift_attendance/shift_attendance.md` — Override `Shift Attendance` + mã nghỉ phép trên bảng công
- `overrides/attendance_request/attendance_request.md` — Attendance Request — bổ sung giờ check in/out
- `overrides/override_attendance_shift_checkin.md` — Attendance, Shift & Check-in Override Documentation
- `customize_erpnext/report/shift_attendance_customize/shift_attendance_customize.md` — Shift Attendance Customize
- `overrides/shift_type/LEGACY_APP_TIMESHEET_ALGORITHM.md` — [LEGACY APP] Timesheet Algorithm — `timesheetFunctions.dart`
- `customize_erpnext/patches/v1_0/patch_daily_timesheet_migration.md` — Daily Timesheet Migration Patch
- `docs/attendance_request_supplement_plan.md` — Attendance Request — Bổ sung giờ check in/out (Plan)
- `docs/daily_attendance_dashboard_plan.md` — Daily Attendance — Dashboard + Email

## Nghỉ phép

- `overrides/leave_application/QUY_DINH_NGHI_PHEP_2025.md` — Quy định nghỉ phép TIQN — TB-TIQN/2025-0018
- `overrides/leave_application/leave_application_override.md` — Leave Application Override
- `overrides/earned_leave/earned_leave_override.md` — Earned Leave Override — phép năm theo Bộ luật Lao động 2019
- `overrides/leave_control_panel/leave_control_panel.md` — Leave Control Panel — chọn nhân viên nào để cấp phép?
- `overrides/leave_reports/leave_reports.md` — Override 2 report số dư phép — chỉ phép năm, tính trong bộ nhớ
- `overrides/leave_application/leave_summary_doc.md` — leave summary doc
- `overrides/leave_application/PLAN_LEAVE_OVERRIDE.md` — Plan — Rà soát & sửa override Nghỉ phép
- `overrides/leave_application/PLAN_IMPORT_AL_2026.md` — Plan — Import dữ liệu nghỉ phép 2026 của HR (`AL_data.xlsx`)

## Tiền lương

- `overrides/payroll_docs/payroll_docs.md` — payroll_docs — thư mục chính thức cho phần Lương
- `overrides/payroll_docs/PAYROLL_SETUP.md` — Tính lương TIQN trên ERPNext — tài liệu thi công
- `overrides/payroll_docs/QUY_CHE_LUONG_2025.md` — Quy chế Tiền lương, Tiền thưởng, Phúc lợi 2025 — TIQN
- `overrides/payroll_docs/PLAN_PAYROLL_SETTINGS.md` — Plan — `TIQN Payroll Settings`: gom hằng số lương vào một chỗ
- `overrides/payroll_docs/PLAN_ATTENDANCE_VS_QUYCHE.md` — Plan — Đối chiếu module chấm công custom với Quy chế lương
- `overrides/payroll_docs/PLAN_EMPLOYEE_DEPENDENT.md` — Plan — DocType quản lý Người phụ thuộc (`Employee Dependent`)

## Tăng ca

- `customize_erpnext/doctype/overtime_registration/overtime_registration.md` — Overtime Registration - Tài liệu

## Hồ sơ nhân viên

- `customize_erpnext/doctype/employee_maternity/employee_maternity.md` — Employee Maternity
- `customize_erpnext/doctype/labor_contract/labor_contract.md` — Labor Contract
- `www/employee-photos/employee-photos.md` — Employee Photos — Tài liệu kỹ thuật
- `public/js/custom_scripts/employee_photos.md` — Tính năng Chụp & Upload Ảnh Nhân viên
- `www/employee-self-update/employee-self-update.md` — Employee Self Update — Tài liệu kỹ thuật
- `www/employee-self-update-info/employee-self-update-info.md` — Employee Self Update Info — Tài liệu kỹ thuật
- `www/employee-self-update/plan_PaddleOCR_VietOCR_CCCD.md` — Kế hoạch tích hợp PaddleOCR + VietOCR để đọc ảnh CCCD

## Kho, sản xuất, in ấn

- `overrides/item_stock_customize.md` — Item & Stock Customizations — TIQN ERPNext
- `overrides/item_stock_customize_guide.md` — Hướng dẫn sử dụng — Quản lý kho hàng TIQN
- `customize_erpnext/report/stock_balance_customize/Stock Balance Customize Report.md` — Stock Balance Customize Report - Refactored
- `customize_erpnext/report/stock_ledger_customize/Stock Ledger Customize Report.md` — Stock Ledger Customize Report
- `customize_erpnext/doctype/packing_list/packing_list.md` — Packing List — Module Documentation
- `customize_erpnext/print_format/stock_entry_material/stock_entry_material.md` — Print Format: Stock Entry Material
- `fixtures/split_print_format.md` — Print Format Split Tool

## Module khác

- `uniform_control/HUONG_DAN_SU_DUNG.md` — Uniform Control — Hướng dẫn sử dụng
- `health_check_up/health_check_up.md` — Health Check Up — Review Module (2026-07-11) + Fix toàn bộ (2026-07-12)
- `health_check_up/page/health_check_up_management/health_check_up_management.md` — Health Check Up Management — Tài liệu kỹ thuật
- `health_check_up/page/health_check_up_management/document_for_user.md` — Hướng Dẫn Sử Dụng Phầm Mềm Quản Lý Khám Sức Khỏe
- `www/jobs/jobs.md` — Job Portal Customizations
- `frontend/src/pages/shoe_rack_layout_manager.md` — Shoe Rack Layout Manager — Review & Tài liệu logic
- `network/doctype/cctv_tracking/cctv_tracking.md` — CCTV Tracking — Tài liệu kỹ thuật

## Thiết bị chấm công, đồng bộ

- `www/biometric_sync/biometric_sync.md` — Biometric Sync — `/biometric_sync`
- `public/js/sync_fingerprint.md` — Tài Liệu Sync Fingerprint - Đồng Bộ Vân Tay

## Sơ đồ và tài liệu về tài liệu

- `docs/flowchart/payroll.md` — Flowchart — Toàn bộ luồng chấm công, tính lương TIQN
- `docs/mindmap_guide.md` — Hướng dẫn bộ sơ đồ mindmap — Sơ đồ chức năng hệ thống / System Functional Mindmaps
- `docs/user_manual/dev-tool.md` — Hướng dẫn dùng trang Dev Tool
- `docs/user_manual/Attendance Request.md` — Attendance Request — bổ sung giờ check in/out

## Nhập liệu hàng loạt

- `api/bulk_update_scripts/create_material_issue_template.md` — Hướng dẫn Import Material Issue Stock Entry
- `api/bulk_update_scripts/create_material_receipt_template.md` — Hướng dẫn Import Material Receipt Stock Entry

## Hạ tầng, công cụ nội bộ

- `api/site_restriction.md` — Site Restriction Module
- `api/vn_address/vn_address.md` — VN Address — Cơ sở dữ liệu địa giới hành chính Việt Nam
- `overrides/monkey_patch.md` — Monkey Patch Overrides — Hướng dẫn
- `workspace_setup.md` — Workspace Setup — thêm link của app vào Workspace HRMS

---

## Không nằm trong mục lục

| Chỗ | Vì sao |
|---|---|
| `docs/mindmap/*.md` | Do `scripts/build_mindmap.py` sinh ra, trang `/mindmap` có parser riêng — chèn tiêu đề vào là hỏng sơ đồ |
| `docs/archive/*.md` | Prompt đặt hàng lúc xây chức năng, giữ để tra chứ không phải tài liệu vận hành |
| `frontend/README.md` | Bản mẫu mặc định của Create React App |
| `frontend/node_modules/`, `*/pyzk-master/` | Thư viện ngoài |

Vẫn tìm được bằng ô tìm kiếm — chỉ là không liệt kê ở đây.

