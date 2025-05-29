# Copyright (c) 2025, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import flt
from erpnext.stock.utils import get_stock_balance


def execute(filters=None):
    if not filters:
        filters = {}
        
    # Nếu có sale order được chọn, lấy danh sách item templates liên quan
    if filters.get("sale_order"):
        item_templates = get_item_templates_from_sales_order(filters.get("sale_order"))
        filters["available_templates"] = item_templates
        
        # Extract item template name từ "name:label" format nếu cần
        item_template = extract_item_template(filters.get("item_template"))
        if item_template:
            filters["item_template"] = item_template
        
        # Nếu có item_template được chọn nhưng không nằm trong danh sách liên quan, thông báo lỗi
        if item_template and item_template not in item_templates:
            frappe.throw(_("Selected Item Template is not related to the chosen Sales Order"))

    columns = get_columns(filters)
    data = get_data(filters)

    return columns, data


def get_columns(filters=None):
    columns = [
        {
            "fieldname": "item_group",
            "fieldtype": "Link",
            "label": _("Item Group"),
            "options": "Item Group",
            "width": 120
        },
        {
            "fieldname": "item",
            "fieldtype": "Link",
            "label": _("Item"),
            "options": "Item",
            "width": 150
        },
        {
            "fieldname": "description",
            "fieldtype": "Data",
            "label": _("Description"),
            "width": 200
        },
        {
            "fieldname": "item_name",
            "fieldtype": "Data",
            "label": _("Item Name"),
            "width": 150
        },
        {
            "fieldname": "color",
            "fieldtype": "Data",
            "label": _("Color"),
            "width": 150
        },
        {
            "fieldname": "size",
            "fieldtype": "Data",
            "label": _("Size"),
            "width": 100
        },
        {
            "fieldname": "lost_percent",
            "fieldtype": "Float",
            "label": _("Lost Percent"),
            "width": 100,
            "precision": 2
        },
        {
            "fieldname": "quantity_require",
            "fieldtype": "Float",
            "label": _("Quantity Require"),
            "width": 120,
            "precision": 2
        },
        {
            "fieldname": "quantity_require_include_lost_percent",
            "fieldtype": "Float",
            "label": _("Qty Require Include Lost Percent"),
            "width": 200,
            "precision": 2
        },  
        {
            "fieldname": "quantity_available_in_stock",
            "fieldtype": "Float",
            "label": _("Qty Available in Stock"),
            "width": 150,
            "precision": 2
    }
    ]
    
 
    
    return columns


def get_data(filters):
    data = []
    
    # If no sale order and no item template, return empty data
    if not filters.get("sale_order") and not filters.get("item_template"):
        return data
        
    boms = get_boms_from_filters(filters)
    
    if not boms:
        return data
        
    items_data = {}
    
    # Kiểm tra xem custom field đã tồn tại chưa
    has_custom_lost = frappe.db.exists(
        "Custom Field",
        {"dt": "BOM Item", "fieldname": "custom_lost"}
    )
    
    # Kiểm tra có sử dụng with_percent_lost không
    with_percent_lost = filters.get("with_percent_lost", 1)
    
    for bom in boms:
        bom_items = get_bom_items(bom.name)
        parent_qty = get_parent_qty_from_filters(filters, bom.item)
        
        for item in bom_items:
            total_qty = flt(parent_qty) * flt(item.qty)
            
            # Lấy lost_percent từ custom field nếu có, nếu không thì mặc định là 0
            lost_percent = 0
            if has_custom_lost and hasattr(item, 'custom_lost'):
                lost_percent = flt(item.custom_lost) or 0
            
            # Tính toán quantity với lost percent
            if with_percent_lost:
                qty_with_lost = total_qty + (total_qty * lost_percent / 100)
            else:
                qty_with_lost = total_qty
                
            key = item.item_code
            
            if key in items_data:
                items_data[key]["quantity_require"] += total_qty
                if with_percent_lost:
                    items_data[key]["quantity_require_include_lost_percent"] += qty_with_lost
            else:
                # Lấy thông tin color, size và item_group
                color, size = get_item_attributes(item.item_code)
                item_group = get_item_group(item.item_code)
                
                default_warehouse = get_default_warehouse()
                stock_qty = 0
                if default_warehouse:
                    try:
                        stock_qty = get_stock_balance(item.item_code, default_warehouse)
                    except:
                        stock_qty = 0
                
                item_data = {
                    "item_group": item_group,
                    "item": item.item_code,
                    "description": item.description,
                    "item_name": item.item_name,
                    "color": color,
                    "size": size,
                    "lost_percent": lost_percent,
                    "quantity_require": total_qty,
                    "quantity_available_in_stock": stock_qty,
                    "with_percent_lost": with_percent_lost
                }
                
                # Only add lost percent quantity if the option is enabled
                if with_percent_lost:
                    item_data["quantity_require_include_lost_percent"] = qty_with_lost
                    
                items_data[key] = item_data
    
    # Convert the dictionary to a list for the report
    data = list(items_data.values())
    
    # Sort data by item code only (no grouping)
    data.sort(key=lambda x: x["item"])
    
    return data


