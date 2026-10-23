# Issue #23: from picture puzzles to interview answers

The [operating contract](MMMU_HARNESS.md) has commands, schemas, parameters and
research links. The assistant implemented this learner-labelled ticket at your
explicit request. Practise running and changing it yourself; describe synthetic
tests honestly in an interview.

## Start with a robot reading a picture

Imagine two bars: a red bar is height 12 and a blue bar is height 17. You ask a
robot which is taller. It must see the bars, understand the question and say
the right answer. A failure anywhere in that chain can produce a wrong answer.

Now show the same puzzle twice: once clear, once slightly fuzzy. Keep the words,
options, model and settings the same. If the robot succeeds on the clear picture
and fails on the fuzzy copy, that is a clue that its answer is sensitive to the
visual change.

This is a **paired test**. Each question acts as its own control. We cannot
accidentally make one condition look better by giving it easier questions.
Pairing controls differences between tasks; it does not remove all randomness
or identify which internal model component caused a failure.

## What we built

Four modules do four jobs:

1. `mmmu_images.py` makes controlled copies and records their identities.
2. `mmmu_requests.py` packages future API requests in original image/text order,
   with the answer key left out of the messages.
3. `mmmu_measurements.py` joins saved responses to exact requests and calculates
   paired measurements, including missing outcomes and QA.
4. `mmmu_cli.py` exposes `demo`, `build`, `plan`, `report`.

The separate `tools/demo_mmmu_pairs.py` runs this whole flow with synthetic images
and scripted responses. It never calls an endpoint.

```text
exported question + original images
                  |
              build bundle
                  |
     original + changed images + IDs
                  |
       review pairs      export plan
             |                |
         saved QA       future endpoint runner
             |                |
             +---- saved responses
                         |
                    paired report
```

The future endpoint runner is not implemented. We can test the machinery
without paying for model calls. Later, the final probe belongs in EvalScope's
native adapter/API/cache/report flow, rather than a new competing framework.

## Why seven ways to change a picture?

Each operation asks a different question about visual information:

| Treatment | Everyday picture | Possible difficulty |
| --- | --- | --- |
| Downsample and restore | Shrink a drawing, stretch it back | Lost tiny details |
| Blur | Foggy glasses | Fine lines and small symbols |
| JPEG | Save with less picture detail | Edges and subtle texture |
| Occlusion | Cover a strip with paper | Hidden evidence |
| Contrast | Ink closer to paper color | Faint boundaries/text |
| Saturation | Make colors less vivid | Color-coded categories |
| Text-region blur | Smudge only saved text regions | Numbers, signs, units |

We use two fixed severities per operation. Both start from the original. We
do not blur a compressed copy, because then two treatments would be mixed.

Downsampling restores the original canvas size. Lost detail does not return
just because we stretch the picture. JPEG is decoded back to PNG so the API
sees the same container type across conditions. That reduces an avoidable
format-handling difference without proving identical provider preprocessing.

Only one target image slot changes. If a question repeats that slot, every
occurrence changes together. If option A contains another image, that image
stays fixed. Image order matters: otherwise we could change the question itself.

## The big trap: erasing the answer

Suppose the picture says `-12 mV` and our blur erases the minus sign. A model
answering `12 mV` may be reading the new image faithfully. It would be unfair
to call that an encoder failure: our transformation destroyed necessary evidence.

So every pair starts as pending semantic QA. Two reviewers must confirm all
question-relevant facts remain available before it enters robustness summaries.
Specialized imagery needs subject expertise. Names written in JSON cannot prove
that review happened; they are an audit record of a separate human process.

Destructive changes can still serve as negative controls. If a model answers
after essential evidence is covered, perhaps it relies on the words or prior
knowledge. That is a different experiment from tolerating harmless degradation.

Our demo's QA is **also scripted**, with explicitly fake reviewer names. It tests
the software gate and does not establish semantic validity of any real MMMU pair.

## Why fingerprints matter

Imagine shuffling a pile of clear pictures and a pile of fuzzy copies. If you
compare unrelated puzzles, the measured difference means nothing.

A pair ID binds the question, original image set, target slot and operation.
We also record dataset revision, image hashes, parameters and runtime/code
identity. A response carries an attempt ID, request hash and repeat index. We
join by these identities, not whichever file happens to sort first.

SHA-256 is a precise barcode for bytes. It detects an image changing after
request preparation. It does not prove an answer key is correct or a reviewer
really looked at a picture. Integrity and authenticity are different promises.

Reproducible means the same inputs and recorded environment give identical
artifacts. It does not mean model answers are deterministic, nor that different
codec builds must produce identical encoded bytes.

## Work through four puzzles

This is an invented arithmetic example, not a measured model result:

| Puzzle | Clear picture | Changed picture | Category |
| --- | --- | --- | --- |
| 1 | Correct | Correct | Stable correct |
| 2 | Correct | Wrong | Regression |
| 3 | Wrong | Correct | Improvement |
| 4 | Wrong | Same wrong answer | Stable wrong |

Clear accuracy is 2/4 = 50%. Changed accuracy is also 2/4 = 50%.
Accuracy drop is **0 percentage points**.

Only puzzles 1 and 4 kept their answers, so answer consistency is 2/4 = 50%.
One regression and one improvement canceled in the average. Reporting only
accuracy would hide that instability.

Puzzle 4 is perfectly consistent and wrong. Stability is not correctness.

