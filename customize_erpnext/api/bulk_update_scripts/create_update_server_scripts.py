import os
import frappe
import re
from datetime import datetime

# Thư mục chứa các file script server
SERVER_SCRIPT_FOLDER_PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../server_scripts"))

def create_update_server_scripts(reference_document_type=None, script_name=None):
    """
    Cập nhật hoặc tạo mới Server Scripts từ thư mục server_scripts vào ERPNext.
    Các thông tin Script Type, Reference Document Type, DocType Event được trích xuất
    từ các comment đầu tiên trong file.
    
    Parameters:
    reference_document_type (str, optional): Tên của reference document type (tương ứng với thư mục con).
    script_name (str, optional): Tên của script (tương ứng với tên file không có phần mở rộng).
    
    Behavior:
    - Nếu reference_document_type=None & script_name=None: áp dụng cho toàn bộ file trong các thư mục con
    - Nếu reference_document_type!=None & script_name=None: áp dụng cho toàn bộ file trong thư mục server_scripts/reference_document_type
    - Nếu reference_document_type!=None & script_name!=None: áp dụng cho file script_name.py trong thư mục. 
      Nếu chưa tồn tại script_name trên database thì thực hiện tạo mới
    """
    
    # Trường hợp 1: Quét các thư mục con của thư mục gốc
    if reference_document_type is None and script_name is None:
        print(f"📂 Đang quét các thư mục con của: {SERVER_SCRIPT_FOLDER_PARENT}")
        
        # Đếm tổng số file sẽ xử lý để hiển thị xác nhận
        total_files = count_py_files_in_subdirectories(SERVER_SCRIPT_FOLDER_PARENT)
        
        if total_files == 0:
            print(" Không tìm thấy file .py nào trong các thư mục con.")
            return
        
        if not confirm_operation(f"Sẽ xử lý {total_files} file server script trong tất cả các thư mục con. Tiếp tục?"):
            print("❌ Đã hủy thao tác.")
            return
        
        # Lấy danh sách các thư mục con
        subdirs = [d for d in os.listdir(SERVER_SCRIPT_FOLDER_PARENT) 
                  if os.path.isdir(os.path.join(SERVER_SCRIPT_FOLDER_PARENT, d))]
        
        if not subdirs:
            print(" Không tìm thấy thư mục con nào trong thư mục gốc.")
            return
        
        for sub_folder in subdirs:
            # Gọi hàm với reference_document_type là tên thư mục con, nhưng không cần xác nhận lại
            create_update_server_scripts_without_confirmation(reference_document_type=sub_folder)
        
        print(" Đã hoàn thành xử lý toàn bộ thư mục con.")
        return
    
    # Trường hợp 2 và 3: reference_document_type đã được chỉ định
    SCRIPT_FOLDER = os.path.join(SERVER_SCRIPT_FOLDER_PARENT, reference_document_type)
    
    if not os.path.exists(SCRIPT_FOLDER):
        print(f"❌ Thư mục không tồn tại: {SCRIPT_FOLDER}")
        return
    
    # Trường hợp 3: Xử lý một file cụ thể
    if script_name is not None:
        file_name = f"{script_name}.py"
        file_path = os.path.join(SCRIPT_FOLDER, file_name)
        
        if not os.path.exists(file_path):
            print(f"❌ File không tồn tại: {file_path}")
            return
        
        process_server_script_file(file_path=file_path, script_name=script_name)
        return
    
    # Trường hợp 2: Xử lý tất cả các file trong thư mục
    py_files = [f for f in os.listdir(SCRIPT_FOLDER) if f.endswith(".py")]
    if not py_files:
        print(f" Không có file .py nào trong thư mục: {SCRIPT_FOLDER}")
        return
    
    if not confirm_operation(f"Sẽ xử lý {len(py_files)} file server script trong thư mục {reference_document_type}. Tiếp tục?"):
        print("❌ Đã hủy thao tác.")
        return
    
    print(f"📂 Đang quét thư mục: {SCRIPT_FOLDER}")
    
    for file_name in py_files:
        file_path = os.path.join(SCRIPT_FOLDER, file_name)
        script_name = file_name.replace(".py", "")
        
        process_server_script_file(file_path=file_path, script_name=script_name)

