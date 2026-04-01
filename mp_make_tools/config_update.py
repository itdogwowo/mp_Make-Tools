from __future__ import annotations

import json
import os
import tempfile


def _set_path(dct: dict, keys: list[str], value) -> None:
    cur = dct
    for k in keys[:-1]:
        nxt = cur.get(k)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[k] = nxt
        cur = nxt
    cur[keys[-1]] = value


def update_json_file(path: str, updates: list[tuple[list[str], object]]) -> str:
    path = os.path.abspath(path)
    base_dir = os.path.dirname(path)
    os.makedirs(base_dir, exist_ok=True)

    data: dict
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if not isinstance(data, dict):
                data = {}
    except FileNotFoundError:
        data = {}

    for keys, value in updates:
        _set_path(data, keys, value)

    fd, tmp = tempfile.mkstemp(prefix='.tmp_mp_make_tools_', suffix='.json', dir=base_dir)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

    return path

