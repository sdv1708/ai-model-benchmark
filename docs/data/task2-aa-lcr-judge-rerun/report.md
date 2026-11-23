# AA-LCR judge noise on the saved answers (#76)

The judge graded each of the 300 saved answers
5 times. The run generated no new answer.

## Result

- The judgments are not all equal for 8 of 300 answers (2.7%).
- At threshold 0.60, 0 of 3 full-set decisions change between passes. 0 of 30 pairs of passes differ.

| Model | Answers with unequal judgments | Scores in the passes | Lowest | Highest | Standard deviation | Saved score | Majority score | Decisions in the passes | Decision changes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-oss-120b | 2 of 100 | 0.52, 0.53, 0.53, 0.52, 0.53 | 0.52 | 0.53 | 0.0055 | 0.48 | 0.52 (+0.04) | NO GO, NO GO, NO GO, NO GO, NO GO | no |
| kimi-k2.5 | 5 of 100 | 0.71, 0.73, 0.72, 0.73, 0.72 | 0.71 | 0.73 | 0.0084 | 0.66 | 0.73 (+0.07) | GO, GO, GO, GO, GO | no |
| minimax-m2.5 | 1 of 100 | 0.65, 0.66, 0.65, 0.66, 0.66 | 0.65 | 0.66 | 0.0055 | 0.64 | 0.66 (+0.02) | GO, GO, GO, GO, GO | no |

## Judge variation and the stage-1 interval

Policy threshold-policy@v1 uses 30 questions, the `pooled_exact_hypergeometric` interval, and the `metadata_stratified` strata.
The mean width covers 20 probes of each model on the saved grades.
The widths are from 0.270 to 0.310, and the mean is 0.297.

| Model | Score range across the passes | Mean stage-1 interval width |
| --- | --- | --- |
| gpt-oss-120b | 0.01 | 0.305 |
| kimi-k2.5 | 0.02 | 0.292 |
| minimax-m2.5 | 0.01 | 0.294 |

The largest score range is 0.067 of the mean interval width.
The interval describes sampling error on fixed grades. It excludes judge noise.

## Judge

- The saved reviews name the judge `qwen-3-235b-a22b-instruct-2507`. This run uses the same model, with the name `Qwen/Qwen3-235B-A22B-Instruct-2507` at this endpoint.
- The saved reviews record no endpoint, no precision, and no settings, and an earlier EvalScope version can have sent another prompt. Each of these can differ from this run.
- The majority of the 5 new judgments agrees with the saved judgment for 287 of 300 answers (95.7%). 0 answers change from CORRECT to INCORRECT, and 13 change from INCORRECT to CORRECT.

| Setting | Value |
| --- | --- |
| Judge model, requested | `Qwen/Qwen3-235B-A22B-Instruct-2507` |
| Judge model, returned | Qwen/Qwen3-235B-A22B-Instruct-2507 |
| Provider, returned | not returned |
| Endpoint | https://api.deepinfra.com/v1/openai |
| Run dates (UTC) | 2026-11-23 |
| Temperature | 0.0 |
| Maximum output tokens | 4096 |
| Seed | none sent |
| Judge prompt | https://github.com/sdv1708/evalscope-pruning at `67fbe5e092a4739d23f5d8cc95319d8b19dc1a24`, no change |
| Prompts SHA-256 | `c1ca698f66eeded19c7e144c6f5431440525ee1d3cffaeb98df179a084bae563` |
| Approval | https://github.com/sdv1708/ai-model-benchmark/issues/76#issuecomment-7115460027 |
| Estimate SHA-256 | `5bf6a1484cb293351dca31620052182fc239058ba7bc6d3c2706c213c78b1655` |

## Requests and cost

- The run made 1,500 requests and got 1,500 judgments.
- 0 replies did not satisfy the output contract, and 0 requests had no usable reply. The run rejected 0 replies, which came from another model or repeated an earlier reply. The run repeated these requests, and `judgments.jsonl` keeps all of them.
- The tokens were 499,075 input and 175,192 output. 0 requests had no token count.
- The cost was at most $0.1413 at the prices of the estimate. The limit was $1.00.

## Limits

- The judgments show the variation of one judge at one endpoint. They do not show whether the judge is correct.
- The passes measure the noise between repeated calls with the same settings. They do not measure the difference between the saved judgments and this run. The agreement section gives that difference, and the run cannot give its cause.
- The temperature was 0.0. A higher temperature can give more noise.
- All passes ran on the dates above. A later model version or another endpoint can differ.
- A repeated request replaces a reply outside the contract. That rule can favor answers for which the judge replies in the correct format.
- Policy v1 does not change. Its interval excludes judge noise.
