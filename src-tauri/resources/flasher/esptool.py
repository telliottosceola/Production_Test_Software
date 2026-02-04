#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2014-2022 Fredrik Ahlberg, Angus Gratton,
# Espressif Systems (Shanghai) CO LTD, other contributors as noted.
#
# SPDX-License-Identifier: GPL-2.0-or-later

# Wrapper script for esptool module

import os
import sys

# Add the directory containing this script to the Python path
# so it can find the esptool module
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from esptool import _main

if __name__ == "__main__":
    _main()
