let
    source = ReadSheet("processed\orders_data.xlsx", "main", {{"mass", type number}, {"date", type date}, {"material", type text}}),
    selected = Table.SelectRows(source, each [mass] <> null and [mass] > 0)
in
    selected
