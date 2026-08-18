import pytest
from tests.ooxml_fixture_factory import create_book
from rns_import_server.ooxml_semantics import OOXMLSemanticError, inventory, map_cell, map_formula

@pytest.mark.parametrize("row", [6,10,104])
def test_sanitized_package_inventory_and_mapping(tmp_path, row):
    path=tmp_path/"fixture.xlsx"; create_book(path,row)
    result=inventory(path)
    assert result.sheets and map_cell("A6",row) == ("A7" if row == 6 else "A6")

def test_formula_maps_quoted_sheet_and_fails_closed_for_structured_refs():
    assert map_formula("='Other sheet'!$A6", 6) == "='Other sheet'!$A7"
    for formula in ("=Table1[#Data]", "=[external.xlsx]Sheet1!A1"):
        with pytest.raises(OOXMLSemanticError): map_formula(formula, 6)
