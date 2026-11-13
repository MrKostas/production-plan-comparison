let
    source = ReadSheet("reference\site_line_info.xlsx", "line", {{"lineKey", type text}, {"sectionKey", Int64.Type}, {"lineName", type text}})
in
    source
