# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import (
    getdate, 
    get_datetime, 
    time_diff_in_hours,
    flt,
    cint
)
from datetime import datetime, timedelta, time
from .attendance_utils import parse_time_field_helper, timedelta_to_time_helper


# Update modules/overtime_calculator.py
# Remove status filter, only use docstatus

def get_approved_overtime_requests_for_doc(doc):
    """Get OT requests for a document object - FIXED VERSION (DocStatus Only)"""
    try:
        # Validate input parameters
        if not doc:
            frappe.logger().error("Document object is None")
            return []
            
        if not hasattr(doc, 'employee') or not hasattr(doc, 'attendance_date'):
            frappe.logger().error("Document missing required fields: employee or attendance_date")
            return []
            
        if not doc.employee or not doc.attendance_date:
            frappe.logger().warning(f"Empty employee or attendance_date: {doc.employee}, {doc.attendance_date}")
            return []
        
        frappe.logger().info(f"=== Getting OT requests for {doc.employee} on {doc.attendance_date} ===")
        
        # FIXED QUERY: Remove status filter, only use docstatus
        try:
            overtime_requests = frappe.db.sql("""
                SELECT 
                    ot.name,
                    ot.request_date,
                    ot.docstatus,
                    otd.employee,
                    otd.employee_name,
                    otd.date,
                    otd.begin_time,
                    otd.end_time,
                    otd.reason,
                    otd.group
                FROM `tabOvertime Registration` ot
                INNER JOIN `tabOvertime Registration Detail` otd ON otd.parent = ot.name
                WHERE otd.employee = %s
                AND otd.date = %s
                AND ot.docstatus = 1
            """, (doc.employee, doc.attendance_date), as_dict=True)
        except Exception as db_error:
            frappe.logger().error(f"Database query error: {str(db_error)}")
            # Check if tables exist
            if "doesn't exist" in str(db_error).lower():
                frappe.logger().error("Overtime Registration tables don't exist. Please create the DocTypes first.")
                return []
            raise db_error
        
        frappe.logger().info(f"Query: employee={doc.employee}, date={doc.attendance_date}")
        frappe.logger().info(f"Found {len(overtime_requests)} OT requests")
        
        # Process and validate each request
        processed_requests = []
        for req in overtime_requests:
            try:
                # Calculate planned hours from begin_time and end_time
                planned_hours = 0.0
                if req.get('begin_time') and req.get('end_time'):
                    begin_time = parse_time_field_helper(req['begin_time'])
                    end_time = parse_time_field_helper(req['end_time'])
                    if begin_time and end_time:
                        # Create datetime objects for calculation
                        work_date = getdate(req['date'])
                        begin_datetime = datetime.combine(work_date, begin_time)
                        end_datetime = datetime.combine(work_date, end_time)
                        
                        # Handle overnight OT
                        if end_datetime <= begin_datetime:
                            end_datetime += timedelta(days=1)
                        
                        planned_hours = time_diff_in_hours(end_datetime, begin_datetime)
                
                # Add planned_hours to request for compatibility
                req['planned_hours'] = flt(planned_hours, 2)
                
                frappe.logger().info(f"OT Request Found:")
                frappe.logger().info(f"  Name: {req['name']}")
                frappe.logger().info(f"  Employee: {req['employee']}")
                frappe.logger().info(f"  Date: {req['date']}")
                frappe.logger().info(f"  Begin Time: {req['begin_time']}")
                frappe.logger().info(f"  End Time: {req['end_time']}")
                frappe.logger().info(f"  Calculated Planned Hours: {req['planned_hours']}")
                frappe.logger().info(f"  Reason: {req.get('reason', 'N/A')}")
                frappe.logger().info(f"  Group: {req.get('group', 'N/A')}")
                frappe.logger().info(f"  DocStatus: {req['docstatus']} (Submitted)")
                
                processed_requests.append(req)
                
            except Exception as process_error:
                frappe.logger().error(f"Error processing OT request {req.get('name', 'Unknown')}: {str(process_error)}")
                continue
        
        return processed_requests
        
    except Exception as e:
        error_msg = f"Error getting overtime requests: {str(e)}"
        frappe.log_error(error_msg, "Custom Attendance Overtime")
        frappe.logger().error(error_msg)
        return []


