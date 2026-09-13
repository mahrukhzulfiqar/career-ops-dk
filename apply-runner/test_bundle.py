"""Cover for bundle.py — the checks that stand between a bundle and a real form."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

import bundle as bundles
from bundle import BadBundle


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def make_bundle(root: Path, name="011-queue-it", company="Queue-it ApS", cover=None) -> Path:
    d = root / name
    d.mkdir(parents=True)
    files = {}
    for fname, content in [("cv.pdf", b"%PDF-1.4 fake"),
                           ("cv.md", b"# CV\n\nProduct Manager at Example Corp.\n"),
                           ("facts.md", b"# Identity facts\n\n- Full name: A Person\n")]:
        (d / fname).write_bytes(content)
        files[fname] = {"sha256": sha(content), "bytes": len(content)}
    if cover is not None:
        (d / "cover-letter.md").write_text(cover, encoding="utf-8")
        files["cover-letter.md"] = {"sha256": sha(cover.encode()), "bytes": len(cover.encode())}
    (d / "job.json").write_text(json.dumps({
        "report": "011", "company": company, "role": "Product Manager",
        "url": "https://careers.example.com/jobs/1",
        "cover_letter": "cover-letter.md" if cover is not None else None,
        "candidate": {
            "full_name": "A Person", "email": "a@example.com", "phone": "+45 1",
            "location": "Copenhagen, Denmark", "linkedin": "in/a",
            "current_title": "Product Manager", "current_employer": "Example Corp",
            "resident_in_denmark": True,
        },
        "files": files,
    }), encoding="utf-8")
    return d


# --- happy path -------------------------------------------------------------

def test_loads_a_well_formed_bundle(tmp_path):
    b = bundles.load(make_bundle(tmp_path))
    assert b.company == "Queue-it ApS"
    assert b.url == "https://careers.example.com/jobs/1"
    assert "Example Corp" in b.cv_md
    assert b.cover_letter is None


def test_label_combines_company_and_role(tmp_path):
    assert bundles.load(make_bundle(tmp_path)).label == "Queue-it ApS — Product Manager"


# --- integrity --------------------------------------------------------------

def test_modified_file_is_refused(tmp_path):
    d = make_bundle(tmp_path)
    (d / "cv.pdf").write_bytes(b"a DIFFERENT pdf")
    with pytest.raises(BadBundle, match="checksum"):
        bundles.load(d)


def test_missing_listed_file_is_refused(tmp_path):
    d = make_bundle(tmp_path)
    (d / "facts.md").unlink()
    with pytest.raises(BadBundle, match="missing"):
        bundles.load(d)


def test_missing_cv_md_is_refused(tmp_path):
    """Without cv.md nothing can answer a factual question about her experience."""
    d = make_bundle(tmp_path)
    job = json.loads((d / "job.json").read_text())
    del job["files"]["cv.md"]
    (d / "job.json").write_text(json.dumps(job))
    (d / "cv.md").unlink()
    with pytest.raises(BadBundle, match="cv.md"):
        bundles.load(d)


def test_unreadable_manifest_is_refused(tmp_path):
    d = make_bundle(tmp_path)
    (d / "job.json").write_text("{not json")
    with pytest.raises(BadBundle, match="unreadable"):
        bundles.load(d)


# --- the anti-crossing guard ------------------------------------------------

def test_cover_letter_for_another_company_is_refused(tmp_path):
    d = make_bundle(tmp_path, company="Templafy",
                    cover="Dear Queue-it team, I am excited about this role.")
    with pytest.raises(BadBundle, match="never mentions"):
        bundles.load(d)


def test_matching_cover_letter_is_accepted(tmp_path):
    d = make_bundle(tmp_path, company="Queue-it ApS",
                    cover="Dear Queue-it team, I am excited about this role.")
    assert "Queue-it" in bundles.load(d).cover_letter


def test_letter_names_company_matches_first_token():
    assert bundles.letter_names_company("Dear Queue-it team", "Queue-it ApS")


def test_letter_names_company_is_case_insensitive():
    assert bundles.letter_names_company("dear TEMPLAFY team", "Templafy")


def test_letter_names_company_passes_when_company_unknown():
    assert bundles.letter_names_company("anything", "")


# --- identity ---------------------------------------------------------------

def test_identity_maps_location_to_city(tmp_path):
    assert bundles.load(make_bundle(tmp_path)).identity()["city"] == "Copenhagen, Denmark"


def test_identity_rejects_a_missing_field(tmp_path):
    d = make_bundle(tmp_path)
    job = json.loads((d / "job.json").read_text())
    del job["candidate"]["email"]
    (d / "job.json").write_text(json.dumps(job))
    with pytest.raises(BadBundle, match="email"):
        bundles.load(d).identity()


def test_identity_keeps_a_false_boolean(tmp_path):
    """False is a real answer. Treating it as absence would blank a real field."""
    d = make_bundle(tmp_path)
    job = json.loads((d / "job.json").read_text())
    job["candidate"]["resident_in_denmark"] = False
    (d / "job.json").write_text(json.dumps(job))
    assert bundles.load(d).identity()["resident_in_denmark"] is False


# --- discovery --------------------------------------------------------------

def test_discover_finds_every_bundle_under_a_root(tmp_path):
    make_bundle(tmp_path, "011-queue-it")
    make_bundle(tmp_path, "012-templafy", company="Templafy")
    assert len(bundles.discover(tmp_path)) == 2


def test_discover_skips_done(tmp_path):
    make_bundle(tmp_path, "011-queue-it")
    done = tmp_path / "done"
    done.mkdir()
    shutil.move(str(make_bundle(tmp_path, "012-templafy", company="Templafy")), str(done / "012-templafy"))
    found = bundles.discover(tmp_path)
    assert [b.path.name for b in found] == ["011-queue-it"]


def test_discover_accepts_a_single_bundle_directory(tmp_path):
    d = make_bundle(tmp_path)
    assert [b.path.name for b in bundles.discover(d)] == ["011-queue-it"]


def test_discover_refuses_an_empty_root(tmp_path):
    with pytest.raises(BadBundle, match="no bundles"):
        bundles.discover(tmp_path)


# --- liveness ---------------------------------------------------------------

def test_liveness_is_unchecked_without_the_repo(monkeypatch):
    monkeypatch.delenv("CAREER_OPS_REPO", raising=False)
    verdict, _ = bundles.liveness("https://example.com/j/1")
    assert verdict == "unchecked"


def test_liveness_is_unchecked_when_the_script_is_absent(monkeypatch, tmp_path):
    monkeypatch.setenv("CAREER_OPS_REPO", str(tmp_path))
    verdict, detail = bundles.liveness("https://example.com/j/1")
    assert verdict == "unchecked" and "check-liveness" in detail


# --- liveness parsing (the verdict that skips a paid browser run) -----------

ACTIVE = "Checking 1 URL(s)...\n\n✅ active           https://x/j/1\n\nResults: 1 active  0 expired  0 uncertain  (0 via API, no browser)\n"
EXPIRED = "Checking 1 URL(s)...\n\n❌ expired          https://x/j/1\n           posting removed\n\nResults: 0 active  1 expired  0 uncertain  (1 via API, no browser)\n"
UNCERTAIN = "Checking 1 URL(s)...\n\n⚠️ uncertain        https://x/j/1\n\nResults: 0 active  0 expired  1 uncertain  (0 via API, no browser)\n"


def test_parse_liveness_reads_active():
    assert bundles.parse_liveness(ACTIVE)[0] == "active"


def test_parse_liveness_reads_expired():
    assert bundles.parse_liveness(EXPIRED)[0] == "expired"


def test_parse_liveness_reads_uncertain():
    assert bundles.parse_liveness(UNCERTAIN)[0] == "uncertain"


def test_parse_liveness_falls_back_to_uncertain_on_junk():
    """A parse failure must never read as 'expired' — that would skip a live job."""
    assert bundles.parse_liveness("node: command not found")[0] == "uncertain"


def test_parse_liveness_does_not_confuse_the_word_expired_in_prose():
    noisy = "the previous posting expired last week\nResults: 1 active  0 expired  0 uncertain\n"
    assert bundles.parse_liveness(noisy)[0] == "active"


def test_liveness_resolves_a_relative_repo_path(monkeypatch, tmp_path):
    """A relative CAREER_OPS_REPO must survive the subprocess cwd change.

    The script path is passed to a subprocess whose cwd IS the repo, so leaving
    it relative re-resolves it against the new cwd and silently loses the check.
    """
    repo = tmp_path / "career-ops"
    repo.mkdir()
    (repo / "check-liveness.mjs").write_text("// stub")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CAREER_OPS_REPO", "./career-ops")
    verdict, detail = bundles.liveness("https://example.com/j/1")
    # The stub prints no summary, so the verdict is uncertain — but it must have
    # RUN, not been reported as unchecked/absent.
    assert verdict == "uncertain", f"expected the script to be found and run, got {verdict}: {detail}"
