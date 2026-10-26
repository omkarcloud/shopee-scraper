"""Offline tests for the Shopee parsers, reference resolvers and value
helpers.

    python -m pytest shopee/test_parsers.py -q

Fixtures are real Shopee pages / JSON captured 2026-10-24 (shopee/fixtures/,
see parsers.py's docstring): an official-store product page on shopee.sg,
the same page for an unknown item (empty cachedMap), trimmed product pages
from shopee.co.th (sparse) and shopee.com.br, shop detail / categories /
reviews / vouchers, the category tree, autocomplete, trending searches,
flash sale, the home feed and the official-store directory. No network.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopee import parsers as P, refs  # noqa: E402
from shopee.fetch import page_title, product_blob  # noqa: E402

FX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture(name):
    with open(os.path.join(FX, name), encoding="utf-8") as f:
        return json.load(f) if name.endswith(".json") else f.read()


def product(name, country):
    html = fixture(name)
    return P.parse_product(html, product_blob(html), country)


@pytest.fixture(scope="module")
def loreal():
    return product("product_loreal_sg_trimmed.html", "sg")


@pytest.fixture(scope="module")
def thai():
    return product("product_th_trimmed.html", "th")


@pytest.fixture(scope="module")
def brazil():
    return product("product_br_trimmed.html", "br")


# ---- refs -------------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("15235546.23326616342", (15235546, 23326616342, None)),
    ("15235546/23326616342", (15235546, 23326616342, None)),
    ("https://shopee.sg/product/15235546/23326616342", (15235546, 23326616342, "sg")),
    ("https://shopee.co.th/product/146916334/29523950820?sp_atk=x", (146916334, 29523950820, "th")),
    ("https://shopee.com.br/Novo-iPhone-17-i.486926153.22192886389", (486926153, 22192886389, "br")),
    ("shopee.sg/x-i.1.2", None),   # not a link, not a pair
    ("https://mall.shopee.sg/universal-link/product/15235546/23326616342", (15235546, 23326616342, "sg")),
])
def test_resolve_product(value, expected):
    if expected is None:
        with pytest.raises(ValueError):
            refs.resolve_product(value)
    else:
        assert tuple(refs.resolve_product(value)) == expected


@pytest.mark.parametrize("value", ["", "abc.def", "https://example.com/product/1/2",
                                   "https://shopee.cl/product/1/2", "https://shopee.sg/search?keyword=x"])
def test_resolve_product_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_product(value)


@pytest.mark.parametrize("value,expected", [
    ("15235546", (15235546, None, None)),
    ("lorealparissg", (None, "lorealparissg", None)),
    ("LorealParisSG", (None, "lorealparissg", None)),
    ("https://shopee.sg/shop/15235546", (15235546, None, "sg")),
    ("https://shopee.sg/shop/15235546?page=2", (15235546, None, "sg")),
    ("https://shopee.com.my/lorealparissg", (None, "lorealparissg", "my")),
])
def test_resolve_shop(value, expected):
    assert tuple(refs.resolve_shop(value)) == expected


@pytest.mark.parametrize("value", ["", "a b", "https://shopee.sg/search?keyword=x", "https://shopee.sg/cart/",
                                   "https://example.com/shop/1", "https://shopee.sg/product/1/2"])
def test_resolve_shop_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_shop(value)


def test_links():
    assert refs.product_link("th", 1, 2) == "https://shopee.co.th/product/1/2"
    assert refs.shop_link("br", 7) == "https://shopee.com.br/shop/7"
    assert refs.category_link("sg", "Women's Apparel", 11012819) == "https://shopee.sg/Women-s-Apparel-cat.11012819"
    assert refs.category_link("th", "อุปกรณ์ DIY", 11045185).endswith("-cat.11045185")
    assert refs.image_link("id", "abc") == "https://down-id.img.susercontent.com/file/abc"
    assert refs.image_link("id", "https://x/y.png") == "https://x/y.png"
    assert refs.image_link("sg", None) is None


# ---- value helpers ------------------------------------------------------------------------

def test_money_and_ts():
    assert P.money(1205000) == 12.05
    assert P.money(0) is None and P.money(-1) is None and P.money(None) is None and P.money("x") is None
    assert P.ts(1792821600) == "2026-10-24T06:00:00Z"
    assert P.ts(0) is None and P.ts(None) is None
    assert P.text("  ") is None and P.text("-") is None and P.text("&amp;x") == "&x"
    assert P.number("12") == 12 and P.number("1.5") == 1.5 and P.number(True) is None
    assert P.rating_block({"rating_star": 4.8912, "rating_count": [10, 1, 0, 1, 2, 6]}) == {
        "average": 4.89, "count": 10, "counts_by_star": {"1": 1, "2": 0, "3": 1, "4": 2, "5": 6}}
    assert P.rating_block({"rating_star": None, "rating_count": []}) is None


# ---- product ------------------------------------------------------------------------------

def test_product_identity_and_links(loreal):
    assert loreal["id"] == 23326616342 and loreal["shop_id"] == 15235546
    assert loreal["name"].startswith("L'Oreal Paris Elseve Fall Resist")
    assert loreal["link"] == "https://shopee.sg/product/15235546/23326616342"
    assert loreal["canonical_link"].endswith("-i.15235546.23326616342")
    assert loreal["status"] == "normal" and loreal["condition"] == "new"
    assert loreal["brand"] == {"id": 2387597, "name": "L'Oreal Paris"}
    assert loreal["currency"] == "SGD"
    assert loreal["listed_at"] == "2023-02-22T17:44:44Z"
    assert loreal["shop"] == {"id": 15235546, "link": "https://shopee.sg/shop/15235546"}


def test_product_paywalled_fields_are_null(loreal, thai, brazil):
    for rec in (loreal, thai, brazil):
        for key in ("price", "price_min", "price_max", "price_before_discount", "stock", "sold_count",
                    "rating", "reviews_count", "likes_count"):
            assert rec[key] is None, key
        for model in rec["models"]:
            assert model["stock"] is None and model["price"] is None


def test_product_content(loreal):
    assert loreal["description"].startswith("• What is it ?")
    assert "Up to 97% Less Hair Fall" in loreal["description"]
    assert len(loreal["images"]) == 8 and all(i.startswith("https://down-sg.img.susercontent.com/file/") for i in loreal["images"])
    assert loreal["variations"] == []          # one-SKU listing: the placeholder tier is dropped
    assert len(loreal["models"]) == 1 and loreal["models"][0]["is_available"] is True
    assert {"id": 100016, "name": "Pack Type", "value": "Value Size"} in loreal["attributes"]
    assert [c["name"] for c in loreal["categories"]] == ["Beauty & Personal Care", "Women's Hair Care", "Shampoo"]
    assert loreal["categories"][0]["link"] == "https://shopee.sg/Beauty-Personal-Care-cat.11012301"
    assert loreal["services"][0]["title"] == "100% Authentic" and loreal["services"][1]["title"] == "15-Day Free Returns"
    assert loreal["shipping"] == {"is_free_shipping": False, "estimated_delivery_days": 1, "ships_from": "SG"}
    assert loreal["purchase_limits"] == {"min_quantity": 1, "max_quantity": None}
    assert loreal["is_official_shop"] is True and loreal["is_adult"] is False and loreal["has_video"] is False


def test_product_variations_and_models(thai, brazil):
    assert thai["currency"] == "THB" and thai["brand"] is None
    assert len(thai["variations"]) == 1 and thai["variations"][0]["name"] == "สี"
    assert len(thai["variations"][0]["options"]) == 25
    assert thai["variations"][0]["options"][0]["image"].startswith("https://down-th.img.susercontent.com/")
    assert len(thai["models"]) == 25 and thai["models"][0]["option_indexes"] == [11]
    assert thai["attributes"] == [{"id": None, "name": "ส่งจาก", "value": "จังหวัดสุโขทัย"}]   # item.attributes null -> product_attributes
    assert thai["categories"][0]["link"].startswith("https://shopee.co.th/%E0%B9%80")
    assert len(brazil["variations"]) == 2 and [v["name"] for v in brazil["variations"]] == ["Cor", "Modelo / Memória"]
    assert len(brazil["models"]) == 21 and brazil["models"][0]["option_indexes"] == [1, 0]
    assert brazil["models"][0]["name"] == "Azul,17 PRO MAX - 1TB"


def test_product_unknown_id_is_none():
    html = fixture("product_unknown_sg_trimmed.html")
    assert product_blob(html) is not None            # the page still renders the blob...
    assert P.parse_product(html, product_blob(html), "sg") is None   # ...with an empty cachedMap
    assert page_title(html) == "Shopee Singapore | Cheaper, Faster On Shopee"
    assert P.parse_product("", None, "sg") is None
    assert P.parse_product("<html></html>", {"initialState": {}}, "sg") is None


# ---- shops --------------------------------------------------------------------------------

def test_parse_shop():
    shop = P.parse_shop(fixture("shop_detail_loreal.json"), "sg")
    assert shop["id"] == 15235546 and shop["name"] == "L'Oreal Paris Official Store"
    assert shop["username"] == "lorealparissg"
    assert shop["link"] == "https://shopee.sg/shop/15235546" and shop["username_link"] == "https://shopee.sg/lorealparissg"
    assert shop["description"].startswith("Buy shampoos")
    assert shop["country"] == "SG" and shop["location"] is None
    assert shop["is_official_shop"] is True and shop["is_shopee_verified"] is False
    assert shop["is_on_vacation"] is False and shop["is_chat_enabled"] is True
    assert shop["items_count"] == 202 and shop["followers_count"] == 71515 and shop["following_count"] == 3
    assert shop["rating"] == {"average": 4.89, "count": 80734, "good": 78757, "normal": 1506, "bad": 471}
    assert shop["response_rate_percent"] == 99 and shop["response_time_seconds"] == 10125
    assert shop["joined_at"] == "2017-01-16T07:07:56Z" and shop["last_active_at"] == "2026-10-24T09:10:46Z"
    assert shop["avatar"].endswith("/f9794753aeed60aadfa103a938795d7e")
    assert shop["vouchers"] == []


def test_parse_shop_other_markets():
    th = P.parse_shop(fixture("shop_detail_th.json"), "th")
    assert th["link"].startswith("https://shopee.co.th/shop/") and th["country"] == "TH" and th["location"]
    br = P.parse_shop(fixture("shop_detail_br.json"), "br")
    assert br["country"] == "BR" and br["name"]
    by_name = P.parse_shop(fixture("shop_detail_by_username.json"), "sg")
    assert by_name["id"] == 1618725281 and by_name["username"] == "lin0012kf.sg"


def test_parse_shop_not_found_payloads():
    assert P.parse_shop(fixture("shop_detail_unknown.json"), "sg")["id"] is None
    assert P.parse_shop(fixture("shop_detail_bad_username.json"), "sg")["id"] is None
    assert P.parse_shop(fixture("shop_base_unknown.json"), "sg")["id"] is None
    assert P.parse_shop({}, "sg")["id"] is None


def test_parse_shop_from_app_base():
    """get_shop_base (the app identity's profile, read since 2026-10-26) maps
    to the same record; the web-only fields come back null."""
    base = P.parse_shop(fixture("shop_base_loreal.json"), "sg")
    detail = P.parse_shop(fixture("shop_detail_loreal.json"), "sg")
    assert list(base) == list(detail)
    assert base["id"] == 15235546 and base["name"] == "L'Oreal Paris Official Store"
    assert base["username"] == "lorealparissg" and base["link"] == "https://shopee.sg/shop/15235546"
    assert base["is_official_shop"] is True and base["is_chat_enabled"] is True
    assert base["rating"] == {"average": 4.89, "count": 80932, "good": 78955, "normal": 1506, "bad": 471}
    assert base["items_count"] == 202 and base["followers_count"] == 71543 and base["following_count"] == 3
    assert base["response_rate_percent"] == 100 and base["response_time_seconds"] == 10466
    assert base["has_live_stream"] is True and base["has_membership"] is True
    assert base["latest_item_listed_at"] == "2026-10-21T07:52:51Z" and base["joined_at"] == "2017-01-16T07:07:56Z"
    assert base["description"].startswith("Buy shampoos")
    for web_only in ("location", "preparation_time_seconds", "cancellation_rate_percent", "has_flash_sale",
                     "has_brand_sale", "updated_at"):
        assert base[web_only] is None, web_only
    th = P.parse_shop(fixture("shop_base_th.json"), "th")
    assert th["username"] == "rayban.th" and th["link"] == "https://shopee.co.th/shop/55953258"
    assert th["is_official_shop"] is True and th["country"] == "TH"


def test_parse_shop_categories():
    rows, total, has_more = P.parse_shop_categories(fixture("shop_categories_loreal.json"), "sg", 15235546)
    assert total == 25 and has_more is False and len(rows) == 25
    assert rows[0] == {"id": 263918827, "name": "🔬 Glycolic Gloss Range",
                       "link": "https://shopee.sg/shop/15235546?shopCollection=263918827",
                       "image": "https://down-sg.img.susercontent.com/file/sg-11134207-8257u-munqrainq60z59",
                       "items_count": 4, "is_auto_generated": False, "is_adult": False}
    assert P.parse_shop_categories({}, "sg", 1) == ([], None, None)


def test_parse_shop_reviews():
    rows = P.parse_shop_reviews(fixture("shop_ratings_loreal_1.json"), "sg")
    assert len(rows) == 20 and all(r["rating"] == 1 for r in rows)
    first = rows[0]
    assert first["id"] == 114085284892 and first["comment"] is None
    assert first["detailed_rating"] == {"product_quality": 1, "seller_service": 5, "delivery_service": 5}
    assert first["author"] == {"username": "iwantmiso", "avatar": None, "is_anonymous": False}
    assert first["product"]["id"] == 42822231542 and first["product"]["variation"] == "375"
    assert first["product"]["link"] == "https://shopee.sg/product/15235546/42822231542"
    assert first["created_at"].startswith("2026-")
    with_text = [r for r in rows if r["comment"]]
    assert with_text, "fixture carries commented reviews"
    five = P.parse_shop_reviews(fixture("shop_ratings_loreal_5.json"), "sg")
    assert len(five) == 20 and all(r["rating"] == 5 for r in five)
    small = P.parse_shop_reviews(fixture("shop_ratings_small_shop.json"), "sg")
    assert small and small[0]["product"]["shop_id"] == 1618725281
    assert P.parse_shop_reviews({"data": {"items": None}}, "sg") == []


def test_parse_vouchers():
    rows = P.parse_vouchers(fixture("shop_vouchers_loreal.json"))
    assert len(rows) == 9
    first = rows[0]
    assert first["id"] == 1537379311820800 and first["code"] == "SVC-1537379311820800"
    assert first["reward_type"] == "percentage" and first["discount_percent"] == 18
    assert first["discount_cap"] == 3.0 and first["min_spend"] == 10.0 and first["discount_amount"] is None
    assert first["starts_at"] == "2026-10-23T16:00:00Z" and first["ends_at"] == "2026-10-27T15:59:59Z"
    assert first["title"] is None and first["percentage_used"] == 23
    assert P.parse_vouchers(fixture("shop_vouchers_small.json")) == []
    assert P.parse_vouchers({}) == []


def test_parse_official_shops():
    rows, total = P.parse_official_shops(fixture("official_shops_sg.json"), "sg")
    assert total == 540 and len(rows) == 20
    assert rows[0] == {"id": 43714378, "name": "TAKA Jewellery Official Store", "username": "takajewellery.sg",
                       "link": "https://shopee.sg/shop/43714378", "brand_name": "Taka Jewellery",
                       "logo": "https://down-sg.img.susercontent.com/file/ef36c4ddf56dfe663e7df0f248c6d1be",
                       "joined_at": "2021-05-14T08:42:01Z"}


# ---- catalog ------------------------------------------------------------------------------

def test_parse_category_tree():
    rows = P.parse_category_tree(fixture("category_tree_sg.json"), "sg")
    assert len(rows) == 27
    women = rows[0]
    assert women["id"] == 11012819 and women["name"] == "Women's Apparel" and women["level"] == 1
    assert women["parent_id"] is None and women["link"] == "https://shopee.sg/Women-s-Apparel-cat.11012819"
    assert len(women["children"]) == 17
    assert women["children"][0]["name"] == "Tops" and women["children"][0]["parent_id"] == 11012819
    assert women["children"][0]["children"] == []
    assert P.parse_category_tree({}, "sg") == []


def test_parse_search_hint():
    keywords, shops = P.parse_search_hint(fixture("search_hint_iphone.json"), "sg")
    assert len(keywords) == 12 and shops == []
    assert keywords[0] == {"keyword": "iphone 16 pro max case",
                           "link": "https://shopee.sg/search?keyword=iphone%2016%20pro%20max%20case", "category": None}
    assert P.parse_search_hint(fixture("search_hint_nonsense.json"), "sg") == ([], [])
    assert P.parse_search_hint({}, "sg") == ([], [])


def test_parse_search_suggestion():
    rows = P.parse_search_suggestion(fixture("search_suggestion.json"), "sg")
    assert len(rows) == 35
    assert rows[0]["keyword"] == "iPhone 18 Pro" and rows[0]["item_ids"] == [42218283362]
    assert rows[0]["shop_ids"] == [442800909] and rows[0]["image"].startswith("https://down-sg.")
    assert P.parse_search_suggestion({}, "sg") == []


def test_parse_flash_sale():
    sessions = P.parse_flash_sessions(fixture("flash_sessions_sg.json"), "sg")
    assert len(sessions) == 4 and sessions[0]["id"] == 513667598795255 and sessions[0]["is_ongoing"] is True
    assert sessions[0]["starts_at"] == "2026-10-24T06:00:00Z" and sessions[0]["name"] == "24 Oct 14:00 - 19:59"
    assert sessions[0]["categories"][1] == {"id": 17, "name": "$1.99 Shop",
                                            "image": "https://down-sg.img.susercontent.com/file/sg-11134004-82589-mu1j7o7nqgau8d"}
    rows, served = P.parse_flash_items(fixture("flash_items_sg.json"), "sg")
    assert served == {"id": 513667598795255, "starts_at": "2026-10-24T06:00:00Z", "ends_at": "2026-10-24T12:00:00Z"}
    assert len(rows) == 16
    chair = rows[0]
    assert chair["id"] == 16931040911 and chair["shop_id"] == 728757183
    assert chair["price"] == 123.77 and chair["price_before_discount"] == 239.0 and chair["discount_percent"] == 48
    assert chair["currency"] == "SGD" and chair["stock"] == 123 and chair["flash_sale_stock"] == 125
    assert chair["sold_count"] == 12174 and chair["rating"]["average"] == 4.82 and chair["rating"]["count"] == 4398
    assert chair["link"] == "https://shopee.sg/product/728757183/16931040911"
    assert P.parse_flash_items({}, "sg") == ([], None)


def test_parse_feed():
    rows, total = P.parse_feed(fixture("daily_discover_sg.json"), "sg")
    assert total == 500 and len(rows) == 30
    first = rows[0]
    assert first["id"] == 44482244164 and first["shop_id"] == 1618725281
    assert first["name"].startswith("Universal Non-Drilling Wall Mount")
    assert first["price"] == 1.64 and first["price_before_discount"] is None and first["discount_percent"] is None
    assert first["rating"]["average"] == 4.76 and first["rating"]["count"] == 196
    assert first["likes_count"] == 307 and first["shop"]["name"] == "lin0012kf.sg"
    assert first["shop"]["location"] == "Mainland China" and len(first["images"]) == 9
    assert first["listed_at"] == "2026-07-03T02:45:37Z"
    discounted = [r for r in rows if r["discount_percent"]]
    assert discounted and discounted[0]["price_before_discount"] > discounted[0]["price"]
    assert P.parse_feed({"data": {"feeds": [{"type": "banner_card"}]}}, "sg") == ([], None)
