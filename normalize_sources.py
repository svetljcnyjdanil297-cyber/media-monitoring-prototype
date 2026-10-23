import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import hashlib

DATA_DIR = Path("data")

OUTPUT_JSON = DATA_DIR / "normalized_articles.json"
OUTPUT_CSV = DATA_DIR / "normalized_articles.csv"
OUTPUT_SUMMARY = DATA_DIR / "source_summary.json"

# Файлы с результатами сбора
SOURCE_FILES = {
    "5koleso": ["5koleso.json"],
    "irecommend": ["irecommend.json"],
    "4pda": ["4pda.json"],
    "otzovik": ["otzovik_sample.json", "otzovik.json"],
    "drive2": ["drive2.json"],
    "dzen": ["dzen.json", "dzen_computers.json"],
}

# Информация об источниках
SOURCE_INFO = {
    "5koleso": {
        "name": "5 Колесо — LiveJournal",
        "url": "https://5koleso.livejournal.com/",
        "class": "Блог",
    },
    "irecommend": {
        "name": "iRecommend",
        "url": "https://irecommend.ru/content/sait-ozontravel-0",
        "class": "Сайт отзывов",
    },
    "dzen": {
        "name": "Дзен — компьютеры",
        "url": "https://dzen.ru/news/rubric/computers",
        "class": "Новостной агрегатор",
    },
    "4pda": {
        "name": "4PDA — форум",
        "url": "https://4pda.to/forum/index.php?showforum=320",
        "class": "Форум",
    },
    "otzovik": {
        "name": "Отзовик — банки",
        "url": "https://otzovik.com/money_systems/banks/",
        "class": "Сайт отзывов",
    },
    "drive2": {
        "name": "Drive2 — публикации",
        "url": "https://www.drive2.ru/featured-topics/CVQ0gEAAcHQ/",
        "class": "Автомобильное сообщество",
    },
}

# Возможные названия полей в исходных файлах
FIELD_ALIASES = {
    "url": [
        "url", "link", "article_url", "review_url", "href"
    ],
    "title": [
        "title", "heading", "topic", "name", "subject"
    ],
    "text": [
        "text", "full_text", "content", "body",
        "review", "description", "text_full"
    ],
    "author": [
        "author", "author_name", "username",
        "user", "nickname", "login"
    ],
    "published_at": [
        "published_at", "date", "publication_date",
        "created_at", "published", "datetime", "timestamp"
    ],
    "rating": [
        "rating", "score", "stars", "grade", "оценка"
    ],
}

LIST_KEYS = [
    "articles", "reviews", "posts", "items",
    "results", "entries", "records"
]


def first_value(record, field_names):
    """Находит значение поля под одним из возможных названий."""
    for name in field_names:
        value = record.get(name)

        if value not in (None, "", [], {}):
            if isinstance(value, (str, int, float, bool)):
                return value

            if isinstance(value, dict):
                return json.dumps(value, ensure_ascii=False)

            return str(value)

    return None


def get_records(payload):
    """Извлекает записи из JSON разных форматов."""
    if isinstance(payload, list):
        return payload, {}

    if not isinstance(payload, dict):
        return [], {}

    for key in LIST_KEYS:
        value = payload.get(key)

        if isinstance(value, list):
            return value, payload

        if isinstance(value, dict):
            for nested_key in LIST_KEYS:
                nested = value.get(nested_key)

                if isinstance(nested, list):
                    return nested, payload

    # Если сам JSON представляет собой одну публикацию
    possible_fields = [
        "text", "content", "body",
        "review", "full_text", "title", "url", "link"
    ]

    if any(field in payload for field in possible_fields):
        return [payload], payload

    return [], payload


