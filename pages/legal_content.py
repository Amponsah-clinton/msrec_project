"""Default wording for the Terms of Service and Privacy Policy
(pages.models.LegalPage). Used the first time a page is shown and by
Site Settings > Legal Pages > "Reset to default". Bodies are written in the
markup pages/legal_markup.py renders; {email} and {site_name} are filled in
from Site Settings.
"""
import datetime

LAST_UPDATED = datetime.date(2026, 10, 21)


TERMS = {
    "nav_label": "Terms of Service",
    "eyebrow": "Help & Legal · Terms",
    "headline": "The terms for using MSREC: as an applicant, a reviewer, a workshop participant, or anyone else with an account.",
    "intro": (
        "MSREC is where a study becomes a reviewed, decided and verifiable ethics application, and where "
        "researchers come to train. This page sets out what we ask of you when you use the platform, and what "
        "you can expect from us in return. It applies the moment you create an account or register for a "
        "workshop, and again every time you submit, review or approve something through the platform."
    ),
    "side_note": (
        "These Terms work alongside our Privacy Policy and the policies published on the Governance page. "
        "Together they are the full picture of how MSREC operates."
    ),
    "version": "2.0",
    "meta_note": "Governed by the laws of Ghana",
    "last_updated": LAST_UPDATED,
    "cta_heading": "Want to see how your data is handled?",
    "cta_text": "The Privacy Policy covers what we collect, why we collect it, and how you can see, correct or delete it.",
    "sections": [
        {
            "heading": "Acceptance of these Terms",
            "summary": "**Using MSREC means you agree to this page.** If you're acting for an institution, you're confirming you're allowed to.",
            "body": (
                "These Terms of Service (\"Terms\") govern your access to and use of the MSREC platform: the website, "
                "applicant and reviewer dashboards, the Secretariat and Committee tools, workshop registration, and the "
                "public verification service (together, the \"Platform\"), operated by the Metascholar Research Ethics "
                "Committee (\"MSREC\", \"we\", \"us\"), established under Metascholar Limited.\n\n"
                "By creating an account, submitting an application, registering for a workshop, accepting an invitation to "
                "review, or otherwise using the Platform, you agree to these Terms and to our "
                "[Privacy Policy](page:privacy). If you use the Platform on behalf of a university, hospital, research "
                "unit or other institution, you confirm that you have the authority to accept these Terms for it, and "
                "\"you\" below covers both you and the institution you represent.\n\n"
                "If you do not agree to these Terms, please don't use the Platform."
            ),
            "note": "",
        },
        {
            "heading": "Accounts & eligibility",
            "summary": "**One real account per person, kept accurate and kept secure.** You're responsible for what happens under your login.",
            "body": (
                "- **Eligibility.** You must be at least 18 years old and able to enter into a binding agreement to create an account.\n"
                "- **One account, accurately described.** Each account belongs to one named individual, not a shared inbox or a "
                "department alias. The name, email, phone, institution and qualification details you give must be accurate, and kept "
                "up to date from your dashboard's Profile & Security page.\n"
                "- **Your login is yours to protect.** Keep your password confidential; you're responsible for all activity under your "
                "account. Tell us straight away at {email} if you think someone else has accessed it.\n"
                "- **We keep a record of sign-ins.** For your security, each session records the device or browser, approximate "
                "location and time of sign-in, which you can see in your dashboard's Active Sessions panel. See our "
                "[Privacy Policy](page:privacy) for detail."
            ),
            "note": "",
        },
        {
            "heading": "Roles on MSREC",
            "summary": "**Everyone starts as an Applicant.** Reviewer and Committee access is granted, not assumed: an administrator approves it first.",
            "body": (
                "Every account gets Applicant access immediately, since opening and tracking an application is the baseline thing "
                "MSREC exists for. Requesting to become a **Reviewer** or a **Committee Member** puts your request into a pending "
                "state that only an MSREC administrator can approve, decline or later revoke. **Chair** and **Secretariat** access "
                "is assigned directly by MSREC.\n\n"
                "| Role | What it can do |\n"
                "| **Applicant** | Prepare, submit and track ethics applications; respond to requests for revision; make payments. |\n"
                "| **Reviewer** | Assess assigned applications and submit independent review reports. Requires approval. |\n"
                "| **Committee Member** | Deliberate and vote on applications at Committee meetings. Requires approval. |\n"
                "| **Chair** | Convene meetings, sign off Committee decisions and oversee the review process. |\n"
                "| **Secretariat** | Screening, scheduling, correspondence, workshops and record-keeping. |\n"
                "| **Administrator** | Platform administration, including approving Reviewer and Committee requests. |\n\n"
                "A role is tied to the judgment it requires, not a permanent entitlement: MSREC may decline a request, or revoke "
                "Reviewer or Committee access, where conduct, conflicts of interest or sustained inactivity make that necessary."
            ),
            "note": "",
        },
        {
            "heading": "Submitting an application",
            "summary": "**What you submit has to be true and complete.** The Committee's decision is only as good as the file it reads.",
            "body": (
                "When you submit a protocol, consent materials, supporting documents or any other part of an application, you "
                "confirm that the information is accurate and complete, and that you have the authority (including any required "
                "supervisor or institutional sign-off) to submit it. Knowingly submitting false, misleading or plagiarised material "
                "breaches these Terms and may be reported to your institution.\n\n"
                "Applications move through administrative screening, then expedited or full Committee review, following the "
                "Standard Operating Procedures on our [Governance page](page:governance#gov-sops). The Committee may ask for "
                "revisions before deciding, and keeps full discretion over the review pathway, timeline and outcome. Submitting "
                "an application, or paying a fee, does not guarantee approval or entitle you to a particular reviewer, timeline "
                "or decision."
            ),
            "note": "",
        },
        {
            "heading": "Review fees & payment",
            "summary": "**Fees pay for the review process, not the outcome.** Paystack handles your card details; we never see or store them.",
            "body": (
                "Some applications carry a fee, billed in Ghanaian Cedis (GHS) under the schedule on our [Fees page](page:fees). "
                "Payments are processed by Paystack; MSREC never receives or stores your card number, only a confirmation that "
                "payment was made.\n\n"
                "**Paying a review fee does not guarantee ethical approval, and cannot speed up or influence a Committee "
                "decision.** Fees for a review that has started are generally non-refundable. If you were charged in error, or you "
                "withdraw before screening begins, contact the Secretariat to request a refund, which is assessed case by case."
            ),
            "note": "",
        },
        {
            "heading": "Workshops, training & certificates",
            "summary": "**Register honestly, pay any certificate fee, and your documents follow.** A certificate records that you took part.",
            "body": (
                "MSREC runs research-ethics workshops and training, listed on our [Workshops page](/workshop/). When you register:\n\n"
                "- **Your details must be accurate.** The name you give is the name printed on your certificate and letter, so check "
                "the spelling before you submit.\n"
                "- **Certificate fees.** Where a workshop charges a certificate fee, it is shown before you register and paid through "
                "Paystack. Where a certificate is compulsory for a workshop, your registration is complete only once the fee is paid. "
                "Certificate fees are generally non-refundable once the workshop has taken place.\n"
                "- **Joining links and materials are for you.** Meeting links, slides and handouts are sent to registered participants "
                "and must not be shared publicly or reused commercially without our permission.\n"
                "- **Documents.** After a workshop, the Secretariat approves each participant. A Certificate of Participation is issued "
                "to those entitled to one (paid where a fee applies), and a Confirmation of Participation letter is issued to every "
                "approved participant.\n\n"
                "We may reschedule, move online or cancel a workshop. If we cancel and do not offer a new date, certificate fees paid "
                "for it are refunded."
            ),
            "note": "",
        },
        {
            "heading": "Reviewers & Committee members",
            "summary": "**Independent judgment, declared conflicts and confidentiality.** That's the deal if you review for MSREC.",
            "body": (
                "- **Confidentiality is a condition of access.** Protocol content, applicant data and deliberations you see may only be "
                "used to complete your assigned review, under the Confidentiality Policy on our "
                "[Governance page](page:governance#gov-policies).\n"
                "- **Declare conflicts before you review.** Any actual, potential or perceived conflict of interest must be declared, and "
                "you'll be recused from that review under our Conflict of Interest Policy.\n"
                "- **Your assessment is yours.** Reviews and votes must reflect your own independent, good-faith judgment, free of "
                "pressure from the applicant, their institution or anyone else.\n"
                "- **Availability is self-reported.** The \"available for new assignments\" setting on your profile reflects your honest "
                "capacity; the Secretariat may also mark you as limited when necessary.\n"
                "- **No fee is implied.** Serving as a Reviewer or Committee Member does not by itself entitle you to payment unless a "
                "separate written agreement says so."
            ),
            "note": "",
        },
        {
            "heading": "Acceptable use",
            "summary": "**Use the Platform the way it was built to be used.** Don't impersonate, don't scrape, don't share access.",
            "body": (
                "You agree not to:\n\n"
                "- impersonate anyone, or misrepresent your affiliation, qualifications or authority to submit or review a study;\n"
                "- share your login, or act on the Platform for someone else, without our written permission;\n"
                "- try to access an account, application or review you haven't been given access to;\n"
                "- scrape, crawl or bulk-query the Platform or the public [verification tool](page:verify) beyond normal use;\n"
                "- upload anything unlawful, infringing or containing malicious code; or\n"
                "- interfere with, probe or try to get around the Platform's security, limits or review workflow.\n\n"
                "We may investigate suspected breaches and act on them, including removing content, revoking a role or "
                "suspending an account."
            ),
            "note": "",
        },
        {
            "heading": "Content you submit",
            "summary": "**You keep ownership.** You're letting us store it and show it to the people reviewing it.",
            "body": (
                "You keep all rights to the protocols, consent forms, CVs, review reports and other material you upload (\"Your "
                "Content\"). By submitting it, you give MSREC a limited licence to store, copy and share it internally (with assigned "
                "Reviewers, Committee Members, the Chair and the Secretariat) only to carry out the review, oversight and "
                "record-keeping described in these Terms and our Governance policies. We don't use Your Content for anything else, "
                "and we never sell it.\n\n"
                "Uploaded files are kept in private storage and are not publicly accessible; our [Privacy Policy](page:privacy) "
                "explains how."
            ),
            "note": "",
        },
        {
            "heading": "The verification tool",
            "summary": "**Verify Approval is a convenience check,** not a substitute for an official approval letter or certificate.",
            "body": (
                "Our public [Verify Approval](page:verify) page lets anyone confirm whether a study holds current MSREC approval, or "
                "whether a certificate is genuine, using its reference number. It's offered in good faith for journals, funders and "
                "institutions and reflects our records at the moment of the check. It is not itself a legal certificate. Where formal "
                "documentation is needed, use the original approval letter from your dashboard or ask the Secretariat."
            ),
            "note": "",
        },
        {
            "heading": "Emails & text messages",
            "summary": "**We contact you about the things you've asked us to do.** Messages about an active application or workshop can't be switched off.",
            "body": (
                "We send email, and text messages to Ghanaian mobile numbers, about your account, applications, payments and "
                "workshops: confirmations, joining links, decisions, certificates and reminders. From time to time we may also tell "
                "past workshop participants about upcoming workshops; you can ask us to stop at any time by replying to the "
                "message or writing to {email}.\n\n"
                "Keep your email address and phone number up to date. We're not responsible for a message you miss because the "
                "details you gave us were wrong or out of date."
            ),
            "note": "",
        },
        {
            "heading": "Suspension & termination",
            "summary": "**We can suspend an account for cause.** You can close yours whenever you like.",
            "body": (
                "We may suspend or deactivate an account that breaches these Terms, submits fraudulent information, or misuses "
                "reviewer or Committee access. A suspended account sees a message at sign-in asking you to contact an administrator. "
                "If you think that's a mistake, reach the Secretariat through our [Contact page](page:contact).\n\n"
                "You can stop using the Platform, or ask us to close your account, at any time by writing to {email}. Closing your "
                "account doesn't erase applications already submitted, reviewed or decided: a decided ethics review is part of the "
                "permanent research record, and is kept as our [Privacy Policy](page:privacy#data-retention) describes."
            ),
            "note": "",
        },
        {
            "heading": "Disclaimers",
            "summary": "**The Platform is provided as it is.** We work to keep it available and accurate, but can't promise uninterrupted service.",
            "body": (
                "The Platform is provided \"as is\" and \"as available\". We don't guarantee that it will be uninterrupted, error-free "
                "or secure against every possible threat, or that a review will be finished within a particular time. Review decisions "
                "reflect the independent professional judgment of Reviewers and the Committee at the time they're made, and MSREC "
                "makes no promise about the outcome of any application."
            ),
            "note": "",
        },
        {
            "heading": "Limitation of liability",
            "summary": "**Our liability to you is capped** at what you've paid us, where the law allows.",
            "body": (
                "To the fullest extent the law allows, MSREC and Metascholar Limited are not liable for any indirect, incidental or "
                "consequential loss arising from your use of the Platform, including delayed reviews, lost research time, or decisions "
                "others make in reliance on a verification result. Where liability can't be excluded, it is limited to the total fees "
                "you paid MSREC in the twelve months before the claim arose."
            ),
            "note": "",
        },
        {
            "heading": "Indemnification",
            "summary": "**If your submission causes a claim against us,** you agree to cover it.",
            "body": (
                "You agree to indemnify MSREC and Metascholar Limited against any claim, loss or expense (including reasonable legal "
                "fees) arising from Your Content, your breach of these Terms, or your breach of any law or anyone else's rights in "
                "connection with your use of the Platform."
            ),
            "note": "",
        },
        {
            "heading": "Governing law & disputes",
            "summary": "**Ghanaian law applies.** We'd rather settle a disagreement directly than in court.",
            "body": (
                "These Terms are governed by the laws of the Republic of Ghana. Before starting formal proceedings, please raise the "
                "issue with the Secretariat: most disagreements about a review, fee, workshop or account can be resolved directly. "
                "Where that isn't possible, disputes are subject to the exclusive jurisdiction of the courts of Ghana."
            ),
            "note": "",
        },
        {
            "heading": "Changes to these Terms",
            "summary": "**We update the date at the top** when something important changes, and tell you if it affects you directly.",
            "body": (
                "We may update these Terms as MSREC's processes change. The \"Last updated\" date at the top of this page always shows "
                "the current version. Where a change materially affects your rights (for example fees or confidentiality "
                "obligations), we'll also email active account holders before it takes effect. Continuing to use the Platform after "
                "a change takes effect means you accept the updated Terms."
            ),
            "note": "",
        },
        {
            "heading": "Contact",
            "summary": "",
            "body": (
                "Questions about these Terms, an application, a workshop or your account can go to the MSREC Secretariat at {email}, "
                "or through our [Contact page](page:contact)."
            ),
            "note": "",
        },
    ],
}


