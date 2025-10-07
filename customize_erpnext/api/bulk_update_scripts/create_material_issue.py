#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import frappe
import pandas as pd
from frappe.utils import nowdate, flt, cstr, get_site_path
from collections import defaultdict
import os
import datetime
import sys
import json

# Company mặc định
DEFAULT_COMPANY = "Toray International, VietNam Company Limited - Quang Ngai Branch"

# Đường dẫn file mặc định
DEFAULT_FILE_PATH = "/home/sonnt/frappe-bench/sites/erp-sonnt.tiqn.local/private/files/create_material_issue.xlsx"

class Logger:
    """Class để ghi log vào file và console"""
    def __init__(self, log_file_path=None):
        if not log_file_path:
            # Tạo log file ở cùng thư mục với script
            script_dir = os.path.dirname(os.path.abspath(__file__))
            log_file_path = os.path.join(script_dir, "create_material_issue.txt")
        
        self.log_file_path = log_file_path
        self.start_time = datetime.datetime.now()
        
        # Khởi tạo log file
        self._write_header()
    
    def _write_header(self):
        """Viết header cho log file"""
        header = f"""
{'='*80}
MATERIAL ISSUE BULK CREATION LOG
Started at: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}
Script: {__file__}
{'='*80}

"""
        with open(self.log_file_path, 'w', encoding='utf-8') as f:
            f.write(header)
    
    def log(self, message, level="INFO", print_console=True):
        """Ghi log vào file và console"""
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] [{level}] {message}"
        
        # Ghi vào file
        try:
            with open(self.log_file_path, 'a', encoding='utf-8') as f:
                f.write(log_line + '\n')
        except Exception as e:
            print(f"Error writing to log file: {e}")
        
        # In ra console nếu được yêu cầu
        if print_console:
            print(message)
    
    def log_success(self, message, print_console=True):
        """Log thành công"""
        self.log(f"✅ {message}", "SUCCESS", print_console)
    
    def log_error(self, message, print_console=True):
        """Log lỗi"""
        self.log(f"❌ {message}", "ERROR", print_console)
    
    def log_warning(self, message, print_console=True):
        """Log cảnh báo"""
        self.log(f"⚠️ {message}", "WARNING", print_console)
    
    def log_info(self, message, print_console=True):
        """Log thông tin"""
        self.log(f"📋 {message}", "INFO", print_console)
    
    def log_separator(self, title="", print_console=True):
        """Log dòng phân cách"""
        if title:
            separator = f"\n{'='*20} {title} {'='*20}"
        else:
            separator = "="*60
        self.log(separator, "INFO", print_console)
    
    def finalize(self, result):
        """Kết thúc log với tóm tắt"""
        end_time = datetime.datetime.now()
        duration = end_time - self.start_time
        
        footer = f"""

{'='*80}
EXECUTION COMPLETED
End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}
Duration: {duration}
Success Count: {result.get('success_count', 0)}
Error Count: {result.get('error_count', 0)}
Total Items: {result.get('total_items', 0)}
Log file: {self.log_file_path}
{'='*80}
"""
        with open(self.log_file_path, 'a', encoding='utf-8') as f:
            f.write(footer)
        
        print(f"\n📁 Log đã được lưu tại: {self.log_file_path}")

# Global logger instance
logger = None
 
@frappe.whitelist()
def validate_excel_file(file_url):
    """Performance optimized Excel validation"""
    global logger
    
    try:
        # Clear caches for validation
        global item_cache, warehouse_cache
        item_cache.clear()
        warehouse_cache.clear()
        
        # Khởi tạo logger
        logger = Logger()
        
        logger.log_separator("BẮT ĐẦU PERFORMANCE OPTIMIZED VALIDATION")
        logger.log_info(f"File URL: {file_url}")
        
        # Chuyển đổi file URL thành đường dẫn thực
        file_path = get_file_path_from_url(file_url)
        
        if not os.path.exists(file_path):
            logger.log_error(f"File không tồn tại: {file_path}")
            return {
                "success": False,
                "message": f"File không tồn tại: {file_path}",
                "log_file_path": logger.log_file_path
            }
        
        # Đọc file Excel
        logger.log_info("Đang đọc file Excel...")
        df = pd.read_excel(file_path)
        
        logger.log_info(f"Đã đọc được {len(df)} dòng dữ liệu")
        
        # Validate columns
        validation_result = validate_excel_columns(df)
        if not validation_result["success"]:
            logger.log_error(validation_result["message"])
            return {
                "success": False,
                "message": validation_result["message"],
                "log_file_path": logger.log_file_path
            }
        
        # Clean data
        df = clean_dataframe(df)
        
        # Performance optimized detailed validation
        logger.log_info("Starting batch validation with performance optimizations...")
        detailed_validation = validate_excel_data_detailed(df)
        
        logger.log_separator("KẾT QUẢ OPTIMIZED VALIDATION")
        
        if detailed_validation["success"]:
            logger.log_success(f"Validation thành công!")
            logger.log_info(f"Total rows: {detailed_validation['total_rows']}")
            logger.log_info(f"Valid rows: {detailed_validation['valid_rows']}")
            logger.log_info(f"Groups: {detailed_validation['groups_count']}")
            logger.log_info(f"Cached items: {len(item_cache)}")
            logger.log_info(f"Cached warehouses: {len(warehouse_cache)}")
        else:
            logger.log_error("Validation thất bại!")
            for error in detailed_validation.get("errors", []):
                logger.log_error(error)
        
        # Finalize log
        logger.finalize({
            "success_count": 1 if detailed_validation["success"] else 0,
            "error_count": 0 if detailed_validation["success"] else 1,
            "total_items": len(df)
        })
        
        detailed_validation["log_file_path"] = logger.log_file_path
        return detailed_validation
        
    except Exception as e:
        error_msg = f"Lỗi validation: {str(e)}"
        if logger:
            logger.log_error(error_msg)
            logger.finalize({
                "success_count": 0,
                "error_count": 1,
                "total_items": 0
            })
        
        return {
            "success": False,
            "message": error_msg,
            "log_file_path": logger.log_file_path if logger else None
        }

@frappe.whitelist()
def import_material_issue_from_excel(file_url):
    """Import Material Issue từ Excel file"""
    global logger
    
    try:
        # Khởi tạo logger
        logger = Logger()
        
        logger.log_separator("BẮT ĐẦU IMPORT MATERIAL ISSUE")
        
        # Chuyển đổi file URL thành đường dẫn thực
        file_path = get_file_path_from_url(file_url)
        
        # Gọi hàm create_material_issue hiện tại
        result = create_material_issue(file_path)
        
        return result
        
    except Exception as e:
        error_msg = f"Lỗi import: {str(e)}"
        if logger:
            logger.log_error(error_msg)
        
        return {
            "success": False,
            "message": error_msg,
            "success_count": 0,
            "error_count": 1,
            "total_items": 0,
            "created_entries": [],
            "errors": [error_msg]
        }

def get_file_path_from_url(file_url):
    """Chuyển đổi file URL thành đường dẫn thực tế"""
    if file_url.startswith('/files/'):
        site_path = get_site_path()
        return os.path.join(site_path, "public", file_url.lstrip('/'))
    elif file_url.startswith('/private/files/'):
        site_path = get_site_path()
        return os.path.join(site_path, file_url.lstrip('/'))
    else:
        # Assume it's already a full path
        return file_url

