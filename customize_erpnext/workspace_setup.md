  Cấu trúc Workspace

  Workspace có 2 thành phần chính cần thêm:

  1. Links (Card links) - 

  Hiển thị trong các card ở phần dưới workspace. Dùng _add_link_to_card() hoặc _add_card_with_link().

  2. Shortcuts - Nút tắt phía trên

  Hiển thị như nút bấm lớn ở phần trên workspace. Cần thêm vào 2 chỗ:
  - Child table shortcuts (tabWorkspace Shortcut)
  - content JSON (block type "shortcut")

  ---
  Để thêm shortcut, bạn cần viết thêm helper function. Ví dụ dựa theo pattern workspace "GA":

  def _add_shortcut(doc, label, link_to, shortcut_type, doc_view="List", color="Grey", stats_filter=None):
      """Add a shortcut to a workspace if it doesn't already exist.

      Args:
          doc: Workspace document
          label: Display label (e.g. "Overtime Registration")
          link_to: Target DocType/Report/Page name
          shortcut_type: "DocType", "Report", or "Page"
          doc_view: "List", "Report Builder", etc.
          color: "Grey", "Green", "Blue", "Orange", "Red", etc.
          stats_filter: JSON string for count filter, e.g. '[["status","=","Open"]]'

      Returns True if added.
      """
      # Check if shortcut already exists
      for s in doc.shortcuts:
          if s.label == label:
              return False

      doc.append("shortcuts", {
          "type": shortcut_type,
          "link_to": link_to,
          "label": label,
          "doc_view": doc_view,
          "color": color,
          "stats_filter": stats_filter or "[]",
      })

      # Add shortcut block to content JSON
      content = json.loads(doc.content or "[]")
      if not any(
          block.get("type") == "shortcut"
          and block.get("data", {}).get("shortcut_name") == label
          for block in content
      ):
          content.append({
              "id": frappe.generate_hash(length=10),
              "type": "shortcut",
              "data": {"shortcut_name": label, "col": 3},
          })
          doc.content = json.dumps(content)

      return True

  Cách sử dụng

  def _setup_shift_attendance_workspace():
      doc = frappe.get_doc("Workspace", "Shift & Attendance")
      changed = False

      # Thêm shortcut
      if _add_shortcut(doc, "Attendance Machine", "Attendance Machine", "DocType", color="Green"):
          changed = True

      if _add_shortcut(doc, "Overtime Registration", "Overtime Registration", "DocType"):
          changed = True

      # Thêm card link (như cũ)
      if _add_link_to_card(doc, "Overtime", "Overtime Registration", ...):
          changed = True

      ...

  Các tham số quan trọng
  ┌───────────────┬──────────────────────────────────────────┬───────────────────────┐
  │    Tham số    │                 Giá trị                  │        Ý nghĩa        │
  ├───────────────┼──────────────────────────────────────────┼───────────────────────┤
  │ shortcut_type │ "DocType"                                │ Link đến list DocType │
  ├───────────────┼──────────────────────────────────────────┼───────────────────────┤
  │               │ "Report"                                 │ Link đến Report       │
  ├───────────────┼──────────────────────────────────────────┼───────────────────────┤
  │               │ "Page"                                   │ Link đến Page         │
  ├───────────────┼──────────────────────────────────────────┼───────────────────────┤
  │ doc_view      │ "List"                                   │ Mở list view          │
  ├───────────────┼──────────────────────────────────────────┼───────────────────────┤
  │               │ "Report Builder"                         │ Mở report builder     │
  ├───────────────┼──────────────────────────────────────────┼───────────────────────┤
  │               │ "New"                                    │ Mở form tạo mới       │
  ├───────────────┼──────────────────────────────────────────┼───────────────────────┤
  │ color         │ "Grey", "Green", "Blue", "Orange", "Red" │ Màu nút               │
  ├───────────────┼──────────────────────────────────────────┼───────────────────────┤
  │ stats_filter  │ '[["status","=","Open"]]'                │ Hiện count badge      │
  └───────────────┴──────────────────────────────────────────┴───────────────────────┘