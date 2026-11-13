let
    source = ReadSheet("reference\product_info.xlsx", "product", {{"name", type text}, {"productGroup", type text}})
in
    source
