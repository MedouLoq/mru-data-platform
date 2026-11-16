"""README screenshots from a running instance.

    python manage.py runserver 8010 &
    python scripts/screenshots.py http://127.0.0.1:8010 <user> <password>
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"
URL, USER, PASSWORD = sys.argv[1:4]

PAGES = [
    ("/", "dashboard.png"),
    ("/asset/GOLD/?days=730", "asset_gold.png"),
    ("/comparison/?assets=EUR&assets=USD&days=365", "comparison.png"),
    ("/statistics/", "statistics.png"),
    ("/calculator/", "calculator.png"),
    ("/predictions/", "predictions.png"),
    ("/admin/operations/", "admin_operations.png"),
]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page.goto(URL + "/login/")
        page.screenshot(path=OUT / "login.png")
        page.fill("input[name=username]", USER)
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit], input[type=submit]")
        page.wait_for_load_state("networkidle")
        for path, name in PAGES:
            page.goto(URL + path)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(1500)  # Plotly animations
            page.screenshot(path=OUT / name)
            if name == "predictions.png":   # second crop: the per-asset metrics and forecast chart
                box = page.locator(".asset-panel.active").bounding_box()
                page.screenshot(path=OUT / "predictions_panel.png", full_page=True,
                                clip={"x": 0, "y": box["y"] - 24, "width": 1440, "height": min(box["height"] + 48, 1100)})
        browser.close()
    print("Saved:", *sorted(x.name for x in OUT.iterdir()), sep="\n  ")


if __name__ == "__main__":
    main()
