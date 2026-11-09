"""Manual test of the simplified Uniform Control (09/11/2026).

    bench --site erp.tiqn.local execute customize_erpnext.uniform_control.test_uniform_simplify.run

Runs against real data inside ONE transaction and rolls everything back at the
end (stock receipt, allocation, profiles, patch). Sends no email, contacts no
device. Prints PASS/FAIL per check and a summary.
"""
import time

import frappe
from frappe.utils import add_days, cint, getdate, today

RESULTS = []


def check(label, cond, detail=""):
    RESULTS.append((bool(cond), label))
    print(("PASS " if cond else "FAIL ") + label + (f" — {detail}" if detail else ""))


def run():
    frappe.flags.mute_emails = True
    try:
        _run()
    finally:
        frappe.db.rollback()
        frappe.flags.mute_emails = False
        passed = sum(1 for ok, _l in RESULTS if ok)
        print(f"\n{passed}/{len(RESULTS)} passed — rolled back")


def _old_rules_by_category(emp, rules, priority):
    """The pre-09/11 resolver: tie-break by Priority, then name."""
    from customize_erpnext.uniform_control.utils import _rule_match_rank
    best = {}
    for r in rules:
        if not r.item or not r.category:
            continue
        rank = _rule_match_rank(r, emp)
        if rank is None:
            continue
        key = (rank, cint(priority.get(r.name)), r.name)
        if r.category not in best or key > best[r.category][0]:
            best[r.category] = (key, r)
    return {c: v[1].name for c, v in best.items()}


