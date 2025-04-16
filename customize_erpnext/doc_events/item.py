import frappe

def after_insert(doc, method=None):
    """
    This function is triggered after an Item is inserted
    """
    try:
        update_item_variant(doc)
        frappe.logger().info("Item After Insert script completed successfully")
    except Exception as e:
        frappe.logger().error(f"Error in Item After Insert script: {str(e)}")
        raise

def update_item_variant(doc):
    """Update item variant properties based on template item"""
    if not doc.variant_of:
        return  # Skip if not a variant
    
    # Lấy template item doc để lấy description
    template_item = frappe.get_doc("Item", doc.variant_of)
    template_description = template_item.description or ""
    
    # Lấy item group từ template
    item_group = template_item.item_group
    
    # Lấy danh sách Attribute Value để tạo variant_summary
    attribute_values = []
    for attr in doc.attributes or []:
        if attr.attribute_value:
            attribute_values.append(attr.attribute_value)
   
    # Xử lý item_name dựa trên item_group
    new_item_name = template_item.item_name
    custom_item_name_detail = template_item.item_name 
    custom_item_name_detail = f"{custom_item_name_detail} {' '.join(attribute_values)}"
    new_item_name = new_item_name.replace("Blank ", " ").strip()
    custom_item_name_detail = custom_item_name_detail.replace("Blank ", " ").strip() 
    
    # Cập nhật item_name
    doc.db_set('item_name', new_item_name, update_modified=False)
    frappe.logger().info(f"Set item_name to: {new_item_name}")
    
    # Cập nhật variant_summary
    doc.db_set('custom_item_name_detail', custom_item_name_detail, update_modified=False)               
    
    # Sao chép description từ template
    if template_description:
        doc.db_set('description', template_description, update_modified=False)
        frappe.logger().info("Copied description from template")
    
    # Sao chép custom_description_vietnamese từ template nếu có
    try:
        if template_item.custom_description_vietnamese:
            doc.db_set('custom_description_vietnamese', template_item.custom_description_vietnamese, update_modified=False)
            frappe.logger().info("Copied custom_description_vietnamese from template")
    except:
        # Trường không tồn tại hoặc không có giá trị, bỏ qua
        pass