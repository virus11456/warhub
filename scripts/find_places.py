"""
Place ID 查詢工具
=================

用途：幫你找出 fetch_data.py 裡 PIZZA_SHOPS 各家店的真實 Google Maps place_id。
查到之後，把結果貼回 scripts/fetch_data.py 的 PIZZA_SHOPS 列表中。

使用步驟：
1. 申請 Google Cloud API key（啟用 Places API）
2. export GOOGLE_MAPS_API_KEY=your_key_here
3. python scripts/find_places.py
4. 把輸出的 place_id 貼回 fetch_data.py
"""

import os
import sys
import requests

# 五角大廈座標
PENTAGON = (38.8719, -77.0563)

# 要搜尋的店家（與 fetch_data.py / index.html 一致）
SHOPS_TO_FIND = [
    "We The Pizza",
    "Pizzato Pizza",
    "Papa Johns Pizza",
    "Domino's Pizza",
    "Extreme Pizza",
    "District Pizza Palace",
]

SEARCH_RADIUS_M = 5000  # 五角大廈周邊 5km


def find_place_id(api_key: str, query: str, lat: float, lng: float) -> list[dict]:
    """用 Places API Text Search 查找最相關的場所"""
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {
        "query":    query,
        "location": f"{lat},{lng}",
        "radius":   SEARCH_RADIUS_M,
        "key":      api_key,
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") not in ("OK", "ZERO_RESULTS"):
        print(f"  ❌ API 錯誤: {data.get('status')} {data.get('error_message', '')}")
        return []
    return data.get("results", [])[:3]


def main():
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key:
        print("❌ 請先設定 GOOGLE_MAPS_API_KEY 環境變數")
        print("   export GOOGLE_MAPS_API_KEY=your_key_here")
        sys.exit(1)

    print("=" * 70)
    print(f"搜尋 Pentagon ({PENTAGON[0]}, {PENTAGON[1]}) 周邊 {SEARCH_RADIUS_M/1000:.0f} km 內的披薩店")
    print("=" * 70)

    snippets = []
    for shop_name in SHOPS_TO_FIND:
        print(f"\n🔍 {shop_name}")
        results = find_place_id(api_key, shop_name, *PENTAGON)
        if not results:
            print("  ⚠️  找不到結果")
            snippets.append(f'    {{"name": "{shop_name}", "place_id": "PLACE_ID_HERE", "baseline": 35}},  # NOT FOUND')
            continue

        for i, r in enumerate(results, 1):
            print(f"  [{i}] {r.get('name')}")
            print(f"      地址: {r.get('formatted_address', 'N/A')}")
            print(f"      place_id: {r.get('place_id')}")

        # 取第一個（最相關）
        top = results[0]
        snippets.append(
            f'    {{"name": "{shop_name}", '
            f'"place_id": "{top["place_id"]}", '
            f'"baseline": 35}},  # {top.get("name")} - {top.get("formatted_address", "")[:50]}'
        )

    print("\n" + "=" * 70)
    print("把以下內容貼到 scripts/fetch_data.py 的 PIZZA_SHOPS 列表：")
    print("=" * 70)
    print("PIZZA_SHOPS = [")
    for s in snippets:
        print(s)
    print("]")


if __name__ == "__main__":
    main()
