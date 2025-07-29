
import frappe

def update_all_items_barcode():
    """
    One-time script to update all items barcode
    - Ensure only 1 barcode per item
    - Barcode = item_code
    - UOM = stock_uom
    - Barcode type = CODE-39
    """
    
    print("🚀 Starting barcode update for all items...")
    
    # Get all items (include variants, exclude templates)
    items = frappe.db.sql("""
        SELECT name, stock_uom, item_name
        FROM `tabItem` 
        WHERE disabled = 0
        ORDER BY name
    """, as_dict=True)
    
    print(f"📦 Found {len(items)} items to process")
    
    stats = {
        'processed': 0,
        'created': 0,
        'updated': 0,
        'cleaned': 0,
        'errors': 0
    }
    
    for i, item in enumerate(items, 1):
        try:
            item_code = item.name
            stock_uom = item.stock_uom
            
            print(f"[{i}/{len(items)}] Processing: {item_code}")
            
            # Get existing barcodes for this item
            existing_barcodes = frappe.db.sql("""
                SELECT name, barcode, uom, barcode_type
                FROM `tabItem Barcode`
                WHERE parent = %s
                ORDER BY creation
            """, item_code, as_dict=True)
            
            # Case 1: No barcode exists - CREATE
            if not existing_barcodes:
                frappe.db.sql("""
                    INSERT INTO `tabItem Barcode` 
                    (name, parent, parenttype, parentfield, idx, barcode, uom, barcode_type, 
                     creation, modified, owner, modified_by, docstatus)
                    VALUES (UUID(), %s, 'Item', 'barcodes', 1, %s, %s, 'CODE-39',
                     NOW(), NOW(), 'Administrator', 'Administrator', 0)
                """, (item_code, item_code, stock_uom))
                
                print(f"  ✅ Created new barcode: {item_code}")
                stats['created'] += 1
            
            # Case 2: Barcode exists - CHECK & UPDATE
            else:
                # Keep only first barcode, delete others
                if len(existing_barcodes) > 1:
                    for extra_barcode in existing_barcodes[1:]:
                        frappe.db.sql("DELETE FROM `tabItem Barcode` WHERE name = %s", extra_barcode.name)
                    print(f"  🧹 Cleaned {len(existing_barcodes)-1} duplicate barcodes")
                    stats['cleaned'] += len(existing_barcodes) - 1
                
                # Check if first barcode is correct
                first_barcode = existing_barcodes[0]
                needs_update = (
                    first_barcode.barcode != item_code or 
                    first_barcode.uom != stock_uom or 
                    first_barcode.barcode_type != 'CODE-39'
                )
                
                if needs_update:
                    frappe.db.sql("""
                        UPDATE `tabItem Barcode` 
                        SET barcode = %s, uom = %s, barcode_type = 'CODE-39', modified = NOW()
                        WHERE name = %s
                    """, (item_code, stock_uom, first_barcode.name))
                    
                    print(f"  🔄 Updated barcode: {item_code}")
                    stats['updated'] += 1
                else:
                    print(f"  ✅ Already correct: {item_code}")
            
            stats['processed'] += 1
            
            # Commit every 50 items
            if i % 50 == 0:
                frappe.db.commit()
                print(f"💾 Committed batch {i}")
                
        except Exception as e:
            print(f"  ❌ Error processing {item_code}: {str(e)}")
            stats['errors'] += 1
            continue
    
    # Final commit
    frappe.db.commit()
    
    # Print summary
    print("\n" + "="*60)
    print("📊 BARCODE UPDATE SUMMARY")
    print("="*60)
    print(f"Total processed: {stats['processed']}")
    print(f"New created: {stats['created']}")
    print(f"Updated: {stats['updated']}")
    print(f"Duplicates cleaned: {stats['cleaned']}")
    print(f"Errors: {stats['errors']}")
    print("="*60)
    print("✅ Barcode update completed!")
    
    return stats

# ====================================================================================
# VERIFICATION SCRIPT
# ====================================================================================

def verify_barcode_update():
    """Verify the barcode update results"""
    
    print("🔍 Verifying barcode update...")
    
    # Check for items without barcodes
    items_without_barcode = frappe.db.sql("""
        SELECT i.name 
        FROM `tabItem` i
        LEFT JOIN `tabItem Barcode` ib ON i.name = ib.parent
        WHERE i.disabled = 0 AND ib.parent IS NULL
        LIMIT 10
    """, as_dict=True)
    
    # Check for items with multiple barcodes
    items_multiple_barcodes = frappe.db.sql("""
        SELECT parent, COUNT(*) as count
        FROM `tabItem Barcode`
        GROUP BY parent
        HAVING COUNT(*) > 1
        LIMIT 10
    """, as_dict=True)
    
    # Check for incorrect barcodes
    incorrect_barcodes = frappe.db.sql("""
        SELECT ib.parent, ib.barcode, i.stock_uom, ib.uom, ib.barcode_type
        FROM `tabItem Barcode` ib
        JOIN `tabItem` i ON ib.parent = i.name
        WHERE (ib.barcode != ib.parent 
               OR ib.uom != i.stock_uom 
               OR ib.barcode_type != 'CODE-39')
        AND i.disabled = 0
        LIMIT 10
    """, as_dict=True)
    
    # Get total counts
    total_items = frappe.db.count('Item', {'disabled': 0})
    total_barcodes = frappe.db.count('Item Barcode')
    
    print(f"\n📈 VERIFICATION RESULTS:")
    print(f"Total active items: {total_items}")
    print(f"Total barcodes: {total_barcodes}")
    print(f"Items without barcode: {len(items_without_barcode)}")
    print(f"Items with multiple barcodes: {len(items_multiple_barcodes)}")
    print(f"Incorrect barcodes: {len(incorrect_barcodes)}")
    
    if items_without_barcode:
        print("\n❌ Items without barcode:")
        for item in items_without_barcode:
            print(f"  - {item.name}")
    
    if items_multiple_barcodes:
        print("\n⚠️ Items with multiple barcodes:")
        for item in items_multiple_barcodes:
            print(f"  - {item.parent} ({item.count} barcodes)")
    
    if incorrect_barcodes:
        print("\n🔧 Incorrect barcodes:")
        for item in incorrect_barcodes:
            print(f"  - {item.parent}: {item.barcode} (Type: {item.barcode_type}, UOM: {item.uom})")
    
    if not items_without_barcode and not items_multiple_barcodes and not incorrect_barcodes:
        print("\n✅ All barcodes are correct!")
    
    return {
        'total_items': total_items,
        'total_barcodes': total_barcodes,
        'missing': len(items_without_barcode),
        'duplicates': len(items_multiple_barcodes),
        'incorrect': len(incorrect_barcodes)
    }
 
update_all_items_barcode()