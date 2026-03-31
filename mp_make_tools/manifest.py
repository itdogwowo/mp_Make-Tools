import os


def _norm(path: str) -> str:
    return os.path.abspath(path)


def include(path: str) -> str:
    return f"include('{_norm(path)}')"


def freeze_file(path: str) -> str:
    abs_path = _norm(path)
    directory, file_name = os.path.split(abs_path)
    return f"freeze('{directory}', '{file_name}')"


def freeze_dir(path: str, *, recursive: bool = False) -> str:
    abs_path = _norm(path)
    if recursive:
        return f"freeze('{abs_path}', recursive=True)"
    return f"freeze('{abs_path}')"


def write_manifest(
    out_path: str,
    *,
    includes: list[str] | None = None,
    freeze_files: list[str] | None = None,
    freeze_dirs: list[tuple[str, bool]] | None = None,
) -> None:
    includes = includes or []
    freeze_files = freeze_files or []
    freeze_dirs = freeze_dirs or []

    lines: list[str] = []
    for inc in includes:
        lines.append(include(inc))

    for file_path in freeze_files:
        lines.append(freeze_file(file_path))

    for dir_path, recursive in freeze_dirs:
        lines.append(freeze_dir(dir_path, recursive=recursive))

    os.makedirs(os.path.dirname(_norm(out_path)), exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + ('\n' if lines else ''))

