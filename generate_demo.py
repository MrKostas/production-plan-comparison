"""Create the fictional April 2027 inputs from scratch."""

import csv
from datetime import date
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parent / "demo"
MONTH = date(2027, 4, 1)
DAY_2 = date(2027, 4, 2)
LINES = ("Демо-завод|DEMO|Линия №1", "Демо-завод|DEMO|Линия №2")
PRODUCTS = ("Продукт A", "Продукт B")
SCENARIOS = (
    ("factory_plan", 1, "Заводской план", "Завод"),
    ("current_version", 2, "Текущая версия", "Планировщик"),
    ("previous_version", 3, "Предыдущая версия", "Планировщик"),
)


def write_book(path, sheets):
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    workbook.remove(workbook.active)
    workbook.properties.creator = "MrKostas"
    workbook.properties.title = "Production Plan Comparison | Synthetic data"
    for sheet, rows in sheets.items():
        worksheet = workbook.create_sheet(sheet)
        for row in rows:
            worksheet.append(row)
    workbook.save(path)


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)


def generate():
    sources = ROOT / "sources"
    reference = ROOT / "reference"
    for folder, masses in (
        ("current_version", (10, 10)),
        ("previous_version", (18, 18)),
    ):
        rows = [
            (
                "Событие",
                "Интервал",
                "Длительность, ч",
                "Режим",
                "Потреблено",
                "Произведено",
                "Произведено, Т.",
            ),
            ("Дата: 01.04.27", None, None, None, None, None, None),
        ]
        for product, mass in zip(PRODUCTS, masses):
            # A repeated daily key exercises the aggregation before norm application.
            chunks = (
                (4, 6)
                if folder == "current_version" and product == PRODUCTS[0]
                else (mass,)
            )
            for chunk in chunks:
                rows.append(
                    (
                        "Выпуск",
                        "08:00–14:00",
                        6,
                        "Выпуск",
                        "Сырье A",
                        f"{product}={chunk}",
                        chunk,
                    )
                )
        write_book(sources / folder / "DEMO 1 demo.xlsx", {"Экспорт": rows})

    write_book(
        sources / "factory-plan.xlsx",
        {
            f"Линия {index}": [
                ("Продукт", None, None, None),
                ("Итого фасовка", None, None, None),
                ("Номенклатура", MONTH, DAY_2, "Факт за месяц"),
                (product, 10 if index == 1 else None, 10 if index == 2 else None, 10),
                ("Итого", None, None, 10),
            ]
            for index, product in enumerate(PRODUCTS, 1)
        },
    )
    write_book(
        sources / "orders апрель 2027.xlsx",
        {
            "Итого фасовка": [
                ("Продукт", None, None, None),
                ("Итого фасовка", None, None, None),
                (None, 1, 2, "Итого за месяц"),
                (PRODUCTS[0], 10, None, 10),
                (PRODUCTS[1], None, 10, 10),
                ("Итого", 10, 10, 20),
            ]
        },
    )
    write_book(
        reference / "product_info.xlsx",
        {
            "product": [
                ("name", "productGroup"),
                (PRODUCTS[0], "Группа A"),
                (PRODUCTS[1], "Группа B"),
            ]
        },
    )
    write_book(
        reference / "site_line_info.xlsx",
        {
            "site": [("siteKey", "siteName"), (1, "Демо-завод")],
            "section": [("sectionKey", "siteKey", "sectionName"), (1, 1, "Фасовка")],
            "line": [
                ("lineKey", "sectionKey", "lineName"),
                (LINES[0], 1, "Линия 1"),
                (LINES[1], 1, "Линия 2"),
            ],
            "scenario": [
                ("scenarioCode", "scenarioKey", "scenarioName", "scenarioOwner"),
                *SCENARIOS,
            ],
            "performance_info": [
                ("lineKey", "product", "performance", "workingHours"),
                *((line, product, 23, 23) for line in LINES for product in PRODUCTS),
            ],
        },
    )
    stops = [("stopID", "scenarioKey", "lineKey", "date", "stopType", "durationHours")]
    for code, *_ in SCENARIOS:
        for line, day in zip(LINES, (MONTH, DAY_2)):
            stops.append((len(stops), code, line, day, "Санитарная остановка", 1))
    write_book(sources / "mandatory_stops.xlsx", {"mandatory_stops": stops})
    write_csv(
        sources / "stop_coverage.csv",
        ("scenarioKey", "lineKey", "month", "isComplete"),
        ((code, line, MONTH, "true") for code, *_ in SCENARIOS for line in LINES),
    )
    write_csv(
        reference / "ikp_comparison.csv",
        (
            "comparisonSetID",
            "methodVersion",
            "scenarioKey",
            "siteKey",
            "month",
            "isProvided",
            "referenceApproved",
            "inputsConfirmed",
        ),
        (
            ("demo-2027-04", "ikp-relative-v1", code, 1, MONTH, "true", "true", "true")
            for code, *_ in SCENARIOS
        ),
    )


if __name__ == "__main__":
    generate()
