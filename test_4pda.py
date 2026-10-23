import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright


SOURCE_URL = "https://4pda.to/forum/index.php?showforum=320"
OUTPUT_FILE = Path("data/4pda.json")
MAX_TOPICS = 10


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    articles = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        try:
            page = browser.new_page()

            # Загружаем список тем форума
            response = page.goto(
                SOURCE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(2000)

            if response is None or response.status != 200:
                print("Не удалось загрузить раздел 4PDA.")
                return

            # Получаем ссылки на темы, исключая меню и пагинацию
            links = page.locator(
                'a[href*="showtopic="]'
            ).evaluate_all("""
                elements => elements.map(a => ({
                    title: (a.innerText || a.textContent || '')
                        .replace(/\\s+/g, ' ').trim(),
                    url: a.href
                }))
            """)

            topics = []
            seen_ids = set()

            for item in links:
                title = item["title"]
                parsed = urlparse(item["url"])
                params = parse_qs(parsed.query)

                topic_ids = params.get("showtopic", [])
                if not topic_ids:
                    continue

                topic_id = topic_ids[0]

                if (
                    params.get("st")
                    or params.get("view")
                    or params.get("utm_source")
                ):
                    continue

                if len(title) < 10 or title.isdigit():
                    continue

                if topic_id in seen_ids:
                    continue

                seen_ids.add(topic_id)

                topic_url = (
                    f"https://4pda.to/forum/index.php"
                    f"?showtopic={topic_id}"
                )

                topics.append({
                    "title": title,
                    "url": topic_url
                })

            print("Найдено тем:", len(topics))

            # Открываем отдельные темы
            for index, topic in enumerate(
                topics[:MAX_TOPICS], 1
            ):
                print(
                    f"[{index}/{min(len(topics), MAX_TOPICS)}] "
                    f"{topic['title']}"
                )

                try:
                    response = page.goto(
                        topic["url"],
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    page.wait_for_timeout(1000)

                    if response is None or response.status != 200:
                        print("  Не удалось загрузить тему")
                        continue

                    posts = page.locator(".postcolor")
                    authors = page.locator(".normalname")

                    if posts.count() == 0:
                        print("  Первое сообщение не найдено")
                        continue

                    page_text = page.locator("body").inner_text()

                    date_match = re.search(
                        r"\b\d{2}\.\d{2}\.\d{2,4},\s*\d{2}:\d{2}\b",
                        page_text
                        )

                    article = {
                        "source_name": "4PDA",
                        "source_type": "forum",
                        "url": topic["url"],
                        "title": page.title().replace(
                            " - 4PDA", ""
                        ),
                        "text": posts.nth(0).inner_text().strip(),
                        "author": (
                            authors.nth(0).inner_text().strip()
                            if authors.count()
                            else None
                        ),
                        "published_at": (
                            date_match.group(0)
                            if date_match
                            else None
                        ),
                        "collected_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                        "status": "success"
                    }

                    articles.append(article)

                except Exception as error:
                    print("  Ошибка:", error)

            result = {
                "source_name": "4PDA",
                "source_url": SOURCE_URL,
                "retrieved_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "topics_found": len(topics),
                "topics_processed": len(articles),
                "articles": articles
            }

            with OUTPUT_FILE.open(
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    result,
                    file,
                    ensure_ascii=False,
                    indent=2
                )

            print("\nСбор завершён.")
            print("Обработано тем:", len(articles))
            print("Файл:", OUTPUT_FILE.resolve())

        finally:
            browser.close()


if __name__ == "__main__":
    main()