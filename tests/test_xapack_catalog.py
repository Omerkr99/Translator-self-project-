from gcrts.xapack_catalog import build_catalog, catalog_entry_for_lba, catalog_entry_for_path


def test_build_catalog_has_43_entries():
    catalog = build_catalog()
    assert len(catalog) == 43


def test_catalog_entries_are_contiguous_and_ordered():
    catalog = build_catalog()
    for i in range(len(catalog) - 1):
        assert catalog[i].end_lba == catalog[i + 1].start_lba
        assert catalog[i].start_lba < catalog[i].end_lba


def test_catalog_entry_sector_count_and_byte_size_are_consistent():
    entry = catalog_entry_for_path("DAT/XA1/XAPACK08.BIN")
    assert entry is not None
    assert entry.sector_count == entry.end_lba - entry.start_lba
    assert entry.byte_size == entry.sector_count * 2352


def test_catalog_entry_for_path_known_file():
    entry = catalog_entry_for_path("DAT/XA1/XAPACK08.BIN")
    assert entry is not None
    assert entry.start_lba == 126218
    assert entry.index == 8


def test_catalog_entry_for_path_unknown_file_is_none():
    assert catalog_entry_for_path("DAT/XA1/NOPE.BIN") is None


def test_catalog_entry_for_lba_matches_known_anchor():
    entry = catalog_entry_for_lba(126921)
    assert entry is not None
    assert entry.disc_path == "DAT/XA1/XAPACK08.BIN"


def test_catalog_entry_for_lba_out_of_range_is_none():
    assert catalog_entry_for_lba(0) is None
    assert catalog_entry_for_lba(999999) is None


def test_catalog_entry_filename_property():
    entry = catalog_entry_for_path("DAT/XA2/XAPACK42.BIN")
    assert entry.filename == "XAPACK42.BIN"
