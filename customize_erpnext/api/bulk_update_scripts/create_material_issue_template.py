import frappe
import os
import shutil

@frappe.whitelist()
def create_material_issue_template():
    """Trả về URL để download file Excel template Material Issue có sẵn."""
    try:
        # Đường dẫn đến file template có sẵn
        template_source_path = "/home/frappe/frappe-bench/apps/customize_erpnext/customize_erpnext/api/bulk_update_scripts/create_material_issue_teamplate.xlsx"
        
        # Kiểm tra file có tồn tại không
        if not os.path.exists(template_source_path):
            return {
                "success": False,
                "message": f"Template file not found at: {template_source_path}"
            }
        
        # Get site path và tạo thư mục public/files nếu chưa có
        site_path = frappe.get_site_path()
        public_files_dir = os.path.join(site_path, "public", "files")
        if not os.path.exists(public_files_dir):
            os.makedirs(public_files_dir)
        
        # Tên file đích
        template_filename = "import_material_issue_template.xlsx"
        template_dest_path = os.path.join(public_files_dir, template_filename)
        
        # Copy file template vào thư mục public/files
        shutil.copy2(template_source_path, template_dest_path)
        
        # Tạo URL để download
        file_url = f"/files/{template_filename}"
        
        return {
            "success": True,
            "file_url": file_url,
            "message": "Material Issue template is ready for download"
        }
        
    except Exception as e:
        frappe.log_error(f"Error serving Material Issue template: {str(e)}", "Material Issue Template Error")
        return {
            "success": False,
            "message": f"Error preparing template: {str(e)}"
        }

@frappe.whitelist()
def get_sample_items():
    """
    Lấy một số item mẫu để làm template
    """
    try:
        items = frappe.db.sql("""
            SELECT 
                item_code,
                custom_item_name_detail,
                item_name,
                stock_uom
            FROM `tabItem`
            WHERE custom_item_name_detail IS NOT NULL
            AND custom_item_name_detail != ''
            AND has_variants = 0
            ORDER BY modified DESC
            LIMIT 10
        """, as_dict=True)
        
        return {
            "success": True,
            "items": items
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": str(e)
        }

# Export functions
__all__ = [
    'create_material_issue_template',
    'get_sample_items'
]