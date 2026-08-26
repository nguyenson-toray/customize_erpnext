# Export Data — column filtering

> Kept **outside** `public/`: everything under `public/` is served at `/assets/…` with no
> authentication, so internal notes and user names must not live there.

Remove columns from the **Export Data** dialog, in two independent passes:

1. **Permlevel** — fields the current user cannot Read at their `permlevel` (automatic).
2. **Manual list** — fields named in `hide_export_fields.json`, per DocType (curation).

| | |
|---|---|
| **Script** | `customize_erpnext/public/js/hide_restricted_export_fields.js` |
| **Config** | `customize_erpnext/public/js/hide_export_fields.json` |
| **Headless test** | `customize_erpnext/overrides/export_dialog/smoke_test.js` (`node smoke_test.js`) |
| **Hook** | `app_include_js` in `customize_erpnext/hooks.py` |
| **Scope** | The *Export Data* dialog only (List view → Export, and the Data Import tool) |
| **Layer** | UI only — **not** a security control |
| **Verified on** | frappe v16.31.0 · erpnext v16.32.1 · hrms v16.16.0 |

---

## 1. The problem (pass 1)

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

1. Resolve the DocType being exported, and one "block" per MultiCheck (the parent DocType, plus one
   per child table).
2. **Pass 1 — permlevel.** Skipped entirely for Administrator / System Manager (§7), for **core
   doctypes**, and for DocTypes with **no Role Permission rows at all** — the two cases where the
   server also returns every field (`frappe/model/__init__.py :: get_permitted_fields`).
   Then, for every field with `permlevel > 0`: if
   `frappe.perm.has_perm(<parent doctype>, permlevel, "read")` is false → **remove the column**, or,
   when the field is a Table, **remove the whole child block** it opens.
3. **Pass 2 — manual list.** Remove every field named in `hide_export_fields.json` for that block's
   DocType — again, a Table fieldname removes the whole child block. Applies to **all users,
   Administrator included**.

No field list is hard-coded in the script. Pass 1 covers any field of any DocType automatically.

---

## 3. `hide_export_fields.json`

A flat map of **DocType name → array of fieldnames**:

```json
{
	"__readme__": "…",

	"Employee": ["image", "custom_fingerprints"],
	"Employee Internal Work History": ["branch"]
}
```

Three kinds of entry:

| Entry | Effect |
|---|---|
| a plain fieldname (`"image"`) | removes that one column |
| a **Table / Table MultiSelect** fieldname (`"custom_fingerprints"`) | removes the **entire child block** it opens — label and every column of `Fingerprint Data`, not one checkbox |
| a **child DocType used as a key** (`"Employee Internal Work History"`) | applies inside that child block, in **every** parent that embeds it |

Rules:

- Values are **fieldnames**, never labels (labels are translated and can collide).
- A Table field never appears as a checkbox at all — `Table` and `Table MultiSelect` are in
  `frappe.model.no_value_type` (`model.js:54`), so `get_columns_for_picker()` drops them. It gets a
  whole MultiCheck section instead. That is why naming one hides the section.
- Any non-array value is ignored, so descriptive keys such as `__readme__` are safe to keep.
- `name` (the ID column) **cannot** be hidden — it is the key column for *Update Existing Records*.
  An attempt is ignored with a console warning.
- A missing or invalid file is treated as `{}`: the dialog keeps working, pass 1 still runs.

Editing the file is enough — **no `bench build`, no `bench restart`**. `sites/assets/customize_erpnext`
is a symlink to the app's `public/` directory, and the script fetches the file with
`cache: "no-cache"` so the browser revalidates instead of serving a stale copy. A hard refresh is
only needed for tabs that were already open.

To re-read it without reloading the page:

```js
customize_erpnext.export_field_perms.reload_config();
```

When a child block is removed, its MultiCheck control stays in the dialog's `fields_list` with an
empty value, so `export_fields` carries `{"custom_fingerprints": []}`. That is exactly what the
dialog already sends when a user unticks every row of a child block, and the server handles it:
`Exporter.get_exportable_fields()` returns `[]` and no column is emitted.

> ⚠ **A hidden field disappears from the Data Import template too**, so it can no longer be
> bulk-updated through Data Import. The two cases cannot be told apart: the list-view *Export*
> button also constructs the dialog with `exporting_for = "Insert New Records"`
> (`frappe/public/js/frappe/list/bulk_operations.js:502`), exactly like a Data Import insert
> template. Only put a field in this list if you are happy to lose that too.

## 4. Why DOM manipulation instead of overriding Frappe internals

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

## 5. Anchors in Frappe source

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

**Selection is by `fieldname`, never by label.** The `fieldname` lives in `data-unit` on both the
`<input>` and the `<span class="label-area">`.

Each MultiCheck is searched **within its own `.frappe-control` wrapper**, so the `name` / `ID` row
that exists in the parent block *and* in every child-table block is never confused across sections.

