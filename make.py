#!/usr/bin/env python3

import sys

if sys.version_info < (3, 10):
    print(f'ERROR: Python >= 3.10 is required (found {sys.version.split()[0]}).')
    raise SystemExit(1)

from mp_make_tools.cli import main


if __name__ == '__main__':
    raise SystemExit(main())
