# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import getdate

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

    def has_permission(self, ptype, user=None):
    """Custom permission logic"""
    if not user:
        user = frappe.session.user
    
    # Admin always has access
    if user == "Administrator":
        return True
        
    # System Manager role has full access
    user_roles = frappe.get_roles(user)
    if "System Manager" in user_roles:
        return True
    
    # HR Manager and HR User always have access
    if "HR Manager" in user_roles or "HR User" in user_roles:
        return True
    
    # Check if user has any manager roles - they can see requests for approval
    manager_roles = ["Department Manager", "Factory Manager", "TIQN Factory Manager", "TIQN Manager"]
    if any(role in user_roles for role in manager_roles):
        return True
    
    # Get current user's employee record
    current_employee = frappe.get_value("Employee", {"user_id": user}, "name")
    
    # If no employee record but user has Employee role, allow create only
    if not current_employee:
        if ptype == "create" and "Employee" in user_roles:
            return True
        # Allow read access for users with manager roles even without employee record
        if ptype == "read" and any(role in user_roles for role in manager_roles):
            return True
        return False
    
    # Check if user has HR designation - they can see all requests
    user_designation = frappe.get_value("Employee", current_employee, "designation")
    if user_designation and "HR" in user_designation.upper():
        return True
    
    # For existing documents, check specific permissions
    if hasattr(self, 'name') and self.name:
        # Owner (requested_by) can always access their own requests
        if hasattr(self, 'requested_by') and self.requested_by == current_employee:
            return True
        
        # Manager approver can access when they are assigned as approver
        if hasattr(self, 'manager_approver') and self.manager_approver == current_employee:
            return True
        
        # Factory manager approver can access when they are assigned as approver
        if hasattr(self, 'factory_manager_approver') and self.factory_manager_approver == current_employee:
            return True
    
    # Anyone with Employee role can create new requests
    if ptype == "create" and "Employee" in user_roles:
        return True
    
    # Default allow read for users with appropriate roles
    if ptype == "read" and ("Employee" in user_roles or any(role in user_roles for role in manager_roles)):
        return True
    
    return False

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
    
    def on_submit(self):
        """Actions when document is submitted"""
        self.status = "Pending Manager Approval"
        self.set_approvers()
        # Chỉ gửi mail cho Department Manager
        self.send_manager_approval_notification()
    
    def on_cancel(self):
        """Actions when document is cancelled"""
        self.status = "Cancelled"
    
    def set_approvers(self):
        """Set default approvers based on requesting employee's hierarchy"""
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

    def send_manager_approval_notification(self):
        """Send email notification to Department Manager only"""
        try:
            if self.manager_approver:
                manager_email = frappe.get_value("Employee", self.manager_approver, "user_id")
                manager_name = frappe.get_value("Employee", self.manager_approver, "employee_name")
                
                if manager_email:
                    subject = f"Overtime Request Approval Required - {self.name}"
                    message = f"""
                    Dear {manager_name},
                    
                    An overtime request requires your approval:
                    
                    Request ID: {self.name}
                    Requested by: {self.requested_by}
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
        """Send email notification to Factory Manager only"""
        try:
            if self.factory_manager_approver:
                factory_manager_email = frappe.get_value("Employee", self.factory_manager_approver, "user_id")
                factory_manager_name = frappe.get_value("Employee", self.factory_manager_approver, "employee_name")
                
                if factory_manager_email:
                    subject = f"Overtime Request Final Approval Required - {self.name}"
                    message = f"""
                    Dear {factory_manager_name},
                    
                    An overtime request requires your final approval:
                    
                    Request ID: {self.name}
                    Requested by: {self.requested_by}
                    OT Date: {self.ot_date}
                    Total Employees: {self.total_employees}
                    Total Hours: {self.total_hours}
                    Reason: {self.reason}
                    
                    Department Manager has already approved this request.
                    
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
        """Send notification to HR users and requester when fully approved"""
        try:
            recipients = []
            
            # Get requester's email
            requester_email = frappe.get_value("Employee", self.requested_by, "user_id")
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
                
                An overtime request has been fully approved:
                
                Request ID: {self.name}
                Requested by: {self.requested_by}
                OT Date: {self.ot_date}
                Total Employees: {self.total_employees}
                Total Hours: {self.total_hours}
                
                Status: Approved
                Manager Approved: {self.manager_approved_on}
                Factory Manager Approved: {self.factory_manager_approved_on}
                
                The overtime entries have been created for all employees.
                
                Link: {frappe.utils.get_url()}/app/overtime-request/{self.name}
                
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
def get_factory_managers(doctype, txt, searchfield, start, page_len, filters):
    """Get employees with Factory Manager or Director designation for approver selection"""
    try:
        conditions = []
        values = []
        
        conditions.append("status = %s")
        values.append("Active")
        
        designation_conditions = []
        designation_conditions.append("designation LIKE %s")
        values.append("%Manager%")
        designation_conditions.append("designation LIKE %s") 
        values.append("%Director%")
        designation_conditions.append("designation LIKE %s")
        values.append("%Head%")
        
        conditions.append(f"({' OR '.join(designation_conditions)})")
        
        if txt:
            conditions.append("(name LIKE %s OR employee_name LIKE %s)")
            values.extend([f"%{txt}%", f"%{txt}%"])
        
        query = f"""
            SELECT name, employee_name, designation
            FROM `tabEmployee`
            WHERE {' AND '.join(conditions)}
            ORDER BY employee_name
            LIMIT %s OFFSET %s
        """
        values.extend([page_len, start])
        
        result = frappe.db.sql(query, values, as_dict=False)
        return result
        
    except Exception as e:
        frappe.log_error(f"Error in get_factory_managers: {str(e)}")
        return []

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
            
            doc.manager_approved_on = frappe.utils.now()
            doc.status = "Pending Factory Manager Approval"
            doc.save()
            frappe.db.commit()
            
            # Send notification to Factory Manager
            doc.send_factory_manager_approval_notification()
            
        elif approval_type == "factory_manager":
            if doc.manager_approved_on is None:
                frappe.throw("Department Manager approval is required before Factory Manager approval")
            
            if doc.factory_manager_approver != current_user_employee:
                frappe.throw("You are not authorized to provide Factory Manager approval for this request")
            
            doc.factory_manager_approved_on = frappe.utils.now()
            doc.status = "Approved"
            doc.save()
            frappe.db.commit()
            
            # Create overtime records for each employee
            create_overtime_records(doc)
            
            # Send final approval notification to HR and requester
            doc.send_final_approval_notification()
        
        frappe.msgprint(f"Overtime request has been approved successfully")
        
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
        elif rejection_type == "factory_manager":
            if doc.factory_manager_approver != current_user_employee:
                frappe.throw("You are not authorized to reject this request at Factory Manager level")
        
        doc.status = "Rejected"
        
        if comments:
            doc.add_comment("Comment", f"Rejected by {rejection_type}: {comments}")
        
        doc.save()
        frappe.db.commit()
        
        frappe.msgprint("Overtime request has been rejected")
        
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

