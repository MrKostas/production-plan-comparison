let
    source = ReadSheet("reference\site_line_info.xlsx", "site", {{"siteKey", Int64.Type}, {"siteName", type text}})
in
    source
