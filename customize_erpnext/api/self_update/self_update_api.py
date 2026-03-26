"""
Employee Self Update API

Public APIs (allow_guest=True) — dùng cho web page self-service:
  get_field_config        → Config JSON từ Settings (fallback về file)
  get_eligible_employees  → Nhân viên trong Setting chưa Approved/Synced
  verify_identity         → Xác thực 2 số cuối SĐT hoặc 2 số ngày sinh
  get_form_data           → Lấy dữ liệu form đã điền + pre-fill từ Employee
  save_form_data          → Tạo mới / cập nhật form
  upload_cccd_photo       → Upload ảnh CCCD

HR APIs (require login):
  approve_form            → Duyệt 1 form
  approve_form_bulk       → Duyệt nhiều form
  reject_form             → Từ chối (kèm lý do)
  sync_to_employee        → Đồng bộ dữ liệu sang Employee
  get_employees_by_date   → Nhân viên theo ngày vào làm
  add_employees_to_setting → Thêm vào danh sách Setting
  download_excel          → Export Excel
  download_cccd_photos    → Export ZIP ảnh CCCD
  generate_qr_codes       → Tạo QR links HTML
"""

import frappe
from frappe import _


# ---------------------------------------------------------------------------
# SYNC_MAP: form field → Employee field
# ---------------------------------------------------------------------------

_SYNC_MAP = {
    "id_card_no":                   "custom_id_card_no",
    "id_card_date_of_issue":        "custom_id_card_date_of_issue",
    "id_card_place_of_issue":       "custom_id_card_place_of_issue",
    "id_card_cmnd_no":              "custom_id_card_cmnd_no",
    "id_card_cmnd_date_of_issue":   "custom_id_card_cmnd_date_of_issue",
    "id_card_cmnd_place_of_issue":  "custom_id_card_cmnd_place_of_issue",
    "marital_status":               "marital_status",
    "bank_ac_no":                   "bank_ac_no",
    "bank_branch":                  "custom_bank_branch",
    "current_address_province":     "custom_current_address_province",
    "current_address_commune":      "custom_current_address_commune",
    "current_address_village":      "custom_current_address_village",
    "current_address_full":         "custom_current_address_full",
    "permanent_address_province":   "custom_permanent_address_province",
    "permanent_address_commune":    "custom_permanent_address_commune",
    "permanent_address_village":    "custom_permanent_address_village",
    "permanent_address_full":       "custom_permanent_address_full",
    "place_of_origin_province":     "custom_place_of_origin_address_province",
    "place_of_origin_commune":      "custom_place_of_origin_address_commune",
    "place_of_origin_village":      "custom_place_of_origin_address_village",
    "place_of_origin_full":         "custom_place_of_origin_address_full",
    "personal_email":               "personal_email",
    "emergency_contact_name":       "person_to_be_contacted",
    "emergency_phone_number":       "emergency_phone_number",
    "relation":                     "relation",
    "date_of_birth":                "date_of_birth",
    "cell_number":                  "cell_number",
    "tax_code":                     "custom_tax_code",
    "shirt_size":                   "custom_shirt_size",
    "shoe_size":                    "custom_shoe_size",
    "social_insurance_number":      "custom_social_insurance_number",
    "driving_license":              "custom_driving_license",
    "driving_license_note":         "custom_driving_license_note",
    "number_of_childrens":          "custom_number_of_childrens",
    "custom_strengths":             "custom_strengths",
    "custom_favorite_sport":        "custom_favorite_sport",
    "custom_vegetarian":            "custom_vegetarian",
}

