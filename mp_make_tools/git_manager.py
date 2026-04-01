from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from .config_update import update_json_file
from .fetch import ensure_repo_ref, ensure_submodule_or_clone
from .git_config import GitConfig, RepoSpec, load_git_config
from .git_tools import (
    current_branch,
    describe,
    head_commit,
    list_recent_remote_branches,
    list_tags,
    tags_pointing_at_head,
)
from .proc import run


@dataclass(frozen=True)
class RepoDetected:
    name: str
    dir: str
    head: str | None
    describe: str | None
    branch: str | None
    tags_at_head: list[str]
    recent_tags: list[str]
    recent_remote_branches: list[str]


def _resolve_path(project_dir: str, p: str) -> str:
    if os.path.isabs(p):
        return os.path.abspath(p)
    return os.path.abspath(os.path.join(project_dir, p))


def _specs_from_git_config(cfg: GitConfig) -> list[tuple[str, RepoSpec]]:
    specs: list[tuple[str, RepoSpec]] = []
    if cfg.repos:
        for spec in cfg.repos:
            specs.append((spec.name, spec))
        return specs

    if cfg.micropython:
        specs.append(('micropython', cfg.micropython))
    if cfg.esp_idf:
        specs.append(('esp_idf', cfg.esp_idf))
    return specs


def _fetch_tags(repo_dir: str, *, cwd: str) -> None:
    run(['git', '-c', 'fetch.recurseSubmodules=no', '-C', repo_dir, 'fetch', '--tags'], cwd=cwd, env=None)


def _detect(repo_name: str, repo_dir: str, *, tags_limit: int, cwd: str) -> RepoDetected:
    _fetch_tags(repo_dir, cwd=cwd)
    return RepoDetected(
        name=repo_name,
        dir=repo_dir,
        head=head_commit(repo_dir),
        describe=describe(repo_dir),
        branch=current_branch(repo_dir),
        tags_at_head=tags_pointing_at_head(repo_dir),
        recent_tags=list_tags(repo_dir, limit=tags_limit),
        recent_remote_branches=list_recent_remote_branches(repo_dir, limit=tags_limit),
    )


def ensure_managed_repos(
    *,
    project_dir: str,
    git_config_path: str | None,
    allow_network: bool = True,
) -> tuple[GitConfig, str | None, dict[str, str], dict[str, RepoDetected]]:
    project_dir = os.path.abspath(project_dir)
    cfg, cfg_path = load_git_config(project_dir, git_config_path)

    repo_dirs: dict[str, str] = {}
    detected: dict[str, RepoDetected] = {}

    for repo_name, spec in _specs_from_git_config(cfg):
        repo_dir = _resolve_path(project_dir, spec.dir)
        repo_dirs[repo_name] = repo_dir

        if allow_network:
            if not os.path.exists(repo_dir):
                ensure_submodule_or_clone(
                    project_dir=project_dir,
                    rel_path=os.path.relpath(repo_dir, project_dir),
                    url=spec.url,
                    ref=spec.ref,
                    recursive=bool(spec.recursive),
                    depth=1,
                )

            ensure_repo_ref(repo_dir, ref=spec.ref, recursive=bool(spec.recursive))

        if os.path.exists(repo_dir):
            detected[repo_name] = _detect(repo_name, repo_dir, tags_limit=cfg.tags_limit, cwd=project_dir)

    if cfg.write_detected_to:
        ts = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        updates: list[tuple[list[str], object]] = []
        updates.append((['detected', 'timestamp_utc'], ts))

        for name, d in detected.items():
            updates.append((['detected', name, 'dir'], d.dir))
            updates.append((['detected', name, 'head'], d.head))
            updates.append((['detected', name, 'describe'], d.describe))
            updates.append((['detected', name, 'branch'], d.branch))
            updates.append((['detected', name, 'tags_at_head'], d.tags_at_head))
            updates.append((['detected', name, 'recent_tags'], d.recent_tags))
            updates.append((['detected', name, 'recent_remote_branches'], d.recent_remote_branches))

        out_path = cfg.write_detected_to
        if not os.path.isabs(out_path):
            out_path = os.path.join(project_dir, out_path)
        update_json_file(out_path, updates, list_wrap=cfg.list_wrap)

    return cfg, cfg_path, repo_dirs, detected
