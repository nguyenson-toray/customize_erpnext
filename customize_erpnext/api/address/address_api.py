import frappe
import json
import os


@frappe.whitelist()
def get_provinces():
    """
    Get all provinces from province.json
    Returns list of provinces with name_with_type only (no code)
    """
    try:
        file_path = os.path.join(
            os.path.dirname(__file__),
            'province.json'
        )

        with open(file_path, 'r', encoding='utf-8') as f:
            provinces = json.load(f)

        # Convert to list format for select field - only name_with_type
        province_list = []
        for data in provinces.values():
            province_list.append(data.get('name_with_type'))

        # Sort alphabetically
        province_list.sort()

        return province_list

    except Exception as e:
        frappe.log_error(f"Error loading provinces: {str(e)}")
        return []


@frappe.whitelist()
def get_communes(province_name=None):
    """
    Get communes filtered by province_name (name_with_type)
    If province_name is None, return all communes

    Args:
        province_name: Parent province name_with_type to filter communes

    Returns:
        List of communes with name_with_type only (no code)
    """
    try:
        # First, get province code from province_name if provided
        province_code = None
        if province_name:
            province_code = get_province_code_by_name(province_name)

        file_path = os.path.join(
            os.path.dirname(__file__),
            'commune.json'
        )

        with open(file_path, 'r', encoding='utf-8') as f:
            communes = json.load(f)

        # Convert to list format for select field - only name_with_type
        commune_list = []
        for data in communes.values():
            # Filter by province_code if provided
            if province_code and data.get('parent_code') != str(province_code):
                continue

            commune_list.append(data.get('name_with_type', data.get('name')))

        # Sort alphabetically
        commune_list.sort()

        return commune_list

    except Exception as e:
        frappe.log_error(f"Error loading communes: {str(e)}")
        return []


def get_province_code_by_name(province_name):
    """
    Get province code by province name_with_type (internal helper function)

    Args:
        province_name: Province name_with_type to search for

    Returns:
        Province code or None
    """
    try:
        file_path = os.path.join(
            os.path.dirname(__file__),
            'province.json'
        )

        with open(file_path, 'r', encoding='utf-8') as f:
            provinces = json.load(f)

        # Search for province by name_with_type (exact match)
        for code, data in provinces.items():
            if data.get('name_with_type') == province_name:
                return code

        return None

    except Exception as e:
        frappe.log_error(f"Error getting province code: {str(e)}")
        return None
