import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


SOURCE_URL = "https://dzen.ru/news/rubric/computers"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Referer": "https://dzen.ru/",
    }


def clean_text(value):
    """Убирает лишние пробелы."""
    return re.sub(r"\s+", " ", value or "").strip()


def main():
    print("Проверяем источник Dzen...")
    print("Адрес:", SOURCE_URL)

    try:
        response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=20,
        allow_redirects=False
        )
        print("Первоначальный HTTP-код:", response.status_code)
        print("Адрес перенаправления:", response.headers.get("Location"))
        print("Заголовок проверки:", response.headers.get("X-Yandex-Captcha"))
        print("\nHTTP-код:", response.status_code)
        print("Фактический адрес:", response.url)
        print(
            "Тип содержимого:",
            response.headers.get("Content-Type")
        )
        print("Размер HTML:", len(response.text), "символов")

    except requests.RequestException as error:
        print("Ошибка загрузки:", error)
        return

    soup = BeautifulSoup(response.text, "lxml")

    # Проверяем заголовок страницы
    page_title = (
        clean_text(soup.title.get_text())
        if soup.title
        else None
    )

    print("\nЗаголовок страницы:", page_title)

    # Смотрим, какой текст вообще пришёл от сайта
    page_text = clean_text(
        soup.get_text(" ", strip=True)
    )

    print("Длина текста страницы:", len(page_text))
    print("\nНачало текста страницы:")
    print(page_text[:1000])

    # Ищем ссылки, которые могут вести на новости
    candidates = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        href = urljoin(response.url, link["href"])
        label = clean_text(link.get_text(" ", strip=True))

        if not label or len(label) < 25:
            continue

        if href in seen_urls:
            continue

        parsed = urlparse(href)

        if parsed.scheme not in ("http", "https"):
            continue

        # Отбираем ссылки на статьи Dzen
        # и внешние публикации с содержательными заголовками
        is_dzen_article = (
            parsed.netloc.lower().endswith("dzen.ru")
            and (
                parsed.path.startswith("/a/")
                or parsed.path.startswith("/news/")
            )
        )

        is_external_article = (
            parsed.netloc
            and not parsed.netloc.lower().endswith("dzen.ru")
        )

        if is_dzen_article or is_external_article:
            seen_urls.add(href)
            candidates.append((label, href))

    print("\nНайдено возможных ссылок на публикации:", len(candidates))
    print("\nПервые 20 ссылок:")

    for index, (label, href) in enumerate(candidates[:20], 1):
        print(f"\n{index}. {label}")
        print(href)

    # Проверяем, есть ли в HTML признаки структурированных данных
    html_lower = response.text.lower()

    print("\nДополнительная диагностика:")
    for marker in [
        "application/ld+json",
        "__next_data__",
        "__initial_state__"
    ]:
        print(f"{marker}: {marker in html_lower}")


if __name__ == "__main__":
    main()