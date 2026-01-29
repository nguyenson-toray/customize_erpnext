# Site Restriction Module

## Overview
Decorator system to restrict function execution to specific sites only (e.g., production site `erp.tiqn.local`).

**Module Location:** `customize_erpnext/api/site_restriction.py`
**Last Updated:** 2025-11-14

---

## Usage

### 1. Import the decorator
```python
from customize_erpnext.api.site_restriction import only_for_sites
```

### 2. Apply to your function
The decorator can be used with specific site names or without arguments to use a default list.

**Example 1: Restrict to one or more specific sites**
```python
@only_for_sites("erp.tiqn.local", "erp-test.tiqn.local")
def my_function(doc, method=None):
    # This only runs on erp.tiqn.local and erp-test.tiqn.local
    # Other sites will bypass silently
    pass
```

**Example 2: Use the default allowed sites list**
```python
@only_for_sites()
def my_function(doc, method=None):
    # This function runs only on sites listed in ALLOWED_SITES
    pass
```

### 3. Manual check inside a function
For more complex logic, you can check manually.
```python
from customize_erpnext.api.site_restriction import is_allowed_site

def my_function(doc, method=None):
    if not is_allowed_site("erp.tiqn.local"):
        return
    # Your code here
```

---

## Configuration

### Configure Allowed Sites
Edit `customize_erpnext/api/site_restriction.py` to define the default list of allowed sites.
```python
ALLOWED_SITES = [
    "erp.tiqn.local",
    # Add more sites as needed
]
```

### Apply Changes
After modifying code, clear the cache and restart the bench.
```bash
bench --site erp.tiqn.local clear-cache
bench restart
```

---

## Functions Currently Protected

| Function | File | Location |
|----------|------|----------|
| `send_daily_check_in_report()` | daily_check_in_report/scheduler.py | Line 13 |
| `send_sunday_overtime_alert_scheduled()` | daily_timesheet/scheduler.py | Line 1050 |
| `monthly_timesheet_recalculation()` | daily_timesheet/scheduler.py | Line 285 |
| `sync_employee_to_mongodb()` | api/employee/erpnext_mongodb.py | Line 124 |
| `delete_employee_from_mongodb()` | api/employee/erpnext_mongodb.py | Line 184 |

---

## Testing Guide (Hướng dẫn kiểm tra)

When a function with the `@only_for_sites()` decorator is called on a non-allowed site, it will **return `None` silently** and will not execute. It only logs a debug message.

### Complete Test Script
You can use the following script in `bench console` to verify the behavior on your current site.

```python
# ============================================================================
# COMPLETE TEST SCRIPT - Copy and paste this entire block into bench console
# ============================================================================

import frappe
from customize_erpnext.api.site_restriction import is_allowed_site
from customize_erpnext.api.employee.erpnext_mongodb import sync_employee_to_mongodb

def test_site_restriction():
    """Test if site restriction is working correctly."""

    print("\n" + "="*70)
    print("SITE RESTRICTION TEST")
    print("="*70)

    # 1. Check current site
    current_site = frappe.local.site
    print(f"\n1. Current Site: {current_site}")

    # 2. Check permissions
    is_production = current_site == "erp.tiqn.local"
    is_allowed_prod = is_allowed_site("erp.tiqn.local")
    is_in_allowed_list = is_allowed_site()

    print(f"2. Site Check:")
    print(f"   - Is production site (erp.tiqn.local): {is_production}")
    print(f"   - Is allowed for production: {is_allowed_prod}")
    print(f"   - Is in ALLOWED_SITES list: {is_in_allowed_list}")

    # 3. Test a restricted function
    print(f"\n3. Testing sync_employee_to_mongodb():")
    try:
        # Replace with a valid employee for your site if needed
        emp = frappe.get_doc("Employee", "TIQN-0148")
        print(f"   Employee: {emp.name} - {emp.employee_name}")

        # Call the restricted function
        result = sync_employee_to_mongodb(emp)

        # Analyze the result
        if result is None:
            if not is_production:
                print(f"\n   ❌ BYPASSED - Function did not run.")
                print(f"      Reason: Current site '{current_site}' is not 'erp.tiqn.local'.")
                print(f"      This is EXPECTED behavior on dev/test sites.")
            else:
                print(f"\n   ✅ EXECUTED - Function ran successfully.")
                print(f"      (No output is normal - check MongoDB to verify sync).")
        else:
            print(f"\n   Result: {result}")

    except Exception as e:
        print(f"\n   ❌ ERROR: {str(e)}")

    # 4. Summary
    print(f"\n{'='*70}")
    print("SUMMARY:")
    if is_production:
        print("✅ You are on a PRODUCTION site - restricted functions will RUN.")
    else:
        print("🚫 You are on a DEV/TEST site - restricted functions will be BYPASSED.")
    print("="*70 + "\n")

# Run the test
test_site_restriction()
```

### Expected Output

