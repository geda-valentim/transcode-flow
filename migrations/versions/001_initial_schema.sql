-- =========================================
-- Transcode Flow - Initial Database Schema
-- Migration: 001
-- Created: 2025-11-18
-- =========================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For text search

-- =========================================
-- Table: api_keys
-- =========================================
CREATE TABLE api_keys (
    id SERIAL PRIMARY KEY,
    key_hash VARCHAR(64) UNIQUE NOT NULL,
    key_prefix VARCHAR(8) NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,

    -- Ownership
    user_id VARCHAR(100),
    master_key_id INTEGER REFERENCES api_keys(id),

    -- Permissions
    scopes TEXT[] DEFAULT ARRAY['read', 'write'],
    rate_limit_per_minute INTEGER DEFAULT 100,
    rate_limit_per_hour INTEGER DEFAULT 1000,
    rate_limit_per_day INTEGER DEFAULT 10000,

    -- Quotas
    storage_quota_bytes BIGINT DEFAULT NULL,
    storage_used_bytes BIGINT DEFAULT 0,
    max_concurrent_jobs INTEGER DEFAULT 8,
    max_video_size_bytes BIGINT DEFAULT 10737418240, -- 10GB

    -- Security
    ip_whitelist TEXT[] DEFAULT ARRAY[]::TEXT[],
    ip_blacklist TEXT[] DEFAULT ARRAY[]::TEXT[],
    webhook_url VARCHAR(500),
    webhook_secret VARCHAR(64),
    webhook_events TEXT[] DEFAULT ARRAY['job.completed', 'job.failed'],

    -- Status
    is_active BOOLEAN DEFAULT TRUE,
    is_revoked BOOLEAN DEFAULT FALSE,
    expires_at TIMESTAMP,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP,
    revoked_at TIMESTAMP,

    -- Usage tracking
    total_requests BIGINT DEFAULT 0,
    total_jobs_created INTEGER DEFAULT 0
);

-- Indexes for api_keys
CREATE INDEX idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX idx_api_keys_active ON api_keys(is_active, is_revoked);
CREATE INDEX idx_api_keys_expires ON api_keys(expires_at);

-- =========================================
-- Table: jobs
-- =========================================
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    api_key VARCHAR(64) NOT NULL,

    -- Job info
    status VARCHAR(20) NOT NULL CHECK (status IN (
        'queued', 'processing', 'transcoding', 'uploading',
        'completed', 'failed', 'cancelled', 'cleaned_up'
    )),
    priority INTEGER DEFAULT 5 CHECK (priority BETWEEN 1 AND 10),

    -- User metadata
    user_metadata JSONB DEFAULT '{}'::JSONB,

    -- Source info
    original_filename VARCHAR(255),
    source_type VARCHAR(20) DEFAULT 'upload', -- upload, filesystem, minio
    source_path TEXT,
    source_size_bytes BIGINT,
    source_file_hash VARCHAR(64), -- SHA-256 for duplicate detection

    -- Video metadata
    duration_seconds FLOAT,
    source_width INTEGER,
    source_height INTEGER,
    source_resolution VARCHAR(20), -- e.g., "1920x1080"
    source_codec VARCHAR(50),
    source_bitrate BIGINT,
    source_fps FLOAT,

    -- Output paths (MinIO)
    output_360p_path TEXT,
    output_720p_path TEXT,
    output_audio_path TEXT,
    output_hls_360p_path TEXT,
    output_hls_720p_path TEXT,

    -- Transcription paths
    transcription_txt_path TEXT,
    transcription_srt_path TEXT,
    transcription_vtt_path TEXT,
    transcription_json_path TEXT,

    -- Thumbnail paths
    thumbnail_auto_paths TEXT[], -- 5 auto-generated thumbnails
    thumbnail_custom_path TEXT,

    -- Output sizes
    output_360p_size_bytes BIGINT,
    output_720p_size_bytes BIGINT,
    output_audio_size_bytes BIGINT,
    segments_360p_size_bytes BIGINT,
    segments_720p_size_bytes BIGINT,

    -- HLS segments
    segments_360p_count INTEGER,
    segments_720p_count INTEGER,

    -- Processing metrics
    validation_time_seconds INTEGER,
    transcode_360p_time_seconds INTEGER,
    transcode_720p_time_seconds INTEGER,
    audio_extraction_time_seconds INTEGER,
    transcription_time_seconds INTEGER,
    total_processing_time_seconds INTEGER,

    -- Transcription info
    transcription_language VARCHAR(10),
    transcription_word_count INTEGER,
    whisper_model VARCHAR(20), -- tiny, base, small, medium, large

    -- Compression ratios
    compression_ratio_360p FLOAT,
    compression_ratio_720p FLOAT,

    -- Progress tracking
    current_task VARCHAR(50),
    current_task_progress INTEGER DEFAULT 0,

    -- Airflow integration
    airflow_dag_id VARCHAR(100),
    airflow_run_id VARCHAR(100),

    -- Error handling
    error_message TEXT,
    failed_task VARCHAR(50),
    retry_count INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Foreign key
    FOREIGN KEY (api_key) REFERENCES api_keys(key_hash) ON DELETE CASCADE
);