def normalize_record(record, source_key, parent):
    """Приводит публикацию к общей структуре."""
    if not isinstance(record, dict):
        record = {"text": str(record)}

    info = SOURCE_INFO[source_key]

    normalized = {
        "source_key": source_key,
        "source_name": (
            record.get("source_name")
            or parent.get("source_name")
            or info["name"]
        ),
        "source_class": info["class"],
        "source_url": (
            parent.get("source_url") or info["url"]
        ),
        "url": first_value(record, FIELD_ALIASES["url"]),
        "title": first_value(record, FIELD_ALIASES["title"]),
        "text": first_value(record, FIELD_ALIASES["text"]),
        "author": first_value(record, FIELD_ALIASES["author"]),
        "published_at": first_value(
            record, FIELD_ALIASES["published_at"]
        ),
        "rating": first_value(record, FIELD_ALIASES["rating"]),
        "collected_at": (
            record.get("collected_at")
            or parent.get("retrieved_at")
        ),
        "status": record.get("status") or (
            "success"
            if first_value(record, FIELD_ALIASES["text"])
            else "partial"
        ),
        "source_file": None,
    }

    # Сохраняем дополнительные данные, если они есть
    known_fields = {
        alias
        for aliases in FIELD_ALIASES.values()
        for alias in aliases
    }

    known_fields.update({
        "source_name", "source_type", "source_url",
        "collected_at", "status", "http_status", "metadata"
    })

    extras = {
        key: value
        for key, value in record.items()
        if key not in known_fields
    }

    if record.get("metadata"):
        extras["metadata"] = record["metadata"]

    normalized["extra_metadata"] = extras or None

    return normalized


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    articles = []
    source_summary = []
    seen = set()
    seen_content = {}

    for source_key, candidates in SOURCE_FILES.items():
        info = SOURCE_INFO[source_key]

        existing = next(
            (
                DATA_DIR / name
                for name in candidates
                if (DATA_DIR / name).exists()
            ),
            None,
        )

        # Если выгрузки нет, фиксируем это в отчёте
        if existing is None:
            note = "JSON-файл источника не найден."

            if source_key == "dzen":
                note += (
                    " Ранее запрос перенаправлялся "
                    "на страницу авторизации."
                )

            source_summary.append({
                "source_key": source_key,
                "source_name": info["name"],
                "source_url": info["url"],
                "source_class": info["class"],
                "file": None,
                "status": "не собран",
                "note": note,
                "articles_in_file": 0,
                "articles_with_text": 0,
            })

            continue

        # Читаем JSON
        try:
            with existing.open("r", encoding="utf-8") as file:
                payload = json.load(file)

        except (OSError, json.JSONDecodeError) as error:
            source_summary.append({
                "source_key": source_key,
                "source_name": info["name"],
                "source_url": info["url"],
                "source_class": info["class"],
                "file": existing.name,
                "status": "ошибка чтения JSON",
                "note": str(error),
                "articles_in_file": 0,
                "articles_with_text": 0,
            })

            continue

        records, parent = get_records(payload)

        with_text = 0

        for record in records:
            item = normalize_record(
                record,
                source_key,
                parent,
            )

            item["source_file"] = existing.name

            if item.get("text"):
                with_text += 1

                        # Убираем повтор одной и той же ссылки
            url_identity = item.get("url")

            if url_identity and url_identity in seen:
                continue

            if url_identity:
                seen.add(url_identity)

            # Находим публикации с одинаковым содержимым
            title = " ".join(
                (item.get("title") or "").split()
            ).casefold()

            text = " ".join(
                (item.get("text") or "").split()
            ).casefold()

            fingerprint = None

            if title and text:
                fingerprint = hashlib.sha256(
                    f"{source_key}|{title}|{text}".encode("utf-8")
                ).hexdigest()

            if fingerprint and fingerprint in seen_content:
                item["duplicate_content"] = True
                item["duplicate_of"] = seen_content[fingerprint]
            else:
                item["duplicate_content"] = False
                item["duplicate_of"] = None

                if fingerprint:
                    seen_content[fingerprint] = (
                        item.get("url") or item.get("title")
                    )

            articles.append(item)
        source_summary.append({
            "source_key": source_key,
            "source_name": info["name"],
            "source_url": info["url"],
            "source_class": info["class"],
            "file": existing.name,
            "status": (
                "обработан"
                if records
                else "записи не найдены"
            ),
            "articles_in_file": len(records),
            "articles_with_text": with_text,
        })

    generated_at = datetime.now(timezone.utc).isoformat()

    # Сохраняем единый JSON
    with OUTPUT_JSON.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "retrieved_at": generated_at,
                "articles_count": len(articles),
                "articles": articles,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    # Сохраняем CSV для Excel
    columns = [
        "source_key", "source_name", "source_class",
        "source_url", "url", "title", "text",
        "author", "published_at", "rating",
        "collected_at", "status", "source_file",
        "extra_metadata",
    ]

    with OUTPUT_CSV.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=columns,
            extrasaction="ignore",
        )

        writer.writeheader()

        for item in articles:
            row = dict(item)

            if row.get("extra_metadata") is not None:
                row["extra_metadata"] = json.dumps(
                    row["extra_metadata"],
                    ensure_ascii=False,
                )

            writer.writerow(row)

    # Сохраняем отчёт по источникам
    with OUTPUT_SUMMARY.open("w", encoding="utf-8") as file:
        json.dump(
            {
                "generated_at": generated_at,
                "sources": source_summary,
            },
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("Объединение завершено.")
    print("Всего уникальных записей:", len(articles))
    print("JSON:", OUTPUT_JSON)
    print("CSV:", OUTPUT_CSV)
    print("Сводка:", OUTPUT_SUMMARY)

    print("\nИсточники:")

    for row in source_summary:
        print(
            f"- {row['source_name']}: "
            f"{row['status']} "
            f"({row['articles_with_text']}/"
            f"{row['articles_in_file']} записей с текстом)"
        )


if __name__ == "__main__":
    main()