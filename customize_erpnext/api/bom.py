import frappe
import json
from frappe import _

@frappe.whitelist()
def copy_bom_for_same_color(doc):
    """
    Copy BOM for all items with the same variant_of and color attribute
    Args:
        doc: JSON string or dict containing BOM document data
    Returns:
        list of created BOMs
    """
    # Convert JSON string to dict if needed
    if isinstance(doc, str):
        doc = json.loads(doc)
        
    if not doc.get('item'):
        frappe.throw(_("Please select an item first"))
        
    # Get source item details
    source_item = frappe.get_doc("Item", doc['item'])
    if not source_item.variant_of:
        frappe.throw(_("Selected item must be a variant"))
        
    # Get color attribute from source item
    color = None
    for attr in source_item.attributes:
        if attr.attribute.lower() == "color":
            color = attr.attribute_value
            break
            
    if not color:
        frappe.throw(_("Source item must have color attribute"))
        
    # Find all items with same variant_of and color
    items = frappe.get_all("Item", 
        filters={
            "variant_of": source_item.variant_of,
            "disabled": 0,
            "name": ["!=", source_item.name]
        },
        fields=["name", "item_name"]
    )
    
    created_boms = []
    source_bom = frappe.get_doc("BOM", doc['name'])
    
    for item in items:
        # Check if item has same color
        item_doc = frappe.get_doc("Item", item.name)
        item_color = None
        
        for attr in item_doc.attributes:
            if attr.attribute.lower() == "color":
                item_color = attr.attribute_value
                break
                
        if item_color != color:
            continue 
            
        # Create new BOM
        new_bom = frappe.copy_doc(source_bom, ignore_no_copy=False)
        new_bom.item = item.name
        new_bom.custom_item_name_bom = item.item_name
        
        # Add warning intros for items marked as different
        for bom_item in new_bom.items:
            if bom_item.custom_is_difference:
                bom_item.intro = f"{bom_item.item_code}: {bom_item.item_name}: Need to review"
                bom_item.intro_color = "orange"
                
        new_bom.save()
        created_boms.append(new_bom.name)
        
    return created_boms
@frappe.whitelist()
def get_item_name_for_bom(item_code):
    """Get item name for BOM custom field"""
    if not item_code:
        return ""
    return frappe.db.get_value("Item", item_code, "item_name")
@frappe.whitelist()
def get_item_attribute(item_code):
    attributes = {}
    if item_code:
        variant_attributes = frappe.get_all(
            "Item Variant Attribute",
            filters={"parent": item_code},
            fields=["attribute", "attribute_value"]
        )
        
        for attr in variant_attributes:
            attributes[attr.attribute.lower()] = attr.attribute_value
            
    return attributes 
#get item attribute "season"    