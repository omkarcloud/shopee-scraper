"""The /shopee/* endpoint functions (route_glue's route_table calls them
with the schema's loaded kwargs: `country` is always a market code, the
ref params are canonical strings — shopee/schemas.py).

Caching (cache.cached_call, keyed on the validated params):
  * shopee.shop        the parsed shop record + vouchers, per (country, shop);
                       products/details slices it for its `shop` block, so a
                       product and its shop cost one shop fetch between them
  * shopee.product     the parsed product record
  * the list endpoints cache their own page
Shops are cached under their resolved numeric id: a username is resolved
through the same record (get_shop_detail accepts either), so a shop reached
by username and by id share one row after the first lookup.
"""
from cache import cached_call
from shopee import cache_config as ttl
from shopee import parsers
from shopee import refs
from shopee.fetch import (ShopeeNotFound, fetch_category_tree, fetch_daily_discover, fetch_flash_items,
                          fetch_flash_sessions, fetch_official_shops, fetch_product_page, fetch_search_hint,
                          fetch_search_suggestion, fetch_shop_base, fetch_shop_categories,
                          fetch_shop_ratings, fetch_shop_vouchers, product_blob)
from shopee.schemas import (FLASH_SALE_PER_PAGE, OFFICIAL_SHOPS_PER_PAGE, REVIEWS_PER_PAGE,
                            SHOP_CATEGORIES_PER_PAGE)

FEED_LIMIT = 100   # the most the feed answers in one call (offset > 0 is empty)