# All data fields stored in the form
# Note: education_level / university / major are NOT in _SYNC_MAP (they sync to a child table),
# but they ARE stored on the form itself and must be included here.
_FORM_FIELDS = list(_SYNC_MAP.keys()) + [
    "education_level", "university", "major",
    "id_card_front_photo", "id_card_back_photo", "work_history_json", "other_docs_json",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_hr():
    """Throw if user is not HR Manager, HR User, or System Manager."""
    if frappe.session.user == "Guest":
        frappe.throw(_("Authentication required"), frappe.AuthenticationError)
    roles = frappe.get_roles()
    if not any(r in roles for r in ("HR Manager", "HR User", "System Manager")):
        frappe.throw(_("Not permitted"), frappe.PermissionError)


def _delete_file_by_url(url):
    """Delete physical file + File record. Silently ignore errors."""
    import os
    from urllib.parse import unquote
    try:
        decoded = unquote(str(url))
        site_path = frappe.get_site_path()
        abs_path = os.path.join(site_path, "public", decoded.lstrip("/"))
        if os.path.exists(abs_path):
            os.remove(abs_path)
        file_name = frappe.db.get_value("File", {"file_url": url}, "name")
        if file_name:
            frappe.delete_doc("File", file_name, ignore_permissions=True, force=True)
    except Exception:
        pass


def _get_setting_employees():
    """Return list of employee IDs configured in Employee Self Update Setting."""
    rows = frappe.db.sql(
        "SELECT `employee` FROM `tabEmployee Self Update Employee`"
        " WHERE `parent`=%s AND `parenttype`=%s AND `employee` IS NOT NULL",
        ("Employee Self Update Setting", "Employee Self Update Setting"),
        as_dict=True,
    )
    return [r["employee"] for r in rows if r.get("employee")]


# ---------------------------------------------------------------------------
# Public APIs
# ---------------------------------------------------------------------------

@frappe.whitelist(allow_guest=True)
def get_page_settings():
    """
    Return page-level settings for the self-update web page.
    Currently includes:
      - verified_by_date_of_birth_or_phone_number (Check, default 1)
    """
    result = frappe.db.sql(
        "SELECT `field`, `value` FROM `tabSingles`"
        " WHERE `doctype`=%s AND `field` IN ('verified_by_date_of_birth_or_phone_number')",
        ("Employee Self Update Setting",),
        as_dict=True,
    )
    settings = {r["field"]: r["value"] for r in result}
    return {
        "require_verification": settings.get("verified_by_date_of_birth_or_phone_number", "1") != "0",
    }


@frappe.whitelist(allow_guest=True)
def get_field_config():
    """
    Return field config JSON from Employee Self Update Setting.
    Fallback to config file if not set.
    """
    import json
    import os

    result = frappe.db.sql(
        "SELECT `value` FROM `tabSingles` WHERE `doctype`=%s AND `field`=%s",
        ("Employee Self Update Setting", "field_config_json"),
        as_list=True,
    )
    config_str = result[0][0] if result and result[0][0] else None

    if not config_str:
        config_path = os.path.join(
            frappe.get_app_path("customize_erpnext"),
            "customize_erpnext", "doctype", "employee_self_update_setting",
            "employee_self_update_config.json"
        )
        with open(config_path, "r", encoding="utf-8") as f:
            config_str = f.read()

    return json.loads(config_str)


@frappe.whitelist(allow_guest=True)
def get_eligible_employees():
    """
    Return employees in Setting who have NOT yet been Approved/Synced.
    Employees with Pending Review or Rejected forms are still shown (can re-submit).
    Filters from Setting (each optional, combinable):
      - filter_date → Employee.date_of_joining == filter_date
      - group       → Employee.custom_group == group
    """
    emp_ids = _get_setting_employees()
    if not emp_ids:
        return []

    # Read filter_date and group from Setting in one query
    setting_rows = frappe.db.sql(
        "SELECT `field`, `value` FROM `tabSingles`"
        " WHERE `doctype`=%s AND `field` IN ('filter_date', 'group')",
        ("Employee Self Update Setting",),
        as_dict=True,
    )
    setting = {r["field"]: (r["value"] or "").strip() for r in setting_rows}
    date_filter  = setting.get("filter_date", "")
    group_filter = setting.get("group", "")

    filters = {"name": ["in", emp_ids]}
    if date_filter:
        filters["date_of_joining"] = date_filter
    if group_filter:
        filters["custom_group"] = group_filter

    employees = frappe.get_all(
        "Employee",
        filters=filters,
        fields=["name", "employee_name", "date_of_birth", "cell_number"],
        order_by="employee_name asc",
        ignore_permissions=True,
    )

    # Get completed (Approved/Synced) forms
    completed_forms = frappe.get_all(
        "Employee Self Update Form",
        filters={"employee": ["in", emp_ids], "status": ["in", ["Approved", "Synced"]]},
        fields=["employee"],
        ignore_permissions=True,
    )
    completed = {f.employee for f in completed_forms}

    result = []
    for emp in employees:
        if emp.name in completed:
            continue
        birth_year = ""
        if emp.date_of_birth:
            try:
                birth_year = str(emp.date_of_birth)[:4]
            except Exception:
                pass
        result.append({
            "employee_id": emp.name,
            "display_name": emp.employee_name,
            "birth_year": birth_year,
            "has_phone": bool(emp.cell_number and str(emp.cell_number).strip()),
        })

    return result


@frappe.whitelist(allow_guest=True)
def verify_identity(employee_id, code):
    """
    Verify identity:
    - If employee has cell_number: check last 2 digits of phone
    - Else: check last 2 digits of day-of-birth (DD, zero-padded)
    Returns {"valid": True/False, "hint": "..."}
    """
    if not employee_id or not code:
        return {"valid": False}

    emp = frappe.db.sql(
        "SELECT `cell_number`, `date_of_birth` FROM `tabEmployee` WHERE `name`=%s LIMIT 1",
        employee_id,
        as_dict=True,
    )
    if not emp:
        return {"valid": False}

    emp = emp[0]
    cell = str(emp.cell_number or "").strip().replace(" ", "").replace("-", "")
    code = str(code).strip()

    if cell:
        expected = cell[-2:] if len(cell) >= 2 else cell
        hint = "2 số cuối số điện thoại"
    else:
        if not emp.date_of_birth:
            return {"valid": False, "hint": "Không có thông tin xác thực"}
        try:
            dob_str = str(emp.date_of_birth)
            expected = dob_str.split("-")[2].zfill(2)
        except Exception:
            return {"valid": False}
        hint = "2 số ngày sinh (VD: ngày 5 → 05)"

    return {"valid": code == expected, "hint": hint}


@frappe.whitelist(allow_guest=True)
def get_form_data(employee_id):
    """
    Return:
    - Existing form data if found (status + all fields)
    - Pre-fill from Employee if no form yet
    """
    if not employee_id:
        frappe.throw(_("Employee ID is required"))

    emp = frappe.db.sql(
        "SELECT `name`, `employee_name`, `date_of_joining`, `cell_number`, `date_of_birth`"
        " FROM `tabEmployee` WHERE `name`=%s LIMIT 1",
        employee_id,
        as_dict=True,
    )
    if not emp:
        frappe.throw(_("Employee not found"))
    emp = emp[0]

    # Check for existing form
    existing = frappe.db.sql(
        "SELECT `name`, `status`, `reject_reason`, " +
        ", ".join(f"`{f}`" for f in _FORM_FIELDS) +
        " FROM `tabEmployee Self Update Form` WHERE `employee`=%s ORDER BY `modified` DESC LIMIT 1",
        employee_id,
        as_dict=True,
    )

    if existing:
        form = existing[0]
        form_name = form.pop("name")
        form["has_existing"] = True
        form["form_name"] = form_name
        # Pre-fill basic info from Employee if missing in form
        if not form.get("date_of_birth"):
            form["date_of_birth"] = str(emp.date_of_birth) if emp.date_of_birth else ""
        if not form.get("cell_number"):
            form["cell_number"] = str(emp.cell_number or "").strip()
        # Convert date fields to string
        for f in ["date_of_birth", "id_card_date_of_issue", "id_card_cmnd_date_of_issue", "date_of_joining"]:
            if form.get(f) and not isinstance(form[f], str):
                form[f] = str(form[f])
        form["employee_name"] = emp.employee_name
        form["date_of_joining"] = str(emp.date_of_joining) if emp.date_of_joining else ""
        return form
    else:
        # Pre-fill from Employee — load all mapped fields via reverse _SYNC_MAP
        import json as _json

        emp_fields = list(set(_SYNC_MAP.values()))
        emp_row = frappe.db.sql(
            "SELECT " + ", ".join(f"`{f}`" for f in emp_fields) +
            " FROM `tabEmployee` WHERE `name`=%s LIMIT 1",
            employee_id,
            as_dict=True,
        )
        emp_row = emp_row[0] if emp_row else {}

        prefill = {
            "has_existing": False,
            "status": None,
            "employee_name": emp.employee_name,
            "date_of_joining": str(emp.date_of_joining) if emp.date_of_joining else "",
        }

        # Reverse-map Employee fields → form fields
        for form_field, emp_field in _SYNC_MAP.items():
            val = emp_row.get(emp_field)
            if val is None:
                prefill[form_field] = ""
            elif hasattr(val, 'isoformat'):
                prefill[form_field] = str(val)
            else:
                prefill[form_field] = str(val).strip()

        # Education child table → education_level / university / major
        edu_rows = frappe.db.sql(
            "SELECT `school_univ`, `level`, `maj_opt_subj`"
            " FROM `tabEmployee Education`"
            " WHERE `parent`=%s ORDER BY `idx` LIMIT 1",
            employee_id,
            as_dict=True,
        )
        if edu_rows:
            prefill["education_level"] = edu_rows[0].get("level") or ""
            prefill["university"]      = edu_rows[0].get("school_univ") or ""
            prefill["major"]           = edu_rows[0].get("maj_opt_subj") or ""
        else:
            prefill.setdefault("education_level", "")
            prefill.setdefault("university", "")
            prefill.setdefault("major", "")

        # External work history child table → work_history_json
        work_rows = frappe.db.sql(
            "SELECT `company_name`, `designation`, `total_experience`"
            " FROM `tabEmployee External Work History`"
            " WHERE `parent`=%s ORDER BY `idx`",
            employee_id,
            as_dict=True,
        )
        if work_rows:
            prefill["work_history_json"] = _json.dumps([
                {
                    "company_name":     r.get("company_name") or "",
                    "designation":      r.get("designation") or "",
                    "total_experience": r.get("total_experience") or "",
                }
                for r in work_rows
            ], ensure_ascii=False)
        else:
            prefill["work_history_json"] = "[]"

        return prefill


@frappe.whitelist(allow_guest=True)
def save_form_data(employee_id, **kwargs):
    """
    Create or update Employee Self Update Form.
    Always sets status = Pending Review.
    """
    if not employee_id:
        frappe.throw(_("Employee ID is required"))

    emp = frappe.db.sql(
        "SELECT `name`, `employee_name`, `date_of_joining` FROM `tabEmployee` WHERE `name`=%s LIMIT 1",
        employee_id,
        as_dict=True,
    )
    if not emp:
        frappe.throw(_("Employee not found"))
    emp = emp[0]

    # Check existing form
    existing_row = frappe.db.sql(
        "SELECT `name`, `status` FROM `tabEmployee Self Update Form` WHERE `employee`=%s ORDER BY `modified` DESC LIMIT 1",
        employee_id,
        as_dict=True,
    )
    existing_name = existing_row[0].name if existing_row else None
    existing_status = existing_row[0].status if existing_row else None

    if existing_name and existing_status in ("Approved", "Synced"):
        frappe.throw(_("Form đã được {0} và không thể chỉnh sửa.").format(_(existing_status)))

    # Remember old other_docs URLs to clean up removed files after save
    import json as _json
    old_other_docs = []
    if existing_name:
        _old_json = frappe.db.get_value("Employee Self Update Form", existing_name, "other_docs_json") or "[]"
        try:
            old_other_docs = _json.loads(_old_json)
        except Exception:
            old_other_docs = []

    if existing_name:
        frappe.flags.ignore_permissions = True
        try:
            doc = frappe.get_doc("Employee Self Update Form", existing_name)
        finally:
            frappe.flags.ignore_permissions = False
        doc.flags.ignore_permissions = True
    else:
        doc = frappe.new_doc("Employee Self Update Form")
        doc.flags.ignore_permissions = True
        doc.employee = employee_id

    doc.employee_name = emp.employee_name
    doc.date_of_joining = emp.date_of_joining

    # Set all submitted fields
    for field in _FORM_FIELDS:
        val = kwargs.get(field)
        if val is not None:
            doc.set(field, val if val != "" else None)

    # Auto-assemble full addresses
    def _join(*parts):
        return ", ".join(str(p) for p in parts if p)

    doc.current_address_full = _join(
        doc.get("current_address_village"),
        doc.get("current_address_commune"),
        doc.get("current_address_province"),
    )
    doc.permanent_address_full = _join(
        doc.get("permanent_address_village"),
        doc.get("permanent_address_commune"),
        doc.get("permanent_address_province"),
    )
    doc.place_of_origin_full = _join(
        doc.get("place_of_origin_village"),
        doc.get("place_of_origin_commune"),
        doc.get("place_of_origin_province"),
    )

    doc.status = "Pending Review"
    doc.flags.ignore_permissions = True
    doc.save()

    # Propagate dob / cell_number back to Employee
    new_dob = (kwargs.get("date_of_birth") or "").strip()
    new_cell = (kwargs.get("cell_number") or "").strip()
    if new_dob:
        frappe.db.sql("UPDATE `tabEmployee` SET `date_of_birth`=%s WHERE `name`=%s", (new_dob, employee_id))
    if new_cell:
        frappe.db.sql("UPDATE `tabEmployee` SET `cell_number`=%s WHERE `name`=%s", (new_cell, employee_id))

    frappe.db.commit()

    # Delete other_docs files that were removed in this submission
    new_other_docs = set()
    try:
        new_other_docs = set(_json.loads(doc.get("other_docs_json") or "[]"))
    except Exception:
        pass
    for url in old_other_docs:
        if url not in new_other_docs and str(url).startswith("/files/"):
            _delete_file_by_url(url)

    return {"status": "success", "message": _("Thông tin đã được lưu thành công.")}


@frappe.whitelist(allow_guest=True)
def upload_cccd_photo(employee_id, side, image_data):
    """
    Upload CCCD photo (front or back).
    employee_id: e.g. "TIQN-1234"
    side: "front" or "back"
    image_data: base64 dataURL (cropped & compressed ≤3MB JPEG)
    Returns: {"file_url": "/files/<encoded_name>"}
    """
    import base64
    import os
    import re
    from urllib.parse import quote

    if not employee_id or side not in ("front", "back"):
        frappe.throw(_("Invalid parameters"))

    emp = frappe.db.sql(
        "SELECT `name`, `employee_name` FROM `tabEmployee` WHERE `name`=%s LIMIT 1",
        employee_id,
        as_dict=True,
    )
    if not emp:
        frappe.throw(_("Employee not found"))
    employee_name = emp[0].employee_name or employee_id

    if not image_data or not image_data.startswith("data:"):
        frappe.throw(_("Invalid image data"))

    match = re.match(r"data:image/(\w+);base64,(.+)", image_data)
    if not match:
        frappe.throw(_("Invalid image format"))

    try:
        file_bytes = base64.b64decode(match.group(2))
    except Exception:
        frappe.throw(_("Failed to decode image"))

    if len(file_bytes) > 4 * 1024 * 1024:
        frappe.throw(_("Image is too large. Maximum size is 4 MB."))

    side_label = "mặt trước" if side == "front" else "mặt sau"
    safe_name = re.sub(r'[\\/:*?"<>|]', "", employee_name).strip()
    file_name = f"{employee_id} {safe_name} CCCD {side_label}.JPG"
    file_url = "/files/" + quote(file_name)

    site_path = frappe.get_site_path()
    public_files = os.path.join(site_path, "public", "files")
    os.makedirs(public_files, exist_ok=True)
    file_path = os.path.join(public_files, file_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # Create/update File record
    existing_file = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if existing_file:
        frappe.db.set_value("File", existing_file, "attached_to_doctype", "Employee Self Update Form")
        frappe.db.set_value("File", existing_file, "attached_to_name", employee_id)
    else:
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": file_name,
            "file_url": file_url,
            "attached_to_doctype": "Employee Self Update Form",
            "attached_to_name": employee_id,
            "is_private": 0,
        })
        file_doc.flags.ignore_permissions = True
        file_doc.insert()

    frappe.db.commit()
    return {"file_url": file_url}


