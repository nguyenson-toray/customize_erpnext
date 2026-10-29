"""Hồi quy Door Alert Setting > Unlock Permissions — chạy tay, KHÔNG phải unittest.

    cd ~/frappe-bench/sites
    ../env/bin/python -c "import frappe; frappe.init(site='erp.tiqn.local'); frappe.connect(); \
        exec(open('../apps/customize_erpnext/customize_erpnext/network/door/test_unlock_permission.py').read())"

KHÔNG kết nối máy cửa nào: `dc._run` bị thay bằng hàm chỉ ghi lại lệnh, `_probe_all`
trả {} (mọi cửa "offline"). Dòng phân quyền / Door Control Action ghi trong test đều
rollback ở cuối; Door Alert Setting / Attendance Machine Setting không được save.
"""

from unittest.mock import patch

import frappe

import customize_erpnext.network.door.control as dc

ok = fail = 0


def check(label, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  PASS  {label} {extra}")
    else:
        fail += 1
        print(f"  FAIL  {label} {extra}")


def raises(fn, exc=Exception):
    try:
        fn()
    except exc:
        return True
    except Exception as e:  # wrong exception type
        print(f"        (raised {type(e).__name__}: {e})")
        return False
    return False


frappe.set_user("Administrator")
doors = dc._doors()
assert len(doors) >= 2, "cần ít nhất 2 máy cửa đang bật"
A, B = doors[0]["device_name"], doors[1]["device_name"]
# a Door Control user who is not System Manager
# a Door Control user who is not System Manager
TESTER = frappe.db.sql(
    """select hr.parent from `tabHas Role` hr join tabUser u on u.name = hr.parent
    where hr.role = 'Door Control' and hr.parenttype = 'User' and u.enabled = 1
    and hr.parent not in (select parent from `tabHas Role` where role in ('System Manager', 'Administrator'))
    limit 1"""
)[0][0]
OTHER = next(u for u in ("son.nt@tiqn.com.vn", "Administrator") if u != TESTER)
print(f"doors A={A!r} B={B!r}, tester={TESTER}")

sent = []
_orig_log_error = frappe.log_error
frappe.log_error = lambda *a, **k: None
patches = [
    patch.object(dc, "_run", lambda cfg, action: sent.append(cfg["ip"]) or None),
    patch.object(dc, "_probe_all", lambda doors, force=False: {}),
    patch.object(dc, "_set_open", lambda *a, **k: None),
    patch.object(dc, "_clear_open", lambda *a, **k: None),
]
for p in patches:
    p.start()

try:
    # ── 1. split_users ──────────────────────────────────────────────────────
    print("1. split_users")
    check("comma / space / newline / case / duplicates",
          dc.split_users(" A@x.vn, b@x.vn;\nc@x.vn  a@x.vn ,") == ["a@x.vn", "b@x.vn", "c@x.vn"])
    check("empty -> []", dc.split_users("") == [] and dc.split_users(None) == [] and dc.split_users(" , ") == [])

    # ── 2. can_unlock ───────────────────────────────────────────────────────
    print("2. can_unlock")
    rules = {A: {"u1@x.vn"}, B: None}
    check("door without row -> everyone", dc.can_unlock("ZZ other", user="u2@x.vn", rules=rules))
    check("row with empty Users -> everyone", dc.can_unlock(B, user="u2@x.vn", rules=rules))
    check("listed user may", dc.can_unlock(A, user="u1@x.vn", rules=rules))
    check("listed user, other case", dc.can_unlock(A, user="U1@X.vn", rules=rules))
    check("unlisted user may not", not dc.can_unlock(A, user="u2@x.vn", rules=rules))
    check("Administrator always", dc.can_unlock(A, user="Administrator", rules=rules))

    # ── 3. validate (in memory, no save) ────────────────────────────────────
    print("3. Door Alert Setting validation")
    s = frappe.get_doc("Door Alert Setting")
    loc_a = next(d["location"] for d in doors if d["device_name"] == A)
    unique_loc = loc_a and sum(1 for d in dc.get_machines(door_only=True) if d["location"].strip().lower() == loc_a.strip().lower()) == 1
    s.set("unlock_permissions", [])
    s.append("unlock_permissions", {"door": (loc_a.upper() if unique_loc else A.lower()),
                                    "users": f" {TESTER.upper()} ,{TESTER};{OTHER}"})
    s.append("unlock_permissions", {"door": B, "users": ""})
    s._validate_unlock_permissions()
    row = s.unlock_permissions[0]
    check("Location / case -> Device Name", row.door == A, row.door)
    check("users normalised", row.users == f"{TESTER}, {OTHER}", repr(row.users))
    check("empty users stay empty", (s.unlock_permissions[1].users or "") == "")

    s.set("unlock_permissions", [{"door": "ZZ No Such Door", "users": ""}])
    check("unknown door throws", raises(s._validate_unlock_permissions, frappe.ValidationError))
    s.set("unlock_permissions", [{"door": A, "users": "zz-nobody@example.invalid"}])
    check("unknown user throws", raises(s._validate_unlock_permissions, frappe.ValidationError))
    s.set("unlock_permissions", [{"door": A, "users": ""}, {"door": A, "users": TESTER}])
    check("door twice throws", raises(s._validate_unlock_permissions, frappe.ValidationError))

    # ── 4. permlevel: a Door Control user cannot change the table ───────────
    print("4. permlevel")
    frappe.set_user(TESTER)
    s = frappe.get_doc("Door Alert Setting")
    before = [(r.door, r.users) for r in s.unlock_permissions]
    s.append("unlock_permissions", {"door": A, "users": TESTER})
    s.validate_higher_perm_levels()
    check("table reset to the saved rows", [(r.door, r.users) for r in s.unlock_permissions] == before)
    check("validation skipped (no write access)", s._validate_unlock_permissions() is None)
    frappe.set_user("Administrator")

    # ── 5. endpoints, rules written in the DB (rolled back) ─────────────────
    print("5. endpoints")
    frappe.db.delete("Door Unlock Permission", {"parenttype": "Door Alert Setting"})
    for idx, (door, users) in enumerate([(A, OTHER), (B, f"{OTHER}, {TESTER.upper()}")], 1):
        frappe.get_doc({
            "doctype": "Door Unlock Permission", "parent": "Door Alert Setting",
            "parenttype": "Door Alert Setting", "parentfield": "unlock_permissions",
            "idx": idx, "door": door, "users": users,
        }).db_insert()

    frappe.set_user(TESTER)
    sent.clear()
    check("unlock A refused", raises(lambda: dc.unlock_door(A), frappe.PermissionError))
    check("hold_open A refused", raises(lambda: dc.hold_open(A), frappe.PermissionError))
    check("close_door A refused", raises(lambda: dc.close_door(A), frappe.PermissionError))
    check("nothing sent to A", not sent, str(sent))
    r = dc.unlock_door(B)
    check("unlock B allowed", r["success"] and len(sent) == 1, str(r.get("message")))
    payload = {d["device_name"]: d for d in dc.get_doors()["doors"]}
    check("get_doors still lists A", A in payload)
    check("payload can_unlock A=0 B=1", payload[A]["can_unlock"] is False and payload[B]["can_unlock"] is True)
    sent.clear()
    r = dc.unlock_all()
    check("unlock_all skips A", A in r["skipped"] and A not in [x["device_name"] for x in r["results"]], str(r["skipped"]))
    check("unlock_all opens B", B in [x["device_name"] for x in r["results"] if x["success"]])
    check("unlock_all sent only to allowed doors", len(sent) == len(r["results"]))

    frappe.db.delete("Door Unlock Permission", {"parenttype": "Door Alert Setting", "door": B})
    frappe.get_doc({
        "doctype": "Door Unlock Permission", "parent": "Door Alert Setting",
        "parenttype": "Door Alert Setting", "parentfield": "unlock_permissions",
        "idx": 2, "door": B, "users": OTHER,
    }).db_insert()
    # every other enabled door is still open to everyone -> only refused when ALL are denied
    with patch.object(dc, "_doors", lambda: [d for d in doors if d["device_name"] in (A, B)]):
        sent.clear()
        check("unlock_all with no allowed door refused", raises(dc.unlock_all, frappe.PermissionError) and not sent)

    frappe.set_user(OTHER)
    check("listed user may unlock A", dc.can_unlock(A))
    frappe.set_user("Administrator")

    # ── 6. rename in Attendance Machine Setting follows into the rules ──────
    print("6. rename cascade")
    ams = frappe.get_doc("Attendance Machine Setting")
    ams._doc_before_save = frappe.get_doc("Attendance Machine Setting")
    row = next(r for r in ams.machines if r.device_name == A)
    row.device_name = "ZZ Renamed Door"
    ams._rename_doors_in_unlock_permissions()
    rules = dc.unlock_rules()
    check("rule moved to the new name", "ZZ Renamed Door" in rules and A not in rules, str(list(rules)))
finally:
    for p in patches:
        p.stop()
    frappe.log_error = _orig_log_error
    frappe.set_user("Administrator")
    frappe.db.rollback()

print(f"\n{ok} PASS / {fail} FAIL")
