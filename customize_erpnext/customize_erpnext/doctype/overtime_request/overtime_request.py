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

class OvertimeRequest(Document):
    def validate(self):
        self.validate_ot_date()
        self.validate_employees()
        self.validate_ot_levels_for_date()
        self.adjust_rate_multipliers()
        self.calculate_totals()
        self.set_default_approvers()

    # SOLUTION 1: Cải thiện has_permission method
    def has_permission(self, ptype, user=None):
        """
        DOCUMENT-LEVEL PERMISSION CHECK - Phiên bản cải thiện
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
        
        # 3. Get current user's employee record - cải thiện logic
        current_employee = None
        
        # Thử nhiều cách để lấy employee record
        employee_filters = [
            {"user_id": user},
            {"email": user},
            {"personal_email": user}
        ]
        
        for filter_dict in employee_filters:
            current_employee = frappe.get_value("Employee", filter_dict, "name")
            if current_employee:
                break
        
        # Nếu vẫn không tìm thấy, thử từ User doctype
        if not current_employee:
            user_doc = frappe.get_doc("User", user)
            if hasattr(user_doc, 'employee'):
                current_employee = user_doc.employee
        
        if not current_employee:
            # Log để debug
            frappe.log_error(f"No employee found for user: {user}", "Overtime Permission Debug")
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
            
            # Assigned as approver
            if hasattr(self, 'manager_approver') and self.manager_approver == current_employee:
                return True
            if hasattr(self, 'factory_manager_approver') and self.factory_manager_approver == current_employee:
                return True
            
            # Manager roles
            manager_roles = ["Department Manager", "Factory Manager", "TIQN Manager", "TIQN Factory Manager"]
            if any(role in user_roles for role in manager_roles):
                return True
            
            return False
        
        # 6. WRITE, SUBMIT, CANCEL permissions 
        if ptype in ["write", "submit", "cancel"]:
            doc_status = getattr(self, 'docstatus', 0)
            if "Employee" in user_roles:
                return True
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
                
                # Manager approver
                if (hasattr(self, 'manager_approver') and 
                    self.manager_approver == current_employee and 
                    status == "Pending Manager Approval"):
                    return True
                
                # Factory manager approver
                if (hasattr(self, 'factory_manager_approver') and 
                    self.factory_manager_approver == current_employee and 
                    status == "Pending Factory Manager Approval"):
                    return True
            
            return False
        
        return False

    def set_default_approvers(self):
        """Set default approvers if not already set"""
        if not self.manager_approver and self.requested_by:
            # Try to get manager from employee's reports_to field
            employee = frappe.get_doc("Employee", self.requested_by)
            if employee.reports_to:
                # Check if reports_to has Manager in designation
                manager_emp = frappe.get_doc("Employee", employee.reports_to)
                if manager_emp.designation and "Manager" in manager_emp.designation:
                    self.manager_approver = employee.reports_to
        
        if not self.factory_manager_approver:
            # Get first available Factory Manager
            factory_managers = get_factory_managers("Employee", "", "name", 0, 1, {})
            if factory_managers:
                self.factory_manager_approver = factory_managers[0][0]

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
    
    def calculate_totals(self):
        """Calculate total employees and hours"""
        self.total_employees = len(self.ot_employees)
        self.total_hours = sum([row.planned_hours or 0 for row in self.ot_employees])
    
    def before_submit(self):
        """Actions before document is submitted"""
        self.status = "Pending Manager Approval"
    
    def on_submit(self):
        """Actions when document is submitted"""
        # Send notification to Department Manager
        self.send_manager_approval_notification()
        
        frappe.msgprint("Overtime request submitted successfully. Department Manager has been notified.")
    
    def on_cancel(self):
        """Actions when document is cancelled"""
        self.status = "Cancelled"
        
        # Notify requester
        self.send_cancellation_notification()

    def send_manager_approval_notification(self):
        """Send email notification to Department Manager"""
        try:
            if self.manager_approver:
                manager_email = frappe.get_value("Employee", self.manager_approver, "user_id")
                manager_name = frappe.get_value("Employee", self.manager_approver, "employee_name")
                requester_name = frappe.get_value("Employee", self.requested_by, "employee_name")
                
                if manager_email:
                    subject = f"Overtime Request Approval Required - {self.name}"
                    message = f"""
                    Dear {manager_name},
                    
                    An overtime request requires your approval:
                    
                    Request ID: {self.name}
                    Requested by: {requester_name} ({self.requested_by})
                    OT Date: {self.ot_date}
                    Total Employees: {self.total_employees}
                    Total Hours: {self.total_hours}
                    Reason: {self.reason}
                    
                    Please click the link below to review and approve this request:
                    {frappe.utils.get_url()}/app/overtime-request/{self.name}
                    
                    Best regards,
                    HR System
                    """
                    
                    frappe.sendmail(
                        recipients=[manager_email],
                        subject=subject,
                        message=message
                    )
                    
        except Exception as e:
            frappe.log_error(f"Error sending manager approval notification: {str(e)}")

    def send_factory_manager_approval_notification(self):
        """Send email notification to Factory Manager"""
        try:
            if self.factory_manager_approver:
                factory_manager_email = frappe.get_value("Employee", self.factory_manager_approver, "user_id")
                factory_manager_name = frappe.get_value("Employee", self.factory_manager_approver, "employee_name")
                requester_name = frappe.get_value("Employee", self.requested_by, "employee_name")
                manager_name = frappe.get_value("Employee", self.manager_approver, "employee_name")
                
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
                    
                    Please click the link below to review and provide final approval:
                    {frappe.utils.get_url()}/app/overtime-request/{self.name}
                    
                    Best regards,
                    HR System
                    """
                    
                    frappe.sendmail(
                        recipients=[factory_manager_email],
                        subject=subject,
                        message=message
                    )
                    
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
                
                frappe.sendmail(
                    recipients=recipients,
                    subject=subject,
                    message=message
                )
                
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
                    rejector_name = frappe.get_value("Employee", self.manager_approver, "employee_name")
                elif rejection_type == "factory_manager":
                    rejector_name = frappe.get_value("Employee", self.factory_manager_approver, "employee_name")
                
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
                
                frappe.sendmail(
                    recipients=[requester_email],
                    subject=subject,
                    message=message
                )
                
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
                manager_email = frappe.get_value("Employee", self.manager_approver, "user_id")
                if manager_email:
                    recipients.append(manager_email)
            
            if self.factory_manager_approver:
                factory_manager_email = frappe.get_value("Employee", self.factory_manager_approver, "user_id")
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
                
                frappe.sendmail(
                    recipients=recipients,
                    subject=subject,
                    message=message
                )
                
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

