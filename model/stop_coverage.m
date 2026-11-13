// Completeness is confirmed separately for each month in stop_coverage.csv.
let
    source =
        Csv.Document(
            File.Contents(
                DemoRoot & "\sources\stop_coverage.csv"
            ),
            [Delimiter = ",", Columns = 4, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
        ),
    promoted = Table.PromoteHeaders(source, [PromoteAllScalars = true]),
    typed =
        Table.TransformColumnTypes(
            promoted,
            {
                {"scenarioKey", type text},
                {"lineKey", type text},
                {"month", type date},
                {"isComplete", type logical}
            },
            "en-US"
        ),
    scenarioCodes = List.Buffer(scenario_info[scenarioCode]),
    lineKeys = List.Buffer(line_info[lineKey]),
    invalid =
        Table.SelectRows(
            typed,
            each
                [scenarioKey] = null
                or not List.Contains(scenarioCodes, [scenarioKey])
                or [lineKey] = null
                or not List.Contains(lineKeys, [lineKey])
                or [month] = null
                or [month] <> Date.StartOfMonth([month])
                or [isComplete] = null
        ),
    keys =
        Table.Distinct(
            Table.SelectColumns(typed, {"scenarioKey", "lineKey", "month"})
        ),
    result =
        if Table.RowCount(invalid) > 0 then
            error "В stop_coverage есть пустые поля, неизвестные ключи или некорректный месяц"
        else if Table.RowCount(keys) <> Table.RowCount(typed) then
            error "В stop_coverage повторяются scenarioKey + lineKey + month"
        else
            typed
in
    result