---

## 6. Removing, not `.hide()`-ing

The column row is **removed from the DOM and spliced out of the control's `options` array**.
Merely hiding it is wrong in two ways, both verified in Frappe source:

- `DataExporter.select_all()` does `this.dialog.$wrapper.find(":checkbox").prop("checked", true)`
  (`data_exporter.js:173`). jQuery's `:checkbox` **still matches hidden inputs**, so one click on
  *Select All* would re-add the hidden column to the export.
- The dialog's search box (`frappe.utils.setup_search`, `utils.js:986`) calls `$(row).toggle(match)`
  on every `.unit-checkbox` on each keystroke — which would **show the hidden row again**.

`control.options` is the *same array instance* as `control.df.options`
(`multicheck.js :: parse_df_options`), so splicing it also keeps any later re-render correct.

The checkbox is also unchecked (with a `change` trigger) before removal, because
`setup_on_page_show()` → `select_mandatory()` runs first and may have pre-ticked a mandatory field.

---

## 7. Edge cases handled

| Case | Behaviour |
|---|---|
| `ID` / `name` and the other `default_fields` | Never hidden by pass 1 (`ALWAYS_VISIBLE`). `name` is additionally refused in pass 2. |
| `permlevel = 0` | Never hidden by pass 1. If level 0 read were denied the user could not open the list at all. |
| User with several roles | `frappe.perm.has_perm` ORs across every role — matches the server's `get_permlevel_access()`. |
| Administrator | Pass 1 skipped. Pass 2 **still applies**. |
| System Manager | Pass 1 skipped — see caveat below. Pass 2 still applies. |
| Table field hidden (either pass) | The whole child block goes — label and all its columns. Its control is emptied, so *Select All* cannot resurrect it and `export_fields` sends `[]` for that table. |
| A child DocType listed in the JSON whose block was already wiped by a Table entry | Skipped silently — not reported as a typo. |
| Child table fields | Pass 1 checks them against the **parent** DocType's Role Permissions. Child DocTypes carry no permissions of their own (`Meta.get_permissions(parenttype)`); checking the child would hide every restricted child field for everyone. |
| Core doctypes / doctypes with no DocPerm rows | Pass 1 skipped, mirroring the server's own short-circuits. |
| Dialog reopened many times | Exactly one delegated listener is bound per page load, guarded by `customize_erpnext.export_field_perms.bound`. |
| JSON not yet fetched on the first open | Pass 1 runs immediately; pass 2 runs when the fetch resolves. `drop_option()` is idempotent and harmless on an already-closed dialog. |
| Anything unexpected (missing meta, changed DOM, perm lookup throws, broken JSON) | Guarded / caught → the dialog works normally. Fails **open**, never blocks export. |

> ⚠ **System Manager does not actually bypass permlevel server-side.** Only Administrator does.
> Skipping System Manager is a deliberate UI choice (admins keep seeing the whole field list); a
> System Manager without read at that level will still get a blank column from the server.
> To change it, drop `"System Manager"` from `should_skip_permlevel_filtering()`.

---

## 8. Two traps found while writing this

Both would have made the script silently do nothing. Recorded so they are not reintroduced:

1. **Do not add a jQuery namespace to the event.** Binding `shown.bs.modal.customize` never fires:
   jQuery only runs a namespaced handler when the *triggered* event carries **all** of the handler's
   namespaces, and Bootstrap triggers only `shown.bs.modal`. Duplicate binding is prevented with a
   flag instead.
2. **`show.bs.modal` cannot be used**, even though it would fire earlier. Bootstrap 4 triggers it
   *before* `_showElement()` attaches the modal to `<body>`, so a handler delegated on `document`
   never receives it from a freshly built dialog.

Known cosmetic limitation: `shown.bs.modal` fires only after the modal's fade transition completes,
so removed rows are visible for the ~150 ms of the fade.

---

## 9. Verification

### Headless test of the script itself

`smoke_test.js` stubs the DOM / `frappe` globals and runs **this exact file** under Node (no jsdom on the
bench), covering both passes: 15 cases, all passing — permlevel removal on parent and child blocks,
the Administrator / System Manager exemption, unchecking before removal, splicing out of
`control.options`, the JSON list, `name` refusal, typo warning, Table-fieldname child-block wipe,
sibling blocks surviving, and a broken/unreachable JSON.

### Pass 1 vs. `get_permitted_fields()`, in bulk

The permlevel rule was re-implemented in Python and diffed against the server's own
`frappe.model.get_permitted_fields()` for every DocType that has `permlevel > 0` fields, plus their
child tables (Table / Table MultiSelect fields excluded — `no_value_type` keeps them out of the
picker anyway):

```
5 real HR users (8-10 roles each) x 21 doctypes + their child tables -> mismatches = 0
```

