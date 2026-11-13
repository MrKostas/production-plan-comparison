// One coverage status for every active scenario-line pair in the loaded month.
// Load to the Data Model; relate scenarioKey and lineKey to their dimensions.
let
    reportMonth = Date.StartOfMonth(List.Min(calendar[date])),
    activeLines =
        Table.Distinct(
            Table.SelectColumns(dailyHours, {"scenarioKey", "lineKey"})
        ),
    withMonth =
        Table.AddColumn(activeLines, "month", each reportMonth, type date),
    joined =
        Table.NestedJoin(
            withMonth,
            {"scenarioKey", "lineKey", "month"},
            stop_coverage,
            {"scenarioKey", "lineKey", "month"},
            "Coverage",
            JoinKind.LeftOuter
        ),
    result =
        Table.ExpandTableColumn(
            joined,
            "Coverage",
            {"isComplete"},
            {"isComplete"}
        )
in
    result
