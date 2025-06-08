import io

from scripts.clean_logs import _read_lines, clean_lines


def test_read_lines_ignores_empty_lines():
    data = """line1

 line2


 line3
 """
    fh = io.StringIO(data)
    assert _read_lines(fh) == ["line1", "line2", "line3"]


def test_clean_lines_counts_duplicates():
    lines = ["alpha", "alpha", "beta", "gamma", "beta"]
    result = clean_lines(lines)
    assert len(result) == 3
    assert "[2] alpha" in result
    assert "[2] beta" in result
    assert "gamma" in result
