# Screen-to-Asset Mapping

The descriptor supports manual mappings with status and `(x,y,width,height)`.
No automatic GPU mapping is implemented yet.

Planned safe order:

1. save manually verified screenshot rectangles;
2. overlay them in a screenshot viewer;
3. click a rectangle to open its registered descriptor;
4. allow human-created mappings with explicit verification state;
5. only later correlate known TIM uploads and GPU primitives.

Automatic mappings must report `VERIFIED`, `HIGH_CONFIDENCE`, `CANDIDATE` or
`UNKNOWN`; visual similarity alone is never sufficient.
