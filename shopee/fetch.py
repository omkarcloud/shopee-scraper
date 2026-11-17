"""Shopee transport: plain curl_cffi with browser-impersonated TLS, no
cookies, no browser, no account. Only the surfaces Shopee serves to a
logged-out visitor are used (research 2026-10-23/24): the anti-fraud gate
(error 90309999, "Login Required") in front of search_items, pdp/get_pc,
item ratings and shop item lists is NOT crossed — those are not fetched.

Egress: the pod's own IP first (config.shopee_proxy(country), knob
SHOPEE_EXIT) — every surface below answered 200 from the GKE pod's own
Google Cloud IP, two datacenter-proxy exits and two SG residential exits
(pod probe 2026-10-24, config's "--- Shopee ---" block). A block on
a market moves that market's sessions one fallback step down for
SHOPEE_BLOCK_COOLDOWN seconds: since 2026-11-11 first to the market's gateway
exit (config.SHOPEE_GATEWAY_EXITS, exit_gateway.py: a fresh gateway address
on nearly every request; "gateway:sg" for the Asian markets, "gateway:br" for br /
mx; the numbers are in config.py's block), and only when that is refused
too to a residential exit in the market's own country
(config.shopee_fallback_proxy). A call the gateway keeps failing makes its
LAST retry on the residential exit, for that call only. A retryable failure
drops the session, so the retry rides a fresh exit.

Language signals match the market (owner rule 2026-10-24): Accept-Language
is the market's own q-weighted list (refs.ACCEPT_LANGUAGE_OF, e.g.
th-TH,th;q=0.9,en-US;q=0.8,en;q=0.7 on shopee.co.th) and x-shopee-language
is "en" — the site's own English UI switch, which keeps category / label
names English where Shopee translates them.

Surfaces (all GET, all per market host; JSON unless noted):

  * PRODUCT PAGE  /product/<shop_id>/<item_id> — HTML whose
    <script type="text/mfe-initial-data"> blob carries the server-rendered
    product (title, description, images, variations, models, attributes,
    categories, brand, shop location, services). Shopee renders it at
    detail_level 1: price, stock, sold, rating, review count and the shop
    block are null in the copy (the live values come from the gated
    get_pc XHR). The blob is only rendered when the request carries
    x-requested-with: XMLHttpRequest (pod test 2026-10-24: without it the
    pod's own IP and any non-market exit get a 160 KB shell; with it every
    market answers the blob from the pod's own IP). An unknown id answers
    HTTP 200 with an EMPTY cachedMap (parsers.parse_product -> None).
  * SHOP PAGE     /shop/<shop_id> or /<username> — HTML whose mfe-initial-data
    blob (same PAGE_HEADERS trick as the product page) carries the shop
    record under the queryState query keyed ["shopInfo", <ref>, ...]: the
    very payload get_shop_base's `data` used to be (shopid, name, account,
    shop_rating, follower_count, item_count, response_*, ctime, ...). An
    unknown id or username answers HTTP 200 with the home shell: a blob
    WITHOUT a shopInfo query -> ShopeeNotFound. Pod test 2026-11-04: the
    page answered the record from the pod's own IP on all 9 markets, by id
    and by username. Every JSON shop-profile API is gated now: the web
    get_shop_detail since 2026-10-26, and since ~2026-11-01 get_shop_base
    with the Android-app identity too (HTTP 418 + error 90309999 — the
    same from the pod IP, a US datacenter exit and an SG residential exit,
    with and without the SPC_* cookies of a prior page load, with the web
    identity's af-ac-enc-dat / x-sz-sdk-version / sec-fetch headers, and
    for product/get_shop_info, get_shop_tab and rcmd_items as well), so
    egress and headers are not the variable — the page is.
  * SHOP CATS     /api/v4/shop/get_categories?shopid=&offset=&limit=
  * SHOP REVIEWS  /api/v4/seller_operation/get_shop_ratings_new?shopid=
                  &type=<1..5 stars>&limit=&offset=  (type=0 answers nothing)
  * SHOP VOUCHERS /api/v4/voucher_wallet/get_shop_vouchers_by_shopid?shopid=
  * CATEGORIES    /api/v4/pages/get_category_tree
  * AUTOCOMPLETE  /api/v4/search/search_hint?keyword=&search_type=0&version=1
  * TRENDING      /api/v4/search/search_suggestion
  * FLASH SALE    /api/v4/flash_sale/get_all_sessions and
                  /api/v4/flash_sale/flash_sale_get_items?promotionid=&limit=&offset=
  * HOME FEED     /api/v4/homepage/get_daily_discover?bundle=daily_discover_main
                  &limit=<=100&offset=0  (offset > 0 answers an empty page)
  * OFFICIAL      /api/v4/official_shop/get_shops?category=-1&limit=&offset=

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  ShopeeUpstreamError  transport failure / 5xx / unexpected payload — retryable
  ShopeeBlocked        403 / 418 / 429 / error 90309999 / verify page   — retryable (fresh exit)
  ShopeeBadRequest     upstream 400                                     — never retried
  ShopeeNotFound       unknown shop / username / product               — never retried

History: shop profile = web get_shop_detail until 2026-10-26, the app's
get_shop_base until ~2026-11-01, the shop page's blob since 2026-11-04.
"""
import fastjson
import os
import re
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import egress
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError
from shopee import refs
from scraper_utils import sessions as sessions_utils

