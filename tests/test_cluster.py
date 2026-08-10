from gcrts.cluster import cluster_strings
from gcrts.extractor import ExtractedString


def make_string(offset: int, length: int, text: str = "x") -> ExtractedString:
    return ExtractedString(offset=offset, text=text, encoding="ascii", length=length)


def test_empty_input():
    assert cluster_strings([]) == []


def test_single_string_is_one_cluster():
    strings = [make_string(0, 4)]
    clusters = cluster_strings(strings, max_gap=8)
    assert len(clusters) == 1
    assert clusters[0].start_offset == 0
    assert clusters[0].end_offset == 4


def test_close_strings_merge_into_one_cluster():
    # ends at 4, next starts at 6 -> gap of 2, within max_gap=8
    strings = [make_string(0, 4), make_string(6, 4)]
    clusters = cluster_strings(strings, max_gap=8)
    assert len(clusters) == 1
    assert len(clusters[0].strings) == 2
    assert clusters[0].start_offset == 0
    assert clusters[0].end_offset == 10


def test_distant_strings_form_separate_clusters():
    # ends at 4, next starts at 1000 -> gap way beyond max_gap
    strings = [make_string(0, 4), make_string(1000, 4)]
    clusters = cluster_strings(strings, max_gap=8)
    assert len(clusters) == 2
    assert clusters[0].strings == [strings[0]]
    assert clusters[1].strings == [strings[1]]


def test_unsorted_input_is_sorted_by_offset():
    strings = [make_string(100, 4), make_string(0, 4)]
    clusters = cluster_strings(strings, max_gap=8)
    assert len(clusters) == 2
    assert clusters[0].start_offset == 0
    assert clusters[1].start_offset == 100


def test_cluster_ids_are_sequential():
    strings = [make_string(0, 4), make_string(1000, 4), make_string(2000, 4)]
    clusters = cluster_strings(strings, max_gap=8)
    assert [c.cluster_id for c in clusters] == [0, 1, 2]
