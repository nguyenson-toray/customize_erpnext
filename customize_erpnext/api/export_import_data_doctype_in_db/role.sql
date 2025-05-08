-- SQL Export for DocType: Role
-- Generated on: 2025-05-08 13:12:25
-- Table: tabRole

DROP TABLE IF EXISTS `tabRole`;

-- Table structure
CREATE TABLE `tabRole` (
  `name` varchar(140) NOT NULL ,
  `creation` datetime NULL DEFAULT NULL,
  `modified` datetime NULL DEFAULT NULL,
  `modified_by` varchar(140) NULL DEFAULT NULL,
  `owner` varchar(140) NULL DEFAULT NULL,
  `docstatus` int NOT NULL DEFAULT 0,
  `idx` int NOT NULL DEFAULT 0,
  `role_name` varchar(140) NULL DEFAULT NULL,
  `home_page` varchar(140) NULL DEFAULT NULL,
  `restrict_to_domain` varchar(140) NULL DEFAULT NULL,
  `disabled` int NOT NULL DEFAULT 0,
  `is_custom` int NOT NULL DEFAULT 0,
  `desk_access` int NOT NULL DEFAULT 1,
  `two_factor_auth` int NOT NULL DEFAULT 0,
  `_user_tags` text NULL DEFAULT NULL,
  `_comments` text NULL DEFAULT NULL,
  `_assign` text NULL DEFAULT NULL,
  `_liked_by` text NULL DEFAULT NULL,
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Data for table `tabRole`
LOCK TABLES `tabRole` WRITE;
/*!40000 ALTER TABLE `tabRole` DISABLE KEYS */;
INSERT INTO `tabRole` (`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`, `role_name`, `home_page`, `restrict_to_domain`, `disabled`, `is_custom`, `desk_access`, `two_factor_auth`, `_user_tags`, `_comments`, `_assign`, `_liked_by`) VALUES
('Academics User', '2024-10-26 11:29:46', '2024-10-26 11:29:46', 'Administrator', 'Administrator', 0, 0, 'Academics User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Accounts Manager', '2024-10-26 11:27:03', '2024-10-26 11:27:03', 'Administrator', 'Administrator', 0, 0, 'Accounts Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Accounts User', '2024-10-26 11:27:03', '2024-10-26 11:27:03', 'Administrator', 'Administrator', 0, 0, 'Accounts User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Administrator', '2024-10-26 11:26:50', '2024-10-26 11:26:50', 'Administrator', 'Administrator', 0, 0, 'Administrator', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Agriculture Manager', '2024-10-26 11:30:02', '2024-10-26 11:30:02', 'Administrator', 'Administrator', 0, 0, 'Agriculture Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Agriculture User', '2024-10-26 11:30:02', '2024-10-26 11:30:02', 'Administrator', 'Administrator', 0, 0, 'Agriculture User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('All', '2024-10-26 11:26:50', '2024-10-26 11:26:50', 'Administrator', 'Administrator', 0, 0, 'All', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Analytics', '2024-10-26 11:30:10', '2024-10-26 11:30:10', 'Administrator', 'Administrator', 0, 0, 'Analytics', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Auditor', '2024-10-26 11:29:22', '2024-10-26 11:29:22', 'Administrator', 'Administrator', 0, 0, 'Auditor', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Blogger', '2024-10-26 11:26:58', '2024-10-26 11:26:58', 'Administrator', 'Administrator', 0, 0, 'Blogger', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Customer', '2024-10-26 11:29:43', '2024-10-26 11:30:11', 'Administrator', 'Administrator', 0, 0, 'Customer', NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL),
('Dashboard Manager', '2024-10-26 11:26:50', '2024-10-26 11:26:50', 'Administrator', 'Administrator', 0, 0, 'Dashboard Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Delivery Manager', '2024-10-26 11:29:44', '2024-10-26 11:29:44', 'Administrator', 'Administrator', 0, 0, 'Delivery Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Delivery User', '2024-10-26 11:29:44', '2024-10-26 11:29:44', 'Administrator', 'Administrator', 0, 0, 'Delivery User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Desk User', '2024-10-26 11:26:50', '2024-10-26 11:26:50', 'Administrator', 'Administrator', 0, 0, 'Desk User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Employee', '2024-10-26 11:29:23', '2024-10-26 11:29:23', 'Administrator', 'Administrator', 0, 0, 'Employee', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Expense Approver', '2024-10-26 13:47:26', '2024-10-26 13:47:26', 'Administrator', 'Administrator', 0, 0, 'Expense Approver', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Fleet Manager', '2024-10-26 11:29:44', '2024-10-26 11:29:44', 'Administrator', 'Administrator', 0, 0, 'Fleet Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Fulfillment User', '2024-10-26 11:29:51', '2024-10-26 11:29:51', 'Administrator', 'Administrator', 0, 0, 'Fulfillment User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Guest', '2024-10-26 11:26:50', '2024-10-26 11:26:50', 'Administrator', 'Administrator', 0, 0, 'Guest', NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL),
('HR Manager', '2024-10-26 11:29:36', '2024-10-26 11:29:36', 'Administrator', 'Administrator', 0, 0, 'HR Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('HR User', '2024-10-26 11:29:41', '2024-10-26 11:29:41', 'Administrator', 'Administrator', 0, 0, 'HR User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Inbox User', '2024-10-26 11:26:53', '2024-10-26 11:26:53', 'Administrator', 'Administrator', 0, 0, 'Inbox User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Insights Admin', '2025-05-06 16:53:46', '2022-12-07 21:36:44', 'Administrator', 'Administrator', 0, 0, 'Insights Admin', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Insights User', '2025-05-06 16:53:46', '2022-12-07 21:36:44', 'Administrator', 'Administrator', 0, 0, 'Insights User', NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL),
('Interviewer', '2024-10-26 13:47:25', '2024-10-26 13:47:25', 'Administrator', 'Administrator', 0, 0, 'Interviewer', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Item Manager', '2024-10-26 11:29:44', '2024-10-26 11:29:44', 'Administrator', 'Administrator', 0, 0, 'Item Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Knowledge Base Contributor', '2024-10-26 11:26:58', '2024-10-26 11:26:58', 'Administrator', 'Administrator', 0, 0, 'Knowledge Base Contributor', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Knowledge Base Editor', '2024-10-26 11:26:58', '2024-10-26 11:26:58', 'Administrator', 'Administrator', 0, 0, 'Knowledge Base Editor', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Leave Approver', '2024-10-26 13:47:31', '2024-10-26 13:47:31', 'Administrator', 'Administrator', 0, 0, 'Leave Approver', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Maintenance Manager', '2024-10-26 11:27:08', '2024-10-26 11:27:08', 'Administrator', 'Administrator', 0, 0, 'Maintenance Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Maintenance User', '2024-10-26 11:27:08', '2024-10-26 11:27:08', 'Administrator', 'Administrator', 0, 0, 'Maintenance User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Manufacturing Manager', '2024-10-26 11:29:38', '2024-10-26 11:29:38', 'Administrator', 'Administrator', 0, 0, 'Manufacturing Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Manufacturing User', '2024-10-26 11:29:41', '2024-10-26 11:29:41', 'Administrator', 'Administrator', 0, 0, 'Manufacturing User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Newsletter Manager', '2024-10-26 11:26:58', '2024-10-26 11:26:58', 'Administrator', 'Administrator', 0, 0, 'Newsletter Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Prepared Report User', '2024-10-26 11:26:54', '2024-10-26 11:26:54', 'Administrator', 'Administrator', 0, 0, 'Prepared Report User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Projects Manager', '2024-10-26 11:29:40', '2024-10-26 11:29:40', 'Administrator', 'Administrator', 0, 0, 'Projects Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Projects User', '2024-10-26 11:29:40', '2024-10-26 11:29:40', 'Administrator', 'Administrator', 0, 0, 'Projects User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Purchase Manager', '2024-10-26 11:27:08', '2024-10-26 11:27:08', 'Administrator', 'Administrator', 0, 0, 'Purchase Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Purchase Master Manager', '2024-10-26 11:27:08', '2024-10-26 11:27:08', 'Administrator', 'Administrator', 0, 0, 'Purchase Master Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Purchase User', '2024-10-26 11:27:03', '2024-10-26 11:27:03', 'Administrator', 'Administrator', 0, 0, 'Purchase User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('QA QC', '2025-02-17 16:34:05', '2025-02-17 16:34:05', 'son.nt@tiqn.com.vn', 'son.nt@tiqn.com.vn', 0, 0, 'QA QC', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Quality Manager', '2024-10-26 11:29:50', '2024-10-26 11:29:50', 'Administrator', 'Administrator', 0, 0, 'Quality Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Report Manager', '2024-10-26 11:26:51', '2024-10-26 11:26:51', 'Administrator', 'Administrator', 0, 0, 'Report Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Sales Manager', '2024-10-26 11:27:08', '2024-10-26 11:27:08', 'Administrator', 'Administrator', 0, 0, 'Sales Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Sales Master Manager', '2024-10-26 11:27:08', '2024-10-26 11:27:08', 'Administrator', 'Administrator', 0, 0, 'Sales Master Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Sales User', '2024-10-26 11:27:03', '2024-10-26 11:27:03', 'Administrator', 'Administrator', 0, 0, 'Sales User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Script Manager', '2024-10-26 11:26:52', '2024-10-26 11:26:52', 'Administrator', 'Administrator', 0, 0, 'Script Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Stock Manager', '2024-10-26 11:29:29', '2024-10-26 11:29:29', 'Administrator', 'Administrator', 0, 0, 'Stock Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Stock User', '2024-10-26 11:29:29', '2024-10-26 11:29:29', 'Administrator', 'Administrator', 0, 0, 'Stock User', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Supplier', '2024-10-26 11:30:09', '2024-10-26 11:30:11', 'Administrator', 'Administrator', 0, 0, 'Supplier', NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL),
('Support Team', '2024-10-26 11:29:59', '2024-10-26 11:29:59', 'Administrator', 'Administrator', 0, 0, 'Support Team', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('System Manager', '2024-10-26 11:26:50', '2024-10-26 11:26:50', 'Administrator', 'Administrator', 0, 0, 'System Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('TIQN Factory Manager', '2024-10-26 16:32:32', '2024-10-26 16:32:32', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 'TIQN Factory Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('TIQN GM of Operation Management', '2024-10-29 16:08:24', '2024-10-29 16:08:24', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 'TIQN GM of Operation Management', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('TIQN Manager', '2024-10-26 16:31:03', '2024-10-26 16:31:03', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 'TIQN Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('TIQN Registration', '2025-05-08 12:30:59', '2025-05-08 12:31:41', 'Administrator', 'Administrator', 0, 0, 'TIQN Registration', '/app/registration', NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('TIQN Staff', '2024-10-28 14:45:23', '2024-10-28 14:45:23', 'it@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 'TIQN Staff', '/app/home', NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Translator', '2024-10-26 11:27:12', '2024-10-26 11:27:12', 'Administrator', 'Administrator', 0, 0, 'Translator', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Website Manager', '2024-10-26 11:26:50', '2024-10-26 11:26:50', 'Administrator', 'Administrator', 0, 0, 'Website Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Wiki Approver', '2025-02-06 11:15:24', '2021-08-21 13:11:40', 'Administrator', 'Administrator', 0, 0, 'Wiki Approver', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL),
('Workspace Manager', '2024-10-26 11:26:51', '2024-10-26 11:26:51', 'Administrator', 'Administrator', 0, 0, 'Workspace Manager', NULL, NULL, 0, 0, 1, 0, NULL, NULL, NULL, NULL);
/*!40000 ALTER TABLE `{table_name}` ENABLE KEYS */;
UNLOCK TABLES;

