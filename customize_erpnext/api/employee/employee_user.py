import json

import frappe
from frappe import _


def _parse_employee_ids(raw):
    if not raw:
        return []
    text = str(raw).replace(",", "\n")
    return [line.strip() for line in text.split("\n") if line.strip()]


def _build_filters(department=None, custom_section=None, custom_group=None, employee_ids=None):
    filters = {"status": "Active"}

    ids = _parse_employee_ids(employee_ids)
    if ids:
        filters["name"] = ["in", ids]
        return filters

    if department:
        filters["department"] = department
    if custom_section:
        filters["custom_section"] = custom_section
    if custom_group:
        filters["custom_group"] = custom_group

    return filters


@frappe.whitelist()
def preview_employees_for_user_generation(
    department=None, custom_section=None, custom_group=None, employee_ids=None
):
    """Return list of Employee docnames that match the filters (status=Active)."""
    filters = _build_filters(department, custom_section, custom_group, employee_ids)

    employees = frappe.get_all(
        "Employee",
        filters=filters,
        fields=["name"],
        order_by="name asc",
        limit_page_length=0,
    )
    return [e.name for e in employees]


@frappe.whitelist()
def generate_users_from_employees(employee_list, role_profile="TIQN All Employee"):
    """Create Frappe Users from a list of Employee docnames.

    For each Employee:
        - If company_email exists → skip (use company_email instead, don't create from personal).
        - If personal_email missing or invalid (no '@') → skip.
        - If User already exists & enabled & has role profile & Employee.user_id linked → skip.
        - If User already exists but is disabled / missing role profile / Employee.user_id not linked
          → reactivate: enable, add role profile, link Employee.user_id.
        - Else create User, link Employee.user_id, assign role profile.
    """
    if isinstance(employee_list, str):
        try:
            employee_list = json.loads(employee_list)
        except (ValueError, TypeError):
            employee_list = [employee_list]

    if not employee_list:
        frappe.throw(_("Employee list is empty"))

    if not role_profile:
        role_profile = "TIQN All Employee"

    if not frappe.db.exists("Role Profile", role_profile):
        frappe.throw(_("Role Profile {0} does not exist").format(role_profile))

    result = {
        "created": [],
        "reactivated": [],
        "skipped_company_email": [],
        "skipped_no_email": [],
        "skipped_invalid_email": [],
        "skipped_exists": [],
        "errors": [],
    }

    for emp_name in employee_list:
        try:
            emp = frappe.db.get_value(
                "Employee",
                emp_name,
                [
                    "name",
                    "employee_name",
                    "first_name",
                    "last_name",
                    "company_email",
                    "personal_email",
                    "user_id",
                ],
                as_dict=True,
            )

            if not emp:
                result["errors"].append({"employee": emp_name, "error": _("Employee not found")})
                continue

            label = f"{emp.name} - {emp.employee_name or ''}".strip(" -")

            if emp.company_email:
                result["skipped_company_email"].append(label)
                continue

            if not emp.personal_email:
                result["skipped_no_email"].append(label)
                continue

            email = emp.personal_email.strip().lower()

            if "@" not in email or "." not in email.split("@", 1)[-1]:
                result["skipped_invalid_email"].append(f"{label} ({email})")
                continue

            if frappe.db.exists("User", email):
                user = frappe.get_doc("User", email)
                changed = False

                if not user.enabled:
                    user.enabled = 1
                    changed = True

                existing_profiles = {p.role_profile for p in (user.role_profiles or [])}
                if role_profile not in existing_profiles:
                    user.append("role_profiles", {"role_profile": role_profile})
                    changed = True

                if changed:
                    user.save(ignore_permissions=True)

                if emp.user_id != email:
                    frappe.db.set_value("Employee", emp.name, "user_id", email, update_modified=True)
                    frappe.clear_document_cache("Employee", emp.name)
                    changed = True

                frappe.db.commit()

                if changed:
                    result["reactivated"].append(f"{label} ({email})")
                else:
                    result["skipped_exists"].append(f"{label} ({email})")
                continue

            user = frappe.get_doc(
                {
                    "doctype": "User",
                    "email": email,
                    "first_name": emp.first_name or emp.employee_name or email.split("@")[0],
                    "last_name": emp.last_name or "",
                    "enabled": 1,
                    "send_welcome_email": 1,
                    "role_profiles": [{"role_profile": role_profile}],
                }
            )
            user.insert(ignore_permissions=True)

            frappe.db.set_value("Employee", emp.name, "user_id", email, update_modified=True)
            frappe.clear_document_cache("Employee", emp.name)
            frappe.db.commit()

            verified_user_id = frappe.db.get_value("Employee", emp.name, "user_id")
            if verified_user_id != email:
                raise Exception(
                    f"user_id verification failed: expected {email}, got {verified_user_id!r}"
                )

            result["created"].append(f"{label} ({email})")

        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(
                title=f"generate_users_from_employees: {emp_name}",
                message=frappe.get_traceback(),
            )
            result["errors"].append({"employee": emp_name, "error": str(e)})

    return result
