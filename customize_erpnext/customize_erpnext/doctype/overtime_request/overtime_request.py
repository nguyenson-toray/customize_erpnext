# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate, now

def validate_ot_level_for_date(ot_level, ot_date):
    """Validate if OT level is allowed for the given date"""
    from frappe.utils import getdate
    
    ot_date = getdate(ot_date)
    
    # Check if it's Sunday (only weekend day for your company)
    is_sunday = ot_date.weekday() == 6  # 6 = Sunday
    
    if is_sunday and not ot_level.is_weekend_allowed:
        frappe.throw(f"OT Level '{ot_level.level_name}' is not allowed on Sundays")
    
    # Check holiday
    holiday_list = frappe.get_cached_value("Company", 
        frappe.defaults.get_user_default("Company"), "default_holiday_list")
    
    if holiday_list:
        is_holiday = frappe.get_all("Holiday", filters={
            "holiday_date": ot_date,
            "parent": holiday_list
        })
        
        if is_holiday and not ot_level.is_holiday_allowed:
            frappe.throw(f"OT Level '{ot_level.level_name}' is not allowed on holidays")

def get_adjusted_rate_multiplier(base_multiplier, ot_date):
    """Calculate adjusted rate multiplier based on date type"""
    from frappe.utils import getdate
    
    ot_date = getdate(ot_date)
    multiplier = base_multiplier
    
    # Check if it's Sunday (Weekend)
    is_sunday = ot_date.weekday() == 6  # 6 = Sunday
    
    # Check holiday
    holiday_list = frappe.get_cached_value("Company", 
        frappe.defaults.get_user_default("Company"), "default_holiday_list")
    
    is_holiday = False
    if holiday_list:
        holidays = frappe.get_all("Holiday", filters={
            "holiday_date": ot_date,
            "parent": holiday_list
        })
        is_holiday = bool(holidays)
    
    # Priority: Holiday > Weekend
    if is_holiday:
        multiplier = 3.0  # Holiday rate
    elif is_sunday:
        multiplier = 2.0  # Weekend rate
    
    return multiplier

def overtime_request_permission(doc, ptype="read", user=None):
    """
    Custom permission logic cho Overtime Request
    Ghi đè hoàn toàn User Permission system
    """
    if not user:
        user = frappe.session.user
    
    # Administrator luôn có quyền
    if user == "Administrator":
        return True
    
    user_roles = frappe.get_roles(user)
    
    # System roles có full access
    if any(role in user_roles for role in ["System Manager", "HR Manager"]):
        return True
    
    # Manager roles có broad access
    manager_roles = ["Department Manager", "Factory Manager", "TIQN Manager", "TIQN Factory Manager"]
    if any(role in user_roles for role in manager_roles):
        return True
    
    # Employee role logic
    if "Employee" in user_roles:
        current_employee = frappe.get_value("Employee", {"user_id": user}, "name")
        if not current_employee:
            return False
        
        # Allow access to own requests
        if hasattr(doc, 'requested_by') and doc.requested_by == current_employee:
            return True
        
        # Allow access if assigned as approver
        if hasattr(doc, 'manager_approver') and doc.manager_approver:
            if doc.manager_approver.startswith(current_employee):
                return True
        
        if hasattr(doc, 'factory_manager_approver') and doc.factory_manager_approver:
            if doc.factory_manager_approver.startswith(current_employee):
                return True
    
    return False

def get_permission_query_conditions(user):
    """
    COMPLETELY BYPASS User Permissions for Overtime Request
    This function is called by ERPNext framework to filter records
    """
    
    # FOR DEBUGGING: Log when this function is called
    frappe.log_error(f"Permission Query Called for user: {user}", "Permission Debug")
    
    if not user:
        user = frappe.session.user
    
    # Administrator sees everything
    if user == "Administrator":
        return ""
    
    user_roles = frappe.get_roles(user)
    
    # System roles see everything
    if any(role in user_roles for role in ["System Manager", "HR Manager"]):
        return ""
    
    # Get current user's employee
    current_employee = frappe.get_value("Employee", {"user_id": user}, "name")
    
    if not current_employee:
        # If no employee record, no access
        return "1=0"
    
    conditions = []
    
    # Manager roles see all
    manager_roles = ["Department Manager", "Factory Manager", "TIQN Manager", "TIQN Factory Manager"]
    if any(role in user_roles for role in manager_roles):
        return ""  # See all records
    
    # Regular employees see own requests + assigned approvals
    if "Employee" in user_roles:
        # Own requests
        conditions.append(f"`tabOvertime Request`.`requested_by` = '{current_employee}'")
        
        # Manager approver assignments (extract ID before " - ")
        conditions.append(f"`tabOvertime Request`.`manager_approver` LIKE '{current_employee} -%'")
        
        # Factory manager approver assignments
        conditions.append(f"`tabOvertime Request`.`factory_manager_approver` LIKE '{current_employee} -%'")
    
    if conditions:
        return "(" + " OR ".join(conditions) + ")"
    else:
        return "1=0"  # No access

def create_system_notification(user, subject, message, document_type, document_name, notification_type):
    """Create system notification that appears in the notification bell"""
    try:
        # Create notification log entry
        notification_doc = frappe.get_doc({
            "doctype": "Notification Log",
            "subject": subject,
            "for_user": user,
            "type": "Alert",
            "document_type": document_type,
            "document_name": document_name,
            "from_user": frappe.session.user,
            "email_content": message,
            "read": 0
        })
        
        notification_doc.insert(ignore_permissions=True)
        
        # Also create a simple desktop notification for immediate popup
        frappe.publish_realtime(
            event="msgprint",
            message={
                "title": subject,
                "message": message,
                "indicator": get_notification_indicator(notification_type)
            },
            user=user
        )
        
        return notification_doc.name
        
    except Exception as e:
        frappe.log_error(f"Error creating system notification: {str(e)}")
        return None

def get_notification_indicator(notification_type):
    """Get notification indicator color based on type"""
    indicators = {
        "Approval Required": "orange",
        "Final Approval Required": "blue", 
        "Approved": "green",
        "Rejected": "red",
        "Cancelled": "grey"
    }
    return indicators.get(notification_type, "blue")

