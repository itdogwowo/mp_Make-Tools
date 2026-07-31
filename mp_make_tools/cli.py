from __future__ import annotations

import glob
import os
import re
import shlex
import shutil
import sys
from datetime import datetime
from argparse import ArgumentParser


def _safe_output_stem(name: str) -> str:
    name = (name or '').strip()
    if not name:
        return 'firmware'
    return re.sub(r'[^A-Za-z0-9._-]+', '_', name)

def _default_esp32_output_name(passthrough: list[str], *, build_name: str | None) -> str | None:
    if build_name:
        bn = build_name.strip()
        if bn.startswith('build-'):
            rest = bn[len('build-'):].strip()
            if rest:
                if '-' in rest:
                    a, b = rest.split('-', 1)
                    a = a.strip()
                    b = b.strip()
                    if a and b:
                        return f'{a}_{b}'
                    if a:
                        return a
                return rest

    mv = _extract_make_vars(passthrough)
    board_variant = (mv.get('BOARD_VARIANT') or '').strip()
    board = (mv.get('BOARD') or '').strip()
    if not board:
        board_dir = (mv.get('BOARD_DIR') or '').strip()
        if board_dir:
            board = os.path.basename(os.path.normpath(board_dir)).strip()
    if not board:
        return None
    if board_variant:
        return f'{board}_{board_variant}'
    return board


def _find_esp32_firmware_bin(port_dir: str) -> str | None:
    candidates: list[str] = []
    candidates.extend(glob.glob(os.path.join(port_dir, 'build*', 'firmware.bin')))
    candidates.extend(glob.glob(os.path.join(port_dir, 'build*', '**', 'firmware.bin'), recursive=True))
    uniq = list(dict.fromkeys(candidates))
    if not uniq:
        return None
    return max(uniq, key=lambda p: os.path.getmtime(p))

def _find_esp32_micropython_bin(port_dir: str) -> str | None:
    candidates: list[str] = []
    candidates.extend(glob.glob(os.path.join(port_dir, 'build*', 'micropython.bin')))
    candidates.extend(glob.glob(os.path.join(port_dir, 'build*', '**', 'micropython.bin'), recursive=True))
    uniq = list(dict.fromkeys(candidates))
    if not uniq:
        return None
    return max(uniq, key=lambda p: os.path.getmtime(p))

