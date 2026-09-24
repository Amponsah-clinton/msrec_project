"""The MSREC Assistant's knowledge base: topic-sized pieces, each with the
words that should bring it up.

Per question, retrieve() picks the handful of pieces that matter (by
keyword match against the question and the recent conversation, filtered by
who's asking), so the assistant can know a great deal without carrying all
of it into every request. Fees and contact addresses are NOT here -- they
are read live from the database (see knowledge.py).

Each Chunk:
  id        unique slug
  title     shown to the model as the section heading
  keywords  lowercase words / phrases; a multi-word phrase found in the
            question scores more than a single word
  audience  "all", or a set of roles the piece is for. "public" means
            a signed-out visitor. Applicant how-tos are also offered to
            reviewers/committee/chair (they can apply too) and to visitors.
  text      the facts, written to be quoted from

Keep every fact here true to the running system; when a dashboard or a
setting changes, change the matching piece.
"""
from dataclasses import dataclass, field

ALL = "all"
APPLYING = frozenset({"public", "applicant", "reviewer", "committee", "chair"})
STAFF = frozenset({"secretariat", "admin", "chair"})


@dataclass(frozen=True)
class Chunk:
    id: str
    title: str
    keywords: tuple
    text: str
    audience: object = ALL


def C(id, title, keywords, text, audience=ALL):
    return Chunk(id, title, tuple(k.lower() for k in keywords.split(",")), text.strip(), audience)