# ===== OTHER EXISTING METHODS =====

@frappe.whitelist()
def approve_overtime_request(name, approval_type, comments=""):
    """Approve overtime request - Manager or Factory Manager approval"""
    try:
        doc = frappe.get_doc("Overtime Request", name)
        
        if not doc.has_permission("write"):
            frappe.throw("You don't have permission to approve this request")
        
        current_user_employee = frappe.get_value("Employee", {"user_id": frappe.session.user}, "name")
        
        if approval_type == "manager":
            if doc.manager_approver != current_user_employee:
                frappe.throw("You are not authorized to provide manager approval for this request")
            
            if doc.status != "Pending Manager Approval":
                frappe.throw("This request is not pending manager approval")
            
            # Use db_set for submitted documents
            doc.db_set("manager_approved_on", now())
            doc.db_set("status", "Pending Factory Manager Approval")
            
            # Reload document to get updated values
            doc.reload()
            
            # Send notification to Factory Manager
            doc.send_factory_manager_approval_notification()
            
            frappe.msgprint("Request approved. Factory Manager has been notified for final approval.")
            
        elif approval_type == "factory_manager":
            if doc.factory_manager_approver != current_user_employee:
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
            if doc.manager_approver != current_user_employee:
                frappe.throw("You are not authorized to reject this request at manager level")
            if doc.status != "Pending Manager Approval":
                frappe.throw("This request is not pending manager approval")
                
        elif rejection_type == "factory_manager":
            if doc.factory_manager_approver != current_user_employee:
                frappe.throw("You are not authorized to reject this request at Factory Manager level")
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

