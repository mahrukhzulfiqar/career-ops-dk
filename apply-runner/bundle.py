"""Load a handoff bundle — one self-contained directory per application.

career-ops' automation/apply-queue.mjs writes these; this module reads them and
nothing else. The runner never reaches into career-ops for a tracker row, a
report or a profile: everything needed to fill one form is inside the directory,
under a generic filename, exactly one candidate per slot.

    handoff/011-queue-it/
        job.json          url, company, role, candidate facts, sha256 of each file
        cv.pdf            the tailored CV to attach
        cv.md             primary source for factual questions about experience
        facts.md          the identity sheet, and what must never be guessed
        cover-letter.md   optional; pasted verbatim when present

Two checks run before a bundle is usable, because the failure that matters is
not a corrupt file but the WRONG file — company A's letter inside company B's
directory. A checksum catches the first. Only the company assertion catches the
second, so both run, and a bundle failing either is refused rather than filled.
"""

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

MANIFEST = "job.json"
DONE_DIR = "done"
LIVENESS_TIMEOUT_S = 120


class BadBundle(Exception):
    """A bundle that must not be filled. Always fatal for that bundle."""


@dataclass(frozen=True)
class Bundle:
    path: Path
    job: dict
    cv_pdf: Path
    cv_md: str
    facts_md: str
    cover_letter: str | None

    @property
    def url(self) -> str:
        return self.job["url"]

    @property
    def company(self) -> str:
        return self.job.get("company") or ""

    @property
    def label(self) -> str:
        role = self.job.get("role") or ""
        return f"{self.company} — {role}".strip(" —") or self.path.name

    def identity(self) -> dict:
        """The fields TASK needs, from the manifest's candidate block.

        `city` is what a form asks for and `location` is what the profile
        stores; the mapping happens here rather than in the prompt so a missing
        value is a loud error instead of a literal "{city}" in a form field.
        """
        c = self.job.get("candidate") or {}
        values = {
            "full_name": c.get("full_name"),
            "email": c.get("email"),
            "phone": c.get("phone"),
            "city": c.get("location"),
            "linkedin": c.get("linkedin"),
            "current_title": c.get("current_title"),
            "current_employer": c.get("current_employer"),
        }
        missing = [k for k, v in values.items() if not v]
        if missing:
            raise BadBundle(f"{self.path.name}: job.json candidate is missing {', '.join(missing)}")
        # A boolean is read separately: False is a real answer, not absence.
        resident = c.get("resident_in_denmark")
        if resident is None:
            raise BadBundle(f"{self.path.name}: job.json candidate is missing resident_in_denmark")
        values["resident_in_denmark"] = bool(resident)
        return values


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def letter_names_company(letter: str, company: str) -> bool:
    """Mirror of apply-queue.mjs's letterNamesCompany.

    Deliberately duplicated rather than imported: the exporter checking its own
    output proves only that it was self-consistent at export time. A bundle can
    be edited, copied or assembled by hand afterwards, and this is the last
    check before the text reaches a real form.
    """
    head = (company or "").strip().split(" ")[0] if company else ""
    if not head:
        return True
    return head.lower() in letter.lower()


def load(path: Path) -> Bundle:
    path = Path(path).expanduser().resolve()
    manifest_path = path / MANIFEST
    if not manifest_path.is_file():
        raise BadBundle(f"{path} has no {MANIFEST}")

    try:
        job = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BadBundle(f"{path.name}: unreadable {MANIFEST} — {exc}") from exc

    for key in ("url", "company"):
        if not job.get(key):
            raise BadBundle(f"{path.name}: {MANIFEST} has no {key}")

    # Integrity: every file the manifest claims must be present and unchanged.
    for name, meta in (job.get("files") or {}).items():
        f = path / name
        if not f.is_file():
            raise BadBundle(f"{path.name}: {MANIFEST} lists {name}, which is missing")
        actual = _sha256(f)
        if actual != meta.get("sha256"):
            raise BadBundle(
                f"{path.name}: {name} does not match its recorded checksum — "
                "the bundle was modified after export; re-export it rather than filling it"
            )

    cv_pdf = path / "cv.pdf"
    if not cv_pdf.is_file():
        raise BadBundle(f"{path.name}: no cv.pdf")
    cv_md_path = path / "cv.md"
    if not cv_md_path.is_file():
        raise BadBundle(f"{path.name}: no cv.md — nothing can answer questions about her experience")
    facts_path = path / "facts.md"
    if not facts_path.is_file():
        raise BadBundle(f"{path.name}: no facts.md")

    cover = None
    cover_name = job.get("cover_letter")
    if cover_name:
        cover_path = path / cover_name
        if not cover_path.is_file():
            raise BadBundle(f"{path.name}: {MANIFEST} names {cover_name}, which is missing")
        cover = cover_path.read_text(encoding="utf-8")
        if not letter_names_company(cover, job.get("company", "")):
            raise BadBundle(
                f"{path.name}: the cover letter never mentions \"{job['company']}\" — "
                "it may belong to another application"
            )

    return Bundle(
        path=path,
        job=job,
        cv_pdf=cv_pdf,
        cv_md=cv_md_path.read_text(encoding="utf-8"),
        facts_md=facts_path.read_text(encoding="utf-8"),
        cover_letter=cover,
    )