PRIVACY = {
    "nav_label": "Privacy Policy",
    "eyebrow": "Help & Legal · Privacy",
    "headline": "What we collect to run ethics reviews and workshops, and nothing beyond that.",
    "intro": (
        "An ethics application or a workshop registration involves real personal and professional detail: yours, and "
        "sometimes your research participants'. This policy explains what MSREC collects at each step, who can see it, how "
        "long we keep it, and how to ask us for a copy, a correction or a deletion."
    ),
    "side_note": (
        "This policy works alongside our Terms of Service and the Data Protection & Records policies published on the "
        "Governance page."
    ),
    "version": "2.0",
    "meta_note": "Data controller: Metascholar Limited, Ghana",
    "last_updated": LAST_UPDATED,
    "cta_heading": "Want the rules the Committee itself follows?",
    "cta_text": "The Governance page has the full Charter, SOPs and policies this Privacy Policy points back to.",
    "sections": [
        {
            "heading": "Who we are",
            "summary": "**MSREC, run under Metascholar Limited (Ghana),** is the data controller for the information described here.",
            "body": (
                "The Metascholar Research Ethics Committee (\"MSREC\", \"we\", \"us\") is established under Metascholar Limited, "
                "based in Ghana. This policy covers the whole MSREC platform (the public website, workshop registration, applicant "
                "and reviewer dashboards, and the Secretariat, Committee and admin tools) and everyone who uses it: applicants, "
                "reviewers, Committee members, workshop participants and visitors.\n\n"
                "We handle personal data in line with Ghana's Data Protection Act, 2012 (Act 843). Read this policy alongside our "
                "[Terms of Service](page:terms) and the Data Protection and Records policies on our "
                "[Governance page](page:governance#gov-policies), which set out retention and access in more procedural detail."
            ),
            "note": "",
        },
        {
            "heading": "Information we collect",
            "summary": "**Only what each step actually needs:** a fuller profile if you ask to review, application content if you apply.",
            "body": (
                "### When you create an account\n"
                "- Name, title, email, phone, country of residence and highest qualification;\n"
                "- Institution, department, position and institutional address, where they apply;\n"
                "- A password, stored only as a salted, one-way hash. We never see or store it in plain text.\n\n"
                "### If you ask for Reviewer or Committee access\n"
                "- Professional background: position, years of experience, review experience, areas of expertise, ORCID and "
                "professional registration numbers;\n"
                "- A short professional bio, a CV and, if you choose, a photo;\n"
                "- Your confidentiality and conflict-of-interest declarations.\n\n"
                "### When you apply for ethics review\n"
                "- Your protocol, consent materials and any supporting documents you upload;\n"
                "- Institutional details, and your supervisor's name and contact if you're a student;\n"
                "- Confirmation of any review fee paid. Paystack processes the payment; we never receive your card details.\n\n"
                "### When you register for a workshop\n"
                "- Your name, institution, email address and phone number;\n"
                "- Whether you want a certificate, and whether the certificate fee has been paid;\n"
                "- Any comment you add to your registration.\n\n"
                "### Automatically, to keep the Platform secure\n"
                "- Session information: browser or device, approximate IP address and sign-in time, shown back to you in your "
                "dashboard's Active Sessions panel;\n"
                "- Basic technical logs needed to run and protect the Platform.\n\n"
                "### When you contact us\n"
                "- Whatever you include in a message through our [Contact page](page:contact), so we can reply."
            ),
            "note": "",
        },
        {
            "heading": "How we use it",
            "summary": "**To run reviews and workshops, keep the record, and tell you when something changes.** Never to build an advertising profile.",
            "body": (
                "- **Running the review process:** routing applications to reviewers and the Committee agenda, tracking status and "
                "recording decisions.\n"
                "- **Running workshops:** confirming your place, sending joining links, materials and reminders, and issuing your "
                "certificate and participation letter.\n"
                "- **Our workshop contact list:** we keep the details of everyone who has registered for an MSREC workshop so the "
                "Secretariat can contact past participants, including about future workshops. You can ask to be removed at any time.\n"
                "- **Account & role administration:** checking eligibility for Reviewer or Committee access, and approving, "
                "declining or suspending accounts.\n"
                "- **Communications:** status updates, decision letters, confirmations and, where you've opted in, sign-in alerts, "
                "by email and by text message.\n"
                "- **Verification:** confirming an approval or certificate when someone checks its reference on our public "
                "[Verify Approval](page:verify) page.\n"
                "- **Payments:** matching review and certificate fees to your application or registration, through Paystack.\n"
                "- **Security:** spotting suspicious sign-ins and enforcing our [Terms of Service](page:terms).\n"
                "- **Legal & governance duties:** keeping the records our Records Policy and research-governance rules require.\n\n"
                "We do not sell your data, and we do not use it for advertising or profiling."
            ),
            "note": "",
        },
        {
            "heading": "Why we're allowed to use it",
            "summary": "**Each use rests on a lawful basis** under Ghana's Data Protection Act: your request, your consent, the law, or a legitimate need.",
            "body": (
                "- **To provide what you asked for.** Reviewing your application, registering you for a workshop and issuing your "
                "documents all need your details.\n"
                "- **Your consent.** For example, sign-in alerts you switch on, or an optional photo on a reviewer profile. You can "
                "withdraw consent at any time.\n"
                "- **Legal and regulatory obligations.** Keeping research-ethics records and financial records as the law and "
                "governance rules require.\n"
                "- **Legitimate interests.** Keeping the Platform secure, preventing fraud, and telling past workshop participants "
                "about future workshops, which you can opt out of."
            ),
            "note": "",
        },
        {
            "heading": "Who we share it with",
            "summary": "**People who need it to do the work, and the few services that keep MSREC running.** Nobody else.",
            "body": (
                "- **Assigned Reviewers & Committee Members** see only the application content they need to assess your study.\n"
                "- **The Chair and Secretariat** can access applications, registrations and account records to administer reviews "
                "and workshops.\n"
                "- **Your named supervisor** may be contacted where your application identifies one and their input is part of the "
                "review.\n\n"
                "We also use a small number of service providers, each bound to use your data only to provide their service to us:\n\n"
                "| Provider | What they handle |\n"
                "| **Supabase** | Hosts our database and the private storage for uploaded documents and photos. |\n"
                "| **Paystack** | Processes review and certificate fees. Card details go to Paystack, never to MSREC. |\n"
                "| **Resend** | Delivers our emails: confirmations, joining links, decision letters and certificates. |\n"
                "| **BMS / mNotify** | Delivers our text messages to Ghanaian mobile numbers. |\n\n"
                "Beyond these, we disclose personal data only where the law requires it, to protect the rights or safety of MSREC or "
                "others, or with your explicit consent."
            ),
            "note": "",
        },
        {
            "heading": "Confidentiality of applications & reviews",
            "summary": "**Review content is need-to-know, always.** Reviewers and Committee members are bound to keep it that way.",
            "body": (
                "Every Reviewer and Committee Member agrees to our Confidentiality Policy before their access is approved: protocol "
                "content, applicant data and Committee deliberations may be used only for the review they've been assigned, and may "
                "not be discussed, published or reused outside it. Conflicts of interest are declared, and the reviewer recused, "
                "before a review begins. Both policies are published in full on our "
                "[Governance page](page:governance#gov-policies)."
            ),
            "note": "",
        },
        {
            "heading": "Cookies",
            "summary": "**Only the cookies needed to keep you signed in and secure.** No advertising trackers, no cross-site profiling.",
            "body": (
                "MSREC sets essential cookies so the Platform can keep you signed in as you move between pages and protect forms "
                "against forgery; without them, dashboards wouldn't work. We don't use advertising or third-party analytics cookies. "
                "Our pages load fonts from Google Fonts, which means your browser requests font files from Google's servers, as on "
                "most modern websites. That request is not linked to your MSREC account."
            ),
            "note": "",
        },
        {
            "heading": "Data retention",
            "summary": "**Decided applications become part of the permanent research record,** and are kept even after you close your account.",
            "body": (
                "How long we keep information depends on what it is, as set out in our Records Policy on the "
                "[Governance page](page:governance#gov-policies):\n\n"
                "- **Applications, review reports and decisions** are kept for as long as our research-governance obligations "
                "require, because a decided review must stay verifiable for years, including through [Verify Approval](page:verify).\n"
                "- **Workshop registrations, certificates and letters** are kept so certificates can be verified and reissued.\n"
                "- **The workshop contact list** keeps your details until you ask us to remove them.\n"
                "- **Account profiles** are kept while your account is active, and for a limited time afterwards for legal and audit "
                "purposes, then deleted or anonymised."
            ),
            "note": "",
        },
        {
            "heading": "International transfers",
            "summary": "**Our service providers operate internationally.** We only use ones bound to protect your data wherever it's held.",
            "body": (
                "MSREC is based in Ghana, but the providers listed under [Who we share it with](#who-we-share-it-with) may process or "
                "store data in other countries. Where that happens, we rely on their contractual and technical safeguards to protect "
                "your data to a standard consistent with this policy and with Ghanaian law."
            ),
            "note": "",
        },
        {
            "heading": "Data security",
            "summary": "**Passwords are hashed, connections are encrypted, access is role-based.** No system is unbreachable, but this is how we reduce the risk.",
            "body": (
                "Passwords are never stored in plain text, only as a salted, one-way hash that can't be reversed, even by us. "
                "Traffic to the Platform is encrypted in transit, uploaded files sit in private storage, and application content is "
                "reachable only by accounts with a role-based reason to see it. Your dashboard's Profile & Security page lets you "
                "review active sessions and set sign-in alerts. No online service can guarantee absolute security, but we design "
                "deliberately to limit what's exposed and to whom."
            ),
            "note": "If we become aware of a data breach affecting your personal information, we'll notify you and the Data Protection Commission as the law requires.",
        },
        {
            "heading": "Your rights & choices",
            "summary": "**See, correct, download or ask us to delete** what we hold about you, subject to our record-keeping duties.",
            "body": (
                "- **Access & correction.** Most of your profile can be edited from your dashboard; for anything else, ask the "
                "Secretariat.\n"
                "- **A copy of your data.** You can ask for an export of the personal data we hold about you.\n"
                "- **Deletion.** You can ask us to close your account and delete your personal data, subject to the retention rules "
                "above. A decided application's record can't be erased on request, because it's part of the research-governance "
                "record.\n"
                "- **Workshop messages.** You can ask to be taken off the workshop contact list at any time.\n"
                "- **Communication preferences.** Sign-in alerts can be switched off on your Profile & Security page. Messages about "
                "an active application or workshop can't be turned off, because they're how we tell you what's happening.\n"
                "- **Objection.** Where we rely on legitimate interests, you can object to that specific use.\n\n"
                "To use any of these rights, email {email} or use our [Contact page](page:contact). We'll reply within a reasonable "
                "time and may need to confirm your identity first."
            ),
            "note": "",
        },
        {
            "heading": "Children's privacy",
            "summary": "",
            "body": (
                "MSREC is intended for researchers, institutions and professionals aged 18 and over, and we don't knowingly collect "
                "personal data from anyone younger. Where a study involves participants who are minors, their data is handled under "
                "that study's own consent and safeguarding protocols, which the Committee reviews as part of the application, not as "
                "account data covered by this policy."
            ),
            "note": "",
        },
        {
            "heading": "Changes to this policy",
            "summary": "",
            "body": (
                "We may update this policy as our practices change. The \"Last updated\" date at the top always shows the current "
                "version, and we'll email active account holders before any change that materially affects how their data is handled."
            ),
            "note": "",
        },
        {
            "heading": "Contact & complaints",
            "summary": "",
            "body": (
                "For any question about this policy or how your data is handled, contact the MSREC Secretariat at {email} or through "
                "our [Contact page](page:contact).\n\n"
                "If you're not satisfied with our response, you can complain to Ghana's Data Protection Commission "
                "([dataprotection.org.gh](https://www.dataprotection.org.gh/)), or to the data protection authority where you live."
            ),
            "note": "",
        },
    ],
}


DEFAULTS = {"terms": TERMS, "privacy": PRIVACY}


def defaults_for(slug):
    """A fresh copy of the default fields for one page (safe to mutate)."""
    import copy

    return copy.deepcopy(DEFAULTS[slug])
