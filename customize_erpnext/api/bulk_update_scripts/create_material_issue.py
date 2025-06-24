#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import frappe
import pandas as pd
from frappe.utils import nowdate, flt, cstr
from collections import defaultdict
import os
import datetime
import sys

# Company mặc định
DEFAULT_COMPANY = "Toray International, VietNam Company Limited - Quang Ngai Branch"

# Đường dẫn file mặc định
DEFAULT_FILE_PATH = "/home/sonnt/frappe-bench/sites/erp-sonnt.tiqn.local/private/files/create_material_issue.xlsx"

class Logger:
    """
    Class để ghi log vào file và console
    """
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
        """
        Ghi log vào file và console
        
        Args:
            message (str): Nội dung log
            level (str): Mức độ log (INFO, ERROR, SUCCESS, WARNING)
            print_console (bool): Có in ra console không
        """
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
    Xử lý file Excel và tạo Stock Entry
    
    Args:
        file_path (str): Đường dẫn file Excel
        
    Returns:
        dict: Kết quả xử lý
    """
    result = {
        "success": True,
        "message": "",
        "success_count": 0,
        "error_count": 0,
        "total_items": 0,
        "created_entries": [],
        "errors": []
    }
    
    try:
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
        
        # Group theo custom_no
        grouped_data = df.groupby('custom_no')
        logger.log_info(f"Tìm thấy {len(grouped_data)} nhóm custom_no khác nhau")
        
        # Xử lý từng nhóm
        for group_index, (custom_no, group_df) in enumerate(grouped_data, 1):
            try:
                logger.log_info(f"Xử lý nhóm {group_index}/{len(grouped_data)}: {custom_no} với {len(group_df)} items")
                
                # Tạo Stock Entry cho nhóm này
                entry_result = create_stock_entry_for_group(custom_no, group_df)
                
                if entry_result["success"]:
                    result["success_count"] += 1
                    result["created_entries"].append(entry_result["stock_entry_name"])
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
        'parttern search item',  # Để tìm item
        'custom_no',            # Để group
        'warehouse',            # s_warehouse cho Material Issue  
        'qty',                  # Số lượng
        'custom_invoice_number' # Số hóa đơn
    ]
    
    # Các cột optional
    optional_columns = [
        'posting_date',         # Ngày chứng từ
        'posting_time'          # Thời gian chứng từ
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
    df = df.dropna(subset=['custom_no', 'parttern search item'])
    
    # Trim các cột text
    text_columns = ['custom_no', 'parttern search item', 'warehouse', 'custom_invoice_number']
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
            stock_entry.posting_time = "08:00:00"
            logger.log_warning(f"  ⚠️ Re-setting posting_time = 08:00:00")
        
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

def find_item_by_pattern(pattern_search):
    """
    Tìm item dựa trên pattern search
    """
    try:
        if not pattern_search or pd.isna(pattern_search):
            return None
            
        pattern_search = cstr(pattern_search).strip()
        
        # Tìm item có custom_item_name_detail chứa pattern
        items = frappe.get_list(
            "Item",
            filters={
                "custom_item_name_detail": ["like", f"%{pattern_search}%"]
            },
            fields=["name", "item_code", "item_name", "stock_uom", "custom_item_name_detail"],
            limit=5
        )
        
        if items:
            # Ưu tiên exact match trước
            for item in items:
                if item.get('custom_item_name_detail') == pattern_search:
                    return item
            # Nếu không có exact match, lấy item đầu tiên
            return items[0]
        
        return None
            
    except Exception as e:
        if logger:
            logger.log_error(f"Lỗi tìm item với pattern '{pattern_search}': {str(e)}")
        return None

def add_item_to_stock_entry(stock_entry, row, row_number):
    """
    Thêm item vào Stock Entry
    """
    try:
        # Tìm item
        pattern_search = row.get('parttern search item', '')
        item = find_item_by_pattern(pattern_search)
        
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
        
        # Kiểm tra warehouse
        warehouse = cstr(row.get('warehouse', '')).strip()
        if not warehouse:
            return {
                "success": False,
                "message": f"Thiếu warehouse cho item {item['item_code']}"
            }
        
        # Kiểm tra warehouse có tồn tại không
        if not frappe.db.exists("Warehouse", warehouse):
            return {
                "success": False,
                "message": f"Warehouse không tồn tại: {warehouse}"
            }
        
        # Kiểm tra invoice number
        invoice_number = cstr(row.get('custom_invoice_number', '')).strip()
        if not invoice_number:
            return {
                "success": False,
                "message": f"Thiếu invoice number cho item {item['item_code']}"
            }
        
        # Tạo item row
        item_row = stock_entry.append("items", {})
        item_row.item_code = item['item_code']
        item_row.s_warehouse = warehouse  # Source warehouse cho Material Issue
        item_row.qty = qty
        item_row.custom_invoice_number = invoice_number
        
        # Sync các field từ parent (theo logic JS)
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
        #  Tối đa độ dài 140 ký tự
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
            'parttern search item': 'AT0452HSMP-3D Iron Gate Vital 25Ss',
            'posting_date': '2024-01-15',
            'posting_time': '14:30:00',
            'custom_no': 'TEST001',
            'warehouse': 'C-Fabric - TIQN',
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
__all__ = ['create_material_issue', 'test_with_sample_data', 'debug_posting_date_issue', 'test_posting_date_formats']


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
'''