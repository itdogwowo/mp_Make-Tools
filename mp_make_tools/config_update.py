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


def _dump_pretty_json(data: object, *, indent: int = 2, list_wrap: int = 3) -> str:
    def dumps_value(v: object, level: int) -> str:
        pad = ' ' * (indent * level)
        pad_in = ' ' * (indent * (level + 1))

        if isinstance(v, dict):
            if not v:
                return '{}'
            items: list[str] = []
            for k, vv in v.items():
                key_s = json.dumps(k, ensure_ascii=False)
                val_s = dumps_value(vv, level + 1)
                items.append(f'{pad_in}{key_s}: {val_s}')
            return '{\n' + ',\n'.join(items) + '\n' + pad + '}'

        if isinstance(v, list):
            if not v:
                return '[]'

            if all(isinstance(x, str) for x in v):
                parts: list[str] = []
                for i in range(0, len(v), max(1, int(list_wrap))):
                    chunk = v[i : i + max(1, int(list_wrap))]
                    line = ', '.join(json.dumps(x, ensure_ascii=False) for x in chunk)
                    parts.append(pad_in + line)
                return '[\n' + ',\n'.join(parts) + '\n' + pad + ']'

            items = [f'{pad_in}{dumps_value(x, level + 1)}' for x in v]
            return '[\n' + ',\n'.join(items) + '\n' + pad + ']'

        return json.dumps(v, ensure_ascii=False)

    return dumps_value(data, 0) + '\n'


def update_json_file(path: str, updates: list[tuple[list[str], object]], *, list_wrap: int = 3) -> str:
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
            f.write(_dump_pretty_json(data, indent=2, list_wrap=list_wrap))
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

    return path
