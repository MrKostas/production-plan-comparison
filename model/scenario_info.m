let
    source = ReadSheet("reference\site_line_info.xlsx", "scenario", {{"scenarioCode", type text}, {"scenarioKey", Int64.Type}, {"scenarioName", type text}, {"scenarioOwner", type text}})
in
    source