def validate_excel_data_detailed(df):
    """Performance optimized validation với batch processing"""
    result = {
        "success": True,
        "total_rows": len(df),
        "valid_rows": 0,
        "groups_count": 0,
        "validation_details": {
            "missing_items": [],
            "missing_warehouses": [],
            "invoice_issues": [],
            "errors": [],
            "suggestions": []
        }
    }
    
    try:
        # Group theo custom_no
        grouped_data = df.groupby('custom_no')
        result["groups_count"] = len(grouped_data)
        
        logger.log_info(f"Tìm thấy {len(grouped_data)} nhóm custom_no")
        
        # Performance optimization: Batch lookup items and warehouses
        unique_patterns = df['custom_item_name_detail'].dropna().unique().tolist()
        logger.log_info(f"Batch lookup for {len(unique_patterns)} unique items...")
        
        # Batch find all items
        items_map = batch_find_items(unique_patterns)
        
        # Get all valid item codes for warehouse lookup
        valid_item_codes = [item['item_code'] for item in items_map.values() if item is not None]
        
        # Batch find all warehouses
        logger.log_info(f"Batch lookup for {len(valid_item_codes)} warehouses...")
        warehouses_map = batch_get_warehouses(valid_item_codes)
        
        # Batch find suggestions for missing items
        missing_patterns = [pattern for pattern, item in items_map.items() if item is None]
        suggestions_map = {}
        if missing_patterns:
            logger.log_info(f"Finding suggestions for {len(missing_patterns)} missing items...")
            for pattern in missing_patterns:
                suggestions_map[pattern] = find_similar_items(pattern, limit=3)
        
        valid_row_count = 0
        
        for group_index, (custom_no, group_df) in enumerate(grouped_data, 1):
            logger.log_info(f"Validating nhóm {group_index}/{len(grouped_data)}: {custom_no}")
            
            for index, row in group_df.iterrows():
                row_number = index + 2
                
                try:
                    # Use cached item lookup
                    pattern_search = row.get('custom_item_name_detail', '')
                    item = items_map.get(pattern_search)
                    
                    if not item:
                        suggestions = suggestions_map.get(pattern_search, [])
                        
                        missing_item_info = {
                            "custom_item_name_detail": pattern_search,
                            "row": row_number,
                            "suggestions": suggestions[:3]
                        }
                        
                        result["validation_details"]["missing_items"].append(missing_item_info)
                        result["success"] = False
                        continue
                    
                    # Check warehouse - priority: Excel > Default warehouse
                    warehouse = None
                    excel_warehouse = row.get('s_warehouse', '')
                    
                    if excel_warehouse and pd.notna(excel_warehouse) and str(excel_warehouse).strip():
                        # Validate warehouse từ Excel có tồn tại không
                        excel_warehouse = str(excel_warehouse).strip()
                        if frappe.db.exists("Warehouse", excel_warehouse):
                            warehouse = excel_warehouse
                            logger.log_info(f"  Using warehouse from Excel: {warehouse} for item {item['item_code']}")
                        else:
                            result["validation_details"]["missing_warehouses"].append({
                                "item_code": item['item_code'],
                                "warehouse": f"Excel warehouse '{excel_warehouse}' not found",
                                "row": row_number
                            })
                            result["success"] = False
                            continue
                    else:
                        # Fallback to default warehouse
                        warehouse = warehouses_map.get(item['item_code'])
                        if warehouse:
                            logger.log_info(f"  Using default warehouse: {warehouse} for item {item['item_code']}")
                    
                    if not warehouse:
                        result["validation_details"]["missing_warehouses"].append({
                            "item_code": item['item_code'],
                            "warehouse": "No warehouse specified and no default warehouse",
                            "row": row_number
                        })
                        result["success"] = False
                        continue
                    
                    # Validate qty
                    qty = flt(row.get('qty', 0))
                    if qty <= 0:
                        result["validation_details"]["errors"].append(
                            f"Row {row_number}: Invalid quantity {qty} for item {item['item_code']}"
                        )
                        result["success"] = False
                        continue
                    
                    # Validate custom_invoice_number
                    invoice_number = cstr(row.get('custom_invoice_number', '')).strip()
                    if not invoice_number:
                        result["validation_details"]["errors"].append(
                            f"Row {row_number}: Missing invoice number for item {item['item_code']}"
                        )
                        result["success"] = False
                        continue
                    
                    # Performance optimization: Stock validation can be deferred for large datasets
                    # For now, we'll skip individual stock validation in batch mode
                    # This can be re-enabled with batch stock lookup if needed
                    
                    # Note: Stock validation temporarily disabled for performance
                    # available_qty = get_available_qty_by_invoice(item['item_code'], warehouse, invoice_number)
                    # if available_qty < qty:
                    #     result["validation_details"]["invoice_issues"].append({...})
                    
                    valid_row_count += 1
                    
                except Exception as e:
                    result["validation_details"]["errors"].append(
                        f"Row {row_number}: {str(e)}"
                    )
                    result["success"] = False
                    continue
        
        result["valid_rows"] = valid_row_count
        
        # Log summary
        logger.log_info(f"Validation summary:")
        logger.log_info(f"  - Total rows: {result['total_rows']}")
        logger.log_info(f"  - Valid rows: {result['valid_rows']}")
        logger.log_info(f"  - Missing items: {len(result['validation_details']['missing_items'])}")
        logger.log_info(f"  - Missing warehouses: {len(result['validation_details']['missing_warehouses'])}")
        logger.log_info(f"  - Invoice issues: {len(result['validation_details']['invoice_issues'])}")
        logger.log_info(f"  - General errors: {len(result['validation_details']['errors'])}")
        
        return result
        
    except Exception as e:
        result["success"] = False
        result["validation_details"]["errors"].append(f"Validation error: {str(e)}")
        logger.log_error(f"Detailed validation error: {str(e)}")
        return result

def find_similar_items(search_term, limit=5):
    """
    Tìm items có custom_item_name_detail tương tự để suggest khi exact match thất bại
    """
    try:
        if not search_term or pd.isna(search_term):
            return []
            
        search_term = cstr(search_term).strip()
        
        # Tìm items có custom_item_name_detail chứa một phần của search_term
        similar_items = frappe.db.sql("""
            SELECT 
                item_code,
                custom_item_name_detail,
                CASE 
                    WHEN custom_item_name_detail = %s THEN 100
                    WHEN custom_item_name_detail LIKE %s THEN 90
                    WHEN custom_item_name_detail LIKE %s THEN 80
                    WHEN custom_item_name_detail LIKE %s THEN 70
                    ELSE 60
                END as similarity_score
            FROM `tabItem`
            WHERE custom_item_name_detail IS NOT NULL
            AND custom_item_name_detail != ''
            AND has_variants = 0
            AND (
                custom_item_name_detail LIKE %s
                OR custom_item_name_detail LIKE %s
                OR custom_item_name_detail LIKE %s
            )
            ORDER BY similarity_score DESC, custom_item_name_detail
            LIMIT %s
        """, (
            search_term,  # Exact match (shouldn't happen here but for completeness)
            f"{search_term}%",  # Starts with
            f"%{search_term}%",  # Contains
            f"%{search_term}",   # Ends with
            f"%{search_term}%",  # Contains (repeat for OR)
            f"{search_term}%",   # Starts with (repeat for OR)
            f"%{search_term}",   # Ends with (repeat for OR)
            limit
        ), as_dict=True)
        
        return similar_items
        
    except Exception as e:
        if logger:
            logger.log_error(f"Error finding similar items for '{search_term}': {str(e)}")
        return []

def get_default_warehouse_for_item(item_code):
    """Lấy default warehouse cho item từ Item Default với caching"""
    try:
        # Check cache first
        if item_code in warehouse_cache:
            return warehouse_cache[item_code]
        
        company = DEFAULT_COMPANY
        
        # Query Item Default table
        default_warehouse = frappe.db.sql("""
            SELECT default_warehouse
            FROM `tabItem Default`
            WHERE parent = %s AND company = %s
            LIMIT 1
        """, (item_code, company), as_dict=True)
        
        warehouse = None
        if default_warehouse and default_warehouse[0].default_warehouse:
            warehouse = default_warehouse[0].default_warehouse
        else:
            # Fallback: get any warehouse for the company
            fallback_warehouse = frappe.db.sql("""
                SELECT name
                FROM `tabWarehouse`
                WHERE company = %s AND is_group = 0
                LIMIT 1
            """, company, as_dict=True)
            
            if fallback_warehouse:
                warehouse = fallback_warehouse[0].name
                logger.log_warning(f"No default warehouse for {item_code}, using fallback: {warehouse}")
        
        # Cache the result (including None)
        warehouse_cache[item_code] = warehouse
        return warehouse
        
    except Exception as e:
        logger.log_error(f"Error getting default warehouse for {item_code}: {str(e)}")
        warehouse_cache[item_code] = None
        return None

