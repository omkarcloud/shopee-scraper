"""Reference resolvers, the market table and link builders for /shopee/*.

ONE param per input (tripadvisor QueryOrIdField convention, tofler/refs.py):

    product   "<shop_id>.<item_id>" / "<shop_id>/<item_id>" OR any Shopee
              product link (…/product/<shop_id>/<item_id>, …-i.<shop_id>.<item_id>,
              …/universal-link/product/<shop_id>/<item_id>)
    shop      a numeric shop id, a username (lorealparissg) OR any Shopee shop
              link (…/shop/<shop_id>, …/<username>)

A link's host names the market (shopee.sg -> "sg"), which then overrides the
`country` param. Resolvers raise ValueError with a user-facing message
(RefField turns it into a 400).

Markets (captured 2026-10-24): the nine Shopee sites whose home feed,
product page and shop surfaces all answered the probes. shopee.cl and
shopee.com.co exist but their feed errors (35500000) and were left out.
Prices on every market are integers in 1/100000 of the local currency
(parsers.money).
"""
import re
from collections import namedtuple
from urllib.parse import urlparse

DEFAULT_MARKET = "sg"

# country code -> site host
SITE_OF = {
    "sg": "shopee.sg", "my": "shopee.com.my", "th": "shopee.co.th", "vn": "shopee.vn",
    "ph": "shopee.ph", "id": "shopee.co.id", "tw": "shopee.tw", "br": "shopee.com.br",
    "mx": "shopee.com.mx",
}
MARKETS = tuple(SITE_OF)
MARKET_OF_HOST = {host: cc for cc, host in SITE_OF.items()}

CURRENCY_OF = {
    "sg": "SGD", "my": "MYR", "th": "THB", "vn": "VND", "ph": "PHP", "id": "IDR",
    "tw": "TWD", "br": "BRL", "mx": "MXN",
}

# The Accept-Language a browser in that market sends (q-weighted, local
# language first, English as the fallback the site's "English" UI needs).
# Owner rule 2026-10-24: the language signals match the exit country.
ACCEPT_LANGUAGE_OF = {
    "sg": "en-SG,en-GB;q=0.9,en-US;q=0.8,en;q=0.7",
    "my": "ms-MY,ms;q=0.9,en-MY;q=0.8,en;q=0.7",
    "th": "th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7",
    "vn": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "ph": "en-PH,en;q=0.9,fil;q=0.8",
    "id": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "tw": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "br": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "mx": "es-MX,es;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Image hashes are served from the market's susercontent CDN
# ("down-sg.img.susercontent.com/file/<hash>" in the pages' og:image).
IMAGE_HOST_OF = {cc: f"https://down-{cc}.img.susercontent.com/file/" for cc in MARKETS}

ProductRef = namedtuple("ProductRef", "shop_id item_id country")
ShopRef = namedtuple("ShopRef", "shop_id username country")

_PAIR_RE = re.compile(r"^(\d{1,12})[./](\d{1,15})$")
_LINK_PRODUCT_RES = (
    re.compile(r"/product/(\d{1,12})/(\d{1,15})(?:[/?#]|$)"),
    re.compile(r"-i\.(\d{1,12})\.(\d{1,15})(?:[/?#]|$)"),
)
_LINK_SHOP_ID_RE = re.compile(r"^/shop/(\d{1,12})(?:[/?#]|$)")
_USERNAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._]{1,48}$")
# first path segments that are pages, never a shop username
_RESERVED_PATHS = {
    "product", "shop", "search", "cart", "checkout", "user", "buyer", "mall", "m", "api", "verify",
    "universal-link", "flash_sale", "daily_discover", "top_products", "find_similar_products",
    "blog", "seller", "events3", "events", "digital-product", "food", "video", "live", "official-shop",
}


def site(country):
    return "https://" + SITE_OF[country]


def _parse_link(value):
    """(host, path) for an http(s) / protocol-relative link, else None."""
    value = value if not value.startswith("//") else "https:" + value
    if not value.lower().startswith(("http://", "https://")):
        return None
    parsed = urlparse(value)
    return (parsed.hostname or "").lower(), parsed.path or "/", value


