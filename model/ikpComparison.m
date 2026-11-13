// Explicit delivery/approval contract. A missing plan is not an empty plan.
let
    source = Csv.Document(
        File.Contents(DemoRoot & "\reference\ikp_comparison.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    headers = Table.PromoteHeaders(source, [PromoteAllScalars = true]),
    typed = Table.TransformColumnTypes(headers, {
        {"comparisonSetID", type text}, {"methodVersion", type text},
        {"scenarioKey", type text}, {"siteKey", Int64.Type}, {"month", type date},
        {"isProvided", type logical}, {"referenceApproved", type logical},
        {"inputsConfirmed", type logical}
    }, "en-US"),
    invalid = Table.SelectRows(typed, each
        [comparisonSetID] = null or Text.Trim([comparisonSetID]) = ""
        or [methodVersion] <> "ikp-relative-v1"
        or not List.Contains(scenario_info[scenarioCode], [scenarioKey])
        or not List.Contains(site_info[siteKey], [siteKey])
        or [month] = null or [month] <> Date.StartOfMonth([month])
        or [isProvided] = null or [referenceApproved] = null or [inputsConfirmed] = null
    ),
    keys = Table.Distinct(Table.SelectColumns(typed, {"scenarioKey", "siteKey", "month"})),
    result =
        if Table.RowCount(invalid) > 0 then error "Некорректный контракт ИКП"
        else if Table.RowCount(keys) <> Table.RowCount(typed) then error "Повтор ключа контракта ИКП"
        else typed
in
    result