@frappe.whitelist(allow_guest=True)
def upload_other_doc(employee_id, image_data):
    """
    Upload one other-document photo. Each call produces a unique file (timestamp suffix).
    Old files are cleaned up by save_form_data when the form is submitted.
    Returns: {"file_url": "/files/<encoded_name>"}
    """
    import base64
    import os
    import re
    import time
    from urllib.parse import quote

    if not employee_id:
        frappe.throw(_("Employee ID is required"))

    emp = frappe.db.sql(
        "SELECT `name`, `employee_name` FROM `tabEmployee` WHERE `name`=%s LIMIT 1",
        employee_id,
        as_dict=True,
    )
    if not emp:
        frappe.throw(_("Employee not found"))
    employee_name = emp[0].employee_name or employee_id

    if not image_data or not image_data.startswith("data:"):
        frappe.throw(_("Invalid image data"))

    match = re.match(r"data:image/(\w+);base64,(.+)", image_data)
    if not match:
        frappe.throw(_("Invalid image format"))

    try:
        file_bytes = base64.b64decode(match.group(2))
    except Exception:
        frappe.throw(_("Failed to decode image"))

    if len(file_bytes) > 4 * 1024 * 1024:
        frappe.throw(_("Image is too large. Maximum 4 MB."))

    safe_name = re.sub(r'[\\/:*?"<>|]', "", employee_name).strip()
    ts = int(time.time() * 1000)
    file_name = f"{employee_id} {safe_name} GiayToKhac {ts}.JPG"
    file_url = "/files/" + quote(file_name)

    site_path = frappe.get_site_path()
    public_files = os.path.join(site_path, "public", "files")
    os.makedirs(public_files, exist_ok=True)
    with open(os.path.join(public_files, file_name), "wb") as f:
        f.write(file_bytes)

    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "file_url": file_url,
        "attached_to_doctype": "Employee Self Update Form",
        "attached_to_name": employee_id,
        "is_private": 0,
    })
    file_doc.flags.ignore_permissions = True
    file_doc.insert()

    frappe.db.commit()
    return {"file_url": file_url}


