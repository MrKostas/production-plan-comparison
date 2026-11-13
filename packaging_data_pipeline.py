from __future__ import annotations

import re
import warnings
from pathlib import Path

import pandas as pd

BASE_DIRECTORY_PATH = Path(__file__).resolve().parent / "demo"
SOURCE_DATA_PATH = "sources"
PROCESSED_DATA_PATH = "processed"
REFERENCE_DATA_PATH = "reference"

CURRENT_PLAN_DIRECTORY_PATH = BASE_DIRECTORY_PATH / SOURCE_DATA_PATH / "current_version"
PREVIOUS_PLAN_DIRECTORY_PATH = (
    BASE_DIRECTORY_PATH / SOURCE_DATA_PATH / "previous_version"
)
FACTORY_SOURCE_FILE_PATH = BASE_DIRECTORY_PATH / SOURCE_DATA_PATH / "factory-plan.xlsx"
ORDERS_SOURCE_FILE_PATH = (
    BASE_DIRECTORY_PATH / SOURCE_DATA_PATH / "orders апрель 2027.xlsx"
)

OUTPUT_FILE_PATH = BASE_DIRECTORY_PATH / PROCESSED_DATA_PATH / "packaging_data.xlsx"
ORDERS_OUTPUT_FILE_PATH = BASE_DIRECTORY_PATH / PROCESSED_DATA_PATH / "orders_data.xlsx"
PRODUCT_INFO_FILE_PATH = BASE_DIRECTORY_PATH / REFERENCE_DATA_PATH / "product_info.xlsx"
SITE_LINE_INFO_FILE_PATH = (
    BASE_DIRECTORY_PATH / REFERENCE_DATA_PATH / "site_line_info.xlsx"
)
ORDERS_TARGET_SHEET = "Итого фасовка"
PACKAGING_COLUMNS = ["mass", "date", "material", "lineKey", "scenarioKey"]

PLAN_SCENARIO_KEYS = {
    CURRENT_PLAN_DIRECTORY_PATH.name: "current_version",
    PREVIOUS_PLAN_DIRECTORY_PATH.name: "previous_version",
}
FACTORY_SCENARIO_KEY = "factory_plan"

RUSSIAN_MONTH_NUMBERS = {
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
}

SAP_EXCLUDE_COLUMNS = [
    "Событие",
    "Интервал",
    "Длительность, ч",
    "Режим",
    "Потреблено",
    "Произведено",
]
SAP_SHEET_NAME = "Экспорт"
SAP_DATE_PATTERN = r"(\d{2}\.\d{2}\.\d{2})"
SAP_NA_COLUMNS = ["Интервал", "Режим", "Потреблено", "Произведено"]

FACTORY_TARGET_SHEETS = ["Линия 1", "Линия 2"]
FACTORY_EXCLUDE_VALUES = ["Итого по группе"]


def save_packaging_data_to_excel(
    data: pd.DataFrame, file_path: Path, sheet_name: str = "main"
) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(file_path, engine="openpyxl", mode="w") as writer:
        data.to_excel(writer, sheet_name=sheet_name, index=False)


def _extract_workshop_and_line(file_name: str) -> tuple[str, str]:
    stem = Path(file_name).stem
    parts = stem.split()
    if len(parts) < 2:
        raise ValueError(
            f"Не удалось разобрать имя файла {file_name!r}: "
            "ожидался формат 'цех номер_линии индекс.xlsx'"
        )
    return parts[0], parts[1]


def _build_line_key(file_name: str) -> str:
    workshop, line_number = _extract_workshop_and_line(file_name)
    return f"Демо-завод|{workshop.upper()}|Линия №{line_number}"


def load_sap_data(source_file_path: Path) -> pd.DataFrame:
    return pd.read_excel(source_file_path, sheet_name=SAP_SHEET_NAME)


def extract_sap_date(df: pd.DataFrame) -> pd.DataFrame:
    dates = df["Событие"].str.extract(SAP_DATE_PATTERN, expand=False)
    df["date"] = pd.to_datetime(dates, format="%d.%m.%y").ffill().dt.date
    return df


def create_sap_material_column(df: pd.DataFrame) -> pd.DataFrame:
    df["material"] = df["Произведено"].str.split("=", n=1).str[0]
    return df