def calculate_working_hours_with_overtime_for_doc(doc):
    """
    MAIN FUNCTION: Calculate working hours including overtime for Custom Attendance document
    
    Logic: 
    - Keep existing regular working hours (already calculated with breaks deducted)
    - Only add overtime hours from approved OT requests
    - Working Hours = Current Regular Hours + Overtime Hours

    Args:
        doc: Custom Attendance document object
        
    Returns:
        dict: {
            "working_hours": float,
            "overtime_hours": float,  
            "regular_hours": float,
            "has_overtime": bool,
            "overtime_details": dict,
            "message": str
        }
    """
    try:
        frappe.logger().info(f"=== CALCULATE WORKING HOURS WITH OVERTIME for {doc.name} ===")
        
        # Validate input
        if not doc.check_in or not doc.check_out:
            return {
                "working_hours": doc.working_hours or 0.0,  # Keep existing if no check times
                "overtime_hours": 0.0,
                "regular_hours": doc.working_hours or 0.0,
                "has_overtime": False,
                "overtime_details": {},
                "message": "Check-in and check-out times required"
            }
        
        check_in_time = get_datetime(doc.check_in)
        check_out_time = get_datetime(doc.check_out)
        
        frappe.logger().info(f"Times: {check_in_time} to {check_out_time}")
        
        if check_out_time <= check_in_time:
            return {
                "working_hours": doc.working_hours or 0.0,
                "overtime_hours": 0.0,
                "regular_hours": doc.working_hours or 0.0,
                "has_overtime": False,
                "overtime_details": {},
                "message": "Invalid time range: check-out must be after check-in"
            }
        
        # Step 1: Get existing regular working hours (already calculated with breaks)
        existing_regular_hours = flt(doc.working_hours or 0.0, 2)
        frappe.logger().info(f"Existing regular working hours: {existing_regular_hours}")
        
        # Step 2: Get overtime details using existing method
        overtime_details = get_overtime_details_for_doc(doc)
        overtime_hours = overtime_details.get('total_actual_ot_hours', 0.0)
        
        frappe.logger().info(f"Overtime details: {overtime_details}")
        frappe.logger().info(f"Overtime hours: {overtime_hours}")
        
        # Step 3: Calculate total working hours = existing regular + overtime
        total_working_hours = existing_regular_hours + overtime_hours
        
        # Step 4: Update document fields
        doc.working_hours = flt(total_working_hours, 2)
        doc.overtime_hours = flt(overtime_hours, 2)
        
        frappe.logger().info(f"Final calculation:")
        frappe.logger().info(f"  Existing regular hours: {existing_regular_hours}")
        frappe.logger().info(f"  Overtime hours: {overtime_hours}")
        frappe.logger().info(f"  Total working hours: {total_working_hours}")
        
        # Return detailed result
        result = {
            "working_hours": flt(total_working_hours, 2),
            "overtime_hours": flt(overtime_hours, 2),
            "regular_hours": flt(existing_regular_hours, 2),
            "has_overtime": overtime_hours > 0,
            "overtime_details": overtime_details,
            "message": f"Calculated: {existing_regular_hours}h regular + {overtime_hours}h overtime = {total_working_hours}h total"
        }
        
        frappe.logger().info(f"Result: {result}")
        return result
        
    except Exception as e:
        error_msg = f"Error calculating working hours with overtime: {str(e)}"
        frappe.log_error(error_msg, "Calculate Working Hours With Overtime")
        frappe.logger().error(error_msg)
        
        return {
            "working_hours": doc.working_hours or 0.0,
            "overtime_hours": 0.0, 
            "regular_hours": doc.working_hours or 0.0,
            "has_overtime": False,
            "overtime_details": {},
            "message": f"Calculation failed: {str(e)}"
        }


