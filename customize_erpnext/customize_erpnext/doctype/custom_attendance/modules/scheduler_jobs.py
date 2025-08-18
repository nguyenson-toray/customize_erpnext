# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import getdate, add_days, today, now_datetime, cint, flt
from datetime import datetime, timedelta, time
from .attendance_utils import get_active_employees_for_date, timedelta_to_time_helper
from .attendance_sync import sync_attendance_from_checkin_data, create_attendance_from_checkin
from .validators import validate_before_submit


def daily_attendance_completion():
    """
    Tạo Custom Attendance cho TẤT CẢ nhân viên active (bao gồm Absent)
    Chạy hàng ngày để đảm bảo không ai bị thiếu attendance record
    """
    try:
        # Lấy ngày cần xử lý (hôm qua hoặc theo cấu hình)
        target_date = add_days(today(), -1)  # Hôm qua
        
        frappe.logger().info(f"Starting daily attendance completion for {target_date}")
        
        # Lấy tất cả nhân viên active
        active_employees = get_active_employees_for_date(target_date)
        
        if not active_employees:
            frappe.logger().info("No active employees found")
            return
        
        # Counters
        created_count = 0
        updated_count = 0
        error_count = 0
        errors = []
        
        for employee in active_employees:
            try:
                result = process_employee_daily_attendance(employee, target_date)
                
                if result['action'] == 'created':
                    created_count += 1
                elif result['action'] == 'updated':
                    updated_count += 1
                    
            except Exception as e:
                error_count += 1
                error_msg = f"Employee {employee['name']}: {str(e)}"
                errors.append(error_msg)
                frappe.log_error(error_msg, "Daily Attendance Completion")
                continue
        
        # Log results
        frappe.logger().info(
            f"Daily attendance completion for {target_date}: "
            f"{created_count} created, {updated_count} updated, {error_count} errors"
        )
        
        # Commit changes
        frappe.db.commit()
        
        return {
            "success": True,
            "date": target_date,
            "total_employees": len(active_employees),
            "created_count": created_count,
            "updated_count": updated_count,
            "error_count": error_count,
            "errors": errors[:10]  # First 10 errors only
        }
        
    except Exception as e:
        frappe.log_error(f"Error in daily_attendance_completion: {str(e)}", "Daily Attendance Completion")
        return {"success": False, "message": str(e)}


def process_employee_daily_attendance(employee, target_date):
    """
    Xử lý attendance cho một nhân viên trong ngày cụ thể
    """
    try:
        # Check if Custom Attendance already exists
        existing_attendance = frappe.db.get_value("Custom Attendance", {
            "employee": employee['name'],
            "attendance_date": target_date,
            "docstatus": ["!=", 2]  # Not cancelled
        }, ["name", "docstatus", "status", "auto_sync_enabled"])
        
        if existing_attendance:
            # Update existing record if needed
            return update_existing_attendance(existing_attendance, employee, target_date)
        else:
            # Create new attendance record
            return create_new_attendance(employee, target_date)
            
    except Exception as e:
        raise Exception(f"Process failed: {str(e)}")


def create_new_attendance(employee, target_date):
    """
    Tạo Custom Attendance mới cho nhân viên
    """
    try:
        # Check if employee has checkins
        has_checkins = frappe.db.exists("Employee Checkin", {
            "employee": employee['name'],
            "time": ["between", [
                f"{target_date} 00:00:00",
                f"{target_date} 23:59:59"
            ]]
        })
        
        # Create new Custom Attendance
        custom_attendance = frappe.new_doc("Custom Attendance")
        custom_attendance.employee = employee['name']
        custom_attendance.employee_name = employee['employee_name']
        custom_attendance.attendance_date = target_date
        custom_attendance.company = employee['company']
        custom_attendance.department = employee['department']
        custom_attendance.shift = employee['default_shift']
        custom_attendance.auto_sync_enabled = 1
        
        # Set initial status
        if has_checkins:
            custom_attendance.status = "Present"  # Will be refined after sync
        else:
            custom_attendance.status = "Absent"
            
        # Skip validations during auto creation
        custom_attendance.flags.ignore_validate = True
        custom_attendance.flags.ignore_auto_sync = True
        custom_attendance.flags.ignore_duplicate_check = True
        
        # Save
        custom_attendance.save(ignore_permissions=True)
        
        # Auto sync if has checkins
        if has_checkins:
            sync_attendance_from_checkin_data(custom_attendance)
            
        frappe.logger().info(f"Created Custom Attendance: {custom_attendance.name} for {employee['name']} - Status: {custom_attendance.status}")
        
        return {"action": "created", "name": custom_attendance.name, "status": custom_attendance.status}
        
    except Exception as e:
        raise Exception(f"Create failed: {str(e)}")