# ---------------------------------------------------------------------------
# HR APIs
# ---------------------------------------------------------------------------

@frappe.whitelist()
def approve_form(form_name):
    """Approve a single form."""
    _require_hr()
    doc = frappe.get_doc("Employee Self Update Form", form_name)
    if doc.status != "Pending Review":
        frappe.throw(_("Chỉ form Pending Review mới có thể duyệt."))
    doc.status = "Approved"
    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "success"}


@frappe.whitelist()
def approve_form_bulk(names=None):
    """Approve multiple forms by name list."""
    import json as _json

    _require_hr()
    if isinstance(names, str):
        try:
            names = _json.loads(names)
        except Exception:
            frappe.throw(_("Invalid names format"))
    names = names or []

    approved, skipped = [], []
    for name in names:
        status = frappe.db.get_value("Employee Self Update Form", name, "status")
        if status != "Pending Review":
            skipped.append(name)
            continue
        frappe.db.set_value("Employee Self Update Form", name, "status", "Approved")
        approved.append(name)

    frappe.db.commit()
    return {"status": "success", "approved_count": len(approved), "skipped_count": len(skipped)}


@frappe.whitelist()
def reopen_form_bulk(names=None):
    """
    Re-open Approved or Synced forms back to Pending Review.
    All form data is preserved — only status is changed.
    """
    import json as _json

    _require_hr()
    if isinstance(names, str):
        try:
            names = _json.loads(names)
        except Exception:
            frappe.throw(_("Invalid names format"))
    names = names or []

    reopened, skipped = [], []
    for name in names:
        status = frappe.db.get_value("Employee Self Update Form", name, "status")
        if status not in ("Approved", "Synced"):
            skipped.append(name)
            continue
        frappe.db.set_value("Employee Self Update Form", name, "status", "Pending Review")
        reopened.append(name)

    frappe.db.commit()
    return {"status": "success", "reopened_count": len(reopened), "skipped_count": len(skipped)}


