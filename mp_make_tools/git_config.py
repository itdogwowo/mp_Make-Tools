from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class RepoSpec:
    dir: str
    url: str
    ref: str | None = None
    recursive: bool = False
    chips: str | None = None
    no_export: bool | None = None


@dataclass(frozen=True)
class GitConfig:
    micropython: RepoSpec | None = None
    esp_idf: RepoSpec | None = None
    tags_limit: int = 30
    write_detected_to: str | None = 'config.json'
    update_detected_on_fetch: bool = False


def _deep_get(dct: dict, keys: list[str], default=None):
    cur = dct
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _find_default_git_config_path(project_dir: str) -> str | None:
    tool_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    candidates = [
        os.path.join(project_dir, 'mp_make_tools.git_config.json'),
        os.path.join(project_dir, 'mp_make_tools.git.json'),
        os.path.join(project_dir, 'git_config.json'),
        os.path.join(project_dir, 'git_config.example.json'),
        os.path.join(tool_root, 'git_config.json'),
        os.path.join(tool_root, 'git_config.example.json'),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _ensure_default_git_config(project_dir: str) -> str | None:
    project_dir = os.path.abspath(project_dir)
    tool_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

    target = os.path.join(project_dir, 'git_config.json')
    if os.path.exists(target):
        return target

    src_candidates = [
        os.path.join(project_dir, 'git_config.example.json'),
        os.path.join(tool_root, 'git_config.example.json'),
    ]

    src = None
    for p in src_candidates:
        if os.path.exists(p):
            src = p
            break
    if not src:
        return None

    shutil.copy2(src, target)
    return target


def resolve_git_config_path(project_dir: str, git_config_path: str | None) -> str | None:
    project_dir = os.path.abspath(project_dir)
    if git_config_path:
        p = os.path.abspath(git_config_path)
        if os.path.exists(p):
            return p
        tool_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        src = os.path.join(tool_root, 'git_config.example.json')
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if os.path.exists(src):
            shutil.copy2(src, p)
            return p
        return p

    found = _find_default_git_config_path(project_dir)
    if found:
        return found

    return _ensure_default_git_config(project_dir)


def _load_repo_spec(data: dict, key: str) -> RepoSpec | None:
    node = data.get(key)
    if not isinstance(node, dict):
        return None
    dir_ = node.get('dir')
    url = node.get('url')
    if not dir_ or not url:
        return None
    return RepoSpec(
        dir=str(dir_),
        url=str(url),
        ref=node.get('ref'),
        recursive=bool(node.get('recursive') is True),
        chips=node.get('chips'),
        no_export=(True if node.get('no_export') is True else (False if node.get('no_export') is False else None)),
    )


def load_git_config(project_dir: str, git_config_path: str | None) -> tuple[GitConfig, str | None]:
    project_dir = os.path.abspath(project_dir)
    path = resolve_git_config_path(project_dir, git_config_path)
    if not path:
        return GitConfig(), None

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        if not isinstance(data, dict):
            data = {}

    micropython = _load_repo_spec(data, 'micropython')
    esp_idf = _load_repo_spec(data, 'esp_idf')
    tags_limit = int(_deep_get(data, ['tags_limit'], 30) or 30)
    write_detected_to = _deep_get(data, ['write_detected_to'], 'config.json')
    update_detected_on_fetch = bool(_deep_get(data, ['update_detected_on_fetch'], False) is True)

    return (
        GitConfig(
            micropython=micropython,
            esp_idf=esp_idf,
            tags_limit=tags_limit,
            write_detected_to=write_detected_to,
            update_detected_on_fetch=update_detected_on_fetch,
        ),
        path,
    )