def create_sap_packaging_data(
    df: pd.DataFrame, file_name: str, source_name: str
) -> pd.DataFrame:
    if df.empty:
        raise ValueError("Лист с данными по фасовке пуст")

    data_date = extract_sap_date(df)
    data_clean = data_date.dropna(subset=SAP_NA_COLUMNS).reset_index(drop=True)
    data_material = create_sap_material_column(data_clean)
    data_material["lineKey"] = _build_line_key(file_name)
    try:
        data_material["scenarioKey"] = PLAN_SCENARIO_KEYS[source_name]
    except KeyError as error:
        raise ValueError(f"Неизвестный источник плана {source_name!r}") from error
    data_mass = data_material.rename(columns={"Произведено, Т.": "mass"})

    result = data_mass.drop(SAP_EXCLUDE_COLUMNS, axis=1)
    return result.reindex(columns=PACKAGING_COLUMNS)


def load_all_sap_sources() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for directory_path in (
        CURRENT_PLAN_DIRECTORY_PATH,
        PREVIOUS_PLAN_DIRECTORY_PATH,
    ):
        if not directory_path.exists():
            continue

        source_name = directory_path.name
        excel_files = sorted(
            file_path
            for file_path in directory_path.glob("*.xlsx")
            if file_path.name != "sap_packaging_data.xlsx"
        )

        for file_path in excel_files:
            raw_data = load_sap_data(file_path)
            frames.append(
                create_sap_packaging_data(raw_data, file_path.name, source_name)
            )

    if not frames:
        return pd.DataFrame(columns=PACKAGING_COLUMNS)

    return pd.concat(frames, ignore_index=True)


def _normalize_sheet_name(sheet_name: str) -> str:
    return " ".join(sheet_name.strip().casefold().split())


def resolve_sheet_name(
    available_sheet_names: list[str], requested_sheet_name: str
) -> str:
    normalized_requested_name = _normalize_sheet_name(requested_sheet_name)
    matches = [
        sheet_name
        for sheet_name in available_sheet_names
        if _normalize_sheet_name(sheet_name) == normalized_requested_name
    ]

    if not matches:
        raise ValueError(f"Не найден лист {requested_sheet_name!r} в исходном файле")

    return matches[0]


def infer_plant_name(file_path: Path) -> str:
    if "factory-plan" in file_path.name:
        return "Демо-завод"

    raise ValueError(
        f"Не удалось определить площадку по имени файла {file_path.name!r}"
    )


def extract_factory_line_number(sheet_name: str) -> str:
    match = re.search(r"\d+", sheet_name)
    if match is None:
        raise ValueError(
            f"Не удалось определить номер линии из имени листа {sheet_name!r}"
        )
    return match.group(0)


def build_factory_line_key(file_path: Path, sheet_name: str) -> str:
    plant_name = infer_plant_name(file_path)
    line_number = extract_factory_line_number(sheet_name)
    return f"{plant_name}|DEMO|Линия №{line_number}"


def create_factory_packaging_data(
    df: pd.DataFrame,
    header_marker: str = "Итого фасовка",
    skip_rows: int = 1,
    tail_marker: str = "Итого",
    total_column_marker: str = "Факт за месяц",
    date_period: pd.Period | None = None,
) -> pd.DataFrame:
    if df.empty:
        raise ValueError("Лист с данными по фасовке пуст")

    header_position = find_position(header_marker, df)
    data_start = header_position + skip_rows
    tail_position = find_position(tail_marker, df, start_position=data_start)

    raw_headers = df.iloc[header_position + skip_rows].to_list()
    try:
        wide_position = int(raw_headers.index(total_column_marker))
    except ValueError as error:
        raise ValueError(
            f"Не найдена итоговая колонка {total_column_marker!r}"
        ) from error
    date_headers = raw_headers[1:wide_position]
    if any(pd.isna(value) or str(value).strip() == "" for value in date_headers):
        raise ValueError("Среди заголовков дневных колонок найдены пустые значения")
    packaging_headers = ["material", *date_headers]

    packaging = (
        df.iloc[header_position + skip_rows : tail_position, :wide_position]
        .copy()
        .set_axis(packaging_headers, axis="columns")
    )

    flat_packaging = packaging.melt(
        id_vars=["material"], var_name="date", value_name="mass"
    )
    flat_packaging["material"] = flat_packaging["material"].astype("string").str.strip()
    flat_packaging["mass"] = pd.to_numeric(flat_packaging["mass"], errors="coerce")
    flat_packaging = flat_packaging.dropna(subset=["material", "date", "mass"]).copy()
    flat_packaging["mass"] = pd.to_numeric(flat_packaging["mass"], errors="raise")
    if date_period is None:
        flat_packaging["date"] = pd.to_datetime(flat_packaging["date"]).dt.date
    else:
        day_numbers = pd.to_numeric(flat_packaging["date"], errors="coerce")
        flat_packaging["date"] = pd.to_datetime(
            {
                "year": date_period.year,
                "month": date_period.month,
                "day": day_numbers,
            },
            errors="coerce",
        ).dt.date
        flat_packaging = flat_packaging.dropna(subset=["date"])

    return flat_packaging.copy()


