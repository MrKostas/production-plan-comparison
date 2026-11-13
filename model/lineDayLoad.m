// Full scenario x registered line x calendar day grid, including idle lines.
// Requires the current performance_info/dailyHours definitions. Never uses
// capped workHours or activeStops. Load with scenario, line and date relations.
let
    month = Date.StartOfMonth(List.Min(calendar[date])),
    dates = List.Dates(month, Date.DaysInMonth(month), #duration(1, 0, 0, 0)),
    badCalendar = List.AnyTrue(List.Transform(calendar[date], each Date.StartOfMonth(_) <> month)),
    scenarioKeys = List.Buffer(scenario_info[scenarioCode]),
    lineKeys = List.Buffer(line_info[lineKey]),
    badDaily = Table.SelectRows(dailyHours, each
        not List.Contains(scenarioKeys, [scenarioKey])
        or not List.Contains(lineKeys, [lineKey]) or not List.Contains(dates, [date])
        or not List.Contains(product[name], [material])
        or [dailyMass] = null or [dailyMass] <= 0
        or Number.IsNaN([dailyMass]) or Number.Abs([dailyMass]) = #infinity
    ),
    checkedDaily = if badCalendar or Table.RowCount(badDaily) > 0
        then error "Некорректные даты или ключи дневного выпуска ИКП" else dailyHours,
    withMissing = Table.AddColumn(checkedDaily, "missingNorm", each
        if [performance] = null or [workingHours] = null then 1
        else if [performance] <= 0 or [workingHours] <= 0
            or Number.IsNaN([performance]) or Number.IsNaN([workingHours])
            or Number.Abs([performance]) = #infinity or Number.Abs([workingHours]) = #infinity
        then 1 else 0, Int64.Type),
    withRaw = Table.AddColumn(withMissing, "raw", each
        if [missingNorm] = 1 then null
        else [dailyMass] * [workingHours] / [performance], type nullable number),
    load = Table.Group(withRaw, {"scenarioKey", "lineKey", "date"}, {
        {"rawHours", each List.Sum([raw]), type nullable number},
        {"missingNorms", each List.Sum([missingNorm]), Int64.Type},
        {"active", each 1, Int64.Type}
    }),
    // IDs must be unique in mandatory_stops. Repeated business events with new
    // IDs are ambiguous without timestamps and must be reviewed, not doubled.
    eventKeys = {"scenarioKey", "lineKey", "date", "stopType", "durationHours"},
    stops = if Table.RowCount(Table.Distinct(mandatory_stops, eventKeys)) <> Table.RowCount(mandatory_stops)
        then error "В ИКП повторяются события остановок с разными ID" else mandatory_stops,
    stopTypes = Table.Group(stops, {"scenarioKey", "lineKey", "date", "stopType"}, {
        {"hours", each List.Sum([durationHours]), type number}
    }),
    stopDays = Table.Group(stopTypes, {"scenarioKey", "lineKey", "date"}, {
        {"stopHours", each List.Sum([hours]), type number},
        {"stopSignature", each Binary.ToText(Json.FromValue(
            Table.ToRecords(Table.Sort(Table.SelectColumns(_, {"stopType", "hours"}), {{"stopType", Order.Ascending}}))
        ), BinaryEncoding.Base64), type text}
    }),
    siteJoin = Table.NestedJoin(Table.SelectColumns(line_info, {"lineKey", "sectionKey"}),
        {"sectionKey"}, section_info, {"sectionKey"}, "Section", JoinKind.LeftOuter),
    lines = Table.ExpandTableColumn(siteJoin, "Section", {"siteKey"}, {"siteKey"}),
    withScenarios = Table.AddColumn(lines, "scenarioKey", each scenarioKeys),
    scenarioGrid = Table.ExpandListColumn(withScenarios, "scenarioKey"),
    withDates = Table.AddColumn(scenarioGrid, "date", each dates),
    grid = Table.TransformColumnTypes(Table.ExpandListColumn(withDates, "date"), {{"date", type date}}),
    loadJoin = Table.NestedJoin(grid, {"scenarioKey", "lineKey", "date"},
        load, {"scenarioKey", "lineKey", "date"}, "Load", JoinKind.LeftOuter),
    loadExpanded = Table.ExpandTableColumn(loadJoin, "Load", {"rawHours", "missingNorms", "active"}),
    stopsJoin = Table.NestedJoin(loadExpanded, {"scenarioKey", "lineKey", "date"},
        stopDays, {"scenarioKey", "lineKey", "date"}, "Stops", JoinKind.LeftOuter),
    stopsExpanded = Table.ExpandTableColumn(stopsJoin, "Stops", {"stopHours", "stopSignature"}),
    numbers = Table.ReplaceValue(stopsExpanded, null, 0, Replacer.ReplaceValue,
        {"rawHours", "missingNorms", "active", "stopHours"}),
    signatures = Table.ReplaceValue(numbers, null, "", Replacer.ReplaceValue, {"stopSignature"}),
    factoryStops = Table.SelectRows(stopDays, each [scenarioKey] = "factory_plan"),
    factoryJoin = Table.NestedJoin(signatures, {"lineKey", "date"}, factoryStops,
        {"lineKey", "date"}, "FactoryStops", JoinKind.LeftOuter),
    factoryExpanded = Table.ExpandTableColumn(factoryJoin, "FactoryStops", {"stopSignature"}, {"factoryStopSignature"}),
    factoryEmpty = Table.ReplaceValue(factoryExpanded, null, "", Replacer.ReplaceValue, {"factoryStopSignature"}),
    comparable = Table.AddColumn(factoryEmpty, "stopsComparable", each [stopSignature] = [factoryStopSignature], type logical),
    withMonth = Table.AddColumn(comparable, "month", each month, type date),
    coverageJoin = Table.NestedJoin(withMonth, {"scenarioKey", "lineKey", "month"},
        stop_coverage, {"scenarioKey", "lineKey", "month"}, "Coverage", JoinKind.LeftOuter),
    coverage = Table.ExpandTableColumn(coverageJoin, "Coverage", {"isComplete"}),
    contractJoin = Table.NestedJoin(coverage, {"scenarioKey", "siteKey", "month"},
        ikpComparison, {"scenarioKey", "siteKey", "month"}, "Contract", JoinKind.LeftOuter),
    contract = Table.ExpandTableColumn(contractJoin, "Contract",
        {"comparisonSetID", "methodVersion", "isProvided", "referenceApproved", "inputsConfirmed"}),
    withFund = Table.AddColumn(contract, "capacityHours", each 23.0, type number),
    result = Table.AddColumn(withFund, "isOverloaded", each
        [rawHours] + [stopHours] > [capacityHours] + 0.000001, type logical)
in
    result
