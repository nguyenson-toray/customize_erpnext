# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, add_days, today, date_diff, flt
from datetime import timedelta
from .overtime_calculator import calculate_working_hours_with_overtime_for_doc, get_approved_overtime_requests_for_doc
from .attendance_sync import sync_attendance_from_checkin_data
from .attendance_utils import get_active_employees_for_date
from .validators import validate_before_submit


def bulk_recalculate_overtime(date_from, date_to):
    """Bulk recalculate overtime cho date range"""
    try:
        date_from = getdate(date_from)
        date_to = getdate(date_to)
        
        # Get all attendance records trong date range có check-in/out
        attendance_records = frappe.get_all("Custom Attendance",
            filters={
                "attendance_date": ["between", [date_from, date_to]],
                "docstatus": 0,  # Only draft records
                "check_in": ["!=", ""],
                "check_out": ["!=", ""]
            },
            fields=["name", "employee", "attendance_date", "working_hours"]
        )
        
        success_count = 0
        error_count = 0
        total_ot_found = 0
        
        for record in attendance_records:
            try:
                doc = frappe.get_doc("Custom Attendance", record.name)
                
                # Store old working hours
                old_hours = doc.working_hours or 0
                
                # Recalculate
                doc.calculate_working_hours()
                doc.save()
                
                # Check if overtime was added
                if doc.working_hours > old_hours:
                    total_ot_found += 1
                
                success_count += 1
                
            except Exception as e:
                error_count += 1
                frappe.log_error(f"Bulk recalc error for {record.name}: {str(e)}", "Bulk Overtime Recalc")
                continue
        
        return {
            "success": True,
            "message": f"Recalculated {success_count} records, {total_ot_found} with overtime, {error_count} errors",
            "success_count": success_count,
            "error_count": error_count,
            "overtime_found_count": total_ot_found
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}


def bulk_process_from_shift_date(shift_name=None, start_date=None, end_date=None):
    """
    Bulk create và sync Custom Attendance từ Process Attendance After date
    """
    try:
        results = {
            "success": True,
            "total_days": 0,
            "total_employees": 0,
            "created_count": 0,
            "synced_count": 0,
            "error_count": 0,
            "details": [],
            "errors": []
        }
        
        # Get date range
        if shift_name:
            # Lấy từ shift settings
            shift_doc = frappe.get_doc("Shift Type", shift_name)
            start_date = shift_doc.process_attendance_after or getdate() - timedelta(days=30)
        elif start_date:
            start_date = getdate(start_date)
        else:
            start_date = getdate() - timedelta(days=30)  # Default 30 ngày trước
            
        if not end_date:
            end_date = getdate()  # Đến hôm nay
        else:
            end_date = getdate(end_date)
                
        # Validate date range
        if start_date > end_date:
            return {"success": False, "message": "Start date cannot be after end date"}
            
        days_count = date_diff(end_date, start_date) + 1
        if days_count > 90:  # Limit để tránh overload
            return {"success": False, "message": "Date range too large (maximum 90 days)"}
        
        results["total_days"] = days_count
        
        frappe.logger().info(f"Starting bulk process from {start_date} to {end_date}")
        
        # Process từng ngày
        current_date = start_date
        while current_date <= end_date:
            try:
                day_result = process_single_day_bulk(current_date, shift_name)
                
                results["total_employees"] += day_result["employees_processed"]
                results["created_count"] += day_result["created_count"]
                results["synced_count"] += day_result["synced_count"]  
                results["error_count"] += day_result["error_count"]
                
                if day_result["created_count"] > 0 or day_result["error_count"] > 0:
                    results["details"].append({
                        "date": str(current_date),
                        "created": day_result["created_count"],
                        "synced": day_result["synced_count"],
                        "errors": day_result["error_count"]
                    })
                
                results["errors"].extend(day_result["errors"])
                
                # Commit sau mỗi ngày để tránh timeout
                frappe.db.commit()
                
            except Exception as e:
                error_msg = f"Error processing {current_date}: {str(e)}"
                results["errors"].append(error_msg)
                results["error_count"] += 1
                frappe.log_error(error_msg, "Bulk Process Custom Attendance")
                
            current_date += timedelta(days=1)
        
        # Summary message
        results["message"] = f"""Bulk processing completed:
        Processed {results['total_days']} days
        Found {results['total_employees']} employee-days with check-ins
        Created {results['created_count']} Custom Attendance records
        Synced {results['synced_count']} records successfully
        {results['error_count']} errors encountered"""
        
        frappe.logger().info(f"Bulk process completed: {results['message']}")
        
        return results
        
    except Exception as e:
        error_msg = f"Error in bulk_process_from_shift_date: {str(e)}"
        frappe.log_error(error_msg, "Bulk Process Custom Attendance")
        return {"success": False, "message": error_msg}