def _pagination(page, per_page, total_count=None, has_next=None):
    block = {"page": page, "items_per_page": per_page}
    if total_count is not None:
        block["total_count"] = total_count
        block["total_pages"] = max(-(-total_count // per_page), 1) if total_count else 0
    else:
        block.update({"has_next": bool(has_next), "total_pages": None, "total_count": None})
    return block


# ---- shops -------------------------------------------------------------------------

def _shop_record(country, shop):
    """Parsed shop + vouchers for a canonical shop ref (digits = id, else username)."""
    if shop.isdigit():
        payload = fetch_shop_base(country, shop_id=int(shop))
    else:
        payload = fetch_shop_base(country, username=shop)
    record = parsers.parse_shop(payload, country)
    if not record.get("id"):
        raise ShopeeNotFound(f"shop {shop} not found")
    record["vouchers"] = parsers.parse_vouchers(fetch_shop_vouchers(country, record["id"]))
    return record


def _shop(country, shop):
    return cached_call("shopee.shop", {"country": country, "shop": shop}, _shop_record, ttl.SHOP_CACHE)


def _shop_id(country, shop):
    """The numeric id behind a canonical shop ref, through the cached shop
    record: an unknown id is a 404 here rather than an empty category list
    (Shopee answers get_categories for a non-existent shop with total 0)."""
    return _shop(country, shop)["id"]


def shop_details(country, shop):
    """Profile, rating breakdown, counts, activity stamps and the shop's
    current vouchers."""
    return _shop(country, shop)


def _shop_categories(country, shop, page):
    shop_id = _shop_id(country, shop)
    payload = fetch_shop_categories(country, shop_id, offset=(page - 1) * SHOP_CATEGORIES_PER_PAGE,
                                    limit=SHOP_CATEGORIES_PER_PAGE)
    rows, total, has_more = parsers.parse_shop_categories(payload, country, shop_id)
    return {
        "shop": {"id": shop_id, "link": refs.shop_link(country, shop_id)},
        "country": country,
        "results": rows,
        "pagination": _pagination(page, SHOP_CATEGORIES_PER_PAGE, total_count=total) if total is not None
        else _pagination(page, SHOP_CATEGORIES_PER_PAGE, has_next=has_more),
    }


def shop_categories(**data):
    return cached_call("shopee.shop_categories", data, _shop_categories, ttl.SHOP_CATEGORIES_CACHE)


def _shop_reviews(country, shop, rating, page):
    shop_id = _shop_id(country, shop)
    payload = fetch_shop_ratings(country, shop_id, rating, offset=(page - 1) * REVIEWS_PER_PAGE,
                                 limit=REVIEWS_PER_PAGE)
    rows = parsers.parse_shop_reviews(payload, country)
    # Shopee publishes no per-star total: `has_next` drives the next link.
    return {
        "shop": {"id": shop_id, "link": refs.shop_link(country, shop_id)},
        "country": country,
        "rating": rating,
        "results": rows,
        "pagination": _pagination(page, REVIEWS_PER_PAGE, has_next=len(rows) >= REVIEWS_PER_PAGE),
    }


def shop_reviews(**data):
    return cached_call("shopee.shop_reviews", data, _shop_reviews, ttl.SHOP_REVIEWS_CACHE)


def _official_shops(country, page):
    payload = fetch_official_shops(country, offset=(page - 1) * OFFICIAL_SHOPS_PER_PAGE,
                                   limit=OFFICIAL_SHOPS_PER_PAGE)
    rows, total = parsers.parse_official_shops(payload, country)
    return {"country": country, "results": rows,
            "pagination": _pagination(page, OFFICIAL_SHOPS_PER_PAGE, total_count=total if total is not None else None,
                                      has_next=len(rows) >= OFFICIAL_SHOPS_PER_PAGE)}


def shops_official(**data):
    return cached_call("shopee.shops_official", data, _official_shops, ttl.OFFICIAL_SHOPS_CACHE)


# ---- products ----------------------------------------------------------------------

def _product_record(country, product):
    shop_id, item_id = (int(x) for x in product.split("."))
    html = fetch_product_page(country, shop_id, item_id)
    record = parsers.parse_product(html, product_blob(html), country)
    if record is None:
        raise ShopeeNotFound(f"product {shop_id}/{item_id} not found on {refs.SITE_OF[country]}")
    return record


def product_details(country, product):
    """The server-rendered product copy (title, description, images,
    variations, models, attributes, categories, services, shipping facts)
    plus the shop's profile. Price, stock, sold count, rating and review
    count are null: Shopee only serves them to logged-in sessions."""
    record = cached_call("shopee.product", {"country": country, "product": product}, _product_record,
                         ttl.PRODUCT_CACHE)
    record = dict(record)
    shop = _shop(country, str(record["shop_id"]))
    record["shop"] = {k: shop.get(k) for k in (
        "id", "name", "username", "link", "location", "is_official_shop", "is_shopee_verified",
        "is_preferred_plus_seller", "rating", "followers_count", "items_count", "response_rate_percent",
        "last_active_at", "joined_at")}
    return record


def _trending_products(country):
    rows, total = parsers.parse_feed(fetch_daily_discover(country, FEED_LIMIT), country)
    return {"country": country, "count": len(rows), "results": rows}


def products_trending(**data):
    return cached_call("shopee.products_trending", data, _trending_products, ttl.TRENDING_PRODUCTS_CACHE)


# ---- deals -------------------------------------------------------------------------

def _flash_sale(country, session, category, page):
    sessions = parsers.parse_flash_sessions(fetch_flash_sessions(country), country)
    if session is None:
        current = next((s for s in sessions if s["is_ongoing"]), sessions[0] if sessions else None)
        if current is None:
            return {"country": country, "session": None, "sessions": [], "results": [],
                    "pagination": _pagination(page, FLASH_SALE_PER_PAGE, has_next=False)}
        session = current["id"]
    payload = fetch_flash_items(country, session, offset=(page - 1) * FLASH_SALE_PER_PAGE,
                                limit=FLASH_SALE_PER_PAGE, category_id=category)
    rows, served = parsers.parse_flash_items(payload, country)
    # an unknown session id answers the ongoing session's items: report it
    if served and served["id"] != session:
        raise ShopeeNotFound(f"flash sale session {session} not found")
    current = next((s for s in sessions if s["id"] == session), None)
    return {
        "country": country,
        "session": current or served,
        "sessions": [{k: s[k] for k in ("id", "name", "starts_at", "ends_at", "is_ongoing")} for s in sessions],
        "results": rows,
        "pagination": _pagination(page, FLASH_SALE_PER_PAGE, has_next=len(rows) >= FLASH_SALE_PER_PAGE),
    }


def deals_flash_sale(**data):
    return cached_call("shopee.deals_flash_sale", data, _flash_sale, ttl.FLASH_SALE_CACHE)


# ---- catalog -----------------------------------------------------------------------

def _categories_list(country):
    rows = parsers.parse_category_tree(fetch_category_tree(country), country)
    return {"country": country, "count": len(rows), "results": rows}


def categories_list(**data):
    return cached_call("shopee.categories_list", data, _categories_list, ttl.CATEGORY_TREE_CACHE)


def _autocomplete(country, query):
    keywords, shops = parsers.parse_search_hint(fetch_search_hint(country, query), country)
    return {"country": country, "query": query, "count": len(keywords), "results": keywords, "shops": shops}


def search_autocomplete(**data):
    return cached_call("shopee.search_autocomplete", data, _autocomplete, ttl.AUTOCOMPLETE_CACHE)


def _trending_searches(country):
    rows = parsers.parse_search_suggestion(fetch_search_suggestion(country), country)
    return {"country": country, "count": len(rows), "results": rows}


def search_trending(**data):
    return cached_call("shopee.search_trending", data, _trending_searches, ttl.TRENDING_SEARCHES_CACHE)
