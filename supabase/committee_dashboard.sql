-- ---------------------------------------------------------------------
-- Committee dashboard: Notifications / Profile & Committee Appointment /
-- Security pages.
--
-- Run this once in the Supabase SQL editor (idempotent -- safe to re-run).
-- Mirrors migration pages/0012_governance_member_user, so if you already
-- ran `python manage.py migrate` against this database you do NOT need to
-- run section 1 again.
--
-- Everything else those three pages read and write already lives in
-- existing tables, so nothing else has to change:
--   * profile, phone, ORCID, notification switches, 2FA / sign-in-alert
--     flags   -> public.users (+ its committee_profile jsonb column)
--   * notification feed + read state -> public.notifications /
--     public.notification_reads
--   * sign-in / password / profile history -> public.audit_logs
--   * active sessions -> public.django_session
--   * meeting invites & RSVPs -> public.meeting_participants
--   * appointment, training, conflict records -> committee_appointments /
--     committee_training_records / committee_conflict_declarations
-- ---------------------------------------------------------------------

-- 1. Link a login account to the Board/Committee seat it holds ----------
alter table public.governance_members
    add column if not exists user_id bigint;

do $$
begin
    if not exists (
        select 1 from pg_constraint where conname = 'governance_members_user_id_key'
    ) then
        alter table public.governance_members
            add constraint governance_members_user_id_key unique (user_id);
    end if;
    if not exists (
        select 1 from pg_constraint where conname = 'governance_members_user_id_fk'
    ) then
        alter table public.governance_members
            add constraint governance_members_user_id_fk
            foreign key (user_id) references public.users (id)
            on delete set null deferrable initially deferred;
    end if;
end $$;

comment on column public.governance_members.user_id is
    'The login account that holds this seat (nullable). Powers the Committee dashboard''s Profile & Committee Appointment page. Set explicitly -- never inferred from a name.';


-- 2. Link accounts to seats --------------------------------------------
-- Option A (explicit, one at a time -- recommended):
--   update public.governance_members
--      set user_id = (select id from public.users where email = 'member@example.com')
--    where id = 4;   -- the governance_members row for that person
--
-- Option B (bulk, by exact name match): links every approved Committee
-- account whose full name (title stripped) equals exactly one roster
-- entry's name, and skips anything ambiguous. Review the SELECT first.
--
--   select gm.id as seat_id, gm.full_name as roster_name, u.id as user_id, u.email
--     from public.governance_members gm
--     join public.users u
--       on lower(regexp_replace(gm.full_name, '^(prof\.|dr\.|rev\.|mr\.|mrs\.|ms\.|madam|barr\.|engr\.)\s+', '', 'i'))
--        = lower(trim(u.first_name || ' ' || u.last_name))
--    where u.role = 'committee' and gm.user_id is null;
--
--   -- then, if the rows above look right:
--   update public.governance_members gm
--      set user_id = u.id
--     from public.users u
--    where u.role = 'committee' and gm.user_id is null
--      and lower(regexp_replace(gm.full_name, '^(prof\.|dr\.|rev\.|mr\.|mrs\.|ms\.|madam|barr\.|engr\.)\s+', '', 'i'))
--        = lower(trim(u.first_name || ' ' || u.last_name));
