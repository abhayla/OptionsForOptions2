# ruff: noqa: E501, PLR2004, S603, S607, RUF059
"""Lane CC: each flag of lane_watch.py is tested on a throwaway repository (a bare origin and a clone) and named after
the real fault of 28 Nov 2026 it must catch. Nothing here touches this repository."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("lane_watch", ROOT / ".claude" / "skills" / "lanes" / "lane_watch.py")
lane_watch = importlib.util.module_from_spec(_spec)
sys.modules["lane_watch"] = lane_watch
_spec.loader.exec_module(lane_watch)

MIG = "backend/ofo_app/alembic/versions"
NOW = "2026-11-28T22:40:00+05:30"
BUILD = "integration/weekend"


class Repo:
    """A bare origin plus one working clone. `commit` writes files on a branch at a given (IST) time and pushes."""

    def __init__(self, tmp: Path):
        self.origin = tmp / "origin.git"
        self.w = tmp / "w"
        self.tmp = tmp
        self._git(tmp, "init", "--bare", "-b", "main", str(self.origin))
        self._git(tmp, "clone", str(self.origin), str(self.w))
        self._git(self.w, "config", "user.email", "t@example.com")
        self._git(self.w, "config", "user.name", "t")
        self._git(self.w, "checkout", "-b", "main")
        self.commit("main", {f"{MIG}/0062_base.py": 'revision = "0062_base"\ndown_revision = "0061_x"\n',
                             "docs/a.md": "a\n"}, "2026-11-28T08:00:00+05:30")
        self._git(self.w, "branch", BUILD)
        self._git(self.w, "push", "-q", "origin", BUILD)

    def _git(self, cwd, *args, when=None):
        env = dict(os.environ)
        if when:
            env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = when
        p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env, check=False)
        assert p.returncode == 0, p.stderr
        return p.stdout

    def commit(self, branch, files, when, base="main"):
        existing = self._git(self.w, "branch", "--list", branch).strip()
        if branch != "main":
            if existing:
                self._git(self.w, "checkout", "-q", branch)
            else:
                self._git(self.w, "checkout", "-q", "-b", branch, base)
        for rel, text in files.items():
            f = self.w / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(text, encoding="utf-8")
        self._git(self.w, "add", "-A")
        self._git(self.w, "commit", "-q", "-m", f"c {when}", when=when)
        self._git(self.w, "push", "-q", "origin", branch)
        sha = self._git(self.w, "rev-parse", "HEAD").strip()
        self._git(self.w, "checkout", "-q", "main")
        return sha

    def merge(self, target, source, when):
        self._git(self.w, "checkout", "-q", target)
        self._git(self.w, "merge", "-q", "--no-ff", "-m", f"merge {source}", f"origin/{source}", when=when)
        self._git(self.w, "push", "-q", "origin", target)
        sha = self._git(self.w, "rev-parse", "HEAD").strip()
        self._git(self.w, "checkout", "-q", "main")
        return sha

    def run(self, state, now=NOW, *extra, capsys=None):
        sf = self.tmp / "state.json"
        sf.write_text(json.dumps(state), encoding="utf-8")
        code = lane_watch.main(["--repo", str(self.w), "--state", str(sf), "--now", now, "--no-fetch", *extra])
        return code, (capsys.readouterr().out if capsys else "")


def lane(name, branch=None, **kw):
    d = {"name": name, "session_id": f"session_{name}", "branch": branch or f"feat/{name.lower()}",
         "results_file": f"RESULTS-{name}.md", "owns": [f"area/{name.lower()}/**", f"RESULTS-{name}.md"],
         "state": "working", "started_at": "2026-11-28T17:00:00+05:30",
         "first_push_due": "2026-11-28T18:15:00+05:30", "next_push_due": None, "context_note": ""}
    d.update(kw)
    return d


def state(lanes, **kw):
    s = {"lanes": lanes, "holds": [], "conditions": [], "waves": [], "build": {"branch": BUILD, "pull_request": 881},
         "commitments": [], "instructions": []}
    s.update(kw)
    return s


@pytest.fixture
def repo(tmp_path):
    return Repo(tmp_path)


def mig(rev, down="0062_base"):
    return {f"{MIG}/{rev}.py": f'revision = "{rev}"\ndown_revision = "{down}"\n'}


def test_lane_watch_migration_three_lanes_0063(repo, capsys):
    """28 Nov: RA2, B2 and R1 each numbered a migration 0063 on parent 0062; two heads, `upgrade head` fails."""
    names = {"RA2": "0063_basket_facts_spot_at", "B2": "0063_order_attempts", "R1": "0063_position_tags"}
    for n, rev in names.items():
        repo.commit(f"feat/{n.lower()}", {**mig(rev), f"area/{n.lower()}/x.py": "x\n"}, "2026-11-28T21:50:00+05:30")
    code, out = repo.run(state([lane(n) for n in names]), capsys=capsys)
    assert code == 1
    assert out.count("MIGRATION COLLISION") == 3  # three pairs
    for rev in names.values():
        assert rev in out
    assert "same revision number 0063" in out and "same down_revision 0062_base" in out


def test_lane_watch_migration_no_collision_when_numbers_differ(repo, capsys):
    repo.commit("feat/ra2", mig("0063_a"), "2026-11-28T21:50:00+05:30")
    repo.commit("feat/b2", mig("0064_b", "0063_a"), "2026-11-28T21:50:00+05:30")
    code, out = repo.run(state([lane("RA2"), lane("B2")]), capsys=capsys)
    assert "MIGRATION COLLISION" not in out
    assert code == 0


def test_lane_watch_migration_same_file_on_two_lanes_is_not_a_collision(repo, capsys):
    """Two lanes cut from one commit that holds 0063 both 'add' the same file: one migration, not two."""
    repo.commit("feat/base0063", mig("0063_shared"), "2026-11-28T20:00:00+05:30")
    for n in ("ra2", "b2"):
        repo.commit(f"feat/{n}", {f"area/{n}/x.py": "x\n"}, "2026-11-28T21:00:00+05:30", base="feat/base0063")
    _, out = repo.run(state([lane("RA2"), lane("B2")]), capsys=capsys)
    assert "MIGRATION COLLISION" not in out


def test_lane_watch_migration_lane_collides_with_build(repo, capsys):
    """A lane's 0063 against a 0063 already in the build."""
    repo.commit("feat/ra2", mig("0063_lane"), "2026-11-28T21:00:00+05:30")
    repo.commit(BUILD, mig("0063_build"), "2026-11-28T21:30:00+05:30")
    code, out = repo.run(state([lane("RA2")]), capsys=capsys)
    assert code == 1 and "MIGRATION COLLISION" in out and "0063_build" in out


