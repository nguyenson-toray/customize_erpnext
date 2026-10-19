# upgrade_checks — kiểm tra rủi ro trước/sau khi update frappe / erpnext / hrms

Dùng ở lần update 17/10/2026 (frappe v16.33 → v16.52, erpnext v16.32 → v16.51.1, hrms v16.16 → v16.51).
Quy trình đầy đủ: skill `erpnext-frappe` → `references/upgrade-playbook.md`.

| Script | Khi nào | Bắt được gì |
|---|---|---|
| `scan_imports.py` | TRƯỚC merge | import của app sẽ gãy ở ref đích |
| `scan_overridden_changed.py` + `func_diff.py` | TRƯỚC merge | hàm upstream mà mình override bị đổi chữ ký / thân |
| `salary_baseline.py` | TRƯỚC và SAU | phiếu lương tính lại có đổi không |
| `../check_integrity.py` | SAU migrate | link chết (workspace/sidebar), custom field/property setter mồ côi, hooks không resolve, report/page/controller lỗi |
| `../test_navigation.py` | SAU migrate | trang TIQN mở đúng sidebar, icon, dock |
