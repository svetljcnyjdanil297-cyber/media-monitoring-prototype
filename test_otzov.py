import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright


URL = "https://otzovik.com/money_systems/banks/"
OUTPUT_FILE = Path("data/otzovik.json")

MAX_OBJECTS = 3
MAX_REVIEWS = 3


def main():
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)

        try:
            page = browser.new_page()

            # 1. Загружаем раздел банков
            response = page.goto(
                URL,
                wait_until="domcontentloaded",
                timeout=60000
            )

            page.wait_for_timeout(1500)

            print(
                "HTTP-код раздела:",
                response.status if response else None
            )

            if response is None or response.status != 200:
                print("Не удалось загрузить раздел банков.")
                return

            # 2. Собираем ссылки на страницы объектов
            links = page.locator(
                'a[href*="/reviews/"]'
            ).evaluate_all("""
                elements => elements.map(a => ({
                    title: (a.innerText || '').trim(),
                    url: a.href
                }))
            """)

            objects = []
            seen_objects = set()

            for item in links:
                url = item["url"].split("#")[0]

                if (
                    "/reviews/" in url
                    and url not in seen_objects
                    and item["title"]
                    and item["title"] != "Добавить отзыв"
                ):
                    seen_objects.add(url)

                    objects.append({
                        "title": item["title"],
                        "url": url
                    })

            print("Найдено объектов с отзывами:", len(objects))

            # 3. Собираем ссылки на отдельные рецензии
            unique_reviews = {}

            for obj in objects[:MAX_OBJECTS]:
                print("Проверяем объект:", obj["title"][:100])

                try:
                    page.goto(
                        obj["url"],
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    page.wait_for_timeout(700)

                    review_links = page.locator(
                        'a[href*="/review_"]'
                    ).evaluate_all("""
                        elements => elements.map(a => ({
                            title: (a.innerText || '').trim(),
                            url: a.href
                        }))
                    """)

                    for item in review_links:
                        review_url = (
                            item["url"].split("#")[0].split("?")[0]
                        )

                        if re.search(
                            r"/review_\d+\.html$",
                            review_url
                        ):
                            unique_reviews.setdefault(
                                review_url,
                                item["title"]
                            )

                    if len(unique_reviews) >= MAX_REVIEWS:
                        break

                except Exception as error:
                    print("Не удалось открыть объект:", error)

            print(
                "\nНайдено уникальных отзывов:",
                len(unique_reviews)
            )

            # 4. Открываем отдельные отзывы и извлекаем данные
            collected = []

            for index, (review_url, link_title) in enumerate(
                list(unique_reviews.items())[:MAX_REVIEWS],
                start=1
            ):
                try:
                    response = page.goto(
                        review_url,
                        wait_until="domcontentloaded",
                        timeout=60000
                    )

                    page.wait_for_timeout(500)

                    if response is None or response.status != 200:
                        print(f"[{index}] Не удалось загрузить отзыв")
                        continue

                    body = page.locator("body").inner_text()

                    lines = [
                        line.strip()
                        for line in body.splitlines()
                        if line.strip()
                    ]

                    # Автор: обычно расположен перед строкой «Репутация»
                    author = None

                    if "Репутация" in lines:
                        author_index = lines.index("Репутация")

                        if author_index > 0:
                            author = lines[author_index - 1]

                    # Дата публикации
                    date_match = re.search(
                        r"\b\d{1,2}\s+[А-Яа-яЁё]+\s+\d{4}\b",
                        body,
                        re.IGNORECASE
                    )

                    # Оценка, указанная непосредственно в поле «Моя оценка»
                    rating_match = re.search(
                        r"Моя оценка\s*([1-5](?:[.,]\d)?)",
                        body,
                        re.IGNORECASE
                    )

                    # Извлекаем текст отзыва без нижнего блока комментариев
                    start = body.find("Отзыв: ")
                    end = body.find("Комментарии к отзыву", start)

                    if start != -1:
                        if end == -1:
                            end = len(body)

                        review_text = body[start:end].strip()
                    else:
                        review_text = None

                    article = {
                        "source_name": "Otzovik",
                        "source_type": "bank_review",
                        "url": review_url,
                        "title": page.title(),
                        "review_title": link_title,
                        "author": author,
                        "published_at": (
                            date_match.group(0)
                            if date_match else None
                        ),
                        "rating": (
                            rating_match.group(1)
                            if rating_match else None
                        ),
                        "text": review_text,
                        "collected_at": datetime.now(
                            timezone.utc
                        ).isoformat(),
                        "status": (
                            "success" if review_text else "partial"
                        )
                    }

                    collected.append(article)

                    print(
                        f"[{index}] Собран отзыв:",
                        article["review_title"] or article["title"]
                    )

                except Exception as error:
                    print(f"[{index}] Ошибка:", error)

            # 5. Сохраняем результат после обработки всех отзывов
            result = {
                "source_name": "Otzovik",
                "source_url": URL,
                "retrieved_at": datetime.now(
                    timezone.utc
                ).isoformat(),
                "objects_found": len(objects),
                "reviews_found": len(unique_reviews),
                "reviews_processed": len(collected),
                "reviews": collected
            }

            with OUTPUT_FILE.open("w", encoding="utf-8") as file:
                json.dump(
                    result,
                    file,
                    ensure_ascii=False,
                    indent=2
                )

            print("\nСбор завершён.")
            print("Обработано отзывов:", len(collected))
            print("Файл:", OUTPUT_FILE.resolve())

        finally:
            browser.close()


if __name__ == "__main__":
    main()