IMPERSONATE = "chrome"
PAGE_TIMEOUT = 40      # product pages are 0.6-1 MB
JSON_TIMEOUT = 20

ANTI_FRAUD_ERROR = 90309999
_BLOB_RE = re.compile(r'<script type="text/mfe-initial-data"[^>]*>(.*?)</script>', re.S)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.S)

API_HEADERS = {
    "accept": "application/json",
    "x-api-source": "pc",
    "x-requested-with": "XMLHttpRequest",
    "x-shopee-language": "en",
}
# The x-* trio is what makes Shopee render the product / shop blob
# server-side (module docstring); accept stays a document accept.
PAGE_HEADERS = {
    "accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "x-api-source": "pc",
    "x-requested-with": "XMLHttpRequest",
    "x-shopee-language": "en",
}


class ShopeeUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unexpected payload — retryable."""


class ShopeeBlocked(ShopeeUpstreamError, Blocked):
    """403 / 418 / 429, the 90309999 anti-fraud reply or a verify page — retryable on a fresh exit."""


class ShopeeBadRequest(BadRequest):
    """Upstream 400 — never retried."""


class ShopeeNotFound(NotFound):
    """Shop / username / product does not exist — never retried."""


# ---- sessions: one per worker thread per market, one exit each ------------------
_local = threading.local()
_fallback_until = {}            # market -> epoch until which its sessions take a fallback exit
_fallback_step = {}             # market -> the fallback step that serves while its cooldown runs (1 = the first)
_fallback_lock = threading.Lock()


def _gateway_step(country, step):
    """True when the market's fallback step `step` is the gateway exit with
    another exit configured behind it."""
    exits = config.shopee_fallback_exits(country)
    return 0 < step < len(exits) and bool(config.gateway_exit(exits[step - 1]))


def _step(country):
    """The fallback step a session of the market built NOW rides: 0 = the
    configured exit (the pod's own IP), 1, 2 =
    config.shopee_fallback_proxy(country, step) while the market's cooldown
    runs; one step past the gateway for the last retry of a call (_retrying)."""
    with _fallback_lock:
        step = _fallback_step.get(country, 1) if _fallback_until.get(country, 0) > time.time() else 0
    if getattr(_local, "past_gateway", False) and _gateway_step(country, step):
        step += 1
    return step


def _proxy_for(country, step=None):
    forced = config.shopee_proxy(country)
    if forced:
        return forced
    step = _step(country) if step is None else step
    return config.shopee_fallback_proxy(country, step) if step else None


def _session(country):
    sessions = getattr(_local, "sessions", None)
    if sessions is None:
        sessions = _local.sessions = {}
    sess = sessions.get(country)
    step = _step(country)
    if sess is not None and getattr(sess, "_shopee_step", 0) != step:
        # 2026-11-11: a session follows its market's step. Before, a thread
        # that took the fallback exit during a cooldown stayed on it until
        # that exit failed.
        _drop_session(country)
        sess = None
    if sess is None:
        # None (the own IP), a proxy URL, or the gateway exit ("gateway:sg")
        sess = egress.new_session(_proxy_for(country, step), impersonate=IMPERSONATE)
        sess._shopee_step = step
        sessions[country] = sess
    return sess


def _drop_session(country):
    """Close the thread's session for a market so a poisoned keep-alive or a
    refused exit dies with it."""
    sessions = getattr(_local, "sessions", None) or {}
    sess = sessions.pop(country, None)
    sessions_utils.close_quietly(sess)


def _note_block(country):
    """The exit this thread's session of the market rides was refused: the
    market's sessions move one fallback step down for a cooldown (own IP ->
    its gateway exit -> residential; on the last step they stay there, each
    on a fresh exit). No-op when no fallback is configured."""
    exits = config.shopee_fallback_exits(country)
    if not exits:
        return
    sess = (getattr(_local, "sessions", None) or {}).get(country)
    own = getattr(sess, "_shopee_step", _step(country))
    if getattr(_local, "past_gateway", False) and own > (
            _fallback_step.get(country, 1) if _fallback_until.get(country, 0) > time.time() else 0):
        # the exit borrowed behind the gateway for this call's last retry
        # (_retrying) was refused: no verdict on the gateway, the market's step stays
        return
    step = min(own + 1, len(exits))
    with _fallback_lock:
        if time.time() >= _fallback_until.get(country, 0) or step > _fallback_step.get(country, 1):
            _fallback_step[country] = step
        _fallback_until[country] = time.time() + config.SHOPEE_BLOCK_COOLDOWN
        now = _fallback_step[country]
    if len(exits) > 1:      # how often each step is refused is the number to watch
        print(f"shopee: {country} exit refused, its sessions on fallback step {now} "
              f"({exits[now - 1]}) for {config.SHOPEE_BLOCK_COOLDOWN} s")


def _retrying(country, fn):
    """Run fn() under the shared retry policy (ShopeeUpstreamError only;
    NotFound / BadRequest surface immediately). A block moves the market
    one fallback step down for a cooldown; every retryable failure drops
    the session. While the market's sessions are on the gateway exit step
    the LAST retry of a call rides the next step (the residential exit),
    for that call only: a gateway failure then costs latency, not the call."""
    last = None
    _local.past_gateway = False
    try:
        for attempt in range(1, config.MAX_RETRIES + 1):
            try:
                return fn()
            except ShopeeBlocked as e:
                last = e
                _note_block(country)
                _drop_session(country)
            except ShopeeUpstreamError as e:
                last = e
                _drop_session(country)
            if attempt < config.MAX_RETRIES:
                _local.past_gateway = attempt + 1 == config.MAX_RETRIES     # read by _step() for the session built next
                time.sleep(config.RETRY_BACKOFF * attempt)
        raise last
    finally:
        _local.past_gateway = False     # _session() rebuilds on the market's own step for the next call


def _headers(country, base, referer=None):
    headers = dict(base)
    headers["accept-language"] = refs.ACCEPT_LANGUAGE_OF[country]
    headers["referer"] = referer or (refs.site(country) + "/")
    return headers


def _status_check(resp, label):
    status = resp.status_code
    if status == 404:
        raise ShopeeNotFound(f"{label} not found")
    if status == 400:
        raise ShopeeBadRequest(resp.text[:200])
    if status in (401, 403, 418, 429):
        raise ShopeeBlocked(f"HTTP {status} for {label}")
    if status != 200:
        raise ShopeeUpstreamError(f"HTTP {status} for {label}")


def _json_once(country, path, label, params=None, not_found_errors=(), base_headers=None):
    url = refs.site(country) + path
    try:
        resp = _session(country).get(url, params=params, headers=_headers(country, base_headers or API_HEADERS),
                                     timeout=JSON_TIMEOUT)
    except Exception as e:
        raise ShopeeUpstreamError(f"request failed: {type(e).__name__}: {e}")
    _status_check(resp, label)
    try:
        payload = resp.json()
    except Exception:
        text = resp.text or ""
        if "verify" in text[:2000].lower() or "<html" in text[:300].lower():
            raise ShopeeBlocked(f"challenge page where JSON was expected for {label}")
        raise ShopeeUpstreamError(f"non-JSON response for {label}: {text[:120]}")
    if not isinstance(payload, dict):
        raise ShopeeUpstreamError(f"unexpected payload shape for {label}")
    error = payload.get("error")
    if error == ANTI_FRAUD_ERROR or payload.get("redirect_to_error_page"):
        raise ShopeeBlocked(f"anti-fraud reply ({ANTI_FRAUD_ERROR}) for {label}")
    if error in not_found_errors:
        raise ShopeeNotFound(f"{label} not found")
    if error not in (None, 0, ""):
        raise ShopeeUpstreamError(f"upstream error {error} {payload.get('error_msg') or ''} for {label}".strip())
    return payload


def _json(country, path, label, params=None, not_found_errors=(), base_headers=None):
    return _retrying(country, lambda: _json_once(country, path, label, params, not_found_errors, base_headers))


# ---- product page ----------------------------------------------------------------

def _product_page_once(country, shop_id, item_id):
    label = f"product {shop_id}/{item_id}"
    url = refs.product_link(country, shop_id, item_id)
    try:
        resp = _session(country).get(url, headers=_headers(country, PAGE_HEADERS), timeout=PAGE_TIMEOUT)
    except Exception as e:
        raise ShopeeUpstreamError(f"request failed: {type(e).__name__}: {e}")
    _status_check(resp, label)
    text = resp.text or ""
    final = str(resp.url or "")
    if "/verify/" in final or "/buyer/login" in final:
        raise ShopeeBlocked(f"redirected to {final.split('?')[0]} for {label}")
    if not _BLOB_RE.search(text):
        # the bare shell: the exit is not getting the server-rendered copy
        raise ShopeeBlocked(f"product page served without its data blob for {label}")
    return text


def fetch_product_page(country, shop_id, item_id):
    """GET the product page HTML (with its mfe-initial-data blob)."""
    return _retrying(country, lambda: _product_page_once(country, shop_id, item_id))


def product_blob(html):
    """The parsed mfe-initial-data JSON of a product page, or None."""
    match = _BLOB_RE.search(html or "")
    if not match:
        return None
    try:
        return fastjson.loads(match.group(1))
    except ValueError:
        return None


def page_title(html):
    match = _TITLE_RE.search(html or "")
    return match.group(1).strip() if match else ""


# ---- shops ------------------------------------------------------------------------

SHOP_NOT_FOUND_ERRORS = (1000000, 2003013)   # service_err (unknown id / username) / invalid_username
RATINGS_NOT_FOUND_ERRORS = (10000,)          # get_shop_ratings_new for a non-existent shop
VOUCHERS_NOT_FOUND_ERRORS = (5300000,)       # get_shop_vouchers_by_shopid for a non-existent shop


def shop_payload(blob):
    """The shop record of a shop page's mfe-initial-data blob, wrapped as the
    {"error": 0, "data": {...}} payload parsers.parse_shop reads (it is the
    shape get_shop_base answered), or None when the blob has no shopInfo
    query (Shopee's home shell for an unknown shop). The page's tab_meta is
    mirrored into show_tab's live / membership flags so the parser's
    has_live_stream / has_membership keep their values."""
    queries = ((blob or {}).get("queryState") or {}).get("queries") or []
    for query in queries:
        key = query.get("queryKey")
        data = (query.get("state") or {}).get("data")
        if isinstance(key, list) and key and key[0] == "shopInfo" and isinstance(data, dict) and data.get("shopid"):
            tabs = data.get("tab_meta") if isinstance(data.get("tab_meta"), dict) else {}
            if tabs and "show_tab" not in data:
                live = tabs.get("live_tab") if isinstance(tabs.get("live_tab"), dict) else {}
                data["show_tab"] = {"show_live_tab": live.get("show_live_tab"),
                                    "membership_tab": tabs.get("membership_tab")}
            return {"error": 0, "error_msg": "", "data": data}
    return None


def _shop_page_once(country, shop_id, username):
    label = f"shop {shop_id or username}"
    url = refs.shop_link(country, shop_id) if shop_id else refs.shop_username_link(country, username)
    try:
        resp = _session(country).get(url, headers=_headers(country, PAGE_HEADERS), timeout=PAGE_TIMEOUT)
    except Exception as e:
        raise ShopeeUpstreamError(f"request failed: {type(e).__name__}: {e}")
    _status_check(resp, label)
    final = str(resp.url or "")
    if "/verify/" in final or "/buyer/login" in final:
        raise ShopeeBlocked(f"redirected to {final.split('?')[0]} for {label}")
    blob = product_blob(resp.text)
    if blob is None:
        raise ShopeeBlocked(f"shop page served without its data blob for {label}")
    payload = shop_payload(blob)
    if payload is None:
        raise ShopeeNotFound(f"{label} not found")
    return payload


def fetch_shop_profile(country, shop_id=None, username=None):
    """The shop profile from the shop page's server-rendered blob (module
    docstring, SHOP PAGE): get_shop_base-shaped so parsers.parse_shop reads
    it unchanged. Every JSON shop-profile API is behind the anti-fraud gate
    since ~2026-11-01 (measured 2026-11-04)."""
    return _retrying(country, lambda: _shop_page_once(country, shop_id, username))


def fetch_shop_categories(country, shop_id, offset=0, limit=50):
    return _json(country, "/api/v4/shop/get_categories", f"shop {shop_id} categories",
                 {"shopid": shop_id, "offset": offset, "limit": limit},
                 not_found_errors=SHOP_NOT_FOUND_ERRORS)


def fetch_shop_ratings(country, shop_id, stars, offset=0, limit=20):
    """Shop reviews filtered to one star value (1-5): the endpoint answers
    nothing for the unfiltered type=0."""
    return _json(country, "/api/v4/seller_operation/get_shop_ratings_new",
                 f"shop {shop_id} reviews", {"shopid": shop_id, "type": stars, "offset": offset, "limit": limit},
                 not_found_errors=RATINGS_NOT_FOUND_ERRORS)


def fetch_shop_vouchers(country, shop_id):
    return _json(country, "/api/v4/voucher_wallet/get_shop_vouchers_by_shopid",
                 f"shop {shop_id} vouchers", {"shopid": shop_id}, not_found_errors=VOUCHERS_NOT_FOUND_ERRORS)


def fetch_official_shops(country, offset=0, limit=20):
    return _json(country, "/api/v4/official_shop/get_shops", "official shops",
                 {"category": -1, "offset": offset, "limit": limit})


# ---- catalog ----------------------------------------------------------------------

def fetch_category_tree(country):
    return _json(country, "/api/v4/pages/get_category_tree", "category tree")


def fetch_search_hint(country, keyword):
    return _json(country, "/api/v4/search/search_hint", f"autocomplete {keyword!r}",
                 {"keyword": keyword, "search_type": 0, "version": 1})


def fetch_search_suggestion(country):
    return _json(country, "/api/v4/search/search_suggestion", "trending searches")


def fetch_flash_sessions(country):
    return _json(country, "/api/v4/flash_sale/get_all_sessions", "flash sale sessions")


def fetch_flash_items(country, promotion_id, offset=0, limit=50, category_id=None):
    params = {"promotionid": promotion_id, "offset": offset, "limit": limit,
              "need_personalize": "true", "sort_soldout": "true", "with_dp_items": "true"}
    if category_id is not None:
        params["categoryid"] = category_id
    return _json(country, "/api/v4/flash_sale/flash_sale_get_items", f"flash sale {promotion_id}", params)


def fetch_daily_discover(country, limit=100):
    return _json(country, "/api/v4/homepage/get_daily_discover", "home feed",
                 {"bundle": "daily_discover_main", "limit": limit, "offset": 0})
