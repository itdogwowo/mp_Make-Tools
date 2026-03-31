from __future__ import annotations

import os
import platform
import shutil
import sys

from .proc import run
from .requirements import requirements_for_target


def _host_os() -> str:
    sys_plat = sys.platform
    if sys_plat.startswith('linux'):
        return 'linux'
    if sys_plat.startswith('darwin'):
        return 'macos'
    if sys_plat.startswith('win'):
        return 'windows'
    return platform.system().lower() or 'unknown'


def _missing_binaries(binaries: tuple[str, ...]) -> list[str]:
    missing: list[str] = []
    for b in binaries:
        if shutil.which(b) is None:
            missing.append(b)
    return missing


def _python_ok(min_major: int, min_minor: int) -> bool:
    vi = sys.version_info
    return (vi.major, vi.minor) >= (min_major, min_minor)


def _print_lines(lines: list[str]) -> None:
    for line in lines:
        print(line)


def doctor(target: str, *, install: bool) -> int:
    host = _host_os()
    req = requirements_for_target(target)

    lines: list[str] = []
    lines.append(f'Target: {req.name}')
    lines.append(f'Host: {host}')
    lines.append(f'Python: {sys.version.split()[0]}')

    if not _python_ok(3, 10):
        lines.append('ERROR: Python >= 3.10 is required.')

    missing = _missing_binaries(req.binaries)
    if missing:
        lines.append('Missing commands: ' + ', '.join(missing))
    else:
        lines.append('Missing commands: (none detected)')

    if req.notes:
        lines.append('Notes:')
        lines.extend([f'- {n}' for n in req.notes])

    if host == 'linux':
        if shutil.which('apt-get') is None:
            lines.append('Install: apt-get not found; use your distro package manager.')
        else:
            if req.apt:
                lines.append('Install (Ubuntu/Debian):')
                lines.append('sudo apt-get update')
                lines.append('sudo apt-get install -y ' + ' '.join(req.apt))
                if install:
                    if os.geteuid() != 0:
                        lines.append('ERROR: install requested but not running as root; re-run with sudo.')
                    else:
                        rc1 = run(['apt-get', 'update'])
                        rc2 = run(['apt-get', 'install', '-y', *req.apt])
                        return 0 if (rc1 == 0 and rc2 == 0) else 1

    elif host == 'macos':
        if shutil.which('xcode-select') is not None:
            rc = run(['xcode-select', '-p'])
            if rc != 0:
                lines.append('Install (macOS): xcode-select --install')
        else:
            lines.append('Install (macOS): xcode-select --install')

        if shutil.which('brew') is None:
            lines.append('Install: Homebrew not found; install brew first.')
        else:
            if req.brew:
                lines.append('Install (macOS, brew):')
                lines.append('brew install ' + ' '.join(req.brew))
                if install:
                    return run(['brew', 'install', *req.brew])

    elif host == 'windows':
        lines.append('Windows: compile is not supported by this tool (use --manifest-only).')
        lines.append('Install: automatic install is not provided on Windows.')
        if req.name == 'esp32':
            lines.append('Tip: use WSL for ESP32 builds, then follow the Linux ESP-IDF instructions.')
    else:
        lines.append('Install: unsupported host OS; please install required tools manually.')

    if req.name == 'esp32' and host in ('linux', 'macos'):
        lines.append('ESP-IDF quick setup:')
        lines.append('- Use --fetch to download esp-idf, then --idf-install, and --idf-export when building.')

    _print_lines(lines)
    return 0 if _python_ok(3, 10) else 1
