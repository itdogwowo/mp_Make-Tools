from __future__ import annotations

import os
import subprocess

from .proc import run


def _read_text_if_exists(path: str) -> str:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        return ''


def _has_submodule(project_dir: str, rel_path: str) -> bool:
    gitmodules = _read_text_if_exists(os.path.join(project_dir, '.gitmodules'))
    return f'path = {rel_path}' in gitmodules


def ensure_submodule_or_clone(
    *,
    project_dir: str,
    rel_path: str,
    url: str,
    ref: str | None = None,
    recursive: bool = False,
    depth: int = 1,
) -> str:
    project_dir = os.path.abspath(project_dir)
    rel_path = rel_path.replace('\\', '/')
    dest = os.path.abspath(os.path.join(project_dir, rel_path))

    if os.path.exists(dest):
        return dest

    if _has_submodule(project_dir, rel_path):
        cmd = ['git', 'submodule', 'update', '--init', f'--depth={depth}']
        if recursive:
            cmd.append('--recursive')
        cmd.extend(['--', rel_path])
        rc = run(cmd, cwd=project_dir)
        if rc == 0 and os.path.exists(dest):
            if ref:
                run(['git', '-C', dest, 'fetch', '--tags', f'--depth={depth}'], cwd=project_dir)
                run(['git', '-C', dest, 'checkout', ref], cwd=project_dir)
                if recursive:
                    run(['git', '-C', dest, 'submodule', 'update', '--init', '--recursive'], cwd=project_dir)
            return dest

    os.makedirs(os.path.dirname(dest), exist_ok=True)
    cmd = ['git', 'clone', f'--depth={depth}']
    if ref:
        cmd.extend(['-b', ref])
    if recursive:
        cmd.append('--recursive')
    cmd.extend([url, dest])
    rc = run(cmd, cwd=project_dir)
    if rc != 0 or not os.path.exists(dest):
        raise RuntimeError(f'Failed to fetch repo into: {dest}')

    return dest


def ensure_repo_ref(dest: str, *, ref: str | None, recursive: bool) -> None:
    dest = os.path.abspath(dest)
    if not os.path.exists(dest):
        return

    def _ref_exists(r: str) -> bool:
        proc = subprocess.run(
            ['git', '-C', dest, 'rev-parse', '--verify', r],
            cwd=dest,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return int(proc.returncode) == 0

    if ref:
        if not _ref_exists(ref):
            run(['git', '-c', 'fetch.recurseSubmodules=no', '-C', dest, 'fetch', '--tags'], cwd=dest)
        if not _ref_exists(ref):
            run(['git', '-c', 'fetch.recurseSubmodules=no', '-C', dest, 'fetch', '--depth=1', 'origin', ref], cwd=dest)

        remote_branch_ref = None
        if not ref.startswith('refs/') and not ref.startswith('origin/'):
            candidate = f'refs/remotes/origin/{ref}'
            if _ref_exists(candidate):
                remote_branch_ref = f'origin/{ref}'
        elif ref.startswith('origin/'):
            candidate = f'refs/remotes/{ref}'
            if _ref_exists(candidate):
                remote_branch_ref = ref

        if remote_branch_ref is not None:
            local_branch = ref[len('origin/') :] if ref.startswith('origin/') else ref
            run(['git', '-C', dest, 'checkout', '-B', local_branch, remote_branch_ref], cwd=dest)
        elif _ref_exists(ref):
            run(['git', '-C', dest, 'checkout', ref], cwd=dest)
        else:
            print(f'WARN: ref not found in {dest}: {ref}')

    if recursive:
        run(['git', '-C', dest, 'submodule', 'update', '--init', '--recursive'], cwd=dest)
