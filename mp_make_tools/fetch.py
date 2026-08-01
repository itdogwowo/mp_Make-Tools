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


def ensure_repo_ref(
    dest: str,
    *,
    ref: str | None,
    recursive: bool,
    require_clean: bool = False,
    strict_ref: bool = False,
    force_reset: bool = False,
) -> None:
    dest = os.path.abspath(dest)
    if not os.path.exists(dest):
        return

    def _clean_untracked() -> None:
        rc = run(['git', '-C', dest, 'clean', '-fd'], cwd=dest)
        if strict_ref and rc != 0:
            raise RuntimeError(f'Failed to git clean in: {dest}')

    if force_reset:
        rc = run(['git', '-C', dest, 'reset', '--hard'], cwd=dest)
        if strict_ref and rc != 0:
            raise RuntimeError(f'Failed to git reset --hard in: {dest}')
        _clean_untracked()

    if require_clean and not force_reset:
        proc = subprocess.run(
            ['git', '-C', dest, 'status', '--porcelain'],
            cwd=dest,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f'Failed to check git status in: {dest}')
        if (proc.stdout or '').strip():
            raise RuntimeError(f'Git worktree not clean: {dest}')

    def _ref_exists(r: str) -> bool:
        proc = subprocess.run(
            ['git', '-C', dest, 'rev-parse', '--verify', r],
            cwd=dest,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return int(proc.returncode) == 0

    # ══════════════════════════════════════════════════════════════
    # 指定 ref 就「每次執行都追該 ref 的最新」：
    #   - ref 是分支（main/master/...）→ 每次 fetch + checkout -B + reset --hard origin/<ref>
    #   - ref 是 tag / commit hash     → 固定點，每次 reset --hard 到該點
    #   - 本地未提交變更與未追蹤檔案 每次都被剷除（方便重新拉最新）
    # （不再只「當 ref 不存在才 fetch」——本地分支存在後也照常更新）
    # ══════════════════════════════════════════════════════════════
    if ref:
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
            # ── 分支：追遠端最新 ──
            local_branch = ref[len('origin/') :] if ref.startswith('origin/') else ref
            rc = run(['git', '-C', dest, 'checkout', '-B', local_branch, remote_branch_ref], cwd=dest)
            if strict_ref and rc != 0:
                raise RuntimeError(f'Failed to checkout branch ref {ref} in: {dest}')
            rc = run(['git', '-C', dest, 'reset', '--hard', remote_branch_ref], cwd=dest)
            if strict_ref and rc != 0:
                raise RuntimeError(f'Failed to reset to {remote_branch_ref} in: {dest}')
            _clean_untracked()
        elif _ref_exists(ref):
            # ── tag / commit：固定點，reset 到該點 ──
            rc = run(['git', '-C', dest, 'checkout', ref], cwd=dest)
            if strict_ref and rc != 0:
                raise RuntimeError(f'Failed to checkout ref {ref} in: {dest}')
            rc = run(['git', '-C', dest, 'reset', '--hard', ref], cwd=dest)
            if strict_ref and rc != 0:
                raise RuntimeError(f'Failed to reset to {ref} in: {dest}')
            _clean_untracked()
        else:
            if strict_ref:
                raise RuntimeError(f'Ref not found in {dest}: {ref}')
            print(f'WARN: ref not found in {dest}: {ref}')

    if recursive:
        rc = run(['git', '-C', dest, 'submodule', 'update', '--init', '--recursive'], cwd=dest)
        if strict_ref and rc != 0:
            raise RuntimeError(f'Failed to update submodules in: {dest}')
        if ref:
            # 有 ref 才同步 submodule 到最新（避免動到無 ref repo 的 submodule）
            rc = run(['git', '-C', dest, 'submodule', 'foreach', '--recursive', 'git reset --hard'], cwd=dest)
            if strict_ref and rc != 0:
                raise RuntimeError(f'Failed to reset submodules in: {dest}')
            rc = run(['git', '-C', dest, 'submodule', 'foreach', '--recursive', 'git clean -fd'], cwd=dest)
            if strict_ref and rc != 0:
                raise RuntimeError(f'Failed to clean submodules in: {dest}')
