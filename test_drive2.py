import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright


SOURCE_URL = "https://www.drive2.ru/featured-topics/CVQ0gEAAcHQ/"
OUTPUT_FILE = Path("data/drive2.json")
MAX_ARTICLES = 10


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    articles = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        try:
            page = browser.new_page()

            response = page.goto(
                SOURCE_URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            if response is None or response.status != 200:
                print("Не удалось загрузить раздел Drive2.")
                return

            # Собираем ссылки на публикации
            links = page.locator('a[href*="/b/"]').evaluate_all("""
                elements => elements.map(a => ({
                    title: (a.innerText || '').trim(),
                    url: a.href
                }))
            """)

            posts = []
            seen = set()

            for item in links:
                url = item["url"].split("?")[0]

                if (
                    re.search(r"drive2\.ru/b/\d+/?$", url)
                    and len(item["title"]) >= 25
                    and url not in seen
                ):
                    seen.add(url)
                    posts.append({
                        "title": item["title"],
                        "url": url
                    })

            print("Найдено публикаций:", len(posts))

            
            date_pattern = re.compile(
                r"\b\d{1,2}\s+[А-Яа-яЁё]+\s+\d{4}\b"
            )

            for index, post in enumerate(posts[:MAX_ARTICLES], 1):
                print(f"[{index}/{min(len(posts), MAX_ARTICLES)}] {post['title'][:80]}")

                try:
                    response = page.goto(
                        post["url"],
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    if response is None or response.status != 200:
                        print("  Не удалось загрузить публикацию.")
                        continue

                    page.wait_for_timeout(500)

                    body = page.locator("body").inner_text()
                    lines = [
                        line.strip()
                        for line in body.splitlines()
                        if line.strip()
                    ]

                    h1 = page.locator("h1")
                    title = (
                        h1.first.inner_text().strip()
                        if h1.count()
                        else page.title().split(" — ")[0].strip()
                    )

                    # Находим дату после заголовка
                    title_index = next(
                        (
                            i for i, line in enumerate(lines)
                            if line == title
                        ),
                        -1
                    )

                    date_index = next(
                        (
                            i for i, line in enumerate(lines)
                            if date_pattern.search(line)
                            and i > title_index
                        ),
                        -1
                    )

                    published_at = (
                        lines[date_index]
                        if date_index != -1
                        else None
                    )

                    author = (
                        lines[date_index - 1]
                        if date_index > title_index + 1
                        else None
                    )

                    # Берём только основной текст публикации
                    content = page.locator(".c-post__body")

                    text = (
                        content.inner_text().strip()
                        if content.count()
                        else ""
                    )

                    articles.append({
                        "source_name": "DRIVE2",
                        "source_type": "automotive_publication",
                        "url": post["url"],
                        "title": title,
                        "author": author,
                        "published_at": published_at,
                        "text": text,
                        "collected_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                        "status": (
                            "success" if text else "partial"
                        )
                    })

                except Exception as error:
                    print("  Ошибка:", error)

                time.sleep(1)

            result = {
                "source_name": "DRIVE2",
                "source_url": SOURCE_URL,
                "retrieved_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "articles_found": len(posts),
                "articles_processed": len(articles),
                "articles": articles
            }

            with OUTPUT_FILE.open("w", encoding="utf-8") as file:
                json.dump(
                    result,
                    file,
                    ensure_ascii=False,
                    indent=2
                )

            print("\\nСбор завершён.")
            print("Обработано публикаций:", len(articles))
            print("Файл:", OUTPUT_FILE.resolve())

        finally:
            browser.close()


if __name__ == "__main__":
    main()