class OvertimeRequest(Document):
    def validate(self):
        self.validate_ot_date()
        self.validate_employees()
        self.validate_ot_levels_for_date()
        self.adjust_rate_multipliers()
        self.calculate_totals()
        self.set_default_approvers()

    def has_permission(self, ptype, user=None):
        """
        DOCUMENT-LEVEL PERMISSION CHECK - Fixed version
        """
        if not user:
            user = frappe.session.user
        
        # 1. Administrator always has access
        if user == "Administrator":
            return True
        
        user_roles = frappe.get_roles(user)
        
        # 2. HR roles have full access
        if any(role in user_roles for role in ["System Manager", "HR Manager"]):
            return True
        
        # 3. Get current user's employee record
        current_employee = frappe.get_value("Employee", {"user_id": user}, "name")
        
        if not current_employee:
            return False
        
        # 4. CREATE permission
        if ptype == "create":
            if "Employee" in user_roles:
                return True
            manager_roles = ["Department Manager", "Factory Manager", "TIQN Manager", "TIQN Factory Manager"]
            if any(role in user_roles for role in manager_roles):
                return True
            return False

        # 5. READ permission
        if ptype == "read":
            # Own requests
            if hasattr(self, 'requested_by') and self.requested_by == current_employee:
                return True
            
            # FIXED: Check if user is assigned as manager_approver
            if hasattr(self, 'manager_approver') and self.manager_approver:
                # Extract employee ID from format: "TIQN-0148 - Name (Designation)"
                if self.manager_approver.startswith(current_employee):
                    return True
            
            # FIXED: Check if user is assigned as factory_manager_approver  
            if hasattr(self, 'factory_manager_approver') and self.factory_manager_approver:
                # Extract employee ID from format: "TIQN-1269 - Name (Designation)"
                if self.factory_manager_approver.startswith(current_employee):
                    return True
            
            # Manager roles can see all requests in their scope
            manager_roles = ["Department Manager", "Factory Manager", "TIQN Manager", "TIQN Factory Manager"]
            if any(role in user_roles for role in manager_roles):
                return True
            
            return False
        
        # 6. WRITE, SUBMIT, CANCEL permissions 
        if ptype in ["write", "submit", "cancel"]:
            doc_status = getattr(self, 'docstatus', 0)
            
            # Owner permissions
            if hasattr(self, 'requested_by') and self.requested_by == current_employee:
                # Owner can cancel anytime
                if ptype == "cancel":
                    return True
                
                # Owner can write/submit draft documents
                if doc_status == 0:  # Draft
                    return True
            
            # Approver permissions for submitted documents
            if doc_status == 1:  # Submitted
                status = getattr(self, 'status', '')
                
                # Manager approver permission
                if (hasattr(self, 'manager_approver') and 
                    self.manager_approver and
                    self.manager_approver.startswith(current_employee) and 
                    status == "Pending Manager Approval"):
                    return True
                
                # Factory manager approver permission
                if (hasattr(self, 'factory_manager_approver') and 
                    self.factory_manager_approver and
                    self.factory_manager_approver.startswith(current_employee) and 
                    status == "Pending Factory Manager Approval"):
                    return True
            
            return False
        
        return False

    def set_default_approvers(self):
        """Set default approvers if not already set"""
        if not self.manager_approver and self.requested_by:
            # Try to get manager from employee's reports_to field
            try:
                employee = frappe.get_doc("Employee", self.requested_by)
                if employee.reports_to:
                    # Check if reports_to has Manager in designation
                    manager_emp = frappe.get_doc("Employee", employee.reports_to)
                    if manager_emp.designation and "Manager" in manager_emp.designation:
                        self.manager_approver = employee.reports_to
            except:
                pass
        
        if not self.factory_manager_approver:
            # Get first available Factory Manager
            try:
                factory_managers = get_factory_managers("Employee", "", "name", 0, 1, {})
                if factory_managers:
                    self.factory_manager_approver = factory_managers[0][0]
            except:
                pass

    def adjust_rate_multipliers(self):
        """Adjust rate multipliers based on OT date"""
        if not self.ot_date:
            return
            
        for row in self.ot_employees:
            if row.ot_level and self.ot_configuration:
                # Get base multiplier from OT Configuration
                base_multiplier = self.get_ot_level_multiplier(row.ot_level)
                
                # Calculate adjusted multiplier
                adjusted_multiplier = get_adjusted_rate_multiplier(base_multiplier, self.ot_date)
                
                # Update if different
                if adjusted_multiplier != row.rate_multiplier:
                    row.rate_multiplier = adjusted_multiplier

    def get_ot_level_multiplier(self, ot_level_name):
        """Get rate multiplier for a specific OT level"""
        if not self.ot_configuration:
            return 1.0
            
        try:
            ot_config = frappe.get_doc("Overtime Configuration", self.ot_configuration)
            for level in ot_config.overtime_levels:
                if level.level_name == ot_level_name:
                    return level.rate_multiplier
        except:
            pass
            
        return 1.0

    def validate_ot_date(self):
        """Validate OT date is not in the past"""
        if self.ot_date and getdate(self.ot_date) < getdate():
            frappe.throw("OT Date cannot be in the past")
    
    def validate_employees(self):
        """Validate employees in the table"""
        if not self.ot_employees:
            frappe.throw("Please add at least one employee for overtime")
        
        # Check for duplicate employees
        employee_list = []
        for row in self.ot_employees:
            if row.employee in employee_list:
                frappe.throw(f"Employee {row.employee} is added multiple times")
            employee_list.append(row.employee)
            
            # Validate planned hours
            if not row.planned_hours or row.planned_hours <= 0:
                frappe.throw(f"Planned hours must be greater than 0 for employee {row.employee}")
            
            # Validate OT level
            if not row.ot_level:
                frappe.throw(f"Please select OT Level for employee {row.employee}")
    
    def validate_ot_levels_for_date(self):
        """Validate OT levels are allowed for the selected date"""
        if not self.ot_date or not self.ot_configuration:
            return
            
        try:
            ot_config = frappe.get_doc("Overtime Configuration", self.ot_configuration)
            
            for row in self.ot_employees:
                if row.ot_level:
                    # Find the OT level in configuration
                    ot_level = None
                    for level in ot_config.overtime_levels:
                        if level.level_name == row.ot_level:
                            ot_level = level
                            break
                    
                    if ot_level:
                        validate_ot_level_for_date(ot_level, self.ot_date)
                    else:
                        frappe.throw(f"OT Level '{row.ot_level}' not found in configuration")
        except Exception as e:
            frappe.log_error(f"Error validating OT levels: {str(e)}")
    
    def calculate_totals(self):
        """Calculate total employees and hours"""
        self.total_employees = len(self.ot_employees)
        self.total_hours = sum([row.planned_hours or 0 for row in self.ot_employees])
    
    def before_submit(self):
        """Actions before document is submitted"""
        self.status = "Pending Manager Approval"
    
    def on_submit(self):
        """Actions when document is submitted"""
        # Set status
        self.status = "Pending Manager Approval"
        
        # Share document with approvers
        self.share_with_approvers()
        
        # Send notification to Department Manager
        self.send_manager_approval_notification()
        
        frappe.msgprint("Overtime request submitted successfully. Department Manager has been notified.")
    
    def on_cancel(self):
        """Actions when document is cancelled"""
        self.status = "Cancelled"
        
        # Notify requester
        self.send_cancellation_notification()

    def send_manager_approval_notification(self):
        """Send email AND system notification to Department Manager"""
        try:
            if self.manager_approver:
                # Extract employee ID from manager_approver field
                manager_employee_id = self.manager_approver.split(' - ')[0] if ' - ' in self.manager_approver else self.manager_approver
                
                manager_email = frappe.get_value("Employee", manager_employee_id, "user_id")
                manager_name = frappe.get_value("Employee", manager_employee_id, "employee_name")
                requester_name = frappe.get_value("Employee", self.requested_by, "employee_name")
                
                if manager_email:
                    subject = f"Overtime Request Approval Required - {self.name}"
                    
                    # 1. Send EMAIL (existing)
                    email_message = f"""
                    Dear {manager_name},
                    
                    An overtime request requires your approval:
                    
                    Request ID: {self.name}
                    Requested by: {requester_name} ({self.requested_by})
                    OT Date: {self.ot_date}
                    Total Employees: {self.total_employees}
                    Total Hours: {self.total_hours}
                    Reason: {self.reason}
                    
                    Please review: {frappe.utils.get_url()}/app/overtime-request/{self.name}
                    
                    Best regards, HR System
                    """
                    
                    frappe.sendmail(
                        recipients=[manager_email],
                        subject=subject,
                        message=email_message
                    )
                    
                    # 2. Send SYSTEM NOTIFICATION (NEW)
                    try:
                        create_system_notification(
                            user=manager_email,
                            subject=f"🔔 Overtime Approval Required",
                            message=f"Request {self.name} from {requester_name} needs your approval",
                            document_type=self.doctype,
                            document_name=self.name,
                            notification_type="Approval Required"
                        )
                    except Exception as notif_error:
                        frappe.log_error(f"System notification error: {str(notif_error)}")
                    
                    # 3. Send POPUP (NEW)
                    try:
                        frappe.publish_realtime(
                            event="msgprint",
                            message=f"🔔 New overtime request {self.name} needs your approval",
                            user=manager_email
                        )
                    except Exception as popup_error:
                        frappe.log_error(f"Popup error: {str(popup_error)}")
                        
        except Exception as e:
            frappe.log_error(f"Manager notification error: {str(e)}")

    def send_factory_manager_approval_notification(self):
        """Send email AND system notification to Factory Manager"""
        try:
            if self.factory_manager_approver:
                # Extract employee ID from factory_manager_approver field
                factory_manager_employee_id = self.factory_manager_approver.split(' - ')[0] if ' - ' in self.factory_manager_approver else self.factory_manager_approver
                
                factory_manager_email = frappe.get_value("Employee", factory_manager_employee_id, "user_id")
                factory_manager_name = frappe.get_value("Employee", factory_manager_employee_id, "employee_name")
                requester_name = frappe.get_value("Employee", self.requested_by, "employee_name")
                manager_name = frappe.get_value("Employee", self.manager_approver.split(' - ')[0] if ' - ' in self.manager_approver else self.manager_approver, "employee_name")
                
                if factory_manager_email:
                    subject = f"Overtime Request Final Approval Required - {self.name}"
                    message = f"""
                    Dear {factory_manager_name},
                    
                    An overtime request requires your final approval:
                    
                    Request ID: {self.name}
                    Requested by: {requester_name} ({self.requested_by})
                    OT Date: {self.ot_date}
                    Total Employees: {self.total_employees}
                    Total Hours: {self.total_hours}
                    Reason: {self.reason}
                    
                    Department Manager ({manager_name}) has already approved this request.
                    
                    Please review: {frappe.utils.get_url()}/app/overtime-request/{self.name}
                    
                    Best regards, HR System
                    """
                    
                    # 1. Send EMAIL
                    frappe.sendmail(
                        recipients=[factory_manager_email],
                        subject=subject,
                        message=message
                    )
                    
                    # 2. Send SYSTEM NOTIFICATION
                    try:
                        create_system_notification(
                            user=factory_manager_email,
                            subject=f"🔔 Final Overtime Approval Required",
                            message=f"Request {self.name} from {requester_name} needs final approval",
                            document_type=self.doctype,
                            document_name=self.name,
                            notification_type="Final Approval Required"
                        )
                    except Exception as notif_error:
                        frappe.log_error(f"Factory manager system notification error: {str(notif_error)}")
                    
                    # 3. Send POPUP
                    try:
                        frappe.publish_realtime(
                            event="msgprint",
                            message=f"🔔 Overtime request {self.name} needs final approval",
                            user=factory_manager_email
                        )
                    except Exception as popup_error:
                        frappe.log_error(f"Factory manager popup error: {str(popup_error)}")
                    
        except Exception as e:
            frappe.log_error(f"Error sending factory manager approval notification: {str(e)}")

    def send_final_approval_notification(self):
        """Send notification when fully approved"""
        try:
            recipients = []
            
            # Get requester's email
            requester_email = frappe.get_value("Employee", self.requested_by, "user_id")
            requester_name = frappe.get_value("Employee", self.requested_by, "employee_name")
            
            if requester_email:
                recipients.append(requester_email)
            
            # Get HR users emails
            hr_emails = self.get_hr_users_emails()
            recipients.extend(hr_emails)
            
            # Remove duplicates
            recipients = list(set(recipients))
            
            if recipients:
                subject = f"Overtime Request Approved - {self.name}"
                message = f"""
                Dear Team,
                
                Your overtime request has been fully approved:
                
                Request ID: {self.name}
                Requested by: {requester_name} ({self.requested_by})
                OT Date: {self.ot_date}
                Total Employees: {self.total_employees}
                Total Hours: {self.total_hours}
                
                Status: Approved
                Manager Approved: {self.manager_approved_on}
                Factory Manager Approved: {self.factory_manager_approved_on}
                
                The overtime entries have been created for all employees.
                
                Best regards,
                HR System
                """
                
                # 1. Send EMAIL notification
                frappe.sendmail(
                    recipients=recipients,
                    subject=subject,
                    message=message
                )
                
                # 2. Send SYSTEM notifications
                for recipient in recipients:
                    try:
                        create_system_notification(
                            user=recipient,
                            subject=f"🎉 Overtime Request Approved",
                            message=f"Request {self.name} has been fully approved",
                            document_type=self.doctype,
                            document_name=self.name,
                            notification_type="Approved"
                        )
                        
                        # 3. Send REAL-TIME notification
                        frappe.publish_realtime(
                            event="overtime_approved",
                            message={
                                "request_id": self.name,
                                "message": f"Overtime request {self.name} has been approved"
                            },
                            user=recipient
                        )
                    except Exception as notif_error:
                        frappe.log_error(f"Error sending final approval notification to {recipient}: {str(notif_error)}")
                
        except Exception as e:
            frappe.log_error(f"Error sending final approval notification: {str(e)}")

    def send_rejection_notification(self, rejection_type, comments):
        """Send notification when request is rejected"""
        try:
            # Get requester's email
            requester_email = frappe.get_value("Employee", self.requested_by, "user_id")
            requester_name = frappe.get_value("Employee", self.requested_by, "employee_name")
            
            if requester_email:
                rejector_name = ""
                if rejection_type == "manager":
                    manager_id = self.manager_approver.split(' - ')[0] if ' - ' in self.manager_approver else self.manager_approver
                    rejector_name = frappe.get_value("Employee", manager_id, "employee_name")
                elif rejection_type == "factory_manager":
                    factory_manager_id = self.factory_manager_approver.split(' - ')[0] if ' - ' in self.factory_manager_approver else self.factory_manager_approver
                    rejector_name = frappe.get_value("Employee", factory_manager_id, "employee_name")
                
                subject = f"Overtime Request Rejected - {self.name}"
                message = f"""
                Dear {requester_name},
                
                Your overtime request has been rejected:
                
                Request ID: {self.name}
                OT Date: {self.ot_date}
                Total Employees: {self.total_employees}
                Total Hours: {self.total_hours}
                
                Rejected by: {rejector_name} ({rejection_type.replace('_', ' ').title()})
                Rejection Comments: {comments}
                
                You can review and modify your request:
                {frappe.utils.get_url()}/app/overtime-request/{self.name}
                
                Best regards,
                HR System
                """
                
                # 1. Send EMAIL notification
                frappe.sendmail(
                    recipients=[requester_email],
                    subject=subject,
                    message=message
                )
                
                # 2. Send SYSTEM notification
                try:
                    create_system_notification(
                        user=requester_email,
                        subject=f"❌ Overtime Request Rejected",
                        message=f"Request {self.name} was rejected by {rejector_name}",
                        document_type=self.doctype,
                        document_name=self.name,
                        notification_type="Rejected"
                    )
                    
                    # 3. Send REAL-TIME notification
                    frappe.publish_realtime(
                        event="overtime_rejected",
                        message={
                            "request_id": self.name,
                            "rejector": rejector_name,
                            "comments": comments,
                            "message": f"Your overtime request {self.name} was rejected"
                        },
                        user=requester_email
                    )
                except Exception as notif_error:
                    frappe.log_error(f"Error sending rejection notification: {str(notif_error)}")
                
        except Exception as e:
            frappe.log_error(f"Error sending rejection notification: {str(e)}")

    def send_cancellation_notification(self):
        """Send notification when request is cancelled"""
        try:
            # Notify all stakeholders
            recipients = []
            
            # Get requester's email
            requester_email = frappe.get_value("Employee", self.requested_by, "user_id")
            if requester_email:
                recipients.append(requester_email)
            
            # Get approvers' emails
            if self.manager_approver:
                manager_id = self.manager_approver.split(' - ')[0] if ' - ' in self.manager_approver else self.manager_approver
                manager_email = frappe.get_value("Employee", manager_id, "user_id")
                if manager_email:
                    recipients.append(manager_email)
            
            if self.factory_manager_approver:
                factory_manager_id = self.factory_manager_approver.split(' - ')[0] if ' - ' in self.factory_manager_approver else self.factory_manager_approver
                factory_manager_email = frappe.get_value("Employee", factory_manager_id, "user_id")
                if factory_manager_email:
                    recipients.append(factory_manager_email)
            
            # Remove duplicates
            recipients = list(set(recipients))
            
            if recipients:
                requester_name = frappe.get_value("Employee", self.requested_by, "employee_name")
                
                subject = f"Overtime Request Cancelled - {self.name}"
                message = f"""
                Dear Team,
                
                The following overtime request has been cancelled:
                
                Request ID: {self.name}
                Requested by: {requester_name} ({self.requested_by})
                OT Date: {self.ot_date}
                Total Employees: {self.total_employees}
                Total Hours: {self.total_hours}
                
                Status: Cancelled
                
                Best regards,
                HR System
                """
                
                # 1. Send EMAIL notification
                frappe.sendmail(
                    recipients=recipients,
                    subject=subject,
                    message=message
                )
                
                # 2. Send SYSTEM notifications
                for recipient in recipients:
                    try:
                        create_system_notification(
                            user=recipient,
                            subject=f"⭕ Overtime Request Cancelled",
                            message=f"Request {self.name} has been cancelled",
                            document_type=self.doctype,
                            document_name=self.name,
                            notification_type="Cancelled"
                        )
                        
                        # 3. Send REAL-TIME notification
                        frappe.publish_realtime(
                            event="overtime_cancelled",
                            message={
                                "request_id": self.name,
                                "message": f"Overtime request {self.name} has been cancelled"
                            },
                            user=recipient
                        )
                    except Exception as notif_error:
                        frappe.log_error(f"Error sending cancellation notification to {recipient}: {str(notif_error)}")
                
        except Exception as e:
            frappe.log_error(f"Error sending cancellation notification: {str(e)}")

    def get_hr_users_emails(self):
        """Get emails of all HR users"""
        try:
            # Get all employees with HR in designation
            hr_employees = frappe.get_all("Employee",
                filters={
                    "status": "Active",
                    "user_id": ["!=", ""]
                },
                fields=["user_id", "designation"]
            )
            
            hr_emails = []
            for emp in hr_employees:
                if emp.designation and "HR" in emp.designation.upper():
                    if emp.user_id:
                        hr_emails.append(emp.user_id)
            
            return hr_emails
            
        except Exception as e:
            frappe.log_error(f"Error getting HR users emails: {str(e)}")
            return []

    def share_with_approvers(self):
        """Share document with all approvers for access"""
        try:
            users_to_share = []
            
            # Add manager approver
            if self.manager_approver:
                manager_id = self.manager_approver.split(' - ')[0] if ' - ' in self.manager_approver else self.manager_approver
                manager_user = frappe.get_value("Employee", manager_id, "user_id")
                if manager_user:
                    users_to_share.append(manager_user)
            
            # Add factory manager approver  
            if self.factory_manager_approver:
                factory_manager_id = self.factory_manager_approver.split(' - ')[0] if ' - ' in self.factory_manager_approver else self.factory_manager_approver
                factory_manager_user = frappe.get_value("Employee", factory_manager_id, "user_id")
                if factory_manager_user:
                    users_to_share.append(factory_manager_user)
            
            # Add HR users
            hr_users = self.get_hr_users_emails()
            users_to_share.extend(hr_users)
            
            # Remove duplicates and requester (already has access)
            requester_user = frappe.get_value("Employee", self.requested_by, "user_id")
            users_to_share = list(set(users_to_share))
            if requester_user in users_to_share:
                users_to_share.remove(requester_user)
            
            # Share with each user
            for user in users_to_share:
                if user:
                    try:
                        # Add document share
                        frappe.share.add(
                            doctype=self.doctype,
                            name=self.name,
                            user=user,
                            read=1,
                            write=1,  # Allow approvers to write (approve/reject)
                            submit=0,
                            share=0,
                            flags={"ignore_share_permission": True}
                        )
                        
                        frappe.log_error(f"Shared {self.name} with user {user}", "Document Share Success")
                        
                    except Exception as e:
                        frappe.log_error(f"Error sharing {self.name} with user {user}: {str(e)}", "Document Share Error")
            
            # Commit the share changes
            frappe.db.commit()
            
        except Exception as e:
            frappe.log_error(f"Error in share_with_approvers: {str(e)}", "Share Approvers Error")

