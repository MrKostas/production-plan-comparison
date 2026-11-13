// Connection-only query. Explicit lineKey supports multiple sites.
// A sheet without lineKey is interpreted only as legacy demo-site norms.
let
    source =
        Excel.Workbook(
            File.Contents(
                DemoRoot & "\reference\site_line_info.xlsx"
            ),
            null,
            true
        ),
    sheet = source{[Item = "performance_info", Kind = "Sheet"]}[Data],
    promoted = Table.PromoteHeaders(sheet, [PromoteAllScalars = true]),
    hasExplicitKey = Table.HasColumns(promoted, "lineKey"),
    keyed =
        if hasExplicitKey then
            promoted
        else
            let
                demoSiteLines =
                    Table.SelectRows(
                        line_info,
                        each Text.StartsWith([lineKey], "Демо-завод|")
                    ),
                aliases =
                    Table.AddColumn(
                        Table.SelectColumns(demoSiteLines, {"lineKey"}),
                        "line",
                        each Text.Split([lineKey], "|"){1}
                            & " №" & Text.AfterDelimiter([lineKey], "Линия №"),
                        type text
                    ),
                uniqueAliases = Table.Distinct(Table.SelectColumns(aliases, {"line"})),
                checkedAliases =
                    if Table.RowCount(uniqueAliases) <> Table.RowCount(aliases) then
                        error "Неоднозначные линии Демо-завод: добавьте lineKey в нормы"
                    else aliases,
                joined =
                    Table.NestedJoin(
                        promoted, {"line"}, checkedAliases, {"line"},
                        "Line", JoinKind.LeftOuter
                    )
            in
                Table.ExpandTableColumn(joined, "Line", {"lineKey"}, {"lineKey"}),
    // Unmatched legacy aliases do not participate in the fact join.
    // Keep them in the source workbook; explicit-key mode rejects unknown keys.
    mapped =
        if hasExplicitKey then keyed
        else Table.SelectRows(keyed, each [lineKey] <> null),
    legacyPairs =
        if hasExplicitKey then null
        else Table.Distinct(Table.SelectColumns(promoted, {"line", "product"})),
    checkedLegacy =
        if not hasExplicitKey and Table.RowCount(legacyPairs) <> Table.RowCount(promoted) then
            error "В performance_info повторяются пары line + product"
        else mapped,
    selected =
        Table.SelectColumns(
            checkedLegacy,
            {"lineKey", "product", "performance", "workingHours"}
        ),
    typed =
        Table.TransformColumnTypes(
            selected,
            {
                {"lineKey", type text},
                {"product", type text},
                {"performance", type number},
                {"workingHours", type number}
            }
        ),
    lineKeys = List.Buffer(line_info[lineKey]),
    invalidKeys =
        Table.SelectRows(
            typed,
            each [lineKey] = null or Text.Trim([lineKey]) = ""
                or not List.Contains(lineKeys, [lineKey])
                or [product] = null or Text.Trim([product]) = ""
        ),
    validKeys =
        if Table.RowCount(invalidKeys) > 0 then
            error "В performance_info пустые или неизвестные ключи; заполните lineKey и product"
        else typed,
    normalized =
        Table.TransformColumns(
            validKeys,
            {
                {
                    "performance",
                    each if _ = null or _ <= 0 then null else _,
                    type nullable number
                },
                {
                    "workingHours",
                    each if _ = null or _ <= 0 then null else _,
                    type nullable number
                }
            }
        ),
    distinctPairs = Table.Distinct(Table.SelectColumns(normalized, {"lineKey", "product"})),
    validated =
        if Table.RowCount(distinctPairs) <> Table.RowCount(normalized) then
            error "В performance_info повторяются пары lineKey + product"
        else
            normalized
in
    validated
