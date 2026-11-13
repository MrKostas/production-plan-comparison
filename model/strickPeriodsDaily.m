// Replace the current strickPeriodsDaily query with this definition.
// A gap without production does not end a series. A product starts a new
// series when it was absent on the line's previous active production day.
let
    daily =
        Table.Group(
            main,
            {"scenarioKey", "lineKey", "material", "date"},
            {{"dailyMass", each List.Sum([mass]), type number}}
        ),
    lineDays =
        Table.Distinct(
            Table.SelectColumns(daily, {"scenarioKey", "lineKey", "date"})
        ),
    byLine =
        Table.Group(
            lineDays,
            {"scenarioKey", "lineKey"},
            {
                {
                    "Rows",
                    (lineRows as table) as table =>
                        let
                            sorted = Table.Sort(lineRows, {{"date", Order.Ascending}}),
                            dates = List.Buffer(sorted[date]),
                            indexed =
                                Table.AddIndexColumn(
                                    sorted, "LineDayIndex", 0, 1, Int64.Type
                                ),
                            withPrevious =
                                Table.AddColumn(
                                    indexed,
                                    "PreviousActiveDate",
                                    each
                                        if [LineDayIndex] = 0
                                        then null
                                        else dates{[LineDayIndex] - 1},
                                    type nullable date
                                )
                        in
                            withPrevious,
                    type table
                }
            }
        ),
    previousDays =
        Table.ExpandTableColumn(
            byLine,
            "Rows",
            {"date", "PreviousActiveDate"},
            {"date", "PreviousActiveDate"}
        ),
    withPrevious =
        Table.NestedJoin(
            daily,
            {"scenarioKey", "lineKey", "date"},
            previousDays,
            {"scenarioKey", "lineKey", "date"},
            "PreviousDay",
            JoinKind.LeftOuter
        ),
    expandedPrevious =
        Table.ExpandTableColumn(
            withPrevious,
            "PreviousDay",
            {"PreviousActiveDate"},
            {"PreviousActiveDate"}
        ),
    withPriorProduct =
        Table.NestedJoin(
            expandedPrevious,
            {"scenarioKey", "lineKey", "material", "PreviousActiveDate"},
            daily,
            {"scenarioKey", "lineKey", "material", "date"},
            "PriorProduct",
            JoinKind.LeftOuter
        ),
    withStart =
        Table.AddColumn(
            withPriorProduct,
            "IsStart",
            each Table.IsEmpty([PriorProduct]),
            type logical
        ),
    withoutJoin = Table.RemoveColumns(withStart, {"PriorProduct"}),
    byProduct =
        Table.Group(
            withoutJoin,
            {"scenarioKey", "lineKey", "material"},
            {
                {
                    "Rows",
                    (productRows as table) as table =>
                        let
                            sorted =
                                Table.Sort(productRows, {{"date", Order.Ascending}}),
                            withAnchor =
                                Table.AddColumn(
                                    sorted,
                                    "PeriodAnchor",
                                    each if [IsStart] then [date] else null,
                                    type nullable date
                                ),
                            filled = Table.FillDown(withAnchor, {"PeriodAnchor"}),
                            indexed =
                                Table.AddIndexColumn(
                                    filled, "DayIndex", 0, 1, Int64.Type
                                )
                        in
                            Table.SelectColumns(
                                indexed,
                                {"date", "dailyMass", "DayIndex", "PeriodAnchor"}
                            ),
                    type table
                }
            }
        ),
    result =
        Table.ExpandTableColumn(
            byProduct,
            "Rows",
            {"date", "dailyMass", "DayIndex", "PeriodAnchor"},
            {"date", "dailyMass", "DayIndex", "PeriodAnchor"}
        ),
    typed = Table.TransformColumnTypes(result, {
        {"date", type date}, {"dailyMass", type number},
        {"DayIndex", Int64.Type}, {"PeriodAnchor", type date}
    })
in
    typed
