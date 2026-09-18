-- ==========================================================================
-- MSREC — Committee "Governance Documents"
-- ==========================================================================
-- Run once in the Supabase SQL editor. Idempotent: safe to re-run.
--
-- The committee dashboard's Governance Documents pages (Charter, Terms of
-- Reference, SOPs, Committee Policies) read the existing policy_documents
-- table, filtered by `category`. An admin adds a document from
-- Settings -> Policy Library and it shows up on the matching committee page
-- immediately -- no new table. The only change is three new category values
-- ('charter', 'terms_of_reference', 'committee_policy'); SOPs reuse 'sop'.
-- ---------------------------------------------------------------------

begin;

alter table public.policy_documents drop constraint if exists policy_documents_category_check;
alter table public.policy_documents
    add constraint policy_documents_category_check
    check (category in ('sop', 'guidance', 'ethics', 'charter', 'terms_of_reference', 'committee_policy'));

commit;