def process_single_day_bulk(date, shift_name=None):
    """Process Custom Attendance cho một ngày cụ thể"""
    try:
        result = {
            "employees_processed": 0,
            "created_count": 0,
            "synced_count": 0,
            "error_count": 0,
            "errors": []
        }
        
        # Get employees có check-ins trong ngày này
        filters = {
            "DATE(time)": date,
            "employee": ["!=", ""]
        }
        
        if shift_name:
            # Lọc theo shift cụ thể
            filters["shift"] = shift_name
            
        # Query employees có checkins
        employees_with_checkins = frappe.db.sql("""
            SELECT DISTINCT 
                ec.employee, 
                e.employee_name, 
                e.company,
                COALESCE(ec.shift, e.default_shift) as shift_type
            FROM `tabEmployee` e  
            INNER JOIN `tabEmployee Checkin` ec ON ec.employee = e.name AND DATE(ec.time) = %s
            WHERE e.status = 'Active'
            {}
            AND NOT EXISTS (
                SELECT 1 FROM `tabCustom Attendance` ca 
                WHERE ca.employee = ec.employee 
                AND ca.attendance_date = %s
                AND ca.docstatus != 2
            )
        """.format("AND (ec.shift = %s OR e.default_shift = %s)" if shift_name else ""),
        (date, shift_name, shift_name, date) if shift_name else (date, date), as_dict=True)
        
        result["employees_processed"] = len(employees_with_checkins)
        
        # Tạo Custom Attendance cho từng employee
        for emp in employees_with_checkins:
            try:
                # Create Custom Attendance
                custom_attendance = frappe.new_doc("Custom Attendance")
                custom_attendance.employee = emp.employee
                custom_attendance.employee_name = emp.employee_name
                custom_attendance.attendance_date = date
                custom_attendance.company = emp.company
                custom_attendance.shift = emp.shift_type
                custom_attendance.auto_sync_enabled = 1
                custom_attendance.status = "Absent"  # Will be updated after sync
                
                # Skip validations during bulk creation
                custom_attendance.flags.ignore_validate = True
                custom_attendance.flags.ignore_auto_sync = True
                custom_attendance.flags.ignore_duplicate_check = True
                
                # Save
                custom_attendance.save(ignore_permissions=True)
                result["created_count"] += 1
                
                # Auto sync from checkins
                try:
                    sync_result = sync_attendance_from_checkin_data(custom_attendance)
                    if "successfully" in str(sync_result).lower() or "success" in str(sync_result).lower():
                        result["synced_count"] += 1
                    else:
                        result["errors"].append(f"{emp.employee} ({date}): Sync issue - {sync_result}")
                        
                except Exception as sync_error:
                    result["errors"].append(f"{emp.employee} ({date}): Sync failed - {str(sync_error)}")
                    
            except Exception as create_error:
                result["error_count"] += 1
                error_msg = f"{emp.employee} ({date}): Create failed - {str(create_error)}"
                result["errors"].append(error_msg)
                frappe.log_error(error_msg, "Bulk Process Single Employee")
                
        return result
        
    except Exception as e:
        return {
            "employees_processed": 0,
            "created_count": 0, 
            "synced_count": 0,
            "error_count": 1,
            "errors": [f"Day processing failed: {str(e)}"]
        }


def get_bulk_process_preview_data(shift_name=None, start_date=None, end_date=None):
    """Preview data trước khi bulk process"""
    try:
        # Get date range
        if shift_name:
            shift_doc = frappe.get_doc("Shift Type", shift_name)
            start_date = shift_doc.process_attendance_after or getdate() - timedelta(days=30)
        elif start_date:
            start_date = getdate(start_date)
        else:
            start_date = getdate() - timedelta(days=30)
            
        if not end_date:
            end_date = getdate()
        else:
            end_date = getdate(end_date)
            
        # Get summary data
        preview_data = frappe.db.sql("""
            SELECT 
                DATE(ec.time) as attendance_date,
                COUNT(DISTINCT ec.employee) as employee_count,
                COUNT(ec.name) as checkin_count,
                COUNT(DISTINCT COALESCE(ec.shift, e.default_shift)) as shift_count
            FROM `tabEmployee` e
            INNER JOIN `tabEmployee Checkin` ec ON ec.employee = e.name 
            WHERE DATE(ec.time) BETWEEN %s AND %s
            AND e.status = 'Active'
            {}
            AND NOT EXISTS (
                SELECT 1 FROM `tabCustom Attendance` ca 
                WHERE ca.employee = ec.employee 
                AND ca.attendance_date = DATE(ec.time)
                AND ca.docstatus != 2
            )
            GROUP BY DATE(ec.time)
            ORDER BY DATE(ec.time)
        """.format("AND (ec.shift = %s OR e.default_shift = %s)" if shift_name else ""),
        (start_date, end_date, shift_name, shift_name) if shift_name else (start_date, end_date), as_dict=True)
        
        total_employees = sum([row.employee_count for row in preview_data])
        total_days = len(preview_data)
        
        return {
            "success": True,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "total_days": total_days,
            "total_employees": total_employees,  
            "daily_breakdown": preview_data,
            "shift_name": shift_name
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}


