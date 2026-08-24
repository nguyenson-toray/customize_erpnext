# hide_restricted_export_fields.js

Hide fields the current user cannot read at their `permlevel` from the **Export Data** dialog.

| | |
|---|---|
| **File** | `customize_erpnext/public/js/hide_restricted_export_fields.js` |
| **Hook** | `app_include_js` in `customize_erpnext/hooks.py` |
| **Scope** | The *Export Data* dialog only (List view → Export, and the Data Import tool) |
| **Layer** | UI only — **not** a security control |
| **Verified on** | frappe v16.31.0 · erpnext v16.32.1 · hrms v16.16.0 |

---

## 1. The problem

`frappe.data_import.DataExporter` builds its column picker from `get_columns_for_picker()`
(`frappe/public/js/frappe/data_import/data_exporter.js:349`). That function filters on
fieldtype (`no_value_type`), `is_virtual` and `lft`/`rgt` — **it never looks at `permlevel`**.

The server, however, does enforce permlevel: `Meta.get_permitted_fieldnames()` →
`Meta.get_permlevel_access()` (`frappe/model/meta.py:684`) keeps only fields whose `permlevel`
appears in a Role Permission row the user's roles match.

Result before this script: a user ticks *Billing Rate*, exports, and gets a column full of blanks
with no explanation. The script removes those columns from the picker so the list matches what the
export can actually contain.

> **This is not a security layer.** The server keeps enforcing permlevel with or without this file.
> Deleting this script changes nothing about what data a user can obtain.

---

## 2. What it does

On every *Export Data* dialog open:

1. Skip entirely for **Administrator** and **System Manager** (see §6).
2. Resolve the DocType being exported.
3. Skip if the DocType is a **core doctype**, or has **no Role Permission rows at all** — the two
   cases where the server also returns every field (`frappe/model/__init__.py :: get_permitted_fields`).
4. For every field of the parent DocType and of each child table, with `permlevel > 0`:
   if `frappe.perm.has_perm(<parent doctype>, permlevel, "read")` is false → **remove the column**
   from the picker.

No field list is hard-coded. Any field of any DocType is covered.

---

## 3. Why DOM manipulation instead of overriding Frappe internals

The obvious alternative is to override `DataExporter.prototype.get_multicheck_options` or
`get_columns_for_picker`. That was rejected:

1. **No stability contract.** Those are internal names; Frappe reshapes them between versions
   (`get_columns_for_picker` only became an exported function in v14). A patch silently stops
   working — or throws — after `bench update`, and export is a function people rely on.
2. **`get_columns_for_picker` is an ES module export, not a namespaced global.** It cannot be
   reliably replaced from an `app_include_js` file at all.
3. **Class overrides collide.** Any other app doing the same thing fights with ours, and the whole
   thing needs re-verification on every upgrade.

The DOM contract used instead is what the entire Frappe desk UI already depends on, so it changes
far more rarely — and every step is guarded, so if it *does* change the script no-ops instead of
breaking the dialog.

---

## 4. Anchors in Frappe source

Everything below was read from the installed source, not assumed.

| What we rely on | Source |
|---|---|
| Dialog root is `.modal`, title is `<h4 class="modal-title">` | `frappe/public/js/frappe/dom.js:341` `get_modal()` |
| `shown.bs.modal` is the open event (Bootstrap 4 — markup uses `data-dismiss`) | `frappe/public/js/frappe/ui/dialog.js:123` |
| Control wrapper is `.frappe-control[data-fieldtype][data-fieldname]`, with the control object on `wrapper.fieldobj` | `frappe/public/js/frappe/form/controls/base_control.js:11-19` |
| Each option row is `.checkbox.unit-checkbox` containing `input[data-unit="<fieldname>"]` | `frappe/public/js/frappe/form/controls/multicheck.js:169-178` |
| First MultiCheck field is named after the **parent DocType**, the rest after the **Table fieldname** | `data_exporter.js:64-90` (`make_dialog`) |
| `frappe.perm.has_perm(doctype, permlevel, "read")` — ORs every Role Permission row whose role the user holds | `frappe/public/js/frappe/model/perm.js:48`, `get_role_permissions:142` |
| `frappe.model.core_doctypes_list`, `frappe.model.no_value_type` | `frappe/public/js/frappe/model/model.js:49,80` |
| `window.cint` is a global | `frappe/public/js/frappe/utils/datatype.js:9` |

**Selection is by `fieldname`, never by label** — labels are translated and can collide. The
`fieldname` lives in `data-unit` on both the `<input>` and the `<span class="label-area">`.

Each MultiCheck is searched **within its own `.frappe-control` wrapper**, so the `name` / `ID` row
that exists in the parent block *and* in every child-table block is never confused across sections.

---

## 5. Removing, not `.hide()`-ing

The column row is **removed from the DOM and spliced out of the control's `options` array**.
Merely hiding it is wrong in two ways, both verified in Frappe source:

- `DataExporter.select_all()` does `this.dialog.$wrapper.find(":checkbox").prop("checked", true)`
  (`data_exporter.js:173`). jQuery's `:checkbox` **still matches hidden inputs**, so one click on
  *Select All* would re-add the restricted column to the export.
- The dialog's search box (`frappe.utils.setup_search`, `utils.js:986`) calls `$(row).toggle(match)`
  on every `.unit-checkbox` on each keystroke — which would **show the hidden row again**.

`control.options` is the *same array instance* as `control.df.options`
(`multicheck.js :: parse_df_options`), so splicing it also keeps any later re-render correct.

