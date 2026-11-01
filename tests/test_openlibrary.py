from mylittlebooklist import openlibrary


def test_normalize_isbn() -> None:
    assert openlibrary.normalize_isbn("3-499-22572-x") == "349922572X"
    assert openlibrary.normalize_isbn("123") is None
    assert openlibrary.format_isbn("9783499225727") == "978-3-499-22572-7"
    assert (
        openlibrary.format_isbn("349922572X") == "349922572X"
    )  # wrong check digit stays unchanged
