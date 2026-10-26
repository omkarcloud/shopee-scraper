"""Offline tests for the /shopee/* request schemas.

    python -m pytest shopee/test_schemas.py -q
"""
import os
import sys

import pytest
from marshmallow import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shopee import schemas  # noqa: E402


def test_product_schema_pair_and_links():
    assert schemas.ProductDetailsSchema().load({"product": "15235546.23326616342"}) == \
        {"product": "15235546.23326616342", "country": "sg"}
    assert schemas.ProductDetailsSchema().load({"product": "15235546/23326616342", "country": "TH"}) == \
        {"product": "15235546.23326616342", "country": "th"}
    # the link's own site wins over `country`
    loaded = schemas.ProductDetailsSchema().load(
        {"product": "https://shopee.com.br/Novo-iPhone-i.486926153.22192886389", "country": "sg"})
    assert loaded == {"product": "486926153.22192886389", "country": "br"}


@pytest.mark.parametrize("value", ["", "abc", "https://example.com/product/1/2", "https://shopee.sg/search?keyword=x"])
def test_product_schema_rejects(value):
    with pytest.raises(ValidationError) as e:
        schemas.ProductDetailsSchema().load({"product": value})
    assert "product" in e.value.messages


def test_product_schema_rejects_sibling_and_unknown_params():
    with pytest.raises(ValidationError):
        schemas.ProductDetailsSchema().load({"product": "1.2", "url": "https://shopee.sg/product/1/2"})
    with pytest.raises(ValidationError):
        schemas.ProductDetailsSchema().load({"product": "1.2", "country": "cl"})
    with pytest.raises(ValidationError):
        schemas.ProductDetailsSchema().load({})


def test_shop_schema():
    assert schemas.ShopSchema().load({"shop": "15235546"}) == {"shop": "15235546", "country": "sg"}
    assert schemas.ShopSchema().load({"shop": "LorealParisSG", "country": "my"}) == {"shop": "lorealparissg", "country": "my"}
    assert schemas.ShopSchema().load({"shop": "https://shopee.co.th/shop/146916334"}) == {"shop": "146916334", "country": "th"}
    assert schemas.ShopSchema().load({"shop": "https://shopee.sg/lorealparissg"}) == {"shop": "lorealparissg", "country": "sg"}
    with pytest.raises(ValidationError):
        schemas.ShopSchema().load({"shop": "https://shopee.sg/cart/"})
    with pytest.raises(ValidationError):
        schemas.ShopSchema().load({})


def test_shop_categories_and_reviews_schemas():
    loaded = schemas.ShopCategoriesSchema().load({"shop": "1", "page": "2"})
    assert loaded == {"shop": "1", "country": "sg", "page": 2}
    loaded = schemas.ShopReviewsSchema().load({"shop": "1"})
    assert loaded == {"shop": "1", "country": "sg", "rating": 5, "page": 1}
    loaded = schemas.ShopReviewsSchema().load({"shop": "1", "rating": "3", "page": "4"})
    assert loaded["rating"] == 3 and loaded["page"] == 4
    with pytest.raises(ValidationError) as e:
        schemas.ShopReviewsSchema().load({"shop": "1", "rating": "6"})
    assert "rating" in e.value.messages
    with pytest.raises(ValidationError):
        schemas.ShopReviewsSchema().load({"shop": "1", "page": "0"})


def test_simple_market_schemas():
    assert schemas.CategoriesListSchema().load({}) == {"country": "sg"}
    assert schemas.CategoriesListSchema().load({"country": "id"}) == {"country": "id"}
    assert schemas.TrendingSearchesSchema().load({"country": "Vn"}) == {"country": "vn"}
    assert schemas.TrendingProductsSchema().load({}) == {"country": "sg"}
    assert schemas.OfficialShopsSchema().load({"page": "3"}) == {"country": "sg", "page": 3}
    with pytest.raises(ValidationError) as e:
        schemas.CategoriesListSchema().load({"country": "us"})
    assert "country" in e.value.messages


def test_autocomplete_schema():
    assert schemas.AutocompleteSchema().load({"query": " iphone "}) == {"query": "iphone", "country": "sg"}
    with pytest.raises(ValidationError):
        schemas.AutocompleteSchema().load({})
    with pytest.raises(ValidationError):
        schemas.AutocompleteSchema().load({"query": "x" * 101})


def test_flash_sale_schema():
    assert schemas.FlashSaleSchema().load({}) == {"country": "sg", "session": None, "category": None, "page": 1}
    loaded = schemas.FlashSaleSchema().load({"session": "513667598795255", "category": "17", "page": "2", "country": "my"})
    assert loaded == {"country": "my", "session": 513667598795255, "category": 17, "page": 2}
    with pytest.raises(ValidationError):
        schemas.FlashSaleSchema().load({"session": "abc"})
