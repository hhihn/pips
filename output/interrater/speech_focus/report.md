# Speech-to-child recipient and segmentation audit

The annotations support a narrower recipient rule for the new rater, but also
show different segmentation. This exploratory audit concerns the ten paired
videos and thirteen aligned care situations, not the entire recordings.

## Recipient classification

For each rater, identify the Pflegekind independently as the unique child code
5.5.1–5.5.10 with exactly the same start/end as the 6.1.1 care window.
Link a speech interval to recipient codes only when both boundaries match
exactly, following the repository's existing convention. General overlap with
the care-window child code does not establish a speech recipient.

| Speech intervals overlapping each rater's own care windows | Old | New |
|---|---:|---:|
| All 5.3.1 intervals | 64 | 28 |
| Exactly linked to that rater's Pflegekind | 50 | 27 |
| Exactly linked to another individual child | 13 | 0 |
| Linked to the group, without an explicit Pflegekind link | 1 | 0 |
| No exact recipient interval | 0 | 1 |

Of the 14 old intervals without an explicit focus-child link, 13 reference another
individual child and one references 5.5.11 (group). The group may include the
Pflegekind, so that interval cannot be interpreted as definitely excluding it.
The data label 5.3.1 as
“FK spricht mit Kind(ern)”; speech to colleagues has a separate 5.3.2 label.
Thus “speech to other children” is supported; “every sentence spoken regardless
of recipient” cannot be established from these annotations.

Child numbers are not stable across raters: for example, in the first 44-PS-2
situation, the old Pflegekind code is 5.5.2 and the new code is 5.5.1. This audit
uses each rater's own focus assignment. The actual child identity requires video
or coder confirmation.

## Differences in segmentation

13 of 28 new speech intervals overlap two or more old focus-directed intervals
in the corresponding care situation. Examples (seconds from video start):

- 33-P-2: old focus speech 34.6–35.3, 35.7–36.9, 38.2–38.7, 40.0–40.5,
  40.6–42.2; new speech 34.4–42.0.
- 61-P-4: old focus speech 60.0–61.5, 61.7–62.6, 64.2–66.3; new speech
  58.0–66.0. Later: old 72.6–73.1, 73.7–74.0, 74.1–74.7; new 72.6–74.9.
- 23-P-2: old 23.2–24.3 and 25.6–28.4; new 23.1–28.4.

These are consistent with grouping utterances into longer speaking episodes,
including pauses. The annotation tables cannot determine whether every gap was
silence or which segmentation rule the rater intended.

## Compare time coverage on shared observation windows

Care-window boundaries differ, so compare durations only in intersections of
aligned old/new care windows (200.9 seconds in total). Merge overlapping speech
intervals within each video before summing; no timestamp tolerance is used here.
Counts above still describe each rater's own windows. In the shared windows,
60 old intervals (50 focus, 10 other) and 26 new intervals have positive overlap.

| Speech time within shared care windows | Seconds |
|---|---:|
| Old: all child-directed speech | 76.3 |
| Old: Pflegekind-directed speech | 65.2 |
| Old: other-child/group-linked speech | 11.1 |
| New: all speech | 92.1 |
| Old Pflegekind speech overlapping new speech | 62.5 |
| Old other-child/group speech overlapping new speech | 1.2 |

The new annotations cover 95.9% of old Pflegekind-directed speech time versus
10.8% of old other-child/group-linked speech time (the latter includes 1.9 seconds
of group speech). Coverage is asymmetric: the new
annotations also include additional time. Symmetric duration Dice is 79.5% for
old focus-directed versus all new speech (75.7% before filtering the old rater).
Bootstrap intervals are in summary.json: 2,000 video-cluster resamples, seed 42.

The one unlinked new speech interval is 2-P-1, 31.8–43.9 seconds; its associated
shorter child reference is 31.8–40.9. The speech interval also overlaps an old
other-child utterance (38.7–40.8), so the new data do not establish a universally
exclusive focus-child rule. Recipient selection, boundary changes, and pauses
can all contribute.

## Interpretation

A focus-child restriction plausibly explains part of the difference. It does
not explain the count difference by itself: 50 old focus intervals remain versus
28 new speech intervals. Broader segmentation is a substantial additional
explanation, and fewer intervals do not imply less annotated speech time.
The new rater actually annotates more speech time in the shared windows.

The current interrater configuration uses tolerance_ms=60000 (60 seconds).
The one-to-one event score therefore reflects segmentation/count differences
strongly; increasing tolerance cannot make one long interval match several
short intervals. It is not a measure of agreement on total speech coverage.

For a Pflegekind speech measure, verify the recipient rule and segmentation
rule with both raters. Report focus-directed time overlap/duration agreement
alongside event matching, keeping those as distinct analyses. This audit is
exploratory and does not change the configured interrater analysis or its results.