The checkbox is also unchecked (with a `change` trigger) before removal, because
`setup_on_page_show()` → `select_mandatory()` runs first and may have pre-ticked a mandatory field.

---

## 6. Edge cases handled

| Case | Behaviour |
|---|---|
| `ID` / `name` and the other `default_fields` | Never hidden (`ALWAYS_VISIBLE` set) — the server always permits them. |
| `permlevel = 0` | Never hidden. If level 0 read were denied the user could not open the list at all. |
| User with several roles | `frappe.perm.has_perm` ORs across every role — matches the server's `get_permlevel_access()`. |
| Administrator | Skipped entirely. |
| System Manager | Skipped entirely — see the caveat below. |
| Child table fields | Checked against the **parent** DocType's Role Permissions. Child DocTypes carry no permissions of their own (`Meta.get_permissions(parenttype)`); checking the child would hide every restricted child field for everyone. |
| Core doctypes / doctypes with no DocPerm rows | Skipped, mirroring the server's own short-circuits. |
| Dialog reopened many times | Exactly one delegated listener is bound per page load, guarded by `customize_erpnext.export_field_perms.bound`. |
| Anything unexpected (missing meta, changed DOM, perm lookup throws) | Guarded / caught → the dialog works normally, unfiltered. Fails **open**, never blocks export. |

> ⚠ **System Manager does not actually bypass permlevel server-side.** Only Administrator does.
> Skipping System Manager is a deliberate UI choice (admins keep seeing the whole field list); a
> System Manager without read at that level will still get a blank column from the server.
> To change it, drop `"System Manager"` from `should_skip_filtering()`.

---

## 7. Two traps found while writing this

Both would have made the script silently do nothing. Recorded so they are not reintroduced:

1. **Do not add a jQuery namespace to the event.** Binding `shown.bs.modal.customize` never fires:
   jQuery only runs a namespaced handler when the *triggered* event carries **all** of the handler's
   namespaces, and Bootstrap triggers only `shown.bs.modal`. Duplicate binding is prevented with a
   flag instead.
2. **`show.bs.modal` cannot be used**, even though it would fire earlier. Bootstrap 4 triggers it
   *before* `_showElement()` attaches the modal to `<body>`, so a handler delegated on `document`
   never receives it from a freshly built dialog.

Known cosmetic limitation: `shown.bs.modal` fires only after the modal's fade transition completes,
so restricted rows are visible for the ~150 ms of the fade before being removed.

---

## 8. Verification

### Algorithm vs. the server, in bulk

The JS rule was re-implemented in Python and diffed against the server's own
`frappe.model.get_permitted_fields()` for every DocType that has `permlevel > 0` fields, plus their
child tables (Table / Table MultiSelect fields excluded — `no_value_type` keeps them out of the
picker anyway):

```
user=hoanh.ltk@tiqn.com.vn roles=8  doctypes_checked=21 mismatches=0
user=vinh.nt@tiqn.com.vn   roles=10 doctypes_checked=21 mismatches=0
user=loan.ptk@tiqn.com.vn  roles=8  doctypes_checked=21 mismatches=0
user=ni.nht@tiqn.com.vn    roles=8  doctypes_checked=21 mismatches=0
user=binh.dtt@tiqn.com.vn  roles=8  doctypes_checked=21 mismatches=0
```

Also confirmed on this site:

- `frappe.boot.user.roles` (→ `frappe.user_roles`) **does** include the implicit `All` role, so
  DocPerm rows granted to `All` at permlevel > 0 are honoured (e.g. `Leave Application.status`).
- `Custom DocPerm` records are resolved inside server `Meta` before the meta is shipped to the
  client, so `meta.permissions` on the client already reflects Role Permission Manager changes.

### UI test — uses existing configuration, no data changed

`Timesheet` grants read at permlevel 1 **only to `Accounts User`**, and `Timesheet Detail` has five
permlevel-1 fields. That is a ready-made test case:

1. Log in as a user with `HR User` but **not** `Accounts User` (e.g. `hoanh.ltk@tiqn.com.vn`).
2. **Timesheet** list → *Export*. In the *Time Logs (Timesheet Detail)* block, these must be gone:
   `billing_hours`, `billing_rate`, `billing_amount`, `costing_rate`, `costing_amount`.
3. Click **Select All**, then export — confirm those five columns are absent from the file.
   (This is the check that a plain `.hide()` would fail.)
4. Log in as **Administrator** → same dialog → all five fields are still listed.
5. Negative check on another DocType: `Leave Application.status` and `Employee Checkin.time` are
   permlevel 1 but `HR User` **is** granted read at level 1 — nothing may disappear there.

Refresh with **Ctrl+Shift+R** the first time: the file is served from a static path with no hash.

---

## 9. Maintenance notes

- **`hooks.py` changed → `bench restart` is required.** Editing only the `.js` afterwards does not:
  `sites/assets/customize_erpnext` is a symlink to the app's `public/` directory, so a saved edit is
  served immediately (browser cache aside).
- The file is **not** a `*.bundle.js`, so it gets no content hash and no cache-busting. If it starts
  changing often, rename it to `hide_restricted_export_fields.bundle.js` and update `hooks.py`
  (same pattern as `csv_bom_fix.bundle.js`).
- No `vi.csv` entries: the script has no user-facing strings. Its only translated value is the
  comparison against `__("Export Data")`, which reuses Frappe's own translation.
- Manual re-run from the browser console on an open dialog:
  ```js
  customize_erpnext.export_field_perms.filter_export_dialog($(".modal:visible"));
  ```
- With `developer_mode` on, a one-line summary of how many columns were removed is logged.
