-- Migration: Add transcription_status field to jobs table
-- Version: 003
-- Date: 2025-11-21
-- Description: Adds dedicated transcription status tracking for decoupled transcription DAG

-- Create transcription status enum type
DO $$ BEGIN
    CREATE TYPE transcription_status_enum AS ENUM (
        'disabled',      -- Transcription not enabled for this job
        'pending',       -- Waiting to be picked up by transcription DAG
        'queued',        -- Queued in transcription DAG
        'processing',    -- Currently being transcribed
        'completed',     -- Transcription completed successfully
        'failed',        -- Transcription failed
        'skipped'        -- Skipped (e.g., no audio track)
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Add transcription_status column to jobs table
ALTER TABLE jobs
ADD COLUMN IF NOT EXISTS transcription_status transcription_status_enum DEFAULT 'disabled';

-- Add transcription retry tracking
ALTER TABLE jobs
ADD COLUMN IF NOT EXISTS transcription_retry_count INTEGER DEFAULT 0;

-- Add transcription error message
ALTER TABLE jobs
ADD COLUMN IF NOT EXISTS transcription_error_message TEXT;

-- Add transcription timestamps
ALTER TABLE jobs
ADD COLUMN IF NOT EXISTS transcription_started_at TIMESTAMP WITH TIME ZONE;

ALTER TABLE jobs
ADD COLUMN IF NOT EXISTS transcription_completed_at TIMESTAMP WITH TIME ZONE;

-- Add transcription DAG tracking
ALTER TABLE jobs
ADD COLUMN IF NOT EXISTS transcription_dag_run_id VARCHAR(255);

-- Create index for transcription DAG to efficiently find pending jobs
CREATE INDEX IF NOT EXISTS idx_jobs_transcription_pending
ON jobs (transcription_status, created_at)
WHERE transcription_status IN ('pending', 'queued');

-- Update existing jobs: Set transcription_status based on enable_transcription
UPDATE jobs
SET transcription_status = CASE
    WHEN enable_transcription = true AND status = 'completed' THEN 'completed'::transcription_status_enum
    WHEN enable_transcription = true AND status = 'processing' THEN 'pending'::transcription_status_enum
    WHEN enable_transcription = true AND status = 'pending' THEN 'pending'::transcription_status_enum
    WHEN enable_transcription = true AND status = 'failed' THEN 'failed'::transcription_status_enum
    ELSE 'disabled'::transcription_status_enum
END
WHERE transcription_status IS NULL OR transcription_status = 'disabled';

-- Add comment for documentation
COMMENT ON COLUMN jobs.transcription_status IS 'Status of the transcription process (separate from main job status)';
COMMENT ON COLUMN jobs.transcription_dag_run_id IS 'Airflow DAG run ID for the transcription pipeline';
