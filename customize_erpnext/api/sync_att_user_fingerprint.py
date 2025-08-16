# attendance_device_sync.py
"""
Module đồng bộ dữ liệu vân tay đến máy chấm công ZKTeco
"""

import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import base64
import socket
import time
from zk import ZK, const
from zk.base import Finger
from config import ATTENDANCE_DEVICES, FINGERPRINT_CONFIG
from core.erpnext_api import ERPNextAPI

logger = logging.getLogger(__name__)


class AttendanceDeviceSync:
    """Lớp xử lý đồng bộ dữ liệu với máy chấm công"""
    
    def __init__(self, erpnext_api: ERPNextAPI):
        self.erpnext_api = erpnext_api
        self.connected_devices = {}
        
    def connect_device(self, device_config: Dict) -> Optional[ZK]:
        """
        Kết nối với một máy chấm công
        
        Args:
            device_config: Thông tin cấu hình thiết bị
            
        Returns:
            ZK object nếu kết nối thành công, None nếu thất bại
        """
        try:
            device_name = device_config.get('device_name', device_config.get('name', f"Device_{device_config.get('id', 1)}"))
            device_ip = device_config.get('ip', device_config.get('ip_address', ''))
            device_port = device_config.get('port', 4370)
            
            logger.info(f"🔌 Đang kết nối với {device_name} ({device_ip}:{device_port})...")
            
            if not device_ip:
                logger.error(f"❌ Thiết bị {device_name} không có địa chỉ IP")
                return None
            
            # Tạo instance ZK với thông tin từ config
            zk = ZK(
                device_ip, 
                port=device_port, 
                timeout=device_config.get('timeout', 10),
                password=device_config.get('password', 0),
                force_udp=device_config.get('force_udp', True),
                ommit_ping=device_config.get('ommit_ping', True)
            )
            
            # Kiểm tra kết nối mạng
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((device_ip, device_port))
                if result != 0:
                    logger.error(f"❌ Không thể kết nối đến {device_ip}:{device_port} - Lỗi: {result}")
                    return None
                sock.close()
            except Exception as e:
                logger.error(f"❌ Lỗi kiểm tra kết nối mạng: {str(e)}")
                return None
            
            # Kết nối với thiết bị
            try:
                conn = zk.connect()
                if not conn:
                    raise Exception("Failed to connect to device")
            except Exception as e:
                logger.error(f"❌ Lỗi kết nối với thiết bị: {str(e)}")
                return None
            
            # Tạm thời vô hiệu hóa thiết bị để tránh xung đột
            try:
                conn.disable_device()
            except Exception as e:
                logger.error(f"❌ Lỗi vô hiệu hóa thiết bị: {str(e)}")
                return None
            
            # Lấy thông tin thiết bị
            try:
                device_info = {
                    'serial': conn.get_serialnumber(),
                    'platform': conn.get_platform(),
                    'device_name': conn.get_device_name(),
                    'firmware': conn.get_firmware_version(),
                    'users': len(conn.get_users()),
                    'fingerprints': conn.get_fp_version()
                }
                
                logger.info(f"✅ Kết nối thành công với {device_name}")
                logger.info(f"   📱 Model: {device_info['device_name']}")
                logger.info(f"   🔢 Serial: {device_info['serial']}")
                logger.info(f"   👥 Số người dùng: {device_info['users']}")
                
                # Lưu connection
                device_id = device_config.get('id', 1)
                self.connected_devices[device_id] = conn
                
                return conn
            except Exception as e:
                logger.error(f"❌ Lỗi lấy thông tin thiết bị: {str(e)}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối với {device_name}: {str(e)}")
            return None
    
    def disconnect_device(self, device_id: int):
        """Ngắt kết nối với thiết bị"""
        if device_id in self.connected_devices:
            try:
                self.connected_devices[device_id].enable_device()
                self.connected_devices[device_id].disconnect()
                del self.connected_devices[device_id]
                logger.info(f"✅ Đã ngắt kết nối thiết bị ID: {device_id}")
            except Exception as e:
                logger.error(f"❌ Lỗi ngắt kết nối: {str(e)}")
    
    def disconnect_all_devices(self):
        """Ngắt kết nối tất cả thiết bị"""
        device_ids = list(self.connected_devices.keys())
        for device_id in device_ids:
            self.disconnect_device(device_id)

    def sync_employee_to_device(self, zk: ZK, employee_data: Dict, 
                               fingerprints: List[Dict]) -> bool:
        """
        Đồng bộ dữ liệu một nhân viên đến thiết bị sử dụng phương pháp mới
        
        Args:
            zk: ZK connection object
            employee_data: Thông tin nhân viên (bao gồm attendance_device_id)
            fingerprints: Danh sách vân tay của nhân viên
            
        Returns:
            True nếu đồng bộ thành công
        """
        try:
            # Kiểm tra dữ liệu đầu vào
            if not employee_data:
                logger.error("❌ Không có dữ liệu nhân viên")
                return False
                
            if not fingerprints:
                logger.warning(f"⚠️ Nhân viên {employee_data.get('employee', 'Unknown')} không có dữ liệu vân tay")
                return False
            
            # Lấy attendance_device_id
            user_id = employee_data.get('attendance_device_id')
            if not user_id:
                logger.error(f"❌ Nhân viên {employee_data.get('employee', 'Unknown')} chưa có attendance_device_id")
                return False
            
            # # Chuyển đổi user_id sang số
            # try:
            #     user_id = int(user_id)
            # except ValueError:
            #     logger.error(f"❌ attendance_device_id không hợp lệ: {user_id}")
            #     return False
            
            logger.info(f"👤 Đang xử lý nhân viên: {employee_data['employee']} - {employee_data['employee_name']} (ID: {user_id})")
            
            # Kiểm tra xem user đã tồn tại chưa
            existing_users = zk.get_users()
            user_exists = any(u.user_id == user_id for u in existing_users) 
            if user_exists:
                logger.info(f"🗑️ User {user_id} đã tồn tại. Đang xóa user cũ...")
                zk.delete_user(user_id=user_id)
                logger.info(f"✅ Đã xóa user {user_id}.")
                time.sleep(0.5)  # Cho thiết bị một chút thời gian
            
            # Tạo user mới
            logger.info(f"➕ Tạo mới user {user_id}...") 
            full_name = employee_data['employee_name']
            shortened_name = self.shorted_name(full_name,24)  
            print(f"   Tên đầy đủ: {full_name}, Tên rút gọn: {shortened_name}")
            privilege= const.USER_ADMIN if employee_data['employee_name']=='USER_ADMIN' else const.USER_DEFAULT
            print(f"   Quyền hạn: {privilege}")
            password = str(employee_data['password']) if employee_data['password'] else None
            print(f"   Mật khẩu: {password}")
            if not password:
                zk.set_user(user_id= user_id , name=shortened_name , privilege=privilege) 
            else:
                zk.set_user(user_id= user_id , name=shortened_name , privilege=privilege, password= password)
            print(f"   Tạo user thành công: {full_name} (ID: {user_id})")
            # Lấy lại thông tin user sau khi tạo
            users = zk.get_users()
            user = next((u for u in users if u.user_id == user_id), None)
            if not user:
                logger.error(f"❌ Không thể tạo hoặc tìm thấy user {user_id} sau khi tạo.")
                return False
            uid_int = user.uid
            # Chuẩn bị danh sách template để gửi
            templates_to_send = []
            success_count = 0
            
            # Tạo 10 Finger objects, với template thực cho các ngón có dữ liệu
            for i in range(10):
                # Tìm vân tay cho ngón tay này
                finger_data = None
                for fp in fingerprints:
                    if fp.get('finger_index') == i and fp.get('template_data'):
                        finger_data = fp
                        break
                
                if finger_data:
                    try:
                        # Decode base64 template data
                        template_bytes = base64.b64decode(finger_data['template_data'])
                        finger_obj = Finger(uid=uid_int, fid=i, valid=True, template=template_bytes)
                        templates_to_send.append(finger_obj)
                        logger.info(f"   ✅ Chuẩn bị template cho ngón {i}")
                        success_count += 1
                    except Exception as e:
                        logger.error(f"   ❌ Lỗi xử lý template ngón {i}: {str(e)}")
                        finger_obj = Finger(uid=uid_int, fid=i, valid=False, template=b'')
                        templates_to_send.append(finger_obj)
                else:
                    # Ngón tay không có dữ liệu, tạo template trống
                    finger_obj = Finger(uid=uid_int, fid=i, valid=False, template=b'')
                    templates_to_send.append(finger_obj)
            
            # Gửi tất cả template lên thiết bị
            logger.info(f"📤 Gửi {success_count} template vân tay lên máy chấm công...")
            
            try:
                zk.save_user_template(user, templates_to_send)
                logger.info(f"✅ Đã gửi thành công {success_count} template cho user {uid_int}")
                
                # Ghi log đồng bộ
                try:
                    self.erpnext_api.log_sync_history(
                        sync_type="fingerprint_sync_to_device",
                        device_name=zk.get_device_name(),
                        employee_count=1,
                        status="success",
                        message=f"Đồng bộ thành công {success_count} vân tay cho {employee_data['employee']}"
                    )
                except Exception as e:
                    logger.error(f"❌ Lỗi ghi log đồng bộ: {str(e)}")
                
                return True
                
            except Exception as e:
                logger.error(f"❌ Lỗi khi gửi template: {str(e)}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Lỗi đồng bộ nhân viên {employee_data.get('employee', 'Unknown')}: {str(e)}")
            return False
    
    def sync_to_device(self, device_config: dict, employees: List[dict]) -> Tuple[int, int]:
        """
        Đồng bộ dữ liệu vân tay đến một thiết bị cụ thể
        
        Args:
            device_config: Cấu hình thiết bị
            employees: Danh sách nhân viên cần đồng bộ
            
        Returns:
            Tuple[int, int]: (số nhân viên đồng bộ thành công, tổng số nhân viên)
        """
        device_name = device_config.get('device_name', device_config.get('name', f"Device_{device_config.get('id', 1)}"))
        device_ip = device_config.get('ip', device_config.get('ip_address', ''))
        
        logger.info(f"🎯 Đồng bộ đến: {device_name}")
        logger.info("=" * 60)
        
        # Kết nối thiết bị
        logger.info(f"🔌 Đang kết nối với {device_name} ({device_ip})...")
        zk = self.connect_device(device_config)
        
        if not zk:
            logger.error(f"❌ Lỗi kết nối với {device_name}")
            return 0, 0
            
        try:
            # Lọc nhân viên có vân tay và attendance_device_id hợp lệ
            valid_employees = []
            for emp in employees:
                if not emp.get('fingerprints'):
                    continue
                    
                # Kiểm tra attendance_device_id
                attendance_id = emp.get('attendance_device_id')
                if not attendance_id or str(attendance_id).strip() == "":
                    logger.warning(f"⚠️ Nhân viên {emp['employee']} - {emp['employee_name']} chưa có ID máy chấm công")
                    continue
                    
                try:
                    attendance_id = int(attendance_id)
                except ValueError:
                    logger.warning(f"⚠️ ID máy chấm công không hợp lệ cho nhân viên {emp['employee']}: {attendance_id}")
                    continue
                    
                # Kiểm tra vân tay
                has_valid_fingerprints = False
                for fp in emp['fingerprints']:
                    if fp.get('template_data'):
                        has_valid_fingerprints = True
                        break
                        
                if not has_valid_fingerprints:
                    logger.warning(f"⚠️ Nhân viên {emp['employee']} - {emp['employee_name']} không có vân tay hợp lệ")
                    continue
                    
                valid_employees.append(emp)
            
            if not valid_employees:
                logger.warning(f"⚠️ Không có nhân viên nào hợp lệ để đồng bộ đến {device_name}")
                return 0, 0
                
            # Đồng bộ từng nhân viên
            success_count = 0
            total_count = len(valid_employees)
            
            for emp in valid_employees:
                try:
                    if self.sync_employee_to_device(zk, emp, emp['fingerprints']):
                        success_count += 1
                        logger.info(f"✅ Đã đồng bộ thành công nhân viên {emp['employee']} - {emp['employee_name']}")
                    else:
                        logger.error(f"❌ Không thể đồng bộ nhân viên {emp['employee']}")
                        
                except Exception as e:
                    logger.error(f"❌ Lỗi khi đồng bộ nhân viên {emp['employee']}: {str(e)}")
                    continue
            
            return success_count, total_count
            
        except Exception as e:
            logger.error(f"❌ Lỗi khi đồng bộ đến {device_name}: {str(e)}")
            return 0, 0
            
        finally:
            # Ngắt kết nối thiết bị
            device_id = device_config.get('id', 1)
            self.disconnect_device(device_id)
    
    def sync_all_to_device(self, device_config: Dict, employees_to_sync: List[Dict]) -> Tuple[int, int]:
        """
        Đồng bộ danh sách nhân viên cụ thể đến một thiết bị
        
        Args:
            device_config: Thông tin cấu hình thiết bị
            employees_to_sync: Danh sách nhân viên cần đồng bộ (đã có vân tay trong current_fingerprints)
            
        Returns:
            Tuple (số nhân viên thành công, tổng số nhân viên)
        """
        success_count = 0
        total_count = len(employees_to_sync)
        
        # Kết nối thiết bị
        zk = self.connect_device(device_config)
        if not zk:
            return 0, 0
        
        try:
            device_name = device_config.get('device_name', device_config.get('name', f"Device_{device_config.get('id', 1)}"))
            logger.info(f"📊 Bắt đầu đồng bộ {total_count} nhân viên đến {device_name}")
            
            # Đồng bộ từng nhân viên
            for i, employee in enumerate(employees_to_sync, 1):
                logger.info(f"\n[{i}/{total_count}] Đang xử lý {employee['employee']} - {employee['employee_name']}")
                
                # Lấy dữ liệu vân tay từ employee object
                fingerprints = employee.get('fingerprints', [])
                
                # Kiểm tra dữ liệu vân tay
                if not fingerprints:
                    logger.warning(f"   ⚠️ Nhân viên không có dữ liệu vân tay để đồng bộ")
                    continue
                    
                # Kiểm tra template data
                valid_fingerprints = []
                for fp in fingerprints:
                    if not isinstance(fp, dict):
                        logger.error(f"   ❌ Dữ liệu vân tay không hợp lệ: {type(fp)}")
                        continue
                        
                    template_data = fp.get('template_data')
                    if not template_data:
                        logger.error(f"   ❌ Không có template data cho ngón {fp.get('finger_index', 'Unknown')}")
                        continue
                        
                    valid_fingerprints.append(fp)
                
                if not valid_fingerprints:
                    logger.warning(f"   ⚠️ Không có vân tay hợp lệ để đồng bộ")
                    continue
                    
                # Đồng bộ
                if self.sync_employee_to_device(zk, employee, valid_fingerprints):
                    success_count += 1
                    logger.info(f"   ✅ Đã đồng bộ thành công")
                else:
                    logger.error(f"   ❌ Đồng bộ thất bại")
            
            # Ghi log đồng bộ tổng
            try:
                device_name = device_config.get('device_name', device_config.get('name', f"Device_{device_config.get('id', 1)}"))
                self.erpnext_api.log_sync_history(
                    sync_type="fingerprint_sync_to_device",
                    device_name=device_name,
                    employee_count=success_count,
                    status="success" if success_count > 0 else "failed",
                    message=f"Đồng bộ thành công {success_count}/{total_count} nhân viên"
                )
            except Exception as e:
                logger.error(f"❌ Lỗi ghi log đồng bộ: {str(e)}")
            
            logger.info(f"\n✅ Hoàn thành đồng bộ: {success_count}/{total_count} nhân viên")
            
        except Exception as e:
            logger.error(f"❌ Lỗi trong quá trình đồng bộ: {str(e)}")
            
        finally:
            # Ngắt kết nối
            device_id = device_config.get('id', 1)
            self.disconnect_device(device_id)
            
        return success_count, total_count
    
    def sync_to_all_devices(self, employees_to_sync: List[Dict]) -> Dict[str, Tuple[int, int]]:
        """
        Đồng bộ danh sách nhân viên cụ thể đến tất cả các thiết bị
        
        Args:
            employees_to_sync: Danh sách nhân viên cần đồng bộ
            
        Returns:
            Dict với key là tên thiết bị, value là (success_count, total_count)
        """
        results = {}
        
        logger.info(f"🔄 Bắt đầu đồng bộ đến {len(ATTENDANCE_DEVICES)} thiết bị")
        
        for device in ATTENDANCE_DEVICES:
            device_name = device.get('device_name', device.get('name', f"Device_{device.get('id', 1)}"))
            logger.info(f"\n{'='*60}")
            logger.info(f"🎯 Đồng bộ đến: {device_name}")
            logger.info(f"{'='*60}")
            
            success, total = self.sync_all_to_device(device, employees_to_sync)
            results[device_name] = (success, total)
        
        # Tổng kết
        logger.info(f"\n{'='*60}")
        logger.info(f"📊 TỔNG KẾT ĐỒNG BỘ")
        logger.info(f"{'='*60}")
        
        for device_name, (success, total) in results.items():
            logger.info(f"✅ {device_name}: {success}/{total} nhân viên")
        
        return results
    
    def delete_employee_from_device(self, zk: ZK, user_id: int) -> bool:
        """
        Xóa nhân viên khỏi thiết bị
        
        Args:
            zk: ZK connection object
            user_id: ID của nhân viên trên thiết bị
            
        Returns:
            True nếu xóa thành công
        """
        try:
            logger.info(f"🗑️ Đang xóa user ID: {user_id}")
            
            # Xóa user
            zk.delete_user(uid=user_id)
            
            logger.info(f"✅ Đã xóa user ID: {user_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Lỗi xóa user: {str(e)}")
            return False
    
    def get_device_users(self, device_config: Dict) -> List[Dict]:
        """
        Lấy danh sách users từ thiết bị
        
        Args:
            device_config: Thông tin cấu hình thiết bị
            
        Returns:
            Danh sách thông tin users
        """
        users_list = []
        
        zk = self.connect_device(device_config)
        if not zk:
            return users_list
        
        try:
            users = zk.get_users()
            
            for user in users:
                user_info = {
                    'user_id': user.user_id,
                    'uid': user.uid,
                    'name': user.name,
                    'privilege': user.privilege,
                    'password': user.password,
                    'group_id': user.group_id,
                    'card': user.card
                }
                users_list.append(user_info)
            
            device_name = device_config.get('device_name', device_config.get('name', f"Device_{device_config.get('id', 1)}"))
            logger.info(f"✅ Lấy được {len(users_list)} users từ {device_name}")
            
        except Exception as e:
            logger.error(f"❌ Lỗi lấy danh sách users: {str(e)}")
            
        finally:
            device_id = device_config.get('id', 1)
            self.disconnect_device(device_id)
        
        return users_list
    
    def clear_device_data(self, device_config: Dict) -> bool:
        """
        Xóa toàn bộ dữ liệu users và vân tay trên thiết bị
        
        Args:
            device_config: Thông tin cấu hình thiết bị
            
        Returns:
            True nếu xóa thành công
        """
        zk = self.connect_device(device_config)
        if not zk:
            return False
        
        try:
            device_name = device_config.get('device_name', device_config.get('name', f"Device_{device_config.get('id', 1)}"))
            logger.warning(f"⚠️ Đang xóa toàn bộ dữ liệu trên {device_name}...")
            
            # Xóa tất cả users
            zk.clear_data()
            
            logger.info(f"✅ Đã xóa toàn bộ dữ liệu trên {device_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Lỗi xóa dữ liệu: {str(e)}")
            return False
            
        finally:
            device_id = device_config.get('id', 1)
            self.disconnect_device(device_id)
    def shorten_employee_name(full_name, max_length=24):
        """
        Rút gọn tên nhân viên nếu vượt quá độ dài tối đa
        
        Args:
            full_name: Tên đầy đủ của nhân viên
            max_length: Độ dài tối đa cho phép
            
        Returns:
            Tên đã rút gọn
        """
        if not full_name or len(full_name) <= max_length:
            return full_name
            
        # Tách các phần trong tên
        name_parts = full_name.split()
        
        if len(name_parts) <= 2:
            # Nếu chỉ có 1-2 phần, cắt ngắn đơn giản
            return full_name[:max_length]
        
        # Lấy chữ cái đầu của các phần trừ phần cuối
        initials = ''.join(part[0] for part in name_parts[:-1])
        
        # Kết hợp chữ cái đầu với phần cuối
        shortened_name = f"{initials} {name_parts[-1]}"
        
        # Nếu vẫn dài quá, cắt ngắn
        if len(shortened_name) > max_length:
            return shortened_name[:max_length]
        
        return shortened_name           
    def shorted_name(self, full_name: str, max_length=24):
        # Loại bỏ khoảng trắng thừa
        text_processed = ' '.join(full_name.split()).strip()

        if len(text_processed) > max_length:
            parts = text_processed.split()
            if len(parts) > 1:
                # Lấy chữ cái đầu của tất cả các phần trừ phần cuối cùng
                initials = "".join(part[0].upper() for part in parts[:-1])
                last_part = parts[-1]
                return f"{initials} {last_part}"
            else:
                # Nếu chỉ có một từ và quá dài, trả về nguyên bản
                return text_processed
        else:
            return text_processed