def calculate_realistic_working_hours_for_doc(doc, in_time, out_time):
    """Calculate realistic working hours for document (regular hours only)"""
    try:
        if not doc.shift:
            # Fallback: simple calculation
            total_hours = time_diff_in_hours(out_time, in_time)
            return max(0, flt(total_hours, 2))
        
        # Get shift document
        shift_doc = frappe.get_cached_doc("Shift Type", doc.shift)
        
        if not shift_doc.start_time or not shift_doc.end_time:
            total_hours = time_diff_in_hours(out_time, in_time)
            return max(0, flt(total_hours, 2))
        
        # Convert shift times
        shift_start_time = timedelta_to_time_helper(shift_doc.start_time)
        shift_end_time = timedelta_to_time_helper(shift_doc.end_time)
        
        work_date = in_time.date()
        shift_start_datetime = datetime.combine(work_date, shift_start_time)
        shift_end_datetime = datetime.combine(work_date, shift_end_time)
        
        # Handle overnight shifts
        if shift_end_datetime <= shift_start_datetime:
            if in_time.time() >= shift_start_time:
                shift_end_datetime += timedelta(days=1)
            else:
                shift_start_datetime -= timedelta(days=1)
        
        # Calculate effective working time (within shift bounds)
        effective_start = max(in_time, shift_start_datetime)
        effective_end = min(out_time, shift_end_datetime)
        
        if effective_end <= effective_start:
            return 0.0
        
        # Calculate hours minus break
        total_working_hours = time_diff_in_hours(effective_end, effective_start)
        
        # Simple break deduction (1 hour lunch break)
        if total_working_hours > 4:
            total_working_hours -= 1
        
        return max(0, flt(total_working_hours, 2))
        
    except Exception as e:
        frappe.log_error(f"Error calculating realistic hours: {str(e)}", "Working Hours Calc")
        total_hours = time_diff_in_hours(out_time, in_time)
        return max(0, flt(total_hours, 2))


def calculate_overtime_hours_for_doc(doc, check_in_time, check_out_time):
    """Calculate overtime hours for document"""
    try:
        # Get OT requests
        overtime_requests = get_approved_overtime_requests_for_doc(doc)
        
        if not overtime_requests:
            return 0.0
        
        total_overtime_hours = 0.0
        
        for ot_request in overtime_requests:
            # Calculate actual OT for this request
            actual_ot_hours = calculate_actual_overtime_for_request_doc(ot_request, check_in_time, check_out_time)
            total_overtime_hours += actual_ot_hours
            
            frappe.logger().info(f"OT Request {ot_request['name']}: {actual_ot_hours} hours")
        
        return total_overtime_hours
        
    except Exception as e:
        frappe.log_error(f"Error calculating overtime: {str(e)}", "Overtime Calculation")
        return 0.0


def calculate_actual_overtime_for_request_doc(ot_request, check_in_time, check_out_time):
    """Calculate actual OT for specific request - UPDATED for new structure"""
    try:
        # Parse OT times using new field names
        ot_start_time = parse_time_field_helper(ot_request['begin_time'])  # Changed from start_time
        ot_end_time = parse_time_field_helper(ot_request['end_time'])      # Same field name
        
        if not ot_start_time or not ot_end_time:
            frappe.logger().warning(f"Could not parse OT times: begin={ot_start_time}, end={ot_end_time}")
            return 0.0
        
        # Convert to datetime objects
        work_date = check_in_time.date()
        ot_start_datetime = datetime.combine(work_date, ot_start_time)
        ot_end_datetime = datetime.combine(work_date, ot_end_time)
        
        # Handle overnight OT
        if ot_end_datetime <= ot_start_datetime:
            ot_end_datetime += timedelta(days=1)
        
        # Calculate effective OT period
        effective_start = max(ot_start_datetime, check_in_time)
        effective_end = min(ot_end_datetime, check_out_time)
        
        if effective_end <= effective_start:
            return 0.0
        
        # Calculate actual hours
        actual_ot_hours = time_diff_in_hours(effective_end, effective_start)
        planned_ot_hours = flt(ot_request.get('planned_hours', 0))
        
        # Don't exceed planned hours
        final_ot_hours = min(actual_ot_hours, planned_ot_hours) if planned_ot_hours > 0 else actual_ot_hours
        
        frappe.logger().info(f"OT Calc: {ot_request['name']} - Actual: {actual_ot_hours}h, Planned: {planned_ot_hours}h, Final: {final_ot_hours}h")
        
        return flt(final_ot_hours, 2)
        
    except Exception as e:
        frappe.log_error(f"Error calculating actual OT: {str(e)}", "Actual OT Calculation")
        return 0.0


