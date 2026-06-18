#!/usr/bin/env python3
"""Local agent worktree hygiene helpers."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT_BRANCH = "main"
ORIGIN_MAIN = "origin/main"
VALID_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class Worktree:
    path: Path
    head: str | None
    branch: str | None
    locked: str | None

    @property
    def is_locked(self) -> bool:
        return self.locked is not None


def run(
    args: list[str],
    *,
    cwd: Path,
    check: bool = True,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        check=check,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def git(args: list[str], *, cwd: Path, check: bool = True) -> str:
    completed = run(["git", *args], cwd=cwd, check=check)
    return completed.stdout.strip()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_worktrees(repo: Path) -> list[Worktree]:
    raw = git(["worktree", "list", "--porcelain"], cwd=repo)
    entries: list[Worktree] = []
    current: dict[str, str] = {}

    def flush() -> None:
        if "worktree" not in current:
            return
        entries.append(
            Worktree(
                path=Path(current["worktree"]),
                head=current.get("HEAD"),
                branch=current.get("branch", "").removeprefix("refs/heads/") or None,
                locked=current.get("locked"),
            )
        )

    for line in raw.splitlines():
        if not line:
            flush()
            current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    flush()
    return entries


def find_main_worktree(repo: Path) -> Path:
    for worktree in parse_worktrees(repo):
        if worktree.branch == ROOT_BRANCH:
            return worktree.path
    fail("could not find a linked worktree checked out on main")


def require_clean(path: Path, *, label: str) -> None:
    status = git(["status", "--porcelain"], cwd=path)
    if status:
        print(status, file=sys.stderr)
        fail(f"{label} has local changes")


def validate_segment(value: str, *, name: str) -> str:
    if not VALID_SEGMENT.match(value):
        fail(f"{name} must match {VALID_SEGMENT.pattern!r}; got {value!r}")
    if ".." in value:
        fail(f"{name} must not contain '..'; got {value!r}")
    return value


def branch_name(agent: str, slug: str, issue: str | None) -> str:
    if issue:
        validate_segment(issue, name="ISSUE")
        return f"{agent}/issue-{issue}-{slug}"
    return f"{agent}/{slug}"


def worktree_path(main_path: Path, agent: str, slug: str) -> Path:
    return main_path.parent / f"{main_path.name}.worktrees" / agent / slug


def sync_main(repo: Path) -> Path:
    main_path = find_main_worktree(repo)
    require_clean(main_path, label="main checkout")
    git(["fetch", "--prune", "origin"], cwd=main_path)
    current = git(["branch", "--show-current"], cwd=main_path)
    if current != ROOT_BRANCH:
        fail(f"main checkout is on {current!r}, expected {ROOT_BRANCH!r}")
    git(["pull", "--ff-only", "origin", ROOT_BRANCH], cwd=main_path)
    return main_path


def create_worktree(args: argparse.Namespace) -> None:
    repo = Path.cwd()
    agent = validate_segment(args.agent, name="AGENT")
    slug = validate_segment(args.slug, name="SLUG")
    main_path = sync_main(repo)
    destination = worktree_path(main_path, agent, slug)
    branch = branch_name(agent, slug, args.issue)
    reason_parts = [f"active agent:{agent}", f"slug:{slug}"]
    if args.issue:
        reason_parts.append(f"issue:{args.issue}")
    reason = " ".join(reason_parts)

    if destination.exists():
        fail(f"target worktree already exists: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    git(["worktree", "add", str(destination), "-b", branch, ORIGIN_MAIN], cwd=main_path)
    git(["worktree", "lock", "--reason", reason, str(destination)], cwd=main_path)
    print(f"created {destination}")
    print(f"branch {branch}")
    print(f"locked {reason}")


def clean_status(path: Path) -> bool:
    return git(["status", "--porcelain"], cwd=path) == ""


def merged_branches(repo: Path) -> set[str]:
    output = git(["branch", "--merged", ORIGIN_MAIN, "--format=%(refname:short)"], cwd=repo)
    return {line.strip() for line in output.splitlines() if line.strip()}


def local_branches(repo: Path) -> set[str]:
    output = git(["branch", "--format=%(refname:short)"], cwd=repo)
    return {line.strip() for line in output.splitlines() if line.strip()}


def gone_upstream_branches(repo: Path) -> list[str]:
    output = git(
        [
            "for-each-ref",
            "refs/heads",
            "--format=%(refname:short)|%(upstream:short)|%(upstream:track)",
        ],
        cwd=repo,
    )
    gone: list[str] = []
    for line in output.splitlines():
        branch, upstream, track = line.split("|", 2)
        if upstream and "gone" in track:
            gone.append(branch)
    return gone


def remote_branches(repo: Path) -> list[str]:
    output = git(["branch", "-r", "--format=%(refname:short)"], cwd=repo)
    branches: list[str] = []
    for line in output.splitlines():
        ref = line.strip()
        if not ref or ref in {"origin", "origin/HEAD", "origin/main"}:
            continue
        branches.append(ref.removeprefix("origin/"))
    return branches


def open_pr_heads(repo: Path) -> set[str] | None:
    completed = run(
        ["gh", "pr", "list", "--state", "open", "--limit", "200", "--json", "headRefName"],
        cwd=repo,
        check=False,
    )
    if completed.returncode != 0:
        print(
            "warning: could not query open PRs with gh; skipping remote no-PR report",
            file=sys.stderr,
        )
        if completed.stderr:
            print(completed.stderr.strip(), file=sys.stderr)
        return None
    rows = json.loads(completed.stdout or "[]")
    return {row["headRefName"] for row in rows if row.get("headRefName")}


def delete_branch(repo: Path, branch: str) -> None:
    completed = run(["git", "branch", "-d", branch], cwd=repo, check=False)
    if completed.returncode != 0:
        print(completed.stderr.strip(), file=sys.stderr)
        fail(f"failed to delete branch {branch!r}")
    print(completed.stdout.strip())


def clean_worktrees(args: argparse.Namespace) -> None:
    repo = Path.cwd()
    git(["fetch", "--prune", "origin"], cwd=repo)
    worktrees = parse_worktrees(repo)
    merged = merged_branches(repo)
    branches = local_branches(repo)
    checked_out = {wt.branch for wt in worktrees if wt.branch}

    clean: list[Worktree] = []
    dirty: list[Worktree] = []
    locked: list[Worktree] = []
    for wt in worktrees:
        if wt.is_locked:
            locked.append(wt)
        if clean_status(wt.path):
            clean.append(wt)
        else:
            dirty.append(wt)

    print("Clean worktrees:")
    for wt in clean:
        marker = " locked" if wt.is_locked else ""
        print(f"  {wt.path} [{wt.branch or 'detached'}]{marker}")

    print("Dirty worktrees:")
    if dirty:
        for wt in dirty:
            marker = " locked" if wt.is_locked else ""
            print(f"  {wt.path} [{wt.branch or 'detached'}]{marker}")
    else:
        print("  none")

    print("Locked active worktrees:")
    if locked:
        for wt in locked:
            print(f"  {wt.path} [{wt.branch or 'detached'}] reason={wt.locked}")
    else:
        print("  none")

    gone = gone_upstream_branches(repo)
    print("Branches whose upstream is gone:")
    if gone:
        for branch in gone:
            print(f"  {branch}")
    else:
        print("  none")

    heads = open_pr_heads(repo)
    print("Remote branches with no open PR:")
    if heads is None:
        print("  unknown")
    else:
        no_pr = [branch for branch in remote_branches(repo) if branch not in heads]
        if no_pr:
            for branch in no_pr:
                print(f"  origin/{branch}")
        else:
            print("  none")

    print("Automatic cleanup:")
    removed_any = False
    for wt in worktrees:
        if wt.branch in {None, ROOT_BRANCH}:
            continue
        if wt.is_locked or wt not in clean or wt.branch not in merged:
            continue
        print(f"  removing clean merged worktree {wt.path} [{wt.branch}]")
        git(["worktree", "remove", str(wt.path)], cwd=repo)
        checked_out.discard(wt.branch)
        removed_any = True

    for branch in sorted((branches & merged) - {ROOT_BRANCH} - checked_out):
        print(f"  deleting merged local branch {branch}")
        delete_branch(repo, branch)
        removed_any = True

    if not removed_any:
        print("  nothing eligible")


def evacuate_main(args: argparse.Namespace) -> None:
    repo = Path.cwd()
    agent = validate_segment(args.agent, name="AGENT")
    slug = validate_segment(args.slug, name="SLUG")
    main_path = find_main_worktree(repo)
    if git(["branch", "--show-current"], cwd=main_path) != ROOT_BRANCH:
        fail("main checkout is not on main")
    if clean_status(main_path):
        fail("main checkout is already clean; nothing to evacuate")

    destination = worktree_path(main_path, agent, slug)
    branch = branch_name(agent, slug, args.issue)
    if destination.exists():
        fail(f"target worktree already exists: {destination}")

    git(["fetch", "--prune", "origin"], cwd=main_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    git(["worktree", "add", str(destination), "-b", branch, ORIGIN_MAIN], cwd=main_path)

    stash_message = f"agent-evacuate:{agent}:{slug}"
    before = git(["stash", "list"], cwd=main_path)
    stash_result = run(
        ["git", "stash", "push", "-u", "-m", stash_message],
        cwd=main_path,
        check=False,
    )
    if stash_result.returncode != 0:
        print(stash_result.stderr.strip(), file=sys.stderr)
        fail("failed to stash dirty main")

    after = git(["stash", "list"], cwd=main_path)
    if before == after:
        fail("stash did not create an entry; refusing to continue")

    apply_result = run(["git", "stash", "apply", "stash@{0}"], cwd=destination, check=False)
    if apply_result.returncode != 0:
        print(apply_result.stdout.strip())
        print(apply_result.stderr.strip(), file=sys.stderr)
        print("stash kept as stash@{0}; inspect before dropping it", file=sys.stderr)
        fail(f"failed to apply evacuated changes to {destination}")

    git(["stash", "drop", "stash@{0}"], cwd=main_path)
    reason_parts = [f"active agent:{agent}", f"slug:{slug}", "evacuated-from-main"]
    if args.issue:
        reason_parts.append(f"issue:{args.issue}")
    reason = " ".join(reason_parts)
    git(["worktree", "lock", "--reason", reason, str(destination)], cwd=main_path)
    print(f"evacuated main changes to {destination}")
    print(f"branch {branch}")
    print(f"locked {reason}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    worktree = subparsers.add_parser("worktree", help="create and lock a clean agent worktree")
    worktree.add_argument("--agent", required=True, choices=["codex", "claude"])
    worktree.add_argument("--slug", required=True)
    worktree.add_argument("--issue")
    worktree.set_defaults(func=create_worktree)

    clean = subparsers.add_parser("clean", help="report and safely clean merged agent branches")
    clean.set_defaults(func=clean_worktrees)

    evacuate = subparsers.add_parser(
        "evacuate",
        help="move dirty main changes to an agent worktree",
    )
    evacuate.add_argument("--agent", required=True, choices=["codex", "claude"])
    evacuate.add_argument("--slug", required=True)
    evacuate.add_argument("--issue")
    evacuate.set_defaults(func=evacuate_main)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
