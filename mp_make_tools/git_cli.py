from __future__ import annotations

import os
import sys
from argparse import ArgumentParser
from datetime import datetime

from .config_update import update_json_file
from .fetch import ensure_repo_ref, ensure_submodule_or_clone
from .git_config import load_git_config
from .git_tools import describe, head_commit, list_tags, tags_pointing_at_head, current_branch, list_recent_remote_branches
from .proc import run


def _default_project_dir() -> str:
    return os.path.abspath(os.getcwd())


def _resolve_path(project_dir: str, p: str) -> str:
    if os.path.isabs(p):
        return os.path.abspath(p)
    return os.path.abspath(os.path.join(project_dir, p))


def _write_detected(
    *,
    project_dir: str,
    out_path: str,
    micropython_dir: str | None,
    esp_idf_dir: str | None,
    tags_limit: int,
) -> str:
    ts = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
    updates: list[tuple[list[str], object]] = []
    updates.append((['detected', 'timestamp_utc'], ts))

    if micropython_dir and os.path.exists(micropython_dir):
        run(['git', '-c', 'fetch.recurseSubmodules=no', '-C', micropython_dir, 'fetch', '--tags'], cwd=project_dir, env=None)
        updates.append((['detected', 'micropython', 'dir'], micropython_dir))
        updates.append((['detected', 'micropython', 'head'], head_commit(micropython_dir)))
        updates.append((['detected', 'micropython', 'describe'], describe(micropython_dir)))
        updates.append((['detected', 'micropython', 'branch'], current_branch(micropython_dir)))
        updates.append((['detected', 'micropython', 'tags_at_head'], tags_pointing_at_head(micropython_dir)))
        updates.append((['detected', 'micropython', 'recent_tags'], list_tags(micropython_dir, limit=tags_limit)))
        updates.append((['detected', 'micropython', 'recent_remote_branches'], list_recent_remote_branches(micropython_dir, limit=tags_limit)))

    if esp_idf_dir and os.path.exists(esp_idf_dir):
        run(['git', '-c', 'fetch.recurseSubmodules=no', '-C', esp_idf_dir, 'fetch', '--tags'], cwd=project_dir, env=None)
        updates.append((['detected', 'esp_idf', 'dir'], esp_idf_dir))
        updates.append((['detected', 'esp_idf', 'head'], head_commit(esp_idf_dir)))
        updates.append((['detected', 'esp_idf', 'describe'], describe(esp_idf_dir)))
        updates.append((['detected', 'esp_idf', 'branch'], current_branch(esp_idf_dir)))
        updates.append((['detected', 'esp_idf', 'tags_at_head'], tags_pointing_at_head(esp_idf_dir)))
        updates.append((['detected', 'esp_idf', 'recent_tags'], list_tags(esp_idf_dir, limit=tags_limit)))
        updates.append((['detected', 'esp_idf', 'recent_remote_branches'], list_recent_remote_branches(esp_idf_dir, limit=tags_limit)))

    if not os.path.isabs(out_path):
        out_path = os.path.join(project_dir, out_path)
    return update_json_file(out_path, updates, list_wrap=3)


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

    micropython_dir: str | None = None
    esp_idf_dir: str | None = None

    if cfg.micropython:
        micropython_dir = _resolve_path(project_dir, cfg.micropython.dir)
        if should_fetch:
            if not os.path.exists(micropython_dir):
                ensure_submodule_or_clone(
                    project_dir=project_dir,
                    rel_path=os.path.relpath(micropython_dir, project_dir),
                    url=cfg.micropython.url,
                    ref=cfg.micropython.ref,
                    recursive=cfg.micropython.recursive,
                    depth=1,
                )
            ensure_repo_ref(micropython_dir, ref=cfg.micropython.ref, recursive=cfg.micropython.recursive)

    if cfg.esp_idf:
        esp_idf_dir = _resolve_path(project_dir, cfg.esp_idf.dir)
        if should_fetch:
            if not os.path.exists(esp_idf_dir):
                ensure_submodule_or_clone(
                    project_dir=project_dir,
                    rel_path=os.path.relpath(esp_idf_dir, project_dir),
                    url=cfg.esp_idf.url,
                    ref=cfg.esp_idf.ref,
                    recursive=cfg.esp_idf.recursive,
                    depth=1,
                )
            ensure_repo_ref(esp_idf_dir, ref=cfg.esp_idf.ref, recursive=cfg.esp_idf.recursive)

    should_write = bool(args.write_detected or (cfg.update_detected_on_fetch and should_fetch))
    if should_write:
        out_cfg = cfg.write_detected_to or 'config.json'
        path_written = _write_detected(
            project_dir=project_dir,
            out_path=out_cfg,
            micropython_dir=micropython_dir,
            esp_idf_dir=esp_idf_dir,
            tags_limit=tags_limit,
        )
        print('Updated config: ' + path_written)
        return 0

    if cfg_path:
        print('Git config: ' + cfg_path)
    if micropython_dir:
        print('MicroPython: ' + micropython_dir)
        print('  describe: ' + str(describe(micropython_dir)))
    if esp_idf_dir:
        print('ESP-IDF: ' + esp_idf_dir)
        print('  describe: ' + str(describe(esp_idf_dir)))
    return 0