def _market_of_host(host):
    """Market code for a Shopee host (shopee.sg, mall.shopee.sg, ...); raises
    for another site or an unsupported Shopee market."""
    labels = host.split(".")
    for i in range(len(labels)):
        candidate = ".".join(labels[i:])
        if candidate in MARKET_OF_HOST:
            return MARKET_OF_HOST[candidate]
    if "shopee" in labels:
        raise ValueError(f"Shopee market {host} is not supported; use one of: "
                         + ", ".join(SITE_OF.values()) + ".")
    raise ValueError("Must be a Shopee link.")


def resolve_product(value):
    """'<shop_id>.<item_id>', '<shop_id>/<item_id>' or a Shopee product link
    -> ProductRef(shop_id, item_id, country | None)."""
    value = (value or "").strip()
    match = _PAIR_RE.match(value)
    if match:
        return ProductRef(int(match.group(1)), int(match.group(2)), None)
    link = _parse_link(value)
    if link:
        host, path, url = link
        country = _market_of_host(host)
        for pattern in _LINK_PRODUCT_RES:
            match = pattern.search(url)
            if match:
                return ProductRef(int(match.group(1)), int(match.group(2)), country)
        raise ValueError("Must be a Shopee product link "
                         "(https://shopee.sg/product/<shop_id>/<item_id> or "
                         "https://shopee.sg/<name>-i.<shop_id>.<item_id>).")
    raise ValueError("Must be '<shop_id>.<item_id>' (e.g. 15235546.23326616342) "
                     "or a Shopee product link.")


def resolve_shop(value):
    """A numeric shop id, a username or a Shopee shop link
    -> ShopRef(shop_id | None, username | None, country | None)."""
    value = (value or "").strip()
    if value.isdigit():
        return ShopRef(int(value), None, None)
    link = _parse_link(value)
    if link:
        host, path, _ = link
        country = _market_of_host(host)
        match = _LINK_SHOP_ID_RE.match(path)
        if match:
            return ShopRef(int(match.group(1)), None, country)
        segments = [s for s in path.split("/") if s]
        if len(segments) == 1 and segments[0].lower() not in _RESERVED_PATHS \
                and _USERNAME_RE.match(segments[0]):
            return ShopRef(None, segments[0].lower(), country)
        raise ValueError("Must be a Shopee shop link "
                         "(https://shopee.sg/shop/<shop_id> or https://shopee.sg/<username>).")
    if _USERNAME_RE.match(value) and "/" not in value:
        return ShopRef(None, value.lower(), None)
    raise ValueError("Must be a Shopee shop id (15235546), a username (lorealparissg) "
                     "or a Shopee shop link.")


# ---- links -----------------------------------------------------------------------

def product_link(country, shop_id, item_id):
    return f"{site(country)}/product/{shop_id}/{item_id}"


def shop_link(country, shop_id):
    return f"{site(country)}/shop/{shop_id}"


def shop_username_link(country, username):
    return f"{site(country)}/{username}"


def search_link(country, keyword):
    from urllib.parse import quote
    return f"{site(country)}/search?keyword={quote(keyword)}"


def category_link(country, name, category_id):
    """The site's own category URL: the display name with separators
    collapsed to "-" (non-Latin names stay, percent-encoded like the site
    does) + "-cat.<id>"."""
    from urllib.parse import quote
    slug = re.sub(r"[\s/&,.'\"()\[\]+:;!?]+", "-", name or "").strip("-") or "cat"
    return f"{site(country)}/{quote(slug, safe='-')}-cat.{category_id}"


def image_link(country, value):
    """A susercontent image hash -> CDN URL (full URLs pass through)."""
    if not value:
        return None
    if str(value).startswith(("http://", "https://")):
        return value
    return IMAGE_HOST_OF.get(country, IMAGE_HOST_OF[DEFAULT_MARKET]) + str(value)