CHUNKS = [
    # ------------------------------------------------------------------ about / governance
    C("about", "About MSREC",
      "msrec,who are you,about,what is msrec,metascholar,committee,established,mission,vision,mandate,history",
      """MSREC (Metascholar Research Ethics Committee) is an independent, multidisciplinary research ethics committee established under Metascholar Limited (Ghana). It reviews ethically sensitive research and supports responsible research conduct across health & biomedical, social science & education, business & engineering, AI/ICT & digital systems, secondary data/evidence synthesis and online research.
Mission: timely, competent, transparent and impartial ethical review; supporting responsible research practice; monitoring approved studies; keeping secure, verifiable and accountable records.
Mandate: decide whether a project needs ethics review; run expedited or full Committee review; require modifications; approve or decline protocols; review amendments; oversee approved studies (safety and deviation reports); suspend or withdraw approval when necessary; issue study-closure determinations.
It does not claim national accreditation or regulator endorsement that it doesn't hold. See [About MSREC](/about/)."""),
    C("structure", "Board, Committee and Secretariat",
      "board,committee,secretariat,structure,governance,who decides,independence,chair,separate,roles of",
      """Three distinct bodies. The Board (Metascholar Limited) provides institutional governance, legal support, finance and resources but never directs or reverses protocol-specific ethics decisions. The Committee is the multidisciplinary review body with collective authority over protocol decisions. The Secretariat handles administrative screening, records, scheduling, correspondence and workflow, and cannot turn payment or screening into ethical approval.
Independence: protocol decisions are protected from commercial, managerial, sponsor or applicant pressure. Members with an actual, potential or perceived conflict of interest must disclose it and are recused. See [Board & Committee](/board-committee/) and [Governance](/governance/)."""),
    C("principles", "Ethical principles",
      "principles,ethics principles,respect for persons,beneficence,justice,transparency,who,cioms,ich,helsinki,guidelines followed,standards",
      """Every review rests on four principles, consistent with WHO, CIOMS and ICH E6(R3) guidance: Respect for persons (voluntary participation, meaningful information, valid consent, right to withdraw); Beneficence (minimise foreseeable harm, weigh harms and benefits); Justice (fair selection, no unjustified exclusion or burden); Transparency & accountability (documented procedures, traceable decisions, conflict management, auditable records)."""),
    C("governance-docs", "Charter, SOPs, policies and annual reports",
      "charter,terms of reference,sop,standard operating procedures,policy,policies,annual report,governing documents,conflict of interest policy,records policy,data protection policy,confidentiality policy",
      """The Governance page publishes: the MSREC Charter and Terms of Reference (founding documents); six numbered SOPs (Administrative Screening, Expedited Review, Full Committee Review, Amendments & Modifications, Adverse Event & Safety Reporting, Record Retention & Archiving); four governing policies (Conflict of Interest, Confidentiality, Records, Data Protection); and annual reports for 2022–2025. See [Governance](/governance/). Reviewers and Committee members also find SOPs, guidance and ethics guidelines in their dashboards."""),
    # ------------------------------------------------------------------ who needs review / eligibility
    C("who-needs-review", "Does my study need ethics review?",
      "need review,need ethics,need approval,do i need,required,exempt,exemption,human participants,who needs,does my study,survey,questionnaire,interview,secondary data,existing data,published data,online survey,systematic review",
      """Any project involving human participants, their data or biological material. Research type alone doesn't decide it: MSREC, not the applicant, makes the determination. Never self-declare exemption; if unsure, submit and request an Ethics Determination.
Common cases: online surveys — possibly; previously collected or published data — often a shorter determination pathway, but MSREC confirms whether individual-level, restricted or unpublished identifiable data trigger full review; systematic/scoping reviews and bibliometrics are usually determination-level; interviews, surveys and classroom or behavioural studies are reviewed by risk. Domains commonly reviewed: Health & Biomedical; Social & Behavioural; Business & Engineering; AI, ICT & Systems; Secondary Data; Online & Digital.
Never say a specific study is exempt or approved — explain the pathway and that MSREC decides. See [For Applicants](/applicants/).""", APPLYING),
    C("ai-review", "AI / machine-learning research",
      "ai,artificial intelligence,machine learning,ml,algorithm,automated,generative,llm,chatbot,digital systems,software,model",
      """AI-related review is risk-based. Projects using human data, producing automated outputs that affect individuals, or lacking human oversight generally need review of data provenance, bias, safety, cybersecurity, explainability and human oversight. The application form has an "AI / ML / Automated Systems" section (complete only if relevant) and a "Software / System / Device" section. Guidance and a training module on AI ethics are on [Resources](/resources/)."""),
    C("eligibility", "Who can apply and extra steps",
      "eligible,eligibility,who can apply,can i apply,undergraduate,student,supervisor,independent researcher,partner institution,collaboration agreement,vulnerable,sponsored,data sharing agreement,principal investigator",
      """Apply directly if you are a registered student, faculty or staff member at a Metascholar-affiliated institution, an independent researcher with a defined protocol, or your research is sponsored by a recognised organisation, and the study has a named Principal Investigator.
One extra step if: you are an undergraduate (supervisor co-signature); your institution isn't a Metascholar partner (collaboration agreement); the study involves a vulnerable population (additional safeguarding review); it is externally sponsored (data-sharing agreement on file). Student applicants also need supervisor sign-off.""", APPLYING),
    # ------------------------------------------------------------------ documents, resources, training
    C("required-documents", "Documents to prepare",
      "documents,required documents,what do i need,attachments,upload,protocol,consent form,checklist,cv,supervisor letter,recruitment,instruments,ethics training,data management",
      """Always required: completed application form; research protocol/proposal; informed consent form(s); data management & confidentiality plan; CV of the Principal Investigator.
Conditional: supervisor approval letter (students); institutional support/collaboration letter (external institutions); recruitment materials — flyers, ads, scripts (if recruiting); data collection instruments — surveys, interview guides; evidence of prior ethics training (where required). The application form says which apply. Upload them in the "Documents Attached" section of the form.""", APPLYING),
    C("resources", "Forms, templates and guidance",
      "template,templates,forms,download form,resources,guidance,guidelines,consent template,assent,parental consent,information sheet,protocol template,amendment form,reporting form",
      """The [Resources](/resources/) page has: Application Forms (universal application form, amendment request, expedited-eligibility checklist, determination/exemption request); Protocol Templates (full protocol, systematic-review protocol, data management plan, study synopsis); Consent Templates (adult consent, parental/guardian consent, minors' assent, participant information sheet); Reporting Forms (adverse event/SAE, deviation/non-compliance, continuing review/annual progress, study closure); Guidelines (AI & ML, vulnerable populations, data protection & confidentiality, conflict of interest, risk classification & sample size, international collaboration & cross-border data); Regulatory Authorizations when published. Use the adult template for adults, the parental/guardian template plus an assent form for minors, and always pair consent with a participant information sheet."""),
    C("training", "Research ethics training",
      "training,course,gcp,good clinical practice,foundations of research ethics,module,certificate of training,ethics training",
      """Self-paced modules recommended before a first submission (see [Resources](/resources/)): Foundations of Research Ethics (about 2 hrs), Good Clinical Practice (about 3 hrs), AI Ethics & Responsible Research (about 1.5 hrs), Data Protection & Confidentiality (about 1 hr). Ethics training isn't mandatory for every applicant category, but it is strongly recommended, and proof is required where a category or policy demands it."""),
    # ------------------------------------------------------------------ pathways, workflow, decisions
    C("pathways", "Review pathways and timelines",
      "pathway,pathways,how long,timeline,turnaround,days,expedited,full committee,exemption,determination,amendment review,duration,when will i get,decision time,speed up,fast",
      """Business-day timelines depend on completeness and reviewer availability:
- Ethics Determination / Exemption: minimal-risk, de-identified existing data or standard educational evaluations; decided by the Secretariat, no full Committee vote — about 5–7 days.
- Expedited Review: minimal risk with direct participant contact but low complexity; one or two designated reviewers — about 10–12 days.
- Full Committee Review: more than minimal risk, vulnerable populations or sensitive data; voted on by the full Committee at a scheduled meeting — about 15–21 days.
- Amendment Review: changes to an approved protocol, reviewed proportionally — about 5–10 days.
Median overall about 21 days. The applicant picks a best guess on the form; the Secretariat assigns the final pathway during screening. Six-stage pathway: Submit (day 0), Screen (3–5 days), Review (10–15), Respond (applicant-paced), Decision (3–5), Monitor (ongoing). Paying a fee does not speed up or guarantee approval."""),
    C("workflow", "The review workflow",
      "workflow,process,stages,steps,screening,how does review work,what happens after submit,after i submit,reviewer assigned,ethical review,eight domains,domains",
      """Seven stages: 1 Applicant submission → 2 Administrative screening (completeness, identity, affiliation, attachments, payment status, scope — never an ethics judgement; incomplete files go back with a checklist) → 3 Review pathway assigned (determination, expedited or full Committee) → 4 Ethical review against eight domains (scientific & social value; participant selection; risk & benefit; consent; privacy & confidentiality; vulnerability; AI & digital systems; conflicts & funding) → 5 Researcher response to any comments → 6 Decision → 7 Post-approval monitoring.
Reviewers are matched on expertise, workload and independence and must declare conflicts of interest before a protocol opens; a conflict blocks the assignment and it is reassigned. Reviewer identity may stay confidential under a blinded policy. See [Ethics Review](/ethics-review/)."""),
    C("decisions", "Decisions and appeals",
      "decision,decisions,approved with conditions,modifications required,deferred,not approved,rejected,appeal,revision,resubmit,respond to comments,outcome",
      """Five outcomes: Approved (proceed under the protocol, subject to any stated conditions; an approval letter is generated); Approved with Conditions (conditions must be met, activation restricted until pre-implementation items are met); Modifications Required (return to the applicant; answer each comment, describe the change made and upload revised documents — routine and available on any protocol returned for changes); Deferred (more information or Committee deliberation needed); Not Approved (reasoned decision issued, with appeal information where permitted).
Formal appeals are only under MSREC's Appeals Policy, are separate from routine responses to modifications, and can't be used to bypass an unresolved ethical concern. In the portal an application shows as Revisions Required or Not Approved; a not-approved applicant may submit a revised application addressing the concerns."""),
    C("meetings", "Committee meetings and quorum",
      "meeting,meetings,quorum,agenda,minutes,committee meeting,schedule,calendar,recusal,vote,when does the committee meet",
      """Full Committee review happens only when quorum is met. Quorum is calculated after recusals; members with a declared conflict can't contribute to that decision and, where policy requires, aren't counted toward quorum. Members are prompted to declare conflicts on every agenda item. The public calendar never shows confidential protocol titles or applicant details; approved minutes are stored securely with version history. The meeting schedule and submission deadlines are on [Board & Committee](/board-committee/)."""),
    # ------------------------------------------------------------------ fees & payment
    C("fees-rules", "Fees: how they work",
      "fee,fees,cost,price,how much,pay,payment,waiver,waived,free,refund,non-refundable,invoice,receipt,paystack,charge,ghs,cedi,student fee",
      """New applications are priced by applicant/study category (not by pathway); Determination/Exemption assessments have one flat fee; post-approval items have their own fees. Quote the live Fee Schedule (given separately) in GHS with thousands separators.
Fees fund the administrative cost of independent review; they are non-refundable, never a condition of approval, and never speed up, guarantee or influence a decision. International-student, international/externally-funded and clinical-trial fees are published in US$ (about US$75 / 200 / 500) and charged in GHS at a rate that the Administrator updates.
The Applicants page mentions a fee waiver for registered students at Metascholar-affiliated institutions with supervisor sign-off, while the Fee Schedule lists student fees — if someone asks about a waiver, say to confirm eligibility with the Secretariat rather than promising one. Exact current prices: [Fee Schedule](/fees/)."""),
    C("payment-how", "How and when payment happens",
      "how do i pay,make payment,payment failed,paid but,not submitted,still draft,invoice,outstanding,receipt,payment history,checkout,mobile money,card,verify payment,paystack,pay fee,where to pay",
      """Payment is part of submitting: if your category carries a fee, pressing Submit on the application takes you to secure online checkout (Paystack). The application is only truly submitted once the payment is verified; until then it stays a draft, with an outstanding invoice under Payments > Make Payment. Payment History lists every attempt (successful, pending, failed); Receipts (and Documents > Certificates / Receipts) hold your receipts. If you paid but the application is still a draft, open Make Payment to check the invoice, then message the Secretariat or email the applications address with your payment reference.""", APPLYING),
    # ------------------------------------------------------------------ verification, approval documents
    C("verification", "Verifying an approval",
      "verify,verification,authentic,genuine,fake,check approval,qr,qr code,verification code,ver-,approval number,is this real,validate",
      """Anyone can check an approval on [Verify](/verify/): enter the approval number (e.g. MSREC/2026/0042) or the verification code printed on the letter and certificate (format VER-XXXX-XXXX), or scan the QR code. It shows the study title, investigator, review pathway, approval and expiry dates and whether the approval is active or expired. Only approved studies are ever shown; nothing confidential is exposed. A study that isn't approved looks exactly like "not found"."""),
    C("approval-docs", "What you receive when a study is approved",
      "approval letter,certificate of ethical clearance,clearance certificate,approval email,approved,download letter,download certificate,approval documents,valid until,valid,valid for,how long is my approval valid,approval valid,expiry,expire,expiration,how long valid,validity,renew approval",
      """An approval is valid for 2 years (24 months) from the approval date — not one year. Renew with a Continuing Review before it expires if the study continues.
When the Secretariat or an Administrator approves a study, the applicant is emailed straight away with two PDFs attached: the approval letter (A4, on MSREC letterhead, with the study details, conditions of approval, the signatory's signature and a verification QR code) and the Certificate of Ethical Clearance (landscape, with the study title, reference, pathway, approval and expiry dates, seal, QR code and the Chair's signature). The email also gives the approval reference and verification code.
Both stay available in the applicant dashboard: Documents > Approval Letters, and Documents > Certificates / Receipts (View or Download PDF). Approval is valid for 2 years from the approval date; a continuing review must be filed before expiry if the study continues. Approval is also visible on the public Verify page."""),
    # ------------------------------------------------------------------ post-approval
    C("post-approval", "After approval: obligations and reports",
      "post approval,after approval,amendment,continuing review,renewal,progress report,annual report,deviation,violation,adverse event,sae,closure,final report,suspension,study closure,report,extend,change protocol,expired",
      """Approval comes with obligations: seek approval before any protocol change (except immediate action to protect participants); report serious adverse events and deviations promptly; submit continuing review before expiry; notify the Committee on completion or early termination.
File each in the applicant dashboard: Post-Approval > choose the type > New > pick the approved study > complete the short form. Types: Minor or Major Amendment (before implementing a material change); Continuing Review (annual renewal); Annual / Progress Report (status, recruitment, changes); Adverse Events (participant-safety issues or serious unexpected problems — report as soon as they arise; severity is recorded; Secretariat and Administrators are alerted immediately; serious or unexpected events may lead to corrective action, extra monitoring or suspension); Deviations / Violations (any departure from the protocol, its cause and the corrective action; also alerts staff); Study Closure / Final Report (completion date, final sample, outstanding events, data status, outputs). Fees apply to some (see the Fee Schedule).
Each filing shows a status — Submitted, Under Review, Action Required, Approved or Acknowledged — with any Secretariat note. Study statuses: Active, Expiring, Expired, Suspended, Closed, Withdrawn; an expired study never silently remains approved.""", APPLYING),
    C("complaints-concerns", "Complaints and ethics concerns",
      "complaint,complain,concern,ethics concern,report misconduct,grievance,unhappy,whistle,contact,support,help,secretariat email,phone",
      """Use the dedicated contacts (given separately) or the [Contact](/contact/) form and pick the matching reason: Secretariat / General Enquiry, Application Support, Complaints, Ethics Concerns or Technical Support. Complaints and ethics concerns are handled by the Secretariat's Complaints / Ethics Concerns queue. For medical, legal or emergency matters MSREC can't advise — contact the appropriate professional."""),
    # ------------------------------------------------------------------ accounts & security
    C("signup", "Creating an account and choosing roles",
      "sign up,signup,register,create account,create an account,new account,open account,roles,request reviewer,request committee,cv,how do i register",
      """Create an account on [Sign up](/signup/): personal and institution details, a strong password, the roles you want (Applicant, Reviewer, Committee Member), and the required agreements. Reviewer and Committee requests need a CV upload plus confidentiality and conflict-of-interest declarations, and are approved by an Administrator — until then the account shows the request as pending and you can still use the applicant side. Approval is emailed to you.""", APPLYING),
    C("role-approval", "When a reviewer/committee request is approved",
      "approved as reviewer,approved reviewer,welcome email,ethics id,membership,temporary password,my password,login details,pending approval,how long approval,waiting for approval,account status,became reviewer",
      """On approval you receive a welcome email with your MSREC Ethics ID (format MSREC/ETH/NNNNN, permanent), what you can do next, your login email, a newly generated password (change it after first login under Profile & Security), a Log in button and your Membership Certificate as a PDF. The Ethics ID and certificate also appear at the top of your Reviewer or Committee dashboard (Copy, View, Download). Committee members are automatically approved reviewers too. A reviewer later approved for the Committee keeps the same Ethics ID and gets an updated certificate. If your request is still pending, an Administrator hasn't decided it yet — you can message the Secretariat or contact support. A declined request is shown on your account and you may contact the Secretariat."""),
    C("password", "Passwords, resets and account security",
      "password,forgot password,reset password,change password,can't log in,cannot log in,locked,login problem,sign in,sessions,sign out,two factor,2fa,security,suspended,email changed",
      """Forgot your password? Use [Forgot password](/forgot-password/) on the login page — you'll get a code by email to set a new one. Passwords need at least 8 characters with an uppercase letter, a lowercase letter, a number and a symbol. Changing your password (Profile & Security) emails you a security alert with the time and IP address; if it wasn't you, reset it immediately and contact support. Profile & Security also lists your active sessions (you can sign out others), holds two-factor preferences, name/email/phone and your profile photo. A suspended account can't sign in until an Administrator reactivates it. Technical problems: use the Technical Support contact."""),
    C("multiple-roles", "One account, several roles",
      "multiple roles,switch dashboard,also reviewer,both roles,applicant and reviewer,dashboard link,my applications,switch role",
      """An account can hold several roles. The sidebar links between them: a reviewer's or committee member's sidebar has "My Applications" (their own applicant side); an applicant who is also an approved reviewer or committee member sees links to the Reviewer or Committee dashboard. Login lands on the primary role's dashboard."""),
    C("notifications-messages", "Notifications and messages",
      "notification,notifications,bell,alerts,message,messages,inbox,chat,contact secretariat,reply,unread",
      """The bell in the top bar lists recent notifications (status changes, payments, decisions, reminders); "Mark all as read" clears the badge and clicking one opens the related page. Messages is a live conversation with the Secretariat/Admin team, for account-specific questions this assistant can't answer. Staff bells also show new Reviewer/Committee applications and adverse-event or deviation filings."""),
    # ------------------------------------------------------------------ applicant how-to
    C("applicant-apply", "Applicant: starting and submitting an application",
      "new application,start application,apply,how do i apply,application form,sections,draft,autosave,save draft,submit,application category,continue draft,delete draft,apply for review,submission",
      """Applications > New Application opens the universal form with 14 sections: Research Information; Type & Field of Research; Principal Investigator; Research Team; Research Methodology; Risks & Benefits; Informed Consent; Privacy & Confidentiality; AI / ML / Automated Systems (only if relevant); Software / System / Device; Funding & Collaboration; Conflict of Interest; Documents Attached; PI Declaration (typed signature).
Choose the Application Category (it sets your fee) and a best-guess review pathway — the Secretariat confirms the pathway at screening. The form autosaves; "Save as Draft" keeps it under Draft Applications where you can continue or delete it. Documents upload when you save or submit. If your category has a fee, Submit takes you to payment and the application is only submitted once payment is verified. You then receive a reference number (MSREC/YEAR/NUMBER) and can track the status.""", APPLYING),
    C("applicant-status", "Applicant: application statuses and revisions",
      "status,statuses,draft,submitted,under review,with committee,revisions required,approved,not approved,track,my application,where is my application,reference number,revise,resubmit,changes requested",
      """Statuses: Draft → Submitted → Under Review → With Committee (full Committee review) → Revisions Required, Approved or Not Approved. Each has its own page under Applications (Draft, Submitted, Under Review, Revisions Required, Approved Studies, Not Approved / Closed). Reference numbers look like MSREC/2026/0042. If revisions are required, open the application from Applications > Revisions Required, read the Secretariat's comments, update the form or documents and resubmit — no review fee is charged again on a resend. You're notified by email and in the bell at each change.""", APPLYING),
    C("applicant-docs", "Applicant: letters, certificates and receipts",
      "letters,decision letter,approval letter,certificate,receipt,download,documents,submitted documents,where are my documents,print,pdf",
      """Documents in the sidebar: Submitted Documents (files you uploaded), Decision Letters (revisions/approved/not-approved outcomes), Approval Letters, and Certificates / Receipts (certificate of ethical clearance and payment receipts). Approval letters and certificates open on screen and can be downloaded as PDF; they carry a verification code and QR. They're also emailed to you when a study is approved.""", APPLYING),
    C("applicant-team", "Applicant: research team, institution, profile",
      "research team,co-investigator,team member,add member,institution,affiliation,profile,photo,update details,help and support,help & support",
      """Research Team: add co-investigators (name, email, institution, photo). Institution / Affiliation: the institution details used on your applications. Profile & Security: name, email, phone, photo, password, two-factor preferences and sessions. Help & Support: guidance and contacts inside the dashboard.""", APPLYING),
    # ------------------------------------------------------------------ reviewer
    C("reviewer-how", "Reviewer: assignments, conflicts and recommendations",
      "reviewer,my reviews,assignment,assigned,accept,decline,conflict of interest,coi,declaration,recommendation,approve subject to minor revisions,major revisions,refer,review a protocol,protocol won't open,assessment,how do i review",
      """Assignments arrive in My Reviews (status New); accept or decline. Before a protocol opens you must complete the conflict-of-interest declaration (Conflict of Interest > Pending Declarations); declaring a conflict returns the assignment to the Secretariat for reassignment. Then assess the protocol against the eight review domains, write comments and choose a recommendation: Approve; Approve Subject to Minor Revisions; Major Revisions Required / Resubmission Required; Refer for Full Committee Review; or Not Approved. Submitting marks it Completed; the Committee/Secretariat make the final decision. Keep Profile & Expertise current — assignments are matched on it. Meetings and SOPs/guidance are in the sidebar.""", frozenset({"reviewer", "committee", "chair", "secretariat", "admin"})),
    C("reviewer-certificate", "Reviewer: peer review certificate and Ethics ID",
      "certificate,peer review certificate,award certificate,my certificate,review certificate,completed review,ethics id,membership certificate,download certificate",
      """After a completed review the Secretariat can award a Certificate of Peer Review: it names the reviewer and the title of the study reviewed, is signed by the Chair, and is emailed as a PDF and available from My Reviews. Separately, every approved Reviewer and Committee member has a permanent MSREC Ethics ID and a Membership Certificate, shown at the top of their dashboard.""", frozenset({"reviewer", "committee", "chair", "secretariat", "admin"})),
    # ------------------------------------------------------------------ committee
    C("committee-how", "Committee member: meetings, protocols, conflicts, deliberation",
      "committee member,protocols for review,recommendations,deliberation,conflict and recusal,recused,cleared,minutes,agenda,rsvp,upcoming meetings,charter,terms of reference,quorum,vote,chair rules",
      """Sidebar: Meetings (Upcoming with RSVP, Calendar, Previous, Agenda), Protocols for Committee Review, Reviewer Recommendations, Conflict & Recusal, Committee Deliberations, Meeting Minutes, governing documents (Charter, Terms of Reference, SOPs, Committee Policies), Notifications, Profile & Committee Appointment (with your Membership Certificate) and Security. Declare conflicts per protocol; statuses are No conflict, Awaiting Chair decision, Recused, Cleared to participate — recused members don't take part in that decision and may not count toward quorum. Decisions: Approved, Approved with Conditions, Modifications Required, Deferred, Not Approved. Discussion happens in Deliberation threads and at meetings; minutes omit confidential participant information. The Chair rules on declared conflicts and signs MSREC's certificates.""", frozenset({"committee", "chair", "secretariat", "admin"})),
    # ------------------------------------------------------------------ secretariat
    C("secretariat-how", "Secretariat: applications, pathways, reviewers, approvals",
      "secretariat,screening,applications,assign reviewer,reviewer assignment,pathway,refer to committee,approve application,start review,request revisions,not approve,reopen,approval email,what happens when i approve",
      """Applications lists every submitted application; open one to Start Review, Request Revisions (a comment is required and emailed to the applicant), Approve, Not Approve or Reopen. Review Pathway pages group Determination/Exemption, Expedited and Full Committee. Reviewer Assignment matches reviewers by expertise and workload (they must clear conflicts first); Reviewer Directory and Assignment History are alongside. Refer to Committee schedules a deliberation meeting and invites members. Screening checks completeness, identity, affiliation, attachments, payment and scope — never an ethics judgement.
When you Approve, the applicant is emailed at once with the approval letter and certificate of ethical clearance attached (wording, letterhead and signatory come from Site Settings > Approval Documents); any open reviewer assignments are cleared automatically. Both PDFs can also be opened from Documents > Approval Letters. Every action is time-stamped in Audit Logs.""", STAFF),
    C("secretariat-more", "Secretariat: committee, meetings, post-approval, finance, communications",
      "committee members,appointments,terms,training,conflict records,schedule meeting,attendance,post approval triage,adverse events,deviations,complaints,finance,email templates,announcements,reminders,letters,reports,users and access,award certificate",
      """Committee: members, membership/appointments, terms & expiry, training, conflict records. Meetings: schedule, calendar, agenda, attendance, quorum, minutes, decisions. Post-Approval: open a filing under Amendments, Continuing Reviews, Progress Reports, Deviations, Adverse Events or Closures, set its status (Submitted, Under Review, Action Required, Approved, Acknowledged) and add a note the applicant sees; Complaints / Ethics Concerns come from the Contact form. Finance: payments and the read-only fee schedule. Communications: applicant and reviewer messages, email templates, announcements, reminders. Documents: decision, approval, amendment, continuing-review and closure letters. Reports & Analytics; Users & Access; Audit Logs. After a reviewer completes a review you can award them a Certificate of Peer Review (signed by the Chair).""", STAFF),
    # ------------------------------------------------------------------ admin
    C("admin-users", "Admin: users, roles and approvals",
      "users and roles,approve reviewer,approve committee,decline,suspend,reactivate,delete account,edit user,role request,pending,accounts,cv,ethics id,who is pending",
      """Users & Roles is a table of every account (member, role, institution, Ethics ID, joined, status, actions) with tabs for All, Pending Approval, Applicants, Reviewers, Committee and Admins, search, and 20 per page. Pending requests show Approve / Decline buttons and the applicant's CV; approving issues the Ethics ID and emails the welcome message with certificate and login details. Icon buttons edit, suspend/reactivate (suspended users can't sign in) or delete an account (deleting also removes their stored files). New Reviewer/Committee applications appear in the top-bar bell.""", frozenset({"admin", "secretariat"})),
    C("admin-settings", "Admin: Site Settings tabs",
      "site settings,settings,logo,hero image,sign in image,footer,contact page,policy library,client logos,testimonials,applicant faqs,paystack,payment gateway,identity,change logo,website content",
      """Site Settings tabs: Site Identity (site name, logo, homepage hero image, the image beside the login page); Payment Gateway (Paystack keys); Footer; Contact Page (the five contact addresses); Policy Library and meetings; Client Logos (landing-page carousel); Testimonials; Applicant FAQs (shown on the public For Applicants page); Certificates; Approval Documents. Images are stored in Supabase Storage and removed when replaced or deleted.""", frozenset({"admin"})),
    C("admin-certificates", "Admin: Chair signature and certificates",
      "certificate signatory,chair signature,sign online,upload signature,signature pad,chair name,certificate preview,membership certificate,peer review certificate,who signs",
      """Site Settings > Certificates sets the Chair's name, title and signature — the only person named on MSREC's certificates (Peer Review, Membership, Ethical Clearance). Draw the signature on the pen-style pad (blue or black ink, Undo/Clear) or upload a photo/scan: the paper background is removed and it's cropped and fitted to the certificate. Preview certificate / PDF buttons show the result. Changes apply to every certificate at once, past and future, because certificates are generated on demand.""", frozenset({"admin"})),
    C("admin-approval-docs", "Admin: approval email, letter and certificate templates",
      "approval documents,approval template,edit letter,edit email,placeholders,letterhead,header image,footer image,letter signatory,letter signature,seal caption,restore defaults,preview pdf,customise letter,change wording,study title placeholder",
      """Site Settings > Approval Documents controls what an applicant receives on approval. Switch between Email, Approval letter and Certificate. Edit the wording; click a placeholder chip to insert it — {applicant_name}, {study_title}, {reference_no}, {review_pathway}, {approval_date}, {valid_until}, {investigator}, {institution}, {committee_name}, {chair_name}, {chair_title}, {verification_code}, {today}. Toggle the details box, QR code and certificate details; Preview shows the unsaved wording; Restore defaults resets one document's text.
Letterhead: upload a header image (top of page 1) and a footer image (bottom of every page) for the approval letter; they're placed edge to edge on A4 (about 2480 px wide; header max height 55 mm, footer 38 mm, larger images are scaled down; blank margins trimmed). Letter signatory: name, title and signature image for the letter, or leave blank to use the Chair. Uploaded images are saved to Supabase Storage and the old file is deleted on replace/remove.""", frozenset({"admin"})),
    C("admin-finance", "Admin: finance and the fee schedule",
      "finance,payments,fee schedule,change fee,edit fee,export csv,total collected,paystack,revenue,price change,update price",
      """To change a fee: open Finance in the sidebar, find the Fee Schedule editor near the top of the page, type the new amount for that item and press Save on its row. It takes effect immediately for new checkouts, the public Fees page and the application form. (There is no separate "Fee Schedule" sidebar item.)
The same Finance page lists every payment (20 per page) with tabs (All, Successful, Pending, Failed), search, a date range and Export CSV. Secretariat sees the schedule read-only.""", frozenset({"admin", "secretariat"})),
    C("admin-security", "Admin: security, audit logs, oversight",
      "access and security,audit log,audit logs,sessions,two factor adoption,staff sessions,adverse events,deviations,oversight,inquiries,reports and analytics,messages",
      """Access & Security shows two-factor adoption and active staff sessions (25 per page). Audit Logs record time-stamped staff actions (approvals, role decisions, settings). Adverse Events and Protocol Deviations give read-only oversight of those filings (the Secretariat triages them); admins are emailed and notified whenever one is filed. Inquiries holds Contact-page messages, answered by email from the dashboard. Reports & Analytics and Messages complete the sidebar.""", frozenset({"admin"})),
    # ------------------------------------------------------------------ the assistant itself
    C("certificates-public", "MSREC certificates and who signs them",
      "certificate,certificates,who signs,signed by,signatory,signature,chair signs,peer review certificate,membership certificate,clearance certificate,ethical clearance",
      """MSREC issues three certificates: the Certificate of Ethical Clearance (to applicants whose study is approved), the Certificate of Peer Review (to reviewers after a completed review, naming the study they reviewed) and the Membership Certificate (to every approved Reviewer and Committee member, with their MSREC Ethics ID). Each is signed by the Chair of the Committee, who is the only person named on them. The approval letter is signed by the Chair unless the Administrator has set a different signatory."""),
    C("become-reviewer", "Becoming a reviewer or committee member",
      "become reviewer,become a reviewer,join as reviewer,register as reviewer,create account as reviewer,sign up as reviewer,reviewer account,committee account,apply to be reviewer,apply to be committee,volunteer,join committee,want to review",
      """Reviewers and Committee members are not appointed by email or support: create an account on [Sign up](/signup/) and tick Reviewer and/or Committee Member as your role(s), upload a CV, accept the confidentiality and conflict-of-interest declarations, and submit. An Administrator reviews the request; you're emailed when it's approved (with your Ethics ID, login details and Membership Certificate). Until then you can still use the applicant side of the portal. You can also add Reviewer/Committee roles when you first register."""),
    C("contact-in-portal", "Contacting the Secretariat from your account",
      "message the secretariat,contact the secretariat,talk to secretariat,reach the secretariat,speak to someone,ask the secretariat,send a message,messages,chat with secretariat,help with my application,support request",
      """Signed-in applicants: the fastest way to reach the Secretariat about your own application or account is Messages in the sidebar, a live conversation with the Secretariat/Admin team. Anyone (signed in or not) can use the [Contact](/contact/) form or the dedicated addresses in the contacts list. Use Technical Support for login or portal problems, Application Support for form questions, Complaints and Ethics Concerns for those matters."""),
    C("annual-reports", "Annual figures",
      "annual report,statistics,how many applications,approval rate,turnaround,average,2025,2024,2023,2022,performance,numbers,meetings held,track record",
      """Published annual reports (see [Governance](/governance/)): 2025 — 142 applications reviewed, 89% approved (including conditional approvals), average turnaround 18 days, 12 Committee meetings held. 2024 — 118 applications reviewed, the first full year including AI/ML protocols. 2023 — 76 applications reviewed, the Committee expanded to seven members. 2022 — 41 applications reviewed, the inaugural year of full operation."""),
    C("privacy", "Data protection and confidentiality",
      "privacy,data protection,confidential,confidentiality,my data,personal data,gdpr,terms,terms of use,privacy notice,secure,security of documents,who sees my protocol",
      """Protocol content, deliberations and applicant data are shared only with those who need them to complete a review, under the Confidentiality and Data Protection policies (see [Governance](/governance/)); confidential participant information is never reproduced in meeting records or shown on the public calendar. Uploaded files are stored in private storage. The public Verify page shows only the basic facts of an approved study. Legal documents: [Terms of Use](/terms-of-use/) and [Privacy Notice](/privacy-notice/). Please don't paste confidential participant data into this chat."""),
    C("assistant", "About this assistant",
      "who are you,what can you do,scholar,assistant,bot,are you ai,can you,help me,do you have access,my application status",
      """"Scholar" is MSREC's help assistant. It answers from MSREC's published information and the portal guide, can point to the right page, and quotes live fees and contacts. It cannot see anyone's applications, payments, messages or account, can't change or submit anything, and never makes ethics decisions — for account-specific matters use Messages in the dashboard or the Secretariat contacts."""),
]

