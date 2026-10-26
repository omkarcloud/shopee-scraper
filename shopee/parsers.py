"""Raw Shopee HTML / JSON -> clean dicts for every /shopee/* endpoint. Pure
functions, no I/O.

Value conventions (shared with the other scraper packages):
  * money   Shopee integers are 1/100000 of the local currency -> float
            amount + a separate `currency` (refs.CURRENCY_OF)
  * dates   epoch seconds -> ISO 8601 UTC ("2026-10-24T09:14:05Z")
  * images  susercontent hashes -> CDN links (refs.image_link)
  * keys    snake_case; `link` not `url`; booleans as questions; absent,
            masked or paywalled values are null (never "" / "N/A")

The product record comes from the page's server-rendered copy, which
Shopee renders at detail_level 1 ("removed_fields": [1]): price, stock,
sold count, rating, review count and the shop block are null in it, and
`models[].stock` is a constant 10 on every market (a display cap, not a
stock figure) — all of those come back null here rather than as fake
numbers.

Fixtures captured 2026-10-24 (shopee/fixtures/): an official-store product
on shopee.sg, the same page for an unknown item id (empty cachedMap) and
product pages from shopee.co.th (sparse: attributes null, 25 colour
options) and shopee.com.br — all four trimmed to the <head> plus the
mfe-initial-data blob, with Shopee's own account / i18n credential-label
keys masked ("pass_word"; never parsed) so a secret scan of the repo stays
clean — shop detail / categories /
reviews / vouchers for L'Oreal SG (15235546) and a small SG shop, shop
detail for TH / BR shops and the two not-found replies, the SG category
tree, autocomplete for "iphone" and for a nonsense term, trending
searches, flash-sale sessions + one session's items, the SG home feed and
the official-store directory.
"""
import html as html_lib
import re
from datetime import datetime, timezone

from shopee import refs

MONEY_UNIT = 100000

_META_RE = re.compile(r'<meta[^>]+(?:name|property)="(description|og:url|og:image)"[^>]+content="([^"]*)"')


# ---- value helpers ----------------------------------------------------------------

def money(value):
    """Shopee price integer (1/100000 units) -> amount; None / 0 / -1 -> None."""
    if value in (None, "", -1) or isinstance(value, bool):
        return None
    try:
        amount = float(value) / MONEY_UNIT
    except (TypeError, ValueError):
        return None
    if amount <= 0:
        return None
    return round(amount, 2)


def ts(value):
    """Epoch seconds -> ISO 8601 UTC string; 0 / None -> None."""
    if not value or isinstance(value, bool):
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def text(value):
    """A trimmed string, or None for empty / placeholder values."""
    if value is None or isinstance(value, (bool, int, float, list, dict)):
        return None
    value = html_lib.unescape(str(value)).strip()
    return value if value and value not in ("-", "N/A", "null") else None


def number(value):
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value) if "." in str(value) else int(value)
    except (TypeError, ValueError):
        return None