# ===== WHITELIST METHODS =====

@frappe.whitelist()
def simple_test():
    """Simple test method to verify file is working"""
    return {
        "message": "File is accessible!", 
        "user": frappe.session.user,
        "timestamp": frappe.utils.now()
    }

@frappe.whitelist()
def test_notification():
    """Test notification system"""
    try:
        current_user = frappe.session.user
        
        # Create notification
        doc = frappe.get_doc({
            "doctype": "Notification Log",
            "subject": "🔔 Test System Notification",
            "for_user": current_user,
            "type": "Alert",
            "document_type": "Overtime Request",
            "document_name": "TEST-001",
            "email_content": "This is a test system notification to verify the bell notification works.",
            "read": 0
        })
        
        doc.insert(ignore_permissions=True)
        frappe.db.commit()
        
        # Send popup
        frappe.publish_realtime(
            event="msgprint",
            message="🎉 Test notification created! Check your notification bell.",
            user=current_user
        )
        
        return {
            "success": True,
            "notification_id": doc.name,
            "message": "Test notification created successfully"
        }
        
    except Exception as e:
        frappe.log_error(f"Test notification error: {str(e)}", "Test Error")
        return {
            "success": False,
            "error": str(e)
        }

@frappe.whitelist()
def get_pending_approvals_for_user(employee_id):
    """Get pending approval requests for specific employee - BYPASS USER PERMISSIONS"""
    try:
        # Use raw SQL to completely bypass permission system
        query = """
            SELECT 
                name, 
                requested_by,
                ot_date,
                total_employees,
                total_hours,
                status,
                manager_approver,
                factory_manager_approver,
                request_date,
                creation,
                modified
            FROM `tabOvertime Request`
            WHERE 
                docstatus = 1 
                AND status IN ('Pending Manager Approval', 'Pending Factory Manager Approval')
                AND (
                    (status = 'Pending Manager Approval' AND manager_approver LIKE %s)
                    OR 
                    (status = 'Pending Factory Manager Approval' AND factory_manager_approver LIKE %s)
                )
            ORDER BY creation DESC
        """
        
        # Search pattern for employee ID
        employee_pattern = f"{employee_id} -%"
        
        results = frappe.db.sql(query, (employee_pattern, employee_pattern), as_dict=True)
        
        # Enrich with employee names
        for record in results:
            if record.requested_by:
                requested_by_name = frappe.get_value("Employee", record.requested_by, "employee_name")
                record["requested_by_name"] = requested_by_name
        
        frappe.log_error(f"Pending approvals for {employee_id}: {len(results)} records", "Approval Debug")
        
        return results
        
    except Exception as e:
        frappe.log_error(f"Error getting pending approvals for {employee_id}: {str(e)}", "Approval Error")
        return []

