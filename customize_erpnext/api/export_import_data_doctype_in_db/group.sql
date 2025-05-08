-- SQL Export for DocType: Group
-- Generated on: 2025-05-08 13:12:25
-- Table: tabGroup

DROP TABLE IF EXISTS `tabGroup`;

-- Table structure
CREATE TABLE `tabGroup` (
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
  `group` varchar(140) NULL DEFAULT NULL,
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Data for table `tabGroup`
LOCK TABLES `tabGroup` WRITE;
/*!40000 ALTER TABLE `tabGroup` DISABLE KEYS */;
INSERT INTO `tabGroup` (`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`, `_user_tags`, `_comments`, `_assign`, `_liked_by`, `group`) VALUES
('Accounting', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Accounting'),
('CAD', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'CAD'),
('Canteen', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Canteen'),
('Control', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Control'),
('Deputy Manager of Development&Production Technology', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Deputy Manager of Development&Production Technology'),
('Development&Production Technology', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Development&Production Technology'),
('Factory Manager', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Factory Manager'),
('General supporting', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'General supporting'),
('HR/GA', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'HR/GA'),
('IE', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'IE'),
('Line technique', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Line technique'),
('Logistics', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Logistics'),
('Maintainance', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Maintainance'),
('Mechanic', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Mechanic'),
('Merchandiser', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Merchandiser'),
('Operation Management', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Operation Management'),
('Preparation', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Preparation'),
('Purchasing', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Purchasing'),
('QA', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'QA'),
('QC', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'QC'),
('Sample', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Sample'),
('Sewing', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 1, NULL, NULL, NULL, NULL, 'Sewing'),
('Supply chain management', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Supply chain management'),
('Supporting', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Supporting'),
('Translator', '2025-05-08 09:22:04', '2025-05-08 09:22:04', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Translator'),
('Utility', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Utility'),
('Warehouse', '2025-05-08 09:22:05', '2025-05-08 09:22:05', 'Administrator', 'Administrator', 0, 0, NULL, NULL, NULL, NULL, 'Warehouse');
/*!40000 ALTER TABLE `{table_name}` ENABLE KEYS */;
UNLOCK TABLES;

