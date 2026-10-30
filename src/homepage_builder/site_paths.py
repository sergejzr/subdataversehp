"""Where the landing page is public, shared by renderjinja.py and landing.py.

Only the standard library, so that importing it can never break the university
pages: the landing code itself stays out of renderjinja.py on purpose.

The environment comes from build-homepage.sh (Ansible server_environment) as
DAPU_SERVER_ENVIRONMENT. Unset or unknown means prod, the safe side.
"""
from __future__ import annotations

import os

ENVIRONMENT_VARIABLE = "DAPU_SERVER_ENVIRONMENT"
ENVIRONMENTS = ("dev", "test", "prod")

# dev and test serve the landing at /at/ (they are never indexed, FS2).
# Prod serves it at /at/ since the go-live; False brings back the hidden preview.
PROD_LIVE = True
LIVE_PATH = "/at/"
PREVIEW_PATH = "/at/_vorschau/"
# hreflang and canonical are absolute on prod, the only indexed host.
# dev and test keep them root-relative.
PROD_ORIGIN = "https://datapublication.nrw"


def raw_environment() -> str:
    return os.environ.get(ENVIRONMENT_VARIABLE, "").strip().lower()


def environment() -> str:
    value = raw_environment()
    return value if value in ENVIRONMENTS else "prod"


def landing_base_path() -> str:
    return LIVE_PATH if environment() != "prod" or PROD_LIVE else PREVIEW_PATH


def link_origin() -> str:
    """Origin in front of hreflang and canonical URLs: absolute on prod, empty elsewhere."""
    return PROD_ORIGIN if environment() == "prod" else ""


def public_site_base() -> str | None:
    """Path the university pages link the legal pages under, None while the landing is a preview."""
    base = landing_base_path()
    return base if base == LIVE_PATH else None
