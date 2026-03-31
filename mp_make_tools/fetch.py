from __future__ import annotations

import os

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

    if ref:
        run(['git', '-C', dest, 'fetch', '--tags'], cwd=dest)
        run(['git', '-C', dest, 'checkout', ref], cwd=dest)

    if recursive:
        run(['git', '-C', dest, 'submodule', 'update', '--init', '--recursive'], cwd=dest)
