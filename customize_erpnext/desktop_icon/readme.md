# Desktop Icon - Hướng dẫn thêm icon lên Desk

## Vấn đề

Frappe v14+ chỉ hiển thị Desktop Icon trên desk nếu có **Workspace Sidebar** cùng tên.
Icon với `link_type: "External"` sẽ không hiện nếu không có Workspace Sidebar tương ứng.

---

## Các bước thêm một Desktop Icon mới

### Bước 1: Tạo file Desktop Icon fixture

Tạo file JSON trong thư mục `customize_erpnext/desktop_icon/`:

```json
{
 "app": "customize_erpnext",
 "doctype": "Desktop Icon",
 "docstatus": 0,
 "hidden": 0,
 "icon_type": "Link",
 "idx": 0,
 "label": "Tên Icon",
 "link": "/duong-dan-url",
 "link_type": "External",
 "logo_url": "/assets/customize_erpnext/images/ten_anh.svg",
 "name": "Tên Icon",
 "owner": "Administrator",
 "restrict_removal": 0,
 "roles": [],
 "standard": 1
}
```

> Nếu muốn giới hạn theo role, thêm vào `roles`:
> ```json
> "roles": [
>   {"role": "HR Manager"},
>   {"role": "HR User"}
> ]
> ```

### Bước 2: Tạo file Workspace Sidebar fixture

Tạo file JSON trong thư mục `customize_erpnext/workspace_sidebar/`:

```json
{
 "app": "customize_erpnext",
 "doctype": "Workspace Sidebar",
 "docstatus": 0,
 "for_user": "",
 "header_icon": "",
 "items": [
  {
   "hidden": 0,
   "icon": "",
   "label": "Tên Icon",
   "link_to": "/duong-dan-url",
   "link_type": "URL",
   "type": "Link"
  }
 ],
 "module": "Customize Erpnext",
 "module_onboarding": "",
 "name": "Tên Icon",
 "title": "Tên Icon"
}
```

> `name` của Workspace Sidebar phải **khớp chính xác** với `label` của Desktop Icon.

### Bước 3: Đăng ký vào hooks.py

Mở `customize_erpnext/hooks.py`, thêm tên icon vào 2 chỗ trong `fixtures`:

```python
# Desktop Icons
{
    "doctype": "Desktop Icon",
    "filters": [
        ["name", "in", ["TIQN App", ..., "Tên Icon Mới"]]
    ]
},
# Workspace Sidebars
{
    "doctype": "Workspace Sidebar",
    "filters": [
        ["name", "in", ["Job Portal", ..., "Tên Icon Mới"]]
    ]
}
```

### Bước 4: Import vào database

```bash
bench --site erp.tiqn.local migrate
```

### Bước 5: Clear cache và reload browser

```bash
bench --site erp.tiqn.local clear-cache
```

Sau khi reload, icon mới sẽ xuất hiện trong phần **"Removed Icons"** ở cuối trang desk.
Bấm dấu `+` để thêm lên màn hình chính.

---

## Giải thích kỹ thuật

- `is_permitted()` trong `frappe/desk/doctype/desktop_icon/desktop_icon.py` kiểm tra
  `bootinfo.workspace_sidebar_item[label.lower()]` trước khi hiển thị icon.
- Nếu không tìm thấy Workspace Sidebar cùng tên → `KeyError` → icon bị ẩn.
- Workspace Sidebar chỉ cần tồn tại với ít nhất 1 item không phải `Section Break`.
- Desktop Icon vẫn giữ `link_type: "External"` → click mở thẳng URL, không qua workspace.

---

## Danh sách icon hiện có

| Label             | URL                       | Roles                      |
|-------------------|---------------------------|----------------------------|
| TIQN App          | Workspace (link_type)     | (all)                      |
| Job Portal        | /jobs                     | (all)                      |
| Employee Photos   | /employee-photos          | HR Manager, HR User, Admin |
| QR Code Generator | /qr-code                  | (all)                      |
| Shoe Rack         | /desk/shoe-rack-dashboard | HR Manager, HR User, Admin |
| Sync Logs         | /erpnext-sync-all-logs    | (all)                      |
