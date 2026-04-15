from __future__ import annotations

import json
import os
import sys
from argparse import ArgumentParser
from datetime import datetime

from .config_update import update_json_file
from .fetch import ensure_repo_ref, ensure_submodule_or_clone
from .git_config import RepoSpec, load_git_config
from .git_tools import describe, head_commit, list_tags, tags_pointing_at_head, current_branch, list_recent_remote_branches
from .proc import run


def _default_project_dir() -> str:
    return os.path.abspath(os.getcwd())


def _resolve_path(project_dir: str, p: str) -> str:
    if os.path.isabs(p):
        return os.path.abspath(p)
    return os.path.abspath(os.path.join(project_dir, p))


def _fetch_tags(repo_dir: str, *, cwd: str) -> None:
    run(['git', '-c', 'fetch.recurseSubmodules=no', '-C', repo_dir, 'fetch', '--tags'], cwd=cwd, env=None)


def _detect_repo(repo_name: str, repo_dir: str, *, tags_limit: int, cwd: str) -> list[tuple[list[str], object]]:
    if not os.path.exists(repo_dir):
        return []
    _fetch_tags(repo_dir, cwd=cwd)
    return [
        (['detected', repo_name, 'dir'], repo_dir),
        (['detected', repo_name, 'head'], head_commit(repo_dir)),
        (['detected', repo_name, 'describe'], describe(repo_dir)),
        (['detected', repo_name, 'branch'], current_branch(repo_dir)),
        (['detected', repo_name, 'tags_at_head'], tags_pointing_at_head(repo_dir)),
        (['detected', repo_name, 'recent_tags'], list_tags(repo_dir, limit=tags_limit)),
        (['detected', repo_name, 'recent_remote_branches'], list_recent_remote_branches(repo_dir, limit=tags_limit)),
    ]


def _write_detected(
    *,
    project_dir: str,
    out_path: str,
    repos: list[tuple[str, str]],
    tags_limit: int,
    list_wrap: int,
) -> str:
    ts = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    updates: list[tuple[list[str], object]] = []
    updates.append((['detected', 'timestamp_utc'], ts))

    for repo_name, repo_dir in repos:
        updates.extend(_detect_repo(repo_name, repo_dir, tags_limit=tags_limit, cwd=project_dir))

    if not os.path.isabs(out_path):
        out_path = os.path.join(project_dir, out_path)
    return update_json_file(out_path, updates, list_wrap=list_wrap)


def _iter_managed_repos(cfg) -> list[tuple[str, RepoSpec]]:
    if cfg.repos:
        return [(spec.name, spec) for spec in cfg.repos if spec.enabled]
    out: list[tuple[str, RepoSpec]] = []
    if cfg.micropython:
        if cfg.micropython.enabled:
            out.append(('micropython', cfg.micropython))
    if cfg.esp_idf:
        if cfg.esp_idf.enabled:
            out.append(('esp_idf', cfg.esp_idf))
    return out


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = ArgumentParser(prefix_chars='-')
    parser.add_argument('--project-dir', dest='project_dir', default=None, action='store')
    parser.add_argument('--git-config', dest='git_config', default=None, action='store')
    parser.add_argument('--fetch', dest='fetch', default=False, action='store_true')
    parser.add_argument('--sync', dest='sync', default=False, action='store_true')
    parser.add_argument('--write-detected', dest='write_detected', default=False, action='store_true')
    parser.add_argument('--tags-limit', dest='tags_limit', default=None, type=int)

    args = parser.parse_args(argv)

    project_dir = os.path.abspath(args.project_dir or _default_project_dir())
    cfg, cfg_path = load_git_config(project_dir, args.git_config)

    tags_limit = int(args.tags_limit if args.tags_limit is not None else cfg.tags_limit)
    should_fetch = bool(args.fetch or args.sync)

    managed: list[tuple[str, str, RepoSpec]] = []
    oneshot_force_reset: list[tuple[str, str]] = []

    specs = _iter_managed_repos(cfg)
    specs.sort(key=lambda it: (0 if os.path.abspath(_resolve_path(project_dir, it[1].dir)) == project_dir else 1))

    for repo_name, spec in specs:
        repo_dir = _resolve_path(project_dir, spec.dir)
        managed.append((repo_name, repo_dir, spec))
        if should_fetch:
            if not os.path.exists(repo_dir):
                ensure_submodule_or_clone(
                    project_dir=project_dir,
                    rel_path=os.path.relpath(repo_dir, project_dir),
                    url=spec.url,
                    ref=spec.ref,
                    recursive=bool(spec.recursive),
                    depth=1,
                )
            ensure_repo_ref(
                repo_dir,
                ref=spec.ref,
                recursive=bool(spec.recursive),
                require_clean=cfg.require_clean,
                strict_ref=cfg.strict_ref,
                force_reset=bool(spec.force_reset),
            )
            if spec.force_reset:
                oneshot_force_reset.append((repo_name, spec.dir))

    if cfg_path and oneshot_force_reset:
        with open(cfg_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                data = {}
        repos = data.get('repos')
        if isinstance(repos, list):
            changed = False
            for item in repos:
                if not isinstance(item, dict):
                    continue
                name = str(item.get('name') or '').strip()
                dir_ = item.get('dir')
                if not isinstance(dir_, str):
                    continue
                for target_name, target_dir in oneshot_force_reset:
                    if name == target_name and dir_ == target_dir and item.get('force_reset') is True:
                        item['force_reset'] = False
                        changed = True
            if changed:
                update_json_file(cfg_path, [(['repos'], repos)], list_wrap=cfg.list_wrap)
        else:
            for target_name, _ in oneshot_force_reset:
                node = data.get(target_name)
                if isinstance(node, dict) and node.get('force_reset') is True:
                    update_json_file(cfg_path, [([target_name, 'force_reset'], False)], list_wrap=cfg.list_wrap)

    should_write = bool(args.write_detected or (cfg.update_detected_on_fetch and should_fetch))
    if should_write:
        out_cfg = cfg.write_detected_to or 'config.json'
        path_written = _write_detected(
            project_dir=project_dir,
            out_path=out_cfg,
            repos=[(name, repo_dir) for name, repo_dir, _ in managed],
            tags_limit=tags_limit,
            list_wrap=cfg.list_wrap,
        )
        print('Updated config: ' + path_written)
        return 0

    if cfg_path:
        print('Git config: ' + cfg_path)
    for repo_name, repo_dir, _ in managed:
        if os.path.exists(repo_dir):
            print(f'{repo_name}: ' + repo_dir)
            print('  describe: ' + str(describe(repo_dir)))
    return 0
