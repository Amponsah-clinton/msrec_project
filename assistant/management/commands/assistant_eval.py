"""Runs the assistant question battery against the live model providers.

    python manage.py assistant_eval            # everything
    python manage.py assistant_eval --role admin --match fee
    python manage.py assistant_eval --retrieval    # offline: which knowledge pieces each question retrieves

Uses the real API keys, so a full run makes ~70 model calls (spaced out to
respect free-tier limits) and takes several minutes. Nothing is written to
the database.
"""
import time

from django.contrib.auth.models import AnonymousUser
from django.core.management.base import BaseCommand
from django.test import RequestFactory

from accounts.models import User
from assistant import kb, knowledge, llm
from assistant.eval_cases import CASES

# Curly quotes, non-breaking hyphens etc. that models like to emit.
NORMALISE = (
    ("’", "'"), ("‘", "'"), ("‑", "-"), ("‐", "-"), ("–", "-"), (" ", " "), (" ", " "), (" ", " "), (" ", " "),
)


def _request(role):
    req = RequestFactory().post("/")
    req.user = AnonymousUser() if role is None else User(first_name="Tester", role=role, is_superuser=False)
    return req


class Command(BaseCommand):
    help = "Test the MSREC Assistant against a battery of questions."

    def add_arguments(self, parser):
        parser.add_argument("--role", help="only cases for this role (use 'public' for visitors)")
        parser.add_argument("--match", help="only questions containing this text")
        parser.add_argument("--retrieval", action="store_true", help="offline: show retrieved knowledge, no model calls")
        parser.add_argument("--only", help="comma-separated case numbers, e.g. 27,28,60-66")
        parser.add_argument("--delay", type=float, default=4.5, help="seconds between model calls")

    def handle(self, *args, **opts):
        cases = [
            (i, c) for i, c in enumerate(CASES)
            if (not opts["role"] or (c[0] or "public") == opts["role"])
            and (not opts["match"] or opts["match"].lower() in c[1].lower())
        ]

        if opts["only"]:
            wanted = set()
            for part in opts["only"].split(","):
                lo, _, hi = part.partition("-")
                wanted.update(range(int(lo), int(hi or lo) + 1))
            cases = [(i, c) for i, c in cases if i in wanted]

        if opts["retrieval"]:
            for _, case in cases:
                role, question = case[0], case[1]
                history = " ".join(c for r, c in (case[4] if len(case) > 4 else []) if r == "user")
                ids = ", ".join(chunk.id for chunk in kb.retrieve(question, history, role))
                self.stdout.write("[%s] %s\n    -> %s" % (role or "public", question, ids))
            return

        failures = 0
        for index, case in cases:
            role, question, groups, forbidden = case[:4]
            history = case[4] if len(case) > 4 else []
            messages = [{"role": r, "content": c} for r, c in history] + [{"role": "user", "content": question}]
            system = knowledge.build_system_prompt(_request(role), {"title": "Dashboard", "path": "/"}, [], messages)
            reply, provider = llm.complete(system, messages)
            for _ in range(3):
                if reply:
                    break
                time.sleep(25)  # every provider was rate-limited; wait it out
                reply, provider = llm.complete(system, messages)

            text = (reply or "").lower()
            for old, new in NORMALISE:
                text = text.replace(old, new)
            missing = [g for g in groups if not any(k.lower() in text for k in g)]
            hit = [f for f in forbidden if f.lower() in text]
            ok = bool(reply) and not missing and not hit
            failures += 0 if ok else 1

            self.stdout.write("%s #%d [%s] %s" % ("PASS" if ok else "FAIL", index, role or "public", question))
            if not ok:
                self.stdout.write("    missing: %s  forbidden: %s\n    reply: %s" % (missing, hit, (reply or "(no reply)")[:500]))
            time.sleep(opts["delay"])

        self.stdout.write("\n%d/%d passed" % (len(cases) - failures, len(cases)))