def update_existing_attendance(existing_attendance, employee, target_date):
    """
    Update existing Custom Attendance if needed
    """
    try:
        attendance_name = existing_attendance[0] if isinstance(existing_attendance, (list, tuple)) else existing_attendance
        
        # Load document
        doc = frappe.get_doc("Custom Attendance", attendance_name)
        
        # Only update if auto_sync is enabled and not submitted
        if doc.auto_sync_enabled and doc.docstatus == 0:
            # Check if employee has checkins
            has_checkins = frappe.db.exists("Employee Checkin", {
                "employee": employee['name'],
                "time": ["between", [
                    f"{target_date} 00:00:00",
                    f"{target_date} 23:59:59"
                ]]
            })
            
            if has_checkins and doc.status == "Absent":
                # Had no checkins before, but now has checkins - sync
                sync_attendance_from_checkin_data(doc)
                frappe.logger().info(f"Updated Custom Attendance: {doc.name} - Status changed from Absent to {doc.status}")
                return {"action": "updated", "name": doc.name, "status": doc.status}
            elif not has_checkins and doc.status != "Absent":
                # Had checkins before, but now no checkins - mark as Absent
                doc.status = "Absent"
                doc.check_in = None
                doc.check_out = None
                doc.working_hours = 0
                doc.in_time = None
                doc.out_time = None
                doc.late_entry = 0
                doc.early_exit = 0
                
                doc.flags.ignore_validate_update_after_submit = True
                doc.save(ignore_permissions=True)
                
                frappe.logger().info(f"Updated Custom Attendance: {doc.name} - Status changed to Absent")
                return {"action": "updated", "name": doc.name, "status": "Absent"}
        
        return {"action": "skipped", "name": attendance_name, "reason": "No update needed"}
        
    except Exception as e:
        raise Exception(f"Update failed: {str(e)}")


def daily_attendance_completion_for_date(target_date):
    """
    Daily completion cho ngày cụ thể
    """
    try:
        frappe.logger().info(f"Manual daily attendance completion for {target_date}")
        
        # Lấy tất cả nhân viên active
        active_employees = get_active_employees_for_date(target_date)
        
        if not active_employees:
            return {"success": True, "message": "No active employees found", "created_count": 0}
        
        # Counters
        created_count = 0
        updated_count = 0
        error_count = 0
        errors = []
        
        for employee in active_employees:
            try:
                result = process_employee_daily_attendance(employee, target_date)
                
                if result['action'] == 'created':
                    created_count += 1
                elif result['action'] == 'updated':
                    updated_count += 1
                    
            except Exception as e:
                error_count += 1
                error_msg = f"Employee {employee['name']}: {str(e)}"
                errors.append(error_msg)
                continue
        
        return {
            "success": True,
            "date": str(target_date),
            "total_employees": len(active_employees),
            "created_count": created_count,
            "updated_count": updated_count,
            "error_count": error_count,
            "errors": errors[:10],
            "message": f"Completed for {target_date}: {created_count} created, {updated_count} updated, {error_count} errors"
        }
        
    except Exception as e:
        frappe.log_error(f"Error in daily_attendance_completion_for_date: {str(e)}", "Daily Attendance Completion")
        return {"success": False, "message": str(e)}