def flag(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def image(country, value):
    return refs.image_link(country, value)


def images(country, values):
    return [image(country, v) for v in (values or []) if v] if isinstance(values, list) else []


def rating_block(raw):
    """{"rating_star", "rating_count": [total, 1★, 2★, 3★, 4★, 5★]} ->
    {average, count, counts_by_star}."""
    if not isinstance(raw, dict):
        return None
    counts = raw.get("rating_count") or raw.get("rating_counts")
    by_star = None
    total = None
    if isinstance(counts, list) and len(counts) == 6:
        total = number(counts[0])
        by_star = {str(star): number(counts[star]) for star in range(1, 6)}
    elif isinstance(counts, list) and counts:
        total = number(counts[0])
    average = number(raw.get("rating_star"))
    if average is None and total is None:
        return None
    return {"average": round(average, 2) if isinstance(average, float) else average,
            "count": total, "counts_by_star": by_star}


# ---- product ----------------------------------------------------------------------

CONDITIONS = {1: "new", 2: "used"}


def _blob_record(blob):
    """The one product record of a product page blob, or None (unknown id)."""
    try:
        cached = blob["initialState"]["DOMAIN_PDP"]["data"]["PDP_BFF_DATA"]["cachedMap"]
    except (KeyError, TypeError):
        return None
    if not isinstance(cached, dict) or not cached:
        return None
    record = next(iter(cached.values()))
    return record if isinstance(record, dict) and isinstance(record.get("item"), dict) else None


def _description(record, item):
    paragraphs = ((record.get("product_description") or {}).get("paragraph_list")) or []
    lines = [text(p.get("text")) for p in paragraphs if isinstance(p, dict) and p.get("type") == 0]
    lines = [line for line in lines if line]
    if lines:
        return "\n".join(lines)
    return text(item.get("description"))


def _variations(country, item):
    out = []
    for tier in item.get("tier_variations") or []:
        if not isinstance(tier, dict):
            continue
        name = text(tier.get("name"))
        options = tier.get("options") or []
        tier_images = tier.get("images") or []
        if not name and options in ([], [""]):
            continue   # the placeholder single-variation of a one-SKU listing
        out.append({
            "name": name,
            "options": [{"name": text(opt),
                         "image": image(country, tier_images[i]) if i < len(tier_images) else None}
                        for i, opt in enumerate(options)],
        })
    return out


def _models(item):
    out = []
    for model in item.get("models") or []:
        if not isinstance(model, dict):
            continue
        ext = model.get("extinfo") or {}
        out.append({
            "id": model.get("model_id") or model.get("modelid"),
            "name": text(model.get("name")),
            "option_indexes": ext.get("tier_index") if isinstance(ext.get("tier_index"), list) else None,
            "price": money(model.get("price")),
            "stock": None,   # a constant 10 in the server copy (module docstring)
            "is_pre_order": flag(ext.get("is_pre_order")),
            "estimated_delivery_days": number(ext.get("estimated_days")),
            "is_available": model.get("status") == 1,
        })
    return out


def _attributes(record, item):
    attrs = item.get("attributes")
    if not isinstance(attrs, list):
        attrs = (record.get("product_attributes") or {}).get("attrs")
    out = []
    for attr in attrs or []:
        if isinstance(attr, dict) and text(attr.get("name")):
            out.append({"id": attr.get("id"), "name": text(attr.get("name")), "value": text(attr.get("value"))})
    return out


def _categories(country, item):
    cats = item.get("fe_categories") or item.get("categories") or []
    return [{"id": c.get("catid"), "name": text(c.get("display_name")),
             "link": refs.category_link(country, c.get("display_name"), c.get("catid"))}
            for c in cats if isinstance(c, dict) and c.get("catid")]


def _videos(item):
    out = []
    for video in item.get("video_info_list") or []:
        if not isinstance(video, dict):
            continue
        out.append({"id": video.get("video_id"), "link": video.get("default_format", {}).get("url")
                    if isinstance(video.get("default_format"), dict) else video.get("url"),
                    "thumbnail": video.get("thumb_url"), "duration_seconds": number(video.get("duration"))})
    return out


def _services(record):
    drawer = (record.get("service_drawer") or {}).get("services")
    entrance = (record.get("service_entrance") or {}).get("services")
    out = []
    for svc in drawer or entrance or []:
        if isinstance(svc, dict):
            title = text(svc.get("title") or svc.get("text"))
            if title:
                out.append({"title": title, "description": text(svc.get("description"))})
    return out


def page_meta(html):
    """description / og:url / og:image of a product page head."""
    found = {}
    for key, value in _META_RE.findall(html or ""):
        found.setdefault(key, html_lib.unescape(value))
    return found


def parse_product(html, blob, country):
    """The product record of a product page, or None when the page carries
    no product (unknown shop_id/item_id pair)."""
    record = _blob_record(blob or {})
    if record is None:
        return None
    item = record["item"]
    shop_id = item.get("shop_id") or item.get("shopid")
    item_id = item.get("item_id") or item.get("itemid")
    meta = page_meta(html)
    brand = text(item.get("brand"))
    return {
        "id": item_id,
        "shop_id": shop_id,
        "name": text(item.get("title") or item.get("name")),
        "link": refs.product_link(country, shop_id, item_id),
        "canonical_link": meta.get("og:url") or None,
        "status": text(item.get("item_status")),
        "condition": CONDITIONS.get(item.get("condition")),
        "brand": {"id": item.get("brand_id") or None, "name": brand} if brand else None,
        "currency": refs.CURRENCY_OF[country],
        # detail_level 1 copy: these are null on the server side (module docstring)
        "price": money(item.get("price")),
        "price_min": money(item.get("price_min")),
        "price_max": money(item.get("price_max")),
        "price_before_discount": money(item.get("price_before_discount")),
        "stock": None,
        "sold_count": number(item.get("historical_sold")),
        "rating": rating_block(item.get("item_rating")),
        "reviews_count": number(item.get("cmt_count")),
        "likes_count": number(item.get("liked_count")),
        "description": _description(record, item),
        "images": images(country, item.get("images") or (record.get("product_images") or {}).get("images")),
        "videos": _videos(item),
        "variations": _variations(country, item),
        "models": _models(item),
        "attributes": _attributes(record, item),
        "categories": _categories(country, item),
        "services": _services(record),
        "shipping": {
            "is_free_shipping": flag(item.get("is_free_shipping")),
            "estimated_delivery_days": number(item.get("estimated_days")),
            "ships_from": text(item.get("shop_location")),
        },
        "purchase_limits": {
            "min_quantity": number(item.get("min_purchase_limit")) or None,
            "max_quantity": number(item.get("overall_purchase_limit")),
        },
        "is_pre_order": flag(item.get("is_pre_order")),
        "is_adult": flag(item.get("is_adult")),
        "has_video": flag(item.get("item_has_video")),
        "is_official_shop": flag(item.get("is_official_shop")),
        "is_mart": flag(item.get("is_mart")),
        "listed_at": ts(item.get("ctime")),
        "shop": {"id": shop_id, "link": refs.shop_link(country, shop_id)},   # filled by api.product_details
    }


# ---- shops ------------------------------------------------------------------------

def parse_shop(payload, country):
    """A shop profile from either payload: the app's get_shop_base (what
    fetch.fetch_shop_base reads since 2026-10-26) or the web get_shop_detail
    (gated now; its extra fields — location, preparation time, cancellation
    rate, flash / brand sale flags, profile-update time — are null from the
    base payload)."""
    data = (payload or {}).get("data") or {}
    account = data.get("account") or {}
    shop_rating = data.get("shop_rating") if isinstance(data.get("shop_rating"), dict) else {}
    tabs = data.get("show_tab") if isinstance(data.get("show_tab"), dict) else {}
    new_arrivals = tabs.get("new_arrival_tab") if isinstance(tabs.get("new_arrival_tab"), dict) else {}
    membership = tabs.get("membership_tab") if isinstance(tabs.get("membership_tab"), dict) else {}
    shop_id = data.get("shopid")
    username = text(account.get("username"))

    def first(*values):
        return next((v for v in values if v is not None), None)

    good = number(first(data.get("rating_good"), shop_rating.get("rating_good")))
    normal = number(first(data.get("rating_normal"), shop_rating.get("rating_normal")))
    bad = number(first(data.get("rating_bad"), shop_rating.get("rating_bad")))
    total = sum(x for x in (good, normal, bad) if isinstance(x, (int, float))) if any(
        isinstance(x, (int, float)) for x in (good, normal, bad)) else None
    average = number(data.get("rating_star"))
    return {
        "id": shop_id,
        "name": text(data.get("name")),
        "username": username,
        "link": refs.shop_link(country, shop_id),
        "username_link": refs.shop_username_link(country, username) if username else None,
        "description": text(data.get("description")),
        "country": text(data.get("country")) or country.upper(),
        "location": text(data.get("shop_location")),
        "avatar": image(country, account.get("portrait")),
        "cover_image": image(country, data.get("cover")),
        "is_official_shop": flag(first(data.get("is_official_shop"), data.get("show_official_shop_label"))),
        "is_shopee_verified": flag(data.get("is_shopee_verified")),
        "is_preferred_plus_seller": flag(data.get("is_preferred_plus_seller")),
        "is_on_vacation": flag(data.get("vacation")),
        "is_chat_enabled": (not data["chat_disabled"]) if isinstance(data.get("chat_disabled"), bool) else None,
        "items_count": number(data.get("item_count")),
        "followers_count": number(data.get("follower_count")),
        "following_count": number(account.get("following_count")),
        "rating": {
            "average": round(average, 2) if isinstance(average, float) else average,
            "count": total,
            "good": good, "normal": normal, "bad": bad,
        },
        "response_rate_percent": number(data.get("response_rate")),
        "response_time_seconds": number(data.get("response_time")),
        "preparation_time_seconds": number(data.get("preparation_time")),
        "cancellation_rate_percent": number(data.get("cancellation_rate")),
        "has_flash_sale": flag(data.get("has_flash_sale")),
        "has_brand_sale": flag(data.get("has_brand_sale")),
        "has_live_stream": flag(first(data.get("show_live_tab"), tabs.get("show_live_tab"))),
        "has_membership": flag(first(data.get("show_membership_tab"), membership.get("show_membership_tab"))),
        "latest_item_listed_at": ts(first(data.get("latest_item_ctime"), new_arrivals.get("latest_item_ctime"))),
        "joined_at": ts(data.get("ctime")),
        "last_active_at": ts(data.get("last_active_time")),
        "updated_at": ts(data.get("mtime")),
        "vouchers": [],   # filled by api.shop_details
    }


def parse_shop_categories(payload, country, shop_id):
    data = (payload or {}).get("data") or {}
    rows = []
    for cat in data.get("shop_categories") or []:
        if not isinstance(cat, dict):
            continue
        cat_id = cat.get("shop_category_id")
        rows.append({
            "id": cat_id,
            "name": text(cat.get("display_name")),
            "link": f"{refs.shop_link(country, shop_id)}?shopCollection={cat_id}",
            "image": image(country, cat.get("image")),
            "items_count": number(cat.get("total")),
            "is_auto_generated": flag(cat.get("is_generated")),
            "is_adult": flag(cat.get("is_adult")),
        })
    return rows, number(data.get("total")), flag(data.get("has_more"))


def _review_product(country, raw):
    if not isinstance(raw, dict):
        return None
    item_id, shop_id = raw.get("itemid"), raw.get("shopid")
    return {
        "id": item_id, "shop_id": shop_id, "name": text(raw.get("name")),
        "link": refs.product_link(country, shop_id, item_id) if item_id and shop_id else None,
        "image": image(country, raw.get("image")),
        "model_id": raw.get("modelid") or None, "variation": text(raw.get("model_name")),
    }


def _reply(raw):
    if not isinstance(raw, dict):
        return None
    comment = text(raw.get("comment"))
    return {"comment": comment, "created_at": ts(raw.get("ctime"))} if comment else None


def parse_shop_reviews(payload, country):
    data = (payload or {}).get("data") or {}
    rows = []
    for review in data.get("items") or []:
        if not isinstance(review, dict):
            continue
        products = review.get("product_items") or []
        tags = [text(t.get("tag_description") or t.get("text") or t.get("name")) if isinstance(t, dict) else text(t)
                for t in (review.get("template_tags") or review.get("tags") or [])]
        rows.append({
            "id": review.get("cmtid"),
            "rating": number(review.get("rating_star")),
            "comment": text(review.get("comment")),
            "detailed_rating": {k: number(v) for k, v in (review.get("detailed_rating") or {}).items()}
            if isinstance(review.get("detailed_rating"), dict) else None,
            "author": {
                "username": text(review.get("author_username")),
                "avatar": image(country, review.get("author_portrait")),
                "is_anonymous": flag(review.get("anonymous")),
            },
            "product": _review_product(country, products[0] if products else None),
            "images": images(country, review.get("images")),
            "videos": [v.get("url") if isinstance(v, dict) else v for v in (review.get("videos") or []) if v],
            "tags": [t for t in tags if t],
            "likes_count": number(review.get("like_count")),
            "is_repeat_purchase": flag(review.get("is_repeated_purchase")),
            "seller_reply": _reply(review.get("ItemRatingReply")),
            "created_at": ts(review.get("ctime")),
            "updated_at": ts(review.get("mtime")),
        })
    return rows


REWARD_TYPES = {0: "percentage", 1: "fixed_amount", 2: "coins"}


def parse_vouchers(payload):
    data = (payload or {}).get("data") or {}
    rows = []
    for v in data.get("voucher_list") or []:
        if not isinstance(v, dict):
            continue
        # reward_percentage is the integer percent; the _with_decimal twin is
        # the same figure in 1/100000 units (18 % -> 1800000)
        percentage = number(v.get("reward_percentage")) or number(v.get("discount_percentage"))
        if not percentage and number(v.get("reward_percentage_with_decimal")):
            percentage = round(number(v.get("reward_percentage_with_decimal")) / MONEY_UNIT, 2)
        rows.append({
            "id": v.get("promotionid"),
            "code": text(v.get("voucher_code")),
            "title": text(v.get("title")),
            "description": text(v.get("description")),
            "reward_type": REWARD_TYPES.get(v.get("reward_type"), text(v.get("reward_type"))),
            "discount_percent": percentage or None,
            "discount_amount": money(v.get("reward_value")) or money(v.get("discount_value")),
            "discount_cap": money(v.get("reward_cap")) or money(v.get("discount_cap")),
            "coins_percent": number(v.get("coin_percentage")) or None,
            "min_spend": money(v.get("min_spend")),
            "starts_at": ts(v.get("start_time")),
            "ends_at": ts(v.get("end_time")),
            "claim_starts_at": ts(v.get("claim_start_time")),
            "claim_ends_at": ts(v.get("claim_end_time")),
            "usage_limit": number(v.get("usage_limit")),
            "used_count": number(v.get("used_count")),
            "left_count": number(v.get("left_count")),
            "percentage_claimed": number(v.get("percentage_claimed")),
            "percentage_used": number(v.get("percentage_used")),
            "is_new_user_only": flag(v.get("new_user_only")),
            "is_fully_claimed": flag(v.get("fully_claimed")),
            "is_expired": flag(v.get("has_expired")),
        })
    return rows


def parse_official_shops(payload, country):
    data = (payload or {}).get("data") or {}
    rows = []
    for shop in data.get("official_shops") or []:
        if not isinstance(shop, dict):
            continue
        shop_id = shop.get("shopid")
        username = text(shop.get("username"))
        rows.append({
            "id": shop_id,
            "name": text(shop.get("shop_name")),
            "username": username,
            "link": refs.shop_link(country, shop_id),
            "brand_name": text(shop.get("brand_name")),
            "logo": image(country, shop.get("logo_pc") or shop.get("logo")),
            "joined_at": ts(shop.get("ctime")),
        })
    return rows, number(data.get("total"))


# ---- catalog ----------------------------------------------------------------------

def _category(country, raw):
    children = raw.get("children") or []
    return {
        "id": raw.get("catid"),
        "name": text(raw.get("display_name") or raw.get("name")),
        "level": number(raw.get("level")),
        "parent_id": raw.get("parent_catid") or None,
        "link": refs.category_link(country, raw.get("display_name") or raw.get("name"), raw.get("catid")),
        "image": image(country, raw.get("image")),
        "children": [_category(country, c) for c in children if isinstance(c, dict)],
    }


def parse_category_tree(payload, country):
    data = (payload or {}).get("data") or {}
    return [_category(country, c) for c in data.get("category_list") or [] if isinstance(c, dict)]


def parse_search_hint(payload, country):
    rows = []
    for kw in (payload or {}).get("keywords") or []:
        if not isinstance(kw, dict) or not text(kw.get("keyword")):
            continue
        keyword = text(kw.get("keyword"))
        cat_id = kw.get("catid") or None
        rows.append({
            "keyword": keyword,
            "link": refs.search_link(country, keyword),
            "category": {"id": cat_id, "name": text(kw.get("cat_display_name"))} if cat_id else None,
        })
    shops = []
    hint = (payload or {}).get("shop_hint")
    for shop in (hint.get("shops") if isinstance(hint, dict) else hint) or []:
        if isinstance(shop, dict) and shop.get("shopid"):
            shops.append({"id": shop.get("shopid"), "name": text(shop.get("shop_name") or shop.get("name")),
                          "link": refs.shop_link(country, shop.get("shopid"))})
    return rows, shops


def parse_search_suggestion(payload, country):
    data = (payload or {}).get("data") or {}
    rows = []
    for q in data.get("queries") or []:
        if not isinstance(q, dict) or not text(q.get("text")):
            continue
        keyword = text(q.get("text"))
        rows.append({
            "keyword": keyword,
            "link": refs.search_link(country, keyword),
            "image": image(country, q.get("image") or (q.get("images") or [None])[0]),
            "item_ids": [i for i in (q.get("item_ids") or []) if i],
            "shop_ids": [i for i in (q.get("shop_ids") or []) if i],
        })
    return rows


def parse_flash_sessions(payload, country):
    data = (payload or {}).get("data") or {}
    rows = []
    for s in data.get("sessions") or []:
        if not isinstance(s, dict):
            continue
        rows.append({
            "id": s.get("promotionid"),
            "name": text(s.get("name")),
            "description": text(s.get("description")),
            "starts_at": ts(s.get("start_time")),
            "ends_at": ts(s.get("end_time")),
            "is_ongoing": flag(s.get("is_ongoing")),
            "categories": [{"id": c.get("catid"), "name": text(c.get("catname")), "image": image(country, c.get("image"))}
                           for c in (s.get("categories") or []) if isinstance(c, dict)],
        })
    return rows


def parse_flash_items(payload, country):
    data = (payload or {}).get("data") or {}
    rows = []
    for it in data.get("items") or []:
        if not isinstance(it, dict):
            continue
        shop_id, item_id = it.get("shopid"), it.get("itemid")
        rating = it.get("item_rating") or {}
        rows.append({
            "id": item_id,
            "shop_id": shop_id,
            "name": text(it.get("name")),
            "link": refs.product_link(country, shop_id, item_id),
            "image": image(country, it.get("image")),
            "images": images(country, it.get("promo_images")),
            "currency": refs.CURRENCY_OF[country],
            "price": money(it.get("price")),
            "price_before_discount": money(it.get("price_before_discount")),
            "discount_percent": number(it.get("raw_discount")) or None,
            "stock": number(it.get("stock")),
            "flash_sale_stock": number(it.get("flash_sale_stock")),
            "sold_count": number(it.get("historical_sold")),
            "rating": rating_block({"rating_star": rating.get("rating_star"), "rating_count": rating.get("rating_counts")}),
            "category_ids": [c for c in (it.get("cats") or []) if c],
            "flash_sale_category_id": it.get("flash_catid"),
            "promotion_id": it.get("promotionid"),
            "starts_at": ts(it.get("start_time")),
            "ends_at": ts(it.get("end_time")),
            "is_shop_official": flag(it.get("is_shop_official")),
            "is_shop_preferred": flag(it.get("is_shop_preferred")),
            "is_shopee_choice": flag(it.get("is_shopee_choice")),
            "is_mart": flag(it.get("is_mart")),
            "is_adult": flag(it.get("is_adult")),
        })
    session = data.get("session") or {}
    return rows, {"id": session.get("promotionid"), "starts_at": ts(session.get("start_time")),
                  "ends_at": ts(session.get("end_time"))} if session.get("promotionid") else None


def parse_feed(payload, country):
    """The homepage feed's product cards (centralised_item_card entries)."""
    data = (payload or {}).get("data") or {}
    rows = []
    for feed in data.get("feeds") or []:
        card = (feed or {}).get("centralised_item_card") if isinstance(feed, dict) else None
        item = (card or {}).get("item_data")
        if not isinstance(item, dict) or not item.get("itemid"):
            continue
        asset = card.get("item_card_displayed_asset") or {}
        price = item.get("item_card_display_price") or {}
        shop = item.get("shop_data") or {}
        shop_id, item_id = item.get("shopid"), item.get("itemid")
        sold = item.get("item_card_display_sold_count")
        rows.append({
            "id": item_id,
            "shop_id": shop_id,
            "name": text(asset.get("name")),
            "link": refs.product_link(country, shop_id, item_id),
            "image": image(country, asset.get("image")),
            "images": images(country, asset.get("images")),
            "currency": refs.CURRENCY_OF[country],
            "price": money(price.get("price")),
            "price_before_discount": money(price.get("strikethrough_price")) or (
                money(price.get("original_price")) if price.get("original_price") != price.get("price") else None),
            "discount_percent": number(price.get("discount")) or None,
            "sold_count": number(sold.get("historical_sold_count") if isinstance(sold, dict) else sold),
            "rating": rating_block(item.get("item_rating")),
            "likes_count": number(item.get("liked_count")),
            "category_id": item.get("catid"),
            "shop": {"id": shop_id, "name": text(shop.get("shop_name")), "link": refs.shop_link(country, shop_id),
                     "location": text(asset.get("shop_location"))},
            "is_sold_out": flag(item.get("is_sold_out")),
            "is_shopee_verified": flag(item.get("shopee_verified")),
            "is_adult": flag(item.get("is_adult")),
            "listed_at": ts(item.get("ctime")),
        })
    return rows, number(data.get("feed_total"))
