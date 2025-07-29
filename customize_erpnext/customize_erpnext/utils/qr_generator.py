# FILE 1: customize_erpnext/customize_erpnext/utils/qr_generator.py

import frappe
from frappe.utils import now_datetime, getdate, get_time, format_date, format_time
import qrcode
import base64
from io import BytesIO
import json

class OvertimeQRGenerator:
    """
    Generator QR Code cho Overtime Request dựa trên công thức Excel
    """
    
    def __init__(self, overtime_request_doc):
        self.doc = overtime_request_doc
    
    def generate_qr_data(self):
        """Tạo data string cho QR code theo format Excel"""
        qr_parts = []
        
        # 1. Timestamp hiện tại
        timestamp = now_datetime().strftime("%Y%m%d%H%M%S")
        qr_parts.append(timestamp)
        
        # 2. Application date
        application_date = ""
        if hasattr(self.doc, 'creation') and self.doc.creation:
            creation_date = getdate(self.doc.creation)
            if creation_date.year > 1900:
                application_date = creation_date.strftime("%Y%m%d")
        qr_parts.append(application_date)
        
        # 3. Overtime details
        overtime_details = self.build_overtime_details()
        qr_parts.append(overtime_details)
        
        # 4. Employee info
        employee_info = self.build_employee_info()
        qr_parts.append(employee_info)
        
        return "; ".join(qr_parts)
    
    def build_overtime_details(self):
        """Build overtime details từ child table"""
        overtime_entries = []
        
        # Check child table name - có thể là 'ot_details', 'ot_employee_details', etc.
        child_table_field = None
        for fieldname in ['ot_details', 'ot_employee_details', 'employee_details']:
            if hasattr(self.doc, fieldname):
                child_table_field = fieldname
                break
        
        if child_table_field:
            child_records = getattr(self.doc, child_table_field)
            for detail in child_records:
                if hasattr(detail, 'ot_date') and detail.ot_date and detail.ot_date.year > 1900:
                    date_str = detail.ot_date.strftime("%Y%m%d")
                    start_time = self.format_time_for_qr(getattr(detail, 'start_time', ''))
                    end_time = self.format_time_for_qr(getattr(detail, 'end_time', ''))
                    
                    if start_time and end_time:
                        entry = f"{date_str} {start_time} {end_time}"
                        overtime_entries.append(entry)
        
        # Fallback to single date fields
        elif hasattr(self.doc, 'ot_date') and self.doc.ot_date:
            if self.doc.ot_date.year > 1900:
                date_str = self.doc.ot_date.strftime("%Y%m%d")
                start_time = self.format_time_for_qr(getattr(self.doc, 'start_time', ''))
                end_time = self.format_time_for_qr(getattr(self.doc, 'end_time', ''))
                
                if start_time and end_time:
                    entry = f"{date_str} {start_time} {end_time}"
                    overtime_entries.append(entry)
        
        return ", ".join(overtime_entries)
    
    def format_time_for_qr(self, time_value):
        """Format time value cho QR code (HH:mm)"""
        if not time_value:
            return ""
        
        try:
            if hasattr(time_value, 'total_seconds'):
                total_seconds = int(time_value.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                return f"{hours:02d}:{minutes:02d}"
            elif isinstance(time_value, str):
                return time_value
            elif hasattr(time_value, 'strftime'):
                return time_value.strftime("%H:%M")
            return str(time_value)
        except Exception:
            return ""
    
    def build_employee_info(self):
        """Build employee info"""
        info_parts = []
        
        # Employee fields
        fields_to_include = [
            'employee', 'employee_name', 'department', 'reason', 
            'status', 'company', 'name'
        ]
        
        for field in fields_to_include:
            if hasattr(self.doc, field) and getattr(self.doc, field):
                info_parts.append(str(getattr(self.doc, field)))
        
        # Total hours if available
        if hasattr(self.doc, 'total_planned_hours') and self.doc.total_planned_hours:
            info_parts.append(f"Total:{self.doc.total_planned_hours}h")
        
        return " ".join(info_parts)
    
    def generate_qr_code_image(self, qr_data=None):
        """Generate QR code image"""
        if not qr_data:
            qr_data = self.generate_qr_data()
        
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return img_str, qr_data

# API Methods
@frappe.whitelist()
def generate_overtime_qr_code(overtime_request_name):
    """API để generate QR code"""
    try:
        doc = frappe.get_doc("Overtime Request", overtime_request_name)
        generator = OvertimeQRGenerator(doc)
        qr_image, qr_data = generator.generate_qr_code_image()
        
        # Update document
        doc.db_set("qr_code_data", qr_data)
        doc.db_set("qr_code_image", qr_image)
        
        return {
            "success": True,
            "qr_data": qr_data,
            "qr_image": f"data:image/png;base64,{qr_image}",
            "message": "QR Code generated successfully"
        }
        
    except Exception as e:
        frappe.log_error(f"QR Code generation error: {str(e)}", "Overtime QR Generation")
        return {"success": False, "message": str(e)}

@frappe.whitelist()
def parse_qr_code_data(qr_data):
    """Parse QR code data"""
    try:
        parts = qr_data.split(";")
        
        if len(parts) < 4:
            return {"success": False, "message": "Invalid QR data format"}
        
        # Parse timestamp
        timestamp_str = parts[0].strip()
        timestamp = None
        if len(timestamp_str) == 14:
            try:
                timestamp = frappe.utils.datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
            except:
                pass
        
        # Parse application date
        app_date_str = parts[1].strip()
        application_date = None
        if len(app_date_str) == 8:
            try:
                application_date = frappe.utils.datetime.strptime(app_date_str, "%Y%m%d").date()
            except:
                pass
        
        # Parse overtime details
        overtime_details = []
        ot_details_str = parts[2].strip()
        if ot_details_str:
            ot_entries = ot_details_str.split(",")
            for entry in ot_entries:
                entry = entry.strip()
                if len(entry) >= 17:
                    try:
                        date_part = entry[:8]
                        time_part = entry[9:]
                        times = time_part.split()
                        
                        if len(times) >= 2:
                            ot_date = frappe.utils.datetime.strptime(date_part, "%Y%m%d").date()
                            start_time = times[0]
                            end_time = times[1]
                            
                            overtime_details.append({
                                "date": ot_date,
                                "start_time": start_time,
                                "end_time": end_time
                            })
                    except:
                        continue
        
        # Parse employee info
        employee_info = parts[3].strip()
        employee_data = employee_info.split() if employee_info else []
        
        return {
            "success": True,
            "data": {
                "timestamp": timestamp,
                "application_date": application_date,
                "overtime_details": overtime_details,
                "employee_info": employee_data,
                "raw_data": qr_data
            }
        }
        
    except Exception as e:
        return {"success": False, "message": str(e)}

# Hook function
def on_update_overtime_request(doc, method):
    """Auto generate QR code khi status = Approved"""
    try:
        if doc.status == "Approved":
            generator = OvertimeQRGenerator(doc)
            qr_image, qr_data = generator.generate_qr_code_image()
            
            doc.db_set("qr_code_data", qr_data, update_modified=False)
            doc.db_set("qr_code_image", qr_image, update_modified=False)
            
    except Exception as e:
        frappe.log_error(f"Auto QR generation error: {str(e)}", "Overtime Request QR")