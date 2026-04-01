from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class MpConfig:
    micropython_dir: str | None = None
    micropython_url: str | None = None
    micropython_ref: str | None = None
    git_manage: str | None = None

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
    no_doctor: bool | None = None
    no_clean: bool | None = None
    no_idf_export: bool | None = None
    name: str | None = None
    esp32_partition_auto: bool | None = None
    esp32_flash_mb: int | None = None
    esp32_app_margin_kb: int | None = None


def _deep_get(dct: dict, keys: list[str], default=None):
    cur = dct
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _find_default_config_path(project_dir: str) -> str | None:
    tool_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    candidates = [
        os.path.join(project_dir, 'make_config.json'),
        os.path.join(project_dir, 'make_config.example.json'),
        os.path.join(project_dir, 'mp_make_tools.config.json'),
        os.path.join(project_dir, 'mp_make_tools.json'),
        os.path.join(project_dir, 'config.json'),
        os.path.join(project_dir, 'config.example.json'),
        os.path.join(tool_root, 'make_config.json'),
        os.path.join(tool_root, 'make_config.example.json'),
        os.path.join(tool_root, 'config.json'),
        os.path.join(tool_root, 'config.example.json'),
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def _ensure_default_make_config(project_dir: str) -> str | None:
    project_dir = os.path.abspath(project_dir)
    tool_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

    target = os.path.join(project_dir, 'make_config.json')
    if os.path.exists(target):
        return target

    src_candidates = [
        os.path.join(project_dir, 'make_config.example.json'),
        os.path.join(project_dir, 'config.example.json'),
        os.path.join(tool_root, 'make_config.example.json'),
        os.path.join(tool_root, 'config.example.json'),
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


def resolve_config_path(project_dir: str, config_path: str | None) -> str | None:
    project_dir = os.path.abspath(project_dir)
    if config_path:
        return os.path.abspath(config_path)

    found = _find_default_config_path(project_dir)
    if found:
        return found

    return _ensure_default_make_config(project_dir)


def load_config(project_dir: str, config_path: str | None) -> MpConfig:
    project_dir = os.path.abspath(project_dir)
    path = resolve_config_path(project_dir, config_path)
    if not path:
        return MpConfig()

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    return MpConfig(
        micropython_dir=_deep_get(data, ['micropython', 'dir']),
        micropython_url=_deep_get(data, ['micropython', 'url']),
        micropython_ref=_deep_get(data, ['micropython', 'ref']),
        git_manage=_deep_get(data, ['git_manage']),
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
        no_doctor=_deep_get(data, ['build', 'no_doctor']),
        no_clean=_deep_get(data, ['build', 'no_clean']),
        no_idf_export=_deep_get(data, ['esp_idf', 'no_export']),
        name=_deep_get(data, ['output', 'name']),
        esp32_partition_auto=_deep_get(data, ['esp32', 'partition', 'auto']),
        esp32_flash_mb=_deep_get(data, ['esp32', 'partition', 'flash_mb']),
        esp32_app_margin_kb=_deep_get(data, ['esp32', 'partition', 'app_margin_kb']),
    )
