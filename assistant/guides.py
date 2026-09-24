"""How each MSREC dashboard works -- the in-portal half of the assistant's
knowledge (knowledge.py holds the public-site half). Written from the real
sidebar pages and workflows; keep it in step when a dashboard changes.

The signed-in user's own role guide is included in the prompt (plus the
applicant guide for reviewers/committee members, who can also apply), so
the assistant can give step-by-step directions inside their dashboard.
"""

PORTAL_OVERVIEW = """
# The MSREC portal (dashboards by role)
- Applicant: submit and track applications, pay review fees, file post-approval reports, download letters and certificates, message the Secretariat.
- Reviewer: declare conflicts of interest, review assigned protocols, submit recommendations, see meetings and policy documents, receive peer-review certificates.
- Committee member / Chair: meetings, agendas, protocols for full Committee review, reviewer recommendations, conflict & recusal, deliberations, minutes, governing documents, membership certificate.
- Secretariat: screening, pathway assignment, reviewer assignment, committee administration, meetings, post-approval oversight, finance, communications, letters, reports.
- Administrator: users & role approvals, applications overview, inquiries, Board & Committee, resources, finance and fee schedule, security, audit logs, site settings.
Reviewer and Committee roles are requested at sign-up (with a CV) and approved by an Administrator; until then the request shows as pending. One account can hold more than one role and switch dashboards from the sidebar.
"""

APPLICANT = """
# Applicant dashboard guide
Sidebar sections: Dashboard; Applications (New Application, Draft Applications, Submitted Applications, Under Review, Revisions Required, Approved Studies, Not Approved / Closed); Post-Approval (Amendments, Continuing Reviews, Annual / Progress Reports, Adverse Events, Deviations / Violations, Study Closure / Final Report); Payments (Fees & Invoices, Make Payment, Payment History, Receipts); Documents (Submitted Documents, Decision Letters, Approval Letters, Certificates / Receipts); Messages; Notifications; Research Team; Institution / Affiliation; Profile & Security; Help & Support.

Applying:
- Applications > New Application opens the universal form with 14 sections: Research Information; Type & Field of Research; Principal Investigator; Research Team; Research Methodology; Risks & Benefits; Informed Consent; Privacy & Confidentiality; AI / ML / Automated Systems (only if relevant); Software / System / Device; Funding & Collaboration; Conflict of Interest; Documents Attached; PI Declaration (typed signature).
- Choose the Application Category (this sets the fee) and a best-guess review pathway; the Secretariat confirms the pathway at screening.
- The form autosaves; "Save as Draft" keeps it under Draft Applications, where it can be continued or deleted. Upload supporting documents in the Documents section (files upload when you save or submit).
- Payment gate: if the category carries a fee, pressing Submit takes you to secure online checkout (Paystack). The application is only truly submitted once payment is verified; until then it stays a draft with an outstanding invoice under Payments > Make Payment. Receipts appear under Payments > Receipts and Documents > Certificates / Receipts.
- After submission you get a reference number (MSREC/<year>/<number>). Statuses: Draft > Submitted > Under Review > With Committee (full review) > Revisions Required, Approved or Not Approved.
- Revisions Required: open the application from Applications > Revisions Required, answer each comment, update the form/documents and resubmit.
- Decision and approval letters are generated automatically under Documents > Decision Letters / Approval Letters; approvals can be checked publicly on the Verify page.

After approval (Post-Approval section): open the type, press "New", pick the approved study and complete the short form.
- Amendments: before implementing any material change.
- Continuing Reviews: annual renewal to keep approval active.
- Annual / Progress Reports: status, recruitment, changes.
- Adverse Events: report participant-safety issues or serious unexpected problems immediately (severity is recorded). The Secretariat and Administrators are alerted straight away.
- Deviations / Violations: any departure from the approved protocol, its cause and corrective action (also alerts the Secretariat and Administrators).
- Study Closure / Final Report: formally close the study.
Each filing shows a status (Submitted, Under Review, Action Required, Approved, Acknowledged) and any Secretariat note.

Other pages:
- Messages: a live conversation with the Secretariat/Admin team (for account-specific questions this assistant can't answer).
- Research Team: add co-investigators (name, email, institution, photo).
- Institution / Affiliation: institution details used on applications.
- Profile & Security: name, email, phone and photo; change password (an email alert is sent whenever the password changes); two-factor preferences; view and sign out other active sessions.
- Notifications: status changes, payment confirmations, decisions and reminders.
"""

REVIEWER = """
# Reviewer dashboard guide
Sidebar: Dashboard; My Applications (your own applicant side); My Reviews; Committee Dashboard (if you also hold that role); Conflict of Interest (Pending Declarations, Previous Declarations); Committee Meetings (Upcoming Meetings, Meeting Documents / Packets); Policies (MSREC SOPs, Reviewer Guidance, Ethics Guidelines); Notifications; Profile & Expertise; Security.
- New assignments arrive in My Reviews with status New; you can accept or decline.
- Conflict first: before a protocol unlocks you must complete the conflict-of-interest declaration (Pending Declarations). Declaring a conflict returns the assignment to the Secretariat for reassignment.
- Reviewing: open the application from My Reviews, assess it against the eight domains, write comments and choose a recommendation: Approve; Approve Subject to Minor Revisions; Major Revisions Required / Resubmission Required; Refer for Full Committee Review; Not Approved. Submitting marks the assignment Completed. The Committee/Secretariat make the final decision.
- Certificates: after a completed review the Secretariat can award a Certificate of Peer Review (emailed as a PDF and downloadable from My Reviews).
- Profile & Expertise: keep disciplines, methods and experience current; assignments are matched on them. Security: password, two-factor preferences and active sessions.
"""

