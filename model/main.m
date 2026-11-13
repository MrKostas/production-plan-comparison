let
    source = ReadSheet("processed\packaging_data.xlsx", "main", {{"mass", type number}, {"date", type date}, {"material", type text}, {"lineKey", type text}, {"scenarioKey", type text}}),
    selected = Table.SelectRows(source, each [mass] <> null and [mass] > 0)
in
    selected