def _extract_make_vars(args: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for a in args:
        if not a or '=' not in a:
            continue
        k, v = a.split('=', 1)
        k = k.strip()
        if not k:
            continue
        out[k] = v
    return out

def _apply_make_vars(passthrough: list[str], vars_from_cfg: dict[str, str] | None) -> list[str]:
    if not vars_from_cfg:
        return passthrough

    existing = _extract_make_vars(passthrough)
    additions: list[str] = []
    for k in sorted(vars_from_cfg.keys()):
        v = vars_from_cfg.get(k)
        if not isinstance(k, str) or not isinstance(v, str):
            continue
        kk = k.strip()
        vv = v.strip()
        if not kk or not vv:
            continue
        if kk in existing:
            continue
        additions.append(f'{kk}={vv}')
    return passthrough + additions

def _cmake_path(path: str) -> str:
    return os.path.abspath(path).replace('\\', '/')

def _append_sdkconfig_defaults(cmake_file: str, sdkconfig_file: str) -> None:
    cmake_file = os.path.abspath(cmake_file)
    sdkconfig_file = _cmake_path(sdkconfig_file)
    line = f'set(SDKCONFIG_DEFAULTS ${{SDKCONFIG_DEFAULTS}} \"{sdkconfig_file}\")'

    with open(cmake_file, 'r', encoding='utf-8') as f:
        data = f.read()

    if sdkconfig_file in data:
        return

    if not data.endswith('\n'):
        data += '\n'
    data += line + '\n'

    with open(cmake_file, 'w', encoding='utf-8') as f:
        f.write(data)

def _ensure_esp32_idf_component_dependencies(port_dir: str, deps: dict[str, str]) -> bool:
    manifest = os.path.join(port_dir, 'main', 'idf_component.yml')
    if not deps or not os.path.exists(manifest):
        return False

    with open(manifest, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()

    idx = None
    for i, line in enumerate(lines):
        if line.strip() == 'dependencies:':
            idx = i
            break
    if idx is None:
        return False

    existing: set[str] = set()
    for line in lines:
        m = re.match(r'^\s+([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)\s*:', line)
        if m:
            existing.add(m.group(1))

    to_add: list[tuple[str, str]] = []
    for k in sorted(deps.keys()):
        v = deps.get(k)
        if not isinstance(k, str) or not isinstance(v, str) or not k.strip() or not v.strip():
            continue
        if k in existing:
            continue
        to_add.append((k.strip(), v.strip()))

    if not to_add:
        return False

    insert_at = idx + 1
    new_lines = lines[:insert_at]
    for k, v in to_add:
        new_lines.append(f'  {k}: \"{v}\"')
    new_lines.extend(lines[insert_at:])

    with open(manifest, 'w', encoding='utf-8') as f:
        f.write('\n'.join(new_lines) + '\n')
    return True

def _write_esp32_sdkconfig_fragment(path: str, *, flash_mb: int, partitions_csv: str) -> None:
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)

    partitions_csv = partitions_csv.replace('\\', '/')
    lines: list[str] = []
    lines.append('CONFIG_PARTITION_TABLE_CUSTOM=y')
    lines.append(f'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME=\"{partitions_csv}\"')

    for mb in (2, 4, 8, 16, 32, 64, 128):
        val = 'y' if mb == flash_mb else 'n'
        lines.append(f'CONFIG_ESPTOOLPY_FLASHSIZE_{mb}MB={val}')

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

def _prepare_esp32_partition_auto(
    *,
    project_dir: str,
    port_dir: str,
    build_dir: str,
    passthrough: list[str],
    flash_mb: int,
) -> tuple[list[str], str, str]:
    mv = _extract_make_vars(passthrough)

    board_variant = mv.get('BOARD_VARIANT') or ''
    board_dir_arg = mv.get('BOARD_DIR')
    board = mv.get('BOARD') or 'ESP32_GENERIC'

    if board_dir_arg:
        board_dir_src = board_dir_arg
        if not os.path.isabs(board_dir_src):
            board_dir_src = os.path.abspath(os.path.join(port_dir, board_dir_src))
        board_name = os.path.basename(os.path.abspath(board_dir_src))
    else:
        board_name = board
        board_dir_src = os.path.abspath(os.path.join(port_dir, 'boards', board_name))

    if not os.path.isdir(board_dir_src):
        raise RuntimeError(f'ESP32 board directory not found: {board_dir_src}')

    tool_dir = os.path.abspath(os.path.join(build_dir, '.mp_make_tools', 'esp32'))
    temp_board_dir = os.path.join(tool_dir, 'boards', board_name)
    if os.path.exists(temp_board_dir):
        shutil.rmtree(temp_board_dir)
    shutil.copytree(board_dir_src, temp_board_dir)

    partitions_csv = os.path.join(tool_dir, 'partitions.csv')
    sdkconfig_fragment = os.path.join(tool_dir, 'sdkconfig.mp_make_tools')
    _write_esp32_sdkconfig_fragment(sdkconfig_fragment, flash_mb=flash_mb, partitions_csv=partitions_csv)

    for cmake in glob.glob(os.path.join(temp_board_dir, 'mpconfigboard.cmake')):
        _append_sdkconfig_defaults(cmake, sdkconfig_fragment)
    for cmake in glob.glob(os.path.join(temp_board_dir, 'mpconfigvariant*.cmake')):
        _append_sdkconfig_defaults(cmake, sdkconfig_fragment)

    new_passthrough: list[str] = []
    for a in passthrough:
        if a.startswith('BOARD=') or a.startswith('BOARD_DIR='):
            continue
        new_passthrough.append(a)
    new_passthrough.append(f'BOARD_DIR={temp_board_dir}')

    build_name = mv.get('BUILD')
    if not build_name:
        build_name = f'build-{board_name}'
        if board_variant:
            build_name += f'-{board_variant}'

    return new_passthrough, build_name, partitions_csv


def _unique_path(path: str) -> str:
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    ts = datetime.now().strftime('%Y_%m_%d_%H_%M_%S')
    candidate = f'{root}_{ts}{ext}'
    if not os.path.exists(candidate):
        return candidate
    i = 1
    while True:
        candidate = f'{root}_{ts}_{i}{ext}'
        if not os.path.exists(candidate):
            return candidate
        i += 1


def _default_project_dir() -> str:
    return os.path.abspath(os.getcwd())


def _default_micropython_dir(project_dir: str) -> str:
    return os.path.join(project_dir, 'lib', 'micropython')

def _default_esp_idf_dir(project_dir: str) -> str:
    return os.path.join(project_dir, 'lib', 'esp-idf')


def _port_dir(micropython_dir: str, target: str) -> str:
    if target.lower() in ('macos', 'raspberry_pi'):
        target = 'unix'
    return os.path.join(micropython_dir, 'ports', target)


def _port_manifest(micropython_dir: str, target: str) -> str:
    if target.lower() in ('macos', 'raspberry_pi'):
        target = 'unix'

    if target.lower() == 'teensy':
        return os.path.join(micropython_dir, 'ports', target, 'manifest.py')

    variants_manifest = os.path.join(micropython_dir, 'ports', target, 'variants', 'manifest.py')
    if os.path.exists(variants_manifest):
        return variants_manifest

    return os.path.join(micropython_dir, 'ports', target, 'boards', 'manifest.py')

def _resolve_exmods(project_dir: str, exmod_root: str, exmods: list[str]) -> list[str]:
    root = exmod_root.strip() if exmod_root else 'ext_mod'
    root_path = os.path.abspath(os.path.join(project_dir, root))
    resolved: list[str] = []
    for item in exmods:
        if not item:
            continue
        p = item.strip()
        if p.startswith('/') or p.startswith('\\'):
            p = p[1:]
            abs_p = os.path.abspath(os.path.join(root_path, p))
        elif os.path.isabs(p):
            abs_p = os.path.abspath(p)
        else:
            abs_p = os.path.abspath(os.path.join(root_path, p))
        if not os.path.exists(abs_p):
            raise RuntimeError(f'exmod not found: {abs_p}')
        resolved.append(abs_p)
    return resolved

def _user_c_modules_value(paths: list[str]) -> str:
    uniq: list[str] = []
    for p in paths:
        if p not in uniq:
            uniq.append(p)
    if len(uniq) == 1:
        return uniq[0]
    return ';'.join(uniq)

def _make_user_c_modules_arg(user_c_modules: str) -> str:
    v = os.path.abspath(user_c_modules)
    if ';' in v:
        return f'USER_C_MODULES="{v}"'
    return f'USER_C_MODULES={v}'


_USERMOD_PROTECT_TMPL = '''# Auto-generated by mp_Make-Tools. Do not edit.
#
# Brackets user C module includes with a build-directory snapshot/restore so
# that a module's configure-time `file(WRITE <path> "")` (e.g. lv_binding's
# placeholder write to ${CMAKE_BINARY_DIR}/lv_mp.c) cannot wipe an already-
# generated source across a reconfigure (such as partition-auto's 2nd pass).
#
# Protection is automatic and module-agnostic: any top-level build-dir file
# that was non-empty before the includes and is empty after is restored, so
# the build never links against a truncated generated source. Modules that
# never write files (e.g. one shipping pre-committed .c sources) see an empty
# before/after diff and are unaffected.
#
# NOTE: uses file(READ)/file(WRITE) rather than configure_file(... COPYONLY).
# configure_file would add the build-dir source into ninja's reconfigure
# dependency graph and cause a "multiple rules generate build.ninja" cycle;
# plain file I/O is invisible to the build system.

set(_MPMT_BK ${CMAKE_BINARY_DIR}/.mp_make_tools_usermod_backup)
file(REMOVE_RECURSE ${_MPMT_BK})
file(MAKE_DIRECTORY ${_MPMT_BK})

# --- snapshot non-empty top-level build-dir files (generated sources live here) ---
file(GLOB _MPMT_FILES ${CMAKE_BINARY_DIR}/*)
set(_MPMT_NAMES "")
foreach(_f ${_MPMT_FILES})
    if(NOT IS_DIRECTORY ${_f})
        file(SIZE ${_f} _sz)
        if(_sz GREATER 0)
            get_filename_component(_n ${_f} NAME)
            file(READ ${_f} _content)
            file(WRITE ${_MPMT_BK}/${_n} "${_content}")
            list(APPEND _MPMT_NAMES ${_n})
        endif()
    endif()
endforeach()

# --- include the real user C modules (paths resolved by mp_Make-Tools) ---
{{INCLUDES}}

# --- restore anything the modules truncated to empty ---
foreach(_n ${_MPMT_NAMES})
    set(_cur ${CMAKE_BINARY_DIR}/${_n})
    if(EXISTS ${_cur})
        file(SIZE ${_cur} _csz)
        if(NOT _csz GREATER 0)
            set(_bk ${_MPMT_BK}/${_n})
            file(SIZE ${_bk} _bsz)
            if(_bsz GREATER 0)
                file(READ ${_bk} _content)
                file(WRITE ${_cur} "${_content}")
                message(STATUS "mp_make_tools: restored truncated ${_n} (${_bsz} bytes)")
            endif()
        endif()
    endif()
endforeach()
'''


def _generate_usermod_protect_wrapper(build_dir: str, module_paths: list[str]) -> str | None:
    """Generate a single USER_C_MODULES wrapper cmake that includes every real
    module between a build-dir snapshot and a restore, so configure-time
    `file(WRITE ... "")` truncation of a generated file can't survive a
    reconfigure. Returns the wrapper path, or None if there are no modules."""
    abs_paths: list[str] = []
    for p in module_paths:
        p = (p or '').strip()
        if not p:
            continue
        abs_paths.append(os.path.abspath(p))
    if not abs_paths:
        return None

    tool_dir = os.path.join(build_dir, '.mp_make_tools')
    os.makedirs(tool_dir, exist_ok=True)
    wrapper = os.path.join(tool_dir, 'usermod_protected.cmake')

    includes = '\n'.join(f'include("{p}")' for p in abs_paths)
    content = _USERMOD_PROTECT_TMPL.replace('{{INCLUDES}}', includes)
    with open(wrapper, 'w', encoding='utf-8') as f:
        f.write(content)
    return wrapper


def _check_config_mismatch(name: str, cfg_value, cli_value, *, strict: bool) -> None:
    if cfg_value is None or cli_value is None:
        return
    if cfg_value == cli_value:
        return
    msg = f'Config mismatch: {name} config={cfg_value} cli={cli_value}'
    if strict:
        raise RuntimeError(msg)
    print('WARN: ' + msg)


def _normalize_target_and_chips(target: str) -> tuple[str, str | None]:
    t = target.lower()
    if t.startswith('esp32') and t != 'esp32':
        return 'esp32', t
    return target, None


def _is_within_dir(path: str, parent_dir: str) -> bool:
    parent_dir = os.path.abspath(parent_dir)
    path = os.path.abspath(path)
    try:
        return os.path.commonpath([path, parent_dir]) == parent_dir
    except ValueError:
        return False


def _ensure_mpy_cross(micropython_dir: str, *, jobs: int, cwd: str, env: dict[str, str]) -> None:
    from .proc import run as _run

    mpy_cross_dir = os.path.join(micropython_dir, 'mpy-cross')
    if not os.path.isdir(mpy_cross_dir):
        return
    rc_clean = _run(['make', '-C', mpy_cross_dir, 'clean'], cwd=cwd, env=env)
    if rc_clean != 0:
        raise RuntimeError('Failed to clean mpy-cross (host tool).')
    cmd = [
        'make',
        f'-j{jobs}',
        '-C',
        mpy_cross_dir,
    ]
    rc = _run(cmd, cwd=cwd, env=env)
    if rc != 0:
        raise RuntimeError('Failed to build mpy-cross (host tool).')


def _ensure_esp_idf_tools(esp_idf_dir: str, *, chips: str, cwd: str, env: dict[str, str]) -> None:
    from .proc import run_bash as _run_bash

    export_sh = os.path.join(esp_idf_dir, 'export.sh')
    if not os.path.exists(export_sh):
        return

    check_cmd = f'source {shlex.quote(export_sh)} >/dev/null 2>&1 && command -v idf.py >/dev/null 2>&1'
    if _run_bash(check_cmd, cwd=cwd, env=env) == 0:
        return

    install_sh = os.path.join(esp_idf_dir, 'install.sh')
    if not os.path.exists(install_sh):
        raise RuntimeError('idf.py not found after sourcing export.sh, and install.sh is missing.')

    rc = _run_bash(
        f'cd {shlex.quote(esp_idf_dir)} && ./install.sh {shlex.quote(chips)}',
        cwd=cwd,
        env=env,
    )
    if rc != 0:
        raise RuntimeError('ESP-IDF tools installation failed (install.sh).')
    if _run_bash(check_cmd, cwd=cwd, env=env) != 0:
        raise RuntimeError('idf.py is still not available after install.sh.')


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print(f'ERROR: Python >= 3.10 is required (found {sys.version.split()[0]}).')
        return 1

    from .config import load_config
    from .doctor import doctor
    from .git_tools import is_head_at_ref
    from .manifest import write_manifest
    from .proc import run, run_bash
    from .git_manager import ensure_managed_repos

    argv = list(sys.argv[1:] if argv is None else argv)

    parser = ArgumentParser(prefix_chars='-')
    parser.add_argument('--project-dir', dest='project_dir', default=None, action='store')
    parser.add_argument('--config', dest='config', default=None, action='store')
    parser.add_argument('--micropython-dir', dest='micropython_dir', default=None, action='store')
    parser.add_argument('--micropython-url', dest='micropython_url', default=None, action='store')
    parser.add_argument('--micropython-ref', dest='micropython_ref', default=None, action='store')
    parser.add_argument('--esp-idf-dir', dest='esp_idf_dir', default=None, action='store')
    parser.add_argument('--esp-idf-url', dest='esp_idf_url', default=None, action='store')
    parser.add_argument('--esp-idf-version', dest='esp_idf_version', default=None, action='store')
    parser.add_argument('--esp-idf-chips', dest='esp_idf_chips', default=None, action='store')
    parser.add_argument('--fetch', dest='fetch', default=False, action='store_true')
    parser.add_argument('--sync', dest='sync', default=False, action='store_true')
    parser.add_argument('--no-git-manage', dest='no_git_manage', default=False, action='store_true')
    esp32_part_group = parser.add_mutually_exclusive_group()
    esp32_part_group.add_argument('--esp32-partition-auto', dest='esp32_partition_auto', action='store_const', const=True, default=None)
    esp32_part_group.add_argument('--no-esp32-partition-auto', dest='esp32_partition_auto', action='store_const', const=False)
    parser.add_argument('--esp32-flash-mb', dest='esp32_flash_mb', default=None, type=int)
    parser.add_argument('--esp32-app-margin-kb', dest='esp32_app_margin_kb', default=None, type=int)
    parser.add_argument('--idf-install', dest='idf_install', default=False, action='store_true')
    parser.add_argument('--idf-export', dest='idf_export', default=False, action='store_true')
    parser.add_argument('--no-idf-export', dest='no_idf_export', default=False, action='store_true')
    parser.add_argument('--build-dir', dest='build_dir', default=None, action='store')
    parser.add_argument('--strict-config', dest='strict_config', default=False, action='store_true')

    parser.add_argument('--manifest-only', dest='manifest_only', default=False, action='store_true')
    parser.add_argument('--doctor', dest='doctor', default=False, action='store_true')
    parser.add_argument('--install', dest='install', default=False, action='store_true')
    parser.add_argument('--no-doctor', dest='no_doctor', default=False, action='store_true')
    parser.add_argument('--clean', dest='clean', default=False, action='store_true')
    parser.add_argument('--no-clean', dest='no_clean', default=False, action='store_true')
    parser.add_argument('--name', dest='name', default=None, action='store')

    parser.add_argument('--include-manifest', dest='include_manifests', action='append', default=[])
    parser.add_argument('--freeze-file', dest='freeze_files', action='append', default=[])
    parser.add_argument('--freeze-dir', dest='freeze_dirs', action='append', default=[])
    parser.add_argument('--freeze-dir-recursive', dest='freeze_dirs_recursive', action='append', default=[])

    parser.add_argument('--user-c-modules', dest='user_c_modules', default=None, action='store')
    parser.add_argument('--exmod-root', dest='exmod_root', default=None, action='store')
    parser.add_argument('--exmod', dest='exmods', action='append', default=[])
    parser.add_argument('--jobs', dest='jobs', default=None, type=int)

    parser.add_argument('target', nargs='?', default=None)
    args, passthrough = parser.parse_known_args(argv)

    project_dir = os.path.abspath(args.project_dir or _default_project_dir())
    cfg = load_config(project_dir, args.config)
    strict = bool(args.strict_config or (cfg.strict is True))

    raw_target = args.target or cfg.target
    if not raw_target:
        raise RuntimeError('Missing required target argument. Provide it on the command line, or set build.target in config.')
    target, implied_chips = _normalize_target_and_chips(raw_target)

    micropython_dir = os.path.abspath(args.micropython_dir or cfg.micropython_dir or _default_micropython_dir(project_dir))
    esp_idf_dir = os.path.abspath(args.esp_idf_dir or cfg.esp_idf_dir or _default_esp_idf_dir(project_dir))

    should_fetch = bool(args.fetch or args.sync)
    if cfg.git_manage and not args.no_git_manage:
        git_cfg, _, repo_dirs, _ = ensure_managed_repos(
            project_dir=project_dir,
            git_config_path=cfg.git_manage,
            allow_network=True,
        )
        micropython_dir = os.path.abspath(repo_dirs.get('micropython', micropython_dir))
        esp_idf_dir = os.path.abspath(repo_dirs.get('esp_idf', esp_idf_dir))

        git_micropython_ref = None
        if git_cfg.micropython and git_cfg.micropython.ref:
            git_micropython_ref = git_cfg.micropython.ref
        elif git_cfg.repos:
            for spec in git_cfg.repos:
                if spec.name == 'micropython' and spec.ref:
                    git_micropython_ref = spec.ref
                    break

        if args.micropython_ref is None and cfg.micropython_ref is None and git_micropython_ref:
            micropython_ref = git_micropython_ref
        else:
            micropython_ref = args.micropython_ref or cfg.micropython_ref

        git_esp_idf_ref = None
        if git_cfg.esp_idf and git_cfg.esp_idf.ref:
            git_esp_idf_ref = git_cfg.esp_idf.ref
        elif git_cfg.repos:
            for spec in git_cfg.repos:
                if spec.name == 'esp_idf' and spec.ref:
                    git_esp_idf_ref = spec.ref
                    break

        if args.esp_idf_version is None and cfg.esp_idf_version is None and git_esp_idf_ref:
            esp_idf_version = git_esp_idf_ref
        else:
            esp_idf_version = args.esp_idf_version or cfg.esp_idf_version or 'v5.5.1'
        should_fetch = False
    else:
        micropython_ref = args.micropython_ref or cfg.micropython_ref
        esp_idf_version = args.esp_idf_version or cfg.esp_idf_version or 'v5.5.1'

    esp_idf_chips = args.esp_idf_chips or cfg.esp_idf_chips or implied_chips or 'esp32'

    build_dir_name = args.build_dir or cfg.build_dir or 'build'
    build_dir = os.path.abspath(os.path.join(project_dir, build_dir_name))
    jobs = args.jobs if args.jobs is not None else (cfg.jobs or (os.cpu_count() or 1))

    if target.lower() == 'esp32' and cfg.esp32_make_vars:
        if not isinstance(cfg.esp32_make_vars, dict):
            raise RuntimeError('esp32.make.vars must be a JSON object mapping make-var -> value')
        passthrough = _apply_make_vars(passthrough, cfg.esp32_make_vars)

    if args.esp32_partition_auto is None:
        esp32_partition_auto = bool(cfg.esp32_partition_auto is True)
    else:
        esp32_partition_auto = bool(args.esp32_partition_auto)
    esp32_flash_mb = int(args.esp32_flash_mb or cfg.esp32_flash_mb or 4)
    if args.esp32_app_margin_kb is not None:
        esp32_app_margin_kb = int(args.esp32_app_margin_kb)
    elif cfg.esp32_app_margin_kb is not None:
        esp32_app_margin_kb = int(cfg.esp32_app_margin_kb)
    else:
        esp32_app_margin_kb = 4

    _check_config_mismatch('micropython.dir', cfg.micropython_dir, args.micropython_dir, strict=strict)
    _check_config_mismatch('micropython.url', cfg.micropython_url, args.micropython_url, strict=strict)
    _check_config_mismatch('micropython.ref', cfg.micropython_ref, args.micropython_ref, strict=strict)
    _check_config_mismatch('esp_idf.dir', cfg.esp_idf_dir, args.esp_idf_dir, strict=strict)
    _check_config_mismatch('esp_idf.url', cfg.esp_idf_url, args.esp_idf_url, strict=strict)
    _check_config_mismatch('esp_idf.version', cfg.esp_idf_version, args.esp_idf_version, strict=strict)
    _check_config_mismatch('esp_idf.chips', cfg.esp_idf_chips, args.esp_idf_chips, strict=strict)
    _check_config_mismatch('build.dir', cfg.build_dir, args.build_dir, strict=strict)
    _check_config_mismatch('build.jobs', cfg.jobs, args.jobs, strict=strict)
    _check_config_mismatch('build.user_c_modules', cfg.user_c_modules, args.user_c_modules, strict=strict)
    _check_config_mismatch('exmod.root', cfg.exmod_root, args.exmod_root, strict=strict)
    if cfg.exmods is not None and args.exmods:
        _check_config_mismatch('exmod.list', cfg.exmods, args.exmods, strict=strict)
    _check_config_mismatch('esp32.partition.auto', cfg.esp32_partition_auto, args.esp32_partition_auto, strict=strict)
    _check_config_mismatch('esp32.partition.flash_mb', cfg.esp32_flash_mb, args.esp32_flash_mb, strict=strict)
    _check_config_mismatch('esp32.partition.app_margin_kb', cfg.esp32_app_margin_kb, args.esp32_app_margin_kb, strict=strict)

    if args.doctor:
        return doctor(target, install=args.install)

    if not should_fetch and not os.path.exists(micropython_dir):
        if _is_within_dir(micropython_dir, project_dir):
            should_fetch = True
        else:
            toolish = os.path.exists(os.path.join(project_dir, 'mp_make_tools')) and os.path.exists(os.path.join(project_dir, 'make.py'))
            if toolish:
                raise RuntimeError(
                    f'MicroPython checkout not found at {micropython_dir}. '
                    f'It looks like project-dir is set to the mp_Make-Tools repo. '
                    f'Run make.py with --project-dir pointing to your firmware repo, or run git.py to update mp_Make-Tools itself.'
                )
            raise RuntimeError(f'MicroPython checkout not found at {micropython_dir}. Run with --fetch or set --micropython-dir.')
    if target.lower() == 'esp32' and not should_fetch and not os.path.exists(esp_idf_dir):
        if _is_within_dir(esp_idf_dir, project_dir):
            should_fetch = True
        else:
            raise RuntimeError(f'ESP-IDF checkout not found at {esp_idf_dir}. Run with --fetch or set --esp-idf-dir.')

    if should_fetch:
        if cfg.git_manage and not args.no_git_manage:
            ensure_managed_repos(project_dir=project_dir, git_config_path=cfg.git_manage, allow_network=True)
            should_fetch = False
            if not os.path.exists(micropython_dir):
                raise RuntimeError(
                    f'MicroPython checkout not found at {micropython_dir}. '
                    f'git_manage is enabled but git_config did not fetch it. '
                    f'Enable the micropython repo in your git_config (repos[].enabled=true), or disable git_manage and use --fetch.'
                )
            if target.lower() == 'esp32' and not os.path.exists(esp_idf_dir):
                raise RuntimeError(
                    f'ESP-IDF checkout not found at {esp_idf_dir}. '
                    f'git_manage is enabled but git_config did not fetch it. '
                    f'Enable the esp_idf repo in your git_config (repos[].enabled=true), or disable git_manage and use --fetch.'
                )

    if os.path.exists(micropython_dir) and os.path.exists(os.path.join(micropython_dir, '.gitmodules')):
        rc = run(['git', '-c', 'fetch.recurseSubmodules=no', 'submodule', 'update', '--init', '--recursive'], cwd=micropython_dir, env=None)
        if rc != 0:
            raise RuntimeError('Failed to initialise MicroPython submodules.')

    if micropython_ref and os.path.exists(micropython_dir) and not is_head_at_ref(micropython_dir, micropython_ref):
        msg = f'MicroPython version mismatch: expected {micropython_ref} at {micropython_dir}'
        if strict:
            raise RuntimeError(msg)
        print('WARN: ' + msg)

    if target.lower() == 'esp32' and os.path.exists(esp_idf_dir) and esp_idf_version and not is_head_at_ref(esp_idf_dir, esp_idf_version):
        msg = f'ESP-IDF version mismatch: expected {esp_idf_version} at {esp_idf_dir}'
        if strict:
            raise RuntimeError(msg)
        print('WARN: ' + msg)

    out_manifest = os.path.join(build_dir, 'manifest.py')
    includes: list[str] = []
    if os.path.exists(micropython_dir):
        port_manifest = _port_manifest(micropython_dir, target)
        if os.path.exists(port_manifest):
            includes.append(port_manifest)

    includes.extend([os.path.abspath(p) for p in args.include_manifests])

    freeze_dirs: list[tuple[str, bool]] = []
    freeze_dirs.extend([(p, False) for p in args.freeze_dirs])
    freeze_dirs.extend([(p, True) for p in args.freeze_dirs_recursive])

    write_manifest(
        out_manifest,
        includes=includes,
        freeze_files=[os.path.abspath(p) for p in args.freeze_files],
        freeze_dirs=[(os.path.abspath(p), rec) for p, rec in freeze_dirs],
    )

    exmod_root = args.exmod_root or cfg.exmod_root or 'ext_mod'
    exmods_cfg = cfg.exmods or []
    exmods_cli = args.exmods or []
    exmods = exmods_cli if exmods_cli else exmods_cfg
    exmods_resolved: list[str] = []
    if exmods:
        exmods_resolved = _resolve_exmods(project_dir, exmod_root, exmods)

    if args.manifest_only:
        print(out_manifest)
        return 0

    port_dir = _port_dir(micropython_dir, target)
    if not os.path.isdir(port_dir):
        if not os.path.exists(micropython_dir):
            raise RuntimeError(
                f'MicroPython checkout not found at {micropython_dir}. Run with --fetch or set --micropython-dir.'
            )
        raise RuntimeError(f'Unknown target or missing port directory: {port_dir}')

    if target.lower() == 'esp32' and cfg.esp32_idf_component_dependencies:
        if not isinstance(cfg.esp32_idf_component_dependencies, dict):
            raise RuntimeError('esp32.idf_component.dependencies must be a JSON object mapping component -> version')
        changed = _ensure_esp32_idf_component_dependencies(port_dir, cfg.esp32_idf_component_dependencies)
        if changed:
            print('INFO: Updated ports/esp32/main/idf_component.yml with extra dependencies from config.')

    if not (args.no_doctor or (cfg.no_doctor is True)):
        rc = doctor(target, install=bool(args.install))
        if rc != 0:
            return rc

    if sys.platform.startswith('win'):
        raise RuntimeError('Building firmware on Windows is not supported by this tool. Use --manifest-only.')

    env = os.environ.copy()
    is_esp32 = target.lower() == 'esp32'
    export_sh = os.path.join(esp_idf_dir, 'export.sh')

    if is_esp32 and os.path.exists(esp_idf_dir):
        env['IDF_PATH'] = esp_idf_dir

    no_idf_export = bool(args.no_idf_export or (cfg.no_idf_export is True))

    if is_esp32 and not no_idf_export and os.path.exists(export_sh) and shutil.which('bash') is None:
        raise RuntimeError('bash is required for ESP32 builds (to source ESP-IDF export.sh).')

    if is_esp32 and not no_idf_export and os.path.exists(esp_idf_dir) and os.path.exists(export_sh):
        _ensure_esp_idf_tools(esp_idf_dir, chips=esp_idf_chips, cwd=project_dir, env=env)

    _ensure_mpy_cross(micropython_dir, jobs=jobs, cwd=project_dir, env=env)

    make_base = [
        'make',
        f'-j{jobs}',
        '-C',
        port_dir,
    ]

    make_args: list[str] = []
    make_args.append(f'FROZEN_MANIFEST={out_manifest}')

    user_c_modules = args.user_c_modules or cfg.user_c_modules
    if not user_c_modules and exmods_resolved:
        user_c_modules = _user_c_modules_value(exmods_resolved)
    user_c_modules_arg: str | None = None
    if user_c_modules:
        mod_paths = [p for p in user_c_modules.split(';') if p.strip()]
        wrapped = _generate_usermod_protect_wrapper(build_dir, mod_paths)
        user_c_modules_arg = _make_user_c_modules_arg(wrapped or user_c_modules)
    if user_c_modules_arg:
        make_args.append(user_c_modules_arg)

    make_args.extend(passthrough)

    if (args.idf_install or args.idf_export) and shutil.which('bash') is None:
        raise RuntimeError('bash is required for --idf-install/--idf-export')

    if is_esp32 and os.path.exists(esp_idf_dir) and os.path.exists(os.path.join(esp_idf_dir, 'install.sh')) and args.idf_install:
        run_bash(f'cd {shlex.quote(esp_idf_dir)} && ./install.sh {shlex.quote(esp_idf_chips)}', cwd=project_dir, env=env)

    use_idf_export = is_esp32 and os.path.exists(export_sh) and (args.idf_export or (not no_idf_export))
    should_clean = not bool(args.no_clean or (cfg.no_clean is True))
    build_name_for_output: str | None = None

    def run_make(cmd: list[str]) -> int:
        if use_idf_export:
            cmd_s = ' '.join(shlex.quote(x) for x in cmd)
            return run_bash(
                f'source {shlex.quote(export_sh)} >/dev/null 2>&1 && {cmd_s}',
                cwd=project_dir,
                env=env,
            )
        return run(cmd, cwd=project_dir, env=env)

    if is_esp32 and esp32_partition_auto:
        from .esp32_partitions import write_factory_partitions_csv

        passthrough_esp32, build_name, partitions_csv = _prepare_esp32_partition_auto(
            project_dir=project_dir,
            port_dir=port_dir,
            build_dir=build_dir,
            passthrough=passthrough,
            flash_mb=esp32_flash_mb,
        )
        build_name_for_output = build_name

        make_args = [f'FROZEN_MANIFEST={out_manifest}']
        if user_c_modules_arg:
            make_args.append(user_c_modules_arg)
        make_args.extend(passthrough_esp32)

        initial_app_size = 0x100000
        write_factory_partitions_csv(partitions_csv, flash_mb=esp32_flash_mb, app_size=initial_app_size)

        if should_clean:
            rc_clean = run_make(make_base + make_args + ['clean'])
            if rc_clean != 0:
                return rc_clean

        rc1 = run_make(make_base + make_args)

        build_path = os.path.join(port_dir, build_name)
        mpy_bin = os.path.join(build_path, 'micropython.bin')
        if not os.path.exists(mpy_bin):
            mpy_bin = _find_esp32_micropython_bin(port_dir) or ''
        if not mpy_bin or not os.path.exists(mpy_bin):
            return rc1

        app_size = os.path.getsize(mpy_bin) + (esp32_app_margin_kb * 1024)
        write_factory_partitions_csv(partitions_csv, flash_mb=esp32_flash_mb, app_size=app_size)

        rc = run_make(make_base + make_args)
    else:
        if should_clean:
            rc_clean = run_make(make_base + make_args + ['clean'])
            if rc_clean != 0:
                return rc_clean

        rc = run_make(make_base + make_args)

    if rc == 0 and is_esp32:
        src_bin = _find_esp32_firmware_bin(port_dir)
        if src_bin is None:
            print('WARN: build succeeded but firmware.bin was not found under the port build directory.')
        else:
            default_name = _default_esp32_output_name(passthrough, build_name=build_name_for_output)
            stem = _safe_output_stem(args.name or cfg.name or default_name or raw_target)
            dst_bin = _unique_path(os.path.join(build_dir, f'{stem}.bin'))
            shutil.copy2(src_bin, dst_bin)
            print('Output: ' + dst_bin)

    return rc
