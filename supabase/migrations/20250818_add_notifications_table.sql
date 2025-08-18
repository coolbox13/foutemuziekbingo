-- Migration: Add notifications table for user notifications
-- Author: Claude Code Assistant
-- Date: 2025-01-18
-- Issue: CRIT-003 - User notification system database schema

-- Create notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    notification_type VARCHAR(50) NOT NULL,
    priority VARCHAR(20) NOT NULL DEFAULT 'medium',
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    action_url VARCHAR(500),
    action_text VARCHAR(100),
    metadata JSONB,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE,
    read BOOLEAN NOT NULL DEFAULT FALSE,
    dismissed BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_notifications_user_id ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, read) WHERE NOT dismissed;
CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(notification_type);
CREATE INDEX IF NOT EXISTS idx_notifications_created_at ON notifications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_notifications_expires_at ON notifications(expires_at) WHERE expires_at IS NOT NULL;

-- Create partial indexes for common queries
CREATE INDEX IF NOT EXISTS idx_notifications_unread_active ON notifications(user_id, created_at DESC) 
WHERE read = FALSE AND dismissed = FALSE AND (expires_at IS NULL OR expires_at > NOW());

-- Add comments for documentation
COMMENT ON TABLE notifications IS 'User notifications for token management and system events';
COMMENT ON COLUMN notifications.id IS 'Unique notification identifier';
COMMENT ON COLUMN notifications.user_id IS 'User who should receive this notification';
COMMENT ON COLUMN notifications.notification_type IS 'Type of notification (token_expiry_warning, reauth_required, etc.)';
COMMENT ON COLUMN notifications.priority IS 'Notification priority: low, medium, high, critical';
COMMENT ON COLUMN notifications.title IS 'Short notification title';
COMMENT ON COLUMN notifications.message IS 'Full notification message';
COMMENT ON COLUMN notifications.action_url IS 'Optional URL for user action (e.g., login link)';
COMMENT ON COLUMN notifications.action_text IS 'Optional text for action button';
COMMENT ON COLUMN notifications.metadata IS 'Additional structured data for the notification';
COMMENT ON COLUMN notifications.expires_at IS 'When this notification should expire (optional)';
COMMENT ON COLUMN notifications.read IS 'Whether the user has read this notification';
COMMENT ON COLUMN notifications.dismissed IS 'Whether the user has dismissed this notification';
