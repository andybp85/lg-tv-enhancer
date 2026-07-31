"""Single source of truth for this project's version.

There is no packaging manifest to carry it: the project is not installed, it is
deployed by copying the tree onto the Pi. That also means the Pi has no git
checkout and so no way to answer "which build is running?" — which is exactly
what this string is for. Bump it per SemVer (see the Versioning section of the
README for what counts as the public surface).
"""

from __future__ import annotations

__version__ = "0.1.0"