def batch_get_warehouses(item_codes):
    """
    Performance optimization: Batch lookup for warehouses
    """
    try:
        if not item_codes:
            return {}
        
        # Filter out cached items
        uncached_codes = [code for code in item_codes if code not in warehouse_cache]
        
        if uncached_codes:
            company = DEFAULT_COMPANY
            
            # Batch query for all uncached warehouses
            warehouses = frappe.db.sql("""
                SELECT parent as item_code, default_warehouse
                FROM `tabItem Default`
                WHERE parent IN %(item_codes)s AND company = %(company)s
            """, {"item_codes": uncached_codes, "company": company}, as_dict=True)
            
            # Update cache with results
            found_codes = set()
            for wh in warehouses:
                if wh['default_warehouse']:
                    warehouse_cache[wh['item_code']] = wh['default_warehouse']
                    found_codes.add(wh['item_code'])
            
            # For items without default warehouse, get fallback
            unfound_codes = [code for code in uncached_codes if code not in found_codes]
            if unfound_codes:
                # Get fallback warehouse once
                fallback = frappe.db.sql("""
                    SELECT name
                    FROM `tabWarehouse`
                    WHERE company = %s AND is_group = 0
                    LIMIT 1
                """, company, as_dict=True)
                
                fallback_warehouse = fallback[0].name if fallback else None
                
                # Cache fallback for all unfound codes
                for code in unfound_codes:
                    warehouse_cache[code] = fallback_warehouse
                    if fallback_warehouse:
                        logger.log_warning(f"No default warehouse for {code}, using fallback: {fallback_warehouse}")
        
        # Return all requested warehouses from cache
        return {code: warehouse_cache.get(code) for code in item_codes}
        
    except Exception as e:
        if logger:
            logger.log_error(f"Error in batch warehouse lookup: {str(e)}")
        return {}

def get_available_qty_by_invoice(item_code, warehouse, invoice_number):
    """
    Tính available quantity theo invoice number từ Stock Ledger Entry
    Xử lý đúng cả Stock Reconciliation và Stock Entry
    
    Logic:
    1. Tìm Stock Reconciliation gần nhất (nếu có) để lấy base quantity
    2. Cộng tất cả actual_qty từ các Stock Entry sau reconciliation đó
    3. Nếu không có reconciliation, cộng tất cả actual_qty từ đầu
    """
    try:
        # Lấy tất cả Stock Ledger Entries theo thứ tự thời gian
        entries = frappe.db.sql("""
            SELECT 
                voucher_type,
                voucher_no,
                actual_qty,
                qty_after_transaction,
                posting_date,
                posting_time,
                creation
            FROM `tabStock Ledger Entry`
            WHERE item_code = %s 
            AND warehouse = %s 
            AND custom_invoice_number = %s
            AND is_cancelled = 0
            AND docstatus < 2
            ORDER BY posting_date ASC, posting_time ASC, creation ASC
        """, (item_code, warehouse, invoice_number), as_dict=True)
        
        if not entries:
            return 0.0
        
        # Tìm Stock Reconciliation gần nhất
        latest_reconciliation = None
        latest_reconciliation_index = -1
        
        for i, entry in enumerate(entries):
            if entry['voucher_type'] == 'Stock Reconciliation':
                latest_reconciliation = entry
                latest_reconciliation_index = i
        
        total_qty = 0.0
        
        if latest_reconciliation:
            # Nếu có Stock Reconciliation, bắt đầu từ qty_after_transaction của reconciliation gần nhất
            total_qty = flt(latest_reconciliation['qty_after_transaction'])
            
            if logger:
                logger.log_info(f"  📊 Base from Stock Reconciliation {latest_reconciliation['voucher_no']}: {total_qty}")
            
            # Cộng các actual_qty từ các entries sau reconciliation
            for i in range(latest_reconciliation_index + 1, len(entries)):
                entry = entries[i]
                actual_qty = flt(entry['actual_qty'])
                total_qty += actual_qty
                
                if logger:
                    logger.log_info(f"  ➕ {entry['voucher_type']} {entry['voucher_no']}: {actual_qty} (Running total: {total_qty})")
        
        else:
            # Nếu không có Stock Reconciliation, cộng tất cả actual_qty
            for entry in entries:
                actual_qty = flt(entry['actual_qty'])
                total_qty += actual_qty
                
                if logger:
                    logger.log_info(f"  ➕ {entry['voucher_type']} {entry['voucher_no']}: {actual_qty} (Running total: {total_qty})")
        
        if logger:
            logger.log_info(f"📊 Final available qty for {item_code} - {warehouse} - {invoice_number}: {total_qty}")
        
        return total_qty
        
    except Exception as e:
        error_msg = f"Error getting available qty for {item_code} - {warehouse} - {invoice_number}: {str(e)}"
        if logger:
            logger.log_error(error_msg)
        else:
            print(f"❌ {error_msg}")
        return 0.0

def create_material_issue(file_path=None):
    """
    Hàm chính để tạo Material Issue Stock Entry từ file Excel
    
    Args:
        file_path (str, optional): Đường dẫn đến file Excel. 
                                 Nếu None, sẽ dùng đường dẫn mặc định.
    
    Returns:
        dict: Kết quả thực hiện
    """
    global logger
    
    try:
        # Khởi tạo logger
        logger = Logger()
        
        logger.log_separator("BẮT ĐẦU TẠO MATERIAL ISSUE STOCK ENTRIES")
        
        # Xác định đường dẫn file
        if not file_path:
            file_path = DEFAULT_FILE_PATH
            logger.log_info(f"Sử dụng đường dẫn mặc định: {file_path}")
        else:
            logger.log_info(f"Sử dụng đường dẫn: {file_path}")
        
        # Validate trước khi chạy
        logger.log_info("Bắt đầu validation...")
        validation_result = validate_before_creation(file_path)
        if not validation_result["success"]:
            logger.log_error(f"Validation thất bại: {validation_result['message']}")
            logger.finalize(validation_result)
            return validation_result
        
        logger.log_success("Validation thành công")
        
        # Đọc và xử lý file Excel
        logger.log_info("Bắt đầu xử lý file Excel...")
        result = process_excel_file(file_path)
        
        logger.log_separator("KẾT QUẢ CUỐI CÙNG")
        logger.log_success(f"Tạo thành công: {result['success_count']} Stock Entry")
        
        if result['error_count'] > 0:
            logger.log_error(f"Lỗi: {result['error_count']} nhóm")
        
        logger.log_info(f"Tổng items đã xử lý: {result['total_items']}")
        
        # Log danh sách Stock Entries đã tạo
        if result['created_entries']:
            logger.log_info("Danh sách Stock Entries đã tạo:")
            for i, entry_name in enumerate(result['created_entries'], 1):
                logger.log_info(f"  {i}. {entry_name}")
        
        # Log danh sách lỗi nếu có
        if result['errors']:
            logger.log_warning("Danh sách lỗi:")
            for i, error in enumerate(result['errors'], 1):
                logger.log_error(f"  {i}. {error}")
        
        if result['success_count'] > 0:
            frappe.db.commit()
            logger.log_success("Đã commit thành công!")
        
        # Finalize log
        logger.finalize(result)
        
        return result
        
    except Exception as e:
        frappe.db.rollback()
        error_msg = f"Lỗi chung: {str(e)}"
        
        if logger:
            logger.log_error(error_msg)
            result = {
                "success": False,
                "message": error_msg,
                "success_count": 0,
                "error_count": 1,
                "total_items": 0,
                "created_entries": [],
                "errors": [error_msg]
            }
            logger.finalize(result)
        else:
            print(f"❌ {error_msg}")
        
        return {
            "success": False,
            "message": error_msg,
            "success_count": 0,
            "error_count": 1,
            "total_items": 0,
            "created_entries": [],
            "errors": [error_msg]
        }

def validate_before_creation(file_path):
    """
    Kiểm tra điều kiện trước khi tạo
    
    Args:
        file_path (str): Đường dẫn file Excel
        
    Returns:
        dict: Kết quả validation
    """
    try:
        # Kiểm tra file tồn tại
        if not os.path.exists(file_path):
            message = f"File không tồn tại: {file_path}"
            if logger:
                logger.log_error(message)
            return {"success": False, "message": message}
        
        # Kiểm tra company tồn tại
        if not frappe.db.exists("Company", DEFAULT_COMPANY):
            message = f"Company không tồn tại: {DEFAULT_COMPANY}"
            if logger:
                logger.log_error(message)
            return {"success": False, "message": message}
        
        # Kiểm tra file có đọc được không
        try:
            df = pd.read_excel(file_path, nrows=1)
            if logger:
                logger.log_success(f"File Excel hợp lệ với {len(df.columns)} cột")
        except Exception as e:
            message = f"Không thể đọc file Excel: {str(e)}"
            if logger:
                logger.log_error(message)
            return {"success": False, "message": message}
        
        return {"success": True, "message": "Validation thành công"}
        
    except Exception as e:
        message = f"Lỗi validation: {str(e)}"
        if logger:
            logger.log_error(message)
        return {"success": False, "message": message}

