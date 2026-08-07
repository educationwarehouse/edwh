"""
This file keeps track of the current package version.
"""

# SPDX-FileCopyrightText: 2023-present Remco Boerma <remco.b@educationwarehouse.nl>
#
# SPDX-License-Identifier: MIT
from importlib.metadata import version

__version__ = version(__package__)