COMMITTEE = """
# Committee dashboard guide
Sidebar: Dashboard; My Applications; My Reviews; Meetings (Upcoming Meetings with RSVP, Meeting Calendar, Previous Meetings, Meeting Agenda); Protocols for Committee Review; Reviewer Recommendations; Conflict & Recusal; Committee Deliberations; Meeting Minutes; Governing documents (Charter, Terms of Reference, SOPs, Committee Policies); Notifications; Profile & Committee Appointment (includes the Membership Certificate); Security.
- Declare conflicts per protocol in Conflict & Recusal. Statuses: No conflict; Awaiting Chair decision; Recused; Cleared to participate. Recused members can't take part in that decision and may not count toward quorum.
- Quorum is calculated after recusals; a Full Committee decision can't proceed without it.
- Protocols for Committee Review lists studies referred to the full Committee, with reviewer recommendations alongside; discussion happens in Committee Deliberations threads and at meetings; minutes are recorded without confidential participant information.
- Possible decisions: Approved, Approved with Conditions, Modifications Required, Deferred, Not Approved.
"""

CHAIR = COMMITTEE + """
As Chair you also rule on declared conflicts (clearing or recusing members). You are the signatory on every certificate MSREC issues; your name, title and signature are set by an Administrator in Site Settings > Certificates.
"""

SECRETARIAT = """
# Secretariat dashboard guide
Sidebar: Dashboard; Applications; Review Pathway (Determination / Exemption, Expedited, Full Committee); Reviewers (Reviewer Assignment, Reviewer Directory, Assignment History); Committee (Committee Members, Membership / Appointments, Terms & Expiry, Training, Conflict Records); Meetings (Schedule Meeting, Meetings Calendar, Agenda, Attendance, Quorum, Minutes, Decisions); Post-Approval (Amendments, Continuing Reviews, Progress Reports, Deviations, Adverse Events, Complaints / Ethics Concerns, Closures); Finance; Communications (Applicant Messages, Reviewer Messages, Email Templates, Notifications, Announcements, Reminders); Documents (Decision, Approval, Amendment, Continuing Review and Closure Letters); Reports & Analytics; Users & Access; Audit Logs; Profile & Security.
- Screening checks completeness, identity, affiliation, attachments, payment and scope; never an ethics judgement. Incomplete applications go back with a checklist.
- Assign the pathway, then reviewers by expertise and workload; reviewers must clear conflicts before access. Refer to Full Committee where needed.
- Post-Approval pages: open a filing, set its status (Submitted, Under Review, Action Required, Approved, Acknowledged) and add a note the applicant sees.
- After a completed review you can award the reviewer a Certificate of Peer Review (signed by the Chair).
- Every action is time-stamped in the Audit Logs.
"""

ADMIN = """
# Administrator dashboard guide
Sidebar: Dashboard; Users & Roles; Applications; Inquiries; Board & Committee; Resources; Adverse Events; Protocol Deviations; Finance; Messages; Reports & Analytics; Access & Security; Audit Logs; Site Settings; Profile & Security; Help & Support.
- Users & Roles: approve or decline Reviewer/Committee role requests (CVs viewable), edit, suspend/reactivate or delete accounts (deleting also removes the user's stored files).
- Adverse Events / Protocol Deviations: read-only oversight of those filings (Secretariat handles triage); admins are emailed whenever one is filed.
- Finance: every payment (20 per page, filter by status, date or search, export CSV) and the Fee Schedule editor; fee changes apply immediately to checkout and the public Fees page.
- Access & Security: two-factor adoption and active staff sessions (25 per page).
- Site Settings tabs: Site Identity (logo, homepage hero image, sign-in page image), Payment Gateway (Paystack keys), Footer, Contact Page addresses, Policy Library, Client Logos, Testimonials, and Certificates (the Chair's name, title and signature, printed on every certificate). The signature can be drawn online on a pen-style pad (blue or black ink) or uploaded as a photo/scan of a signature on paper; the paper background is removed automatically and the signature is cropped to fit. "Preview certificate" and "PDF" buttons show the result.
- Inquiries: Contact-page messages, answered by email from the dashboard.
"""

GUIDES = {
    "applicant": APPLICANT,
    "reviewer": REVIEWER + APPLICANT,
    "committee": COMMITTEE + APPLICANT,
    "chair": CHAIR,
    "secretariat": SECRETARIAT,
    "admin": ADMIN + SECRETARIAT,
}


def guide_for(role):
    return GUIDES.get(role or "", "")
