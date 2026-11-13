// Target query for daily productive and idle hours.
// Norms are resolved to site-qualified lineKey by performance_info.
let
    daily =
        Table.Group(
            main,
            {"scenarioKey", "lineKey", "material", "date"},
            {{"dailyMass", each List.Sum([mass]), type number}}
        ),
    withNorm =
        Table.NestedJoin(
            daily,
            {"lineKey", "material"},
            performance_info,
            {"lineKey", "product"},
            "Norm",
            JoinKind.LeftOuter
        ),
    expanded =
        Table.ExpandTableColumn(
            withNorm,
            "Norm",
            {"performance", "workingHours"},
            {"performance", "workingHours"}
        ),
    withWork =
        Table.AddColumn(
            expanded,
            "workHours",
            each
                if [performance] = null or [workingHours] = null then
                    null
                else
                    let
                        rawHours = [dailyMass] * [workingHours] / [performance]
                    in
                        if rawHours > [workingHours] then [workingHours] else rawHours,
            type nullable number
        ),
    withDowntime =
        Table.AddColumn(
            withWork,
            "downtimeHours",
            each
                if [performance] = null or [workingHours] = null then
                    null
                else
                    let
                        rawHours =
                            ([performance] - [dailyMass])
                            * [workingHours]
                            / [performance]
                    in
                        if rawHours < 0 then 0 else rawHours,
            type nullable number
        )
in
    withDowntime