Also confirmed on this site:

- `frappe.boot.user.roles` (→ `frappe.user_roles`) **does** include the implicit `All` role, so
  DocPerm rows granted to `All` at permlevel > 0 are honoured (e.g. `Leave Application.status`).
- `Custom DocPerm` records are resolved inside server `Meta` before the meta is shipped to the
  client, so `meta.permissions` on the client already reflects Role Permission Manager changes.

### What the exporter actually enforces — pass 1 is deliberately stricter for child tables

Traced through `frappe/core/doctype/data_import/exporter.py`:

- **Parent** rows are fetched with `frappe.db.get_list()` (`exporter.py:177`). That path runs
  `DatabaseQuery.apply_fieldlevel_read_permissions()` (`db_query.py:695`), which **drops**
  non-permitted columns from the query — hence the blank column the user sees today.
- **Child** rows are fetched with `frappe.get_all()` (`exporter.py:200`), i.e.
  `ignore_permissions=True`, and `apply_fieldlevel_read_permissions()` returns immediately on that
  flag (`db_query.py:710`). `Exporter.get_exportable_fields()` only filters on fieldtype, never on
  permlevel.

Confirmed on this site: running `Exporter("Timesheet", export_fields={"time_logs":
["name","billing_rate","costing_rate"]}, export_data=True)` as an `HR User` **without**
`Accounts User` raises nothing and emits the header
`['ID', 'Employee', 'ID (Time Sheets)', 'Billing Rate (Time Sheets)', 'Costing Rate (Time Sheets)']`.
(The site has 0 Timesheet rows, so only the header could be observed — but no filtering happens
anywhere on that path.)

**So: Frappe's exporter does not apply permlevel to child-table columns.** Pass 1 hides them anyway,
which is *stricter* than the server. That is deliberate — the DocType declares those fields
restricted, and a picker that offers them contradicts the form UI, which does hide them. It does
mean the earlier framing "the picker matches what the export can contain" is exact for parent
fields and conservative for child fields. To follow the exporter instead, skip the
`ctx.parent_doctype !== block.doctype` blocks in `remove_by_permlevel()`.

### UI test for pass 1 — uses existing configuration, no data changed

`Timesheet` grants read at permlevel 1 **only to `Accounts User`**, and `Timesheet Detail` has five
permlevel-1 fields. That is a ready-made test case:

1. Log in as a user with `HR User` but **not** `Accounts User`.
2. **Timesheet** list → *Export*. In the *Time Logs (Timesheet Detail)* block, these must be gone:
   `billing_hours`, `billing_rate`, `billing_amount`, `costing_rate`, `costing_amount`.
3. Click **Select All**, then export — confirm those five columns are absent from the file.
   (This is the check that a plain `.hide()` would fail.)
4. Log in as **Administrator** → same dialog → all five fields are still listed.
5. Negative check on another DocType: `Leave Application.status` and `Employee Checkin.time` are
   permlevel 1 but `HR User` **is** granted read at level 1 — nothing may disappear there.

### UI test for pass 2

1. **Employee** list → *Export* → *Image* and *Offer Date* (`scheduled_confirmation_date`) must be
   absent from the field list, **including as Administrator**.
2. Add a typo to the JSON, reopen the dialog with `developer_mode` on → a console warning names the
   fieldname that was not found in the picker.

Refresh with **Ctrl+Shift+R** the first time: both files are served from static paths with no hash.

---

## 10. Maintenance notes

- **`hooks.py` changed → `bench restart` is required.** Editing only the `.js` or the `.json`
  afterwards does not: `sites/assets/customize_erpnext` is a symlink to the app's `public/`
  directory, so a saved edit is served immediately.
- The script is **not** a `*.bundle.js`, so it gets no content hash and no cache-busting. If it
  starts changing often, rename it to `hide_restricted_export_fields.bundle.js` and update
  `hooks.py` (same pattern as `csv_bom_fix.bundle.js`).
- No `vi.csv` entries: the script has no user-facing strings. Its only translated value is the
  comparison against `__("Export Data")`, which reuses Frappe's own translation.
- Console helpers:
  ```js
  customize_erpnext.export_field_perms.reload_config();                       // re-read the JSON
  customize_erpnext.export_field_perms.filter_export_dialog($(".modal:visible")); // re-run on an open dialog
  ```
- With `developer_mode` on, each dialog logs how many columns each pass removed.

---

## 11. Rollback

- **Instant, no restart:** overwrite the `.js` with a no-op (the assets symlink serves it
  immediately); users refresh the tab.
- **Clean:** comment the `app_include_js` line in `hooks.py` + `bench restart`. Unlike `fixtures`,
  `app_include_js` really is read from `hooks.py`, so commenting it out genuinely stops the load.
- Nothing persists in the database — no Property Setter, no Custom Field, no patch. Removing the
  script leaves no residue.