def create_update_server_scripts_without_confirmation(reference_document_type):
    """
    Phiên bản không yêu cầu xác nhận của hàm chính, dùng cho xử lý đệ quy các thư mục con
    sau khi đã xác nhận ở cấp cao nhất.
    """
    SCRIPT_FOLDER = os.path.join(SERVER_SCRIPT_FOLDER_PARENT, reference_document_type)
    
    if not os.path.exists(SCRIPT_FOLDER):
        print(f"❌ Thư mục không tồn tại: {SCRIPT_FOLDER}")
        return
    
    print(f"📂 Đang quét thư mục: {SCRIPT_FOLDER}")
    
    for file_name in os.listdir(SCRIPT_FOLDER):
        if file_name.endswith(".py"):
            file_path = os.path.join(SCRIPT_FOLDER, file_name)
            script_name = file_name.replace(".py", "")
            
            process_server_script_file(file_path=file_path, script_name=script_name)

def count_py_files_in_subdirectories(folder_path):
    """
    Đếm số lượng file .py trong các thư mục con, bỏ qua các file trực tiếp trong thư mục gốc
    """
    count = 0
    # Lặp qua các mục trong thư mục gốc
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        # Chỉ xử lý các thư mục, bỏ qua file
        if os.path.isdir(item_path):
            # Đếm các file .py trong thư mục con này và các thư mục con của nó
            for root, dirs, files in os.walk(item_path):
                count += sum(1 for f in files if f.endswith('.py'))
    return count

def confirm_operation(message):
    """
    Hiển thị thông báo xác nhận và trả về True nếu người dùng đồng ý, ngược lại trả về False
    """
    response = input(f"\n {message} (y/n): ")
    return response.lower() in ['y', 'yes']

def extract_script_metadata(script_content):
    """
    Trích xuất thông tin metadata từ các comment đầu tiên của file script
    
    Returns:
    dict: Dictionary chứa các thông tin metadata của script
    """
    metadata = {
        'script_type': 'DocType Event',  # Giá trị mặc định
        'reference_doctype': None,
        'doctype_event': 'Before Save'   # Giá trị mặc định
    }
    
    # Lấy các dòng đầu tiên của file để tìm metadata
    lines = script_content.split('\n')[:10]  # Chỉ xét 10 dòng đầu tiên
    
    # Pattern để tìm các comment metadata
    script_type_pattern = r'#\s*Script Type\s*:\s*(.+)'
    reference_doctype_pattern = r'#\s*Reference Document Type\s*:\s*(.+)'
    doctype_event_pattern = r'#\s*DocType Event\s*:\s*(.+)'
    
    for line in lines:
        # Tìm Script Type
        script_type_match = re.search(script_type_pattern, line)
        if script_type_match:
            metadata['script_type'] = script_type_match.group(1).strip()
            continue
            
        # Tìm Reference Document Type
        reference_doctype_match = re.search(reference_doctype_pattern, line)
        if reference_doctype_match:
            metadata['reference_doctype'] = reference_doctype_match.group(1).strip()
            continue
            
        # Tìm DocType Event
        doctype_event_match = re.search(doctype_event_pattern, line)
        if doctype_event_match:
            metadata['doctype_event'] = doctype_event_match.group(1).strip()
            continue
    
    return metadata

def get_current_user():
    """
    Lấy thông tin user đang thao tác với script thông qua lệnh whoami
    
    Returns:
    str: Tên của user đang thao tác với hệ thống
    """
    try:
        # Sử dụng lệnh whoami để lấy tên người dùng hiện tại
        import subprocess
        user_login = subprocess.check_output(['whoami'], text=True).strip()
        # Ensure user_login is returned correctly
        match user_login:
            case 'son_nt':
                user = 'son.nt@tiqn.com.vn'
            case 'vinh_nt': 
                user = 'vinh.nt@tiqn.com.vn'
            case 'frappe': 
                user = 'Administrator'  
        return user
    except Exception as e:
        # Ghi log lỗi và trả về giá trị mặc định an toàn
        print(f"Không thể xác định người dùng hiện tại: {str(e)}")
        return "Unknown User"

