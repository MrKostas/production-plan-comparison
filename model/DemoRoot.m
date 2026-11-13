let
    config = Excel.CurrentWorkbook(){[Name = "DemoPath"]}[Content],
    input = Text.Trim(Text.From(config{0}[Column1])),
    root = if input = "" then error "Укажите путь к папке demo в параметре DemoPath."
           else Text.TrimEnd(input, {"\", "/"})
in
    root
