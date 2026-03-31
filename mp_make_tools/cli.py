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


def _find_esp32_firmware_bin(port_dir: str) -> str | None:
    candidates: list[str] = []
    candidates.extend(glob.glob(os.path.join(port_dir, 'build*', 'firmware.bin')))
    candidates.extend(glob.glob(os.path.join(port_dir, 'build*', '**', 'firmware.bin'), recursive=True))
    uniq = list(dict.fromkeys(candidates))
    if not uniq:
        return None
    return max(uniq, key=lambda p: os.path.getmtime(p))


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
    from .fetch import ensure_repo_ref, ensure_submodule_or_clone
    from .git_tools import is_head_at_ref
    from .manifest import write_manifest
    from .proc import run, run_bash

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

    parser.add_argument('target', nargs=1)
    args, passthrough = parser.parse_known_args(argv)

    raw_target = args.target[0]
    target, implied_chips = _normalize_target_and_chips(raw_target)

    project_dir = os.path.abspath(args.project_dir or _default_project_dir())
    cfg = load_config(project_dir, args.config)
    strict = bool(args.strict_config or (cfg.strict is True))

    micropython_dir = os.path.abspath(args.micropython_dir or cfg.micropython_dir or _default_micropython_dir(project_dir))
    esp_idf_dir = os.path.abspath(args.esp_idf_dir or cfg.esp_idf_dir or _default_esp_idf_dir(project_dir))

    micropython_url = args.micropython_url or cfg.micropython_url or 'https://github.com/micropython/micropython'
    micropython_ref = args.micropython_ref or cfg.micropython_ref

    esp_idf_url = args.esp_idf_url or cfg.esp_idf_url or 'https://github.com/espressif/esp-idf'
    esp_idf_version = args.esp_idf_version or cfg.esp_idf_version or 'v5.5.1'
    esp_idf_chips = args.esp_idf_chips or cfg.esp_idf_chips or implied_chips or 'esp32'

    build_dir_name = args.build_dir or cfg.build_dir or 'build'
    build_dir = os.path.abspath(os.path.join(project_dir, build_dir_name))
    jobs = args.jobs if args.jobs is not None else (cfg.jobs or (os.cpu_count() or 1))
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

    if args.doctor:
        return doctor(target, install=args.install)

    should_fetch = bool(args.fetch or args.sync)
    if not should_fetch and not os.path.exists(micropython_dir):
        if _is_within_dir(micropython_dir, project_dir):
            should_fetch = True
        else:
            raise RuntimeError(f'MicroPython checkout not found at {micropython_dir}. Run with --fetch or set --micropython-dir.')
    if target.lower() == 'esp32' and not should_fetch and not os.path.exists(esp_idf_dir):
        if _is_within_dir(esp_idf_dir, project_dir):
            should_fetch = True
        else:
            raise RuntimeError(f'ESP-IDF checkout not found at {esp_idf_dir}. Run with --fetch or set --esp-idf-dir.')

    if should_fetch:
        if not os.path.exists(micropython_dir):
            micropython_dir = ensure_submodule_or_clone(
                project_dir=project_dir,
                rel_path=os.path.relpath(micropython_dir, project_dir),
                url=micropython_url,
                ref=micropython_ref,
                depth=1,
            )
        else:
            ensure_repo_ref(micropython_dir, ref=micropython_ref, recursive=False)

        if target.lower() == 'esp32':
            if not os.path.exists(esp_idf_dir):
                ensure_submodule_or_clone(
                    project_dir=project_dir,
                    rel_path=os.path.relpath(esp_idf_dir, project_dir),
                    url=esp_idf_url,
                    ref=esp_idf_version,
                    recursive=True,
                    depth=1,
                )
            else:
                ensure_repo_ref(esp_idf_dir, ref=esp_idf_version, recursive=True)

    if os.path.exists(micropython_dir) and os.path.exists(os.path.join(micropython_dir, '.gitmodules')):
        rc = run(['git', 'submodule', 'update', '--init', '--recursive'], cwd=micropython_dir, env=None)
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

    if not args.no_doctor:
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

    if is_esp32 and not args.no_idf_export and os.path.exists(export_sh) and shutil.which('bash') is None:
        raise RuntimeError('bash is required for ESP32 builds (to source ESP-IDF export.sh).')

    if is_esp32 and not args.no_idf_export and os.path.exists(esp_idf_dir) and os.path.exists(export_sh):
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
    if user_c_modules:
        make_args.append(f'USER_C_MODULES={os.path.abspath(user_c_modules)}')

    make_args.extend(passthrough)

    if (args.idf_install or args.idf_export) and shutil.which('bash') is None:
        raise RuntimeError('bash is required for --idf-install/--idf-export')

    if is_esp32 and os.path.exists(esp_idf_dir) and os.path.exists(os.path.join(esp_idf_dir, 'install.sh')) and args.idf_install:
        run_bash(f'cd {shlex.quote(esp_idf_dir)} && ./install.sh {shlex.quote(esp_idf_chips)}', cwd=project_dir, env=env)

    use_idf_export = is_esp32 and os.path.exists(export_sh) and (args.idf_export or (not args.no_idf_export))
    should_clean = not bool(args.no_clean)

    if should_clean:
        clean_cmd = make_base + make_args + ['clean']
        if use_idf_export:
            clean_cmd_s = ' '.join(shlex.quote(x) for x in clean_cmd)
            rc = run_bash(
                f'source {shlex.quote(export_sh)} >/dev/null 2>&1 && {clean_cmd_s}',
                cwd=project_dir,
                env=env,
            )
        else:
            rc = run(clean_cmd, cwd=project_dir, env=env)
        if rc != 0:
            return rc

    build_cmd = make_base + make_args
    if use_idf_export:
        build_cmd_s = ' '.join(shlex.quote(x) for x in build_cmd)
        rc = run_bash(
            f'source {shlex.quote(export_sh)} >/dev/null 2>&1 && {build_cmd_s}',
            cwd=project_dir,
            env=env,
        )
    else:
        rc = run(build_cmd, cwd=project_dir, env=env)

    if rc == 0 and is_esp32:
        src_bin = _find_esp32_firmware_bin(port_dir)
        if src_bin is None:
            print('WARN: build succeeded but firmware.bin was not found under the port build directory.')
        else:
            stem = _safe_output_stem(args.name or raw_target)
            dst_bin = _unique_path(os.path.join(build_dir, f'{stem}.bin'))
            shutil.copy2(src_bin, dst_bin)
            print('Output: ' + dst_bin)

    return rc