Scoring must preserve important differences too. `mV` means millivolts while
`MV` means megavolts: changing case changes magnitude by a billion. Our open
scorer only collapses whitespace, preserves case, and requires other acceptable
spellings to be listed explicitly. Lowercasing everything would hide real errors.

When every binary outcome is scored and properly formatted, signed drop equals
`100 * (regressions - improvements) / paired attempts`. Format failures also
score zero but have their own exclusive category, so use component scores rather
than that category shorthand when malformed outputs occur.

Percentage points mean subtraction: 80% minus 70% is 10 points. A relative
percentage decrease would be 10/80 = 12.5%. We report points.

## What if an answer disappears?

Suppose both original answers are correct. One changed answer is malformed and
the other request never completes. The malformed completed answer scores zero.
On the single complete pair the descriptive drop is 100 points.

Across both planned pairs, we do not know the exact drop. If the missing answer
would have been right, drop is 50 points. If wrong, drop is 100 points. We report
**[50, 100]** as completion bounds, plus the 50% completion coverage.

These bounds describe missing outcomes on the existing questions. They do not
tell us whether two questions represent all users or MMMU. A population sampling
confidence interval is a separate job requiring a sampling design and enough
independent questions.

A zero-width completion bound can occur with a single completed question while
population uncertainty remains enormous. Never confuse complete data with
precise generalization.

## Why repeated calls are not new questions

Ask a person the same puzzle twice and their answer may change. Model generation
can vary too, even at temperature zero. Repeats help expose that instability.

But two attempts on one question are not two independent questions. Fourteen
changes to one image are not fourteen new school subjects. The original attempt
is intentionally reused across its transform comparisons, so these comparisons
are correlated. The report shows unique question counts and separates transform
groups; it does not invent statistical precision from a larger call count.

## Can we say the encoder is broken?

No. The defensible phrase is **visual-path sensitivity**. From outside we observe
a whole system: preprocessing, image encoder, projector/fusion, language reasoning
and formatting. This prototype cannot uniquely identify one internal component.

The larger issue #22 design adds controls:

- **No image:** can words/prior knowledge already solve it?
- **Equivalent factual text:** can it reason when humans provide image facts in
  words, without handing it the solution?
- **Visual facts:** can it extract labels, symbols or spatial relations before
  answering the main question?

Original wrong, factual text right, no image wrong and fact extraction wrong
would be consistent with a visual-path bottleneck. Even then, changing modality
changes the prompt and preprocessing/fusion remain possible causes. Causal
encoder attribution needs a comparison where only the encoder changes while
other components and serving settings are held fixed.

## Where this fits

Issue #22 designs the full experiment; issue #23 prototypes transformations and
paired measurements. The official inventory has 11,550 questions and 30 subjects;
its test split has 10,500. The 660 supplied references cover only 22 subjects.
Three synthetic pictures cannot establish representative MMMU accuracy, sufficient
pruning, production readiness, actual cost savings or an encoder regression.

The harness accepts exported actual images but does not fetch/select them. Next
steps are source/label audits, answer-blind annotations, coverage-aware selection,
semantic checks, endpoint preflight, pilot precision/power, and frozen confirmation.
No-image, equivalent-text and extraction controls remain future work.

## Rehearse these answers

**What did you build?**

“An offline prototype that creates versioned original/transformed image pairs,
exports answer-blind request plans and measures paired saved responses. It covers
seven visual treatments with explicit applicability and semantic QA.”

**What is the main design decision?**

“Hold the task and provider profile fixed, change one image slot, then inspect
paired failures rather than only aggregate accuracy. Content-bound identities
keep requests and observations correctly matched.”

**How did you validate without an endpoint?**

“Synthetic images and scripted responses with worked expected metrics, including
cancellation, missing calls and format failures. These validate software behavior,
not model robustness.”

**How do malformed answers differ from timeouts?**

“A completed format failure gets zero under a frozen parser. A timeout or
truncation stays unknown. I report coverage and worst/best completion bounds
instead of quietly dropping missing outcomes.”

**Why not approve mild transforms automatically?**

“A small change can erase the only important sign, line or color cue. Preservation
depends on the question, so humans must inspect the actual pair.”

**Why no confidence interval?**

“The prototype has no probability sample of MMMU and its calls are clustered
inside questions. I report diagnostics and missing-outcome bounds; population
inference requires the larger design and uncertainty machinery.”

**Does pairing isolate the encoder?**

“It isolates an input intervention from differences between questions. It does
not identify the internal component responsible. I need extra controls and an
encoder-only intervention for causal attribution.”

**What did the experiment find?**

“No live-model finding yet. The demo created 38 pairs and exercised reporting
with 79 scripted responses for 82 planned calls. Real claims still require
original MMMU imagery, human QA and endpoint records.”

## Practise until you need no notes

1. Run the demo in a fresh directory and inspect preview/report.
2. Explain why saturation is skipped on grayscale images.
3. Explain the strong-blur completion bounds and missing count.
4. Draw the four-puzzle cancellation table from memory.
5. Change one source pixel, rebuild elsewhere and compare pair IDs.
6. Set a QA record to pending and explain its removal from summary metrics.
7. Give a case where consistency is 100% and accuracy is 0%.
8. Explain why answers stay outside requests and originals remain untouched.
9. Name the extra experiment needed before claiming the encoder caused it.
