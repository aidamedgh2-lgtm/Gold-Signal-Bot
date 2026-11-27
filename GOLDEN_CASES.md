# Golden visual cases — original PDF

Purpose: create a source-grounded visual benchmark before any historical profitability test. The original PDF is the authority. The screenshots are examples, not a substitute for the source text.

## Case catalogue

| Case ID | PDF pages | Visual lesson explicitly shown | Label status | What must be annotated |
|---|---:|---|---|---|
| `PDF-DEPARTURE-01` | 33–35 | Horizontal/nearly horizontal departure = 0; smooth diagonal ≈45° = 1; steep/near-vertical = 2 | Partially labelable from source text; chart crop must be selected | Origin zone, full departure path, departure class, visible evidence |
| `PDF-MTF-01` | 67–76 | Start at largest timeframe; compare the same approximate zone downward; 3 matching zones = 2, 2 = 1; skip a frame when no suitable zone exists | Source rule labelled; screenshot-level zone coordinates need human annotation | Each frame, each zone polygon/price band if legible, zone identity, hierarchy, skipped-frame reason |
| `PDF-APPROACH-01` | 135–141 | Return path to the zone: impulsive/rocket-like versus diagonal or sideways; page 141 uses a 7/8-like analogy | Source rule labelled; exact numeric geometry intentionally unresolved | Full return path, zone, class (fast/diagonal/sideways/uncertain), visible evidence |
| `PDF-SCORE-01` | 143 | Six criteria and weights: 2,2,2,2,1,1 | Fully labelled | Verify criterion weights only; no chart prediction |
| `PDF-ZONE-BOUNDARY-01` | 67–76, 139–143 | Coloured zones and cross-timeframe refinement are illustrated | Incomplete | Human must mark exact upper/lower boundaries where source image and price scale permit; otherwise label boundary as unresolved |

## Annotation protocol

For each case, record:
- PDF page number and screenshot/image crop reference.
- Instrument and timeframe only when visible in the screenshot; never infer missing metadata.
- Zone direction and exact upper/lower prices only when legible from the source image.
- Origin/departure and full return path.
- Each of the six criterion labels, including `UNKNOWN` where the source or image is insufficient.
- Evidence sentence pointing to the visible part of the chart and the source page.
- Reviewer identity/date and a second-review status for disputed boundaries.

## Important exclusions

- Do not fabricate candle OHLC values from screenshots.
- Do not convert a visual angle into a fixed ATR, point, or candle-body threshold.
- Do not infer zone boundaries from the automated detector and then use them as the "ground truth".
- Do not treat a model's confidence as a strategy score.
- Do not use examples from the PDF as a profitability sample; they are selected illustrations and are subject to selection bias.

## First acceptance test

Before testing historical P&L, the model must classify all labelled departure/approach cases with explicit evidence and preserve `UNKNOWN` for ambiguous cases. Zone boundaries and multi-timeframe identity must be separately reviewed. A passing result is a visual-fidelity result only, not evidence of profitability.
