from gcrts.runtime_pages import MatchingMode, PageStatus, RuntimePageDetector


def test_same_stable_composition_reuses_page_and_new_composition_creates_candidate():
    d=RuntimePageDetector(.6);a,new=d.observe({"background","start","prepare"});assert new
    again,new=d.observe({"background","start"});assert not new and again is a
    b,new=d.observe({"table","photos"});assert new and b is not a


def test_page_candidates_persist_and_revisit_without_duplicate(tmp_path):
    path=tmp_path/"pages.json";d=RuntimePageDetector();page,_=d.observe({"background","photos"});d.save(path);loaded=RuntimePageDetector.load(path);again,new=loaded.observe({"background","photos"});assert not new and again.page_id==page.page_id


def test_observe_never_assigns_a_name_or_promotes_status():
    """7.1: composition detection is purely mechanical -- observe() must
    never invent a semantic name or move a page past CANDIDATE."""
    d = RuntimePageDetector()
    page, _ = d.observe({"main_menu.start", "main_menu.prepare", "progdat.group0"})
    assert page.name is None
    assert page.status == PageStatus.CANDIDATE
    for _ in range(5):
        d.observe({"main_menu.start", "main_menu.prepare", "progdat.group0"})
    assert page.name is None and page.status == PageStatus.CANDIDATE


def test_create_named_page_promotes_candidate_and_keeps_history():
    d = RuntimePageDetector()
    candidate, _ = d.observe({"main_menu.start", "main_menu.prepare", "progdat.group0"})
    d.observe({"main_menu.start", "main_menu.prepare", "progdat.group0"})  # bump observations
    assert candidate.observations == 2

    named = d.create_named_page(
        {"main_menu.start", "main_menu.prepare", "progdat.group0"},
        name="Main Menu",
        page_id=candidate.page_id,
    )

    assert named is candidate  # promoted in place, not a duplicate
    assert named.name == "Main Menu"
    assert named.status == PageStatus.USER_DEFINED
    assert named.observations == 2  # history preserved


def test_create_named_page_without_page_id_creates_fresh_user_defined_page():
    d = RuntimePageDetector()
    page = d.create_named_page({"category.photos", "progdat.group2"}, name="Photos")
    assert page.status == PageStatus.USER_DEFINED
    assert page.name == "Photos"
    assert page in d.pages


def test_manual_only_page_is_never_auto_matched():
    d = RuntimePageDetector()
    page = d.create_named_page(
        {"main_menu.start", "main_menu.prepare"}, name="Main Menu (manual)",
        matching_mode=MatchingMode.MANUAL_ONLY,
    )
    _, is_new = d.observe({"main_menu.start", "main_menu.prepare"})
    assert is_new  # MANUAL_ONLY page must never be matched by observe(), even on an exact composition repeat


def test_strict_mode_requires_exact_match_within_scope():
    d = RuntimePageDetector()
    page = d.create_named_page(
        {"a", "b"}, name="Strict page", required={"a", "b"}, matching_mode=MatchingMode.STRICT,
    )
    matched, is_new = d.observe({"a", "b"})
    assert not is_new and matched is page
    matched2, is_new2 = d.observe({"a", "b", "c"})  # extra asset -- STRICT must reject
    assert is_new2


def test_loose_mode_ignores_extra_and_missing_optional_assets():
    d = RuntimePageDetector()
    page = d.create_named_page(
        {"a", "b"}, name="Loose page", required={"a"}, optional={"b"}, matching_mode=MatchingMode.LOOSE,
    )
    matched, is_new = d.observe({"a", "b", "z", "y", "x"})  # required present, plus lots of unrelated extras
    assert not is_new and matched is page


def test_custom_threshold_overrides_detector_default():
    d = RuntimePageDetector(similarity=0.99)  # detector default would reject a loose match
    page = d.create_named_page(
        {"a", "b", "c"}, name="Custom page", required={"a", "b", "c"},
        matching_mode=MatchingMode.CUSTOM, custom_threshold=0.4,
    )
    matched, is_new = d.observe({"a", "b"})  # score = 2/3 = 0.667 -- fails 0.99 default, passes page's own 0.4
    assert not is_new and matched is page


def test_declare_variant_is_explicit_never_inferred():
    d = RuntimePageDetector()
    primary = d.create_named_page({"a", "b"}, name="Menu")
    variant = d.create_named_page({"a", "b", "cursor_on_item2"}, name="Menu (item 2 selected)")
    assert variant.variant_of is None  # never auto-linked just for being similar

    d.declare_variant(variant.page_id, primary.page_id)

    assert variant.variant_of == primary.page_id
    assert d.variants_of(primary.page_id) == [variant]


def test_declare_variant_rejects_unknown_target():
    d = RuntimePageDetector()
    page = d.create_named_page({"a"}, name="Solo")
    try:
        d.declare_variant(page.page_id, "runtime.page.999")
        assert False, "expected ValueError for unknown variant target"
    except ValueError:
        pass


def test_user_defined_fields_survive_save_and_load(tmp_path):
    path = tmp_path / "pages.json"
    d = RuntimePageDetector()
    primary = d.create_named_page(
        {"a", "b"}, name="Menu", required={"a"}, optional={"b"}, ignored={"cursor"},
        matching_mode=MatchingMode.LOOSE,
    )
    variant = d.create_named_page({"a", "b", "cursor"}, name="Menu variant")
    d.declare_variant(variant.page_id, primary.page_id)
    d.save(path)

    reloaded = RuntimePageDetector.load(path)
    reloaded_primary = next(p for p in reloaded.pages if p.page_id == primary.page_id)
    reloaded_variant = next(p for p in reloaded.pages if p.page_id == variant.page_id)

    assert reloaded_primary.name == "Menu"
    assert reloaded_primary.required_assets == frozenset({"a"})
    assert reloaded_primary.optional_assets == frozenset({"b"})
    assert reloaded_primary.ignored_assets == frozenset({"cursor"})
    assert reloaded_primary.matching_mode == MatchingMode.LOOSE.value
    assert reloaded_variant.variant_of == primary.page_id
