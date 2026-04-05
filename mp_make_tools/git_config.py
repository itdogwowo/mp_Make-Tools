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


@dataclass(frozen=True)
class NamedRepoSpec(RepoSpec):
    name: str = ''


@dataclass(frozen=True)
class GitConfig:
    micropython: RepoSpec | None = None
    esp_idf: RepoSpec | None = None
    repos: list[NamedRepoSpec] | None = None
    tags_limit: int = 30
    list_wrap: int = 3
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
    )


def _load_repos_list(data: dict) -> list[NamedRepoSpec] | None:
    node = data.get('repos')
    if not isinstance(node, list):
        return None

    out: list[NamedRepoSpec] = []
    for item in node:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()
        dir_ = item.get('dir')
        url = item.get('url')
        if not name or not dir_ or not url:
            continue
        out.append(
            NamedRepoSpec(
                name=name,
                dir=str(dir_),
                url=str(url),
                ref=item.get('ref'),
                recursive=bool(item.get('recursive') is True),
            )
        )
    return out or None


def _load_implicit_named_repos(data: dict) -> list[NamedRepoSpec] | None:
    reserved = {
        'micropython',
        'esp_idf',
        'repos',
        'tags_limit',
        'list_wrap',
        'write_detected_to',
        'update_detected_on_fetch',
    }

    out: list[NamedRepoSpec] = []
    for key, node in data.items():
        if key in reserved or not isinstance(node, dict):
            continue
        dir_ = node.get('dir')
        url = node.get('url')
        if not dir_ or not url:
            continue
        out.append(
            NamedRepoSpec(
                name=str(key),
                dir=str(dir_),
                url=str(url),
                ref=node.get('ref'),
                recursive=bool(node.get('recursive') is True),
            )
        )
    return out or None


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
    repos = _load_repos_list(data)
    if repos is None:
        implicit: list[NamedRepoSpec] = []
        if micropython is not None:
            implicit.append(
                NamedRepoSpec(
                    name='micropython',
                    dir=micropython.dir,
                    url=micropython.url,
                    ref=micropython.ref,
                    recursive=bool(micropython.recursive),
                )
            )
        if esp_idf is not None:
            implicit.append(
                NamedRepoSpec(
                    name='esp_idf',
                    dir=esp_idf.dir,
                    url=esp_idf.url,
                    ref=esp_idf.ref,
                    recursive=bool(esp_idf.recursive),
                )
            )
        implicit_extra = _load_implicit_named_repos(data)
        if implicit_extra:
            implicit.extend(implicit_extra)
        repos = implicit or None
    tags_limit = int(_deep_get(data, ['tags_limit'], 30) or 30)
    list_wrap = int(_deep_get(data, ['list_wrap'], 3) or 3)
    write_detected_to = _deep_get(data, ['write_detected_to'], 'config.json')
    update_detected_on_fetch = bool(_deep_get(data, ['update_detected_on_fetch'], False) is True)

    return (
        GitConfig(
            micropython=micropython,
            esp_idf=esp_idf,
            repos=repos,
            tags_limit=tags_limit,
            list_wrap=list_wrap,
            write_detected_to=write_detected_to,
            update_detected_on_fetch=update_detected_on_fetch,
        ),
        path,
    )
