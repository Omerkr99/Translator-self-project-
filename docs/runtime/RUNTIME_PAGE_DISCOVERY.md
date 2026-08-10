# Runtime Page Discovery

A runtime page is a stable composition of active runtime object identities, not a saved screenshot. `RuntimePageDetector` uses set similarity to reuse a page across small state changes and creates a candidate for substantially different compositions. Candidates and observation counts persist in `runtime_pages.json`. The Visual Inspector shows the current candidate ID; naming, confirmation and merge controls remain pending.

Live verification on 2026-08-09 produced exactly two candidates:

- `runtime.page.1`: `main_menu.start`, `main_menu.prepare`, `progdat.group0` (classroom background).
- `runtime.page.2`: `category.photos`, `progdat.group2` (spoils-table background).

Returning from Photos to Main Menu reused `runtime.page.1` and increased its observation count; it did not create a duplicate. The detector therefore follows runtime asset composition across navigation rather than matching a captured screen template.
