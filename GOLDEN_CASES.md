# Golden visual cases — original PDF

Purpose: create a source-grounded visual benchmark before any historical profitability test. The original PDF is the authority. The screenshots are examples, not a substitute for the source text.

## Prepared benchmark artifacts

- `golden_cases/manifest.json`: machine-readable cases and source-supported expected labels.
- `golden_cases/ANNOTATION_RULES.md`: required human annotation fields and strict prohibitions.
- `tests/test_golden_manifest.py`: structural tests for case IDs, score weights, unresolved zone boundaries, and the no-proxy acceptance policy.

## Case catalogue

| Case ID | PDF pages | Visual lesson explicitly shown | Label status | What must be annotated |
|---|---:|---|---|---|
| `PDF-DEPARTURE-01A` | 33–34 | Page 34 steep green departure path; page 33 defines horizontal 0, diagonal 1, steep 2 | Source-labelled class; pixel crop/boundary still needs review | Origin zone and full departure path |
| `PDF-MTF-01A` | 69–74 | Monthly → weekly → daily example; page 69 says three matching zones = 2 | Rule and example labelled; exact price boundaries incomplete | Same-zone identity, hierarchy, each frame's zone |
| `PDF-MTF-01B` | 74–76 | If monthly is difficult/unsuitable, move to weekly and refine there | Source-labelled | Record the skipped frame and reason |
| `PDF-APPROACH-01A` | 135–137 | Three schematic return paths: steep/fast = 1; two slower stair/diagonal paths = 0 | Source-labelled | Complete path for each example |
| `PDF-APPROACH-01B` | 139–141 | Rocket-like return; 7/8-like visual analogy for one point | Source-labelled visual rule | Full return path; do not convert 7/8 into a formula |
| `PDF-SCORE-01` | 143 | Six criteria and weights: 2,2,2,2,1,1 | Fully labelled | Verify weights only |
| `PDF-ZONE-BOUNDARY-01` | 67–76, 139–141 | Coloured zones and cross-timeframe refinement are illustrated | Incomplete | Human must mark exact boundaries where legible; otherwise UNKNOWN |

## Annotation protocol

For each case, record:
- PDF page number and screenshot/image crop reference.
- Instrument and timeframe only when legible in the screenshot; never infer missing metadata.
- Zone polygon in normalized image coordinates, or `null` with a reason.
- Exact upper/lower price only when both the price scale and boundary are legible.
- Origin/departure and full return path, separately.
- Each of the six criterion labels, including `UNKNOWN` where source/image evidence is insufficient.
- Evidence note tied to the visible chart and source page.
- Reviewer/date and independent second-review status for disputed boundaries.

## Important exclusions

- Do not fabricate candle OHLC values from screenshots.
- Do not convert visual angles into fixed ATR, point, candle-body, or candle-count thresholds.
- Do not infer zone boundaries from the automated detector and then use them as ground truth.
- Do not treat model confidence as a strategy score.
- Do not use examples from the PDF as a profitability sample; they are selected illustrations and are subject to selection bias.

## First acceptance test

Before historical P&L testing, the model must classify every source-labelled departure/approach case with explicit evidence and preserve `UNKNOWN` for ambiguous cases. Zone boundaries and multi-timeframe identity must be separately reviewed. A passing result is a visual-fidelity result only, not evidence of profitability. The live-signal gate remains closed until zone boundaries and all six criteria pass review.
