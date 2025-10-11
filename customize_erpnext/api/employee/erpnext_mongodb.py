# -*- coding: utf-8 -*-
# Copyright (c) 2024, IT Team - TIQN and contributors
# For license information, please see license.txt

"""
ERPNext MongoDB Integration for Employee Sync
Automatically syncs Employee data from ERPNext to MongoDB
"""

from __future__ import unicode_literals
import frappe
from frappe import _
from pymongo import MongoClient, errors
from datetime import datetime

# MongoDB connection settings
MONGODB_HOST = "10.0.1.4"
MONGODB_PORT = 27017
MONGODB_DB = "tiqn"
MONGODB_COLLECTION = "Employee"

def get_mongodb_connection():
    """
    Get MongoDB connection and return collection
    Returns: MongoDB collection object or None if connection fails
    """
    try:
        client = MongoClient(
            host=MONGODB_HOST,
            port=MONGODB_PORT,
            serverSelectionTimeoutMS=5000,  # 5 second timeout
            connectTimeoutMS=5000
        )
        # Test connection
        client.server_info()
        db = client[MONGODB_DB]
        collection = db[MONGODB_COLLECTION]
        return collection, client
    except errors.ServerSelectionTimeoutError as e:
        frappe.log_error(
            message=f"MongoDB Connection Timeout: {str(e)}",
            title="MongoDB Connection Error"
        )
        return None, None
    except Exception as e:
        frappe.log_error(
            message=f"MongoDB Connection Error: {str(e)}",
            title="MongoDB Connection Error"
        )
        return None, None


def transform_employee_data(doc):
    """
    Transform ERPNext Employee document to MongoDB format

    Args:
        doc: ERPNext Employee document

    Returns:
        dict: Transformed data for MongoDB
    """
    # Gender mapping
    gender_map = {
        "Female": "F",
        "Male": "M"
    }

    # Status mapping
    status_map = {
        "Active": "Working",
        "Left": "Resigned"
    }

    # Department cleanup - remove " - TIQN" suffix
    department = doc.get("department") or ""
    if department:
        department = department.replace(" - TIQN", "").strip()

    # Handle relieving_date - if empty, use 2099-01-01
    relieving_date = doc.get("relieving_date")
    if not relieving_date:
        relieving_date = datetime(2099, 1, 1)
    else:
        # Convert string date to datetime if needed
        if isinstance(relieving_date, str):
            relieving_date = datetime.strptime(relieving_date, "%Y-%m-%d")

    # Handle other dates
    def convert_date(date_value):
        """Convert date to datetime object"""
        if not date_value:
            return None
        if isinstance(date_value, str):
            return datetime.strptime(date_value, "%Y-%m-%d")
        return date_value

    # Build MongoDB document with all fields from collection
    mongo_doc = {
        "empId": doc.get("name") or "",
        "name": doc.get("employee_name") or "",
        "gender": gender_map.get(doc.get("gender"), ""),
        "department": department,
        "group": doc.get("custom_group") or "",
        "section": doc.get("custom_section") or "",
        "position": doc.get("designation") or "",
        "level": doc.get("grade") or "",
        "workStatus": status_map.get(doc.get("status"), ""),
        "attFingerId": int(doc.get("attendance_device_id")) or 0,
        "dob": convert_date(doc.get("date_of_birth")),
        "joiningDate": convert_date(doc.get("date_of_joining")),
        "resignOn": relieving_date,
        # Additional fields from MongoDB collection
        "directIndirect": "",
        "lineTeam": doc.get("custom_group") or "",
        "sewingNonSewing": "",
        "supporting": ""
    }

    return mongo_doc


