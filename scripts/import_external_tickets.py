from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


SOURCE_REPO = "https://github.com/etspring/pdd_russia.git"

TOPIC_MAP = {
    "Сигналы светофора и регулировщика": ["controller_signals", "traffic_lights"],
    "Проезд перекрестков": ["priority_rules"],
    "Дорожная разметка": ["road_markings"],
    "Остановка и стоянка": ["stopping_parking"],
    "Пешеходные переходы и места остановок маршрутных транспортных средств": ["pedestrians"],
    "Приоритет маршрутных транспортных средств": ["pedestrians"],
    "Движение через железнодорожные пути": ["railroad"],
    "Оказание доврачебной медицинской помощи": ["first_aid"],
    "Дорожные знаки": ["priority_rules"]
}

TOPIC_KEYWORDS = [
    (("регулировщик", "сигнал регулировщика", "жест"), ["controller_signals"]),
    (("светофор", "дополнительная секция", "реверсив"), ["traffic_lights"]),
    (("разметка", "сплошн", "прерывист", "стоп-линия"), ["road_markings"]),
    (("остановка", "стоянка", "парков"), ["stopping_parking"]),
    (("пешеход", "маршрутн", "автобус"), ["pedestrians"]),
    (("железнодорож", "переезд", "шлагбаум"), ["railroad"]),
    (("медицин", "доврачеб", "первая помощь", "пострадавш"), ["first_aid"]),
    (("обгон", "опережение", "разъезд", "маневр", "перекрест", "приоритет", "скорост", "обязанности водител", "движения", "расположение"), ["priority_rules"]),
]


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    content_dir = project_root / "content" / "generated"
    assets_dir = project_root / "assets" / "imported"
    content_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="pdd_source_") as tmp_dir:
        repo_dir = Path(tmp_dir) / "pdd_russia"
        subprocess.run(["git", "clone", "--depth", "1", SOURCE_REPO, str(repo_dir)], check=True)
        questions = load_questions(repo_dir)
        with (content_dir / "imported_questions.json").open("w", encoding="utf-8") as fh:
            json.dump(questions, fh, ensure_ascii=False, indent=2)
        copy_images(repo_dir, assets_dir)
    print(f"Imported {len(questions)} questions into {content_dir / 'imported_questions.json'}")
    return 0


def load_questions(repo_dir: Path) -> list[dict[str, object]]:
    tickets_dir = repo_dir / "questions" / "A_B" / "tickets"
    results: list[dict[str, object]] = []
    for file_path in sorted(tickets_dir.glob("*.json")):
        ticket_id = file_path.stem
        raw_items = json.loads(file_path.read_text(encoding="utf-8"))
        for item in raw_items:
            topic_ids = map_topics(item.get("topic", []), item.get("question", ""))
            answers = item.get("answers", [])
            correct_index = next((idx for idx, answer in enumerate(answers) if answer.get("is_correct")), None)
            if correct_index is None:
                continue
            image_ref = item.get("image")
            results.append(
                {
                    "id": item["id"],
                    "topic_ids": topic_ids,
                    "prompt": item["question"].strip(),
                    "options": [answer["answer_text"].strip() for answer in answers],
                    "correct_index": correct_index,
                    "explanation": item.get("answer_tip") or item.get("correct_answer") or "Смотри текст ПДД по теме.",
                    "source": "etspring/pdd_russia",
                    "exam_ticket": ticket_id,
                    "image_path": normalize_image_path(image_ref),
                    "remedy_image_path": infer_remedy_image(item["question"], topic_ids),
                }
            )
    return results


def map_topics(raw_topics: list[str], question_text: str = "") -> list[str]:
    result: list[str] = []
    normalized_text = " ".join(raw_topics + [question_text]).lower().replace("ё", "е")
    for raw_topic in raw_topics:
        for mapped in TOPIC_MAP.get(raw_topic, []):
            if mapped not in result:
                result.append(mapped)
    for keywords, mapped_ids in TOPIC_KEYWORDS:
        if any(keyword in normalized_text for keyword in keywords):
            for mapped in mapped_ids:
                if mapped not in result:
                    result.append(mapped)
    if not result:
        for raw_topic in raw_topics:
            if raw_topic:
                fallback = f"external_{slugify(raw_topic)}"
                if fallback not in result:
                    result.append(fallback)
    return result