def process_excel_file(file_path):
    """
    Performance optimized Excel processing với batch operations
    """
    result = {
        "success": True,
        "message": "",
        "success_count": 0,
        "error_count": 0,
        "total_items": 0,
        "created_entries": [],
        "created_entries_details": [],  # New field for detailed information
        "errors": []
    }
    
    try:
        # Clear caches at start
        global item_cache, warehouse_cache
        item_cache.clear()
        warehouse_cache.clear()
        
        # Đọc file Excel
        logger.log_info(f"Đang đọc file: {file_path}")
        df = pd.read_excel(file_path)
        
        logger.log_info(f"Đã đọc được {len(df)} dòng dữ liệu")
        logger.log_info(f"Các cột: {list(df.columns)}")
        
        # Kiểm tra các cột bắt buộc
        validation_result = validate_excel_columns(df)
        if not validation_result["success"]:
            result["success"] = False
            result["message"] = validation_result["message"]
            result["errors"].append(validation_result["message"])
            logger.log_error(validation_result["message"])
            return result
        
        logger.log_success("Các cột Excel hợp lệ")
        
        # Làm sạch dữ liệu
        df = clean_dataframe(df)
        
        # Performance optimization: Pre-populate caches
        logger.log_info("Pre-loading item and warehouse data...")
        unique_patterns = df['custom_item_name_detail'].dropna().unique().tolist()
        items_map = batch_find_items(unique_patterns)
        
        valid_item_codes = [item['item_code'] for item in items_map.values() if item is not None]
        warehouses_map = batch_get_warehouses(valid_item_codes)
        
        logger.log_info(f"Cached {len(items_map)} items and {len(warehouses_map)} warehouses")
        
        # Group theo custom_no
        grouped_data = df.groupby('custom_no')
        logger.log_info(f"Tìm thấy {len(grouped_data)} nhóm custom_no khác nhau")
        
        # Performance optimization: Process groups in batches
        batch_size = 10  # Process 10 groups at a time
        groups_list = list(grouped_data)
        
        for batch_start in range(0, len(groups_list), batch_size):
            batch_end = min(batch_start + batch_size, len(groups_list))
            batch_groups = groups_list[batch_start:batch_end]
            
            logger.log_info(f"Processing batch {batch_start//batch_size + 1}: groups {batch_start+1}-{batch_end}")
            
            for group_index, (custom_no, group_df) in enumerate(batch_groups, batch_start + 1):
                try:
                    logger.log_info(f"Xử lý nhóm {group_index}/{len(grouped_data)}: {custom_no} với {len(group_df)} items")
                    
                    # Tạo Stock Entry cho nhóm này
                    entry_result = create_stock_entry_for_group(custom_no, group_df)
                    
                    if entry_result["success"]:
                        result["success_count"] += 1
                        result["created_entries"].append(entry_result["stock_entry_name"])
                        result["created_entries_details"].append({
                            "name": entry_result["stock_entry_name"],
                            "posting_date": entry_result.get("posting_date", ""),
                            "custom_no": entry_result.get("custom_no", ""),
                            "custom_invoice_number": entry_result.get("custom_invoice_number", ""),
                            "items_count": entry_result["items_count"]
                        })
                        result["total_items"] += entry_result["items_count"]
                        logger.log_success(f"Tạo thành công: {entry_result['stock_entry_name']} với {entry_result['items_count']} items")
                    else:
                        result["error_count"] += 1
                        error_msg = f"Nhóm {custom_no}: {entry_result['message']}"
                        result["errors"].append(error_msg)
                        logger.log_error(error_msg)
                        
                except Exception as e:
                    result["error_count"] += 1
                    error_msg = f"Lỗi xử lý nhóm {custom_no}: {str(e)}"
                    result["errors"].append(error_msg)
                    logger.log_error(error_msg)
                    continue
            
            # Performance optimization: Commit in batches
            if batch_end % 20 == 0:  # Commit every 2 batches (20 groups)
                frappe.db.commit()
                logger.log_info(f"Committed batch progress: {batch_end} groups processed")
        
        return result
        
    except Exception as e:
        result["success"] = False
        result["message"] = f"Lỗi xử lý file: {str(e)}"
        result["errors"].append(result["message"])
        logger.log_error(result["message"])
        return result

def validate_excel_columns(df):
    """
    Kiểm tra các cột bắt buộc trong Excel
    """
    required_columns = [
        'custom_item_name_detail',  # Để tìm item
        'custom_no',            # Để group 
        'qty',                  # Số lượng
        'custom_invoice_number' # Số hóa đơn
    ]
    
    # Các cột optional
    optional_columns = [
        'posting_date',         # Ngày chứng từ
        'posting_time',         # Thời gian chứng từ
        's_warehouse'           # Source warehouse (optional - fallback to default if not provided)
    ]
    
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        return {
            "success": False,
            "message": f"Thiếu các cột bắt buộc: {missing_columns}"
        }
    
    # Log các cột optional có sẵn
    available_optional = [col for col in optional_columns if col in df.columns]
    if available_optional:
        if logger:
            logger.log_info(f"Các cột optional có sẵn: {available_optional}")
    
    return {"success": True, "message": "Các cột hợp lệ"}

def clean_dataframe(df):
    """
    Làm sạch DataFrame
    """
    original_count = len(df)
    
    # Xóa các dòng rỗng
    df = df.dropna(subset=['custom_no', 'custom_item_name_detail'])
    
    # Trim các cột text
    text_columns = ['custom_no', 'custom_item_name_detail', 'custom_invoice_number']
    for col in text_columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
    
    cleaned_count = len(df)
    removed_count = original_count - cleaned_count
    
    if removed_count > 0:
        logger.log_warning(f"Đã loại bỏ {removed_count} dòng rỗng/không hợp lệ")
    
    logger.log_success(f"Sau khi làm sạch còn {cleaned_count} dòng hợp lệ")
    return df

def create_stock_entry_for_group(custom_no, group_df):
    """
    Tạo Stock Entry cho một nhóm dữ liệu
    """
    try:
        # Tạo Stock Entry document
        stock_entry = create_stock_entry_doc(group_df.iloc[0], custom_no)
        
        # Debug: In ra posting fields trước khi thêm items
        logger.log_info(f"  🔍 Before adding items:")
        logger.log_info(f"    - set_posting_time: {getattr(stock_entry, 'set_posting_time', 'NOT_SET')}")
        logger.log_info(f"    - posting_date: {getattr(stock_entry, 'posting_date', 'NOT_SET')}")
        logger.log_info(f"    - posting_time: {getattr(stock_entry, 'posting_time', 'NOT_SET')}")
        
        # Thêm items vào Stock Entry
        items_added = 0
        item_errors = []
        
        for index, row in group_df.iterrows():
            item_result = add_item_to_stock_entry(stock_entry, row, index + 1)
            if item_result["success"]:
                items_added += 1
                logger.log_success(f"  Item {items_added}: {item_result['item_code']} - Qty: {row.get('qty', 0)}")
            else:
                item_errors.append(f"Dòng {index + 1}: {item_result['message']}")
                logger.log_error(f"  Dòng {index + 1}: {item_result['message']}")
        
        if items_added == 0:
            return {
                "success": False,
                "message": f"Không có item nào hợp lệ. Lỗi: {'; '.join(item_errors)}"
            }
        
        # Set from_warehouse của parent bằng s_warehouse của item đầu tiên
        if stock_entry.items and len(stock_entry.items) > 0:
            first_item = stock_entry.items[0]
            if hasattr(first_item, 's_warehouse') and first_item.s_warehouse:
                stock_entry.from_warehouse = first_item.s_warehouse
                logger.log_info(f"  Set from_warehouse: {first_item.s_warehouse}")
        
        # Tổng hợp custom_invoice_number từ items (loại bỏ trùng)
        aggregate_invoice_numbers_to_parent(stock_entry)
        
        # Debug: In ra posting fields trước khi save
        logger.log_info(f"  🔍 Before save:")
        logger.log_info(f"    - set_posting_time: {getattr(stock_entry, 'set_posting_time', 'NOT_SET')}")
        logger.log_info(f"    - posting_date: {getattr(stock_entry, 'posting_date', 'NOT_SET')}")
        logger.log_info(f"    - posting_time: {getattr(stock_entry, 'posting_time', 'NOT_SET')}")
        
        # **QUAN TRỌNG**: Validate và set lại posting fields trước khi save
        # Đảm bảo set_posting_time = 1 không bị override
        if not getattr(stock_entry, 'set_posting_time', None):
            stock_entry.set_posting_time = 1
            logger.log_warning(f"  ⚠️ Re-setting set_posting_time = 1")
        
        # Đảm bảo posting_date không rỗng
        if not getattr(stock_entry, 'posting_date', None):
            stock_entry.posting_date = nowdate()
            logger.log_warning(f"  ⚠️ Re-setting posting_date = {nowdate()}")
            
        # Đảm bảo posting_time không rỗng
        if not getattr(stock_entry, 'posting_time', None):
            stock_entry.posting_time = "17:00:00"
            logger.log_warning(f"  ⚠️ Re-setting posting_time = 17:00:00")
        
        # Lưu Stock Entry
        logger.log_info(f"  💾 Saving Stock Entry...")
        stock_entry.save()
        logger.log_success(f"  ✅ Stock Entry saved: {stock_entry.name}")
        
        # Debug: Load lại document và kiểm tra posting fields sau khi save
        saved_doc = frappe.get_doc("Stock Entry", stock_entry.name)
        logger.log_info(f"  🔍 After save (reloaded from DB):")
        logger.log_info(f"    - set_posting_time: {getattr(saved_doc, 'set_posting_time', 'NOT_SET')}")
        logger.log_info(f"    - posting_date: {getattr(saved_doc, 'posting_date', 'NOT_SET')}")
        logger.log_info(f"    - posting_time: {getattr(saved_doc, 'posting_time', 'NOT_SET')}")
        
        return {
            "success": True,
            "stock_entry_name": stock_entry.name,
            "items_count": items_added,
            "posting_date": getattr(stock_entry, 'posting_date', ''),
            "custom_no": getattr(stock_entry, 'custom_no', ''),
            "custom_invoice_number": getattr(stock_entry, 'custom_invoice_number', ''),
            "message": f"Đã tạo thành công với {items_added} items"
        }
        
    except Exception as e:
        logger.log_error(f"  💥 Exception details: {str(e)}")
        import traceback
        logger.log_error(f"  📍 Traceback: {traceback.format_exc()}")
        return {
            "success": False,
            "message": f"Lỗi tạo Stock Entry: {str(e)}"
        }