def bulk_sync_custom_attendance(date_from, date_to):
    """Bulk sync Custom Attendance records trong date range"""
    try:
        date_from = getdate(date_from)
        date_to = getdate(date_to)
        
        records = frappe.get_all("Custom Attendance",
            filters={
                "attendance_date": ["between", [date_from, date_to]],
                "auto_sync_enabled": 1,
                "docstatus": 0
            },
            fields=["name", "employee", "attendance_date"]
        )
        
        success_count = 0
        error_count = 0
        
        for record in records:
            try:
                doc = frappe.get_doc("Custom Attendance", record.name)
                sync_result = sync_attendance_from_checkin_data(doc)
                
                if "successfully" in str(sync_result).lower():
                    success_count += 1
                else:
                    error_count += 1
                    
                frappe.db.commit()
                
            except Exception as e:
                error_count += 1
                frappe.log_error(f"Bulk sync error for {record.name}: {str(e)}", "Bulk Sync Custom Attendance")
                continue
        
        return {
            "success": True, 
            "message": f"Bulk sync completed: {success_count} success, {error_count} errors",
            "success_count": success_count,
            "error_count": error_count
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}


def bulk_daily_completion_range(start_date, end_date):
    """
    Bulk daily completion cho nhiều ngày
    """
    try:
        start_date = getdate(start_date)
        end_date = getdate(end_date)
        
        if start_date > end_date:
            return {"success": False, "message": "Start date cannot be after end date"}
            
        # Limit 30 days để tránh overload
        if date_diff(end_date, start_date) > 30:
            return {"success": False, "message": "Date range too large (maximum 30 days)"}
        
        results = {
            "success": True,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "total_created": 0,
            "total_updated": 0,
            "total_errors": 0,
            "daily_results": [],
            "errors": []
        }
        
        current_date = start_date
        while current_date <= end_date:
            from .scheduler_jobs import daily_attendance_completion_for_date
            day_result = daily_attendance_completion_for_date(current_date)
            
            if day_result["success"]:
                results["total_created"] += day_result["created_count"]
                results["total_updated"] += day_result["updated_count"]
                results["total_errors"] += day_result["error_count"]
                
                if day_result["created_count"] > 0 or day_result["updated_count"] > 0:
                    results["daily_results"].append({
                        "date": str(current_date),
                        "created": day_result["created_count"],
                        "updated": day_result["updated_count"],
                        "errors": day_result["error_count"]
                    })
                
                results["errors"].extend(day_result["errors"])
            else:
                results["total_errors"] += 1
                results["errors"].append(f"{current_date}: {day_result['message']}")
            
            current_date = add_days(current_date, 1)
            frappe.db.commit()  # Commit sau mỗi ngày
        
        results["message"] = f"""Bulk completion: {results['total_created']} created, {results['total_updated']} updated, {results['total_errors']} errors"""
        
        return results
        
    except Exception as e:
        return {"success": False, "message": str(e)}