def slugify(value: str) -> str:
    lowered = value.lower().replace("ё", "е")
    cleaned = re.sub(r"[^a-zа-я0-9]+", "_", lowered)
    return cleaned.strip("_")


def normalize_image_path(image_ref: str | None) -> str | None:
    if not image_ref:
        return None
    cleaned = image_ref.replace("./images/", "").replace("\\", "/")
    return f"imported/{cleaned}"


def infer_remedy_image(question_text: str, topic_ids: list[str]) -> str | None:
    text = question_text.lower().replace("ё", "е")

    if "регулировщик" in text or "рука поднята" in text or "руки в стороны" in text:
        if "рука поднята" in text or "поднята вверх" in text:
            return "lessons/controller_slide_1.png"
        if "руки в стороны" in text or "опущены" in text:
            return "lessons/controller_slide_2.png"
        if "правая рука" in text or "вытянута вперед" in text:
            return "lessons/controller_slide_3.png"
        return "lessons/controller_slide_3.png"

    if "светофор" in text or "дополнительн" in text or "стрелк" in text:
        if "дополнительн" in text or "стрелк" in text:
            return "lessons/traffic_lights_slide_2.png"
        return "lessons/traffic_lights_slide_1.png"

    if "главн" in text or "уступить дорогу" in text or "перекрест" in text or "помех" in text:
        if "помех" in text or "регулировщик" in text:
            return "lessons/priority_slide_1.png"
        if "главн" in text or "уступить дорогу" in text:
            return "lessons/priority_slide_2.png"
        if "налево" in text or "разворот" in text or "встречн" in text:
            return "lessons/priority_slide_3.png"
        return "lessons/priority_slide_1.png"

    if "разметк" in text or "сплошн" in text or "прерывист" in text or "стоп-лини" in text:
        if "стоп-лини" in text or "приближ" in text:
            return "lessons/markings_slide_2.png"
        return "lessons/markings_slide_1.png"

    if "останов" in text or "стоянк" in text:
        if "5 м" in text or "пешеходн" in text or "перекрест" in text:
            return "lessons/stopping_slide_1.png"
        return "lessons/stopping_slide_2.png"

    if "пешеход" in text or "маршрутн" in text or "автобус" in text or "остановк" in text:
        if "маршрутн" in text or "автобус" in text:
            return "lessons/pedestrians_slide_2.png"
        return "lessons/pedestrians_slide_1.png"

    if "железнодорож" in text or "переезд" in text or "шлагбаум" in text or "рельс" in text:
        if "10 м" in text or "5 м" in text or "рельс" in text:
            return "lessons/railroad_slide_2.png"
        return "lessons/railroad_slide_1.png"

    if "первая помощь" in text or "кровотеч" in text or "пострадавш" in text or "дыхани" in text:
        if "перемещ" in text or "извлеч" in text:
            return "lessons/first_aid_slide_2.png"
        return "lessons/first_aid_slide_1.png"

    for topic_id in topic_ids:
        fallback = {
            "controller_signals": "lessons/controller_slide_3.png",
            "traffic_lights": "lessons/traffic_lights_slide_1.png",
            "priority_rules": "lessons/priority_slide_1.png",
            "road_markings": "lessons/markings_slide_1.png",
            "stopping_parking": "lessons/stopping_slide_1.png",
            "pedestrians": "lessons/pedestrians_slide_1.png",
            "railroad": "lessons/railroad_slide_1.png",
            "first_aid": "lessons/first_aid_slide_1.png",
        }.get(topic_id)
        if fallback:
            return fallback
    return None


def copy_images(repo_dir: Path, assets_dir: Path) -> None:
    source_images = repo_dir / "images"
    if not source_images.exists():
        return
    target = assets_dir
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source_images, target)


if __name__ == "__main__":
    raise SystemExit(main())
