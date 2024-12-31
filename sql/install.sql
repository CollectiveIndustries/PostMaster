-- Drop existing tables if they exist
DROP TABLE IF EXISTS email_processing_log;
DROP TABLE IF EXISTS classification_folders;
DROP TABLE IF EXISTS classifications;
DROP TABLE IF EXISTS email_hashes;

-- Table to store email hashes, their classifications, and the X-GM-MSGID
CREATE TABLE email_hashes (
    hash_id CHAR(64) PRIMARY KEY,           -- SHA256 hash as a unique identifier
    classification_id VARCHAR(50) NOT NULL, -- Classification label (e.g., 'spam', 'ham')
    additional_classification_ids JSON DEFAULT NULL, -- JSON array for additional classification numbers
    X_GM_MSGID BIGINT UNSIGNED,             -- X-GM-MSGID for Gmail-specific email identification
    trained BOOLEAN DEFAULT FALSE,         -- Flag to indicate if the email has been trained
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- Timestamp of when the hash was added
);

-- Table to store classification metadata (optional, for extensibility)
CREATE TABLE classifications (
    classification_id VARCHAR(50) PRIMARY KEY, -- Unique classification label
    description TEXT,                          -- Description of the classification
    is_dynamic BOOLEAN DEFAULT FALSE           -- Flag to indicate dynamic label generation (e.g., NN-based)
);

-- Table to map classification IDs to folder names
CREATE TABLE classification_folders (
    map_id BIGINT AUTO_INCREMENT PRIMARY KEY, -- Auto-incremented map ID
    classification_id VARCHAR(50) NOT NULL,  -- Foreign key to classifications
    folder_name VARCHAR(255) NOT NULL,       -- Folder name in email client (e.g., Gmail)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Timestamp of when the mapping was added
    FOREIGN KEY (classification_id) REFERENCES classifications(classification_id)
);

-- Table to log email processing (optional, for debugging and tracking)
CREATE TABLE email_processing_log (
    log_id BIGINT AUTO_INCREMENT PRIMARY KEY, -- Auto-incremented log ID
    sequence_number VARCHAR(20) NOT NULL,    -- Email sequence number
    hash_id CHAR(64),                        -- Foreign key to email_hashes
    source_folder VARCHAR(255) NOT NULL,    -- Source folder name
    destination_folder VARCHAR(255) NOT NULL, -- Destination folder name
    status VARCHAR(20) NOT NULL,            -- Status (e.g., 'moved', 'skipped')
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, -- Log timestamp
    FOREIGN KEY (hash_id) REFERENCES email_hashes(hash_id)
);

-- Optional indexes for performance
CREATE INDEX idx_email_hashes_classification ON email_hashes (classification_id);
CREATE INDEX idx_log_status ON email_processing_log (status);
CREATE INDEX idx_email_hashes_x_gm_msgid ON email_hashes (X_GM_MSGID); -- Index for the X-GM-MSGID column
