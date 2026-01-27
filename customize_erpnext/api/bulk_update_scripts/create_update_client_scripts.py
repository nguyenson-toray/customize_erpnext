import os
import frappe
from datetime import datetime

# Thư mục chứa các file script
SCRIPT_FOLDER_PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../client_scripts"))

def create_update_client_scripts(doc_type=None, script_name=None):
    """
    Cập nhật hoặc tạo mới Client Scripts từ thư mục client_scripts vào ERPNext.
    
    Parameters:
    doc_type (str, optional): Tên của document type. Mặc định là None.
    script_name (str, optional): Tên của script. Mặc định là None.
    
    Behavior:
    - Nếu doc_type=None & script_name=None: áp dụng cho toàn bộ file trong các thư mục con của SCRIPT_FOLDER_PARENT
    - Nếu doc_type!=None & script_name=None: áp dụng cho toàn bộ file trong SCRIPT_FOLDER
    - Nếu doc_type!=None & script_name!=None: áp dụng cho file script_name.js trong SCRIPT_FOLDER.
      Nếu chưa tồn tại script_name trên database thì thực hiện tạo mới
    """
    
    # Trường hợp 1: Quét các thư mục con của thư mục gốc, bỏ qua các file trong thư mục gốc
    if doc_type is None and script_name is None:
        print(f"📂 Đang quét các thư mục con của: {SCRIPT_FOLDER_PARENT}")
        
        # Đếm tổng số file sẽ xử lý để hiển thị xác nhận (không tính các file trực tiếp trong SCRIPT_FOLDER_PARENT)
        total_files = count_js_files_in_subdirectories(SCRIPT_FOLDER_PARENT)
        
        if total_files == 0:
            print(" Không tìm thấy file .js nào trong các thư mục con.")
            return
        
        if not confirm_operation(f"Sẽ xử lý {total_files} file script trong tất cả các thư mục con. Tiếp tục?"):
            print("❌ Đã hủy thao tác.")
            return
        
        # Lấy danh sách các thư mục con (đại diện cho các doc_type)
        subdirs = [d for d in os.listdir(SCRIPT_FOLDER_PARENT) 
                  if os.path.isdir(os.path.join(SCRIPT_FOLDER_PARENT, d))]
        
        if not subdirs:
            print(" Không tìm thấy thư mục con nào trong thư mục gốc.")
            return
        
        for sub_folder in subdirs:
            # Đệ quy gọi hàm này với doc_type là tên thư mục con, nhưng không cần xác nhận lại
            create_update_client_scripts_without_confirmation(doc_type=sub_folder)
        
        print(" Đã hoàn thành xử lý toàn bộ thư mục con.")
        return
    
    # Trường hợp 2 và 3: doc_type đã được chỉ định
    SCRIPT_FOLDER = os.path.join(SCRIPT_FOLDER_PARENT, doc_type)
    
    if not os.path.exists(SCRIPT_FOLDER):
        print(f"❌ Thư mục không tồn tại: {SCRIPT_FOLDER}")
        return
    
    # Trường hợp 3: Xử lý một file cụ thể
    if script_name is not None:
        file_name = f"{script_name}.js"
        file_path = os.path.join(SCRIPT_FOLDER, file_name)
        
        if not os.path.exists(file_path):
            print(f"❌ File không tồn tại: {file_path}")
            return
        
        process_script_file(file_path, script_name, doc_type)
        return
    
    # Trường hợp 2: Xử lý tất cả các file trong thư mục
    js_files = [f for f in os.listdir(SCRIPT_FOLDER) if f.endswith(".js")]
    if not js_files:
        print(f" Không có file .js nào trong thư mục: {SCRIPT_FOLDER}")
        return
    
    if not confirm_operation(f"Sẽ xử lý {len(js_files)} file script trong thư mục {doc_type}. Tiếp tục?"):
        print("❌ Đã hủy thao tác.")
        return
    
    print(f"📂 Đang quét thư mục: {SCRIPT_FOLDER}")
    
    for file_name in js_files:
        file_path = os.path.join(SCRIPT_FOLDER, file_name)
        script_name = file_name.replace(".js", "")
        
        process_script_file(file_path, script_name, doc_type)

