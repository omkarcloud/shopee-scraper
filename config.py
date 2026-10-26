"""Configuration for the Shopee Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT           port the API listens on (default 8000)
    SHOPEE_PROXY   proxy URL for every request, e.g. http://user:pass@host:port
                   (default: none — direct). Every endpoint answers home,
                   office and cloud-server connections directly, so you very
                   likely don't need this. Set it only if you start seeing
                   failures at high volume.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

SHOPEE_PROXY = os.environ.get("SHOPEE_PROXY") or None

# Seconds a market keeps using its fallback exit after a block. Only matters
# when shopee_fallback_proxy() returns a proxy; here it never does.
SHOPEE_BLOCK_COOLDOWN = 900


def shopee_proxy(country=None):
    """The proxy for one curl session on a market (None = direct)."""
    return os.environ.get("SHOPEE_PROXY") or None


def shopee_fallback_proxy(country=None):
    """A proxy to switch a market to after a block (None = no fallback)."""
    return None
