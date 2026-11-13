"""Independently calculate the plan-quality index from demo ETL outputs.

Run: python ikp_validation.py [--month 2027-04] [--output report.json]
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from packaging_data_pipeline import resolve_performance_line_keys

METHOD_VERSION = "ikp-relative-v1"
EPSILON = 1e-6
WEIGHTS = (0.60, 0.25, 0.15)


def _check_keys(frame, columns, unique=False):
    if frame[columns].isna().any().any():
        raise ValueError(f"Missing keys: {columns}")
    if any(frame[c].astype(str).str.strip().eq("").any() for c in columns):
        raise ValueError(f"Empty keys: {columns}")
    if unique and frame.duplicated(columns).any():
        raise ValueError(f"Duplicate keys: {columns}")


def _dates(frame, column, month):
    result = frame.copy()
    result[column] = pd.to_datetime(result[column], errors="raise")
    if (
        result[column].isna().any()
        or not result[column].eq(result[column].dt.normalize()).all()
    ):
        raise ValueError(f"Missing or non-daily dates: {column}")
    if not result[column].dt.to_period("M").eq(month).all():
        raise ValueError("Mixed reporting months")
    return result


def _positive_mass(frame):
    result = frame.copy()
    result["mass"] = pd.to_numeric(result["mass"], errors="raise")
    if not np.isfinite(result["mass"]).all() or result["mass"].lt(0).any():
        raise ValueError("Mass must be finite and nonnegative")
    return result.loc[result["mass"].gt(0)].copy()


def build_line_day_load(plans, norms, stops, coverage, lines, scenarios, month):
    """Build a full registered-line grid; never cap productive hours."""
    _check_keys(lines, ["lineKey"], unique=True)
    _check_keys(norms, ["lineKey", "product"], unique=True)
    _check_keys(plans, ["scenarioKey", "lineKey", "material", "date"])
    _check_keys(stops, ["stopID"], unique=True)
    _check_keys(stops, ["scenarioKey", "lineKey", "date", "stopType"])
    _check_keys(coverage, ["scenarioKey", "lineKey", "month"], unique=True)
    for data in (plans, stops, coverage):
        if not set(data.lineKey).issubset(lines.lineKey):
            raise ValueError("Unknown line key")
        if not set(data.scenarioKey).issubset(scenarios):
            raise ValueError("Unknown scenario key")
    if not set(norms.lineKey).issubset(lines.lineKey):
        raise ValueError("Unknown norm line key")
    production = _positive_mass(_dates(plans, "date", month))
    stops = _dates(stops, "date", month)
    stops["durationHours"] = pd.to_numeric(stops.durationHours, errors="raise")
    if not np.isfinite(stops.durationHours).all() or stops.durationHours.le(0).any():
        raise ValueError("Invalid stop duration")
    event_keys = ["scenarioKey", "lineKey", "date", "stopType", "durationHours"]
    if stops.duplicated(event_keys).any():
        raise ValueError("Repeated stop events with different IDs need review")
    coverage = _dates(coverage, "month", month)
    if not coverage.month.eq(month.start_time).all():
        raise ValueError("Coverage month must start on day one")
    if not coverage.isComplete.dropna().isin([True, False]).all():
        raise ValueError("Invalid coverage flag")
    daily_keys = ["scenarioKey", "lineKey", "material", "date"]
    daily = production.groupby(daily_keys, as_index=False).mass.sum()
    daily = daily.merge(
        norms[["lineKey", "product", "performance", "workingHours"]],
        left_on=["lineKey", "material"],
        right_on=["lineKey", "product"],
        how="left",
        validate="many_to_one",
    )
    for c in ("performance", "workingHours"):
        daily[c] = pd.to_numeric(daily[c], errors="raise")
    valid = (
        np.isfinite(daily.performance)
        & np.isfinite(daily.workingHours)
        & daily.performance.gt(0)
        & daily.workingHours.gt(0)
    )
    daily["missingNorms"] = (~valid).astype(int)
    daily["rawHours"] = daily.mass * daily.workingHours / daily.performance.where(valid)
    if not np.isfinite(daily.loc[valid, "rawHours"]).all():
        raise ValueError("Nonfinite productive hours")
    line_keys = ["scenarioKey", "lineKey", "date"]
    loads = daily.groupby(line_keys, as_index=False).agg(
        rawHours=("rawHours", "sum"), missingNorms=("missingNorms", "sum")
    )
    loads["active"] = 1
    grid = pd.MultiIndex.from_product(
        [scenarios, lines.lineKey, pd.date_range(month.start_time, month.end_time)],
        names=line_keys,
    ).to_frame(index=False)
    result = grid.merge(loads, on=line_keys, how="left", validate="one_to_one")
    stop_days = stops.groupby(line_keys, as_index=False).durationHours.sum()
    result = result.merge(stop_days, on=line_keys, how="left", validate="one_to_one")
    result = result.rename(columns={"durationHours": "stopHours"})
    cols = ["rawHours", "missingNorms", "active", "stopHours"]
    result[cols] = result[cols].fillna(0)
    result["month"] = month.start_time
    result = result.merge(
        coverage,
        on=["scenarioKey", "lineKey", "month"],
        how="left",
        validate="many_to_one",
    )
    result["isOverloaded"] = result.rawHours + result.stopHours > 23 + EPSILON
    return result


def _series_count(production):
    # Track the previous ACTIVE day per line, not the previous calendar day.
    # Only the small aggregated daily product sets are iterated here.
    count = 0
    for _, line in production.groupby("lineKey"):
        previous = set()
        for _, day in line.groupby("date", sort=True):
            current = set(day.material)
            count += len(current - previous)
            previous = current
    return count


def relative_components(c, d, n, c0, d0, n0, error, weights=WEIGHTS):
    """Return contributions in points; weights are overrideable only in analysis."""
    if not np.isfinite([c, d, n, c0, d0, n0, error, *weights]).all():
        raise ValueError("Nonfinite index input")
    if min(c, n, c0, n0, error) < 0 or not (0 <= d <= 1 and 0 <= d0 <= 1):
        raise ValueError("Invalid index input")
    if len(weights) != 3 or min(weights) < 0 or abs(sum(weights) - 1) > 1e-12:
        raise ValueError("Weights must be three nonnegative values summing to one")
    return {
        "compactness": 100 * weights[0] * ((c0 - c) / max(c0, c) if max(c0, c) else 0),
        "dates": 100 * weights[1] * (d - d0),
        "series": 100 * weights[2] * ((n0 - n) / max(n0, n) if max(n0, n) else 0),
        "volume": -100 * error,
    }


def _stop_signature(stops):
    return stops.groupby(["lineKey", "date", "stopType"]).durationHours.sum().to_dict()


def _fingerprint(frame):
    normalized = frame.reindex(sorted(frame.columns), axis=1).sort_values(
        sorted(frame.columns)
    )
    payload = normalized.to_csv(
        index=False, float_format="%.17g", date_format="%Y-%m-%dT%H:%M:%S"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def evaluate_plans(
    plans,
    orders,
    norms,
    stops,
    coverage,
    lines,
    contract,
    month,
    site_key=1,
    *,
    scenarios=None,
    context_valid=True,
):
    """Evaluate one site's full month. Absence is distinguished by the contract.

    Input frames must be scoped to one site; orders have no site in the model.
    Malformed schemas/keys fail fast. Missing norms/coverage yield a status.
    """
    month = pd.Period(month, freq="M")
    scenarios = sorted(
        scenarios
        if scenarios is not None
        else set(plans.scenarioKey) | set(contract.scenarioKey) | {"factory_plan"}
    )
    _check_keys(contract, ["scenarioKey", "siteKey", "month"], unique=True)
    contract = _dates(contract, "month", month)
    if not contract.month.eq(month.start_time).all():
        raise ValueError("Contract month must start on day one")
    if not contract.siteKey.eq(site_key).all():
        raise ValueError("Scope the contract to the selected site")
    if "siteKey" in lines and not lines.siteKey.eq(site_key).all():
        raise ValueError("Scope the lines to the selected site")
    for flag in ("isProvided", "referenceApproved", "inputsConfirmed"):
        if not contract[flag].dropna().isin([True, False]).all():
            raise ValueError(f"Invalid contract flag: {flag}")
    production = _positive_mass(_dates(plans, "date", month))
    orders = _positive_mass(_dates(orders, "date", month))
    _check_keys(orders, ["date", "material"])
    load = build_line_day_load(plans, norms, stops, coverage, lines, scenarios, month)
    stops = _dates(stops, "date", month)
    order_pairs = set(orders[["date", "material"]].itertuples(index=False, name=None))
    factory = production.loc[production.scenarioKey.eq("factory_plan")]
    factory_mass = factory.groupby("material").mass.sum()
    m0 = factory_mass.sum()
    contracts = contract.set_index("scenarioKey")
    result = {}
    for scenario in scenarios:
        plan = production.loc[production.scenarioKey.eq(scenario)]
        scenario_load = load.loc[load.scenarioKey.eq(scenario)]
        declared = scenario in contracts.index
        row = contracts.loc[scenario] if declared else None
        ready = (
            bool(context_valid)
            and len(lines) > 0
            and bool(order_pairs)
            and declared
            and all(
                pd.notna(row[c]) and bool(row[c])
                for c in ("isProvided", "referenceApproved", "inputsConfirmed")
            )
            and pd.notna(row.comparisonSetID)
            and bool(str(row.comparisonSetID).strip())
            and row.methodVersion == METHOD_VERSION
            and scenario_load.missingNorms.sum() == 0
            and scenario_load.isComplete.eq(True).all()
        )
        pairs = set(plan[["date", "material"]].itertuples(index=False, name=None))
        mass = plan.groupby("material").mass.sum()
        both = pd.concat(
            [factory_mass.rename("factory"), mass.rename("plan")], axis=1
        ).fillna(0)
        error = float((both.plan - both.factory).abs().sum() / m0) if m0 > 0 else None
        outside = (both.plan - both.factory).abs() > 0.05 * both.factory + EPSILON
        result[scenario] = {
            "ready": bool(ready),
            "comparisonSetID": str(row.comparisonSetID) if declared else None,
            "lineDays": int(scenario_load.active.sum()),
            "dateMatch": (
                len(pairs & order_pairs) / len(order_pairs) if order_pairs else None
            ),
            "series": _series_count(plan),
            "mass": float(mass.sum()),
            "rawHours": (
                float(scenario_load.rawHours.sum())
                if not scenario_load.missingNorms.sum()
                else None
            ),
            "missingNorms": int(scenario_load.missingNorms.sum()),
            "incompleteLineDays": int((~scenario_load.isComplete.eq(True)).sum()),
            "overloadedLineDays": int(scenario_load.isOverloaded.sum()),
            "volumeError": error,
            "productsOutsideTolerance": int(outside.sum()),
            "planHash": _fingerprint(plan),
        }
    base = result["factory_plan"]
    factory_stops = _stop_signature(stops.loc[stops.scenarioKey.eq("factory_plan")])
    for scenario, values in result.items():
        comparable = (
            values["ready"]
            and base["ready"]
            and m0 > 0
            and values["comparisonSetID"] == base["comparisonSetID"]
            and _stop_signature(stops.loc[stops.scenarioKey.eq(scenario)])
            == factory_stops
        )
        values["comparable"] = bool(comparable)
        contributions = None
        if comparable:
            contributions = relative_components(
                values["lineDays"],
                values["dateMatch"],
                values["series"],
                base["lineDays"],
                base["dateMatch"],
                base["series"],
                values["volumeError"],
            )
        if not context_valid:
            code = 1
        elif not base["ready"] or m0 <= 0:
            code = 2
        elif not values["ready"]:
            code = 3
        elif not comparable:
            code = 4
        elif base["overloadedLineDays"]:
            code = 5
        elif values["overloadedLineDays"]:
            code = 6
        elif values["mass"] == 0:
            code = 8
        elif values["productsOutsideTolerance"]:
            code = 7
        else:
            code = 0
        status = {
            0: "Исследовательская версия; суточная мощность проверена",
            1: "Выберите одну площадку, полный месяц и один сценарий без детализации",
            2: "Эталон отсутствует, не подтвержден или его данные неполны",
            3: "Нет обязательных данных: нормы, остановки, заказы или контракт",
            4: "Вводные несопоставимы: контракт или остановки отличаются от эталона",
            5: "Эталон не прошел проверку суточной мощности",
            6: f"План перегружен: {values['overloadedLineDays']} линия-дней",
            7: "Объемы вне допуска; оценка ограничена",
            8: "Пустой план; объемы вне допуска",
        }[code]
        raw = max(0.0, 100 + sum(contributions.values())) if contributions else None
        score = (
            0.0
            if code == 8
            else min(100.0, raw) if code == 7 else raw if code == 0 else None
        )
        values.update(
            statusCode=code,
            status=status,
            score=score,
            contributions=contributions,
            delta=score - 100 if score is not None else None,
            adjustment=(
                (score - 100 - sum(contributions.values()))
                if score is not None
                else None
            ),
        )
    return {
        "methodVersion": METHOD_VERSION,
        "month": str(month),
        "siteKey": site_key,
        "weights": WEIGHTS,
        "excelVerified": False,
        "inputHashes": {
            "orders": _fingerprint(orders),
            "norms": _fingerprint(norms),
            "lines": _fingerprint(lines),
            "factory": _fingerprint(factory),
            "factoryStops": _fingerprint(
                stops.loc[stops.scenarioKey.eq("factory_plan")]
            ),
            "contract": _fingerprint(contract),
            "coverage": _fingerprint(coverage),
        },
        "scenarios": result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--month", default="2027-04", help="Comparison month (YYYY-MM)")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent / "demo"
    reference = root / "reference/site_line_info.xlsx"
    with pd.ExcelFile(reference) as workbook:
        lines = pd.read_excel(workbook, sheet_name="line")
        sections = pd.read_excel(workbook, sheet_name="section")
        lines = lines.merge(
            sections[["sectionKey", "siteKey"]], on="sectionKey", validate="many_to_one"
        )
        norms = resolve_performance_line_keys(
            pd.read_excel(workbook, sheet_name="performance_info"), lines
        )
        scenarios = pd.read_excel(workbook, sheet_name="scenario").scenarioCode.tolist()
    report = evaluate_plans(
        pd.read_excel(root / "processed/packaging_data.xlsx"),
        pd.read_excel(root / "processed/orders_data.xlsx"),
        norms,
        pd.read_excel(root / "sources/mandatory_stops.xlsx"),
        pd.read_csv(root / "sources/stop_coverage.csv"),
        lines,
        pd.read_csv(root / "reference/ikp_comparison.csv"),
        args.month,
        scenarios=scenarios,
    )
    # Sensitivity is diagnostic; it cannot override overload/missing-data gates.
    base = report["scenarios"]["factory_plan"]
    report["sensitivity"] = {}
    for weights in (
        (0.5, 0.35, 0.15),
        WEIGHTS,
        (0.7, 0.15, 0.15),
        (0.6, 0.2, 0.2),
        (0.6, 0.3, 0.1),
    ):
        scores = {}
        for scenario, value in report["scenarios"].items():
            if value["statusCode"] not in (0, 7, 8):
                scores[scenario] = None
                continue
            parts = relative_components(
                value["lineDays"],
                value["dateMatch"],
                value["series"],
                base["lineDays"],
                base["dateMatch"],
                base["series"],
                value["volumeError"],
                weights,
            )
            raw = max(0, 100 + sum(parts.values()))
            scores[scenario] = (
                0
                if value["statusCode"] == 8
                else min(100, raw) if value["statusCode"] == 7 else raw
            )
        report["sensitivity"][str(weights)] = scores
    output = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    else:
        print(output)


if __name__ == "__main__":
    main()