@frappe.whitelist()
def get_overtime_requests_list(filters=None, fields=None, limit=20, start=0):
    """Custom list method that bypasses User Permission restrictions"""
    user = frappe.session.user
    user_roles = frappe.get_roles(user)
    
    # Build base query with permission conditions
    permission_conditions = get_permission_query_conditions(user)
    
    # If no permission conditions (admin users), don't add WHERE clause
    if permission_conditions and permission_conditions != "":
        # Remove table prefix for SQL query
        permission_conditions = permission_conditions.replace("`tabOvertime Request`.", "")
    else:
        permission_conditions = ""
    
    # Base fields
    if not fields:
        fields = [
            "name", "requested_by", "status", "ot_date", "total_employees", 
            "total_hours", "manager_approver", "factory_manager_approver",
            "docstatus", "creation", "modified"
        ]
    
    # Build SQL query
    sql_fields = ", ".join([f"`{field}`" for field in fields])
    sql_query = f"SELECT {sql_fields} FROM `tabOvertime Request`"
    
    # Add WHERE conditions
    where_conditions = []
    
    # Add permission conditions
    if permission_conditions:
        where_conditions.append(f"({permission_conditions})")
    
    # Add additional filters
    if filters:
        for key, value in filters.items():
            if isinstance(value, list):
                if value[0] == "in":
                    values_str = "', '".join(str(v) for v in value[1])
                    where_conditions.append(f"`{key}` IN ('{values_str}')")
                else:
                    where_conditions.append(f"`{key}` {value[0]} '{value[1]}'")
            else:
                where_conditions.append(f"`{key}` = '{value}'")
    
    # Combine WHERE conditions
    if where_conditions:
        sql_query += " WHERE " + " AND ".join(where_conditions)
    
    # Add ORDER BY
    sql_query += " ORDER BY modified DESC"
    
    # Add LIMIT
    if limit:
        sql_query += f" LIMIT {start}, {limit}"
    
    # Debug log the query
    frappe.log_error(f"Overtime Request Query: {sql_query}", "Custom List Query")
    
    # Execute query with ignore_permissions
    try:
        result = frappe.db.sql(sql_query, as_dict=True)
        return result
    except Exception as e:
        frappe.log_error(f"Error in custom list query: {str(e)}", "Custom List Error")
        # Fallback to standard query
        return frappe.get_all("Overtime Request",
            filters=filters or {},
            fields=fields,
            limit_start=start,
            limit_page_length=limit,
            order_by="modified desc"
        )

@frappe.whitelist()
def get_user_overtime_requests(user=None):
    """Get overtime requests that user should be able to see"""
    if not user:
        user = frappe.session.user
    
    # Force ignore user permissions for this query
    return frappe.get_all("Overtime Request",
        filters=get_permission_query_conditions(user),
        fields=["name", "requested_by", "status", "manager_approver", "factory_manager_approver", "docstatus"],
        ignore_permissions=True,  # Force ignore user permissions
        order_by="modified desc"
    )

# Override get_list to ignore user permissions for specific roles
def get_list_context(context):
    """Custom list context to ignore user permissions"""
    user_roles = frappe.get_roles()
    
    # For manager roles, ignore user permissions
    if any(role in user_roles for role in ["Department Manager", "Factory Manager", "TIQN Manager", "TIQN Factory Manager", "HR Manager", "HR User"]):
        context.ignore_user_permissions = True
    
    return context

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
    """Trả về string options cho Select field"""
    managers = get_managers_list(manager_type)
    options = []
    
    for manager in managers:
        # Chỉ lưu employee_id vào database
        options.append(manager['employee_id'])
    
    return "\n".join(options)

