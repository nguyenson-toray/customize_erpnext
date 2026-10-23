import frappe
import json


@frappe.whitelist()
def send_biometric_error_report(subject, body, recipients=None):
    """
    Nhận nội dung lỗi từ biometric sync tool và gửi email qua frappe.sendmail.
    Được gọi qua REST API từ biometric-attendance-sync-tool.

    Args:
        subject (str): Tiêu đề email
        body (str): Nội dung email (plain text)
        recipients (str|list): JSON string hoặc list email nhận. Nếu None dùng default.
    """
    # Caller = the retired sync tool with Administrator's API key. Without this any
    # logged-in user could send arbitrary mail to arbitrary recipients (found 23/10/2026).
    frappe.only_for("System Manager")

    default_recipients = ["son.nt@tiqn.com.vn", "vinh.son@tiqn.com.vn"]

    if recipients:
        if isinstance(recipients, str):
            try:
                recipient_list = json.loads(recipients)
            except (json.JSONDecodeError, ValueError):
                recipient_list = [r.strip() for r in recipients.split(',') if r.strip()]
        else:
            recipient_list = list(recipients)
    else:
        recipient_list = default_recipients

    if not recipient_list:
        frappe.throw("No recipients specified")

    # Wrap plain text body in minimal HTML for readability
    html_body = f"""<html><body><pre style="font-family: monospace; font-size: 13px; white-space: pre-wrap;">{frappe.utils.escape_html(body)}</pre></body></html>"""

    frappe.sendmail(
        recipients=recipient_list,
        subject=subject,
        message=html_body,
        delayed=False
    )

    frappe.logger().info(f"Biometric error report sent to {recipient_list}: {subject}")
    return {"status": "ok", "recipients": recipient_list}