def create_update_client_scripts_without_confirmation(doc_type):
    """
    Phiên bản không yêu cầu xác nhận của hàm chính, dùng cho xử lý đệ quy các thư mục con
    sau khi đã xác nhận ở cấp cao nhất.
    """
    SCRIPT_FOLDER = os.path.join(SCRIPT_FOLDER_PARENT, doc_type)
    
    if not os.path.exists(SCRIPT_FOLDER):
        print(f"❌ Thư mục không tồn tại: {SCRIPT_FOLDER}")
        return
    
    print(f"📂 Đang quét thư mục: {SCRIPT_FOLDER}")
    
    for file_name in os.listdir(SCRIPT_FOLDER):
        if file_name.endswith(".js"):
            file_path = os.path.join(SCRIPT_FOLDER, file_name)
            script_name = file_name.replace(".js", "")
            
            process_script_file(file_path, script_name, doc_type)

def count_js_files_in_subdirectories(folder_path):
    """
    Đếm số lượng file .js trong các thư mục con, bỏ qua các file trực tiếp trong thư mục gốc
    """
    count = 0
    # Lặp qua các mục trong thư mục gốc
    for item in os.listdir(folder_path):
        item_path = os.path.join(folder_path, item)
        # Chỉ xử lý các thư mục, bỏ qua file
        if os.path.isdir(item_path):
            # Đếm các file .js trong thư mục con này và các thư mục con của nó
            for root, dirs, files in os.walk(item_path):
                count += sum(1 for f in files if f.endswith('.js'))
    return count

def confirm_operation(message):
    """
    Hiển thị thông báo xác nhận và trả về True nếu người dùng đồng ý, ngược lại trả về False
    """
    response = input(f"\n {message} (y/n): ")
    return response.lower() in ['y', 'yes']

def process_script_file(file_path, script_name, doc_type):
    """
    Xử lý một file script: đọc nội dung và cập nhật hoặc tạo mới trong database
    
    Parameters:
    file_path (str): Đường dẫn đến file script
    script_name (str): Tên của script (không bao gồm phần mở rộng .js)
    doc_type (str): Tên của document type
    """
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            script_content = file.read()
        
        file_name = os.path.basename(file_path)
        print(f"📄 Đọc file: {file_name}")
        
        # Thêm thời gian vào script trước khi update hoặc tạo mới
        updated_script = f"// Updated at {datetime.now()}\n" + script_content
        
        # Kiểm tra script có tồn tại trong DB không
        existing_script = frappe.get_value("Client Script", script_name, "name")
        
        if existing_script:
            # Cập nhật script vào DB
            frappe.db.set_value("Client Script", script_name, "script", updated_script)
            frappe.db.commit()
            print(f" Đã cập nhật: {script_name}")
        else:
            # Tạo mới Client Script
            doc = frappe.new_doc("Client Script")
            doc.dt = doc_type  # Sử dụng doc_type được truyền vào
            doc.name = script_name
            doc.script = updated_script
            doc.enabled = 1  # Mặc định là bật
            doc.insert()
            frappe.db.commit()
            print(f" Đã tạo mới: {script_name} cho DocType: {doc_type}")
    
    except Exception as e:
        print(f"❌ Lỗi khi xử lý {os.path.basename(file_path)}: {e}")

'''
bench --site erp.tiqn.local console
import custom_features.custom_features.bulk_update_scripts.create_update_client_scripts as script
1. Create, update all file.js in all sub-folder of "client_scripts": 
    script.create_update_client_scripts()
2. Create, update all file.js in ONE sub-folder of "client_scripts": 
    script.create_update_client_scripts(doc_type="Item")
3. Create, update ONE file.js in ONE sub-folder of "client_scripts": 
    script.create_update_client_scripts(doc_type="Item", script_name="create_new_item") 
'''        