def get_overtime_details_for_doc(doc):
    """Get overtime details for document - UPDATED for new structure"""
    try:
        ot_requests = get_approved_overtime_requests_for_doc(doc)
        
        if not ot_requests:
            return {"has_overtime": False, "requests": []}
        
        overtime_details = []
        total_actual_ot_hours = 0.0
        
        if doc.check_in and doc.check_out:
            check_in_time = get_datetime(doc.check_in)
            check_out_time = get_datetime(doc.check_out)
            
            for req in ot_requests:
                actual_ot_hours = calculate_actual_overtime_for_request_doc(req, check_in_time, check_out_time)
                total_actual_ot_hours += actual_ot_hours
                
                overtime_details.append({
                    "request_name": req['name'],
                    "planned_from": str(req['begin_time']),    # Updated field name
                    "planned_to": str(req['end_time']),
                    "planned_hours": flt(req.get('planned_hours', 0), 2),
                    "actual_hours": flt(actual_ot_hours, 2),
                    "reason": req.get('reason', ''),
                    "group": req.get('group', '')
                })
        
        return {
            "has_overtime": True,
            "total_requests": len(ot_requests),
            "total_actual_ot_hours": flt(total_actual_ot_hours, 2),
            "requests": overtime_details
        }
        
    except Exception as e:
        frappe.log_error(f"Error getting overtime details: {str(e)}", "Overtime Details")
        return {"has_overtime": False, "error": str(e)}


def get_approved_overtime_hours_for_doc(doc):
    """Get approved overtime hours for document"""
    try:
        if not doc.check_in or not doc.check_out:
            return 0.0
            
        # Get OT requests
        overtime_requests = get_approved_overtime_requests_for_doc(doc)
        
        if not overtime_requests:
            return 0.0
        
        check_in_time = get_datetime(doc.check_in)
        check_out_time = get_datetime(doc.check_out)
        
        total_overtime_hours = 0.0
        
        for ot_request in overtime_requests:
            # Calculate actual OT for this request
            actual_ot_hours = calculate_actual_overtime_for_request_doc(ot_request, check_in_time, check_out_time)
            total_overtime_hours += actual_ot_hours
        
        return flt(total_overtime_hours, 2)
        
    except Exception as e:
        frappe.log_error(f"Error getting approved overtime hours: {str(e)}", "Approved Overtime Hours")
        return 0.0


# Enhanced calculation methods
def calculate_shift_duration_helper(shift_doc):
    """Calculate shift duration in hours"""
    if not shift_doc.start_time or not shift_doc.end_time:
        return 8.0  # Default 8 hours
    
    start_time = timedelta_to_time_helper(shift_doc.start_time)
    end_time = timedelta_to_time_helper(shift_doc.end_time)
    
    if not start_time or not end_time:
        return 8.0
    
    # Handle overnight shifts
    if end_time <= start_time:
        # Overnight shift
        duration = (24 * 3600 - start_time.hour * 3600 - start_time.minute * 60 + 
                   end_time.hour * 3600 + end_time.minute * 60) / 3600
    else:
        # Regular shift
        duration = ((end_time.hour * 3600 + end_time.minute * 60) - 
                   (start_time.hour * 3600 + start_time.minute * 60)) / 3600
    
    return flt(duration, 2)


