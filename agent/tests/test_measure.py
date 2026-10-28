import pytest

from scripts.measure import PDF_TS, cap_pages, prepare_text, read_text_cap


def test_pages_within_the_cap_are_all_kept():
    assert cap_pages(["aaa", "bbb"], 100) == ("aaa\nbbb", 2, False)


def test_whole_pages_are_dropped_past_the_cap():
    text, kept, truncated = cap_pages(["a" * 40] * 3, 90)
    assert (len(text), kept, truncated) == (81, 2, True)


def test_a_single_oversized_page_is_cut_at_the_cap():
    text, kept, truncated = cap_pages(["a" * 150], 100)
    assert (len(text), kept, truncated) == (100, 1, True)


def test_truncation_is_announced_in_front_of_the_text():
    assert prepare_text(["a" * 40] * 3, 90).startswith(
        "[Document tronqué : pages 1 à 2 sur 3]\n"
    )
    assert prepare_text(["aaa", "bbb"], 100) == "aaa\nbbb"


def test_cap_is_read_from_the_front_end_source():
    assert read_text_cap() > 0


def test_missing_cap_constant_fails_loudly(tmp_path):
    source = tmp_path / "pdf.ts"
    source.write_text("export const OTHER = 1;", encoding="utf-8")
    with pytest.raises(RuntimeError, match="PDF_TEXT_MAX_CHARS"):
        read_text_cap(source)


def test_underscore_separators_are_understood(tmp_path):
    source = tmp_path / "pdf.ts"
    source.write_text("export const PDF_TEXT_MAX_CHARS = 60_000;", encoding="utf-8")
    assert read_text_cap(source) == 60000
    assert PDF_TS.is_file()
