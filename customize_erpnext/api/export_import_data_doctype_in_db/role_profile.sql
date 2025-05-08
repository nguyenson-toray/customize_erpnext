-- SQL Export for DocType: Role Profile
-- Generated on: 2025-05-08 15:46:32
-- Table: tabRole Profile

DROP TABLE IF EXISTS `tabRole Profile`;

-- Table structure
CREATE TABLE `tabRole Profile` (
  `name` varchar(140) NOT NULL ,
  `creation` datetime NULL DEFAULT NULL,
  `modified` datetime NULL DEFAULT NULL,
  `modified_by` varchar(140) NULL DEFAULT NULL,
  `owner` varchar(140) NULL DEFAULT NULL,
  `docstatus` int NOT NULL DEFAULT 0,
  `idx` int NOT NULL DEFAULT 0,
  `role_profile` varchar(140) NULL DEFAULT NULL,
  `_user_tags` text NULL DEFAULT NULL,
  `_comments` text NULL DEFAULT NULL,
  `_assign` text NULL DEFAULT NULL,
  `_liked_by` text NULL DEFAULT NULL,
  PRIMARY KEY (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Data for table `tabRole Profile`
LOCK TABLES `tabRole Profile` WRITE;
/*!40000 ALTER TABLE `tabRole Profile` DISABLE KEYS */;
INSERT INTO `tabRole Profile` (`name`, `creation`, `modified`, `modified_by`, `owner`, `docstatus`, `idx`, `role_profile`, `_user_tags`, `_comments`, `_assign`, `_liked_by`) VALUES
('Accounts', '2024-10-26 11:30:11', '2025-02-17 13:45:15', 'erp@tiqn.com.vn', 'Administrator', 0, 1, 'Accounts', NULL, NULL, NULL, NULL),
('HR', '2025-02-17 14:24:36', '2025-02-17 14:24:36', 'erp@tiqn.com.vn', 'erp@tiqn.com.vn', 0, 0, 'HR', NULL, NULL, NULL, NULL),
('Inventory', '2024-10-26 11:30:11', '2025-02-18 15:47:33', 'son.nt@tiqn.com.vn', 'Administrator', 0, 0, 'Inventory', NULL, NULL, NULL, NULL),
('Manufacturing', '2024-10-26 11:30:11', '2025-02-17 13:47:35', 'erp@tiqn.com.vn', 'Administrator', 0, 0, 'Manufacturing', NULL, NULL, NULL, NULL),
('MD', '2025-02-28 09:35:08', '2025-02-28 09:52:46', 'son.nt@tiqn.com.vn', 'son.nt@tiqn.com.vn', 0, 1, 'MD', NULL, NULL, NULL, NULL),
('Purchase', '2024-10-26 11:30:11', '2025-02-20 14:39:20', 'son.nt@tiqn.com.vn', 'Administrator', 0, 1, 'Purchase', NULL, NULL, NULL, NULL),
('Purchase Manager', '2025-02-20 14:39:13', '2025-02-20 14:39:13', 'son.nt@tiqn.com.vn', 'son.nt@tiqn.com.vn', 0, 0, 'Purchase Manager', NULL, NULL, NULL, NULL),
('QA QC', '2025-02-17 16:37:44', '2025-02-17 16:37:44', 'son.nt@tiqn.com.vn', 'son.nt@tiqn.com.vn', 0, 0, 'QA QC', NULL, NULL, NULL, NULL),
('Sales', '2024-10-26 11:30:11', '2024-12-14 12:50:40', 'it@tiqn.com.vn', 'Administrator', 0, 2, 'Sales', NULL, NULL, NULL, NULL),
('TIQN All Employee', '2025-05-08 12:30:17', '2025-05-08 12:38:12', 'Administrator', 'Administrator', 0, 4, 'TIQN All Employee', NULL, NULL, NULL, NULL),
('TIQN Staff', '2025-01-22 15:53:31', '2025-02-17 13:46:12', 'erp@tiqn.com.vn', 'it@tiqn.com.vn', 0, 0, 'TIQN Staff', NULL, NULL, NULL, NULL),
('Warehouse', '2025-02-18 15:48:23', '2025-02-18 15:48:23', 'son.nt@tiqn.com.vn', 'son.nt@tiqn.com.vn', 0, 0, 'Warehouse', NULL, NULL, NULL, NULL);
/*!40000 ALTER TABLE `tabRole Profile` ENABLE KEYS */;
UNLOCK TABLES;