def calculate_break_duration_helper(shift_doc):
    """Calculate break duration in hours"""
    try:
        # Check for custom break settings
        if getattr(shift_doc, 'custom_has_break', False):
            break_start = getattr(shift_doc, 'custom_break_start_time', None)
            break_end = getattr(shift_doc, 'custom_break_end_time', None)
        else:
            # Standard ERPNext break
            if not getattr(shift_doc, 'has_break', False):
                return 0.0
            break_start = getattr(shift_doc, 'break_start_time', None)
            break_end = getattr(shift_doc, 'break_end_time', None)
        
        if not break_start or not break_end:
            return 1.0  # Default 1 hour break
        
        break_start = timedelta_to_time_helper(break_start)
        break_end = timedelta_to_time_helper(break_end)
        
        if not break_start or not break_end:
            return 1.0
        
        # Calculate break duration
        if break_end <= break_start:
            # Overnight break (unusual but possible)
            duration = (24 * 3600 - break_start.hour * 3600 - break_start.minute * 60 + 
                       break_end.hour * 3600 + break_end.minute * 60) / 3600
        else:
            duration = ((break_end.hour * 3600 + break_end.minute * 60) - 
                       (break_start.hour * 3600 + break_start.minute * 60)) / 3600
        
        return flt(duration, 2)
        
    except Exception as e:
        frappe.logger().warning(f"Error calculating break duration: {str(e)}")
        return 1.0  # Default fallback


def calculate_working_hours_with_overtime_enhanced(doc):
    """
    Enhanced version with shift validation and break deduction
    """
    try:
        if not doc.check_in or not doc.check_out:
            return {"working_hours": 0.0, "overtime_hours": 0.0, "message": "Missing check times"}
        
        check_in_time = get_datetime(doc.check_in)
        check_out_time = get_datetime(doc.check_out)
        
        # Basic validation
        if check_out_time <= check_in_time:
            return {"working_hours": 0.0, "overtime_hours": 0.0, "message": "Invalid time range"}
        
        # Calculate total actual working time
        total_actual_hours = time_diff_in_hours(check_out_time, check_in_time)
        
        # Get shift information for proper calculation
        regular_hours = total_actual_hours
        overtime_hours = 0.0
        
        if doc.shift:
            try:
                shift_doc = frappe.get_cached_doc("Shift Type", doc.shift)
                
                if shift_doc.start_time and shift_doc.end_time:
                    # Calculate standard shift duration
                    shift_duration = calculate_shift_duration_helper(shift_doc)
                    
                    # Deduct break time if applicable
                    break_duration = calculate_break_duration_helper(shift_doc)
                    net_shift_duration = shift_duration - break_duration
                    
                    # Calculate regular vs overtime
                    if total_actual_hours > net_shift_duration:
                        regular_hours = net_shift_duration
                        overtime_hours = total_actual_hours - net_shift_duration
                    else:
                        regular_hours = total_actual_hours
                        overtime_hours = 0.0
                        
            except Exception as e:
                frappe.logger().warning(f"Error processing shift {doc.shift}: {str(e)}")
                # Fallback to basic calculation
                pass
        
        # Get approved overtime hours từ OT Requests
        approved_overtime = get_approved_overtime_hours_for_doc(doc)
        
        # Use the higher of calculated overtime or approved overtime
        final_overtime = max(overtime_hours, approved_overtime)
        
        # Final working hours = regular + actual approved overtime
        final_working_hours = regular_hours + final_overtime
        
        # Update document
        doc.working_hours = flt(final_working_hours, 2)
        doc.overtime_hours = flt(final_overtime, 2)
        
        return {
            "working_hours": flt(final_working_hours, 2),
            "overtime_hours": flt(final_overtime, 2),
            "regular_hours": flt(regular_hours, 2),
            "calculated_overtime": flt(overtime_hours, 2),
            "approved_overtime": flt(approved_overtime, 2),
            "message": f"Success: {final_working_hours}h total ({regular_hours}h regular + {final_overtime}h overtime)"
        }
        
    except Exception as e:
        return {"working_hours": 0.0, "overtime_hours": 0.0, "message": f"Error: {str(e)}"}