def get_boms_from_filters(filters):
    if filters.get("sale_order") and not filters.get("item_template"):
        # Nếu chỉ có sale order thì lấy tất cả BOMs từ sale order (hiển thị toàn bộ nguyên phụ liệu)
        return get_boms_from_sales_order(filters)
    elif filters.get("sale_order") and filters.get("item_template"):
        # Nếu có cả sale order và item template
        if filters.get("color"):
            return get_boms_from_template_and_color(filters)
        else:
            return get_boms_from_template(filters)
    elif filters.get("item_template"):
        # Nếu chỉ có item template
        if filters.get("color"):
            return get_boms_from_template_and_color(filters)
        else:
            return get_boms_from_template(filters)
    
    return []


def get_boms_from_sales_order(filters):
    sales_order_items = frappe.get_all(
        "Sales Order Item",
        filters={"parent": filters.get("sale_order")},
        fields=["item_code", "qty"]
    )
    
    boms = []
    for item in sales_order_items:
        bom = frappe.get_all(
            "BOM",
            filters={
                "item": item.item_code,
                "is_active": 1,
                "is_default": 1
            },
            fields=["name", "item"]
        )
        
        if bom:
            boms.extend(bom)
    
    return boms


def get_boms_from_template_and_color(filters):
    # Extract item template name từ "name:label" format nếu cần
    item_template = extract_item_template(filters.get("item_template"))
    
    # If filters has available_templates and the current template is not in it, return empty
    if filters.get("available_templates") and item_template not in filters.get("available_templates"):
        return []
        
    # Lấy các variants của item template có color được chọn
    variant_items = frappe.db.sql("""
        SELECT i.name
        FROM `tabItem` i
        JOIN `tabItem Variant Attribute` iva ON i.name = iva.parent
        WHERE i.variant_of = %s
        AND iva.attribute = 'Color'
        AND iva.attribute_value = %s
    """, (item_template, filters.get("color")), as_dict=1)
    
    boms = []
    for item in variant_items:
        bom = frappe.get_all(
            "BOM",
            filters={
                "item": item.name,
                "is_active": 1,
                "is_default": 1
            },
            fields=["name", "item"]
        )
        
        if bom:
            boms.extend(bom)
    
    return boms


def get_boms_from_template(filters):
    # Extract item template name từ "name:label" format nếu cần
    item_template = extract_item_template(filters.get("item_template"))
    
    # If filters has available_templates and the current template is not in it, return empty
    if filters.get("available_templates") and item_template not in filters.get("available_templates"):
        return []
        
    variant_items = frappe.db.sql("""
        SELECT i.name
        FROM `tabItem` i
        WHERE i.variant_of = %s
    """, item_template, as_dict=1)
    
    boms = []
    for item in variant_items:
        bom = frappe.get_all(
            "BOM",
            filters={
                "item": item.name,
                "is_active": 1,
                "is_default": 1
            },
            fields=["name", "item"]
        )
        
        if bom:
            boms.extend(bom)
    
    return boms


def get_bom_items(bom_name):
    # Kiểm tra xem custom field đã tồn tại chưa
    has_custom_lost = frappe.db.exists(
        "Custom Field",
        {"dt": "BOM Item", "fieldname": "custom_lost"}
    )
    
    # Chuẩn bị danh sách trường cần lấy
    fields = ["item_code", "item_name", "description", "qty"]
    
    # Chỉ thêm custom_lost vào fields nếu nó tồn tại
    if has_custom_lost:
        fields.append("custom_lost")
    
    bom_items = frappe.get_all(
        "BOM Item",
        filters={"parent": bom_name},
        fields=fields
    )
    
    return bom_items