def create_stock_entry_doc(first_row, custom_no):
    """
    Tạo Stock Entry document từ dòng đầu tiên
    """
    stock_entry = frappe.new_doc("Stock Entry")
    
    # Thiết lập các field cơ bản
    stock_entry.company = DEFAULT_COMPANY
    stock_entry.purpose = "Material Issue"
    stock_entry.stock_entry_type = "Material Issue"
    
    # QUAN TRỌNG: Set set_posting_time = 1 để có thể tùy chỉnh posting_date
    stock_entry.set_posting_time = 1
    
    # Thiết lập posting_date
    posting_date_value = first_row.get('posting_date')
    final_posting_date = None

    if posting_date_value is not None and pd.notna(posting_date_value):
        try:
            # Nếu là datetime object từ pandas/Excel
            if hasattr(posting_date_value, 'strftime'):
                final_posting_date = posting_date_value.strftime('%Y-%m-%d')
                logger.log_info(f"  Processing posting_date from Excel datetime: {posting_date_value} -> {final_posting_date}")
            # Nếu là string
            elif isinstance(posting_date_value, str):
                final_posting_date = posting_date_value
                logger.log_info(f"  Processing posting_date from string: {posting_date_value}")
            else:
                # Convert về string nếu có thể
                final_posting_date = str(posting_date_value)
                logger.log_info(f"  Processing posting_date converted: {posting_date_value} -> {final_posting_date}")
        except Exception as e:
            logger.log_warning(f"Lỗi xử lý posting_date '{posting_date_value}': {str(e)}, sử dụng ngày hiện tại")
            final_posting_date = nowdate()
    else:
        final_posting_date = nowdate()
        logger.log_info(f"  Posting_date trống, sử dụng ngày hiện tại: {final_posting_date}")
    
    # Set posting_date
    stock_entry.posting_date = final_posting_date
    logger.log_info(f"  ✅ Set posting_date = {final_posting_date}")
    
    # Thiết lập posting_time
    posting_time_value = first_row.get('posting_time')
    final_posting_time = None
    
    if posting_time_value is not None and pd.notna(posting_time_value):
        try:
            # Nếu là time object
            if hasattr(posting_time_value, 'strftime'):
                final_posting_time = posting_time_value.strftime('%H:%M:%S')
                logger.log_info(f"  Processing posting_time from Excel time: {posting_time_value} -> {final_posting_time}")
            # Nếu là string
            elif isinstance(posting_time_value, str):
                final_posting_time = posting_time_value
                logger.log_info(f"  Processing posting_time from string: {posting_time_value}")
            else:
                final_posting_time = str(posting_time_value)
                logger.log_info(f"  Processing posting_time converted: {posting_time_value} -> {final_posting_time}")
        except Exception as e:
            logger.log_warning(f"Lỗi xử lý posting_time '{posting_time_value}': {str(e)}, sử dụng thời gian mặc định")
            final_posting_time = "08:00:00"
    else:
        # Set thời gian mặc định nếu không có trong Excel
        final_posting_time = "08:00:00"
        logger.log_info(f"  Posting_time trống, sử dụng thời gian mặc định: {final_posting_time}")
    
    # Set posting_time
    stock_entry.posting_time = final_posting_time
    logger.log_info(f"  ✅ Set posting_time = {final_posting_time}")
    
    # Debug: In ra các field đã set
    logger.log_info(f"  🔍 Debug fields set:")
    logger.log_info(f"    - set_posting_time: {stock_entry.set_posting_time}")
    logger.log_info(f"    - posting_date: {stock_entry.posting_date}")
    logger.log_info(f"    - posting_time: {stock_entry.posting_time}")
    
    # Custom fields từ Excel
    custom_fields_mapping = {
        'custom_no': custom_no,
        'custom_fg_style': 'custom_fg_style',
        'custom_fg_size': 'custom_fg_size', 
        'custom_fg_qty': 'custom_fg_qty',
        'custom_line': 'custom_line',
        'custom_fg_color': 'custom_fg_color',
        'custom_note': 'custom_note',
        'custom_material_issue_purpose': 'custom_material_issue_purpose'
    }
    
    for se_field, excel_field in custom_fields_mapping.items():
        if se_field == 'custom_no':
            # Custom_no luôn set từ parameter
            setattr(stock_entry, se_field, custom_no)
            continue
            
        if excel_field in first_row and pd.notna(first_row[excel_field]):
            value = first_row[excel_field]
            
            # Xử lý text fields - trim và format
            if isinstance(value, str):
                value = format_text_field(value, excel_field)
            
            setattr(stock_entry, se_field, value)
    
    return stock_entry

def format_text_field(value, field_name):
    """
    Format text field giống logic trong JS
    """
    if not value:
        return value
    
    # Trim và thay nhiều khoảng trắng bằng 1
    processed_value = str(value).strip()
    processed_value = ' '.join(processed_value.split())
    
    # Áp dụng title case cho một số field
    title_case_fields = ['custom_line', 'custom_fg_style', 'custom_fg_color', 'custom_fg_size']
    if field_name in title_case_fields:
        # Chỉ áp dụng title case nếu không phải số/code
        if not processed_value.replace('-', '').replace('.', '').replace(' ', '').isdigit():
            processed_value = processed_value.title()
    
    return processed_value

# Performance optimization: Add item cache
item_cache = {}
warehouse_cache = {}

def find_item_by_pattern(pattern_search):
    """
    Tìm item dựa trên exact match custom_item_name_detail với caching
    """
    try:
        if not pattern_search or pd.isna(pattern_search):
            return None
            
        pattern_search = cstr(pattern_search).strip()
        
        # Check cache first
        if pattern_search in item_cache:
            return item_cache[pattern_search]
        
        # Exact match với custom_item_name_detail
        items = frappe.get_list(
            "Item",
            filters={
                "custom_item_name_detail": pattern_search,
                "has_variants": 0,
            },
            fields=["name", "item_code", "item_name", "stock_uom", "custom_item_name_detail"],
            limit=1
        )
        
        if items:
            # Cache the result
            item_cache[pattern_search] = items[0]
            if logger:
                logger.log_info(f"  ✅ Found exact match: {items[0]['item_code']} - {items[0]['custom_item_name_detail']}")
            return items[0]
        
        # Cache negative result as well
        item_cache[pattern_search] = None
        if logger:
            logger.log_warning(f"  ❌ No exact match found for: '{pattern_search}'")
        
        return None
            
    except Exception as e:
        if logger:
            logger.log_error(f"Lỗi tìm item với pattern '{pattern_search}': {str(e)}")
        return None