def find_position(value_marker: str, df: pd.DataFrame, start_position: int = 0) -> int:
    values = df.iloc[start_position:, 0].astype("string").str.strip()
    matches = values.eq(value_marker).fillna(False)

    positions = matches.to_numpy().nonzero()[0]
    if len(positions) == 0:
        raise ValueError(
            f"Не найден маркер {value_marker!r}, начиная с позиции {start_position}"
        )

    return start_position + int(positions[0])


def load_factory_packaging_data(
    file_path: Path, requested_sheet_names: list[str]
) -> pd.DataFrame:
    if not file_path.exists():
        raise FileNotFoundError(f"Не найден файл {file_path}")

    frames: list[pd.DataFrame] = []
    with pd.ExcelFile(file_path) as workbook:
        for requested_sheet in requested_sheet_names:
            sheet_name = resolve_sheet_name(workbook.sheet_names, requested_sheet)
            raw_data = pd.read_excel(workbook, sheet_name=sheet_name)
            cleaned_data = create_factory_packaging_data(raw_data).copy()
            cleaned_data["lineKey"] = build_factory_line_key(file_path, sheet_name)
            cleaned_data["scenarioKey"] = FACTORY_SCENARIO_KEY
            frames.append(cleaned_data)

    if not frames:
        return pd.DataFrame(columns=PACKAGING_COLUMNS)

    result = pd.concat(frames, ignore_index=True)
    result = result[~result["material"].isin(FACTORY_EXCLUDE_VALUES)]
    return result.reindex(columns=PACKAGING_COLUMNS)


def infer_orders_period(file_path: Path) -> pd.Period:
    normalized_file_name = file_path.stem.casefold()
    month_numbers = [
        month_number
        for month_name, month_number in RUSSIAN_MONTH_NUMBERS.items()
        if re.search(rf"\b{month_name}\b", normalized_file_name)
    ]
    years = re.findall(r"\b(20\d{2})\b", normalized_file_name)

    if len(month_numbers) != 1 or len(years) != 1:
        raise ValueError(
            "Не удалось однозначно определить месяц и год заказов "
            f"из имени файла {file_path.name!r}"
        )

    return pd.Period(year=int(years[0]), month=month_numbers[0], freq="M")


def load_orders_data(
    file_path: Path = ORDERS_SOURCE_FILE_PATH,
    requested_sheet_name: str = ORDERS_TARGET_SHEET,
) -> pd.DataFrame:
    if not file_path.exists():
        raise FileNotFoundError(f"Не найден файл {file_path}")

    with pd.ExcelFile(file_path) as workbook:
        sheet_name = resolve_sheet_name(workbook.sheet_names, requested_sheet_name)
        raw_data = pd.read_excel(workbook, sheet_name=sheet_name)
    orders_data = create_factory_packaging_data(
        raw_data,
        total_column_marker="Итого за месяц",
        date_period=infer_orders_period(file_path),
    )
    orders_data = orders_data[~orders_data["material"].isin(FACTORY_EXCLUDE_VALUES)]
    return orders_data.reindex(columns=["mass", "date", "material"]).reset_index(
        drop=True
    )


def build_unified_packaging_dataset() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []

    sap_data = load_all_sap_sources()
    if not sap_data.empty:
        frames.append(sap_data)

    if FACTORY_SOURCE_FILE_PATH.exists():
        frames.append(
            load_factory_packaging_data(FACTORY_SOURCE_FILE_PATH, FACTORY_TARGET_SHEETS)
        )

    if not frames:
        raise ValueError("Не найдено данных для объединения")

    return pd.concat(frames, ignore_index=True).reindex(columns=PACKAGING_COLUMNS)


def validate_single_period(
    packaging_data: pd.DataFrame, orders_data: pd.DataFrame
) -> pd.Period:
    periods: set[pd.Period] = set()
    for name, data in (
        ("планы производства", packaging_data),
        ("заказы", orders_data),
    ):
        if data.empty or data["date"].isna().any():
            raise ValueError(f"В наборе «{name}» отсутствуют даты")
        periods.update(pd.to_datetime(data["date"], errors="raise").dt.to_period("M"))

    if len(periods) != 1:
        raise ValueError(
            "Планы производства и заказы должны относиться к одному "
            f"календарному месяцу; найдены периоды: {sorted(map(str, periods))}"
        )

    return periods.pop()


