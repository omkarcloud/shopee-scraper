# 🛍️ Shopee Scraper

Shopee Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Shopee data for free.

## ✨ What Can I Get?

- 🛍️ **Full product listings across 9 Shopee markets** — title, description, images, variations, SKUs, attributes & shop
- ⚡ **Live flash-sale deals, 50 per page** — price, original price, discount, stock left & units sold
- 🏪 **Complete shop profiles & buyer reviews** — rating breakdown, followers, response rate, vouchers & review text
- 🔥 **What's hot right now** — 100 trending products with live prices, trending searches, autocomplete & the full category tree

## 🎥 Example: A Full Shopee Product

```json
{
  "id": 45964140630,
  "shop_id": 1887840381,
  "name": "Pandora Moments Sparkling Infinity Heart Collier Necklace",
  "link": "https://shopee.sg/product/1887840381/45964140630",
  "status": "normal",
  "condition": "new",
  "brand": { "id": 1146872, "name": "PANDORA" },
  "currency": "SGD",
  "description": "The ultimate symbol of eternal love. This sparkling sterling silver pendant features an openwork heart motif set with sparkling cubic zirconia. An asymmetric infinity sign is entwined around the heart, creating a three-dimensional look.",
  "images": [
    "https://down-sg.img.susercontent.com/file/sg-11134207-8258f-mqq0ip3m1p8re1",
    "https://down-sg.img.susercontent.com/file/sg-11134207-825bd-mqq0ip3z01se6d"
  ],
  "variations": [
    { "name": "Length", "options": [{ "name": "50cm", "image": null }] }
  ],
  "models": [
    { "id": 371217182931, "name": "50cm", "option_indexes": [0], "estimated_delivery_days": 1, "is_available": true }
  ],
  "attributes": [
    { "id": 100134, "name": "Material", "value": "Silver" },
    { "id": 100169, "name": "Style", "value": "Casual, Elegant" },
    { "id": 100037, "name": "Region of Origin", "value": "Denmark" }
  ],
  "categories": [
    { "id": 11013142, "name": "Fine Jewellery", "link": "https://shopee.sg/Fine-Jewellery-cat.11013142" },
    { "id": 11013148, "name": "Necklaces & Pendants", "link": "https://shopee.sg/Necklaces-Pendants-cat.11013148" }
  ],
  "services": [
    { "title": "100% Authentic", "description": "Shopee Mall products are guaranteed 100% authentic, and are sourced directly from brands and authorised distributors." }
  ],
  "shipping": { "is_free_shipping": false, "estimated_delivery_days": 1, "ships_from": "SG" },
  "is_official_shop": true,
  "listed_at": "2026-07-16T09:35:17Z",
  "shop": {
    "id": 1887840381,
    "name": "Pandora Official Store",
    "username": "pandora_singapore",
    "rating": { "average": 4.94, "count": 276, "good": 275, "normal": 1, "bad": 0 },
    "followers_count": 1271,
    "items_count": 234,
    "response_rate_percent": 99
  }
}
```

*Trimmed for readability.*

Shopee shows live prices, stock and sales only to logged-in shoppers, so Product Details carries the listing itself. You get live prices, discounts, stock and units sold from **Flash Sale Deals** and **Trending Products**.

## 🚀 Unlimited Free Shopee Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/shopee-scraper
cd shopee-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/products/details?product=1887840381.45964140630"
```

```json
{
  "id": 45964140630,
  "shop_id": 1887840381,
  "name": "Pandora Moments Sparkling Infinity Heart Collier Necklace",
  "link": "https://shopee.sg/product/1887840381/45964140630",
  "condition": "new",
  "brand": { "id": 1146872, "name": "PANDORA" },
  "currency": "SGD",
  "images": [
    "https://down-sg.img.susercontent.com/file/sg-11134207-8258f-mqq0ip3m1p8re1",
    "https://down-sg.img.susercontent.com/file/sg-11134207-825bd-mqq0ip3z01se6d"
  ],
  "variations": [{ "name": "Length", "options": [{ "name": "50cm", "image": null }] }],
  "attributes": [
    { "id": 100134, "name": "Material", "value": "Silver" },
    { "id": 100195, "name": "Necklace Length", "value": "Long" }
  ],
  "shop": {
    "id": 1887840381,
    "name": "Pandora Official Store",
    "username": "pandora_singapore",
    "rating": { "average": 4.94, "count": 276, "good": 275, "normal": 1, "bad": 0 },
    "followers_count": 1271
  }
}
```

All 10 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

10 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Product Details | `/products/details` | Everything about one listing: description, images, SKUs, attributes, shop |
| Flash Sale Deals | `/deals/flash-sale` | 50 live deals per page with price, discount, stock and sales |
| Trending Products | `/products/trending` | 100 trending products with live prices and ratings |
| Shop Details | `/shops/details` | Rating breakdown, followers, response rate and live vouchers |
| Shop Reviews | `/shops/reviews` | Buyer reviews per star rating with photos and seller replies |
| Shop Categories | `/shops/categories` | A shop's own categories with item counts |
| Official Stores | `/shops/official` | Every official brand store in a market |
| Autocomplete | `/search/autocomplete` | Shopee's own search suggestions for any partial query |
| Trending Searches | `/search/trending` | What shoppers are searching for right now |
| Categories | `/categories/list` | The full category tree with IDs and links |

Every endpoint takes a `country` parameter: `sg`, `my`, `th`, `vn`, `ph`, `id`, `tw`, `br` or `mx`.

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-shopee-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-shopee-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-shopee-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/products/details",
    params={"product": "1887840381.45964140630"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Shopee Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Shopee%20Scraper%20API.)

[![Ask Us by Email about Shopee Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Shopee%20Scraper%20API&body=I%20need%20help%20using%20the%20Shopee%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/shopee-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/shopee-scraper)
