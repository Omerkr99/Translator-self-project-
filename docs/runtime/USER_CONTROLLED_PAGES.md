# User-Controlled Pages / Scenes

Milestone 7 of the post-audit development workflow, and the last of the
"convert today's proofs into reusable capabilities" tier before the
backlog (complex image formats, movies, audio, subtitles, persistent
build). Core rule, stated up front in the milestone spec and worth
repeating: **pages are organization metadata, never runtime detection.**
`gcrts.runtime_pages` must never decide *what a composition means* --
only a user does.

## What already existed, and was already compliant with 7.1

`gcrts/runtime_pages.py`'s `RuntimePageDetector.observe()` predates this
milestone and already got 7.1 right: it answers a purely mechanical
question ("have I seen this asset composition before, within a similarity
threshold"), auto-creates a `RuntimePage` when it hasn't, and never once
assigns that page a name or promotes it past `status=CANDIDATE`. Confirmed
with a new regression test
(`test_observe_never_assigns_a_name_or_promotes_status`) since nothing had
tested this invariant explicitly before.

## What was missing: 7.2, 7.3, 7.4 had no real implementation

`RuntimePage` had a `name` field that nothing ever set, and no
required/optional/ignored breakdown, no matching-mode choice, no variant
concept at all -- the auto-detector's implicit all-or-nothing Jaccard
similarity over the full observed set was the ONLY behavior that existed.

### 7.2 -- `RuntimePageDetector.create_named_page()`

The only function that ever sets `name`, `required_assets`,
`optional_assets`, `ignored_assets`, or `matching_mode` -- always an
explicit call, never invoked by `observe()`. Given a `page_id`, promotes
an existing candidate in place (keeping its observation history);
otherwise creates a fresh `USER_DEFINED` page. `required` defaults to the
full observed set (matches "this exact snapshot" until narrowed).

Visual Inspector UI: "Create Page..." opens `CreatePageDialog` -- a real
Tk dialog with a name field, a matching-mode dropdown, and three listboxes
(Required / Optional / Ignored, everything starts Required) with "move
selected to" buttons. Every field the user actually sets.

### 7.3 -- `MatchingMode` and `page_matches()`

Five modes, all inert until a user picks one via `create_named_page()`
(a raw candidate keeps the original Jaccard-over-`core_assets` behavior
forever, so nothing regresses for pages nobody has touched):

- `MANUAL_ONLY` -- never auto-matched by `observe()`, ever.
- `STRICT` -- required+optional must equal the observed set exactly
  (after removing ignored assets).
- `BALANCED` -- Jaccard similarity over required+optional vs. observed,
  the detector's threshold. This is the original behavior, kept as the
  default so promoting a candidate without touching the mode dropdown
  changes nothing about how it matches.
- `LOOSE` -- every required asset present is enough; extra/missing
  optional assets don't matter.
- `CUSTOM` -- like BALANCED but with a page-specific threshold
  (`custom_threshold`) instead of the detector's global default.

### 7.4 -- `RuntimePageDetector.declare_variant()`

Purely a user action, exactly matching the milestone's own example (a
menu with a different highlighted selection). `observe()`'s similarity
matching answers "is this the same runtime composition" -- a mechanical
fact; whether two *different* compositions should be treated as one
conceptual Page is a judgment call only a person makes. Never inferred:
two similar-but-not-identical pages stay completely unrelated
(`variant_of=None`) until a user explicitly links them.

## Live-verified, not just unit-tested

Loaded a real main-menu scene, captured it through the actual Visual
Inspector, and drove the real `CreatePageDialog` (via scheduled `after()`
callbacks while its modal `wait_window` was blocking -- not external
clicking, but every line of dialog-handling code that would run for a
real click ran identically): named it "Main Menu (live test)", moved
`progdat.group0` from Required to Optional, clicked Create. Confirmed a
real `USER_DEFINED` page landed in `runtime_pages.json` with exactly the
chosen fields (`required=[main_menu.prepare, main_menu.start]`,
`optional=[progdat.group0]`, `mode=BALANCED`), observation history
preserved from the auto-candidate it promoted.

## Tests

`tests/test_runtime_pages.py` grew from 2 to 12 tests: the two original
(untouched, still passing unmodified) plus 10 new covering the
never-auto-named invariant, candidate promotion with history preservation,
fresh page creation, all five matching modes' actual matching behavior
(not just that the field can be set), explicit variant declaration and its
rejection of an unknown target, and full save/load round-tripping of every
new field. Full suite: **400 passed** (390 + 10), no regressions.
