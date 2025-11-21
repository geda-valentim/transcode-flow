-- =========================================
-- Transcode Flow - Jobs Table Aligned with Python Models
-- Migration: 002
-- Created: 2025-11-19
-- =========================================

-- Drop existing jobs table if it exists (from old schema)
DROP TABLE IF EXISTS jobs CASCADE;

-- =========================================
-- Table: jobs (aligned with app/models/job.py)
-- =========================================
CREATE TABLE jobs (
    -- Primary Key
    id SERIAL PRIMARY KEY,

    -- Foreign Key to api_keys table (nullable for now)
    api_key_id INTEGER,

    -- Job Identification
    job_id VARCHAR(36) UNIQUE NOT NULL,

    -- Status & Priority
    status VARCHAR(20) NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'queued', 'processing', 'completed', 'failed', 'cancelled'
    )),
    priority INTEGER DEFAULT 5 NOT NULL,

    -- Source Video Information
    source_path VARCHAR(2048) NOT NULL,
    source_filename VARCHAR(512) NOT NULL,
    source_size_bytes BIGINT,
    source_duration_seconds DECIMAL(10, 2),
    source_resolution VARCHAR(20),  -- e.g., "1920x1080"
    source_codec VARCHAR(50),
    source_bitrate BIGINT,
    source_fps DECIMAL(5, 2),

    -- Processing Configuration
    target_resolutions JSONB,  -- ["360p", "720p", "1080p"]
    enable_hls BOOLEAN DEFAULT TRUE NOT NULL,
    enable_audio_extraction BOOLEAN DEFAULT FALSE NOT NULL,
    enable_transcription BOOLEAN DEFAULT FALSE NOT NULL,
    transcription_language VARCHAR(10),  -- "auto" or ISO code
    custom_thumbnail_path VARCHAR(2048),

    -- Output Information
    output_path VARCHAR(2048),
    output_formats JSONB,  -- List of generated formats
    hls_manifest_url VARCHAR(2048),
    audio_file_url VARCHAR(2048),
    transcription_url VARCHAR(2048),
    thumbnail_url VARCHAR(2048),

    -- Processing Metrics
    processing_started_at TIMESTAMP WITH TIME ZONE,
    processing_completed_at TIMESTAMP WITH TIME ZONE,
    processing_duration_seconds INTEGER,
    compression_ratio DECIMAL(5, 2),
    output_total_size_bytes BIGINT,

    -- Error Handling
    error_message VARCHAR(2048),
    retry_count INTEGER DEFAULT 0 NOT NULL,

    -- Metadata & Webhooks
    job_metadata JSONB,  -- Flexible JSON storage
    webhook_url VARCHAR(2048),
    webhook_sent BOOLEAN DEFAULT FALSE NOT NULL,

    -- Timestamps
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- =========================================
-- Indexes for jobs table
-- =========================================
CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_api_key_id ON jobs(api_key_id);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);
CREATE INDEX idx_jobs_job_id ON jobs(job_id);
CREATE INDEX idx_jobs_status_priority ON jobs(status, priority DESC);
CREATE INDEX idx_jobs_api_key_status ON jobs(api_key_id, status);

-- =========================================
-- Function to update updated_at timestamp
-- =========================================
CREATE OR REPLACE FUNCTION update_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger for jobs table
DROP TRIGGER IF EXISTS update_jobs_updated_at ON jobs;
CREATE TRIGGER update_jobs_updated_at
    BEFORE UPDATE ON jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_jobs_updated_at();

-- =========================================
-- Comments
-- =========================================
COMMENT ON TABLE jobs IS 'Video transcoding jobs';
COMMENT ON COLUMN jobs.job_metadata IS 'Custom metadata provided by user (JSON format)';
COMMENT ON COLUMN jobs.compression_ratio IS 'Output size / Input size';
