#!/usr/bin/env python3
"""
Split Print Format Tool
Đọc file print_format.json và tách thành các file riêng biệt cho từng print format
với file HTML/CSS dễ đọc để copy vào Web UI
"""

import os
import json
import re


def format_html_content(html_content):
    """Format HTML content để dễ đọc"""
    if not html_content:
        return html_content

    # Chuyển đổi escape characters thành newlines
    formatted_html = html_content.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\r\n', '\n')

    # Thêm indentation cơ bản cho HTML tags
    lines = formatted_html.split('\n')
    formatted_lines = []
    indent_level = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Giảm indent cho closing tags
        if line.startswith('</') and not line.startswith('</br>') and not line.startswith('</hr>'):
            indent_level = max(0, indent_level - 1)

        # Thêm indentation
        formatted_lines.append('  ' * indent_level + line)

        # Tăng indent cho opening tags (không self-closing)
        if '<' in line and not line.startswith('</') and not line.endswith('/>') and not any(tag in line for tag in ['<br>', '<hr>', '<img', '<input', '<meta']):
            if not line.endswith('>'):
                continue
            tag_match = re.search(r'<(\w+)', line)
            if tag_match and not line.endswith(f'</{tag_match.group(1)}>'):
                indent_level += 1

    return '\n'.join(formatted_lines)


def format_css_content(css_content):
    """Format CSS content để dễ đọc"""
    if not css_content:
        return css_content

    # Chuyển đổi escape characters
    formatted_css = css_content.replace('\\r\\n', '\n').replace('\\n', '\n').replace('\r\n', '\n')

    # Format CSS với indentation
    lines = formatted_css.split('\n')
    formatted_lines = []
    indent_level = 0

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if '}' in line:
            indent_level = max(0, indent_level - 1)

        formatted_lines.append('  ' * indent_level + line)

        if '{' in line:
            indent_level += 1

    return '\n'.join(formatted_lines)


def save_html_css_files(pf_data, print_formats_dir):
    """Tạo file .html và .css riêng biệt"""
    if not pf_data.get('name'):
        return

    safe_name = pf_data['name'].replace(' ', '_').replace('/', '_').replace('\\', '_')

    # Tạo thư mục templates
    templates_dir = os.path.join(print_formats_dir, "templates")
    os.makedirs(templates_dir, exist_ok=True)

    # Lưu file HTML
    if pf_data.get('html'):
        html_file = os.path.join(templates_dir, f"{safe_name}.html")
        formatted_html = format_html_content(pf_data['html'])
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write(formatted_html)
        print(f"   📄 Created: {safe_name}.html")

    # Lưu file CSS
    if pf_data.get('css'):
        css_file = os.path.join(templates_dir, f"{safe_name}.css")
        formatted_css = format_css_content(pf_data['css'])
        with open(css_file, 'w', encoding='utf-8') as f:
            f.write(formatted_css)
        print(f"   🎨 Created: {safe_name}.css")


def split_print_formats():
    """Tách print format từ file JSON thành các file riêng"""
    # Đường dẫn fixtures
    current_dir = os.path.dirname(os.path.abspath(__file__))
    fixtures_path = current_dir  # fixtures directory is current directory
    print_format_file = os.path.join(fixtures_path, "print_format.json")

    if not os.path.exists(print_format_file):
        print("❌ Không tìm thấy file print_format.json")
        print(f"   Đường dẫn: {print_format_file}")
        print("   Hãy chạy: bench --site [site] export-fixtures trước")
        return

    print(f"📂 Đọc file: {print_format_file}")

    # Đọc file JSON
    with open(print_format_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data:
        print("❌ Không có print format nào trong file")
        return

    print(f"📋 Tìm thấy {len(data)} print formats")

    # Tạo thư mục print_formats
    print_formats_dir = os.path.join(fixtures_path, "print_formats")
    os.makedirs(print_formats_dir, exist_ok=True)

    # Tách từng print format
    for i, pf in enumerate(data, 1):
        if 'name' in pf:
            print(f"🔄 [{i}/{len(data)}] Đang xử lý: {pf['name']}")

            # Tạo tên file an toàn
            safe_name = pf['name'].replace(' ', '_').replace('/', '_').replace('\\', '_')
            filename = os.path.join(print_formats_dir, f"{safe_name}.json")

            # Ghi file JSON (giữ nguyên format gốc)
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump([pf], f, indent=2, ensure_ascii=False)
            print(f"   📄 Created: {safe_name}.json")

            # Tạo file HTML/CSS dễ đọc
            save_html_css_files(pf, print_formats_dir)

    print(f"\n✅ Hoàn thành!")
    print(f"📂 Thư mục output: {print_formats_dir}")
    print(f"📋 Đã tạo {len(data)} files JSON")
    print(f"📄 Các file HTML/CSS trong: {os.path.join(print_formats_dir, 'templates')}")


if __name__ == "__main__":
    split_print_formats()