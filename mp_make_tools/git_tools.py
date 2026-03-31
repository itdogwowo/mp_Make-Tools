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

