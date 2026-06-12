from __future__ import annotations

import subprocess
from pathlib import Path


W = 1400
H = 1000
FONT = "DejaVu Sans"


def wrap_svg(title: str, body: str, bg: str = "#f5f2ea") -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
  <rect width="{W}" height="{H}" fill="{bg}"/>
  <text x="{W//2}" y="78" text-anchor="middle" font-family="{FONT}" font-size="42" font-weight="700" fill="#1f2b33">{title}</text>
  {body}
</svg>
"""


def text_block(x: int, y: int, lines: list[str], size: int = 26, fill: str = "#1f2b33", anchor: str = "start") -> str:
    out = []
    for index, line in enumerate(lines):
        out.append(
            f'<text x="{x}" y="{y + index * (size + 14)}" text-anchor="{anchor}" '
            f'font-family="{FONT}" font-size="{size}" fill="{fill}">{line}</text>'
        )
    return "\n".join(out)


def controller_figure(cx: int, cy: int, left_arm: tuple[int, int], right_arm: tuple[int, int]) -> str:
    return f"""
    <circle cx="{cx}" cy="{cy - 120}" r="30" fill="#f0c9a4" stroke="#1f2b33" stroke-width="8"/>
    <line x1="{cx}" y1="{cy - 90}" x2="{cx}" y2="{cy + 60}" stroke="#1f2b33" stroke-width="16" stroke-linecap="round"/>
    <line x1="{cx}" y1="{cy - 40}" x2="{cx + left_arm[0]}" y2="{cy + left_arm[1]}" stroke="#1f2b33" stroke-width="16" stroke-linecap="round"/>
    <line x1="{cx}" y1="{cy - 40}" x2="{cx + right_arm[0]}" y2="{cy + right_arm[1]}" stroke="#1f2b33" stroke-width="16" stroke-linecap="round"/>
    <line x1="{cx}" y1="{cy + 60}" x2="{cx - 55}" y2="{cy + 180}" stroke="#1f2b33" stroke-width="16" stroke-linecap="round"/>
    <line x1="{cx}" y1="{cy + 60}" x2="{cx + 55}" y2="{cy + 180}" stroke="#1f2b33" stroke-width="16" stroke-linecap="round"/>
    """


def make_cards() -> dict[str, str]:
    cards: dict[str, str] = {}

    cards["controller_slide_1"] = wrap_svg(
        "Регулировщик: рука вверх",
        f"""
        <rect x="90" y="130" width="560" height="760" rx="28" fill="#fffdf8" stroke="#d8ccb1" stroke-width="4"/>
        {controller_figure(370, 430, (-90, 60), (0, -190))}
        {text_block(760, 240, ["Рука поднята вверх", "Движение запрещено всем", "Исключение: если уже нельзя", "остановиться без экстренного торможения"], size=30)}
        {text_block(760, 520, ["Смотри не на фразу, а на картинку:", "поднятая рука = общая пауза", "для всех направлений"], size=28)}
        """,
    )
    cards["controller_slide_2"] = wrap_svg(
        "Регулировщик: руки в стороны",
        f"""
        <rect x="90" y="130" width="560" height="760" rx="28" fill="#fffdf8" stroke="#d8ccb1" stroke-width="4"/>
        {controller_figure(370, 430, (-150, 0), (150, 0))}
        {text_block(760, 220, ["С боков можно:", "прямо и направо"], size=32)}
        {text_block(760, 380, ["Со стороны груди и спины:", "движение запрещено"], size=32)}
        {text_block(760, 570, ["Быстрый якорь:", "грудь и спина закрыты,", "бока открыты"], size=28)}
        """,
    )
    cards["controller_slide_3"] = wrap_svg(
        "Регулировщик: правая рука вперед",
        f"""
        <rect x="90" y="130" width="560" height="760" rx="28" fill="#fffdf8" stroke="#d8ccb1" stroke-width="4"/>
        {controller_figure(370, 430, (-80, 60), (150, 0))}
        {text_block(760, 190, ["Левый бок:", "можно во всех направлениях"], size=32)}
        {text_block(760, 360, ["Грудь:", "только направо"], size=32)}
        {text_block(760, 520, ["Спина и правый бок:", "движение запрещено"], size=32)}
        {text_block(760, 700, ["Главное правило темы:", "регулировщик всегда выше", "светофора, знаков и разметки"], size=26)}
        """,
    )

    cards["traffic_lights_slide_1"] = wrap_svg(
        "Светофор: базовые сигналы",
        f"""
        <rect x="150" y="160" width="260" height="620" rx="42" fill="#222831"/>
        <circle cx="280" cy="290" r="76" fill="#d93b2d"/>
        <circle cx="280" cy="470" r="76" fill="#f0c419"/>
        <circle cx="280" cy="650" r="76" fill="#2ca25f"/>
        {text_block(520, 300, ["Красный / красный+жёлтый: стоим"], size=32)}
        {text_block(520, 470, ["Жёлтый: обычно стоим,", "кроме безопасного завершения"], size=32)}
        {text_block(520, 660, ["Зелёный: движение разрешено"], size=32)}
        """,
        bg="#eef4f1",
    )
    cards["traffic_lights_slide_2"] = wrap_svg(
        "Светофор: допсекция",
        f"""
        <rect x="170" y="220" width="260" height="520" rx="38" fill="#222831"/>
        <circle cx="300" cy="410" r="72" fill="#d93b2d"/>
        <rect x="520" y="280" width="250" height="260" rx="32" fill="#222831"/>
        <polygon points="610,360 700,410 610,460" fill="#2ca25f"/>
        {text_block(860, 320, ["Стрелка горит:", "ехать можно только", "в указанном направлении"], size=32)}
        {text_block(860, 520, ["Если основной красный или жёлтый:", "обязан уступить тем,", "кто едет на свой разрешающий"], size=28)}
        """,
        bg="#eef4f1",
    )
    cards["traffic_lights_slide_3"] = wrap_svg(
        "Светофор: как решать задачу",
        f"""
        <rect x="180" y="180" width="1040" height="110" rx="22" fill="#c84c2b"/>
        <rect x="180" y="340" width="1040" height="110" rx="22" fill="#de9b22"/>
        <rect x="180" y="500" width="1040" height="110" rx="22" fill="#2c8b72"/>
        <rect x="180" y="660" width="1040" height="110" rx="22" fill="#456b8c"/>
        {text_block(700, 250, ["1. Какой основной сигнал?"], size=34, fill="#fff", anchor="middle")}
        {text_block(700, 410, ["2. Есть ли дополнительная секция?"], size=34, fill="#fff", anchor="middle")}
        {text_block(700, 570, ["3. В каком направлении она разрешает ехать?"], size=34, fill="#fff", anchor="middle")}
        {text_block(700, 730, ["4. Нужно ли уступить другим?"], size=34, fill="#fff", anchor="middle")}
        """,
        bg="#eef4f1",
    )

    cards["priority_slide_1"] = wrap_svg(
        "Приоритет: порядок разбора",
        f"""
        <rect x="180" y="170" width="1040" height="120" rx="24" fill="#c84c2b"/>
        <rect x="180" y="330" width="1040" height="120" rx="24" fill="#de9b22"/>
        <rect x="180" y="490" width="1040" height="120" rx="24" fill="#2c8b72"/>
        <rect x="180" y="650" width="1040" height="120" rx="24" fill="#4d6f94"/>
        {text_block(700, 245, ["1. Регулировщик / временный знак?"], size=34, fill="#fff", anchor="middle")}
        {text_block(700, 405, ["2. Если нет: кто на главной?"], size=34, fill="#fff", anchor="middle")}
        {text_block(700, 565, ["3. Если дороги равны: помеха справа"], size=34, fill="#fff", anchor="middle")}
        {text_block(700, 725, ["4. Левый поворот: уступи встречным"], size=34, fill="#fff", anchor="middle")}
        """,
    )
    cards["priority_slide_2"] = wrap_svg(
        "Знаки приоритета: что помнить",
        f"""
        <polygon points="290,240 360,170 430,240 360,310" fill="#f0c419" stroke="#1f2b33" stroke-width="10"/>
        <polygon points="290,510 360,390 430,510" fill="#ffffff" stroke="#d93b2d" stroke-width="16"/>
        <rect x="780" y="185" width="430" height="520" rx="26" fill="#fffdf8" stroke="#d8ccb1" stroke-width="4"/>
        {text_block(860, 270, ["Главная дорога:", "кто на ней, тот имеет", "преимущество перед", "теми, кто на второстепенной"], size=30)}
        {text_block(860, 520, ["Уступите дорогу:", "не продолжай движение,", "если заставишь другого", "изменить скорость или траекторию"], size=28)}
        """,
    )
    cards["priority_slide_3"] = wrap_svg(
        "Перекрёсток: типичная ловушка",
        f"""
        <rect x="200" y="220" width="1000" height="120" rx="20" fill="#5a6168"/>
        <rect x="640" y="120" width="120" height="760" rx="20" fill="#5a6168"/>
        <rect x="648" y="130" width="104" height="740" fill="#707980"/>
        <rect x="210" y="228" width="980" height="104" fill="#707980"/>
        <polygon points="520,540 610,500 610,580" fill="#2c8b72"/>
        <polygon points="880,500 790,540 790,460" fill="#456b8c"/>
        {text_block(170, 730, ["При левом повороте не забывай:", "встречный, который едет прямо", "или направо, имеет приоритет"], size=32)}
        """,
    )

    cards["markings_slide_1"] = wrap_svg(
        "Разметка: сплошная и прерывистая",
        f"""
        <rect x="150" y="200" width="1100" height="220" rx="30" fill="#4e5861"/>
        <line x1="230" y1="310" x2="1170" y2="310" stroke="#ffffff" stroke-width="18"/>
        {text_block(700, 390, ["1.1 Сплошная: пересекать нельзя"], size=32, fill="#fff", anchor="middle")}
        <rect x="150" y="520" width="1100" height="220" rx="30" fill="#4e5861"/>
        <line x1="230" y1="630" x2="320" y2="630" stroke="#ffffff" stroke-width="18"/>
        <line x1="400" y1="630" x2="490" y2="630" stroke="#ffffff" stroke-width="18"/>
        <line x1="570" y1="630" x2="660" y2="630" stroke="#ffffff" stroke-width="18"/>
        <line x1="740" y1="630" x2="830" y2="630" stroke="#ffffff" stroke-width="18"/>
        <line x1="910" y1="630" x2="1000" y2="630" stroke="#ffffff" stroke-width="18"/>
        {text_block(700, 710, ["1.5 Прерывистая: перестроение разрешено"], size=32, fill="#fff", anchor="middle")}
        """,
        bg="#edf1f4",
    )
    cards["markings_slide_2"] = wrap_svg(
        "Разметка: линия приближения и стоп-линия",
        f"""
        <rect x="150" y="220" width="1100" height="220" rx="30" fill="#4e5861"/>
        <line x1="220" y1="330" x2="390" y2="330" stroke="#ffffff" stroke-width="18"/>
        <line x1="470" y1="330" x2="640" y2="330" stroke="#ffffff" stroke-width="18"/>
        <line x1="720" y1="330" x2="890" y2="330" stroke="#ffffff" stroke-width="18"/>
        <line x1="970" y1="330" x2="1140" y2="330" stroke="#ffffff" stroke-width="18"/>
        {text_block(700, 400, ["1.6 Длинные штрихи: скоро будет сплошная"], size=32, fill="#fff", anchor="middle")}
        <rect x="150" y="560" width="1100" height="220" rx="30" fill="#4e5861"/>
        <line x1="700" y1="580" x2="700" y2="760" stroke="#ffffff" stroke-width="26"/>
        {text_block(700, 840, ["1.12 Стоп-линия: место обязательной остановки"], size=30, anchor="middle")}
        """,
        bg="#edf1f4",
    )

    cards["stopping_slide_1"] = wrap_svg(
        "Остановка: где нельзя",
        f"""
        <circle cx="280" cy="300" r="130" fill="#d9432c"/>
        <line x1="190" y1="390" x2="370" y2="210" stroke="#ffffff" stroke-width="28"/>
        {text_block(520, 250, ["Пешеходный переход и 5 м перед ним"], size=32)}
        {text_block(520, 360, ["Перекрёсток и 5 м от края", "пересекаемой проезжей части"], size=32)}
        {text_block(520, 510, ["Места, где закроешь знак,", "светофор, обзор или проход пешеходам"], size=30)}
        """,
    )
    cards["stopping_slide_2"] = wrap_svg(
        "Остановка и стоянка: как различать",
        f"""
        <rect x="180" y="220" width="420" height="500" rx="30" fill="#2c8b72"/>
        <rect x="800" y="220" width="420" height="500" rx="30" fill="#456b8c"/>
        {text_block(390, 340, ["Остановка"], size=40, fill="#fff", anchor="middle")}
        {text_block(390, 430, ["до 5 минут", "или для посадки,", "высадки, загрузки"], size=30, fill="#fff", anchor="middle")}
        {text_block(1010, 340, ["Стоянка"], size=40, fill="#fff", anchor="middle")}
        {text_block(1010, 430, ["дольше 5 минут", "без этих причин"], size=30, fill="#fff", anchor="middle")}
        {text_block(700, 850, ["На экзамене сначала ищи запрет места, а уже потом считай минуты"], size=28, anchor="middle")}
        """,
    )

    cards["pedestrians_slide_1"] = wrap_svg(
        "Пешеходный переход",
        f"""
        <rect x="120" y="200" width="1160" height="260" rx="28" fill="#4e5861"/>
        <rect x="240" y="245" width="60" height="170" fill="#ffffff"/>
        <rect x="380" y="245" width="60" height="170" fill="#ffffff"/>
        <rect x="520" y="245" width="60" height="170" fill="#ffffff"/>
        <rect x="660" y="245" width="60" height="170" fill="#ffffff"/>
        <rect x="800" y="245" width="60" height="170" fill="#ffffff"/>
        <rect x="940" y="245" width="60" height="170" fill="#ffffff"/>
        <circle cx="620" cy="290" r="22" fill="#2c8b72"/>
        <line x1="620" y1="312" x2="620" y2="372" stroke="#2c8b72" stroke-width="12"/>
        <line x1="620" y1="336" x2="580" y2="360" stroke="#2c8b72" stroke-width="12"/>
        <line x1="620" y1="336" x2="660" y2="360" stroke="#2c8b72" stroke-width="12"/>
        <line x1="620" y1="372" x2="590" y2="420" stroke="#2c8b72" stroke-width="12"/>
        <line x1="620" y1="372" x2="650" y2="420" stroke="#2c8b72" stroke-width="12"/>
        {text_block(700, 560, ["Если пешеход уже идёт или только вступил на проезжую часть,", "ты обязан уступить"], size=32, anchor="middle")}
        {text_block(700, 720, ["Если машина впереди тормозит перед переходом,", "считай ситуацию потенциально опасной"], size=28, anchor="middle")}
        """,
        bg="#edf5ef",
    )
    cards["pedestrians_slide_2"] = wrap_svg(
        "Остановка маршрутного транспорта",
        f"""
        <rect x="160" y="320" width="460" height="250" rx="32" fill="#456b8c"/>
        <circle cx="260" cy="600" r="40" fill="#26343f"/>
        <circle cx="520" cy="600" r="40" fill="#26343f"/>
        <rect x="240" y="380" width="90" height="70" fill="#d9eefb"/>
        <rect x="360" y="380" width="90" height="70" fill="#d9eefb"/>
        <rect x="480" y="380" width="90" height="70" fill="#d9eefb"/>
        {text_block(760, 330, ["В населённом пункте автобус,", "начинающий движение от остановки,", "имеет преимущество"], size=32)}
        {text_block(760, 520, ["Но рядом с остановкой всегда жди", "скрытого пешехода из-за автобуса"], size=30)}
        """,
        bg="#edf5ef",
    )

    cards["railroad_slide_1"] = wrap_svg(
        "Ж/д переезд: когда не выезжать",
        f"""
        <line x1="170" y1="760" x2="1230" y2="760" stroke="#5b6166" stroke-width="16"/>
        <line x1="170" y1="830" x2="1230" y2="830" stroke="#5b6166" stroke-width="16"/>
        <rect x="230" y="320" width="240" height="36" rx="14" fill="#ffffff" stroke="#d9432c" stroke-width="10"/>
        <line x1="230" y1="338" x2="470" y2="338" stroke="#d9432c" stroke-width="12"/>
        {text_block(600, 250, ["Не выезжай, если:", "шлагбаум закрыт или закрывается", "горит запрещающий сигнал", "есть дежурный с запретом", "затормозишь на путях из-за затора"], size=30)}
        """,
        bg="#f7f0ed",
    )
    cards["railroad_slide_2"] = wrap_svg(
        "Ж/д переезд: где остановиться",
        f"""
        <line x1="250" y1="650" x2="1150" y2="650" stroke="#5b6166" stroke-width="16"/>
        <line x1="250" y1="720" x2="1150" y2="720" stroke="#5b6166" stroke-width="16"/>
        <line x1="450" y1="450" x2="450" y2="610" stroke="#d9432c" stroke-width="18"/>
        <line x1="820" y1="430" x2="820" y2="610" stroke="#2c8b72" stroke-width="18"/>
        {text_block(310, 400, ["5 м до шлагбаума"], size=30)}
        {text_block(690, 400, ["10 м до ближайшего рельса,", "если шлагбаума нет"], size=30)}
        {text_block(700, 860, ["На переезде выбирай остановку раньше, а не рискованный проезд позже"], size=28, anchor="middle")}
        """,
        bg="#f7f0ed",
    )

    cards["first_aid_slide_1"] = wrap_svg(
        "Первая помощь: правильный порядок",
        f"""
        <rect x="150" y="180" width="1100" height="110" rx="22" fill="#c84c2b"/>
        <rect x="150" y="340" width="1100" height="110" rx="22" fill="#de9b22"/>
        <rect x="150" y="500" width="1100" height="110" rx="22" fill="#2c8b72"/>
        <rect x="150" y="660" width="1100" height="110" rx="22" fill="#456b8c"/>
        {text_block(700, 248, ["1. Безопасность места"], size=34, fill="#fff", anchor="middle")}
        {text_block(700, 408, ["2. Сознание и дыхание"], size=34, fill="#fff", anchor="middle")}
        {text_block(700, 568, ["3. Вызов 112 и остановка кровотечения"], size=34, fill="#fff", anchor="middle")}
        {text_block(700, 728, ["4. Без нужды не перемещай пострадавшего"], size=34, fill="#fff", anchor="middle")}
        """,
        bg="#eef3f6",
    )
    cards["first_aid_slide_2"] = wrap_svg(
        "Первая помощь: типичные ошибки",
        f"""
        <circle cx="280" cy="300" r="130" fill="#d9432c"/>
        <line x1="190" y1="390" x2="370" y2="210" stroke="#ffffff" stroke-width="28"/>
        {text_block(520, 240, ["Не вытаскивай человека из машины без крайней нужды"], size=32)}
        {text_block(520, 380, ["Не начинай с «лечения», если место небезопасно"], size=32)}
        {text_block(520, 520, ["На экзамене выигрывает порядок действий,", "а не медицинские детали"], size=30)}
        """,
        bg="#eef3f6",
    )

    return cards


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    assets_dir = project_root / "assets" / "lessons"
    assets_dir.mkdir(parents=True, exist_ok=True)
    for name, svg in make_cards().items():
        svg_path = assets_dir / f"{name}.svg"
        png_path = assets_dir / f"{name}.png"
        svg_path.write_text(svg, encoding="utf-8")
        subprocess.run(["convert", str(svg_path), str(png_path)], check=True)
    print(f"Generated {len(make_cards())} lesson slides in {assets_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