def auto_submit_custom_attendance():
    """
    Tự động submit tất cả Custom Attendance records (trừ ngày hôm nay)
    Chạy hàng ngày qua scheduler
    """
    try:
        # Check if feature is enabled (fallback to True if setting doesn't exist)
        try:
            auto_submit_enabled = frappe.db.get_single_value("HR Settings", "custom_auto_submit_attendance_enabled")
            if auto_submit_enabled is None:
                auto_submit_enabled = True  # Default enabled
        except:
            auto_submit_enabled = True  # Fallback if settings table doesn't exist
            
        if not auto_submit_enabled:
            frappe.logger().info("Auto submit Custom Attendance is disabled in HR Settings")
            return {"success": True, "message": "Auto submit disabled"}
        
        # Use settings or default values
        try:
            lookback_days = frappe.db.get_single_value("HR Settings", "custom_auto_submit_attendance_days") or 30
        except:
            lookback_days = 30  # Default
        
        # Giới hạn tối đa 90 ngày
        if lookback_days > 90:
            lookback_days = 90
            
        # Tính toán date range (từ X ngày trước đến hôm qua)
        end_date = add_days(today(), -1)  # Hôm qua
        start_date = add_days(end_date, -lookback_days)  # X ngày trước
        
        frappe.logger().info(f"Auto submit Custom Attendance from {start_date} to {end_date}")
        
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
            frappe.logger().info("No draft Custom Attendance records found to submit")
            return {
                "success": True, 
                "message": "No records to submit",
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
        
        frappe.logger().info(f"Auto submit completed: {submitted_count}/{total_records} records submitted, {error_count} errors")
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Auto submit Custom Attendance error: {str(e)}", "Auto Submit Custom Attendance")
        return {"success": False, "message": str(e)}


def auto_daily_attendance_completion():
    """
    Enhanced scheduler function - chạy hàng ngày với settings support
    """
    try:
        # Check if feature is enabled (fallback to True if setting doesn't exist)
        try:
            completion_enabled = frappe.db.get_single_value("HR Settings", "custom_daily_attendance_completion_enabled")
            if completion_enabled is None:
                completion_enabled = True  # Default enabled
        except:
            completion_enabled = True  # Fallback if settings table doesn't exist
            
        if not completion_enabled:
            frappe.logger().info("Daily attendance completion is disabled in HR Settings")
            return
        
        result = daily_attendance_completion()
        
        if result and result.get("success"):
            frappe.logger().info(f"Auto daily attendance completion: {result.get('message', 'Completed')}")
        else:
            frappe.logger().error(f"Auto daily attendance completion failed: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        frappe.log_error(f"Auto daily attendance completion error: {str(e)}", "Auto Daily Attendance Completion")


def auto_bulk_create_custom_attendance():
    """
    Tự động bulk create Custom Attendance cho các ngày trước đó
    Chạy hàng ngày qua scheduler
    """
    try:
        # Lấy settings từ System Settings hoặc Custom Settings DocType
        # auto_create_days = frappe.db.get_single_value("HR Settings", "auto_create_attendance_days") or 7
        
        # Hoặc hardcode số ngày muốn tự động tạo (ví dụ 3 ngày trước)
        auto_create_days = 3
        
        end_date = add_days(today(), -1)  # Hôm qua
        start_date = add_days(end_date, -auto_create_days)  # 3 ngày trước
        
        # Log để debug
        frappe.logger().info(f"Auto bulk create Custom Attendance from {start_date} to {end_date}")
        
        # Gọi function bulk process có sẵn
        from .bulk_operations import bulk_process_from_shift_date
        result = bulk_process_from_shift_date(
            start_date=start_date,
            end_date=end_date
        )
        
        if result.get('success'):
            frappe.logger().info(f"Auto bulk create completed: {result.get('created_count', 0)} records created")
            
            # Gửi email thông báo cho HR Manager (optional)
            # send_auto_create_notification(result)
            
        else:
            frappe.logger().error(f"Auto bulk create failed: {result.get('message', 'Unknown error')}")
            
    except Exception as e:
        frappe.logger().error(f"Auto bulk create Custom Attendance error: {str(e)}")
        frappe.log_error(f"Auto bulk create error: {str(e)}", "Auto Bulk Create Custom Attendance")


# Smart scheduler for shift-based processing
def smart_auto_update_custom_attendance():
    """
    Smart scheduler - chỉ chạy khi shifts thực sự kết thúc + tolerance time
    Thay vì chạy mỗi 15 phút, chỉ chạy khi cần thiết
    """
    try:
        current_time = now_datetime()
        current_date = getdate()
        
        # Get all active shifts có auto attendance enabled
        shifts = get_shifts_ready_for_processing(current_time)
        
        if not shifts:
            return  # Không có shift nào cần process
            
        processed_count = 0
        
        for shift_info in shifts:
            try:
                employees = get_employees_for_shift_processing(shift_info)
                
                for employee in employees:
                    if process_employee_custom_attendance(employee, shift_info):
                        processed_count += 1
                        
            except Exception as e:
                frappe.log_error(f"Error processing shift {shift_info['name']}: {str(e)}", "Smart Auto Custom Attendance")
                continue
        
        if processed_count > 0:
            frappe.logger().info(f"Smart auto-update processed {processed_count} Custom Attendance records")
            
    except Exception as e:
        frappe.log_error(f"Error in smart_auto_update_custom_attendance: {str(e)}", "Smart Auto Custom Attendance")


def get_shifts_ready_for_processing(current_time):
    """
    Get shifts sẵn sàng để process based on end time + tolerance
    Chỉ return shifts thực sự cần process ngay bây giờ
    """
    try:
        # Get all active shifts with auto attendance enabled
        shifts = frappe.db.sql("""
            SELECT 
                name, 
                start_time, 
                end_time, 
                allow_check_out_after_shift_end_time,
                process_attendance_after,
                last_sync_of_checkin
            FROM `tabShift Type`
            WHERE enable_auto_attendance = 1
        """, as_dict=True)
        
        ready_shifts = []
        
        for shift in shifts:
            if is_shift_ready_for_processing(shift, current_time):
                # Add processing info
                shift['processing_date'] = calculate_processing_date(shift, current_time)
                shift['tolerance_minutes'] = cint(shift.get('allow_check_out_after_shift_end_time', 60))
                ready_shifts.append(shift)
        
        return ready_shifts
        
    except Exception as e:
        frappe.log_error(f"Error getting ready shifts: {str(e)}", "Smart Auto Custom Attendance")
        return []


def is_shift_ready_for_processing(shift, current_time):
    """
    Check if shift is ready for processing dựa trên ERPNext logic:
    1. Shift đã kết thúc + tolerance time
    2. Sau process_attendance_after date
    3. Chưa process gần đây (tránh duplicate)
    """
    try:
        # Check process_attendance_after date
        if shift.process_attendance_after and getdate() < getdate(shift.process_attendance_after):
            return False
            
        if not shift.end_time:
            return False
            
        # Calculate actual shift end time + tolerance
        tolerance_minutes = cint(shift.get('allow_check_out_after_shift_end_time', 60))
        
        # Convert shift end time to datetime
        end_time = shift.end_time
        if hasattr(end_time, 'total_seconds'):
            total_seconds = int(end_time.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            end_time = datetime.min.time().replace(hour=hours, minute=minutes)
        
        # Determine which date this shift ended
        shift_date = current_time.date()
        
        # Handle overnight shifts
        if shift.start_time and shift.end_time <= shift.start_time:
            # Overnight shift - end time is next day
            if current_time.time() < end_time:
                # We're in the next day, shift ended today
                shift_end_datetime = datetime.combine(shift_date, end_time)
            else:
                # We're still in same day, shift will end tomorrow
                shift_end_datetime = datetime.combine(shift_date + timedelta(days=1), end_time)
        else:
            # Regular shift - same day
            shift_end_datetime = datetime.combine(shift_date, end_time)
        
        # Add tolerance time
        processing_time = shift_end_datetime + timedelta(minutes=tolerance_minutes)
        
        # Check if it's time to process (within 5-minute window để avoid missing)
        time_diff = (current_time - processing_time).total_seconds()
        
        # Ready if:
        # 1. Current time is after processing_time
        # 2. But not more than 30 minutes late (to avoid old processing)
        return 0 <= time_diff <= 1800  # 0-30 minutes after processing time
        
    except Exception as e:
        frappe.log_error(f"Error checking shift readiness: {str(e)}", "Smart Auto Custom Attendance")
        return False


def calculate_processing_date(shift, current_time):
    """Calculate which date this shift should be processed for"""
    try:
        if not shift.start_time or not shift.end_time:
            return current_time.date()
            
        # Convert times
        start_time = shift.start_time
        end_time = shift.end_time
        
        if hasattr(start_time, 'total_seconds'):
            total_seconds = int(start_time.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            start_time = datetime.min.time().replace(hour=hours, minute=minutes)
            
        if hasattr(end_time, 'total_seconds'):
            total_seconds = int(end_time.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            end_time = datetime.min.time().replace(hour=hours, minute=minutes)
        
        current_date = current_time.date()
        
        if end_time <= start_time:
            # Overnight shift
            if current_time.time() < end_time:
                # We're in the "next day" part of shift
                return current_date - timedelta(days=1)  # Attendance date is previous day
            else:
                return current_date  # Attendance date is today
        else:
            # Regular shift
            return current_date
            
    except Exception as e:
        frappe.log_error(f"Error calculating processing date: {str(e)}", "Smart Auto Custom Attendance")
        return current_time.date()


def get_employees_for_shift_processing(shift_info):
    """Get employees cần process cho shift này"""
    try:
        processing_date = shift_info['processing_date']
        
        # Get employees có checkins trong shift này và chưa có Custom Attendance
        employees = frappe.db.sql("""
            SELECT DISTINCT ec.employee, e.employee_name, e.company
            FROM `tabEmployee` e
            INNER JOIN `tabEmployee Checkin` ec ON ec.employee = e.name
            WHERE e.status = 'Active'
            AND DATE(ec.time) = %s
            AND (ec.shift = %s OR e.default_shift = %s)
            AND NOT EXISTS (
                SELECT 1 FROM `tabCustom Attendance` ca 
                WHERE ca.employee = ec.employee 
                AND ca.attendance_date = %s
                AND ca.docstatus != 2
            )
        """, (processing_date, shift_info['name'], shift_info['name'], processing_date), as_dict=True)
        
        return employees
        
    except Exception as e:
        frappe.log_error(f"Error getting employees for shift processing: {str(e)}", "Smart Auto Custom Attendance")
        return []


def process_employee_custom_attendance(employee_info, shift_info):
    """Process Custom Attendance cho employee với shift info"""
    try:
        processing_date = shift_info['processing_date']
        
        # Create Custom Attendance
        custom_attendance = frappe.new_doc("Custom Attendance")
        custom_attendance.employee = employee_info['employee']
        custom_attendance.employee_name = employee_info['employee_name']
        custom_attendance.attendance_date = processing_date
        custom_attendance.company = employee_info['company']
        custom_attendance.shift = shift_info['name']
        custom_attendance.auto_sync_enabled = 1
        custom_attendance.status = "Absent"  # Will be updated after sync
        
        # Skip validations during auto creation
        custom_attendance.flags.ignore_validate = True
        custom_attendance.flags.ignore_auto_sync = True
        custom_attendance.flags.ignore_duplicate_check = True
        
        # Save
        custom_attendance.save(ignore_permissions=True)
        
        # Auto sync from checkins
        sync_result = sync_attendance_from_checkin_data(custom_attendance)
        
        frappe.logger().info(f"Auto-created Custom Attendance {custom_attendance.name} for {employee_info['employee']} (Shift: {shift_info['name']}, Date: {processing_date}): {sync_result}")
        
        return True
        
    except Exception as e:
        frappe.log_error(f"Error processing employee custom attendance: {str(e)}", "Smart Auto Custom Attendance")
        return False


# Shift change handlers
def on_shift_update(doc, method):
    """Trigger khi Shift Type được update"""
    try:
        # Nếu shift times thay đổi, có thể cần re-calculate working hours
        if doc.has_value_changed("start_time") or doc.has_value_changed("end_time"):
            # Get Custom Attendance records sử dụng shift này từ 7 ngày qua
            recent_date = getdate() - timedelta(days=7)
            
            affected_records = frappe.get_all("Custom Attendance",
                filters={
                    "shift": doc.name,
                    "attendance_date": [">=", recent_date],
                    "docstatus": 0
                },
                fields=["name"]
            )
            
            # Re-calculate working hours cho affected records
            for record in affected_records:
                try:
                    ca_doc = frappe.get_doc("Custom Attendance", record.name)
                    if ca_doc.check_in and ca_doc.check_out:
                        ca_doc.calculate_working_hours()
                        ca_doc.save(ignore_permissions=True)
                except Exception as e:
                    frappe.log_error(f"Error recalculating hours for {record.name}: {str(e)}", "Shift Update Impact")
                    continue
                    
            if affected_records:
                frappe.logger().info(f"Recalculated working hours for {len(affected_records)} Custom Attendance records after shift update")
                
    except Exception as e:
        frappe.log_error(f"Error in on_shift_update: {str(e)}", "Custom Attendance Shift Update")


# Scheduled job wrappers
def daily_custom_attendance_sync():
    """Daily job để sync tất cả Custom Attendance records chưa được sync"""
    try:
        yesterday = getdate() - timedelta(days=1)
        
        # Get all Custom Attendance records từ hôm qua cần sync
        records_to_sync = frappe.get_all("Custom Attendance",
            filters={
                "attendance_date": yesterday,
                "auto_sync_enabled": 1,
                "docstatus": 0,
                # Chỉ sync những record chưa có data hoặc chưa sync gần đây
                "last_sync_time": ["is", "not set"]
            },
            fields=["name", "employee", "attendance_date"]
        )
        
        synced_count = 0
        failed_count = 0
        
        for record in records_to_sync:
            try:
                doc = frappe.get_doc("Custom Attendance", record.name)
                result = sync_attendance_from_checkin_data(doc)
                
                if "successfully" in str(result).lower():
                    synced_count += 1
                else:
                    failed_count += 1
                    
                frappe.db.commit()
                
            except Exception as e:
                failed_count += 1
                frappe.log_error(f"Daily sync failed for {record.name}: {str(e)}", "Daily Custom Attendance Sync")
                continue
        
        frappe.logger().info(f"Daily Custom Attendance Sync completed: {synced_count} synced, {failed_count} failed")
        
    except Exception as e:
        frappe.log_error(f"Error in daily_custom_attendance_sync: {str(e)}", "Daily Custom Attendance Sync")