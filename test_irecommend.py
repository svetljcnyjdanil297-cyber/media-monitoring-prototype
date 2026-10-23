import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright


SOURCE_URL = "https://irecommend.ru/content/sait-ozontravel-0"
OUTPUT_FILE = Path("data/irecommend.json")
MAX_REVIEWS = 10


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        try:
            page = browser.new_page()
            page.goto(
                SOURCE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )
            page.wait_for_timeout(2000)
            

            cards = page.locator(".reviews-list-item")
            count = cards.count()

            print("Найдено карточек:", count)

            page_text = page.locator("body").inner_text()
            rating = re.search(
                r"Среднее:\s*([\d.,]+)\s*\((\d+)\s*голос",
                page_text,
                re.IGNORECASE
            )

            reviews = []

            for card in cards.all()[:MAX_REVIEWS]:
                date_element = card.locator(".created")
                comments_element = card.locator(".comments")
                text_element = card.locator(".reviewTextSnippet")

                published_at = (
                    date_element.inner_text().strip()
                    if date_element.count() else None
                )

                lines = [
                    line.strip()
                    for line in card.inner_text().splitlines()
                    if line.strip()
                ]

                author = None
                if published_at in lines:
                    date_index = lines.index(published_at)
                    if date_index > 0:
                        author = lines[date_index - 1]

                review_text = (
                    text_element.inner_text().strip()
                    if text_element.count() else None
                )

                href = (
                    text_element.get_attribute("href")
                    if text_element.count() else None
                )

                comments = (
                    comments_element.inner_text().strip()
                    if comments_element.count() else None
                )

                reviews.append({
                    "source_name": "iRecommend",
                    "source_type": "review",
                    "url": urljoin(SOURCE_URL, href) if href else SOURCE_URL,
                    "title": review_text,
                    "text": review_text,
                    "author": author,
                    "published_at": published_at,
                    "comments_count": comments,
                    "collected_at": datetime.now(
                        timezone.utc
                    ).isoformat()
                })
            # Загружаем полные тексты отзывов
            for review in reviews:
                try:
                    page.goto(
                        review["url"],
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    full_text = page.locator(
                        ".description.hasinlineimage"
                    ).first.inner_text(timeout=5000).strip()

                    if full_text:
                        review["text"] = full_text
                        review["text_type"] = "full"

                except Exception as error:
                    review["text_type"] = "snippet"
                    print("Не удалось загрузить полный отзыв:", error)
            result = {
                "source_name": "iRecommend",
                "source_url": SOURCE_URL,
                "site_rating": rating.group(1) if rating else None,
                "rating_votes": int(rating.group(2)) if rating else None,
                "retrieved_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "reviews_found": count,
                "reviews_processed": len(reviews),
                "reviews": reviews
            }

            OUTPUT_FILE.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            with OUTPUT_FILE.open("w", encoding="utf-8") as file:
                json.dump(
                    result,
                    file,
                    ensure_ascii=False,
                    indent=2
                )

            print("Обработано отзывов:", len(reviews))
            print("Общая оценка сайта:", result["site_rating"])
            print("Количество голосов:", result["rating_votes"])
            print("Сохранено:", OUTPUT_FILE.resolve())

        finally:
            browser.close()


if __name__ == "__main__":
    main()