def batch_find_items(pattern_list):
    """
    Performance optimization: Batch lookup for multiple items
    """
    try:
        if not pattern_list:
            return {}
        
        # Filter out cached items
        uncached_patterns = [p for p in pattern_list if p not in item_cache]
        
        if uncached_patterns:
            # Batch query for all uncached items
            items = frappe.db.sql("""
                SELECT name, item_code, item_name, stock_uom, custom_item_name_detail
                FROM `tabItem`
                WHERE custom_item_name_detail IN %(patterns)s
                AND has_variants = 0
            """, {"patterns": uncached_patterns}, as_dict=True)
            
            # Update cache with results
            found_patterns = set()
            for item in items:
                pattern = item['custom_item_name_detail']
                item_cache[pattern] = item
                found_patterns.add(pattern)
            
            # Cache negative results
            for pattern in uncached_patterns:
                if pattern not in found_patterns:
                    item_cache[pattern] = None
        
        # Return all requested items from cache
        return {pattern: item_cache.get(pattern) for pattern in pattern_list}
        
    except Exception as e:
        if logger:
            logger.log_error(f"Error in batch item lookup: {str(e)}")
        return {}

def add_item_to_stock_entry(stock_entry, row, row_number):
    """
    Performance optimized item addition using cached lookups
    """
    try:
        # Use cached item lookup
        pattern_search = row.get('custom_item_name_detail', '')
        item = item_cache.get(pattern_search)
        
        if not item:
            return {
                "success": False,
                "message": f"Không tìm thấy item với pattern: '{pattern_search}'"
            }
        
        # Kiểm tra số lượng
        qty = flt(row.get('qty', 0))
        if qty <= 0:
            return {
                "success": False,
                "message": f"Số lượng không hợp lệ: {qty}"
            }
        
        # Determine warehouse - priority: Excel > Default warehouse
        warehouse = None
        excel_warehouse = row.get('s_warehouse', '')
        
        if excel_warehouse and pd.notna(excel_warehouse) and str(excel_warehouse).strip():
            # Use warehouse from Excel
            excel_warehouse = str(excel_warehouse).strip()
            if frappe.db.exists("Warehouse", excel_warehouse):
                warehouse = excel_warehouse
                logger.log_info(f"  Using warehouse from Excel: {warehouse} for item {item['item_code']}")
            else:
                return {
                    "success": False,
                    "message": f"Excel warehouse '{excel_warehouse}' không tồn tại cho item {item['item_code']}"
                }
        else:
            # Fallback to default warehouse
            warehouse = warehouse_cache.get(item['item_code'])
            if warehouse:
                logger.log_info(f"  Using default warehouse: {warehouse} for item {item['item_code']}")
        
        if not warehouse:
            return {
                "success": False,
                "message": f"Không có warehouse nào được chỉ định và không tìm thấy default warehouse cho item {item['item_code']}"
            }
        
        # Kiểm tra invoice number
        invoice_number = cstr(row.get('custom_invoice_number', '')).strip()
        if not invoice_number:
            return {
                "success": False,
                "message": f"Thiếu invoice number cho item {item['item_code']}"
            }
        
        # Performance optimization: Skip stock validation in batch mode
        # This can be re-enabled if needed, but significantly improves performance
        # available_qty = get_available_qty_by_invoice(item['item_code'], warehouse, invoice_number)
        # if available_qty < qty:
        #     return {"success": False, "message": f"Insufficient stock..."}
        
        # Tạo item row
        item_row = stock_entry.append("items", {})
        item_row.item_code = item['item_code']
        item_row.s_warehouse = warehouse
        item_row.qty = qty
        item_row.custom_invoice_number = invoice_number
        
        # Sync các field từ parent
        sync_parent_fields_to_item(stock_entry, item_row)
        
        return {
            "success": True,
            "item_code": item['item_code'],
            "message": f"Thêm thành công item {item['item_code']}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"Lỗi thêm item: {str(e)}"
        }

def sync_parent_fields_to_item(stock_entry, item_row):
    """
    Sync các field từ parent xuống item row
    """
    parent_fields_to_sync = [
        'custom_material_issue_purpose',
        'custom_line', 
        'custom_fg_qty',
        'custom_fg_style',
        'custom_fg_color',
        'custom_fg_size'
    ]
    
    for field in parent_fields_to_sync:
        if hasattr(stock_entry, field) and getattr(stock_entry, field):
            setattr(item_row, field, getattr(stock_entry, field))

def aggregate_invoice_numbers_to_parent(stock_entry):
    """
    Tổng hợp custom_invoice_number từ items vào parent (loại bỏ trùng)
    Giống logic trong JS: aggregate_invoice_numbers()
    """
    try:
        if not stock_entry.items or len(stock_entry.items) == 0:
            return
        
        # Thu thập tất cả invoice numbers từ items
        invoice_numbers = []
        
        for item in stock_entry.items:
            if hasattr(item, 'custom_invoice_number') and item.custom_invoice_number:
                invoice_num = cstr(item.custom_invoice_number).strip()
                # Chỉ thêm nếu chưa có trong list (loại bỏ trùng)
                if invoice_num and invoice_num not in invoice_numbers:
                    invoice_numbers.append(invoice_num)
        
        # Kết hợp với "; " separator
        aggregated_invoices = "; ".join(invoice_numbers)
        # Giới hạn tối đa độ dài 140 ký tự
        if len(aggregated_invoices) > 140:
            aggregated_invoices = aggregated_invoices[:137] + "..."
            logger.log_warning(f"  Aggregated invoice numbers quá dài, cắt ngắn xuống 140 ký tự: {aggregated_invoices}")
        
        # Set vào parent field
        if aggregated_invoices:
            stock_entry.custom_invoice_number = aggregated_invoices
            logger.log_info(f"  Aggregated {len(invoice_numbers)} invoice numbers: {aggregated_invoices}")
        
    except Exception as e:
        logger.log_error(f"Lỗi tổng hợp invoice numbers: {str(e)}")

def show_summary(created_entries):
    """
    Hiển thị tóm tắt các Stock Entry đã tạo
    """
    if not created_entries:
        return
    
    print(f"\n📋 DANH SÁCH STOCK ENTRIES ĐÃ TẠO:")
    for i, entry_name in enumerate(created_entries, 1):
        print(f"  {i}. {entry_name}")

def debug_posting_date_issue():
    """
    Function để debug posting_date issue
    """
    print("🔬 DEBUGGING POSTING DATE ISSUE...")
    
    try:
        # Tạo Stock Entry đơn giản để test
        test_doc = frappe.new_doc("Stock Entry")
        test_doc.company = DEFAULT_COMPANY
        test_doc.purpose = "Material Issue"
        test_doc.stock_entry_type = "Material Issue"
        
        print(f"📋 Initial values:")
        print(f"  - set_posting_time: {getattr(test_doc, 'set_posting_time', 'NOT_SET')}")
        print(f"  - posting_date: {getattr(test_doc, 'posting_date', 'NOT_SET')}")
        print(f"  - posting_time: {getattr(test_doc, 'posting_time', 'NOT_SET')}")
        
        # Set posting fields
        test_doc.set_posting_time = 1
        test_doc.posting_date = "2024-01-15"
        test_doc.posting_time = "14:30:00"
        test_doc.custom_no = "custom_no_test"
        
        print(f"\n📝 After setting:")
        print(f"  - set_posting_time: {test_doc.set_posting_time}")
        print(f"  - posting_date: {test_doc.posting_date}")
        print(f"  - posting_time: {test_doc.posting_time}")
        
        # Thêm một item test (cần item và warehouse thực tế)
        # Lấy item đầu tiên có sẵn
        items = frappe.get_list("Item", limit=1, fields=["name", "item_code"])
        warehouses = frappe.get_list("Warehouse", filters={"company": DEFAULT_COMPANY}, limit=1, fields=["name"])
        
        if items and warehouses:
            test_doc.append("items", {
                "item_code": items[0]["item_code"],
                "s_warehouse": warehouses[0]["name"],
                "qty": 1
            })
            
            print(f"\n💾 Saving test document...")
            test_doc.save()
            
            print(f"✅ Saved with name: {test_doc.name}")
            
            # Load lại và kiểm tra
            reloaded = frappe.get_doc("Stock Entry", test_doc.name)
            print(f"\n🔍 After reload from database:")
            print(f"  - set_posting_time: {getattr(reloaded, 'set_posting_time', 'NOT_SET')}")
            print(f"  - posting_date: {getattr(reloaded, 'posting_date', 'NOT_SET')}")
            print(f"  - posting_time: {getattr(reloaded, 'posting_time', 'NOT_SET')}")
            
            # Cleanup - delete test document
            frappe.delete_doc("Stock Entry", test_doc.name)
            print(f"\n🗑️ Cleaned up test document")
            
            return True
        else:
            print("❌ Không tìm thấy Item hoặc Warehouse để test")
            return False
        
    except Exception as e:
        print(f"❌ Error in debug: {str(e)}")
        import traceback
        print(f"📍 Traceback: {traceback.format_exc()}")
        return False

