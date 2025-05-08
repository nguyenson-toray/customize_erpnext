#!/usr/bin/env python
# -*- coding: utf-8 -*-
# export_import_site_db.py

import os
import frappe
import datetime

# Get the current script folder path
SCRIPT_FOLDER_PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../export_import_data_doctype_in_db"))


def export_sql():
    """
    Export DocType table data to SQL files.
    Each DocType's data is exported as a .sql file with INSERT statements.
    """
    print("Starting SQL export process...")
    print(f"Script folder: {SCRIPT_FOLDER_PARENT}")
    
    # Path to the file containing DocType names
    doctype_file_path = os.path.join(SCRIPT_FOLDER_PARENT, "doctype_list.txt")
    
    # Check if the file exists
    if not os.path.exists(doctype_file_path):
        print(f"Error: File {doctype_file_path} not found.")
        return
    
    # Read DocType names from file
    with open(doctype_file_path, 'r') as file:
        doctypes = [line.strip() for line in file if line.strip()]
    
    print(f"Found {len(doctypes)} DocTypes to export to SQL: {doctypes}")
    
    # Export each DocType
    for doctype in doctypes:
        try:
            # Get the table name for the DocType
            table_name = f"tab{doctype}"
            
            # Get table structure
            columns_info = frappe.db.sql(f"""
                SELECT column_name, data_type, column_default, is_nullable
                FROM information_schema.columns 
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position
            """, as_dict=True)
            
            if not columns_info:
                print(f"No table found for DocType: {doctype}")
                continue
            
            # Get column names
            column_names = [col['column_name'] for col in columns_info]
            
            # Get all data from the table
            data = frappe.db.sql(f"SELECT * FROM `{table_name}`", as_dict=True)
            if not data:
                print(f"No data found in table for DocType: {doctype} - table name: {table_name}")
                continue
            
            # Create SQL file
            sql_filename = os.path.join(SCRIPT_FOLDER_PARENT, f"{doctype.replace(' ', '_').lower()}.sql")
            
            with open(sql_filename, 'w') as sql_file:
                # Write header
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sql_file.write(f"-- SQL Export for DocType: {doctype}\n")
                sql_file.write(f"-- Generated on: {current_time}\n")
                sql_file.write(f"-- Table: {table_name}\n\n")
                
                # Add DROP TABLE IF EXISTS statement
                sql_file.write(f"DROP TABLE IF EXISTS `{table_name}`;\n\n")
                
                # Add table structure
                sql_file.write(f"-- Table structure\n")
                sql_file.write(f"CREATE TABLE `{table_name}` (\n")
                
                # Add columns with their data types
                column_defs = []
                primary_key = None
                for col in columns_info:
                    nullable = "NULL" if col['is_nullable'] == "YES" else "NOT NULL"
                    default = f"DEFAULT {col['column_default']}" if col['column_default'] is not None else ""
                    
                    # Adjust data type format
                    data_type = col['data_type']
                    if data_type in ['varchar', 'char']:
                        # Get character limit from frappe
                        max_length = frappe.db.sql(f"""
                            SELECT character_maximum_length 
                            FROM information_schema.columns 
                            WHERE table_name = '{table_name}' 
                            AND column_name = '{col['column_name']}'
                        """)[0][0]
                        data_type = f"{data_type}({max_length})"
                    
                    column_defs.append(f"  `{col['column_name']}` {data_type} {nullable} {default}")
                    
                    # Check if this is the primary key (usually 'name')
                    if col['column_name'] == 'name':
                        primary_key = col['column_name']
                
                sql_file.write(",\n".join(column_defs))
                
                # Add primary key
                if primary_key:
                    sql_file.write(f",\n  PRIMARY KEY (`{primary_key}`)")
                
                sql_file.write("\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;\n\n")
                
                # Write data as INSERT statements
                sql_file.write(f"-- Data for table `{table_name}`\n")
                sql_file.write(f"LOCK TABLES `{table_name}` WRITE;\n")
                sql_file.write(f"/*!40000 ALTER TABLE `{table_name}` DISABLE KEYS */;\n")
                
                # Process in batches of 100 to avoid huge INSERT statements
                batch_size = 100
                for i in range(0, len(data), batch_size):
                    batch = data[i:i+batch_size]
                    
                    # Start INSERT statement
                    sql_file.write(f"INSERT INTO `{table_name}` (`")
                    sql_file.write("`, `".join(column_names))
                    sql_file.write("`) VALUES\n")
                    
                    # Add values
                    value_strings = []
                    for row in batch:
                        values = []
                        for col in column_names:
                            val = row.get(col)
                            if val is None:
                                values.append("NULL")
                            elif isinstance(val, (int, float)):
                                values.append(str(val))
                            elif isinstance(val, datetime.datetime):
                                values.append(f"'{val.strftime('%Y-%m-%d %H:%M:%S')}'")
                            elif isinstance(val, datetime.date):
                                values.append(f"'{val.strftime('%Y-%m-%d')}'")
                            else:
                                # Escape single quotes in string values
                                escaped_val = str(val).replace("'", "''")
                                values.append(f"'{escaped_val}'")
                        
                        value_strings.append(f"({', '.join(values)})")
                    
                    sql_file.write(",\n".join(value_strings))
                    sql_file.write(";\n")
                
                sql_file.write("/*!40000 ALTER TABLE `{table_name}` ENABLE KEYS */;\n")
                sql_file.write("UNLOCK TABLES;\n\n")
            
            print(f"Exported SQL for DocType: {doctype} with {len(data)} records to {sql_filename}")
            
        except Exception as e:
            print(f"Error exporting SQL for DocType {doctype}: {str(e)}")
    
    print("SQL export process completed.")