@frappe.whitelist()
def reject_form(form_name, reason=""):
    """Reject a form with a reason."""
    _require_hr()
    doc = frappe.get_doc("Employee Self Update Form", form_name)
    if doc.status != "Pending Review":
        frappe.throw(_("Chỉ form Pending Review mới có thể từ chối."))
    doc.status = "Rejected"
    doc.reject_reason = reason
    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "success"}


@frappe.whitelist()
def sync_to_employee(form_name):
    """
    Sync form data to Employee.
    Special handling: bank_name = Vietcombank, work_history_json → external_work_history.
    """
    import json as _json

    _require_hr()
    doc = frappe.get_doc("Employee Self Update Form", form_name)
    if doc.status != "Approved":
        frappe.throw(_("Chỉ form Approved mới có thể sync."))

    emp = frappe.get_doc("Employee", doc.employee)
    emp_meta = frappe.get_meta("Employee")
    valid_emp_fields = {f.fieldname for f in emp_meta.fields}
    # frappe.get_meta().fields only returns standard DocFields; custom fields live in
    # tabCustom Field and must be merged in separately to avoid being silently skipped.
    custom_field_names = frappe.db.sql(
        "SELECT fieldname FROM `tabCustom Field` WHERE dt='Employee'",
        as_list=True,
    )
    valid_emp_fields.update(row[0] for row in custom_field_names)

    synced = []
    for form_field, emp_field in _SYNC_MAP.items():
        val = doc.get(form_field)
        if emp_field in valid_emp_fields:
            emp.set(emp_field, val)
            synced.append(emp_field)

    # Special: bank_name always Vietcombank
    if "bank_name" in valid_emp_fields:
        emp.set("bank_name", "Vietcombank")

    # Special: work_history_json → external_work_history child table
    work_json = (doc.get("work_history_json") or "").strip()
    if work_json and work_json != "[]":
        try:
            rows = _json.loads(work_json)
            emp.set("external_work_history", [])
            for row in rows:
                emp.append("external_work_history", {
                    "company_name": row.get("company_name", ""),
                    "designation": row.get("designation", ""),
                    "total_experience": row.get("total_experience", ""),
                })
        except Exception:
            pass

    # Special: education_level / university / major → education child table (Employee Education)
    edu_level = (doc.get("education_level") or "").strip()
    edu_univ  = (doc.get("university") or "").strip()
    edu_major = (doc.get("major") or "").strip()
    if edu_level or edu_univ or edu_major:
        emp.set("education", [])
        emp.append("education", {
            "school_univ":    edu_univ,
            "level":          edu_level,
            "maj_opt_subj":   edu_major,
        })

    emp.flags.ignore_permissions = True
    emp.flags.ignore_mandatory = True
    emp.save()

    doc.status = "Synced"
    doc.flags.ignore_validate_update_after_submit = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "success", "synced_fields": synced, "message": _("Đã đồng bộ vào Employee thành công.")}