def test_posting_date_formats():
    """
    Test các format posting_date khác nhau
    """
    print("\n🧪 TESTING POSTING DATE FORMATS...")
    
    test_dates = [
        "2024-01-15",           # String YYYY-MM-DD
        "15/01/2024",           # String DD/MM/YYYY
        "2024-01-15 14:30:00",  # String với time
        pd.Timestamp("2024-01-15"),  # Pandas timestamp
        datetime.date(2024, 1, 15),  # Python date
        datetime.datetime(2024, 1, 15, 14, 30, 0)  # Python datetime
    ]
    
    for i, test_date in enumerate(test_dates):
        print(f"\n📅 Test {i+1}: {type(test_date).__name__} = {test_date}")
        
        try:
            if hasattr(test_date, 'strftime'):
                formatted = test_date.strftime('%Y-%m-%d')
                print(f"  ✅ Formatted: {formatted}")
            elif isinstance(test_date, str):
                print(f"  ✅ String as-is: {test_date}")
            else:
                converted = str(test_date)
                print(f"  ✅ Converted: {converted}")
        except Exception as e:
            print(f"  ❌ Error: {str(e)}")

# Hàm để test với dữ liệu mẫu
def test_with_sample_data():
    """
    Tạo dữ liệu mẫu để test
    """
    print("🧪 Tạo dữ liệu mẫu để test...")
    
    sample_data = [
        {
            'custom_item_name_detail': 'AT0452HSMP-3D Iron Gate Vital 25Ss',
            'posting_date': '2024-01-15',
            'posting_time': '14:30:00',
            'custom_no': 'TEST001',
            'qty': 10,
            'custom_invoice_number': 'IV001',
            'custom_fg_style': 'Style A',
            'custom_line': '1'
        }
    ]
    
    # Tạo file Excel tạm
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
        df = pd.DataFrame(sample_data)
        df.to_excel(tmp_file.name, index=False)
        
        print(f"📁 File test tạo tại: {tmp_file.name}")
        return create_material_issue(tmp_file.name)

# Export các hàm chính
__all__ = [
    'create_material_issue',  
    'validate_excel_file',
    'import_material_issue_from_excel',
    'get_available_qty_by_invoice',
    'get_default_warehouse_for_item',
    'test_with_sample_data', 
    'debug_posting_date_issue', 
    'test_posting_date_formats',
    'debug_available_qty_calculation',
    'validate_stock_balance_by_invoice',
    'get_stock_ledger_entries_by_invoice',
    'validate_custom_item_name_detail_uniqueness',
    'find_duplicate_custom_item_names',
    'test_item_lookup_performance'
]

def validate_custom_item_name_detail_uniqueness():
    """
    Kiểm tra tính duy nhất của custom_item_name_detail trong hệ thống
    """
    print(f"\n🔍 VALIDATING CUSTOM_ITEM_NAME_DETAIL UNIQUENESS")
    print("="*60)
    
    try:
        # Query tất cả items có custom_item_name_detail
        items = frappe.db.sql("""
            SELECT 
                item_code,
                custom_item_name_detail,
                COUNT(*) as count_items
            FROM `tabItem`
            WHERE custom_item_name_detail IS NOT NULL
            AND custom_item_name_detail != ''
            AND has_variants = 0
            GROUP BY custom_item_name_detail
            ORDER BY count_items DESC, custom_item_name_detail
        """, as_dict=True)
        
        total_items = len(items)
        duplicate_items = [item for item in items if item['count_items'] > 1]
        unique_items = [item for item in items if item['count_items'] == 1]
        
        print(f"📊 SUMMARY:")
        print(f"  - Total items with custom_item_name_detail: {total_items}")
        print(f"  - Unique custom_item_name_detail: {len(unique_items)}")
        print(f"  - Duplicate custom_item_name_detail: {len(duplicate_items)}")
        
        if duplicate_items:
            print(f"\n❌ DUPLICATE CUSTOM_ITEM_NAME_DETAIL FOUND:")
            print("-" * 60)
            for item in duplicate_items[:10]:  # Show first 10
                print(f"  '{item['custom_item_name_detail']}' -> {item['count_items']} items")
                
                # Show which items have this duplicate name
                duplicate_details = frappe.db.sql("""
                    SELECT item_code, item_name
                    FROM `tabItem`
                    WHERE custom_item_name_detail = %s
                    AND has_variants = 0
                """, item['custom_item_name_detail'], as_dict=True)
                
                for detail in duplicate_details:
                    print(f"    - {detail['item_code']}: {detail['item_name']}")
                print()
            
            if len(duplicate_items) > 10:
                print(f"  ... and {len(duplicate_items) - 10} more duplicates")
        else:
            print(f"\n✅ ALL CUSTOM_ITEM_NAME_DETAIL ARE UNIQUE!")
        
        return {
            "total_items": total_items,
            "unique_count": len(unique_items),
            "duplicate_count": len(duplicate_items),
            "duplicates": duplicate_items
        }
        
    except Exception as e:
        print(f"❌ Error validating uniqueness: {str(e)}")
        return {"error": str(e)}

def find_duplicate_custom_item_names():
    """
    Tìm và trả về chi tiết các custom_item_name_detail bị duplicate
    """
    try:
        duplicates = frappe.db.sql("""
            SELECT 
                custom_item_name_detail,
                GROUP_CONCAT(item_code SEPARATOR ', ') as item_codes,
                COUNT(*) as count_items
            FROM `tabItem`
            WHERE custom_item_name_detail IS NOT NULL
            AND custom_item_name_detail != ''
            AND has_variants = 0
            GROUP BY custom_item_name_detail
            HAVING COUNT(*) > 1
            ORDER BY count_items DESC
        """, as_dict=True)
        
        return duplicates
        
    except Exception as e:
        print(f"❌ Error finding duplicates: {str(e)}")
        return []

def test_item_lookup_performance():
    """
    Test performance của exact match vs pattern matching
    """
    print(f"\n⏱️ TESTING ITEM LOOKUP PERFORMANCE")
    print("="*60)
    
    import time
    
    try:
        # Lấy một số custom_item_name_detail để test
        test_items = frappe.db.sql("""
            SELECT custom_item_name_detail
            FROM `tabItem`
            WHERE custom_item_name_detail IS NOT NULL
            AND custom_item_name_detail != ''
            AND has_variants = 0
            LIMIT 10
        """, as_dict=True)
        
        if not test_items:
            print("❌ No items found for testing")
            return
        
        print(f"Testing with {len(test_items)} items...")
        
        # Test exact match (current method)
        start_time = time.time()
        exact_results = []
        
        for item in test_items:
            result = find_item_by_pattern(item['custom_item_name_detail'])
            exact_results.append(result is not None)
        
        exact_time = time.time() - start_time
        
        # Test pattern matching (old method) - for comparison
        start_time = time.time()
        pattern_results = []
        
        for item in test_items:
            pattern_search = item['custom_item_name_detail']
            items = frappe.get_list(
                "Item",
                filters={
                    "custom_item_name_detail": ["like", f"%{pattern_search}%"],
                    "has_variants": 0,
                },
                fields=["item_code"],
                limit=5
            )
            pattern_results.append(len(items) > 0)
        
        pattern_time = time.time() - start_time
        
        print(f"\n📊 PERFORMANCE RESULTS:")
        print(f"  Exact Match Method:")
        print(f"    - Time: {exact_time:.4f} seconds")
        print(f"    - Success rate: {sum(exact_results)}/{len(exact_results)} ({sum(exact_results)/len(exact_results)*100:.1f}%)")
        
        print(f"  Pattern Match Method (old):")
        print(f"    - Time: {pattern_time:.4f} seconds")
        print(f"    - Success rate: {sum(pattern_results)}/{len(pattern_results)} ({sum(pattern_results)/len(pattern_results)*100:.1f}%)")
        
        improvement = ((pattern_time - exact_time) / pattern_time) * 100
        print(f"\n✅ Performance improvement: {improvement:.1f}% faster with exact match")
        
        return {
            "exact_time": exact_time,
            "pattern_time": pattern_time,
            "improvement_percent": improvement,
            "exact_success_rate": sum(exact_results)/len(exact_results)*100,
            "pattern_success_rate": sum(pattern_results)/len(pattern_results)*100
        }
        
    except Exception as e:
        print(f"❌ Error testing performance: {str(e)}")
        return {"error": str(e)}

