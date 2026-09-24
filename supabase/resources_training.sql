-- MSREC: editable Research Ethics Training on the public Resources page.
--
-- Equivalent of Django migration pages/0023_resource_training_fields.py.
-- You do NOT need to run this if you run `python manage.py migrate` -- it is
-- here for running by hand in the Supabase SQL Editor. Safe to run twice.
--
-- What it does:
--   1. adds two columns to resource_documents (card label + card icon)
--   2. loads the four training modules the page used to hardcode, so the
--      Admin and the Secretariat can now edit or remove them
--
-- No storage or RLS changes are needed: the app connects as the database
-- owner, and uploaded files still go to the existing "resources" bucket.

-- 1. Columns (defaults are kept so older app code can still INSERT) ---------
ALTER TABLE resource_documents
  ADD COLUMN IF NOT EXISTS badge_label varchar(60) NOT NULL DEFAULT '';
ALTER TABLE resource_documents
  ADD COLUMN IF NOT EXISTS icon varchar(40) NOT NULL DEFAULT 'bi-mortarboard-fill';

-- 2. The four default training modules (skipped if a title already exists) --
INSERT INTO resource_documents
  (category, title, description, file_path, file_size, external_url,
   badge_label, icon, is_published, display_order, created_at, updated_at)
SELECT 'training', v.title, v.description, '', 0, '',
       v.badge_label, v.icon, TRUE, v.display_order, now(), now()
FROM (VALUES
  ('Foundations of Research Ethics',
   'The core principles of respect for persons, beneficence, justice and accountability behind every MSREC decision.',
   'Online course · 2 hrs', 'bi-mortarboard-fill', 100),
  ('Good Clinical Practice (GCP)',
   'International standards for designing, conducting and reporting trials that involve human participants.',
   'Online course · 3 hrs', 'bi-clipboard2-pulse', 110),
  ('AI Ethics & Responsible Research',
   'Bias, transparency, human oversight and participant awareness for studies that involve AI or automated systems.',
   'Online module · 1.5 hrs', 'bi-cpu', 120),
  ('Data Protection & Confidentiality',
   'Practical handling of identifiable, sensitive and cross-border data across the research lifecycle.',
   'Online module · 1 hr', 'bi-shield-lock', 130)
) AS v(title, description, badge_label, icon, display_order)
WHERE NOT EXISTS (
  SELECT 1 FROM resource_documents r
  WHERE r.category = 'training' AND r.title = v.title
);

-- 3. Only if you ran this file by hand: tell Django the migration is done so
--    `manage.py migrate` doesn't try to add the columns again.
INSERT INTO django_migrations (app, name, applied)
SELECT 'pages', '0023_resource_training_fields', now()
WHERE NOT EXISTS (
  SELECT 1 FROM django_migrations
  WHERE app = 'pages' AND name = '0023_resource_training_fields'
);

-- Check:
-- SELECT id, title, badge_label, icon, display_order, is_published
-- FROM resource_documents WHERE category = 'training' ORDER BY display_order;