@frappe.whitelist()
def get_employees_by_date(date):
    """Return employees with date_of_joining == date (HR use)."""
    _require_hr()
    if not date:
        return []
    return frappe.get_all(
        "Employee",
        filters={"date_of_joining": date, "status": "Active"},
        fields=["name", "employee_name", "date_of_joining"],
        order_by="employee_name asc",
    )


@frappe.whitelist()
def add_employees_to_setting(employee_ids):
    """Add employees to Employee Self Update Setting employee list."""
    import json as _json

    _require_hr()
    if isinstance(employee_ids, str):
        employee_ids = _json.loads(employee_ids)

    setting = frappe.get_doc("Employee Self Update Setting")
    existing = {row.employee for row in (setting.employees or [])}
    added = 0
    for emp_id in employee_ids:
        if emp_id not in existing:
            setting.append("employees", {"employee": emp_id})
            added += 1
    setting.save(ignore_permissions=True)
    frappe.db.commit()
    return {"status": "success", "added": added}


@frappe.whitelist()
def download_excel(names=None):
    """Export Excel for selected (or all) forms."""
    import base64
    import json as _json

    _require_hr()

    filters = {}
    if names:
        names_list = _json.loads(names) if isinstance(names, str) else names
        if names_list:
            filters["name"] = ["in", names_list]

    records = frappe.get_all(
        "Employee Self Update Form",
        filters=filters,
        fields=[
            "employee", "employee_name", "date_of_joining", "cell_number", "status",
            "date_of_birth",
            "id_card_no", "id_card_date_of_issue", "id_card_place_of_issue",
            "id_card_cmnd_no", "id_card_cmnd_date_of_issue", "id_card_cmnd_place_of_issue",
            "marital_status", "number_of_childrens",
            "bank_ac_no", "bank_branch",
            "social_insurance_number", "tax_code",
            "education_level", "university", "major",
            "work_history_json",
            "current_address_province", "current_address_commune",
            "current_address_village", "current_address_full",
            "permanent_address_province", "permanent_address_commune",
            "permanent_address_village", "permanent_address_full",
            "place_of_origin_province", "place_of_origin_commune",
            "place_of_origin_village", "place_of_origin_full",
            "personal_email",
            "emergency_contact_name", "relation", "emergency_phone_number",
            "driving_license", "driving_license_note",
            "shirt_size", "shoe_size",
            "custom_strengths", "custom_favorite_sport", "custom_vegetarian",
        ],
        order_by="employee_name asc",
    )

    columns = [
        "Mã NV", "Họ tên", "Ngày gia nhập", "SĐT", "Trạng thái",
        "Ngày sinh",
        "Số CCCD", "Ngày cấp CCCD", "Nơi cấp CCCD",
        "Số CMND", "Ngày cấp CMND", "Nơi cấp CMND",
        "Hôn nhân", "Số con",
        "STK NH", "Chi nhánh NH",
        "Số BHXH", "Mã số thuế",
        "Trình độ", "Trường học", "Chuyên ngành",
        "Kinh nghiệm",
        "ĐC HT - Tỉnh/TP", "ĐC HT - Xã/Phường", "ĐC HT - Số nhà/Thôn", "ĐC HT - Đầy đủ",
        "ĐC HK - Tỉnh/TP", "ĐC HK - Xã/Phường", "ĐC HK - Số nhà/Thôn", "ĐC HK - Đầy đủ",
        "ĐC NQ - Tỉnh/TP", "ĐC NQ - Xã/Phường", "ĐC NQ - Số nhà/Thôn", "ĐC NQ - Đầy đủ",
        "Email cá nhân",
        "Liên hệ khẩn cấp", "Mối quan hệ", "SĐT liên hệ KK",
        "Có bằng lái", "Ghi chú bằng lái",
        "Size áo", "Size giày/dép",
        "Sở trường", "Môn thể thao", "Nhu cầu ăn chay",
    ]
    field_keys = [
        "employee", "employee_name", "date_of_joining", "cell_number", "status",
        "date_of_birth",
        "id_card_no", "id_card_date_of_issue", "id_card_place_of_issue",
        "id_card_cmnd_no", "id_card_cmnd_date_of_issue", "id_card_cmnd_place_of_issue",
        "marital_status", "number_of_childrens",
        "bank_ac_no", "bank_branch",
        "social_insurance_number", "tax_code",
        "education_level", "university", "major",
        "work_history_json",
        "current_address_province", "current_address_commune",
        "current_address_village", "current_address_full",
        "permanent_address_province", "permanent_address_commune",
        "permanent_address_village", "permanent_address_full",
        "place_of_origin_province", "place_of_origin_commune",
        "place_of_origin_village", "place_of_origin_full",
        "personal_email",
        "emergency_contact_name", "relation", "emergency_phone_number",
        "driving_license", "driving_license_note",
        "shirt_size", "shoe_size",
        "custom_strengths", "custom_favorite_sport", "custom_vegetarian",
    ]

    def _format_work_history(json_str):
        """Convert work_history_json to human-readable text, one entry per line."""
        if not json_str or not json_str.strip() or json_str.strip() == "[]":
            return ""
        try:
            entries = _json.loads(json_str)
            lines = []
            for e in entries:
                company = e.get("company_name", "").strip()
                designation = e.get("designation", "").strip()
                experience = e.get("total_experience", "").strip()
                parts = [p for p in [company, designation, experience] if p]
                if parts:
                    lines.append(" | ".join(parts))
            return "\n".join(lines)
        except Exception:
            return json_str

    data = [columns]
    for r in records:
        row = []
        for f in field_keys:
            v = r.get(f)
            if v is None:
                v = ""
            elif f == "work_history_json":
                v = _format_work_history(str(v))
            else:
                v = str(v)
            row.append(v)
        data.append(row)

    from frappe.utils.xlsxutils import make_xlsx
    xlsx_file = make_xlsx(data, "Employee Self Update")
    return {
        "filename": "employee_self_update.xlsx",
        "data": base64.b64encode(xlsx_file.getvalue()).decode("utf-8"),
    }


