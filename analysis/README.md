# Analysis provenance and reproduction

This folder contains the actual engine-labeling and NumPy logistic-regression training source used for the case study. It is separate from the browser application. The fitted artifact is in `../dist/assets/risk-model.json`.

The archived window is fixed in `download_games.py`: Nov 4, 2025, 21:28:19 through Nov 4, 2026, 21:28:19 America/Los_Angeles. Public games can subsequently be removed or changed upstream, so a later export is not guaranteed to be byte-identical. `download_manifest.json` records the original export.

## Reproduce the analysis

Create an isolated Python environment and install `requirements.txt`. Obtain Stockfish 19 from the [official release](https://github.com/official-stockfish/Stockfish/releases/tag/sf_19) for your machine. Set `STOCKFISH_PATH` to its executable path, then run from this folder:

```sh
python download_games.py --output-dir data
python analyze_history.py --data-dir data --engine "$STOCKFISH_PATH" --cache-dir cache --nodes 12000
python refine_errors.py --data-dir data --engine "$STOCKFISH_PATH" --cache-dir refined_cache --nodes 100000
python -m unittest test_refine_errors.py
python ../scripts/export-data.py --engine "$STOCKFISH_PATH"
python ../scripts/build-transfer.py --engine "$STOCKFISH_PATH"
```

Full engine analysis is expensive; running the site does not require it. Engine scheduling and search history can change finite-budget evaluations between runs. The saved coefficients and validation results are included with the site.

The exporter is specific to this case study's fixed archive and selected positions. It uses the `data/refined` results and `refined_cache` created by the commands above. The displayed teaching notes are authored interpretations of those checked lines. A different archive would need its own reviewed selection and notes; this is not a general upload interface.

The base model uses pre-move features, a chronological whole-game split, training-only feature scaling, and validation-selected L2 regularization. Its target is a ≥10-point decline in a fixed evaluation proxy. It is not a calibrated personal probability of losing the game.

The tactical classifiers are explicit, conservative motif detectors. They can assign overlapping labels. More than a thousand refined large-error moves do not match those detectors and were left unclassified. Action labels such as a quiet king move do not establish the psychological cause of a mistake.

The website offers 26 practice positions. The export retains its original two collections internally: 20 original examples and six additional rook endings from different games. All 701 legal candidate first moves are evaluated. They now appear in one practice session; no separate assessment mode is exposed. The classifier’s chronological train/test split remains separate from practice content.

Practice feedback uses separately precomputed Stockfish 19 searches at 100,000 nodes per candidate; the browser neither runs nor downloads a chess engine. Browser inference uses the exact saved logistic coefficients. First attempts, retries and reveals have distinct scoring behavior, stored only in the visitor's browser. No later real-game training effect has been measured.