-- Indexes for jobs
CREATE INDEX idx_jobs_api_key ON jobs(api_key);
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_priority ON jobs(priority DESC);
CREATE INDEX idx_jobs_status_priority ON jobs(status, priority DESC, created_at ASC);
CREATE INDEX idx_jobs_created_at ON jobs(created_at DESC);
CREATE INDEX idx_jobs_file_hash ON jobs(source_file_hash, api_key, status);
CREATE INDEX idx_jobs_api_key_status ON jobs(api_key, status);
CREATE INDEX idx_jobs_user_metadata ON jobs USING GIN (user_metadata);

-- =========================================
-- Table: usage_stats (for analytics)
-- =========================================
CREATE TABLE usage_stats (
    id SERIAL PRIMARY KEY,
    api_key VARCHAR(64) NOT NULL,

    -- Timestamp (date for daily aggregation)
    date DATE NOT NULL,

    -- Counters
    total_jobs INTEGER DEFAULT 0,
    completed_jobs INTEGER DEFAULT 0,
    failed_jobs INTEGER DEFAULT 0,

    -- Sizes (in bytes)
    total_input_bytes BIGINT DEFAULT 0,
    total_output_bytes BIGINT DEFAULT 0,

    -- Processing time (in seconds)
    total_processing_time INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),

    -- Unique constraint
    UNIQUE(api_key, date),

    -- Foreign key
    FOREIGN KEY (api_key) REFERENCES api_keys(key_hash) ON DELETE CASCADE
);

-- Index for usage_stats
CREATE INDEX idx_usage_stats_api_key_date ON usage_stats(api_key, date DESC);

-- =========================================
-- Table: system_metrics (for monitoring)
-- =========================================
CREATE TABLE system_metrics (
    id SERIAL PRIMARY KEY,

    -- Metrics
    metric_name VARCHAR(100) NOT NULL,
    metric_value FLOAT NOT NULL,
    metric_labels JSONB DEFAULT '{}'::JSONB,

    -- Timestamp
    timestamp TIMESTAMP DEFAULT NOW()
);

-- Index for system_metrics
CREATE INDEX idx_system_metrics_name_timestamp ON system_metrics(metric_name, timestamp DESC);
CREATE INDEX idx_system_metrics_timestamp ON system_metrics(timestamp DESC);

-- =========================================
-- Functions and Triggers
-- =========================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for jobs table
CREATE TRIGGER update_jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Trigger for usage_stats table
CREATE TRIGGER update_usage_stats_updated_at
    BEFORE UPDATE ON usage_stats
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =========================================
-- Initial Data
-- =========================================

-- Create default admin API key (hash of 'admin_key_CHANGE_ME_123')
-- You should change this in production!
INSERT INTO api_keys (
    key_hash,
    key_prefix,
    name,
    description,
    scopes,
    is_active
) VALUES (
    'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855',
    'admin_ke',
    'Admin Key',
    'Default administrator API key - CHANGE THIS IN PRODUCTION',
    ARRAY['read', 'write', 'admin'],
    TRUE
);

-- =========================================
-- Comments
-- =========================================

COMMENT ON TABLE api_keys IS 'API keys for authentication and authorization';
COMMENT ON TABLE jobs IS 'Video transcoding jobs';
COMMENT ON TABLE usage_stats IS 'Daily usage statistics per API key';
COMMENT ON TABLE system_metrics IS 'System-wide metrics for monitoring';

COMMENT ON COLUMN jobs.user_metadata IS 'Custom metadata provided by user (JSON format)';
COMMENT ON COLUMN jobs.source_file_hash IS 'SHA-256 hash for duplicate detection';
COMMENT ON COLUMN jobs.compression_ratio_360p IS 'Output size / Input size for 360p';
COMMENT ON COLUMN jobs.compression_ratio_720p IS 'Output size / Input size for 720p';
