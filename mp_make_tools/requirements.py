from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RequirementSet:
    name: str
    binaries: tuple[str, ...]
    apt: tuple[str, ...]
    brew: tuple[str, ...]
    notes: tuple[str, ...] = ()


COMMON = RequirementSet(
    name='common',
    binaries=('python3', 'make', 'git'),
    apt=(),
    brew=(),
    notes=(
        'Python >= 3.10 is required.',
    ),
)


ESP32 = RequirementSet(
    name='esp32',
    binaries=('cmake', 'ninja', 'python3', 'make', 'git'),
    apt=(
        'build-essential',
        'cmake',
        'ninja-build',
        'python3',
        'python3-venv',
        'libusb-1.0-0-dev',
    ),
    brew=(
        'cmake',
        'ninja',
        'python',
    ),
    notes=(
        'ESP-IDF is required for ESP32 builds (set IDF_PATH or use --esp-idf-dir).',
        'MicroPython recommended ESP-IDF: v5.5.1 (also supports v5.3, v5.4, v5.4.1, v5.4.2).',
    ),
)


RP2 = RequirementSet(
    name='rp2',
    binaries=('cmake', 'ninja', 'python3', 'make', 'arm-none-eabi-gcc', 'git'),
    apt=(
        'build-essential',
        'cmake',
        'ninja-build',
        'python3',
        'gcc-arm-none-eabi',
        'libnewlib-arm-none-eabi',
    ),
    brew=(
        'make',
        'cmake',
        'ninja',
        'python',
        'armmbed/formulae/arm-none-eabi-gcc',
    ),
)


STM32 = RequirementSet(
    name='stm32',
    binaries=('python3', 'make', 'ninja', 'arm-none-eabi-gcc', 'git'),
    apt=(
        'gcc-arm-none-eabi',
        'libnewlib-arm-none-eabi',
        'build-essential',
        'ninja-build',
        'python3',
    ),
    brew=(
        'make',
        'ninja',
        'python',
        'armmbed/formulae/arm-none-eabi-gcc',
    ),
)


UNIX = RequirementSet(
    name='unix',
    binaries=('python3', 'make', 'cmake', 'ninja', 'pkg-config', 'git'),
    apt=(
        'build-essential',
        'libffi-dev',
        'pkg-config',
        'cmake',
        'ninja-build',
        'gnome-desktop-testing',
        'libasound2-dev',
        'libpulse-dev',
        'libaudio-dev',
        'libjack-dev',
        'libsndio-dev',
        'libx11-dev',
        'libxext-dev',
        'libxrandr-dev',
        'libxcursor-dev',
        'libxfixes-dev',
        'libxi-dev',
        'libxss-dev',
        'libxkbcommon-dev',
        'libdrm-dev',
        'libgbm-dev',
        'libgl1-mesa-dev',
        'libgles2-mesa-dev',
        'libegl1-mesa-dev',
        'libdbus-1-dev',
        'libibus-1.0-dev',
        'libudev-dev',
        'fcitx-libs-dev',
        'libpipewire-0.3-dev',
        'libwayland-dev',
        'libdecor-0-dev',
    ),
    brew=(
        'libffi',
        'ninja',
        'make',
        'sdl2',
    ),
)


def requirements_for_target(target: str) -> RequirementSet:
    t = target.lower()
    if t in ('macos', 'raspberry_pi'):
        t = 'unix'
    if t == 'esp32':
        return ESP32
    if t == 'rp2':
        return RP2
    if t == 'stm32':
        return STM32
    if t == 'unix':
        return UNIX
    return COMMON