@frappe.whitelist()
def get_processed_approvals_for_user(employee_id):
    """Get processed approval requests for specific employee - BYPASS USER PERMISSIONS"""
    try:
        # Raw SQL query to get all processed requests
        query = """
            SELECT 
                name,
                requested_by,
                ot_date,
                total_employees,
                total_hours,
                status,
                manager_approver,
                factory_manager_approver,
                manager_approved_on,
                factory_manager_approved_on,
                request_date,
                creation,
                modified
            FROM `tabOvertime Request`
            WHERE 
                docstatus != 0
                AND (
                    (manager_approver LIKE %s AND manager_approved_on IS NOT NULL)
                    OR 
                    (factory_manager_approver LIKE %s AND factory_manager_approved_on IS NOT NULL)
                    OR
                    (
                        (manager_approver LIKE %s OR factory_manager_approver LIKE %s)
                        AND status IN ('Rejected', 'Draft', 'Approved')
                    )
                )
            ORDER BY 
                COALESCE(factory_manager_approved_on, manager_approved_on, modified) DESC
            LIMIT 50
        """
        
        employee_pattern = f"{employee_id} -%"
        
        results = frappe.db.sql(query, (employee_pattern, employee_pattern, employee_pattern, employee_pattern), as_dict=True)
        
        # Enrich with employee names
        for record in results:
            if record.requested_by:
                requested_by_name = frappe.get_value("Employee", record.requested_by, "employee_name")
                record["requested_by_name"] = requested_by_name
        
        frappe.log_error(f"Processed approvals for {employee_id}: {len(results)} records", "Approval Debug")
        
        return results
        
    except Exception as e:
        frappe.log_error(f"Error getting processed approvals for {employee_id}: {str(e)}", "Approval Error")
        return []