def import_sql():
    """
    Import data from SQL files into the current site's database.
    """
    print("Starting SQL import process...")
    print(f"Script folder: {SCRIPT_FOLDER_PARENT}")
    
    # Path to the file containing DocType names
    doctype_file_path = os.path.join(SCRIPT_FOLDER_PARENT, "doctype_list.txt")
    
    # Check if the file exists
    if not os.path.exists(doctype_file_path):
        print(f"Error: File {doctype_file_path} not found.")
        return
    
    # Read DocType names from file
    with open(doctype_file_path, 'r') as file:
        doctypes = [line.strip() for line in file if line.strip()]
    
    print(f"Found {len(doctypes)} DocTypes to import from SQL.")
    
    # Import each DocType
    for doctype in doctypes:
        try:
            # Get the table name for the DocType
            table_name = f"tab{doctype}"
            
            # Prepare SQL filename
            sql_filename = os.path.join(SCRIPT_FOLDER_PARENT, f"{doctype.replace(' ', '_').lower()}.sql")
            
            if not os.path.exists(sql_filename):
                print(f"Warning: SQL file {sql_filename} not found. Skipping DocType: {doctype}")
                continue
            
            # Read SQL file
            with open(sql_filename, 'r') as f:
                sql_content = f.read()
            
            if not sql_content:
                print(f"No SQL commands found in file {sql_filename}. Skipping DocType: {doctype}")
                continue
            
            print(f"Importing SQL for DocType: {doctype}")
            
            # Drop existing table if needed
            frappe.db.sql(f"DROP TABLE IF EXISTS `{table_name}`")
            
            # Execute SQL commands - we'll need to split by semicolons
            # This approach is simplified and might not handle all SQL scenarios
            statements = []
            current_statement = ""
            
            # Split SQL into statements, handling multiline issues
            for line in sql_content.split('\n'):
                if line.strip().startswith('--'):
                    continue  # Skip comment lines
                
                current_statement += line + "\n"
                
                if line.strip().endswith(';'):
                    statements.append(current_statement.strip())
                    current_statement = ""
            
            # Add any remaining statement
            if current_statement.strip():
                statements.append(current_statement.strip())
            
            # Execute each statement
            for stmt in statements:
                if not stmt.strip():
                    continue
                
                try:
                    frappe.db.sql(stmt)
                except Exception as e:
                    print(f"Error executing SQL statement: {str(e)}")
                    print(f"Statement preview: {stmt[:100]}...")
                    raise
            
            # Commit changes
            frappe.db.commit()
            
            print(f"Successfully imported SQL for DocType: {doctype}")
            
        except Exception as e:
            # Rollback transaction if error occurs
            frappe.db.rollback()
            print(f"Error importing SQL for DocType {doctype}: {str(e)}")
    
    print("SQL import process completed.")


if __name__ == "__main__":
    # This block allows running the script directly
    import argparse
    
    parser = argparse.ArgumentParser(description='Export or import DocType SQL data')
    parser.add_argument('action', choices=['export', 'import'], 
                        help='Action to perform: export or import SQL data')
    
    args = parser.parse_args()
    
    if args.action == 'export':
        export_sql()
    elif args.action == 'import':
        import_sql()


# doctype_list.txt : Every Doctype in a line
# For use in bench console:
# bench --site [site-name] console
#
# Example usage:
# import customize_erpnext.api.export_import_data_doctype_in_db.export_import_data_doctype_in_db as script
# script.export_sql()  # To export data from current site
# script.import_sql()  # To import data to current site

