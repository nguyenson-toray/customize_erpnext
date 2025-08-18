# Copyright (c) 2025, IT Team - TIQN and contributors
# For license information, please see license.txt

"""
Custom Attendance Modules

This package contains all the refactored modules for Custom Attendance functionality:
- overtime_calculator: Overtime calculation and management
- attendance_sync: Synchronization with Employee Checkin records  
- bulk_operations: Bulk processing and batch operations
- scheduler_jobs: Automated scheduling and background jobs
- attendance_utils: Helper utilities and common functions
- api_methods: API endpoints for client-server communication
- validators: Validation logic and data integrity checks
"""

# Core functions from overtime calculator
from .overtime_calculator import (
    get_approved_overtime_requests_for_doc,
    calculate_working_hours_with_overtime_for_doc,
    get_overtime_details_for_doc,
    calculate_actual_overtime_for_request_doc
)

# Sync functionality
from .attendance_sync import (
    sync_attendance_from_checkin_data,
    auto_sync_attendance_from_checkin,
    batch_sync_attendance_records,
    extract_in_out_times
)

# Bulk operations
from .bulk_operations import (
    bulk_recalculate_overtime,
    bulk_process_from_shift_date,
    bulk_sync_custom_attendance,
    bulk_daily_completion_range,
    migrate_existing_attendance_records
)

# Scheduler jobs
from .scheduler_jobs import (
    daily_attendance_completion,
    auto_submit_custom_attendance,
    auto_daily_attendance_completion,
    smart_auto_update_custom_attendance,
    on_shift_update
)

# Utilities
from .attendance_utils import (
    timedelta_to_time_helper,
    parse_time_field_helper,
    get_active_employees_for_date,
    validate_time_range,
    get_shift_type_info
)

# Validators
from .validators import (
    validate_duplicate_attendance,
    validate_employee_active_on_date,
    validate_before_submit,
    validate_comprehensive
)

# Version info
__version__ = "2.0.0"
__author__ = "IT Team - TIQN"

# Public API - functions that should be available for external use
__all__ = [
    # Overtime functions
    "get_approved_overtime_requests_for_doc",
    "calculate_working_hours_with_overtime_for_doc",
    "get_overtime_details_for_doc",
    "calculate_actual_overtime_for_request_doc",
    
    # Sync functions
    "sync_attendance_from_checkin_data",
    "auto_sync_attendance_from_checkin",
    "batch_sync_attendance_records",
    "extract_in_out_times",
    
    # Bulk operations
    "bulk_recalculate_overtime",
    "bulk_process_from_shift_date", 
    "bulk_sync_custom_attendance",
    "bulk_daily_completion_range",
    "migrate_existing_attendance_records",
    
    # Scheduler jobs
    "daily_attendance_completion",
    "auto_submit_custom_attendance",
    "auto_daily_attendance_completion",
    "smart_auto_update_custom_attendance",
    "on_shift_update",
    
    # Utilities
    "timedelta_to_time_helper",
    "parse_time_field_helper",
    "get_active_employees_for_date",
    "validate_time_range",
    "get_shift_type_info",
    
    # Validators
    "validate_duplicate_attendance",
    "validate_employee_active_on_date",
    "validate_before_submit",
    "validate_comprehensive"
]

def get_module_info():
    """Get information about the modules"""
    return {
        "version": __version__,
        "author": __author__,
        "modules": [
            "overtime_calculator",
            "attendance_sync", 
            "bulk_operations",
            "scheduler_jobs",
            "attendance_utils",
            "api_methods",
            "validators"
        ],
        "total_functions": len(__all__)
    }

def check_module_integrity():
    """Check if all required modules are available"""
    import importlib
    
    modules = [
        "overtime_calculator",
        "attendance_sync",
        "bulk_operations", 
        "scheduler_jobs",
        "attendance_utils",
        "api_methods",
        "validators"
    ]
    
    missing_modules = []
    for module in modules:
        try:
            importlib.import_module(f".{module}", package=__name__)
        except ImportError:
            missing_modules.append(module)
    
    return {
        "all_modules_available": len(missing_modules) == 0,
        "missing_modules": missing_modules,
        "available_modules": [m for m in modules if m not in missing_modules]
    }