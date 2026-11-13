let
    first = Date.StartOfMonth(List.Min(main[date])),
    last = Date.EndOfMonth(first),
    dates = Table.FromColumns({List.Dates(first, Duration.Days(last - first) + 1, #duration(1, 0, 0, 0))}, type table [date = date]),
    day = Table.AddColumn(dates, "day", each Date.Day([date]), Int64.Type),
    month = Table.AddColumn(day, "month", each Date.Month([date]), Int64.Type),
    year = Table.AddColumn(month, "year", each Date.Year([date]), Int64.Type),
    week = Table.AddColumn(year, "weekNumber", each Date.WeekOfYear([date], Day.Monday), Int64.Type)
in
    week