#### On a production site (`erp.tiqn.local`):
```
======================================================================
SITE RESTRICTION TEST
======================================================================

1. Current Site: erp.tiqn.local
2. Site Check:
   - Is production site (erp.tiqn.local): True
   - Is allowed for production: True
   - Is in ALLOWED_SITES list: True

3. Testing sync_employee_to_mongodb():
   Employee: TIQN-0148 - Nguyễn Văn A

   ✅ EXECUTED - Function ran successfully
      (No output is normal - check MongoDB to verify sync)

======================================================================
SUMMARY:
✅ You are on PRODUCTION site - functions will RUN
======================================================================
```

#### On a development or test site:
```
======================================================================
SITE RESTRICTION TEST
======================================================================

1. Current Site: erp-sonnt.tiqn.local
2. Site Check:
   - Is production site (erp.tiqn.local): False
   - Is allowed for production: False
   - Is in ALLOWED_SITES list: False

3. Testing sync_employee_to_mongodb():
   Employee: TIQN-0148 - Nguyễn Văn A

   ❌ BYPASSED - Function did not run
      Reason: Current site 'erp-sonnt.tiqn.local' is not 'erp.tiqn.local'
      This is EXPECTED behavior on dev/test sites

======================================================================
SUMMARY:
🚫 You are on DEV/TEST site - restricted functions will BYPASS
======================================================================
```

### Quick Check
To quickly check your current site's status:
```python
import frappe
from customize_erpnext.api.site_restriction import is_allowed_site
print(f"Site: {frappe.local.site} | Allowed for 'erp.tiqn.local': {is_allowed_site('erp.tiqn.local')}")
```

### View Debug Logs
To see the debug message when a function is bypassed, you can tail the logs:
```bash
# In your terminal
tail -f logs/frappe.log | grep "Skipping"
```

---

## Advanced Examples (Ví dụ nâng cao)
This section contains more examples of how to apply site restrictions.

```python
# -*- coding: utf-8 -*-
"""
This file contains examples of how to apply site checks
to only allow events to run on specific sites.
"""

import frappe
from customize_erpnext.api.site_restriction import only_for_sites, is_allowed_site


# ============================================================================
# EXAMPLE 1: Using the decorator (RECOMMENDED)
# ============================================================================

@only_for_sites("erp.tiqn.local")
def example_on_checkin_update(doc, method):
	"""
	Event handler that ONLY runs on erp.tiqn.local.
	Other sites will be bypassed automatically.
	"""
	frappe.logger().info(f"Processing checkin for {doc.name}")
	# Your code here
	pass


@only_for_sites("erp.tiqn.local", "erp-sonnt.tiqn.local")
def example_on_employee_update(doc, method):
	"""
	Event handler that runs on two sites: erp.tiqn.local and erp-sonnt.tiqn.local.
	"""
	frappe.logger().info(f"Processing employee {doc.name}")
	# Your code here
	pass


@only_for_sites()  # Uses the default ALLOWED_SITES
def example_on_shift_update(doc, method):
	"""
	Event handler that runs on sites listed in the default ALLOWED_SITES.
	"""
	frappe.logger().info(f"Processing shift update for {doc.name}")
	# Your code here
	pass


# ============================================================================
# EXAMPLE 2: Manual check for complex logic
# ============================================================================

def example_complex_logic(doc, method):
	"""
	Example with more complex logic.
	"""
	# Method 1: Direct check
	if frappe.local.site != "erp.tiqn.local":
		frappe.logger().debug(f"Skipping on site: {frappe.local.site}")
		return

	# Your code here
	frappe.logger().info(f"Processing on allowed site: {frappe.local.site}")


def example_with_helper_function(doc, method):
	"""
	Using the is_allowed_site() helper function.
	"""
	# Check for a specific site
	if not is_allowed_site("erp.tiqn.local"):
		return

	# Or check against the default ALLOWED_SITES list
	if not is_allowed_site():
		return

	# Your code here
	pass


# ============================================================================
# EXAMPLE 3: Conditional logic for different sites
# ============================================================================

def example_conditional_logic(doc, method):
	"""
	Example: Run different logic for different sites.
	"""
	current_site = frappe.local.site

	if current_site == "erp.tiqn.local":
		# Logic for production site
		frappe.logger().info("Running production logic")
		# do_production_sync(doc)

	elif current_site == "erp-sonnt.tiqn.local":
		# Logic for dev site
		frappe.logger().info("Running dev/test logic")
		# do_test_sync(doc)

	else:
		# Bypass for other sites
		frappe.logger().debug(f"Skipping on site: {current_site}")
		return


# ============================================================================
# EXAMPLE 4: Applying to existing event handlers in hooks.py
# ============================================================================

"""
You do NOT need to change hooks.py!

Just add the decorator to the event handler functions themselves.

EXAMPLE:

# hooks.py (REMAINS UNCHANGED)
doc_events = {
    "Employee Checkin": {
        "on_update": [
            "customize_erpnext.customize_erpnext.doctype.daily_timesheet.scheduler.auto_sync_on_checkin_update",
        ]
    }
}

# scheduler.py (ADD THE DECORATOR)
from customize_erpnext.api.site_restriction import only_for_sites

@only_for_sites("erp.tiqn.local")
def auto_sync_on_checkin_update(doc, method):
	# Existing code here
	pass
"""