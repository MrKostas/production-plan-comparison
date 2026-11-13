(relativePath as text, sheetName as text, columns as list) as table =>
let
    source = Excel.Workbook(File.Contents(DemoRoot & "\" & relativePath), null, true),
    sheet = source{[Item = sheetName, Kind = "Sheet"]}[Data],
    headers = Table.PromoteHeaders(sheet, [PromoteAllScalars = true]),
    typed = Table.TransformColumnTypes(headers, columns, "en-US")
in
    typed