@frappe.whitelist()
def get_managers_list(manager_type="department"):
    """Trả về full data để hiển thị"""
    query = """
        SELECT name as employee_id, 
               employee_name,
               designation,
               CONCAT(name, ' - ', employee_name, ' (', designation, ')') as display_name
        FROM `tabEmployee`
        WHERE status = 'Active' AND designation LIKE '%Manager%' OR designation LIKE '%Head%'
    """
    return frappe.db.sql(query, as_dict=True)

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

@frappe.whitelist()
def get_pending_approvals(user=None):
    """Get pending overtime requests for approval"""
    try:
        if not user:
            user = frappe.session.user
        
        employee = frappe.get_value("Employee", {"user_id": user}, "name")
        if not employee:
            return []
        
        pending_requests = []
        
        manager_requests = frappe.get_all("Overtime Request",
            filters={
                "status": "Pending Manager Approval",
                "manager_approver": employee,
                "docstatus": 1
            },
            fields=["name", "requested_by", "ot_date", "total_employees", "total_hours", "request_date"],
            order_by="request_date desc"
        )
        
        for req in manager_requests:
            req["approval_type"] = "Manager"
            pending_requests.append(req)
        
        factory_manager_requests = frappe.get_all("Overtime Request",
            filters={
                "status": "Pending Factory Manager Approval",
                "factory_manager_approver": employee,
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


# AUTO SHARE DOCUMENT WITH APPROVERS
# Thêm vào overtime_request.py

def on_submit(self):
    """Actions when document is submitted"""
    # Set status
    self.status = "Pending Manager Approval"
    
    # Share document with approvers
    self.share_with_approvers()
    
    # Send notification to Department Manager
    self.send_manager_approval_notification()
    
    frappe.msgprint("Overtime request submitted successfully. Department Manager has been notified.")

def share_with_approvers(self):
    """Share document with all approvers for access"""
    try:
        users_to_share = []
        
        # Add manager approver
        if self.manager_approver:
            manager_user = frappe.get_value("Employee", self.manager_approver, "user_id")
            if manager_user:
                users_to_share.append(manager_user)
        
        # Add factory manager approver  
        if self.factory_manager_approver:
            factory_manager_user = frappe.get_value("Employee", self.factory_manager_approver, "user_id")
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

# Update approve functions to re-share when status changes
@frappe.whitelist()
def approve_overtime_request(name, approval_type, comments=""):
    """Approve overtime request - Manager or Factory Manager approval"""
    try:
        doc = frappe.get_doc("Overtime Request", name)
        
        if not doc.has_permission("write"):
            frappe.throw("You don't have permission to approve this request")
        
        current_user_employee = frappe.get_value("Employee", {"user_id": frappe.session.user}, "name")
        
        if approval_type == "manager":
            if doc.manager_approver != current_user_employee:
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
            if doc.factory_manager_approver != current_user_employee:
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

# HELPER: Check document shares
@frappe.whitelist()
def check_document_shares(doc_name):
    """Debug function to check who has access to document"""
    shares = frappe.get_all("DocShare",
        filters={"share_doctype": "Overtime Request", "share_name": doc_name},
        fields=["user", "read", "write", "submit", "creation"]
    )
    
    result = {
        "document": doc_name,
        "shares": shares,
        "total_shares": len(shares)
    }
    
    return result

# HELPER: Manual share function
@frappe.whitelist()
def manual_share_with_user(doc_name, user_email):
    """Manually share document with specific user"""
    try:
        frappe.share.add(
            doctype="Overtime Request",
            name=doc_name,
            user=user_email,
            read=1,
            write=1,
            submit=0,
            share=0,
            flags={"ignore_share_permission": True}
        )
        
        frappe.db.commit()
        frappe.msgprint(f"Document {doc_name} shared with {user_email}")
        
    except Exception as e:
        frappe.throw(f"Error sharing document: {str(e)}")
