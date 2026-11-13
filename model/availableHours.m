// One row per calendar date and line-product pair active in a scenario/month.
// The current ETL guarantees one selected month across plans and orders.
let
    activePairs =
        Table.Distinct(
            Table.SelectColumns(
                dailyHours,
                {"scenarioKey", "lineKey", "material", "workingHours"}
            )
        ),
    withDates =
        Table.AddColumn(
            activePairs,
            "Dates",
            each Table.SelectColumns(calendar, {"date"}),
            type table
        ),
    result =
        Table.ExpandTableColumn(
            withDates,
            "Dates",
            {"date"},
            {"date"}
        ),
    typed = Table.TransformColumnTypes(result, {{"date", type date}})
in
    typed
