from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class MpConfig:
    micropython_dir: str | None = None
    micropython_url: str | None = None
    micropython_ref: str | None = None

    esp_idf_dir: str | None = None
    esp_idf_url: str | None = None
    esp_idf_version: str | None = None
    esp_idf_chips: str | None = None

    build_dir: str | None = None
    jobs: int | None = None
    user_c_modules: str | None = None
    exmod_root: str | None = None
    exmods: list[str] | None = None
    strict: bool | None = None


def _deep_get(dct: dict, keys: list[str], default=None):
    cur = dct
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _find_default_config_path(project_dir: str) -> str | None:
    candidates = [
        os.path.join(project_dir, 'mp_make_tools.config.json'),
        os.path.join(project_dir, 'mp_make_tools.json'),
        os.path.join(project_dir, 'config.json'),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def load_config(project_dir: str, config_path: str | None) -> MpConfig:
    project_dir = os.path.abspath(project_dir)
    path = os.path.abspath(config_path) if config_path else _find_default_config_path(project_dir)
    if not path:
        return MpConfig()

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return MpConfig(
        micropython_dir=_deep_get(data, ['micropython', 'dir']),
        micropython_url=_deep_get(data, ['micropython', 'url']),
        micropython_ref=_deep_get(data, ['micropython', 'ref']),
        esp_idf_dir=_deep_get(data, ['esp_idf', 'dir']),
        esp_idf_url=_deep_get(data, ['esp_idf', 'url']),
        esp_idf_version=_deep_get(data, ['esp_idf', 'version']),
        esp_idf_chips=_deep_get(data, ['esp_idf', 'chips']),
        build_dir=_deep_get(data, ['build', 'dir']),
        jobs=_deep_get(data, ['build', 'jobs']),
        user_c_modules=_deep_get(data, ['build', 'user_c_modules']),
        exmod_root=_deep_get(data, ['exmod', 'root']),
        exmods=_deep_get(data, ['exmod', 'list']),
        strict=_deep_get(data, ['build', 'strict']),
    )
