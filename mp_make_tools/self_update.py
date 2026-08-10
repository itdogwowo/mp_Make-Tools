from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class SelfUpdateResult:
    updated: bool
    reason: str | None = None
    error: str | None = None


def _run_git(repo_dir, args, *, capture=True):
    if capture:
        proc = subprocess.run(
            ['git', *args],
            cwd=repo_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        return int(proc.returncode), (proc.stdout or '').strip()
    proc = subprocess.run(['git', *args], cwd=repo_dir)
    return int(proc.returncode), ''


def _repo_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _is_git_repo(repo_dir):
    return os.path.isdir(os.path.join(repo_dir, '.git'))


def _is_worktree_clean(repo_dir):
    rc, out = _run_git(repo_dir, ['status', '--porcelain'])
    return rc == 0 and not out


def _head_commit(repo_dir):
    rc, out = _run_git(repo_dir, ['rev-parse', 'HEAD'])
    return out if rc == 0 else None


def _current_branch(repo_dir):
    rc, out = _run_git(repo_dir, ['rev-parse', '--abbrev-ref', 'HEAD'])
    if rc != 0 or out == 'HEAD':
        return None
    return out


def _head_tags(repo_dir):
    rc, out = _run_git(repo_dir, ['tag', '--points-at', 'HEAD', '--sort=-creatordate'])
    if rc != 0 or not out:
        return []
    return [t.strip() for t in out.splitlines() if t.strip()]


def _upstream_branch(repo_dir, branch):
    rc, out = _run_git(repo_dir, ['rev-parse', '--abbrev-ref', f'{branch}@{{u}}'])
    return out if rc == 0 else None


def _fetch_origin(repo_dir, *, tags=False):
    args = ['fetch', '--prune']
    if tags:
        args.append('--tags')
    rc, _ = _run_git(repo_dir, args, capture=False)
    return rc == 0


def _remote_commit(repo_dir, remote_ref):
    rc, out = _run_git(repo_dir, ['rev-parse', remote_ref])
    return out if rc == 0 else None


def _tag_version_key(tag):
    m = re.match(r'^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?(?:[.-](.+))?$', tag)
    if not m:
        return (0, 0, 0, 0, tag)
    major = int(m.group(1))
    minor = int(m.group(2) or 0)
    patch = int(m.group(3) or 0)
    suffix = m.group(4) or ''
    has_suffix = bool(suffix)
    pre_release = bool(re.search(r'rc|alpha|beta|preview|dev|pre', suffix, re.I)) if has_suffix else False
    release_rank = 0 if (has_suffix and pre_release) else 1
    return (major, minor, patch, release_rank, suffix)


def _find_latest_series_tag(repo_dir, current_tag):
    rc, out = _run_git(repo_dir, ['tag', '--sort=-creatordate'])
    if rc != 0 or not out:
        return None
    current_key = _tag_version_key(current_tag)
    current_major = current_key[0]
    candidates = []
    for t in out.splitlines():
        t = t.strip()
        if not t or t == current_tag:
            continue
        k = _tag_version_key(t)
        if k[0] != current_major:
            continue
        if k > current_key:
            candidates.append((k, t))
    if not candidates:
        return None
    candidates.sort(key=lambda x: x[0])
    return candidates[-1][1]


def _pull_ff_only(repo_dir):
    rc, _ = _run_git(repo_dir, ['pull', '--ff-only'], capture=False)
    return rc == 0


def _checkout_tag(repo_dir, tag):
    rc, _ = _run_git(repo_dir, ['checkout', tag], capture=False)
    return rc == 0


def _is_dirty_blocking(repo_dir, *, strict=False):
    important = ['*.py', '*.json', '*.sh', 'make.py', 'tools/', 'mp_make_tools/']
    args = ['status', '--porcelain', '--'] + important
    rc, out = _run_git(repo_dir, args)
    if rc == 0 and out:
        return True
    if strict:
        return not _is_worktree_clean(repo_dir)
    return False


def try_self_update(*, enabled=True, argv=None, strict_clean=False):
    if not enabled:
        return SelfUpdateResult(updated=False, reason='self-update disabled by flag')

    env_skip = os.environ.get('MP_MAKE_TOOLS_NO_SELF_UPDATE', '').strip()
    if env_skip and env_skip not in ('0', 'false', 'no'):
        return SelfUpdateResult(updated=False, reason='skipped via MP_MAKE_TOOLS_NO_SELF_UPDATE')

    repo_dir = _repo_dir()
    if not _is_git_repo(repo_dir):
        return SelfUpdateResult(updated=False, reason='not a git repository')

    branch = _current_branch(repo_dir)
    head_tags = _head_tags(repo_dir)
    current_commit = _head_commit(repo_dir)

    if _is_dirty_blocking(repo_dir, strict=strict_clean):
        return SelfUpdateResult(updated=False, reason='local worktree is dirty; skipping self-update')

    updated = False
    action_performed = None

    if head_tags:
        current_tag = head_tags[0]
        if not _fetch_origin(repo_dir, tags=True):
            return SelfUpdateResult(updated=False, error='git fetch (tags) failed')
        latest_tag = _find_latest_series_tag(repo_dir, current_tag)
        if latest_tag:
            print(f'[self-update] Newer tag available: {current_tag} -> {latest_tag}')
            if _checkout_tag(repo_dir, latest_tag):
                updated = True
                action_performed = f'checkout tag {latest_tag}'
    elif branch is not None:
        upstream = _upstream_branch(repo_dir, branch)
        if upstream is None:
            return SelfUpdateResult(updated=False, reason=f'branch {branch} has no upstream tracking')
        if not _fetch_origin(repo_dir, tags=False):
            return SelfUpdateResult(updated=False, error='git fetch failed')
        remote_head = _remote_commit(repo_dir, upstream)
        if remote_head is None:
            return SelfUpdateResult(updated=False, error=f'cannot resolve upstream {upstream}')
        if remote_head != current_commit:
            rc, ahead = _run_git(repo_dir, ['rev-list', '--count', f'{upstream}..HEAD'])
            ahead_count = int(ahead) if rc == 0 and ahead.isdigit() else 0
            if ahead_count > 0:
                return SelfUpdateResult(updated=False, reason=f'local branch is ahead of {upstream} by {ahead_count} commit(s); skipping')
            print(f'[self-update] Branch {branch} behind {upstream}; running pull --ff-only')
            if _pull_ff_only(repo_dir):
                updated = True
                action_performed = f'pull --ff-only from {upstream}'
    else:
        return SelfUpdateResult(updated=False, reason='HEAD is detached (not on branch or tag); skipping')

    if not updated:
        return SelfUpdateResult(updated=False, reason='already up to date')

    new_commit = _head_commit(repo_dir)
    old_short = current_commit[:10] if current_commit else '?'
    new_short = new_commit[:10] if new_commit else '?'
    print(f'[self-update] Updated ({action_performed}): {old_short} -> {new_short}')
    print('[self-update] Re-executing with updated code...')

    if argv is None:
        argv = list(sys.argv)

    python = sys.executable
    os.execv(python, [python, *argv])
