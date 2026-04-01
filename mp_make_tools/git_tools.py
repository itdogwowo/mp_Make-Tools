from __future__ import annotations

import os
import subprocess


def _git(args: list[str], *, cwd: str) -> tuple[int, str]:
    proc = subprocess.run(['git', *args], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return int(proc.returncode), (proc.stdout or '').strip()


def resolve_ref(repo_dir: str, ref: str) -> str | None:
    repo_dir = os.path.abspath(repo_dir)
    rc, out = _git(['rev-list', '-n', '1', ref], cwd=repo_dir)
    if rc != 0:
        return None
    return out


def head_commit(repo_dir: str) -> str | None:
    repo_dir = os.path.abspath(repo_dir)
    rc, out = _git(['rev-parse', 'HEAD'], cwd=repo_dir)
    if rc != 0:
        return None
    return out


def is_head_at_ref(repo_dir: str, ref: str) -> bool:
    desired = resolve_ref(repo_dir, ref)
    head = head_commit(repo_dir)
    return bool(desired and head and desired == head)


def tags_pointing_at_head(repo_dir: str) -> list[str]:
    repo_dir = os.path.abspath(repo_dir)
    rc, out = _git(['tag', '--points-at', 'HEAD'], cwd=repo_dir)
    if rc != 0 or not out:
        return []
    return [line.strip() for line in out.splitlines() if line.strip()]


def list_tags(repo_dir: str, *, limit: int = 50) -> list[str]:
    repo_dir = os.path.abspath(repo_dir)
    rc, out = _git(['tag', '--sort=-creatordate'], cwd=repo_dir)
    if rc != 0 or not out:
        return []
    tags = [line.strip() for line in out.splitlines() if line.strip()]
    return tags[: max(0, int(limit))]


def describe(repo_dir: str) -> str | None:
    repo_dir = os.path.abspath(repo_dir)
    rc, out = _git(['describe', '--tags', '--always', '--dirty'], cwd=repo_dir)
    if rc != 0 or not out:
        return None
    return out