@frappe.whitelist()
def get_pending_approvals_count(employee_id):
    """Get count of pending approvals for badge display"""
    try:
        query = """
            SELECT COUNT(*) as count
            FROM `tabOvertime Request`
            WHERE 
                docstatus = 1 
                AND status IN ('Pending Manager Approval', 'Pending Factory Manager Approval')
                AND (
                    (status = 'Pending Manager Approval' AND manager_approver LIKE %s)
                    OR 
                    (status = 'Pending Factory Manager Approval' AND factory_manager_approver LIKE %s)
                )
        """
        
        employee_pattern = f"{employee_id} -%"
        result = frappe.db.sql(query, (employee_pattern, employee_pattern), as_dict=True)
        
        count = result[0].get('count', 0) if result else 0
        
        return {
            "count": count,
            "employee_id": employee_id
        }
        
    except Exception as e:
        frappe.log_error(f"Error getting pending count for {employee_id}: {str(e)}", "Count Error")
        return {"count": 0}

@frappe.whitelist()
def get_user_approval_authority():
    """Check if current user has approval authority and return their employee info"""
    try:
        user = frappe.session.user
        
        # Get employee record
        employee = frappe.get_value("Employee", {"user_id": user}, 
                                  ["name", "employee_name", "designation", "department"], 
                                  as_dict=True)
        
        if not employee:
            return {
                "has_authority": False,
                "message": "No employee record found for current user"
            }
        
        # Check roles
        user_roles = frappe.get_roles(user)
        manager_roles = ["Department Manager", "Factory Manager", "TIQN Manager", "TIQN Factory Manager", "HR Manager"]
        has_manager_role = any(role in user_roles for role in manager_roles)
        
        # Check designation
        designation = employee.get("designation", "").lower()
        has_manager_designation = "manager" in designation or "head" in designation
        
        has_authority = has_manager_role or has_manager_designation
        
        return {
            "has_authority": has_authority,
            "employee_id": employee.name,
            "employee_name": employee.employee_name,
            "designation": employee.designation,
            "department": employee.department,
            "roles": user_roles,
            "manager_roles": has_manager_role,
            "manager_designation": has_manager_designation
        }
        
    except Exception as e:
        frappe.log_error(f"Error checking user approval authority: {str(e)}", "Authority Check Error")
        return {
            "has_authority": False,
            "error": str(e)
        }

