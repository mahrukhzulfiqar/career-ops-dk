"""Mechanically derived facts from career-ops' profile.

Reads named keys out of config/profile.yml verbatim. It never summarizes,
infers, or rephrases — see the Source-of-Truth Boundary in career-ops'
AGENTS.md. If a value is not in the profile it is absent here, and the agent
is told to stop rather than invent one.
"""

import os
from pathlib import Path

import yaml


class MissingFact(KeyError):
    pass


def career_ops_repo() -> Path:
    repo = os.getenv("CAREER_OPS_REPO")
    if not repo:
        raise MissingFact("CAREER_OPS_REPO is not set; see .env.example")
    path = Path(repo)
    if not path.is_dir():
        raise MissingFact(f"CAREER_OPS_REPO does not exist: {path}")
    return path


def load_profile(repo: Path = None) -> dict:
    repo = repo or career_ops_repo()
    profile_path = repo / "config" / "profile.yml"
    if not profile_path.is_file():
        raise MissingFact(f"no profile at {profile_path}")
    return yaml.safe_load(profile_path.read_text()) or {}


def identity(profile: dict) -> dict:
    """The fields every application form asks for, copied verbatim."""
    candidate = profile.get("candidate") or {}
    location = candidate.get("location") or profile.get("location") or {}
    if isinstance(location, str):
        location = {"city": location}

    values = {
        "full_name": candidate.get("full_name"),
        "email": candidate.get("email"),
        "phone": candidate.get("phone"),
        "city": location.get("city"),
        "linkedin": candidate.get("linkedin"),
        "current_title": candidate.get("current_title"),
        "current_employer": candidate.get("current_employer"),
    }
    missing = [k for k, v in values.items() if not v]
    if missing:
        raise MissingFact(f"profile.yml is missing: {', '.join(missing)}")

    # Booleans must be read separately: `False` is a real answer, not absence.
    resident = candidate.get("resident_in_denmark")
    if resident is None:
        raise MissingFact("profile.yml is missing: resident_in_denmark")
    values["resident_in_denmark"] = bool(resident)
    return values


def cv_text(repo: Path = None) -> str:
    """cv.md, verbatim.

    cv.md is a primary source under career-ops' Source-of-Truth Boundary, so
    the agent may answer factual questions about experience, responsibilities
    and accomplishments from it. It is passed whole and unedited — summarizing
    it here would put a model between the ground truth and the answer, which is
    the fabrication path this system exists to close.
    """
    repo = repo or career_ops_repo()
    cv_path = repo / "cv.md"
    if not cv_path.is_file():
        raise MissingFact(f"no cv.md at {cv_path}")
    return cv_path.read_text()


def cv_pdf(repo: Path = None) -> Path:
    repo = repo or career_ops_repo()
    candidates = sorted((repo / "output").glob("*.pdf"))
    if not candidates:
        raise MissingFact(f"no CV PDF in {repo / 'output'}")
    if len(candidates) > 1:
        # The real runner is handed exactly one cv.pdf inside a per-job
        # handoff directory, so this ambiguity cannot arise there.
        raise MissingFact(
            f"{len(candidates)} PDFs in output/; the fill test needs exactly one: "
            + ", ".join(p.name for p in candidates)
        )
    return candidates[0]
