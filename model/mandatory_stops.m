// Canonical source query. Load to Power Query as a connection only;
// activeStops is the fact table loaded to the Data Model.
let
    source =
        Excel.Workbook(
            File.Contents(
                DemoRoot & "\sources\mandatory_stops.xlsx"
            ),
            null,
            true
        ),
    sheet = source{[Item = "mandatory_stops", Kind = "Sheet"]}[Data],
    promoted = Table.PromoteHeaders(sheet, [PromoteAllScalars = true]),
    selected =
        Table.SelectColumns(
            promoted,
            {"stopID", "scenarioKey", "lineKey", "date", "stopType", "durationHours"}
        ),
    typed =
        Table.TransformColumnTypes(
            selected,
            {
                {"stopID", Int64.Type},
                {"scenarioKey", type text},
                {"lineKey", type text},
                {"date", type date},
                {"stopType", type text},
                {"durationHours", type number}
            }
        ),
    reportMonth = Date.StartOfMonth(List.Min(calendar[date])),
    scenarioCodes = List.Buffer(scenario_info[scenarioCode]),
    lineKeys = List.Buffer(line_info[lineKey]),
    invalid =
        Table.SelectRows(
            typed,
            each
                [stopID] = null
                or [scenarioKey] = null
                or Text.Trim([scenarioKey]) = ""
                or not List.Contains(scenarioCodes, [scenarioKey])
                or [lineKey] = null
                or Text.Trim([lineKey]) = ""
                or not List.Contains(lineKeys, [lineKey])
                or [date] = null
                or Date.StartOfMonth([date]) <> reportMonth
                or [stopType] = null
                or Text.Trim([stopType]) = ""
                or [durationHours] = null
                or [durationHours] <= 0
        ),
    distinctIDs = Table.Distinct(Table.SelectColumns(typed, {"stopID"})),
    valid =
        if Table.RowCount(invalid) > 0 then
            error "В mandatory_stops есть пустые поля, неизвестные ключи, неположительные часы или дата вне месяца плана"
        else if Table.RowCount(distinctIDs) <> Table.RowCount(typed) then
            error "В mandatory_stops повторяются stopID"
        else
            typed
in
    valid