def migrate_existing_attendance_records():
    """Migrate existing Custom Attendance records to include overtime calculation"""
    try:
        # Get records that might have overtime but overtime_hours = 0
        records = frappe.db.sql("""
            SELECT ca.name, ca.employee, ca.attendance_date
            FROM `tabCustom Attendance` ca
            WHERE ca.overtime_hours = 0
            AND ca.check_in IS NOT NULL 
            AND ca.check_out IS NOT NULL
            AND ca.docstatus = 0
            AND EXISTS (
                SELECT 1 FROM `tabOvertime Registration` ot
                INNER JOIN `tabOvertime Registration Detail` ote ON ote.parent = ot.name
                WHERE ote.employee = ca.employee
                AND ote.date = ca.attendance_date
                AND ot.status = 'Approved'
                AND ot.docstatus = 1
            )
            LIMIT 100
        """, as_dict=True)
        
        updated_count = 0
        error_count = 0
        
        for record in records:
            try:
                doc = frappe.get_doc("Custom Attendance", record.name)
                old_hours = doc.working_hours
                old_overtime = doc.overtime_hours
                
                result = calculate_working_hours_with_overtime_for_doc(doc)
                
                if result["overtime_hours"] > 0:
                    doc.flags.ignore_validate_update_after_submit = True
                    doc.save(ignore_permissions=True)
                    updated_count += 1
                    
                    print(f"Updated {record.name}: {old_hours}h -> {doc.working_hours}h (OT: {old_overtime} -> {doc.overtime_hours})")
                    
            except Exception as e:
                error_count += 1
                print(f"Error updating {record.name}: {str(e)}")
                continue
        
        frappe.db.commit()
        
        return {
            "success": True,
            "message": f"Migration completed: {updated_count} updated, {error_count} errors",
            "updated_count": updated_count,
            "error_count": error_count
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}


def bulk_submit_attendance_records(start_date, end_date):
    """
    Bulk submit Custom Attendance records trong date range
    """
    try:
        start_date = getdate(start_date)
        end_date = getdate(end_date)
        
        # Validate date range
        if start_date > end_date:
            return {"success": False, "message": "Start date cannot be after end date"}
            
        days_count = date_diff(end_date, start_date) + 1
        if days_count > 90:  # Limit để tránh overload
            return {"success": False, "message": "Date range too large (maximum 90 days)"}
        
        # Lấy tất cả records chưa submit trong khoảng thời gian
        draft_records = frappe.get_all("Custom Attendance", 
            filters={
                "docstatus": 0,  # Draft
                "attendance_date": ["between", [start_date, end_date]]
            },
            fields=["name", "employee", "employee_name", "attendance_date", "status", "working_hours"],
            order_by="attendance_date asc, employee asc"
        )
        
        if not draft_records:
            return {
                "success": True, 
                "message": "No draft records found to submit",
                "submitted_count": 0,
                "error_count": 0
            }
        
        # Counters
        submitted_count = 0
        error_count = 0
        errors = []
        
        # Process records by batches để tránh timeout
        batch_size = 50
        total_records = len(draft_records)
        
        for i in range(0, total_records, batch_size):
            batch = draft_records[i:i + batch_size]
            
            for record in batch:
                try:
                    # Load document
                    doc = frappe.get_doc("Custom Attendance", record.name)
                    
                    # Validate trước khi submit
                    validation_result = validate_before_submit(doc)
                    if not validation_result["valid"]:
                        error_msg = f"{record.name}: {validation_result['message']}"
                        errors.append(error_msg)
                        error_count += 1
                        frappe.logger().warning(error_msg)
                        continue
                    
                    # Submit document
                    doc.submit()
                    submitted_count += 1
                    
                except Exception as e:
                    error_msg = f"{record.name}: {str(e)}"
                    errors.append(error_msg)
                    error_count += 1
                    frappe.logger().error(f"Failed to submit {record.name}: {str(e)}")
                    
            # Commit sau mỗi batch
            frappe.db.commit()
            
        # Kết quả
        result = {
            "success": True,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "total_found": total_records,
            "submitted_count": submitted_count,
            "error_count": error_count,
            "errors": errors[:20]  # Chỉ lấy 20 errors đầu tiên
        }
        
        frappe.logger().info(f"Bulk submit completed: {submitted_count}/{total_records} records submitted, {error_count} errors")
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Bulk submit error: {str(e)}", "Bulk Submit Custom Attendance")
        return {"success": False, "message": str(e)}


