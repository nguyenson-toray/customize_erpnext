"""
API endpoints for biometric log viewer
"""

import frappe
import os


@frappe.whitelist()
def get_log_files():
    """Get list of available log files"""
    try:
        # Path to biometric sync tool logs
        log_dir = '/home/frappe/frappe-bench/apps/biometric-attendance-sync-tool/logs'

        if not os.path.exists(log_dir):
            return {
                'status': 'success',
                'files': []
            }

        # Get all .log files
        files = []
        for file in os.listdir(log_dir):
            if file.endswith('.log'):
                files.append(file)

        # Sort by modification time, newest first
        files.sort(key=lambda x: os.path.getmtime(os.path.join(log_dir, x)), reverse=True)

        return {
            'status': 'success',
            'files': files
        }

    except Exception as e:
        frappe.log_error(f"Error getting log files: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }


@frappe.whitelist()
def get_log_content(log_file):
    """Get content of a specific log file"""
    try:
        # Validate file name (security check)
        if not log_file or '..' in log_file or '/' in log_file or '\\' in log_file:
            return {
                'status': 'error',
                'message': 'Invalid file name'
            }

        if not log_file.endswith('.log'):
            return {
                'status': 'error',
                'message': 'Only .log files are allowed'
            }

        # Path to biometric sync tool logs
        log_dir = '/home/frappe/frappe-bench/apps/biometric-attendance-sync-tool/logs'
        log_path = os.path.join(log_dir, log_file)

        # Security check: ensure file is within log directory
        if not os.path.abspath(log_path).startswith(log_dir):
            return {
                'status': 'error',
                'message': 'Access denied'
            }

        if not os.path.exists(log_path):
            return {
                'status': 'error',
                'message': 'Log file not found'
            }

        # Read file content
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        return {
            'status': 'success',
            'content': content,
            'file': log_file
        }

    except Exception as e:
        frappe.log_error(f"Error reading log file {log_file}: {str(e)}")
        return {
            'status': 'error',
            'message': str(e)
        }
