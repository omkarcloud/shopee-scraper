"""Cache TTL per /shopee/* endpoint (cache.py, keyed on the validated
params). All of Shopee's open surfaces are catalog-ish data that moves on
the seller's / the platform's schedule, so hours of caching never serve a
materially stale record; the two promotion feeds turn over fastest.
"""
from datetime import timedelta

# The server-rendered product copy carries no price/stock, so only the
# listing itself (title, images, variations) can change — rarely.
PRODUCT_CACHE = timedelta(hours=6)
# Shop profile (ratings, followers, item count) drifts slowly; vouchers
# ride along in the same response and are valid for days.
SHOP_CACHE = timedelta(hours=6)
# A shop's own category tabs change when the seller reorganises.
SHOP_CATEGORIES_CACHE = timedelta(hours=12)
# New reviews land continuously on big shops; an hour keeps page 1 fresh.
SHOP_REVIEWS_CACHE = timedelta(hours=1)
# The site-wide category tree changes a few times a year.
CATEGORY_TREE_CACHE = timedelta(hours=24)
# Autocomplete suggestions are search-engine output; stable within a day.
AUTOCOMPLETE_CACHE = timedelta(hours=6)
# Trending searches refresh on the site every few minutes (refresh_interval_sec 360).
TRENDING_SEARCHES_CACHE = timedelta(minutes=30)
# Flash-sale sessions last 2-6 h; stock and sold counts move during one.
FLASH_SALE_CACHE = timedelta(minutes=10)
# The homepage feed is re-ranked continuously; prices in it are live.
TRENDING_PRODUCTS_CACHE = timedelta(minutes=30)
# The official-store directory grows slowly.
OFFICIAL_SHOPS_CACHE = timedelta(hours=24)