def process_server_script_file(file_path, script_name):
    """
    Xử lý một file server script: đọc nội dung, trích xuất metadata và cập nhật hoặc tạo mới trong database
    
    Parameters:
    file_path (str): Đường dẫn đến file script
    script_name (str): Tên của script (không bao gồm phần mở rộng .py)
    """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            script_content = file.read()
        
        file_name = os.path.basename(file_path)
        print(f"📄 Đọc file: {file_name}")
        
        # Trích xuất metadata từ nội dung script
        metadata = extract_script_metadata(script_content)
        
        # Lấy thông tin thời gian hiện tại và người dùng đang đăng nhập
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_user = get_current_user()
        
        # Thêm thời gian và user vào script trước khi update hoặc tạo mới
        lines = script_content.split('\n')
        metadata_end_index = 0
        
        # Tìm vị trí kết thúc của metadata
        for i, line in enumerate(lines[:10]):
            if (re.search(r'#\s*Script Type\s*:', line) or 
                re.search(r'#\s*Reference Document Type\s*:', line) or 
                re.search(r'#\s*DocType Event\s*:', line)):
                metadata_end_index = i + 1
        
        # Thêm Update at và User sau metadata
        update_info = [
            f"# Update at: {current_time}",
            f"# Updated by: {current_user}"
        ]
        
        # Loại bỏ các dòng Update at và Updated by cũ nếu có
        filtered_lines = []
        for i, line in enumerate(lines):
            if not (re.search(r'#\s*Update at\s*:', line) or re.search(r'#\s*Updated by\s*:', line)):
                filtered_lines.append(line)
        
        # Chèn thông tin update vào sau metadata
        updated_lines = filtered_lines[:metadata_end_index] + update_info + filtered_lines[metadata_end_index:]
        updated_script = '\n'.join(updated_lines)
        
        # Kiểm tra script có tồn tại trong DB không
        existing_script = frappe.get_value("Server Script", script_name, "name")
        
        if existing_script:
            # Cập nhật script vào DB
            frappe.db.set_value("Server Script", script_name, "script", updated_script)
            
            # Cập nhật các thông tin metadata
            frappe.db.set_value("Server Script", script_name, "script_type", metadata['script_type'])
            
            if metadata['reference_doctype']:
                frappe.db.set_value("Server Script", script_name, "reference_doctype", metadata['reference_doctype'])
            
            # Cập nhật doctype_event nếu script_type là DocType Event
            if metadata['script_type'] == 'DocType Event':
                frappe.db.set_value("Server Script", script_name, "doctype_event", metadata['doctype_event'])
                
            frappe.db.commit()
            print(f" Đã cập nhật: {script_name}")
        else:
            # Tạo mới Server Script
            doc = frappe.new_doc("Server Script")
            doc.name = script_name
            doc.script = updated_script
            doc.script_type = metadata['script_type']
            
            if metadata['reference_doctype']:
                doc.reference_doctype = metadata['reference_doctype']
            else:
                # Lấy tên thư mục chứa làm reference_doctype nếu không có trong metadata
                doc.reference_doctype = os.path.basename(os.path.dirname(file_path))
            
            # Thiết lập doctype_event nếu script_type là DocType Event
            if metadata['script_type'] == 'DocType Event':
                doc.doctype_event = metadata['doctype_event']
                
            doc.enabled = 1  # Mặc định là bật
            doc.insert()
            frappe.db.commit()
            
            ref_doctype = metadata['reference_doctype'] or os.path.basename(os.path.dirname(file_path))
            print(f" Đã tạo mới: {script_name} cho DocType: {ref_doctype}")
    
    except Exception as e:
        print(f"❌ Lỗi khi xử lý {os.path.basename(file_path)}: {e}")

'''
bench --site erp.tiqn.local console
import custom_features.custom_features.bulk_update_scripts.create_update_server_scripts as script
1. Create, update all file.py in all sub-folder of "server_scripts": 
    script.create_update_server_scripts()
2. Create, update all file.py in ONE sub-folder of "server_scripts": 
    script.create_update_server_scripts(reference_document_type="Item")
3. Create, update ONE file.py in ONE sub-folder of "server_scripts": 
    script.create_update_server_scripts(reference_document_type="Item", script_name="item_variants_after_insert") 
'''                