def test_lane_watch_overdue_f1b_no_branch_83_minutes_after_start(repo, capsys):
    """28 Nov: F1b had no branch on origin 83 minutes after start (first push due at 75 minutes)."""
    f1b = lane("F1b", started_at="2026-11-28T21:17:00+05:30", first_push_due="2026-11-28T22:32:00+05:30")
    code, out = repo.run(state([f1b]), capsys=capsys)
    assert "OVERDUE" in out and "no branch" in out and "F1b" in out
    assert out.startswith("ACT NOW: 1")
    assert code == 0  # a late push alone does not exit 1


def test_lane_watch_overdue_r1_missed_2230_push(repo, capsys):
    """28 Nov: R1's 22:30 push was missed. Last commit 21:00, next_push_due 22:30, now 22:40."""
    repo.commit("feat/r1", {"area/r1/x.py": "x\n"}, "2026-11-28T21:00:00+05:30")
    r1 = lane("R1", next_push_due="2026-11-28T22:30:00+05:30")
    _, out = repo.run(state([r1]), capsys=capsys)
    assert "OVERDUE: R1: push due 22:30" in out and "10 min late" in out


def test_lane_watch_not_overdue_when_pushed_after_the_due_time(repo, capsys):
    repo.commit("feat/r1", {"area/r1/x.py": "x\n"}, "2026-11-28T22:35:00+05:30")
    r1 = lane("R1", next_push_due="2026-11-28T22:30:00+05:30")
    _, out = repo.run(state([r1]), capsys=capsys)
    assert "OVERDUE" not in out


