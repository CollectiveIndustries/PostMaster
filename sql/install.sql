/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET NAMES utf8 */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

-- Dumping database structure for postmaster_db
DROP DATABASE IF EXISTS `postmaster_db`;
CREATE DATABASE IF NOT EXISTS `postmaster_db` /*!40100 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci */;
USE `postmaster_db`;

-- Dumping structure for table postmaster_db.classifications
DROP TABLE IF EXISTS `classifications`;
CREATE TABLE IF NOT EXISTS `classifications` (
  `classification_id` varchar(50) NOT NULL,
  `description` text DEFAULT NULL,
  `is_dynamic` tinyint(1) DEFAULT 0,
  PRIMARY KEY (`classification_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table postmaster_db.classification_folders
DROP TABLE IF EXISTS `classification_folders`;
CREATE TABLE IF NOT EXISTS `classification_folders` (
  `map_id` bigint(20) NOT NULL AUTO_INCREMENT,
  `classification_id` varchar(50) NOT NULL,
  `folder_name` varchar(255) NOT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`map_id`),
  UNIQUE KEY `folder_name` (`folder_name`),
  KEY `classification_id` (`classification_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table postmaster_db.email_hashes
DROP TABLE IF EXISTS `email_hashes`;
CREATE TABLE IF NOT EXISTS `email_hashes` (
  `hash_id` char(64) NOT NULL,
  `classification_id` varchar(50) NOT NULL DEFAULT '-1',
  `additional_classification_ids` longtext CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DEFAULT NULL CHECK (json_valid(`additional_classification_ids`)),
  `X_GM_MSGID` bigint(20) unsigned DEFAULT NULL,
  `trained` tinyint(1) DEFAULT 0,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`hash_id`),
  UNIQUE KEY `X_GM_MSGID` (`X_GM_MSGID`),
  KEY `idx_email_hashes_classification` (`classification_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table postmaster_db.email_processing_log
DROP TABLE IF EXISTS `email_processing_log`;
CREATE TABLE IF NOT EXISTS `email_processing_log` (
  `log_id` bigint(20) NOT NULL AUTO_INCREMENT,
  `sequence_number` varchar(20) NOT NULL,
  `hash_id` char(64) DEFAULT NULL,
  `source_folder` varchar(255) NOT NULL,
  `destination_folder` varchar(255) NOT NULL,
  `status` varchar(20) NOT NULL,
  `created_at` timestamp NULL DEFAULT current_timestamp(),
  PRIMARY KEY (`log_id`),
  KEY `hash_id` (`hash_id`),
  KEY `idx_log_status` (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

-- Dumping structure for table postmaster_db.mail_que
DROP TABLE IF EXISTS `mail_que`;
CREATE TABLE IF NOT EXISTS `mail_que` (
  `id` int(11) NOT NULL AUTO_INCREMENT,
  `x_gm_msgid` bigint(20) NOT NULL,
  `added_at` timestamp NULL DEFAULT current_timestamp(),
  `processed` tinyint(1) DEFAULT 0,
  `thread_marker` varchar(50) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `x_gm_msgid` (`x_gm_msgid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

-- Data exporting was unselected.

/*!40103 SET TIME_ZONE=IFNULL(@OLD_TIME_ZONE, 'system') */;
/*!40101 SET SQL_MODE=IFNULL(@OLD_SQL_MODE, '') */;
/*!40014 SET FOREIGN_KEY_CHECKS=IFNULL(@OLD_FOREIGN_KEY_CHECKS, 1) */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40111 SET SQL_NOTES=IFNULL(@OLD_SQL_NOTES, 1) */;
