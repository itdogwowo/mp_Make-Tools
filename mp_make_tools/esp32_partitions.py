from __future__ import annotations

import os


PARTITION_HEADER = '# Name,   Type, SubType, Offset,  Size, Flags\n'


def _align_up(value: int, align: int) -> int:
    return ((value + align - 1) // align) * align


def _align_down(value: int, align: int) -> int:
    return (value // align) * align


def write_factory_partitions_csv(
    out_csv: str,
    *,
    flash_mb: int,
    app_size: int,
    nvs_size: int = 0x6000,
    phy_init_size: int = 0x1000,
    first_offset: int = 0x9000,
    vfs_subtype: str = 'fat',
) -> None:
    if flash_mb <= 0:
        raise ValueError('flash_mb must be > 0')

    out_csv = os.path.abspath(out_csv)
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)

    app_size = _align_up(int(app_size), 0x1000)
    offset = first_offset

    parts: list[str] = []
    parts.append(f'nvs,data,nvs,0x{offset:X},0x{nvs_size:X}')
    offset += nvs_size

    parts.append(f'phy_init,data,phy,0x{offset:X},0x{phy_init_size:X}')
    offset += phy_init_size

    parts.append(f'factory,app,factory,0x{offset:X},0x{app_size:X}')
    offset += app_size

    total_size = _align_down(int(flash_mb) * (2**20), 0x1000)
    vfs_size = _align_down(total_size - offset, 0x1000)
    if vfs_size <= 0:
        raise RuntimeError('There is not enough flash to store the firmware.')

    parts.append(f'vfs,data,{vfs_subtype},0x{offset:X},0x{vfs_size:X}')
    offset += vfs_size

    if offset > total_size:
        raise RuntimeError('There is not enough flash to store the firmware.')

    with open(out_csv, 'w', encoding='utf-8') as f:
        f.write(PARTITION_HEADER)
        f.write('\n'.join(parts))
        f.write('\n')

