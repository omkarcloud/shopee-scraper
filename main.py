"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json.
"""
import json
import os

from shopee.api import deals_flash_sale, product_details, shop_details

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # "<shop_id>.<item_id>" from any Shopee product link (…-i.<shop_id>.<item_id>)
    save("product_pandora_necklace.json", product_details(country="sg", product="1887840381.45964140630"))

    # the flash sale running now: 50 deals per page with price, discount, stock and units sold
    save("flash_sale_sg.json", deals_flash_sale(country="sg", session=None, category=None, page=1))

    # a shop by username or numeric id: ratings, followers, vouchers
    save("shop_apple.json", shop_details(country="sg", shop="apple.flagshipstore"))