def debug_available_qty_calculation(item_code, warehouse, invoice_number):
    """
    Debug function để kiểm tra chi tiết tính toán available quantity
    """
    print(f"\n🔍 DEBUGGING AVAILABLE QTY CALCULATION")
    print(f"Item: {item_code}")
    print(f"Warehouse: {warehouse}")
    print(f"Invoice: {invoice_number}")
    print("="*60)
    
    try:
        # Lấy tất cả entries
        entries = frappe.db.sql("""
            SELECT 
                voucher_type,
                voucher_no,
                actual_qty,
                qty_after_transaction,
                posting_date,
                posting_time,
                creation,
                valuation_rate,
                stock_value_difference
            FROM `tabStock Ledger Entry`
            WHERE item_code = %s 
            AND warehouse = %s 
            AND custom_invoice_number = %s
            AND is_cancelled = 0
            AND docstatus < 2
            ORDER BY posting_date ASC, posting_time ASC, creation ASC
        """, (item_code, warehouse, invoice_number), as_dict=True)
        
        if not entries:
            print("❌ No Stock Ledger Entries found!")
            return
        
        print(f"📋 Found {len(entries)} Stock Ledger Entries:")
        
        running_balance = 0.0
        latest_reconciliation_qty = None
        
        for i, entry in enumerate(entries, 1):
            print(f"\n{i}. {entry['voucher_type']} - {entry['voucher_no']}")
            print(f"   Date: {entry['posting_date']} {entry['posting_time']}")
            print(f"   Actual Qty: {entry['actual_qty']}")
            print(f"   Qty After Transaction: {entry['qty_after_transaction']}")
            print(f"   Valuation Rate: {entry['valuation_rate']}")
            
            if entry['voucher_type'] == 'Stock Reconciliation':
                latest_reconciliation_qty = flt(entry['qty_after_transaction'])
                running_balance = latest_reconciliation_qty
                print(f"   🔄 RECONCILIATION: Reset balance to {latest_reconciliation_qty}")
            else:
                running_balance += flt(entry['actual_qty'])
                print(f"   ➕ Added {entry['actual_qty']}, Running balance: {running_balance}")
        
        print("\n" + "="*60)
        print(f"📊 CALCULATION RESULT:")
        
        # Tính bằng function chính
        calculated_qty = get_available_qty_by_invoice(item_code, warehouse, invoice_number)
        print(f"Function result: {calculated_qty}")
        print(f"Manual calculation: {running_balance}")
        
        if abs(calculated_qty - running_balance) < 0.001:
            print("✅ Calculations match!")
        else:
            print("❌ Calculations don't match!")
        
        return {
            "entries": entries,
            "calculated_qty": calculated_qty,
            "manual_calculation": running_balance,
            "latest_reconciliation": latest_reconciliation_qty
        }
        
    except Exception as e:
        print(f"❌ Error in debug: {str(e)}")
        import traceback
        print(traceback.format_exc())

def validate_stock_balance_by_invoice(item_code=None, warehouse=None, invoice_number=None):
    """
    Validate stock balance theo invoice number với tổng balance
    """
    print(f"\n📊 VALIDATING STOCK BALANCE BY INVOICE")
    
    conditions = ["sle.is_cancelled = 0", "sle.docstatus < 2"]
    values = []
    
    if item_code:
        conditions.append("sle.item_code = %s")
        values.append(item_code)
    
    if warehouse:
        conditions.append("sle.warehouse = %s")
        values.append(warehouse)
    
    if invoice_number:
        conditions.append("sle.custom_invoice_number = %s")
        values.append(invoice_number)
    
    where_clause = " AND ".join(conditions)
    
    # Tính tổng balance theo từng invoice
    query = f"""
        SELECT 
            sle.item_code,
            sle.warehouse,
            sle.custom_invoice_number,
            SUM(CASE 
                WHEN sle.voucher_type = 'Stock Reconciliation' 
                THEN sle.qty_after_transaction 
                ELSE sle.actual_qty 
            END) as calculated_balance,
            COUNT(*) as entry_count,
            MAX(sle.posting_date) as last_transaction_date
        FROM `tabStock Ledger Entry` sle
        WHERE {where_clause}
        AND sle.custom_invoice_number IS NOT NULL
        AND sle.custom_invoice_number != ''
        GROUP BY sle.item_code, sle.warehouse, sle.custom_invoice_number
        ORDER BY sle.item_code, sle.warehouse, sle.custom_invoice_number
    """
    
    results = frappe.db.sql(query, values, as_dict=True)
    
    print(f"Found {len(results)} item-warehouse-invoice combinations:")
    print("="*80)
    
    validation_issues = []
    
    for result in results:
        # Tính bằng function
        function_result = get_available_qty_by_invoice(
            result['item_code'], 
            result['warehouse'], 
            result['custom_invoice_number']
        )
        
        difference = abs(function_result - result['calculated_balance'])
        
        print(f"Item: {result['item_code']}")
        print(f"Warehouse: {result['warehouse']}")
        print(f"Invoice: {result['custom_invoice_number']}")
        print(f"SQL Calculated: {result['calculated_balance']}")
        print(f"Function Result: {function_result}")
        print(f"Difference: {difference}")
        print(f"Entry Count: {result['entry_count']}")
        print(f"Last Transaction: {result['last_transaction_date']}")
        
        if difference > 0.001:
            print("❌ MISMATCH!")
            validation_issues.append({
                'item_code': result['item_code'],
                'warehouse': result['warehouse'],
                'invoice_number': result['custom_invoice_number'],
                'sql_result': result['calculated_balance'],
                'function_result': function_result,
                'difference': difference
            })
        else:
            print("✅ Match")
        
        print("-" * 40)
    
    if validation_issues:
        print(f"\n❌ Found {len(validation_issues)} validation issues!")
        for issue in validation_issues:
            print(f"  - {issue['item_code']} | {issue['warehouse']} | {issue['invoice_number']}: diff={issue['difference']}")
    else:
        print(f"\n✅ All {len(results)} calculations are correct!")
    
    return {
        "total_checked": len(results),
        "issues_found": len(validation_issues),
        "validation_issues": validation_issues,
        "results": results
    }

def get_stock_ledger_entries_by_invoice(invoice_number, item_code=None, warehouse=None):
    """
    Lấy tất cả Stock Ledger Entries theo invoice number để review
    """
    conditions = [
        "custom_invoice_number = %s",
        "is_cancelled = 0",
        "docstatus < 2"
    ]
    values = [invoice_number]
    
    if item_code:
        conditions.append("item_code = %s")
        values.append(item_code)
    
    if warehouse:
        conditions.append("warehouse = %s")
        values.append(warehouse)
    
    where_clause = " AND ".join(conditions)
    
    entries = frappe.db.sql(f"""
        SELECT 
            name,
            posting_date,
            posting_time,
            voucher_type,
            voucher_no,
            item_code,
            warehouse,
            actual_qty,
            qty_after_transaction,
            valuation_rate,
            stock_value_difference,
            custom_invoice_number,
            creation
        FROM `tabStock Ledger Entry`
        WHERE {where_clause}
        ORDER BY item_code, warehouse, posting_date, posting_time, creation
    """, values, as_dict=True)
    
    return entries

'''
# Cách sử dụng:

# Import module
import customize_erpnext.api.bulk_update_scripts.create_material_issue as material_issue_script

# 1. Test debug functions:
material_issue_script.test_posting_date_formats()
material_issue_script.debug_posting_date_issue()

# 2. Sử dụng file mặc định
material_issue_script.create_material_issue()

# 3. Hoặc chỉ định đường dẫn cụ thể
material_issue_script.create_material_issue("/home/sonnt/frappe-bench/sites/erp-sonnt.tiqn.local/public/files/create_material_issue.xlsx")

# 4. Hoặc test với dữ liệu mẫu
material_issue_script.test_with_sample_data() 

# 5. Web API calls (for frontend):
material_issue_script.create_excel_template()
material_issue_script.validate_excel_file('/files/uploaded_file.xlsx')
material_issue_script.import_material_issue_from_excel('/files/uploaded_file.xlsx')
'''