def _run():
    from customize_erpnext.uniform_control import utils
    from customize_erpnext.uniform_control.api import uniform_api, forecast
    from customize_erpnext.uniform_control.report.uniform_tracking import uniform_tracking
    from customize_erpnext.uniform_control.report.uniform_assignment_preview import uniform_assignment_preview

    prefix = utils.get_employee_id_prefix()
    like = f"{prefix}%"
    warehouse = utils.get_uniform_warehouse()

    # ── 1. Priority removed: same winner for every Active employee ──
    rules = utils.load_active_rules()
    priority = dict(frappe.db.sql("select name, priority from `tabUniform Rule`"))
    emps = frappe.get_all("Employee", filters={"status": "Active", "name": ["like", like]},
                          fields=utils.EMPLOYEE_FIELDS)
    diff = [e.name for e in emps
            if {c: r.name for c, r in utils.get_rules_by_category(e).items()}
            != _old_rules_by_category(e, rules, priority)]
    check("1 dropping Priority changes no employee's rule", not diff, f"{len(emps)} employees, diff {diff[:5]}")

    # ── 2. Sizes from the Employee ──
    check("2a shirt XL → attribute Xl", utils.size_value({"custom_shirt_size": "XL"}, "Shirt Size") == "Xl")
    check("2b no shoe size → Free Size", utils.size_value({}, "Shoe Size") == "Free Size")
    v, err = utils.get_variant_for_sizes("Dép", {}, None, "Shoe Size")
    check("2c Dép without size → Dép Free Size", v == "Dép Free Size", f"{v} {err}")
    v, err = utils.get_variant_for_sizes("Áo thun nữ", {"custom_shirt_size": "XL"}, None, "Shirt Size")
    check("2d Áo thun nữ XL → its Xl variant", bool(v) and not err, f"{v} {err}")
    v, err = utils.get_variant_for_sizes("Dép", {"custom_shoe_size": "6-7"}, None, "Shoe Size")
    check("2e Dép 6-7 before the variant exists → clear error", not v and "6-7" in (err or ""), err)

    # ── 3. Manual Override semantics ──
    rule = frappe._dict(item="RULE-ITEM")
    check("3a no profile → rule item", utils.chosen_item(None, "Shirt", rule) == "RULE-ITEM")
    check("3b unticked → rule item", utils.chosen_item({"manual_override": 0, "shirt_item": "X"}, "Shirt", rule) == "RULE-ITEM")
    check("3c ticked + value → HR pick", utils.chosen_item({"manual_override": 1, "shirt_item": "X"}, "Shirt", rule) == "X")
    check("3d ticked + blank → rule item", utils.chosen_item({"manual_override": 1, "shirt_item": None}, "Shirt", rule) == "RULE-ITEM")
    check("3e Shoe never overridden", utils.chosen_item({"manual_override": 1, "shirt_item": "X"}, "Shoe", rule) == "RULE-ITEM")

    # ── 4. Data patch ──
    from customize_erpnext.patches import uniform_manual_override_from_assignments as patch
    patch.execute()
    ticked = frappe.db.count("Employee Uniform Profile", {"manual_override": 1, "employee": ["like", like]})
    check("4a patch ticked the profiles that differ from the rules", 150 <= ticked <= 230, f"{ticked} ticked")
    before = frappe.db.sql("select name, manual_override, shirt_item, cap_item from `tabEmployee Uniform Profile`")
    patch.execute()
    after = frappe.db.sql("select name, manual_override, shirt_item, cap_item from `tabEmployee Uniform Profile`")
    check("4b patch is idempotent", before == after)

    # ── 5. refresh_tracking ──
    t = time.time()
    res = utils.refresh_tracking()
    secs = time.time() - t
    check("5a refresh_tracking runs", res["profiles"] > 2000, f"{res} in {secs:.1f}s")
    res2 = utils.refresh_tracking()
    check("5b second refresh changes nothing", res2["assignments_synced"] == 0 and res2["rows_updated"] == 0, str(res2))
    bad = frappe.db.sql(
        """select count(*) from `tabEmployee Uniform Item` eui
        join `tabEmployee Uniform Profile` p on p.name = eui.parent
        where p.employee like %s and eui.status != (case
            when eui.last_issue_date is null then 'Not Issued'
            when eui.next_due_date is null then 'Active'
            when eui.next_due_date < %s then 'Overdue'
            when datediff(eui.next_due_date, %s) <= %s then 'Due Soon' else 'Active' end)""",
        (like, today(), today(), utils.get_reminder_days()))[0][0]
    check("5c stored status matches the dates", bad == 0, f"{bad} rows off")

    # ── 6. sync_profile_copies / ensure_profiles ──
    stale = lambda: frappe.db.sql(  # noqa: E731
        """select count(*) from `tabEmployee Uniform Profile` p join tabEmployee e on e.name = p.employee
        where not (p.employment_status <=> e.status and p.shirt_size <=> e.custom_shirt_size
                   and p.shoe_size <=> e.custom_shoe_size and p.`group` <=> e.custom_group)""")[0][0]
    n_before = stale()
    utils.sync_profile_copies()
    check("6a profile copies refreshed from the Employee", stale() == 0, f"{n_before} stale before")
    missing = frappe.db.sql(
        """select count(*) from tabEmployee e where e.status = 'Active' and e.name like %s
        and not exists (select 1 from `tabEmployee Uniform Profile` p where p.employee = e.name)""", like)[0][0]
    conflicts = frappe.db.sql(
        """select count(*) from tabEmployee e join `tabEmployee Uniform Profile` p on p.name = e.name
        where e.status = 'Active' and e.name like %s and p.employee != e.name
        and not exists (select 1 from `tabEmployee Uniform Profile` x where x.employee = e.name)""", like)[0][0]
    created = utils.ensure_profiles()
    still = frappe.db.sql(
        """select count(*) from tabEmployee e where e.status = 'Active' and e.name like %s
        and not exists (select 1 from `tabEmployee Uniform Profile` p where p.employee = e.name)""", like)[0][0]
    check("6b ensure_profiles creates all but the name conflicts", created + conflicts == missing and still == conflicts,
          f"{missing} missing, {created} created, {conflicts} name conflicts left (renamed at deploy)")
    utils.sync_profile_copies()
    sample = frappe.db.sql(
        """select p.employee from `tabEmployee Uniform Profile` p join tabEmployee e on e.name = p.employee
        where e.status = 'Active' and e.name like %s and ifnull(e.custom_uniform_profile, '') != p.name limit 1""", like)
    check("6c Employee.custom_uniform_profile linked", not sample, str(sample))

    # ── 7. get_due_rows ──
    t = time.time()
    rows = utils.get_due_rows()
    check("7a get_due_rows (all)", len(rows) > 0, f"{len(rows)} rows in {time.time() - t:.1f}s")
    reasons = {r["issue_reason"] for r in rows}
    check("7b both reasons present", reasons == {"New Issue", "Periodic Supplement"}, str(reasons))
    ni = utils.get_due_rows(issue_filter="New Issue")
    ps = utils.get_due_rows(issue_filter="Periodic Supplement")
    check("7c issue_filter splits the rows", {r["issue_reason"] for r in ni} <= {"New Issue"}
          and {r["issue_reason"] for r in ps} <= {"Periodic Supplement"} and len(ni) + len(ps) == len(rows),
          f"{len(ni)} + {len(ps)} = {len(rows)}")
    one_time_templates = {utils.template_of(r.item) for r in rules if cint(r.one_time)}
    check("7d one-time items never periodic", not [r for r in ps if r["item_template"] in one_time_templates])
    later = utils.get_due_rows(issue_filter="Periodic Supplement", due_before=add_days(today(), 400))
    check("7e later Due On or Before → more periodic rows", len(later) >= len(ps), f"{len(ps)} → {len(later)}")
    shoe_rows = [r for r in ni if r["item_template"] == "Dép"]
    check("7f new hires without a shoe size get Dép Free Size",
          shoe_rows and all(r["item_code"] == "Dép Free Size" or r["item_error"] for r in shoe_rows),
          f"{len(shoe_rows)} shoe rows")

    # ── 8. Allocation: receive stock, submit, cancel restores imported history ──
    new_row = next((r for r in ni if r["item_code"] and r["item_template"] != "Dép"), None)
    old_row = next((r for r in ps if r["item_code"]), None)
    check("8a fixtures found", new_row and old_row, f"{new_row and new_row['employee']} / {old_row and old_row['employee']}")
    if not (new_row and old_row):
        return
    legacy = frappe.db.sql(
        """select eui.name, eui.item_template, eui.last_issue_date, eui.last_issue_qty, eui.total_issued_qty
        from `tabEmployee Uniform Item` eui join `tabEmployee Uniform Profile` p on p.name = eui.parent
        join tabItem i on i.name = eui.item_template
        where p.employee = %s and coalesce(nullif(i.variant_of, ''), i.name) = %s""",
        (old_row["employee"], old_row["item_template"]), as_dict=True)[0]

    # The uniform warehouse has no inventory account yet (accounting decision before
    # go-live): borrow one for this transaction only — rolled back.
    if not frappe.db.get_value("Warehouse", warehouse, "account"):
        acc = frappe.db.get_value("Warehouse", "G-Sewing - TIQN", "account")
        frappe.db.set_value("Warehouse", warehouse, "account", acc)
        print(f"     (test only) {warehouse}.account = {acc}")
    try:
        uniform_api.receive_stock([{"item_code": new_row["item_code"], "qty": 1, "rate": 0}])
        check("8b receive_stock refuses a zero price", False)
    except frappe.ValidationError:
        check("8b receive_stock refuses a zero price", True)
    try:
        uniform_api.receive_stock([{"item_code": "Áo thun nữ", "qty": 1, "rate": 1000}])
        check("8c receive_stock refuses a template", False)
    except frappe.ValidationError:
        check("8c receive_stock refuses a template", True)
    rec = uniform_api.receive_stock([
        {"item_code": new_row["item_code"], "qty": 10, "rate": 50000},
        {"item_code": old_row["item_code"], "qty": 10, "rate": 50000},
    ])
    check("8d receive_stock posts a Material Receipt",
          frappe.db.get_value("Stock Entry", rec["name"], ["docstatus", "stock_entry_type"]) == (1, "Material Receipt"),
          rec["name"])

    alloc = frappe.get_doc({
        "doctype": "Uniform Allocation", "posting_date": today(),
        "items": [
            {"employee": new_row["employee"], "item_code": new_row["item_code"], "qty": new_row["qty"],
             "issue_reason": "New Issue"},
            {"employee": old_row["employee"], "item_code": old_row["item_code"], "qty": old_row["qty"],
             "issue_reason": "Periodic Supplement"},
            {"employee": old_row["employee"], "item_code": new_row["item_code"], "qty": 1,
             "issue_reason": "Damaged", "reuse_old_item": 1},
        ],
    })
    alloc.insert()
    check("8e company taken from the warehouse",
          alloc.company == frappe.db.get_value("Warehouse", warehouse, "company") and alloc.set_warehouse == warehouse,
          alloc.company)
    alloc.submit()
    se_rows = frappe.get_all("Stock Entry Detail", filters={"parent": alloc.stock_entry}, pluck="item_code")
    check("8f submit → Material Issue without the reuse row", alloc.stock_entry and len(se_rows) == 2, str(se_rows))
    row = frappe.get_doc("Employee Uniform Item", legacy.name)
    check("8g periodic row updated + imported history kept in base_*",
          getdate(row.last_issue_date) == getdate(today())
          and cint(row.total_issued_qty) == cint(legacy.total_issued_qty) + cint(old_row["qty"])
          and getdate(row.base_last_issue_date) == getdate(legacy.last_issue_date)
          and cint(row.base_total_qty) == cint(legacy.total_issued_qty),
          f"total {row.total_issued_qty}, base {row.base_last_issue_date}/{row.base_total_qty}")
    check("8h next due recomputed from today", row.next_due_date and getdate(row.next_due_date) > getdate(today()),
          str(row.next_due_date))

    alloc.reload()
    alloc.cancel()
    row = frappe.get_doc("Employee Uniform Item", legacy.name)
    check("8i cancel restores the imported history",
          getdate(row.last_issue_date) == getdate(legacy.last_issue_date)
          and cint(row.total_issued_qty) == cint(legacy.total_issued_qty)
          and row.item_template == legacy.item_template,
          f"{row.last_issue_date} {row.total_issued_qty} {row.item_template}")
    check("8j stock entry cancelled", frappe.db.get_value("Stock Entry", alloc.stock_entry, "docstatus") == 2)
    new_track = frappe.db.sql(
        """select eui.total_issued_qty, eui.last_issue_date from `tabEmployee Uniform Item` eui
        join `tabEmployee Uniform Profile` p on p.name = eui.parent where p.employee = %s and eui.item_template = %s""",
        (new_row["employee"], new_row["item_code"]), as_dict=True)
    check("8k new employee's row back to not issued",
          new_track and cint(new_track[0].total_issued_qty) == 0 and not new_track[0].last_issue_date, str(new_track))

    bad_alloc = frappe.get_doc({
        "doctype": "Uniform Allocation", "posting_date": today(),
        "items": [{"employee": new_row["employee"], "item_code": new_row["item_code"], "qty": 1}],
    }).insert()
    try:
        bad_alloc.submit()
        check("8l row without Issue Reason is blocked", False)
    except frappe.ValidationError:
        check("8l row without Issue Reason is blocked", True)

    # ── 9. Dashboard card = Uniform Tracking report ──
    summary = uniform_api.get_dashboard_summary()
    rep_overdue = len(uniform_tracking.get_data(frappe._dict(status="Overdue")))
    rep_soon = len(uniform_tracking.get_data(frappe._dict(status="Due Soon")))
    check("9a Overdue card = report", summary["employees_overdue"] == rep_overdue, f"{summary['employees_overdue']} / {rep_overdue}")
    check("9b Due Soon card = report", summary["employees_due_soon"] == rep_soon, f"{summary['employees_due_soon']} / {rep_soon}")
    check("9c warnings computed", summary["missing_profiles"] == conflicts and summary["missing_shoe_size"] > 0, str(summary))

    # ── 10. Assignment Preview report ──
    prev = uniform_assignment_preview.get_data(frappe._dict())
    probs = uniform_assignment_preview.get_data(frappe._dict(only_problems=1))
    check("10 Assignment Preview runs", len(prev) == len(emps), f"{len(prev)} rows, {len(probs)} with problems")

    # ── 11. daily_refresh end to end ──
    res = utils.daily_refresh()
    check("11 daily_refresh", res["profiles_created"] == 0 and res["rows_updated"] == 0, str(res))

    # ── 12. Forecast still computes (sizes now from the Employee) ──
    fc = frappe.db.get_value("Uniform Demand Forecast", {}, ["name", "total_forecast_qty"], as_dict=True)
    if fc:
        out = forecast.compute(fc.name)
        check("12 forecast computes", out["items"] > 0,
              f"{fc.name}: total {fc.total_forecast_qty} → {out['total_forecast']}, "
              f"missing variants {out['missing_variants'][:3]}")
