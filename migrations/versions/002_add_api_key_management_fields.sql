-- Migration: Add API Key Management Fields
-- Description: Adds fields for IP filtering, scopes, master/sub-key hierarchy, and rotation tracking
-- Sprint: 7 - NGINX Streaming & API Key Management
-- Date: 2025-11-19

-- Add IP filtering fields
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS ip_whitelist JSONB DEFAULT NULL;
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS ip_blacklist JSONB DEFAULT NULL;

-- Add fine-grained scopes
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS scopes JSONB NOT NULL DEFAULT '["jobs:create", "jobs:read", "jobs:list", "streaming:generate_token"]';

-- Add master/sub-key hierarchy
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS parent_key_id INTEGER DEFAULT NULL;
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS is_master_key BOOLEAN NOT NULL DEFAULT FALSE;

-- Add rotation tracking
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS rotated_from_key_id INTEGER DEFAULT NULL;
ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS rotation_scheduled_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;

-- Create index on parent_key_id for hierarchy queries
CREATE INDEX IF NOT EXISTS idx_api_keys_parent_key_id ON api_keys(parent_key_id);

-- Add foreign key constraint for parent_key_id (self-referencing)
-- Note: This allows a key to reference its parent key
ALTER TABLE api_keys
  ADD CONSTRAINT fk_api_keys_parent_key
  FOREIGN KEY (parent_key_id)
  REFERENCES api_keys(id)
  ON DELETE SET NULL;

-- Add comments for documentation
COMMENT ON COLUMN api_keys.ip_whitelist IS 'JSONB array of allowed IP addresses. If set, only these IPs can use this key.';
COMMENT ON COLUMN api_keys.ip_blacklist IS 'JSONB array of blocked IP addresses. These IPs cannot use this key even if in whitelist.';
COMMENT ON COLUMN api_keys.scopes IS 'JSONB array of permission scopes (e.g., ["jobs:create", "streaming:generate_token"])';
COMMENT ON COLUMN api_keys.parent_key_id IS 'Reference to parent API key for sub-key hierarchy';
COMMENT ON COLUMN api_keys.is_master_key IS 'True if this key can create sub-keys';
COMMENT ON COLUMN api_keys.rotated_from_key_id IS 'Reference to the previous key in the rotation chain';
COMMENT ON COLUMN api_keys.rotation_scheduled_at IS 'When this key should be rotated for security';

-- Rollback instructions (for reference, not executed):
-- ALTER TABLE api_keys DROP CONSTRAINT IF EXISTS fk_api_keys_parent_key;
-- DROP INDEX IF EXISTS idx_api_keys_parent_key_id;
-- ALTER TABLE api_keys DROP COLUMN IF EXISTS rotation_scheduled_at;
-- ALTER TABLE api_keys DROP COLUMN IF EXISTS rotated_from_key_id;
-- ALTER TABLE api_keys DROP COLUMN IF EXISTS is_master_key;
-- ALTER TABLE api_keys DROP COLUMN IF EXISTS parent_key_id;
-- ALTER TABLE api_keys DROP COLUMN IF EXISTS scopes;
-- ALTER TABLE api_keys DROP COLUMN IF EXISTS ip_blacklist;
-- ALTER TABLE api_keys DROP COLUMN IF EXISTS ip_whitelist;