def bulk_cancel_attendance_records(start_date, end_date, reason="Bulk cancellation"):
    """
    Bulk cancel Custom Attendance records trong date range
    """
    try:
        start_date = getdate(start_date)
        end_date = getdate(end_date)
        
        # Validate date range
        if start_date > end_date:
            return {"success": False, "message": "Start date cannot be after end date"}
            
        days_count = date_diff(end_date, start_date) + 1
        if days_count > 30:  # Smaller limit for cancellation
            return {"success": False, "message": "Date range too large (maximum 30 days)"}
        
        # Lấy tất cả submitted records trong khoảng thời gian
        submitted_records = frappe.get_all("Custom Attendance", 
            filters={
                "docstatus": 1,  # Submitted
                "attendance_date": ["between", [start_date, end_date]]
            },
            fields=["name", "employee", "employee_name", "attendance_date"],
            order_by="attendance_date asc, employee asc"
        )
        
        if not submitted_records:
            return {
                "success": True, 
                "message": "No submitted records found to cancel",
                "cancelled_count": 0,
                "error_count": 0
            }
        
        # Counters
        cancelled_count = 0
        error_count = 0
        errors = []
        
        for record in submitted_records:
            try:
                # Load document
                doc = frappe.get_doc("Custom Attendance", record.name)
                
                # Add cancellation reason
                doc.add_comment("Comment", f"Bulk cancelled: {reason}")
                
                # Cancel document
                doc.cancel()
                cancelled_count += 1
                
            except Exception as e:
                error_msg = f"{record.name}: {str(e)}"
                errors.append(error_msg)
                error_count += 1
                frappe.logger().error(f"Failed to cancel {record.name}: {str(e)}")
                
        # Commit changes
        frappe.db.commit()
        
        result = {
            "success": True,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "total_found": len(submitted_records),
            "cancelled_count": cancelled_count,
            "error_count": error_count,
            "errors": errors[:10]  # Chỉ lấy 10 errors đầu tiên
        }
        
        frappe.logger().info(f"Bulk cancel completed: {cancelled_count}/{len(submitted_records)} records cancelled, {error_count} errors")
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Bulk cancel error: {str(e)}", "Bulk Cancel Custom Attendance")
        return {"success": False, "message": str(e)}


def bulk_delete_draft_attendance_records(start_date, end_date):
    """
    Bulk delete draft Custom Attendance records trong date range
    """
    try:
        start_date = getdate(start_date)
        end_date = getdate(end_date)
        
        # Validate date range
        if start_date > end_date:
            return {"success": False, "message": "Start date cannot be after end date"}
            
        days_count = date_diff(end_date, start_date) + 1
        if days_count > 30:  # Limit for safety
            return {"success": False, "message": "Date range too large (maximum 30 days)"}
        
        # Lấy tất cả draft records trong khoảng thời gian
        draft_records = frappe.get_all("Custom Attendance", 
            filters={
                "docstatus": 0,  # Draft
                "attendance_date": ["between", [start_date, end_date]]
            },
            fields=["name", "employee", "attendance_date"],
            order_by="attendance_date asc, employee asc"
        )
        
        if not draft_records:
            return {
                "success": True, 
                "message": "No draft records found to delete",
                "deleted_count": 0,
                "error_count": 0
            }
        
        # Counters
        deleted_count = 0
        error_count = 0
        errors = []
        
        for record in draft_records:
            try:
                # Load and delete document
                doc = frappe.get_doc("Custom Attendance", record.name)
                doc.delete()
                deleted_count += 1
                
            except Exception as e:
                error_msg = f"{record.name}: {str(e)}"
                errors.append(error_msg)
                error_count += 1
                frappe.logger().error(f"Failed to delete {record.name}: {str(e)}")
                
        # Commit changes
        frappe.db.commit()
        
        result = {
            "success": True,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "total_found": len(draft_records),
            "deleted_count": deleted_count,
            "error_count": error_count,
            "errors": errors[:10]  # Chỉ lấy 10 errors đầu tiên
        }
        
        frappe.logger().info(f"Bulk delete completed: {deleted_count}/{len(draft_records)} records deleted, {error_count} errors")
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Bulk delete error: {str(e)}", "Bulk Delete Custom Attendance")
        return {"success": False, "message": str(e)}


def get_bulk_operations_summary(start_date, end_date):
    """
    Get summary of attendance records for bulk operations planning
    """
    try:
        start_date = getdate(start_date)
        end_date = getdate(end_date)
        
        # Count by status
        status_summary = frappe.db.sql("""
            SELECT 
                docstatus,
                status,
                COUNT(*) as count
            FROM `tabCustom Attendance`
            WHERE attendance_date BETWEEN %s AND %s
            GROUP BY docstatus, status
            ORDER BY docstatus, status
        """, (start_date, end_date), as_dict=True)
        
        # Count by dates
        daily_summary = frappe.db.sql("""
            SELECT 
                attendance_date,
                COUNT(*) as total_records,
                SUM(CASE WHEN docstatus = 0 THEN 1 ELSE 0 END) as draft_count,
                SUM(CASE WHEN docstatus = 1 THEN 1 ELSE 0 END) as submitted_count,
                SUM(CASE WHEN docstatus = 2 THEN 1 ELSE 0 END) as cancelled_count
            FROM `tabCustom Attendance`
            WHERE attendance_date BETWEEN %s AND %s
            GROUP BY attendance_date
            ORDER BY attendance_date
        """, (start_date, end_date), as_dict=True)
        
        return {
            "success": True,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "status_summary": status_summary,
            "daily_summary": daily_summary
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}