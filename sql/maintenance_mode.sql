-- ============================================================================
-- MSREC: maintenance mode
-- Run in the Supabase SQL Editor ONLY if you are not using
--   python manage.py migrate
-- (the migration pages/0024_maintenance_mode does exactly this). Safe to run
-- more than once. Adds four columns to the single site_settings row.
-- ============================================================================
BEGIN;

ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS maintenance_enabled boolean     NOT NULL DEFAULT false;
ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS maintenance_start   timestamptz NULL;
ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS maintenance_end     timestamptz NULL;
ALTER TABLE site_settings ADD COLUMN IF NOT EXISTS maintenance_message text        NOT NULL DEFAULT '';

-- Tell Django this migration is already applied, so `migrate` won't try again.
INSERT INTO django_migrations (app, name, applied)
SELECT 'pages', '0024_maintenance_mode', now()
WHERE NOT EXISTS (
    SELECT 1 FROM django_migrations WHERE app = 'pages' AND name = '0024_maintenance_mode'
);

COMMIT;

-- ============================================================================
-- Handy controls (changes take effect within ~5 seconds)
-- ============================================================================

-- Emergency: reopen the site right now (e.g. if you can't reach the admin area)
--   UPDATE site_settings SET maintenance_enabled = false WHERE id = 1;

-- Lock the site now for two hours (it reopens by itself afterwards)
--   UPDATE site_settings
--      SET maintenance_enabled = true,
--          maintenance_start   = now(),
--          maintenance_end     = now() + interval '2 hours'
--    WHERE id = 1;

-- Schedule a window (times are UTC / GMT)
--   UPDATE site_settings
--      SET maintenance_enabled = true,
--          maintenance_start   = '2026-10-04 22:00+00',
--          maintenance_end     = '2026-10-05 02:00+00',
--          maintenance_message = 'We are upgrading our servers.'
--    WHERE id = 1;

-- See the current settings
--   SELECT maintenance_enabled, maintenance_start, maintenance_end, maintenance_message
--     FROM site_settings WHERE id = 1;

-- ============================================================================
-- Undo (removes the feature's columns -- only do this if you are rolling the
-- code back too)
-- ============================================================================
--   ALTER TABLE site_settings DROP COLUMN IF EXISTS maintenance_enabled;
--   ALTER TABLE site_settings DROP COLUMN IF EXISTS maintenance_start;
--   ALTER TABLE site_settings DROP COLUMN IF EXISTS maintenance_end;
--   ALTER TABLE site_settings DROP COLUMN IF EXISTS maintenance_message;
--   DELETE FROM django_migrations WHERE app = 'pages' AND name = '0024_maintenance_mode';