@frappe.whitelist()
def download_cccd_photos(names=None):
    """Return base64-encoded ZIP of CCCD photos for selected (or all) forms."""
    import base64
    import io
    import json as _json
    import os
    import zipfile
    from urllib.parse import unquote

    _require_hr()

    filters = {}
    if names:
        names_list = _json.loads(names) if isinstance(names, str) else names
        if names_list:
            filters["name"] = ["in", names_list]

    records = frappe.get_all(
        "Employee Self Update Form",
        filters=filters,
        fields=["employee", "employee_name", "id_card_front_photo", "id_card_back_photo"],
        order_by="employee_name asc",
    )

    site_path = frappe.get_site_path()
    buf = io.BytesIO()
    added = 0

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in records:
            for url_field in ("id_card_front_photo", "id_card_back_photo"):
                file_url = r.get(url_field)
                if not file_url:
                    continue
                decoded_url = unquote(file_url)
                if decoded_url.startswith("/private/"):
                    abs_path = os.path.join(site_path, decoded_url.lstrip("/"))
                else:
                    abs_path = os.path.join(site_path, "public", decoded_url.lstrip("/"))
                if not os.path.exists(abs_path):
                    continue
                zf.write(abs_path, os.path.basename(abs_path))
                added += 1

    if added == 0:
        frappe.throw(_("Không có ảnh CCCD nào để tải."))

    return {
        "filename": "CCCD_self_update.zip",
        "data": base64.b64encode(buf.getvalue()).decode("utf-8"),
    }