def test_lane_watch_silent_f3_status_clock_is_not_a_heartbeat(repo, capsys):
    """28 Nov: F3's STATUS read 23:20 at 22:40. The commit is from 20:00, so the lane is SILENT."""
    repo.commit("feat/f3", {"RESULTS-F3.md": "STATUS 23:20 | item 3: fixed | next push 23:50 | blocker: none\n"},
                "2026-11-28T20:00:00+05:30")
    f3 = lane("F3", next_push_due="2026-11-28T19:00:00+05:30")
    code, out = repo.run(state([f3]), capsys=capsys)
    assert "SILENT: F3: no commit for 160 min" in out
    assert "STATUS CLOCK AHEAD" in out
    assert "STATUS 23:20" in out  # the text is shown, not trusted
    assert code == 0


def test_lane_watch_not_silent_when_a_commit_is_recent(repo, capsys):
    repo.commit("feat/f3", {"area/f3/x.py": "x\n"}, "2026-11-28T22:00:00+05:30")
    _, out = repo.run(state([lane("F3", next_push_due="2026-11-28T21:00:00+05:30")]), capsys=capsys)
    assert "SILENT" not in out and "40 min since last commit" in out


def test_lane_watch_status_line_shown_cut_to_200_characters(repo, capsys):
    repo.commit("feat/f3", {"RESULTS-F3.md": "STATUS 22:00 | " + "x" * 400 + "\n"}, "2026-11-28T22:00:00+05:30")
    _, out = repo.run(state([lane("F3", next_push_due="2026-11-28T21:00:00+05:30")]), capsys=capsys)
    line = next(ln for ln in out.splitlines() if ln.strip().startswith("STATUS 22:00"))
    assert len(line.strip()) == 200


def test_lane_watch_closing_without_safe_to_close_tg2(repo, capsys):
    """28 Nov: TG2 went to closing with no SAFE TO CLOSE line in its results file."""
    repo.commit("feat/tg2", {"RESULTS-TG2.md": "STATUS 22:00 | done | next push none | blocker: none\n"},
                "2026-11-28T22:00:00+05:30")
    tg2 = lane("TG2", state="closing")
    code, out = repo.run(state([tg2]), capsys=capsys)
    assert "CLOSING WITHOUT SAFE TO CLOSE: TG2" in out
    repo.commit("feat/tg2", {"RESULTS-TG2.md": "STATUS 22:10 | done\nSAFE TO CLOSE (head abc, nothing left)\n"},
                "2026-11-28T22:10:00+05:30")
    code, out = repo.run(state([tg2]), capsys=capsys)
    assert "CLOSING WITHOUT SAFE TO CLOSE" not in out and code == 0