@frappe.whitelist()
def approve_overtime_request(name, approval_type, comments=""):
    """Approve overtime request - Manager or Factory Manager approval"""
    try:
        doc = frappe.get_doc("Overtime Request", name)
        
        if not doc.has_permission("write"):
            frappe.throw("You don't have permission to approve this request")
        
        current_user_employee = frappe.get_value("Employee", {"user_id": frappe.session.user}, "name")
        
        if approval_type == "manager":
            manager_id = doc.manager_approver.split(' - ')[0] if doc.manager_approver else ""
            if manager_id != current_user_employee:
                frappe.throw("You are not authorized to provide manager approval for this request")
            
            if doc.status != "Pending Manager Approval":
                frappe.throw("This request is not pending manager approval")
            
            # Use db_set for submitted documents
            doc.db_set("manager_approved_on", now())
            doc.db_set("status", "Pending Factory Manager Approval")
            
            # Reload document to get updated values
            doc.reload()
            
            # Re-share with factory manager (in case it wasn't shared before)
            doc.share_with_approvers()
            
            # Send notification to Factory Manager
            doc.send_factory_manager_approval_notification()
            
            frappe.msgprint("Request approved. Factory Manager has been notified for final approval.")
            
        elif approval_type == "factory_manager":
            factory_manager_id = doc.factory_manager_approver.split(' - ')[0] if doc.factory_manager_approver else ""
            if factory_manager_id != current_user_employee:
                frappe.throw("You are not authorized to provide Factory Manager approval for this request")
            
            if doc.status != "Pending Factory Manager Approval":
                frappe.throw("This request is not pending Factory Manager approval")
            
            if not doc.manager_approved_on:
                frappe.throw("Department Manager approval is required before Factory Manager approval")
            
            # Use db_set for submitted documents
            doc.db_set("factory_manager_approved_on", now())
            doc.db_set("status", "Approved")
            
            # Reload document to get updated values
            doc.reload()
            
            # Create overtime records for each employee
            create_overtime_records(doc)
            
            # Send final approval notification
            doc.send_final_approval_notification()
            
            frappe.msgprint("Request fully approved. Overtime entries have been created.")
        
    except Exception as e:
        frappe.log_error(f"Error in approve_overtime_request: {str(e)}")
        frappe.throw(f"Error approving request: {str(e)}")

@frappe.whitelist()
def reject_overtime_request(name, rejection_type, comments=""):
    """Reject overtime request"""
    try:
        doc = frappe.get_doc("Overtime Request", name)
        
        if not doc.has_permission("write"):
            frappe.throw("You don't have permission to reject this request")
        
        current_user_employee = frappe.get_value("Employee", {"user_id": frappe.session.user}, "name")
        
        if rejection_type == "manager":
            # Extract employee ID from manager_approver (before " - ")
            manager_id = doc.manager_approver.split(' - ')[0] if doc.manager_approver else ""
            if manager_id != current_user_employee:
                frappe.throw(f"You are not authorized to reject this request at manager level. Manager: {manager_id}, Current: {current_user_employee}")
            if doc.status != "Pending Manager Approval":
                frappe.throw("This request is not pending manager approval")
                
        elif rejection_type == "factory_manager":
            # Extract employee ID from factory_manager_approver (before " - ")
            factory_manager_id = doc.factory_manager_approver.split(' - ')[0] if doc.factory_manager_approver else ""
            if factory_manager_id != current_user_employee:
                frappe.throw(f"You are not authorized to reject this request at Factory Manager level. Factory Manager: {factory_manager_id}, Current: {current_user_employee}")
            if doc.status != "Pending Factory Manager Approval":
                frappe.throw("This request is not pending Factory Manager approval")
        
        # Cancel the document first, then reset to draft
        doc.cancel()
        
        # Use db_set to update fields for cancelled document
        doc.db_set("docstatus", 0)  # Set back to draft
        doc.db_set("status", "Draft")
        
        # Clear approval timestamps based on rejection level
        if rejection_type == "manager":
            doc.db_set("manager_approved_on", None)
        elif rejection_type == "factory_manager":
            doc.db_set("factory_manager_approved_on", None)
            doc.db_set("manager_approved_on", None)  # Clear both if factory manager rejects
        
        # Reload document to get updated values
        doc.reload()
        
        # Add comment
        if comments:
            doc.add_comment("Comment", f"Rejected by {rejection_type.replace('_', ' ').title()}: {comments}")
        
        # Send rejection notification
        doc.send_rejection_notification(rejection_type, comments)
        
        frappe.msgprint("Request has been rejected and returned to draft status. Requester has been notified.")
        
    except Exception as e:
        frappe.log_error(f"Error in reject_overtime_request: {str(e)}")
        frappe.throw(f"Error rejecting request: {str(e)}")

def create_overtime_records(overtime_request):
    """Create individual overtime records for each employee after approval"""
    try:
        for employee_row in overtime_request.ot_employees:
            existing = frappe.get_all("Overtime Entry",
                filters={
                    "employee": employee_row.employee,
                    "overtime_date": overtime_request.ot_date,
                    "overtime_request": overtime_request.name
                }
            )
            
            if existing:
                continue
            
            overtime_entry = frappe.new_doc("Overtime Entry")
            overtime_entry.employee = employee_row.employee
            overtime_entry.employee_name = employee_row.employee_name
            overtime_entry.overtime_date = overtime_request.ot_date
            overtime_entry.overtime_hours = employee_row.planned_hours
            overtime_entry.overtime_rate_multiplier = employee_row.rate_multiplier
            overtime_entry.start_time = employee_row.start_time
            overtime_entry.end_time = employee_row.end_time
            overtime_entry.overtime_request = overtime_request.name
            overtime_entry.status = "Approved"
            
            try:
                overtime_entry.insert()
                overtime_entry.submit()
            except Exception as e:
                frappe.log_error(f"Error creating overtime entry for {employee_row.employee}: {str(e)}")
                
    except Exception as e:
        frappe.log_error(f"Error in create_overtime_records: {str(e)}")

# Additional helper methods
@frappe.whitelist()
def get_managers_list(manager_type="department"):
    """Get list of managers"""
    try:
        query = """
            SELECT name as employee_id, 
                   employee_name,
                   designation,
                   CONCAT(name, ' - ', employee_name, ' (', designation, ')') as display_name
            FROM `tabEmployee`
            WHERE status = 'Active' AND (designation LIKE '%Manager%' OR designation LIKE '%Head%')
        """
        return frappe.db.sql(query, as_dict=True)
    except Exception as e:
        frappe.log_error(f"Error getting managers list: {str(e)}")
        return []

