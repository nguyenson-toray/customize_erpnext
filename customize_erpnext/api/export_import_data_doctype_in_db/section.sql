-- SQL Export for DocType: Section
-- Generated on: 2025-05-08 11:27:58
-- Table: tabSection

DROP TABLE IF EXISTS `tabSection`;

-- Table structure
CREATE TABLE `tabSection` (
  `name` varchar(140) NOT NULL ,
  `creation` datetime NULL DEFAULT NULL,
  `modified` datetime NULL DEFAULT NULL,
  `modified_by` varchar(140) NULL DEFAULT NULL,
  `owner` varchar(140) NULL DEFAULT NULL,
  `docstatus` int NOT NULL DEFAULT 0,
  `idx` int NOT NULL DEFAULT 0,
  `department_name` varchar(140) NULL DEFAULT NULL,
  `parent_department` varchar(140) NULL DEFAULT NULL,
  `company` varchar(140) NULL DEFAULT NULL,
  `is_group` int NOT NULL DEFAULT 0,
  `disabled` int NOT NULL DEFAULT 0,
  `lft` int NOT NULL DEFAULT 0,
  `rgt` int NOT NULL DEFAULT 0,
  `old_parent` varchar(140) NULL DEFAULT NULL,
  `_user_tags` text NULL DEFAULT NULL,
  `_comments` text NULL DEFAULT NULL,
  `_assign` text NULL DEFAULT NULL,
  `_liked_by` text NULL DEFAULT NULL,
  `section` varchar(140) NULL DEFAULT NULL,
  `parent_section` varchar(140) NULL DEFAULT NULL,
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Data for table `tabSection`
LOCK TABLES `tabSection` WRITE;
/*!40000 ALTER TABLE `tabSection` DISABLE KEYS */;
INSERT INTO `tabSection` (`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`, `department_name`, `parent_department`, `company`, `is_group`, `disabled`, `lft`, `rgt`, `old_parent`, `_user_tags`, `_comments`, `_assign`, `_liked_by`, `section`, `parent_section`) VALUES
('Accounting', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'Accounting', NULL),
('Canteen', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'Canteen', NULL),
('Development&Production Technology', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'Development&Production Technology', NULL),
('Engineering', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'Engineering', NULL),
('Factory Manager', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'Factory Manager', NULL),
('HR/GA', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'HR/GA', NULL),
('Operation Management', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'Operation Management', NULL),
('Pattern', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'Pattern', NULL),
('Preparation', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'Preparation', NULL),
('Production', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'Production', NULL),
('Purchasing', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'Purchasing', NULL),
('QA', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'QA', NULL),
('QA/QC', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'QA/QC', NULL),
('Supply chain management', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'Supply chain management', NULL),
('Warehouse', '2025-05-08 09:16:51', '2025-05-08 09:16:51', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, 0, 0, 0, 0, NULL, NULL, NULL, NULL, NULL, 'Warehouse', NULL);
/*!40000 ALTER TABLE `{table_name}` ENABLE KEYS */;
UNLOCK TABLES;

