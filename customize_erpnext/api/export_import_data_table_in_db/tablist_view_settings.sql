-- SQL Export for Table: tabList View Settings
-- Generated on: 2025-06-14 13:08:10
-- Records: 18

SET SQL_MODE = "NO_AUTO_VALUE_ON_ZERO";
SET AUTOCOMMIT = 0;
START TRANSACTION;
SET time_zone = "+00:00";

DROP TABLE IF EXISTS `tabList View Settings`;

-- Table structure for `tabList View Settings`
CREATE TABLE `tabList View Settings` (
  `name` VARCHAR(140) NOT NULL,
  `creation` DATETIME DEFAULT NULL,
  `modified` DATETIME DEFAULT NULL,
  `modified_by` VARCHAR(140) DEFAULT 'NULL',
  `owner` VARCHAR(140) DEFAULT 'NULL',
  `docstatus` INT(11) NOT NULL DEFAULT 0,
  `idx` INT(11) NOT NULL DEFAULT 0,
  `disable_count` INT(11) NOT NULL DEFAULT 0,
  `disable_comment_count` INT(11) NOT NULL DEFAULT 0,
  `disable_sidebar_stats` INT(11) NOT NULL DEFAULT 0,
  `disable_auto_refresh` INT(11) NOT NULL DEFAULT 0,
  `allow_edit` INT(11) NOT NULL DEFAULT 0,
  `total_fields` VARCHAR(140) DEFAULT 'NULL',
  `fields` LONGTEXT DEFAULT 'NULL',
  `_user_tags` TEXT DEFAULT 'NULL',
  `_comments` TEXT DEFAULT 'NULL',
  `_assign` TEXT DEFAULT 'NULL',
  `_liked_by` TEXT DEFAULT 'NULL',
  `disable_automatic_recency_filters` INT(11) NOT NULL DEFAULT 0,
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Data for table `tabList View Settings`
LOCK TABLES `tabList View Settings` WRITE;
/*!40000 ALTER TABLE `tabList View Settings` DISABLE KEYS */;

INSERT INTO `tabList View Settings` (`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`, `disable_count`, `disable_comment_count`, `disable_sidebar_stats`, `disable_auto_refresh`, `allow_edit`, `total_fields`, `fields`, `_user_tags`, `_comments`, `_assign`, `_liked_by`, `disable_automatic_recency_filters`) VALUES
('BOM', '2024-12-03 08:28:15', '2025-03-20 10:10:51', 'son.nt@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '9', '[{"fieldname":"name","label":"ID"},{"fieldname":"status_field","label":"Status"},{"fieldname":"item","label":"Item"},{"fieldname":"custom_item_name_detail","label":"Item Name Detail"},{"fieldname":"total_cost","label":"Total Cost"}]', NULL, NULL, NULL, NULL, 0),
('Brand', '2025-02-26 08:17:09', '2025-02-26 08:17:28', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '8', '[{"label":"ID","fieldname":"name"},{"label":"Description","fieldname":"description"},{"label":"Brand Code","fieldname":"custom_brand_code"},{"label":"Brand Name","fieldname":"brand"}]', NULL, NULL, NULL, NULL, 0),
('Deleted Document', '2025-03-04 08:35:46', '2025-03-04 08:35:46', 'son.nt@tiqn.com.vn', 'son.nt@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '6', '[{"label":"Deleted Name","fieldname":"deleted_name"},{"label":"Deleted DocType","fieldname":"deleted_doctype"},{"label":"Restored","fieldname":"restored"},{"label":"Data","fieldname":"data"}]', NULL, NULL, NULL, NULL, 0),
('Employee', '2024-10-28 13:54:33', '2025-05-17 16:26:57', 'Administrator', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '7', '[{"fieldname":"employee_name","label":"Full Name"},{"fieldname":"attendance_device_id","label":"Attendance Device ID (Biometric/RF tag ID)"},{"fieldname":"status_field","label":"Status"},{"fieldname":"department","label":"Department"},{"fieldname":"designation","label":"Designation"}]', NULL, NULL, NULL, NULL, 0),
('Inspection', '2024-12-27 11:27:26', '2024-12-31 11:21:22', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '8', '[{"label":"ID","fieldname":"name"},{"label":"Date / Ngày","fieldname":"date"},{"label":"NG / SL lỗi","fieldname":"ng"},{"label":"Qty / SL kiểm","fieldname":"quantity"},{"label":"Work Order / Lệnh sản xuất","fieldname":"work_order"},{"label":"1st - 2nd Inspection / Kiểm sơ cấp - thứ cấp","fieldname":"inspection12"}]', NULL, NULL, NULL, NULL, 0),
('Item', '2024-10-26 16:38:13', '2025-03-18 09:32:42', 'son.nt@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '8', '[{"fieldname":"item_name","label":"Item Name"},{"fieldname":"custom_item_name_detail","label":"Item Name Detail"},{"fieldname":"status_field","label":"Status"},{"fieldname":"stock_uom","label":"Default Unit of Measure"},{"fieldname":"item_group","label":"Item Group"}]', NULL, NULL, NULL, NULL, 0),
('Item Group', '2025-02-18 13:45:10', '2025-02-18 13:45:10', 'son.nt@tiqn.com.vn', 'son.nt@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '5', '[{"label":"ID","fieldname":"name"},{"label":"Is Group","fieldname":"is_group"},{"label":"Item Group Name","fieldname":"item_group_name"},{"label":"Parent Item Group","fieldname":"parent_item_group"}]', NULL, NULL, NULL, NULL, 0),
('Job Card', '2024-12-24 10:16:00', '2024-12-24 10:16:00', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '6', '[{"fieldname":"operation","label":"Operation"},{"fieldname":"item_name","label":"Item Name"},{"fieldname":"status_field","label":"Status"},{"fieldname":"for_quantity","label":"Qty To Manufacture"},{"fieldname":"work_order","label":"Work Order"},{"fieldname":"workstation","label":"Workstation"}]', NULL, NULL, NULL, NULL, 0),
('Material Request', '2024-10-29 10:44:56', '2024-12-12 15:41:08', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '8', '[{"label":"Title","fieldname":"title"},{"type":"Status","label":"Status","fieldname":"status_field"},{"label":"+ Total Amount","fieldname":"custom_total_amount"},{"label":"Purpose","fieldname":"material_request_type"},{"label":"Required By","fieldname":"schedule_date"},{"label":"Workflow State","fieldname":"workflow_state"},{"label":"Note","fieldname":"custom_note"}]', NULL, NULL, NULL, NULL, 0),
('Production Plan', '2024-12-11 15:30:48', '2024-12-11 15:31:24', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '8', '[{"fieldname":"name","label":"ID"},{"fieldname":"status_field","label":"Status"},{"fieldname":"customer","label":"Customer"},{"fieldname":"get_items_from","label":"Get Items From"},{"fieldname":"posting_date","label":"Posting Date"},{"fieldname":"custom_note","label":"Note"}]', NULL, NULL, NULL, NULL, 0),
('Purchase Request', '2024-10-26 16:28:20', '2024-10-26 16:28:20', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '5', '[{"label":"ID","fieldname":"name"},{"label":"Bộ phận / Department","fieldname":"department"},{"label":"Mục đích/ Purpose:","fieldname":"purpose"},{"label":"Ngày yêu cầu / Request date","fieldname":"request_date"},{"label":"Thời gian muốn nhận / ETA:","fieldname":"eta"}]', NULL, NULL, NULL, NULL, 0),
('Report', '2025-05-09 08:57:18', '2025-05-09 08:57:46', 'Administrator', 'Administrator', 0, 0, 0, 0, 0, 0, 0, '7', '[{"label":"ID","fieldname":"name"},{"type":"Status","label":"Status","fieldname":"status_field"},{"label":"Is Standard","fieldname":"is_standard"},{"label":"Ref DocType","fieldname":"ref_doctype"},{"label":"Report Type","fieldname":"report_type"},{"label":"Report Name","fieldname":"report_name"}]', NULL, NULL, NULL, NULL, 0),
('Stock Entry', '2024-11-27 14:12:54', '2025-06-14 12:43:44', 'Administrator', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '10', '[{"fieldname":"stock_entry_type","label":"Stock Entry Type"},{"fieldname":"status_field","label":"Status"},{"fieldname":"purpose","label":"Purpose"},{"fieldname":"custom_no","label":"No#"},{"fieldname":"custom_declaration_invoice_number","label":"Declaration Invoice number"},{"fieldname":"custom_invoice_number","label":"Invoice number"},{"fieldname":"from_warehouse","label":"Default Source Warehouse"},{"fieldname":"to_warehouse","label":"Default Target Warehouse"},{"fieldname":"per_transferred","label":"Per Transferred"},{"fieldname":"posting_date","label":"Posting Date"}]', NULL, NULL, NULL, NULL, 0),
('Supplier', '2025-02-20 10:18:26', '2025-02-20 10:18:26', 'son.nt@tiqn.com.vn', 'son.nt@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '5', '[{"label":"Supplier Name","fieldname":"supplier_name"},{"type":"Status","label":"Status","fieldname":"status_field"},{"label":"Supplier Group","fieldname":"supplier_group"},{"label":"Supplier Name (Short)","fieldname":"custom_supplier_name_short"}]', NULL, NULL, NULL, NULL, 0),
('Translation', '2025-02-25 21:48:24', '2025-02-25 21:48:24', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '5', '[{"label":"Tiêu đề nguồn","fieldname":"source_text"},{"label":"văn bản đã được dịch","fieldname":"translated_text"},{"label":"Ngôn ngữ","fieldname":"language"}]', NULL, NULL, NULL, NULL, 0),
('Warehouse', '2024-11-20 09:38:21', '2025-05-07 13:14:07', 'Administrator', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '7', '[{"fieldname":"name","label":"ID"},{"fieldname":"status_field","label":"Status"},{"fieldname":"is_group","label":"Is Group Warehouse"},{"fieldname":"warehouse_name","label":"Warehouse Name"},{"fieldname":"account","label":"Account"}]', NULL, NULL, NULL, NULL, 0),
('Work Order', '2024-12-17 16:02:45', '2024-12-17 16:03:04', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '6', '[{"fieldname":"production_item","label":"Item To Manufacture"},{"fieldname":"item_name","label":"Item Name"},{"fieldname":"status_field","label":"Status"}]', NULL, NULL, NULL, NULL, 0),
('Workspace', '2024-12-20 14:26:04', '2024-12-20 14:26:04', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 0, 0, 0, 0, 0, '7', '[{"label":"ID","fieldname":"name"},{"label":"Module","fieldname":"module"},{"label":"Name","fieldname":"label"},{"label":"Public","fieldname":"public"},{"label":"Icon","fieldname":"icon"}]', NULL, NULL, NULL, NULL, 0);

/*!40000 ALTER TABLE `tabList View Settings` ENABLE KEYS */;
UNLOCK TABLES;

COMMIT;
