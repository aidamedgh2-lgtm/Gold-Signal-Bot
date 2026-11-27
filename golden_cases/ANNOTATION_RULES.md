# Golden-case annotation rules

## Scope
This benchmark is a visual-fidelity check against the original 143-page PDF, not a profitability dataset. The PDF remains authoritative.

## Cases prepared from the source
- `PDF-DEPARTURE-01A`: page 34's steep green departure path; expected departure-strength score 2, using the scale on page 33.
- `PDF-MTF-01A`: pages 69–74; monthly → weekly → daily top-down example; the source says three matching zones score 2.
- `PDF-MTF-01B`: pages 74–76; explicitly permits skipping an unsuitable/difficult monthly drawing and refining on weekly.
- `PDF-APPROACH-01A`: pages 135–137; the first steep/fast schematic path scores 1, the two slower stair/diagonal paths score 0.
- `PDF-APPROACH-01B`: pages 139–141; rocket-like return and the 7/8-like visual analogy are source-labelled as the one-point pattern.
- `PDF-SCORE-01`: page 143; six criterion weights total 10.
- `PDF-ZONE-BOUNDARY-01`: pages with coloured zones; deliberately remains incomplete until a human annotates exact chart-space boundaries.

## Annotation fields required for each chart crop
1. Source PDF page and crop identifier.
2. Symbol/timeframe only if legible in the original screenshot.
3. Zone polygon in normalized image coordinates `[x_min, y_min, x_max, y_max]`; if the zone cannot be identified reliably, set it to `null` and explain why.
4. Upper/lower price only when the price scale and boundary are both legible; otherwise `null`.
5. Departure path and return path polygons, separately.
6. Expected class and criterion points, or `UNKNOWN`.
7. Short evidence note tied to the source page.
8. Reviewer and independent second-review status for disputed boundaries.

## Hard prohibitions
- Do not manufacture OHLC candles from screenshots.
- Do not use ATR, fixed point distances, candle-body ratios, or fixed candle counts as replacements for the PDF's visual judgements.
- Do not let the model define a zone and then score its own zone as ground truth.
- Do not translate the 7/8 analogy into a mathematical curve requirement.
- Do not use confidence as a criterion score.
- Do not treat these selected teaching examples as evidence of historical profitability.

## Gate
A benchmark row is eligible for automated scoring only after its visual crop and human ground-truth labels are complete. Any unresolved zone boundary or criterion remains `UNKNOWN` and blocks strategy-compliant scoring. No live signal path may be re-enabled by this benchmark alone.
