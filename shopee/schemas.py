"""Marshmallow request schemas for every /shopee/* route.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    product   "<shop_id>.<item_id>" OR any Shopee product link
    shop      a shop id, a username OR any Shopee shop link
    country   the market (sg, my, th, vn, ph, id, tw, br, mx); default sg.
              A link's host wins over it (shopee.co.th/... -> th).

The market is resolved once in MarketSchema.post_load: `country` is always
a market code in the loaded data and the ref params are canonical strings
("<shop_id>.<item_id>", "<shop_id>" or "<username>") so the response cache
keys stay plain.
"""
from marshmallow import ValidationError, post_load

from schema_fields import (BaseSchema, ChoiceField, PageField, PositiveInt, QueryField,
                           RefField)
from shopee import refs

REVIEWS_PER_PAGE = 20
FLASH_SALE_PER_PAGE = 50
OFFICIAL_SHOPS_PER_PAGE = 20
SHOP_CATEGORIES_PER_PAGE = 50


class CountryField(ChoiceField):
    """Shopee market code (the site's country), default sg."""

    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", refs.DEFAULT_MARKET)
        kwargs.setdefault("metadata", {"description": "Shopee market: " + ", ".join(refs.MARKETS)
                                       + " (default sg); a link's own site overrides it"})
        super().__init__(list(refs.MARKETS), **kwargs)


class ProductRefField(RefField):
    resolver = staticmethod(refs.resolve_product)


class ShopRefField(RefField):
    resolver = staticmethod(refs.resolve_shop)


class MarketSchema(BaseSchema):
    country = CountryField()

    @post_load
    def _resolve_market(self, data, **kwargs):
        ref = data.get("product") or data.get("shop")
        if ref is not None and getattr(ref, "country", None):
            data["country"] = ref.country
        if isinstance(data.get("product"), refs.ProductRef):
            data["product"] = f"{data['product'].shop_id}.{data['product'].item_id}"
        if isinstance(data.get("shop"), refs.ShopRef):
            shop = data["shop"]
            data["shop"] = str(shop.shop_id) if shop.shop_id else shop.username
        data["country"] = data.get("country") or refs.DEFAULT_MARKET
        return data


class ProductDetailsSchema(MarketSchema):
    product = ProductRefField(metadata={
        "description": "'<shop_id>.<item_id>' (e.g. 15235546.23326616342) or a Shopee product link"})


class ShopSchema(MarketSchema):
    shop = ShopRefField(metadata={
        "description": "shop id (15235546), username (lorealparissg) or a Shopee shop link"})


class ShopCategoriesSchema(ShopSchema):
    page = PageField(max_page=50, metadata={"description": f"page of {SHOP_CATEGORIES_PER_PAGE} categories"})


class ShopReviewsSchema(ShopSchema):
    rating = ChoiceField(["5", "4", "3", "2", "1"], load_default="5", metadata={
        "description": "star rating to list (5, 4, 3, 2 or 1; default 5) — Shopee serves shop reviews per star"})
    page = PageField(max_page=500, metadata={"description": f"page of {REVIEWS_PER_PAGE} reviews"})

    @post_load(pass_original=True)
    def _rating_int(self, data, original, **kwargs):
        data["rating"] = int(data["rating"])
        return data


class CategoriesListSchema(MarketSchema):
    pass


class AutocompleteSchema(MarketSchema):
    query = QueryField(max_length=100, metadata={"description": "search text to complete"})


class TrendingSearchesSchema(MarketSchema):
    pass


class FlashSaleSchema(MarketSchema):
    session = PositiveInt(metadata={
        "description": "flash-sale session (promotion) id from the `sessions` list; default: the ongoing one"})
    category = PositiveInt(metadata={
        "description": "flash-sale category id from the session's `categories` list (default: all)"})
    page = PageField(max_page=50, metadata={"description": f"page of {FLASH_SALE_PER_PAGE} deals"})


class TrendingProductsSchema(MarketSchema):
    pass


class OfficialShopsSchema(MarketSchema):
    page = PageField(max_page=200, metadata={"description": f"page of {OFFICIAL_SHOPS_PER_PAGE} official stores"})
