-- SQL Export for DocType: Line Team
-- Generated on: 2025-05-08 15:46:32
-- Table: tabLine Team

DROP TABLE IF EXISTS `tabLine Team`;

-- Table structure
CREATE TABLE `tabLine Team` (
  `name` varchar(140) NOT NULL ,
  `creation` datetime NULL DEFAULT NULL,
  `modified` datetime NULL DEFAULT NULL,
  `modified_by` varchar(140) NULL DEFAULT NULL,
  `owner` varchar(140) NULL DEFAULT NULL,
  `docstatus` int NOT NULL DEFAULT 0,
  `idx` int NOT NULL DEFAULT 0,
  `_user_tags` text NULL DEFAULT NULL,
  `_comments` text NULL DEFAULT NULL,
  `_assign` text NULL DEFAULT NULL,
  `_liked_by` text NULL DEFAULT NULL,
  `line_team` varchar(140) NULL DEFAULT NULL,
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Data for table `tabLine Team`
LOCK TABLES `tabLine Team` WRITE;
/*!40000 ALTER TABLE `tabLine Team` DISABLE KEYS */;
INSERT INTO `tabLine Team` (`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`, `_user_tags`, `_comments`, `_assign`, `_liked_by`, `line_team`) VALUES
('Accounting', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Accounting'),
('CAD', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'CAD'),
('Canteen', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Canteen'),
('Control', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Control'),
('Engineering', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Engineering'),
('Factory Manager', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Factory Manager'),
('General supporting', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'General supporting'),
('Grand leader', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Grand leader'),
('HR/GA', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'HR/GA'),
('IE', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'IE'),
('Line 01', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 1, NULL, NULL, NULL, NULL, 'Line 01'),
('Line 02', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line 02'),
('Line 03', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line 03'),
('Line 04', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line 04'),
('Line 05', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line 05'),
('Line 06', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line 06'),
('Line 07', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line 07'),
('Line 08', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line 08'),
('Line 09', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line 09'),
('Line 10', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line 10'),
('Line 11', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line 11'),
('Line 12', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line 12'),
('Line technique', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line technique'),
('Logistics', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Logistics'),
('Merchandiser', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Merchandiser'),
('Preparation', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Preparation'),
('Purchasing', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Purchasing'),
('QA', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'QA'),
('QC', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'QC'),
('Sample', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Sample'),
('Technical A', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Technical A'),
('Technical B', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Technical B'),
('Trainees', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Trainees'),
('Translator', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Translator'),
('Utilities', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Utilities'),
('Warehouse', '2025-05-08 11:25:16', '2025-05-08 11:25:16', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Warehouse');
/*!40000 ALTER TABLE `tabLine Team` ENABLE KEYS */;
UNLOCK TABLES;