@frappe.whitelist()
def get_active_employees(doctype, txt, searchfield, start, page_len, filters):
    """Get all active employees for OT Employee Detail selection"""
    try:
        conditions = []
        values = []
        
        # Always filter active employees
        conditions.append("status = %s")
        values.append("Active")
        
        # Add search condition if text provided
        if txt:
            conditions.append("(name LIKE %s OR employee_name LIKE %s)")
            values.extend([f"%{txt}%", f"%{txt}%"])
        
        query = f"""
            SELECT name, employee_name, designation, department
            FROM `tabEmployee`
            WHERE {' AND '.join(conditions)}
            ORDER BY employee_name
            LIMIT %s OFFSET %s
        """
        values.extend([page_len, start])
        
        result = frappe.db.sql(query, values, as_dict=False)
        return result
        
    except Exception as e:
        frappe.log_error(f"Error in get_active_employees: {str(e)}")
        return []

# Add these missing methods to the END of your overtime_request.py file
# (After all other methods)

@frappe.whitelist()
def get_pending_approvals(user=None):
    """Get pending overtime requests for approval - LEGACY METHOD"""
    try:
        if not user:
            user = frappe.session.user
        
        employee = frappe.get_value("Employee", {"user_id": user}, "name")
        if not employee:
            return []
        
        pending_requests = []
        
        # Manager requests
        manager_requests = frappe.get_all("Overtime Request",
            filters={
                "status": "Pending Manager Approval",
                "manager_approver": ["like", f"{employee} -%"],
                "docstatus": 1
            },
            fields=["name", "requested_by", "ot_date", "total_employees", "total_hours", "request_date"],
            order_by="request_date desc"
        )
        
        for req in manager_requests:
            req["approval_type"] = "Manager"
            pending_requests.append(req)
        
        # Factory manager requests
        factory_manager_requests = frappe.get_all("Overtime Request",
            filters={
                "status": "Pending Factory Manager Approval",
                "factory_manager_approver": ["like", f"{employee} -%"],
                "docstatus": 1
            },
            fields=["name", "requested_by", "ot_date", "total_employees", "total_hours", "request_date"],
            order_by="request_date desc"
        )
        
        for req in factory_manager_requests:
            req["approval_type"] = "Factory Manager"
            pending_requests.append(req)
        
        return pending_requests
        
    except Exception as e:
        frappe.log_error(f"Error in get_pending_approvals: {str(e)}")
        return []

@frappe.whitelist()
def bypass_get_overtime_list(filters=None, limit=20):
    """Bypass permissions and get overtime list directly"""
    try:
        user = frappe.session.user
        user_roles = frappe.get_roles(user)
        
        # Method 1: Try raw SQL
        try:
            permission_conditions = get_permission_query_conditions(user)
            
            base_query = """
                SELECT name, requested_by, status, ot_date, total_employees, 
                       total_hours, manager_approver, factory_manager_approver,
                       docstatus, creation, modified
                FROM `tabOvertime Request`
            """
            
            where_conditions = []
            if permission_conditions and permission_conditions != "":
                # Clean permission conditions for raw SQL
                cleaned_conditions = permission_conditions.replace("`tabOvertime Request`.", "")
                where_conditions.append(f"({cleaned_conditions})")
            
            if where_conditions:
                base_query += " WHERE " + " AND ".join(where_conditions)
            
            base_query += f" ORDER BY modified DESC LIMIT {limit}"
            
            result = frappe.db.sql(base_query, as_dict=True)
            
            return {
                "success": True,
                "query_used": "raw_sql",
                "count": len(result),
                "data": result
            }
            
        except Exception as sql_error:
            # Method 2: Try ignore_permissions
            try:
                result = frappe.get_all("Overtime Request",
                    fields=["name", "requested_by", "status", "ot_date", "total_employees", 
                           "total_hours", "manager_approver", "factory_manager_approver",
                           "docstatus", "creation", "modified"],
                    limit=limit,
                    ignore_permissions=True,
                    order_by="modified desc"
                )
                
                return {
                    "success": True,
                    "query_used": "ignore_permissions",
                    "count": len(result),
                    "data": result,
                    "sql_error": str(sql_error)
                }
                
            except Exception as ignore_error:
                return {
                    "success": False,
                    "sql_error": str(sql_error),
                    "ignore_permissions_error": str(ignore_error)
                }
    
    except Exception as e:
        return {"success": False, "error": str(e)}

@frappe.whitelist()
def get_user_overtime_requests(user=None):
    """Get overtime requests that user should be able to see"""
    try:
        if not user:
            user = frappe.session.user
        
        # Force ignore user permissions for this query
        permission_conditions = get_permission_query_conditions(user)
        
        if permission_conditions and permission_conditions != "":
            # Use raw SQL with permission conditions
            query = f"""
                SELECT name, requested_by, status, manager_approver, factory_manager_approver, docstatus
                FROM `tabOvertime Request`
                WHERE {permission_conditions.replace('`tabOvertime Request`.', '')}
                ORDER BY modified DESC
            """
            
            result = frappe.db.sql(query, as_dict=True)
            return result
        else:
            # User can see all (admin/manager)
            return frappe.get_all("Overtime Request",
                fields=["name", "requested_by", "status", "manager_approver", "factory_manager_approver", "docstatus"],
                ignore_permissions=True,
                order_by="modified desc"
            )
            
    except Exception as e:
        frappe.log_error(f"Error in get_user_overtime_requests: {str(e)}")
        return []

@frappe.whitelist()
def get_ot_level_options(ot_configuration):
    """Get OT Level options for dropdown based on configuration"""
    try:
        if not ot_configuration:
            return []
        
        ot_config = frappe.get_doc("Overtime Configuration", ot_configuration)
        active_levels = []
        
        for level in ot_config.overtime_levels:
            if level.is_active:
                active_levels.append({
                    'level_name': level.level_name,
                    'rate_multiplier': level.rate_multiplier,
                    'start_time': level.start_time,
                    'end_time': level.end_time,
                    'default_hours': level.default_hours,
                    'max_hours': level.max_hours
                })
        
        return active_levels
        
    except Exception as e:
        frappe.log_error(f"Error in get_ot_level_options: {str(e)}")
        return []

@frappe.whitelist()
def show_employee_selection_dialog(group_name, ot_configuration):
    """Get employees from selected group and OT configuration levels"""
    try:
        # Get employees from the group
        employees = frappe.get_all("Employee", 
            filters={
                "status": "Active",
                "custom_group": group_name
            },
            fields=["name", "employee_name", "designation", "department"]
        )
        
        # If no group field exists, try Group Employee table
        if not employees:
            group_employees = frappe.get_all("Group Employee",
                filters={"parent": group_name},
                fields=["employee"]
            )
            
            if group_employees:
                employee_list = [emp.employee for emp in group_employees]
                employees = frappe.get_all("Employee",
                    filters={
                        "status": "Active",
                        "name": ["in", employee_list]
                    },
                    fields=["name", "employee_name", "designation", "department"]
                )
        
        # Get OT configuration levels
        ot_levels = get_ot_level_options(ot_configuration)
        
        return {
            "employees": employees,
            "ot_levels": ot_levels
        }
        
    except Exception as e:
        frappe.log_error(f"Error in show_employee_selection_dialog: {str(e)}")
        frappe.throw(f"Error getting employees from group: {str(e)}")

