"""Dựng Salary Slip tạm (không lưu, rollback) cho mọi NV có Salary Structure Assignment để so trước/sau update.

    cd ~/frappe-bench/sites && ../env/bin/python -c "import frappe, sys; frappe.init(site='erp.tiqn.local', sites_path='.'); frappe.connect(); \
        sys.path.insert(0, '../apps/customize_erpnext/customize_erpnext/scripts/upgrade_checks'); import salary_baseline; salary_baseline.run('/tmp/before.json')"
Chạy 1 lần TRƯỚC update, 1 lần SAU, so 2 file JSON: phải giống hệt (17/10/2026: 72/72).
"""
import json, frappe
PERIODS = [("2026-01-26", "2026-02-25"), ("2026-04-26", "2026-05-25"), ("2026-07-26", "2026-08-25"), ("2026-08-26", "2026-09-25")]
FIELDS = ["total_working_days", "payment_days", "absent_days", "leave_without_pay", "gross_pay", "total_deduction", "net_pay"]
def run(out_path):
    emps = frappe.get_all("Salary Structure Assignment", filters={"docstatus": 1}, pluck="employee", distinct=True)
    result = {}
    for emp in sorted(emps):
        for s, e in PERIODS:
            key = f"{emp}|{s}"
            try:
                ss = frappe.get_doc({"doctype": "Salary Slip", "employee": emp, "start_date": s, "end_date": e,
                                     "posting_date": e, "payroll_frequency": "Monthly"})
                ss.get_emp_and_working_day_details()
                result[key] = {f: float(ss.get(f) or 0) for f in FIELDS}
            except Exception as ex:
                result[key] = {"error": f"{type(ex).__name__}: {str(ex)[:120]}"}
            frappe.clear_messages()
    frappe.db.rollback()
    json.dump(result, open(out_path, "w"), indent=1, sort_keys=True)
    ok = sum(1 for v in result.values() if "error" not in v)
    print(f"{ok}/{len(result)} slips computed -> {out_path}")
    errs = {}
    for k, v in result.items():
        if "error" in v: errs.setdefault(v["error"], []).append(k)
    for m, ks in errs.items(): print(f"  {len(ks)}x {m}  e.g. {ks[0]}")