def test_lane_watch_hold_ra2_with_f3_as_of_held_then_violated(repo, capsys):
    """28 Nov: RA2 was held at the lane only; the build merged the held commit. Violated when the build has it."""
    c1 = repo.commit("feat/ra2", {"area/ra2/a.py": "1\n"}, "2026-11-28T20:00:00+05:30")
    c2 = repo.commit("feat/ra2", {"area/ra2/b.py": "2\n"}, "2026-11-28T21:00:00+05:30")
    hold = {"branch": "feat/ra2", "commit": c2, "reason": "RA2 waits for F3's as-of", "until": "2026-11-29T06:00:00+05:30"}
    st = state([lane("RA2", next_push_due="2026-11-28T23:00:00+05:30")], holds=[hold])
    code, out = repo.run(st, capsys=capsys)
    assert "HELD feat/ra2" in out and "VIOLATED" not in out and code == 0
    repo.merge(BUILD, "feat/ra2", "2026-11-28T21:30:00+05:30")
    code, out = repo.run(st, capsys=capsys)
    assert code == 1 and "HOLD VIOLATED: feat/ra2" in out and "VIOLATED feat/ra2" in out
    # not_newer_than: the build may hold RA2 up to c1 only; it holds c2, so violated
    hold2 = {"branch": "feat/ra2", "not_newer_than": c1, "reason": "as-of", "until": "2026-11-29T06:00:00+05:30"}
    code, out = repo.run(state([lane("RA2", next_push_due="2026-11-28T23:00:00+05:30")], holds=[hold2]), capsys=capsys)
    assert code == 1 and "HOLD VIOLATED" in out


def test_lane_watch_hold_not_newer_than_allows_the_older_commit(repo, capsys):
    c1 = repo.commit("feat/ra2", {"area/ra2/a.py": "1\n"}, "2026-11-28T20:00:00+05:30")
    repo.merge(BUILD, "feat/ra2", "2026-11-28T20:30:00+05:30")
    repo.commit("feat/ra2", {"area/ra2/b.py": "2\n"}, "2026-11-28T21:00:00+05:30")
    hold = {"branch": "feat/ra2", "not_newer_than": c1, "reason": "as-of", "until": "2026-11-29T06:00:00+05:30"}
    code, out = repo.run(state([lane("RA2", next_push_due="2026-11-28T23:00:00+05:30")], holds=[hold]), capsys=capsys)
    assert "HOLD VIOLATED" not in out and code == 0


def test_lane_watch_hold_expired_is_not_violated(repo, capsys):
    c = repo.commit("feat/ra2", {"area/ra2/a.py": "1\n"}, "2026-11-28T20:00:00+05:30")
    repo.merge(BUILD, "feat/ra2", "2026-11-28T20:30:00+05:30")
    hold = {"branch": "feat/ra2", "commit": c, "reason": "r", "until": "2026-11-28T22:00:00+05:30"}
    code, out = repo.run(state([lane("RA2", next_push_due="2026-11-28T23:00:00+05:30")], holds=[hold]), capsys=capsys)
    assert code == 0 and "EXPIRED" in out


def test_lane_watch_file_overlap_and_outside_owns_six_conflicts(repo, capsys):
    """28 Nov: lanes edited files another lane owns; the build lane met 6 document and script conflicts."""
    repo.commit("feat/a", {"area/a/x.py": "1\n", "docs/shared.md": "A\n", "scripts/s.py": "A\n"},
                "2026-11-28T21:00:00+05:30")
    repo.commit("feat/b", {"area/b/y.py": "1\n", "docs/shared.md": "B\n"}, "2026-11-28T21:05:00+05:30")
    st = state([lane("A", next_push_due="2026-11-28T23:00:00+05:30"), lane("B", next_push_due="2026-11-28T23:00:00+05:30")])
    code, out = repo.run(st, capsys=capsys)
    assert "FILE OVERLAP: A and B both changed 1 file(s)" in out and "docs/shared.md" in out
    assert "OUTSIDE OWNS: A changed 2 file(s)" in out and "scripts/s.py" in out
    assert "OUTSIDE OWNS: B changed 1 file(s)" in out
    assert code == 0


def test_lane_watch_no_overlap_when_each_stays_in_its_own_files(repo, capsys):
    repo.commit("feat/a", {"area/a/x.py": "1\n"}, "2026-11-28T21:00:00+05:30")
    repo.commit("feat/b", {"area/b/y.py": "1\n"}, "2026-11-28T21:05:00+05:30")
    st = state([lane("A", next_push_due="2026-11-28T23:00:00+05:30"), lane("B", next_push_due="2026-11-28T23:00:00+05:30")])
    _, out = repo.run(st, capsys=capsys)
    assert "FILE OVERLAP" not in out and "OUTSIDE OWNS" not in out