def get_parent_qty_from_filters(filters, item_code):
    if filters.get("sale_order"):
        sales_order_item = frappe.get_all(
            "Sales Order Item",
            filters={
                "parent": filters.get("sale_order"),
                "item_code": item_code
            },
            fields=["qty"]
        )
        
        if sales_order_item:
            return sales_order_item[0].qty
    
    return 1  # Default quantity if not specified


def get_default_warehouse():
    default_warehouse = frappe.db.get_single_value("Stock Settings", "default_warehouse")
    
    if not default_warehouse:
        # Fallback to a company's default warehouse if Stock Settings doesn't have one
        company = frappe.defaults.get_user_default("Company")
        if company:
            default_warehouse = frappe.db.get_value("Company", company, "default_warehouse")
    
    return default_warehouse


def get_item_attributes(item_code):
    """Get color and size attributes for an item"""
    attributes = frappe.db.sql("""
        SELECT attribute, attribute_value
        FROM `tabItem Variant Attribute`
        WHERE parent = %s AND attribute IN ('Color', 'Size')
    """, item_code, as_dict=1)
    
    color = ""
    size = ""
    
    for attr in attributes:
        if attr.attribute == "Color":
            color = attr.attribute_value
        elif attr.attribute == "Size":
            size = attr.attribute_value
    
    return color, size


def get_item_group(item_code):
    """Get item group for an item"""
    item_group = frappe.db.get_value("Item", item_code, "item_group")
    return item_group or ""

def extract_item_template(item_template_filter):
    """Extract item template name từ 'name:label' format nếu cần"""
    if item_template_filter and ":" in item_template_filter:
        return item_template_filter.split(":")[0]
    return item_template_filter

@frappe.whitelist()
def get_item_templates_from_sales_order(sales_order):
    """Get all B-Finished Goods item templates related to items in a sales order"""
    templates = frappe.db.sql("""
        SELECT DISTINCT i.variant_of as template
        FROM `tabSales Order Item` soi
        JOIN `tabItem` i ON soi.item_code = i.name
        WHERE soi.parent = %s 
        AND i.variant_of IS NOT NULL
        AND i.variant_of != ''
        AND i.is_sales_item = 1
        AND i.disabled = 0
        AND i.variant_of LIKE 'B-%%'
    """, sales_order, as_dict=1)
    
    return [t.template for t in templates if t.template]

@frappe.whitelist()
def get_filtered_item_templates(sales_order=None):
    """
    Get filtered item templates for Select field based on sales order
    Returns data formatted for ERPNext Select field
    """
    try:
        if sales_order:
            # Get item templates from specific sales order
            templates = get_item_templates_from_sales_order(sales_order)
            
            if not templates:
                return []
            
            # Get full item details for these templates
            item_details = frappe.db.sql("""
                SELECT 
                    item.name,
                    item.item_name,
                    item.description
                FROM `tabItem` item
                WHERE 
                    item.name IN %(templates)s
                    AND item.has_variants = 1
                    AND item.is_sales_item = 1
                    AND item.disabled = 0
                    AND item.name LIKE 'B-%%'
                ORDER BY item.item_name
            """, {
                'templates': templates
            }, as_dict=True)
            
            return item_details
            
        else:
            # Return all B-Finished Goods templates when no sales order
            item_details = frappe.db.sql("""
                SELECT 
                    item.name,
                    item.item_name,
                    item.description
                FROM `tabItem` item
                WHERE 
                    item.has_variants = 1
                    AND item.is_sales_item = 1
                    AND item.disabled = 0
                    AND item.name LIKE 'B-%%'
                ORDER BY item.item_name
                LIMIT 100
            """, as_dict=True)
            
            return item_details
            
    except Exception as e:
        frappe.log_error(f"Error in get_filtered_item_templates: {str(e)}")
        return []

@frappe.whitelist()
def get_filtered_item_templates_with_cache(sales_order=None):
    """
    Enhanced version with caching for better performance
    """
    cache_key = f"bom_item_templates_{sales_order or 'all'}"
    
    # Try to get from cache first (cache for 5 minutes)
    cached_result = frappe.cache().get_value(cache_key)
    if cached_result:
        return cached_result
    
    try:
        result = get_filtered_item_templates(sales_order)
        
        # Cache the result for 5 minutes
        frappe.cache().set_value(cache_key, result, expires_in_sec=300)
        
        return result
        
    except Exception as e:
        frappe.log_error(f"Error in get_filtered_item_templates_with_cache: {str(e)}")
        return []