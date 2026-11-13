let
    groups = Table.Distinct(Table.SelectColumns(product, {"productGroup"})),
    named = Table.RenameColumns(groups, {{"productGroup", "name"}})
in
    named