@frappe.whitelist()
def get_managers_options(manager_type="department"):
    """Get manager options for Select field"""
    try:
        managers = get_managers_list(manager_type)
        options = []
        
        for manager in managers:
            # Just save employee_id to database
            options.append(manager['employee_id'])
        
        return "\n".join(options)
        
    except Exception as e:
        frappe.log_error(f"Error in get_managers_options: {str(e)}")
        return ""

@frappe.whitelist()
def get_date_multiplier_info(ot_date):
    """Get information about date type and appropriate multiplier"""
    try:
        from frappe.utils import getdate
        
        ot_date = getdate(ot_date)
        is_sunday = ot_date.weekday() == 6
        
        holiday_list = frappe.get_cached_value("Company", 
            frappe.defaults.get_user_default("Company"), "default_holiday_list")
        
        is_holiday = False
        holiday_name = ""
        
        if holiday_list:
            holidays = frappe.get_all("Holiday", 
                filters={
                    "holiday_date": ot_date,
                    "parent": holiday_list
                },
                fields=["holiday_date", "description"]
            )
            if holidays:
                is_holiday = True
                holiday_name = holidays[0].description
        
        multiplier = 1.0
        if is_holiday:
            multiplier = 3.0
        elif is_sunday:
            multiplier = 2.0
        
        return {
            "is_weekend": is_sunday,
            "is_holiday": is_holiday,
            "holiday_name": holiday_name,
            "suggested_multiplier": multiplier,
            "date_type": "Holiday" if is_holiday else ("Weekend" if is_sunday else "Weekday")
        }
        
    except Exception as e:
        frappe.log_error(f"Error in get_date_multiplier_info: {str(e)}")
        return {
            "is_weekend": False,
            "is_holiday": False,
            "holiday_name": "",
            "suggested_multiplier": 1.0,
            "date_type": "Weekday"
        }

@frappe.whitelist()
def quick_approve_multiple(request_names, approval_type, comments=""):
    """Quick approve multiple requests at once"""
    try:
        if isinstance(request_names, str):
            import json
            request_names = json.loads(request_names)
        
        results = []
        
        for name in request_names:
            try:
                # Call existing approve method
                approve_overtime_request(name, approval_type, comments)
                results.append({
                    "name": name,
                    "status": "success",
                    "message": "Approved successfully"
                })
            except Exception as e:
                results.append({
                    "name": name,
                    "status": "error", 
                    "message": str(e)
                })
        
        return {
            "success": True,
            "results": results,
            "total": len(request_names),
            "success_count": len([r for r in results if r["status"] == "success"]),
            "error_count": len([r for r in results if r["status"] == "error"])
        }
        
    except Exception as e:
        frappe.log_error(f"Error in quick_approve_multiple: {str(e)}", "Quick Approve Error")
        return {
            "success": False,
            "error": str(e)
        }

@frappe.whitelist()
def get_overtime_request_details_bypass_permission(name):
    """Get overtime request details bypassing permission for popup view"""
    try:
        # Raw SQL to bypass permissions
        query = """
            SELECT *
            FROM `tabOvertime Request`
            WHERE name = %s
        """
        
        result = frappe.db.sql(query, (name,), as_dict=True)
        
        if not result:
            return None
        
        doc_data = result[0]
        
        # Get child table data
        employees_query = """
            SELECT *
            FROM `tabOT Employee Detail`
            WHERE parent = %s
            ORDER BY idx
        """
        
        employees = frappe.db.sql(employees_query, (name,), as_dict=True)
        doc_data["ot_employees"] = employees
        
        # Enrich with names
        if doc_data.get("requested_by"):
            requested_by_name = frappe.get_value("Employee", doc_data["requested_by"], "employee_name")
            doc_data["requested_by_name"] = requested_by_name
        
        return doc_data
        
    except Exception as e:
        frappe.log_error(f"Error getting request details for {name}: {str(e)}", "Details Error")
        return None

@frappe.whitelist()
def send_bulk_notification(users, subject, message, document_type=None, document_name=None):
    """Send notification to multiple users at once"""
    try:
        if isinstance(users, str):
            import json
            users = json.loads(users)
        
        results = []
        
        for user in users:
            try:
                # Create system notification
                notification_id = create_system_notification(
                    user=user,
                    subject=subject,
                    message=message,
                    document_type=document_type or "Overtime Request",
                    document_name=document_name or "",
                    notification_type="Info"
                )
                
                results.append({
                    "user": user,
                    "status": "success",
                    "notification_id": notification_id
                })
                
            except Exception as e:
                results.append({
                    "user": user,
                    "status": "error",
                    "error": str(e)
                })
        
        return {
            "success": True,
            "results": results,
            "total_users": len(users),
            "success_count": len([r for r in results if r["status"] == "success"])
        }
        
    except Exception as e:
        frappe.log_error(f"Error in bulk notification: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@frappe.whitelist()
def cleanup_old_notifications(days=30):
    """Clean up notification logs older than specified days"""
    try:
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days)
        
        old_notifications = frappe.get_all("Notification Log",
            filters={
                "creation": ["<", cutoff_date],
                "document_type": "Overtime Request"
            },
            fields=["name"]
        )
        
        for notification in old_notifications:
            frappe.delete_doc("Notification Log", notification.name, ignore_permissions=True)
        
        return {
            "success": True,
            "deleted_count": len(old_notifications),
            "message": f"Cleaned up {len(old_notifications)} old notifications"
        }
        
    except Exception as e:
        frappe.log_error(f"Error cleaning up notifications: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

# Override get_list to ignore user permissions for specific roles
def get_list_context(context):
    """Custom list context to ignore user permissions"""
    try:
        user_roles = frappe.get_roles()
        
        # For manager roles, ignore user permissions
        if any(role in user_roles for role in ["Department Manager", "Factory Manager", "TIQN Manager", "TIQN Factory Manager", "HR Manager", "HR User"]):
            context.ignore_user_permissions = True
        
        return context
    except Exception as e:
        frappe.log_error(f"Error in get_list_context: {str(e)}")
        return context

# Define missing factory manager method
def get_factory_managers(doctype, txt, searchfield, start, page_len, filters):
    """Get factory managers for selection"""
    try:
        query = """
            SELECT name, employee_name, designation
            FROM `tabEmployee`
            WHERE status = 'Active' 
            AND (designation LIKE '%Factory Manager%' OR designation LIKE '%Manager%')
            ORDER BY employee_name
            LIMIT %s OFFSET %s
        """
        
        result = frappe.db.sql(query, (page_len, start), as_dict=False)
        return result
        
    except Exception as e:
        frappe.log_error(f"Error in get_factory_managers: {str(e)}")
        return []