def test_lane_watch_instruction_not_acknowledged_ra2_deaf_four_hours(repo, capsys):
    """28 Nov: instructions queued from 17:37 reached RA2 only at 21:42."""
    repo.commit("feat/ra2", {"area/ra2/a.py": "1\n"}, "2026-11-28T22:30:00+05:30")
    ins = [{"to_lane": "RA2", "sent_at": "2026-11-28T17:37:00+05:30", "text_short": "take F3 as-of",
            "acknowledged_at": None},
           {"to_lane": "RA2", "sent_at": "2026-11-28T22:25:00+05:30", "text_short": "fresh one", "acknowledged_at": None},
           {"to_lane": "RA2", "sent_at": "2026-11-28T18:00:00+05:30", "text_short": "old but heard",
            "acknowledged_at": "2026-11-28T18:20:00+05:30"}]
    _, out = repo.run(state([lane("RA2", next_push_due="2026-11-28T23:00:00+05:30")], instructions=ins), capsys=capsys)
    assert "INSTRUCTION NOT ACKNOWLEDGED: RA2: sent 17:37" in out and "303 min" in out
    assert out.count("INSTRUCTION NOT ACKNOWLEDGED") == 1


def test_lane_watch_wave_one_at_2245_and_the_10_00_freeze_commitment(repo, capsys):
    """28 Nov: wave 1 at 22:45 and the 10:00 freeze. A commitment past due exits 1; a wave past due does not."""
    waves = [{"name": "wave 1", "due": "2026-11-28T22:45:00+05:30", "commit": None, "ci": None}]
    com = [{"what": "freeze at 10:00", "by": "2026-11-29T10:00:00+05:30"}]
    st = state([], waves=waves, commitments=com)
    code, out = repo.run(st, now="2026-11-28T22:50:00+05:30", capsys=capsys)
    assert "WAVE PAST DUE: wave wave 1 was due 22:45" in out and code == 0
    code, out = repo.run(st, now="2026-11-29T10:05:00+05:30", capsys=capsys)
    assert code == 1 and "COMMITMENT PAST DUE: promised by 10:00" in out
    com[0]["done"] = True
    code, out = repo.run(st, now="2026-11-29T10:05:00+05:30", capsys=capsys)
    assert "COMMITMENT PAST DUE" not in out
    waves[0]["ci"] = "green"
    _, out = repo.run(st, now="2026-11-29T10:05:00+05:30", capsys=capsys)
    assert "WAVE PAST DUE" not in out


def test_lane_watch_condition_not_met_after_its_time(repo, capsys):
    st = state([], conditions=[{"what": "F3 as-of on origin", "by": "2026-11-28T22:00:00+05:30", "met": False}])
    _, out = repo.run(st, capsys=capsys)
    assert "CONDITION NOT MET" in out


def test_lane_watch_unknown_branch_hold_and_state_are_findings_not_crashes(repo, capsys):
    st = state([lane("Z", branch="feat/does-not-exist", next_push_due="2026-11-28T23:00:00+05:30")],
               holds=[{"branch": "feat/gone", "commit": "deadbeef" * 5, "reason": "r", "until": "2026-11-29T06:00:00+05:30"}])
    code, out = repo.run(st, capsys=capsys)
    assert "FINDING" in out and "deadbeef" in out
    assert code == 0
    st["build"] = {"branch": "integration/not-there", "pull_request": 1}
    code, out = repo.run(st, capsys=capsys)
    assert "build branch integration/not-there not found" in out


def test_lane_watch_state_file_unreadable_is_a_finding(tmp_path, capsys):
    code = lane_watch.main(["--repo", str(tmp_path), "--state", str(tmp_path / "nope.json"), "--no-fetch"])
    assert code == 1 and "ACT NOW: 1" in capsys.readouterr().out


