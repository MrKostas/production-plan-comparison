// Stop events for lines with positive production in the selected scenario/month.
// Inactive-line events remain available in the mandatory_stops source query.
let
    activeLines =
        Table.Distinct(
            Table.SelectColumns(dailyHours, {"scenarioKey", "lineKey"})
        ),
    joined =
        Table.NestedJoin(
            mandatory_stops,
            {"scenarioKey", "lineKey"},
            activeLines,
            {"scenarioKey", "lineKey"},
            "ActiveLine",
            JoinKind.Inner
        ),
    result = Table.RemoveColumns(joined, {"ActiveLine"})
in
    result