def validate_model_keys(
    packaging_data: pd.DataFrame, orders_data: pd.DataFrame
) -> None:
    products = pd.read_excel(PRODUCT_INFO_FILE_PATH, usecols=["name"])
    lines = pd.read_excel(
        SITE_LINE_INFO_FILE_PATH, sheet_name="line", usecols=["lineKey"]
    )
    scenarios = pd.read_excel(
        SITE_LINE_INFO_FILE_PATH,
        sheet_name="scenario",
        usecols=["scenarioCode"],
    )
    production = packaging_data.loc[packaging_data["mass"] > 0]

    for source, source_column, lookup, lookup_column in (
        (
            production,
            "material",
            products,
            "name",
        ),
        (
            orders_data,
            "material",
            products,
            "name",
        ),
        (
            production,
            "lineKey",
            lines,
            "lineKey",
        ),
        (
            production,
            "scenarioKey",
            scenarios,
            "scenarioCode",
        ),
    ):
        if source[source_column].isna().any():
            raise ValueError(f"В данных есть пустые значения {source_column!r}")
        if (
            lookup[lookup_column].isna().any()
            or lookup[lookup_column].duplicated().any()
        ):
            raise ValueError(
                f"Ключ справочника {lookup_column!r} должен быть уникальным"
            )
        missing = sorted(set(source[source_column]) - set(lookup[lookup_column]))
        if missing:
            raise ValueError(
                f"Значения {source_column!r} отсутствуют в справочнике "
                f"{lookup_column!r}: {missing}"
            )

    norms = pd.read_excel(SITE_LINE_INFO_FILE_PATH, sheet_name="performance_info")
    resolve_performance_line_keys(norms, lines)


def resolve_performance_line_keys(
    norms: pd.DataFrame, lines: pd.DataFrame
) -> pd.DataFrame:
    """Resolve legacy demo-site norms; explicit keys are required for other sites."""
    result = norms.copy()
    explicit_keys = "lineKey" in result.columns
    if not explicit_keys:
        if result.duplicated(["line", "product"]).any():
            raise ValueError("В performance_info повторяются пары line + product")
        legacy_lines = lines.loc[
            lines["lineKey"].str.startswith("Демо-завод|", na=False), ["lineKey"]
        ].copy()
        legacy_lines["line"] = legacy_lines["lineKey"].str.replace(
            r"^Демо-завод\|([^|]+)\|Линия №", r"\1 №", regex=True
        )
        if legacy_lines["line"].duplicated().any():
            raise ValueError("Неоднозначные линии Демо-завод: добавьте lineKey в нормы")
        result = result.merge(
            legacy_lines, on="line", how="left", validate="many_to_one"
        )
        unmatched = result.loc[result["lineKey"].isna(), "line"].unique().tolist()
        if unmatched:
            warnings.warn(
                f"Нормы legacy без линии в справочнике не участвуют в расчете: {unmatched}",
                stacklevel=2,
            )
            result = result.loc[result["lineKey"].notna()].copy()

    for column in ("lineKey", "product"):
        if (
            result[column].isna().any()
            or result[column].astype("string").str.strip().eq("").any()
        ):
            raise ValueError(
                f"В performance_info пустой {column}; заполните явные ключи"
            )
    if result.duplicated(["lineKey", "product"]).any():
        raise ValueError("В performance_info повторяются пары lineKey + product")
    missing = sorted(set(result["lineKey"]) - set(lines["lineKey"]))
    if missing:
        raise ValueError(f"В performance_info неизвестные lineKey: {missing}")
    return result


def main() -> None:
    packaging_data = build_unified_packaging_dataset()
    orders_data = load_orders_data()
    period = validate_single_period(packaging_data, orders_data)
    validate_model_keys(packaging_data, orders_data)

    save_packaging_data_to_excel(packaging_data, OUTPUT_FILE_PATH)
    save_packaging_data_to_excel(orders_data, ORDERS_OUTPUT_FILE_PATH)
    print(
        f"Сохранены данные за {period}: "
        f"{len(packaging_data)} строк плана, {len(orders_data)} строк заказов"
    )


if __name__ == "__main__":
    main()