@frappe.whitelist()
def generate_qr_codes(names=None):
    """Generate HTML with QR code links for selected forms (printable)."""
    import json as _json

    _require_hr()

    if not names:
        frappe.throw(_("Vui lòng chọn ít nhất 1 form."))

    names_list = _json.loads(names) if isinstance(names, str) else names
    records = frappe.get_all(
        "Employee Self Update Form",
        filters={"name": ["in", names_list]},
        fields=["employee", "employee_name"],
        order_by="employee_name asc",
    )

    site_url = frappe.utils.get_url()
    items_html = ""
    for r in records:
        link = f"{site_url}/employee-self-update?emp={r.employee}"
        items_html += f"""
        <div style="display:inline-block;margin:12px;text-align:center;width:200px;vertical-align:top;">
            <img src="https://api.qrserver.com/v1/create-qr-code/?size=160x160&data={link}"
                 width="160" height="160" alt="{r.employee}">
            <div style="margin-top:6px;font-size:13px;font-weight:600;">{r.employee_name}</div>
            <div style="font-size:11px;color:#666;">{r.employee}</div>
        </div>"""

    html = f"""
    <div style="font-family:sans-serif;padding:16px;">
        <h3 style="margin-bottom:16px;">QR Codes — Employee Self Update</h3>
        <p style="color:#666;font-size:13px;margin-bottom:20px;">
            Nhân viên quét QR để truy cập trực tiếp form cập nhật thông tin.
        </p>
        <div>{items_html}</div>
        <div style="margin-top:20px;">
            <button onclick="window.print()" style="padding:8px 20px;cursor:pointer;">In QR</button>
        </div>
    </div>
    """
    return {"html": html}
