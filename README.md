# Chess Insight — a Lichess learning proposal

[Open the live demo](https://codepog.github.io/chess-insight/)

A product and business strategy proposal for **Lichess**, grounded in **chickenboi2's public games**. Connect existing analysis to a focused practice plan and a separate assessment, while preserving free access and operating within a sustainable donation-funded budget.

## Run locally

No dependency installation or build step is needed. From this folder:

```sh
python3 -m http.server 4173 --bind 127.0.0.1 --directory dist
```

Open http://127.0.0.1:4173. `npm start` runs the same command. Use an HTTP server; opening `index.html` directly prevents the data request in some browsers.

## The five pages

- **Overview:** thesis, archive summary, personal recommendations and historical rating.
- **Game explorer:** 20 curated positions, original clock and move, better continuation and opponent refutation. Category and time-control filters; keyboard playback with arrow keys.
- **Practice:** 20 review positions and six separate assessment positions from different source games. All 701 legal candidates have offline engine evaluations. Sound alternatives count. First attempts and reveals are stored only in the current browser. Retrying cannot raise the first-attempt score; revealing a solution excludes it.
- **Model lab:** the saved logistic regression performs actual inference in the browser on 50 held-out examples. Includes the whole-game chronological split, baselines, risk groups, coefficients and limits.
- **Business case:** problem definition, nonprofit objectives, existing tools and competitors, delivery choices, a controlled pilot, a hypothetical cost scenario, and an explicit rollout decision.

## What the model does

The trained classifier predicts a binary engine-defined error risk, using 21 features available before the player's move. It does **not** learn labels such as fork or pin. Those motif labels come from explicit chess rules and engine continuations.

The model uses 589 standard bullet games, split chronologically into 353 training, 118 validation and 118 test games. The held-out 3,765 turns contain 375 error labels. ROC AUC is 0.689; log loss is 0.304 versus 0.324 for a constant-rate baseline. This is an evaluated personal model, not a proven training intervention.

Original engine labels use Stockfish 19 at 12,000 nodes. Refined motif/endgame review uses 100,000 nodes. Practice grades compare separately checked legal candidates, each searched at 100,000 nodes. Finite search budgets can produce different estimates. The website is a frozen case study, not a live engine or a general-purpose analysis service.

## GitHub Pages

The static site uses relative asset paths and hash routes, so it can live at a repository subpath. For the intended `codepog/chess-insight` repository:

1. Push the source to its `main` branch.
2. In GitHub **Settings → Pages**, choose **GitHub Actions** as the publishing source.
3. Run the included **Deploy Chess Insight to GitHub Pages** workflow, or push another commit.

The workflow uploads only `dist/`, so the raw analysis and source scripts are not served as website assets. It requests the standard Pages deployment permissions. See [GitHub's workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## Source and validation

- `dist/`: complete, portable site; no third-party runtime scripts or fonts.
- `scripts/check-data.cjs`: verifies data reconciliation, inference, split separation and asset existence using Node's standard library.
- `analysis/`: engine-labeling, motif classification and training source, plus instructions and provenance.
- `dist/assets/`: saved model, evaluation report and practice PGN for direct download.

Run `npm run check` with Node 18 or newer. The implementation was also reviewed in a browser at desktop and mobile sizes, including move grading, playback, clock-feature inference and saved practice progress.

## Attribution

The interface follows Apple's principles of clarity, hierarchy and deference to content: system typography, a quiet horizontal navigation bar, generous spacing and controls near the board. References: [Apple Human Interface Guidelines](https://developer.apple.com/design/human-interface-guidelines/), [Apple Design Resources](https://developer.apple.com/design/resources/), and the [community Apple Design System catalog](https://github.com/mjmirza/apple-design-system). No Apple font, icon or UI-kit files are distributed. No Chess.com or Lichess logos or interface code are used. Chess pieces are Cburnett designs distributed by python-chess; see `THIRD_PARTY_NOTICES.md`.

The product distinction demonstrated here is a free guided-learning proposal for Lichess, with review success separated from first-exposure assessment and follow-up real games explicitly unmeasured. The business case evaluates learning, repeat use, cost and trust; it does not propose subscriptions or paid feature access. Chess.com already offers Game Review retries, Insights, course recommendations and Skills; Aimchess already offers personalized plans. This case does not claim universal feature novelty or established learning improvement. Independent case study, not affiliated with these products.

This source is distributed under GPL-3.0-or-later. Public game records are attributed to their Lichess source links. Product claims are sourced on the Product thesis page; proposed business and learning outcomes are explicitly hypotheses.
