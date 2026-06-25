"""Compatibility wrapper.

The application uses xml_parser.py to avoid collisions with modules named parser.
Existing imports from parser keep working through this file.
"""

from xml_parser import *  # noqa: F401,F403