def test_lane_watch_json_output_matches_text(repo, capsys):
    repo.commit("feat/r1", {"area/r1/x.py": "x\n"}, "2026-11-28T21:00:00+05:30")
    st = state([lane("R1", next_push_due="2026-11-28T22:30:00+05:30")])
    code, out = repo.run(st, NOW, "--json", capsys=capsys)
    data = json.loads(out)
    assert data["exit_code"] == code == 0
    assert [a["flag"] for a in data["act_now"]] == ["OVERDUE", "SILENT"]
    assert data["lanes"][0]["name"] == "R1" and data["lanes"][0]["minutes_since_commit"] == 100


def test_lane_watch_state_example_json_parses_and_runs(repo, capsys):
    ex = json.loads((ROOT / ".claude" / "skills" / "lanes" / "state.example.json").read_text("utf-8"))
    for key in ("lanes", "holds", "conditions", "waves", "build", "commitments", "instructions"):
        assert key in ex
    for ln in ex["lanes"]:
        for key in ("name", "session_id", "branch", "results_file", "owns", "state", "started_at", "first_push_due",
                    "next_push_due", "context_note"):
            assert key in ln, (ln["name"], key)
    code, out = repo.run(ex, now="2026-11-28T22:40:00+05:30", capsys=capsys)
    assert out.startswith("ACT NOW:")  # branches are unknown here: findings, no crash


def _tree_and_refs_hash(repo: Repo) -> str:
    h = hashlib.sha256()
    h.update(repo._git(repo.w, "for-each-ref", "--format=%(refname) %(objectname)").encode())
    h.update(repo._git(repo.w, "status", "--porcelain=v1", "-uall").encode())
    for p in sorted(repo.w.rglob("*")):
        if ".git" in p.parts or not p.is_file():
            continue
        h.update(str(p.relative_to(repo.w)).encode() + p.read_bytes())
    return h.hexdigest()


def test_lane_watch_makes_no_network_write_and_changes_no_file(repo, capsys):
    repo.commit("feat/ra2", {**mig("0063_a"), "area/ra2/a.py": "1\n"}, "2026-11-28T21:00:00+05:30")
    repo.commit("feat/b2", {**mig("0063_b"), "area/b2/a.py": "1\n"}, "2026-11-28T21:00:00+05:30")
    st = state([lane("RA2"), lane("B2")], holds=[{"branch": "feat/ra2", "commit": "0" * 40, "reason": "r", "until": None}])
    origin_before = repo._git(repo.origin, "for-each-ref")
    before = _tree_and_refs_hash(repo)
    lane_watch.GIT_LOG.clear()
    code, _ = repo.run(st, capsys=capsys)  # --no-fetch
    assert code == 1
    assert lane_watch.GIT_LOG, "no git command was logged"
    assert {c[0] for c in lane_watch.GIT_LOG} <= lane_watch.READ_ONLY
    assert "fetch" not in {c[0] for c in lane_watch.GIT_LOG}
    assert not {"push", "commit", "merge", "checkout", "reset", "add", "update-ref"} & {c[0] for c in lane_watch.GIT_LOG}
    assert _tree_and_refs_hash(repo) == before
    assert repo._git(repo.origin, "for-each-ref") == origin_before
    # with a fetch: the only extra command is one fetch, and origin still does not change
    lane_watch.GIT_LOG.clear()
    sf = repo.tmp / "state.json"
    lane_watch.main(["--repo", str(repo.w), "--state", str(sf), "--now", NOW])
    assert [c[0] for c in lane_watch.GIT_LOG].count("fetch") == 1
    assert {c[0] for c in lane_watch.GIT_LOG} <= lane_watch.READ_ONLY | {"fetch"}
    assert repo._git(repo.origin, "for-each-ref") == origin_before
    assert _tree_and_refs_hash(repo) == before


def test_lane_watch_refuses_a_git_write_command():
    with pytest.raises(RuntimeError):
        lane_watch.git(".", "push", "origin", "main")