def discover(target: Path) -> list[Bundle]:
    """One bundle if `target` is a bundle, otherwise every bundle beneath it.

    Anything under done/ is skipped: those were submitted, and Greenhouse takes
    duplicate applications while Ashby silently merges them by email, so a
    second fill is invisible rather than rejected.
    """
    target = Path(target).expanduser().resolve()
    if not target.is_dir():
        raise BadBundle(f"{target} is not a directory")
    if (target / MANIFEST).is_file():
        return [load(target)]

    dirs = sorted(d for d in target.iterdir() if d.is_dir() and d.name != DONE_DIR)
    bundles = [load(d) for d in dirs if (d / MANIFEST).is_file()]
    if not bundles:
        raise BadBundle(f"no bundles under {target} (expected subdirectories holding {MANIFEST})")
    return bundles


def liveness(url: str) -> tuple[str, str]:
    """('active' | 'expired' | 'uncertain' | 'unchecked', detail).

    Delegates to career-ops' check-liveness.mjs, which is zero-token and about a
    second — cheap insurance against a paid browser run against a dead posting.
    The check that matters happens HERE, not at export: a bundle can sit for days,
    and run-chain.sh's own liveness stage only ever sees unevaluated pipeline rows.

    Its exit code conflates expired with uncertain, so the verdict is read from
    stdout. Unchecked and uncertain both proceed — refusing to fill on a merely
    unconfirmed posting would block more real applications than it saves.
    """
    repo = os.getenv("CAREER_OPS_REPO")
    if not repo:
        return "unchecked", "CAREER_OPS_REPO not set"
    # resolve() before use: the subprocess runs WITH cwd set to the repo, so a
    # relative script path (the documented ../../career-ops) would be re-resolved
    # against that new cwd and miss. It failed as "uncertain", which proceeds —
    # so the check went quietly missing instead of erroring.
    root = Path(repo).expanduser().resolve()
    script = root / "check-liveness.mjs"
    if not script.is_file():
        return "unchecked", f"no check-liveness.mjs at {script}"
    try:
        proc = subprocess.run(
            ["node", str(script), url],
            capture_output=True, text=True, timeout=LIVENESS_TIMEOUT_S, cwd=str(root),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return "unchecked", f"liveness check did not run ({type(exc).__name__})"

    return parse_liveness(proc.stdout)


def parse_liveness(stdout: str) -> tuple[str, str]:
    """Read the verdict off check-liveness.mjs's summary line.

        Results: 1 active  0 expired  0 uncertain  (0 via API, no browser)

    The summary is parsed rather than the per-URL line because only the summary
    is a fixed shape; the per-URL line carries an emoji and padding. Anything
    unrecognised is 'uncertain', which proceeds — the one verdict that stops a
    run has to be positively asserted, never inferred from a parse failure.
    """
    m = re.search(r"Results:\s*(\d+) active\s+(\d+) expired\s+(\d+) uncertain", stdout)
    if not m:
        return "uncertain", "could not read the liveness summary"
    active, expired, _ = (int(g) for g in m.groups())
    if expired:
        return "expired", "check-liveness reports the posting is expired"
    if active:
        return "active", "confirmed live"
    return "uncertain", "liveness inconclusive"
