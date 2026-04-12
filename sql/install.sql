-- ============================================
-- PostMaster Database Schema
-- ============================================

-- Drop tables if they exist (for clean install)
DROP TABLE IF EXISTS email_processing_log;
DROP TABLE IF EXISTS mail_que;
DROP TABLE IF EXISTS classification_folders;
DROP TABLE IF EXISTS email_hashes;
DROP TABLE IF EXISTS classifications;

-- ============================================
-- Classifications Table
-- Stores classification types (0=Spam, 1=Ham, etc.)
-- ============================================
CREATE TABLE classifications (
    classification_id INT PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    is_dynamic BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default classifications
INSERT INTO classifications (classification_id, description, is_dynamic) VALUES
(0, 'Spam - Unsolicited bulk email', FALSE),
(1, 'Ham - Legitimate email', FALSE),
(2, 'Unsorted - Awaiting classification', FALSE),
(3, 'Infected - Contains malware or suspicious content', FALSE);

-- ============================================
-- Classification Folders Table
-- Maps classification IDs to IMAP folder names
-- ============================================
CREATE TABLE classification_folders (
    classification_id INT NOT NULL,
    folder_name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (classification_id, folder_name),
    FOREIGN KEY (classification_id) REFERENCES classifications(classification_id) ON DELETE CASCADE
);

-- ============================================
-- Email Hashes Table
-- Stores unique email identifiers for deduplication
-- ============================================
CREATE TABLE email_hashes (
    hash_id VARCHAR(64) PRIMARY KEY,
    x_gm_msgid VARCHAR(64) UNIQUE NOT NULL,
    classification_id INT,
    trained BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (classification_id) REFERENCES classifications(classification_id) ON DELETE SET NULL
);

-- ============================================
-- Mail Queue Table
-- Manages email processing queue for training and classification
-- ============================================
CREATE TABLE mail_que (
    x_gm_msgid VARCHAR(64) PRIMARY KEY,
    thread_marker VARCHAR(50) NOT NULL,  -- 'Trainer-Spam', 'Trainer-Ham', 'PostMan'
    processed TINYINT DEFAULT 0,          -- 0=Not processed, 1=Processed
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP NULL,
    INDEX idx_thread_marker (thread_marker),
    INDEX idx_processed (processed),
    INDEX idx_thread_processed (thread_marker, processed)
);

-- ============================================
-- Email Processing Log Table
-- Audit log of all email processing actions
-- ============================================
CREATE TABLE email_processing_log (
    log_id INT AUTO_INCREMENT PRIMARY KEY,
    sequence_number VARCHAR(64) NOT NULL,
    hash_id VARCHAR(64) NOT NULL,
    source_folder VARCHAR(255) NOT NULL,
    destination_folder VARCHAR(255) NOT NULL,
    status VARCHAR(50) NOT NULL,  -- 'trained', 'processed', 'failed', 'skipped'
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_hash_id (hash_id),
    INDEX idx_sequence (sequence_number),
    INDEX idx_processed_at (processed_at),
    FOREIGN KEY (hash_id) REFERENCES email_hashes(hash_id) ON DELETE CASCADE
);

-- ============================================
-- Views for easier monitoring
-- ============================================

-- View: Queue Status
CREATE OR REPLACE VIEW v_queue_status AS
SELECT
    thread_marker,
    COUNT(*) as total_queued,
    SUM(CASE WHEN processed = 0 THEN 1 ELSE 0 END) as pending,
    SUM(CASE WHEN processed = 1 THEN 1 ELSE 0 END) as completed,
    MIN(added_at) as oldest,
    MAX(processed_at) as latest_processed
FROM mail_que
GROUP BY thread_marker;

-- View: Processing Summary
CREATE OR REPLACE VIEW v_processing_summary AS
SELECT
    DATE(processed_at) as date,
    source_folder,
    destination_folder,
    status,
    COUNT(*) as count
FROM email_processing_log
GROUP BY DATE(processed_at), source_folder, destination_folder, status
ORDER BY date DESC;

-- View: Classification Distribution
CREATE OR REPLACE VIEW v_classification_distribution AS
SELECT
    c.classification_id,
    c.description,
    COUNT(eh.hash_id) as total_emails,
    SUM(CASE WHEN eh.trained = 1 THEN 1 ELSE 0 END) as trained_count
FROM classifications c
LEFT JOIN email_hashes eh ON c.classification_id = eh.classification_id
GROUP BY c.classification_id, c.description;

-- ============================================
-- Indexes for performance optimization
-- ============================================

-- Additional indexes for common queries
CREATE INDEX idx_mail_que_added_at ON mail_que(added_at);
CREATE INDEX idx_email_hashes_classification ON email_hashes(classification_id);
CREATE INDEX idx_email_hashes_trained ON email_hashes(trained);
CREATE INDEX idx_processing_log_destination ON email_processing_log(destination_folder);

-- ============================================
-- Stored Procedure: Clean old queue entries
-- ============================================
DELIMITER //

CREATE PROCEDURE clean_old_queue_entries(IN days_old INT)
BEGIN
    DELETE FROM mail_que
    WHERE processed = 1
    AND processed_at < DATE_SUB(NOW(), INTERVAL days_old DAY);
END //

DELIMITER ;

-- ============================================
-- Stored Procedure: Get processing statistics
-- ============================================
DELIMITER //

CREATE PROCEDURE get_processing_stats()
BEGIN
    SELECT
        'Total Processed' as metric,
        COUNT(*) as value
    FROM email_processing_log

    UNION ALL

    SELECT
        'Currently Queued',
        COUNT(*)
    FROM mail_que
    WHERE processed = 0

    UNION ALL

    SELECT
        'Completed Training',
        COUNT(*)
    FROM email_hashes
    WHERE trained = 1;
END //

DELIMITER ;

-- ============================================
-- Initial folder mappings
-- ============================================
INSERT INTO classification_folders (classification_id, folder_name) VALUES
(0, 'INBOX/Spam'),
(1, 'INBOX/Ham'),
(2, 'INBOX/Unsorted'),
(3, 'INBOX/Infected')
ON DUPLICATE KEY UPDATE folder_name = VALUES(folder_name);