def sync_employee_to_mongodb(doc, method=None):
    """
    Sync Employee document to MongoDB
    Called by ERPNext hooks on Employee insert/update

    Args:
        doc: ERPNext Employee document
        method: Hook method name (after_insert, on_update, etc.)
    """
    try:
        collection, client = get_mongodb_connection()

        if collection is None:
            frappe.log_error(
                message=f"Failed to sync Employee {doc.name} to MongoDB - No connection",
                title="MongoDB Sync Failed"
            )
            return

        # Transform data
        mongo_doc = transform_employee_data(doc)

        # Check if employee exists in MongoDB
        existing = collection.find_one({"empId": doc.name})

        if existing:
            # Update existing document (don't update _id)
            result = collection.update_one(
                {"empId": doc.name},
                {"$set": mongo_doc}
            )
            frappe.logger().info(
                f"Updated Employee {doc.name} in MongoDB - Modified: {result.modified_count}"
            )
        else:
            # Get next _id value
            max_id_doc = collection.find_one(sort=[("_id", -1)])
            next_id = (max_id_doc["_id"] + 1) if max_id_doc else 1

            # Add _id to document
            mongo_doc["_id"] = next_id

            # Insert new document
            result = collection.insert_one(mongo_doc)
            frappe.logger().info(
                f"Inserted Employee {doc.name} to MongoDB - ID: {result.inserted_id}"
            )

        # Close connection
        if client is not None:
            client.close()

    except Exception as e:
        frappe.log_error(
            message=f"Error syncing Employee {doc.name} to MongoDB: {str(e)}\n{frappe.get_traceback()}",
            title="MongoDB Sync Error"
        )


def delete_employee_from_mongodb(doc, method=None):
    """
    Delete Employee document from MongoDB
    Called by ERPNext hooks on Employee deletion

    Args:
        doc: ERPNext Employee document
        method: Hook method name (on_trash, etc.)
    """
    try:
        collection, client = get_mongodb_connection()

        if collection is None:
            frappe.log_error(
                message=f"Failed to delete Employee {doc.name} from MongoDB - No connection",
                title="MongoDB Delete Failed"
            )
            return

        # Delete document
        result = collection.delete_one({"empId": doc.name})

        if result.deleted_count > 0:
            frappe.logger().info(
                f"Deleted Employee {doc.name} from MongoDB - Deleted: {result.deleted_count}"
            )
        else:
            frappe.logger().info(
                f"Employee {doc.name} not found in MongoDB for deletion"
            )

        # Close connection
        if client is not None:
            client.close()

    except Exception as e:
        frappe.log_error(
            message=f"Error deleting Employee {doc.name} from MongoDB: {str(e)}\n{frappe.get_traceback()}",
            title="MongoDB Delete Error"
        )


@frappe.whitelist()
def test_mongodb_connection():
    """
    Test MongoDB connection
    Can be called from frontend or console

    Returns:
        dict: Connection test results
    """
    try:
        collection, client = get_mongodb_connection()

        if collection is None:
            return {
                "success": False,
                "message": "Failed to connect to MongoDB"
            }

        # Test query
        count = collection.count_documents({})

        # Close connection
        if client is not None:
            client.close()

        return {
            "success": True,
            "message": f"Successfully connected to MongoDB. Collection has {count} documents.",
            "host": MONGODB_HOST,
            "port": MONGODB_PORT,
            "database": MONGODB_DB,
            "collection": MONGODB_COLLECTION,
            "document_count": count
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }


@frappe.whitelist()
def sync_all_employees():
    """
    Manually sync all active employees to MongoDB
    Useful for initial setup or bulk sync

    Returns:
        dict: Sync results
    """
    try:
        # Get all employees
        employees = frappe.get_all(
            "Employee",
            fields=["name"]
        )

        success_count = 0
        error_count = 0
        errors = []

        for emp in employees:
            try:
                doc = frappe.get_doc("Employee", emp.name)
                sync_employee_to_mongodb(doc)
                success_count += 1
            except Exception as e:
                error_count += 1
                errors.append(f"{emp.name}: {str(e)}")

        return {
            "success": True,
            "total": len(employees),
            "synced": success_count,
            "errors": error_count,
            "error_details": errors
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Error: {str(e)}"
        }
