# Translation View

Translation View filters the current context to text-bearing screen objects, regardless of storage mechanism. It therefore treats a rasterized menu label and runtime dialogue as peers while preserving their different edit routes.

Each text object carries one of: `ORIGINAL`, `TRANSLATED`, `PARTIAL`, `NEEDS_REVIEW`, `NOT_EDITABLE`, or `UNKNOWN`. The main-menu START and SETTINGS/PREPARE objects are currently marked `TRANSLATED` and identify themselves as `RASTER_TEXT_ASSET`.

This first milestone provides filtering, status/details, hit testing, and direct routing. A progress dashboard and bulk status editing are future work.
