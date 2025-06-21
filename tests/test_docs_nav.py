from scripts import check_docs_nav


def test_docs_navigation_complete():
    assert check_docs_nav.main() == 0
