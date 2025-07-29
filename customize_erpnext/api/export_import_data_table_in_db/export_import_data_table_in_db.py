#!/usr/bin/env python
# -*- coding: utf-8 -*-
# export_import_table_db.py

import os
import frappe
import datetime
import json

# Get the current script folder path
SCRIPT_FOLDER_PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../export_import_data_table_in_db"))


def export_sql():
    """
    Export database table data to SQL files.
    Each table's data is exported as a .sql file with INSERT statements.
    """
    print("Starting SQL table export process...")
    print(f"Script folder: {SCRIPT_FOLDER_PARENT}")
    
    # Path to the file containing table names
    table_file_path = os.path.join(SCRIPT_FOLDER_PARENT, "table_list.txt")
    
    # Check if the file exists
    if not os.path.exists(table_file_path):
        print(f"Error: File {table_file_path} not found.")
        print("Please create table_list.txt with one table name per line.")
        print("Example content:")
        print("tabList View Settings")
        print("tabUser Settings")
        print("tabCustom Field")
        return
    
    # Read table names from file
    with open(table_file_path, 'r') as file:
        tables = [line.strip() for line in file if line.strip()]
    
    print(f"Found {len(tables)} tables to export to SQL: {tables}")
    
    # Create export directory if not exists
    os.makedirs(SCRIPT_FOLDER_PARENT, exist_ok=True)
    
    # Export each table
    for table_name in tables:
        try:
            # Check if table exists
            table_exists = frappe.db.sql(f"""
                SELECT COUNT(*) as count 
                FROM information_schema.tables 
                WHERE table_name = '{table_name}' 
                AND table_schema = DATABASE()
            """, as_dict=True)
            
            if not table_exists or table_exists[0]['count'] == 0:
                print(f"Table not found: {table_name}")
                continue
            
            # Get table structure
            columns_info = frappe.db.sql(f"""
                SELECT column_name, data_type, column_default, is_nullable, 
                       character_maximum_length, column_key, extra
                FROM information_schema.columns 
                WHERE table_name = '{table_name}' 
                AND table_schema = DATABASE()
                ORDER BY ordinal_position
            """, as_dict=True)
            
            if not columns_info:
                print(f"No columns found for table: {table_name}")
                continue
            
            # Get column names
            column_names = [col['column_name'] for col in columns_info]
            
            # Get all data from the table
            data = frappe.db.sql(f"SELECT * FROM `{table_name}`", as_dict=True)
            if not data:
                print(f"No data found in table: {table_name}")
                # Still create empty SQL file for structure
            
            # Create SQL file
            safe_table_name = table_name.replace(' ', '_').replace('`', '').lower()
            sql_filename = os.path.join(SCRIPT_FOLDER_PARENT, f"{safe_table_name}.sql")
            
            with open(sql_filename, 'w', encoding='utf-8') as sql_file:
                # Write header
                current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sql_file.write(f"-- SQL Export for Table: {table_name}\n")
                sql_file.write(f"-- Generated on: {current_time}\n")
                sql_file.write(f"-- Records: {len(data)}\n\n")
                
                # Add SET statements for safety
                sql_file.write("SET SQL_MODE = \"NO_AUTO_VALUE_ON_ZERO\";\n")
                sql_file.write("SET AUTOCOMMIT = 0;\n")
                sql_file.write("START TRANSACTION;\n")
                sql_file.write("SET time_zone = \"+00:00\";\n\n")
                
                # Add DROP TABLE IF EXISTS statement
                sql_file.write(f"DROP TABLE IF EXISTS `{table_name}`;\n\n")
                
                # Add table structure
                sql_file.write(f"-- Table structure for `{table_name}`\n")
                sql_file.write(f"CREATE TABLE `{table_name}` (\n")
                
                # Add columns with their data types
                column_defs = []
                primary_keys = []
                auto_increment_col = None
                
                for col in columns_info:
                    nullable = "NULL" if col['is_nullable'] == "YES" else "NOT NULL"
                    default = ""
                    
                    # Handle default values
                    if col['column_default'] is not None:
                        if col['data_type'] in ['varchar', 'text', 'char', 'longtext']:
                            default = f"DEFAULT '{col['column_default']}'"
                        else:
                            default = f"DEFAULT {col['column_default']}"
                    
                    # Handle data types
                    data_type = col['data_type'].upper()
                    if col['character_maximum_length'] and data_type in ['VARCHAR', 'CHAR']:
                        data_type = f"{data_type}({col['character_maximum_length']})"
                    elif data_type == 'TEXT':
                        pass  # TEXT doesn't need length
                    elif data_type == 'LONGTEXT':
                        pass  # LONGTEXT doesn't need length
                    elif data_type in ['INT', 'BIGINT']:
                        data_type = f"{data_type}(11)"
                    
                    # Handle AUTO_INCREMENT
                    extra = ""
                    if col['extra'] and 'auto_increment' in col['extra'].lower():
                        extra = "AUTO_INCREMENT"
                        auto_increment_col = col['column_name']
                    
                    column_def = f"  `{col['column_name']}` {data_type}"
                    if nullable != "NULL":
                        column_def += f" {nullable}"
                    if default:
                        column_def += f" {default}"
                    if extra:
                        column_def += f" {extra}"
                    
                    column_defs.append(column_def)
                    
                    # Check for primary key
                    if col['column_key'] == 'PRI':
                        primary_keys.append(col['column_name'])
                
                sql_file.write(",\n".join(column_defs))
                
                # Add primary key
                if primary_keys:
                    sql_file.write(f",\n  PRIMARY KEY (`{'`, `'.join(primary_keys)}`)")
                
                sql_file.write("\n) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;\n\n")
                
                # Write data as INSERT statements if data exists
                if data:
                    sql_file.write(f"-- Data for table `{table_name}`\n")
                    sql_file.write(f"LOCK TABLES `{table_name}` WRITE;\n")
                    sql_file.write(f"/*!40000 ALTER TABLE `{table_name}` DISABLE KEYS */;\n\n")
                    
                    # Process in batches to avoid huge INSERT statements
                    batch_size = 50
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
                                    # Escape single quotes and backslashes in string values
                                    escaped_val = str(val).replace("\\", "\\\\").replace("'", "\\'")
                                    values.append(f"'{escaped_val}'")
                            
                            value_strings.append(f"({', '.join(values)})")
                        
                        sql_file.write(",\n".join(value_strings))
                        sql_file.write(";\n\n")
                    
                    sql_file.write(f"/*!40000 ALTER TABLE `{table_name}` ENABLE KEYS */;\n")
                    sql_file.write(f"UNLOCK TABLES;\n\n")
                else:
                    sql_file.write(f"-- No data to insert for table `{table_name}`\n\n")
                
                # Reset AUTO_INCREMENT if needed
                if auto_increment_col and data:
                    max_id = max(row.get(auto_increment_col, 0) for row in data if row.get(auto_increment_col))
                    sql_file.write(f"ALTER TABLE `{table_name}` AUTO_INCREMENT = {max_id + 1};\n")
                
                sql_file.write("COMMIT;\n")
            
            print(f"Exported SQL for table: {table_name} with {len(data)} records to {sql_filename}")
            
        except Exception as e:
            print(f"Error exporting SQL for table {table_name}: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("SQL table export process completed.")


def import_sql():
    """
    Import data from SQL files into the current site's database.
    """
    print("Starting SQL table import process...")
    print(f"Script folder: {SCRIPT_FOLDER_PARENT}")
    
    # Path to the file containing table names
    table_file_path = os.path.join(SCRIPT_FOLDER_PARENT, "table_list.txt")
    
    # Check if the file exists
    if not os.path.exists(table_file_path):
        print(f"Error: File {table_file_path} not found.")
        return
    
    # Read table names from file
    with open(table_file_path, 'r') as file:
        tables = [line.strip() for line in file if line.strip()]
    
    print(f"Found {len(tables)} tables to import from SQL.")
    
    # Import each table
    for table_name in tables:
        try:
            # Prepare SQL filename
            safe_table_name = table_name.replace(' ', '_').replace('`', '').lower()
            sql_filename = os.path.join(SCRIPT_FOLDER_PARENT, f"{safe_table_name}.sql")
            
            if not os.path.exists(sql_filename):
                print(f"Warning: SQL file {sql_filename} not found. Skipping table: {table_name}")
                continue
            
            # Read SQL file
            with open(sql_filename, 'r', encoding='utf-8') as f:
                sql_content = f.read()
            
            if not sql_content:
                print(f"No SQL commands found in file {sql_filename}. Skipping table: {table_name}")
                continue
            
            print(f"Importing SQL for table: {table_name}")
            
            # Disable foreign key checks for import
            frappe.db.sql("SET FOREIGN_KEY_CHECKS = 0")
            
            # Split SQL content into statements
            statements = []
            current_statement = ""
            in_insert = False
            
            for line in sql_content.split('\n'):
                line = line.strip()
                
                # Skip comment lines
                if line.startswith('--') or line.startswith('/*') or not line:
                    continue
                
                current_statement += line + "\n"
                
                # Check if we're in an INSERT statement
                if line.upper().startswith('INSERT'):
                    in_insert = True
                
                # End of statement
                if line.endswith(';'):
                    if current_statement.strip():
                        statements.append(current_statement.strip())
                    current_statement = ""
                    in_insert = False
            
            # Add any remaining statement
            if current_statement.strip():
                statements.append(current_statement.strip())
            
            # Execute each statement
            total_statements = len(statements)
            for idx, stmt in enumerate(statements):
                if not stmt.strip():
                    continue
                
                try:
                    # Show progress for large imports
                    if total_statements > 10 and idx % 10 == 0:
                        print(f"  Processing statement {idx + 1}/{total_statements}")
                    
                    frappe.db.sql(stmt)
                    
                except Exception as e:
                    print(f"Error executing SQL statement {idx + 1}: {str(e)}")
                    print(f"Statement preview: {stmt[:200]}...")
                    # Continue with other statements instead of failing completely
                    continue
            
            # Re-enable foreign key checks
            frappe.db.sql("SET FOREIGN_KEY_CHECKS = 1")
            
            # Commit changes
            frappe.db.commit()
            
            print(f"Successfully imported SQL for table: {table_name}")
            
        except Exception as e:
            # Rollback transaction if error occurs
            frappe.db.rollback()
            frappe.db.sql("SET FOREIGN_KEY_CHECKS = 1")  # Re-enable foreign key checks
            print(f"Error importing SQL for table {table_name}: {str(e)}")
            import traceback
            traceback.print_exc()
    
    print("SQL table import process completed.")


def export_json():
    """
    Export database table data to JSON files (alternative format).
    """
    print("Starting JSON table export process...")
    print(f"Script folder: {SCRIPT_FOLDER_PARENT}")
    
    # Path to the file containing table names
    table_file_path = os.path.join(SCRIPT_FOLDER_PARENT, "table_list.txt")
    
    if not os.path.exists(table_file_path):
        print(f"Error: File {table_file_path} not found.")
        return
    
    # Read table names from file
    with open(table_file_path, 'r') as file:
        tables = [line.strip() for line in file if line.strip()]
    
    print(f"Found {len(tables)} tables to export to JSON: {tables}")
    
    # Create export directory
    os.makedirs(SCRIPT_FOLDER_PARENT, exist_ok=True)
    
    # Export each table
    for table_name in tables:
        try:
            # Get all data from the table
            data = frappe.db.sql(f"SELECT * FROM `{table_name}`", as_dict=True)
            
            # Create JSON file
            safe_table_name = table_name.replace(' ', '_').replace('`', '').lower()
            json_filename = os.path.join(SCRIPT_FOLDER_PARENT, f"{safe_table_name}.json")
            
            # Convert datetime objects to strings for JSON serialization
            json_data = []
            for row in data:
                json_row = {}
                for key, value in row.items():
                    if isinstance(value, (datetime.datetime, datetime.date)):
                        json_row[key] = value.isoformat()
                    else:
                        json_row[key] = value
                json_data.append(json_row)
            
            with open(json_filename, 'w', encoding='utf-8') as json_file:
                json.dump({
                    'table_name': table_name,
                    'export_date': datetime.datetime.now().isoformat(),
                    'record_count': len(json_data),
                    'data': json_data
                }, json_file, indent=2, ensure_ascii=False)
            
            print(f"Exported JSON for table: {table_name} with {len(data)} records to {json_filename}")
            
        except Exception as e:
            print(f"Error exporting JSON for table {table_name}: {str(e)}")
    
    print("JSON table export process completed.")


def create_sample_table_list():
    """
    Create a sample table_list.txt file with common Frappe tables
    """
    sample_content = """tabList View Settings
tabUser Settings
tabCustom Field
tabProperty Setter
tabWorkspace
tabDesktop Icon"""
    
    table_file_path = os.path.join(SCRIPT_FOLDER_PARENT, "table_list.txt")
    os.makedirs(SCRIPT_FOLDER_PARENT, exist_ok=True)
    
    with open(table_file_path, 'w') as f:
        f.write(sample_content)
    
    print(f"Created sample table_list.txt at {table_file_path}")
    print("Edit this file to include the tables you want to export/import.")


if __name__ == "__main__":
    # This block allows running the script directly
    import argparse
    
    parser = argparse.ArgumentParser(description='Export or import database table data')
    parser.add_argument('action', choices=['export', 'import', 'export-json', 'create-sample'], 
                        help='Action to perform: export, import, export-json, or create-sample')
    
    args = parser.parse_args()
    
    if args.action == 'export':
        export_sql()
    elif args.action == 'import':
        import_sql()
    elif args.action == 'export-json':
        export_json()
    elif args.action == 'create-sample':
        create_sample_table_list()


# table_list.txt : Every table name in a line (with or without backticks)
# Example content:
# tabList View Settings
# tabUser Settings  
# tabCustom Field
# tabProperty Setter
#
# For use in bench console:
# bench --site erp-sonnt.tiqn.local console
#
# Example usage:
# import customize_erpnext.api.export_import_data_table_in_db.export_import_data_table_in_db as script
# script.export_sql()     # To export table data from current site
# script.import_sql()     # To import table data to current site
# script.export_json()    # To export as JSON format
# script.create_sample_table_list()  # Create sample table list file