_BY_ID = {c.id: c for c in CHUNKS}
CORE = ("about",)


_STOP = {"the", "and", "for", "with", "that", "this", "from", "how", "what", "where", "when", "why", "who",
         "can", "does", "did", "are", "was", "not", "you", "your", "our", "any", "get", "have", "has", "will",
         "would", "should", "could", "about", "into", "than", "then", "there", "their", "them", "they", "its"}


def _stem(word):
    """Cheap normalisation so plurals/-ing forms match: requests -> request,
    messages -> message, reporting -> report."""
    word = word.strip("'\"-")
    for suffix in ("ing", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def _tokens(text):
    import re

    return set(_stem(w) for w in re.findall(r"[a-z0-9][a-z0-9'\-]{1,}", (text or "").lower())
               if len(w) > 2 and w not in _STOP)


def _audience_ok(chunk, role):
    who = role or "public"
    return chunk.audience == ALL or who in chunk.audience or (who in ("applicant",) and "public" in chunk.audience)


def retrieve(question, history_text="", role=None, limit=5, budget_chars=7500):
    """Best-matching Chunks for `question` (plus a little recent
    conversation for follow-ups), never more than `limit` or `budget_chars`."""
    q = (question or "").lower()
    ctx = (history_text or "").lower()
    q_tokens, ctx_tokens = _tokens(q), _tokens(ctx)
    # A short follow-up ("and for a Master's student?") carries little on
    # its own -- lean on what was being discussed.
    follow = 2.5 if len(q_tokens) <= 4 else 1.0
    scored = []
    for chunk in CHUNKS:
        if not _audience_ok(chunk, role):
            continue
        score = 0.0
        for kw in chunk.keywords:
            kw_tokens = _tokens(kw)
            multiword = len(kw_tokens) > 1 or " " in kw
            if multiword:
                if kw in q:
                    score += 4                       # exact phrase
                elif kw_tokens and kw_tokens <= q_tokens:
                    score += 3                       # same words, any order / filler between
                elif kw_tokens and kw_tokens <= ctx_tokens:
                    score += 0.8 * follow
            elif kw_tokens:
                stem = next(iter(kw_tokens))
                if stem in q_tokens:
                    score += 2
                elif stem in ctx_tokens:
                    score += 0.5 * follow
        score += len(_tokens(chunk.title) & q_tokens) * 1.5
        if score > 0:
            scored.append((score, chunk))
    scored.sort(key=lambda pair: -pair[0])

    # Drop weak matches once there's a clear front-runner, so a stray shared
    # word can't drag unrelated sections into the prompt.
    if scored:
        floor = max(1.0 if follow > 1 else 2.0, scored[0][0] * 0.35)
        scored = [pair for pair in scored if pair[0] >= floor]

    chosen, used = [], 0
    for score, chunk in scored:
        if len(chosen) >= limit:
            break
        if used + len(chunk.text) > budget_chars and chosen:
            continue
        chosen.append(chunk)
        used += len(chunk.text)
    if not chosen:
        chosen = [_BY_ID[i] for i in CORE]
    return chosen
