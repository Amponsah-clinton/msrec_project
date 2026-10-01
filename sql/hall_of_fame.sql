-- ============================================================
-- Hall of Fame tables for Supabase
-- Run in the Supabase SQL Editor (Dashboard > SQL Editor > New Query)
-- ============================================================

BEGIN;

-- 1. Nominations table
CREATE TABLE IF NOT EXISTS hof_nominations (
    id              BIGSERIAL PRIMARY KEY,
    reference_no    VARCHAR(60) UNIQUE NOT NULL DEFAULT '',
    status          VARCHAR(20) NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','submitted','under_review','revision_requested',
                                      'resubmitted','approved','rejected','published','archived')),

    -- Personal
    full_name           VARCHAR(200) NOT NULL,
    professional_title  VARCHAR(200) NOT NULL DEFAULT '',
    email               VARCHAR(254) NOT NULL,
    phone               VARCHAR(40)  NOT NULL DEFAULT '',
    nationality         VARCHAR(120) NOT NULL DEFAULT '',
    current_location    VARCHAR(200) NOT NULL DEFAULT '',

    -- Professional
    institution         VARCHAR(200) NOT NULL DEFAULT '',
    position            VARCHAR(200) NOT NULL DEFAULT '',
    department          VARCHAR(200) NOT NULL DEFAULT '',
    years_experience    INTEGER CHECK (years_experience IS NULL OR years_experience >= 0),
    areas_of_expertise  TEXT NOT NULL DEFAULT '',

    -- Recognition profile
    biography               TEXT NOT NULL DEFAULT '',
    achievements            TEXT NOT NULL DEFAULT '',
    contribution            TEXT NOT NULL DEFAULT '',
    reason_for_nomination   TEXT NOT NULL DEFAULT '',

    -- File paths (Supabase Storage "hall" bucket)
    cv_path                     VARCHAR(500) NOT NULL DEFAULT '',
    activity_report_path        VARCHAR(500) NOT NULL DEFAULT '',
    supporting_evidence_path    VARCHAR(500) NOT NULL DEFAULT '',
    photo_path                  VARCHAR(500) NOT NULL DEFAULT '',

    -- Consent
    consent_accurate    BOOLEAN NOT NULL DEFAULT FALSE,
    consent_publish     BOOLEAN NOT NULL DEFAULT FALSE,
    consent_verify      BOOLEAN NOT NULL DEFAULT FALSE,

    -- Recognition IDs (set on approval)
    hof_member_id       VARCHAR(60) UNIQUE,
    certificate_ref     VARCHAR(60) UNIQUE,
    letter_ref          VARCHAR(60) UNIQUE,
    recognition_year    INTEGER CHECK (recognition_year IS NULL OR recognition_year >= 2000),

    -- Admin-edited public biography
    approved_biography  TEXT NOT NULL DEFAULT '',

    -- Review
    revision_message    TEXT NOT NULL DEFAULT '',
    rejection_reason    TEXT NOT NULL DEFAULT '',
    reviewed_by_id      BIGINT REFERENCES users(id) ON DELETE SET NULL,

    -- Timestamps
    submitted_at    TIMESTAMPTZ,
    reviewed_at     TIMESTAMPTZ,
    approved_at     TIMESTAMPTZ,
    published_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Owner
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_hof_nominations_user    ON hof_nominations (user_id);
CREATE INDEX IF NOT EXISTS idx_hof_nominations_status  ON hof_nominations (status);
CREATE INDEX IF NOT EXISTS idx_hof_nominations_year    ON hof_nominations (recognition_year);

-- 2. Audit log table
CREATE TABLE IF NOT EXISTS hof_audit_logs (
    id              BIGSERIAL PRIMARY KEY,
    nomination_id   BIGINT NOT NULL REFERENCES hof_nominations(id) ON DELETE CASCADE,
    actor_id        BIGINT REFERENCES users(id) ON DELETE SET NULL,
    action          VARCHAR(60) NOT NULL,
    detail          TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hof_audit_logs_nomination ON hof_audit_logs (nomination_id);

-- 3. Mark the Django migration as applied so `manage.py migrate` won't
--    try to re-create these tables.
INSERT INTO django_migrations (app, name, applied)
VALUES ('hall_of_fame', '0001_initial', NOW())
ON CONFLICT DO NOTHING;

-- 4. Create the "hall" storage bucket (private -- files served via signed URLs)
-- Run this separately in the Supabase Dashboard > Storage > New Bucket:
--   Name: hall
--   Public: OFF (private)
--   File size limit: 10 MB
--   Allowed MIME types: application/pdf, image/jpeg, image/png, image/webp,
--                       application/msword, application/vnd.openxmlformats-officedocument.wordprocessingml.document

COMMIT;

-- ============================================================
-- Handy lookups
-- ============================================================
-- SELECT * FROM hof_nominations WHERE status = 'published' ORDER BY recognition_year DESC, full_name;
-- SELECT * FROM hof_nominations WHERE status IN ('submitted','under_review','resubmitted') ORDER BY submitted_at;
-- SELECT n.*, u.email AS user_email FROM hof_nominations n JOIN users u ON u.id = n.user_id WHERE n.status = 'submitted';
-- SELECT * FROM hof_audit_logs WHERE nomination_id = <id> ORDER BY created_at DESC;

-- ============================================================
-- Undo (DANGER -- deletes all Hall of Fame data)
-- ============================================================
-- DROP TABLE IF EXISTS hof_audit_logs;
-- DROP TABLE IF EXISTS hof_nominations;
-- DELETE FROM django_migrations WHERE app = 'hall_of_fame';
