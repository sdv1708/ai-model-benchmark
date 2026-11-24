# The old one-word judge prompt on the saved AA-LCR answers (#88)

The control run sent each saved answer to the judge 5 times, with the old one-word prompt.
It used the judge and the endpoint of the JSON run (#76). It generated no new answer.
Each grade of a run is the majority of 5 judgments.

## Result

10 of the 13 answers are INCORRECT again.
**The prompt explains most of the shift.**

Issue #88 fixed this rule before the run. It covers the 13 answers that the JSON prompt changed from INCORRECT to CORRECT:

| Answers of the 13 that are INCORRECT again | Conclusion |
| --- | --- |
| 10 to 13 | The prompt explains most of the shift |
| 4 to 9 | The prompt explains a part of the shift |
| 0 to 3 | The prompt does not explain the shift |

| Model | Question | Reference answer | CORRECT votes, JSON prompt | CORRECT votes, one-word prompt | Majority, one-word prompt |
| --- | --- | --- | --- | --- | --- |
| gpt-oss-120b | 39 | Excel date number, for example `45444` | 5 of 5 | 0 of 5 | INCORRECT |
| gpt-oss-120b | 74 | List with a literal `\n` | 5 of 5 | 3 of 5 | CORRECT |
| gpt-oss-120b | 86 | Decimal below 1, for example `0.1` for 10% | 5 of 5 | 0 of 5 | INCORRECT |
| gpt-oss-120b | 89 | Decimal below 1, for example `0.1` for 10% | 5 of 5 | 2 of 5 | INCORRECT |
| kimi-k2.5 | 23 | Other | 4 of 5 | 0 of 5 | INCORRECT |
| kimi-k2.5 | 37 | List with a literal `\n` | 5 of 5 | 1 of 5 | INCORRECT |
| kimi-k2.5 | 41 | Other | 5 of 5 | 0 of 5 | INCORRECT |
| kimi-k2.5 | 60 | Other | 5 of 5 | 1 of 5 | INCORRECT |
| kimi-k2.5 | 74 | List with a literal `\n` | 4 of 5 | 5 of 5 | CORRECT |
| kimi-k2.5 | 86 | Decimal below 1, for example `0.1` for 10% | 3 of 5 | 0 of 5 | INCORRECT |
| kimi-k2.5 | 93 | Decimal below 1, for example `0.1` for 10% | 3 of 5 | 0 of 5 | INCORRECT |
| minimax-m2.5 | 74 | List with a literal `\n` | 5 of 5 | 5 of 5 | CORRECT |
| minimax-m2.5 | 86 | Decimal below 1, for example `0.1` for 10% | 3 of 5 | 0 of 5 | INCORRECT |

## Agreement on all answers

| Grades | Agreement | INCORRECT to CORRECT | CORRECT to INCORRECT |
| --- | --- | --- | --- |
| Saved, then one-word prompt | 296 of 300 (98.7%) | 3 | 1 |
| Saved, then JSON prompt | 287 of 300 (95.7%) | 13 | 0 |
| JSON prompt, then one-word prompt | 289 of 300 (96.3%) | 0 | 11 |

## The three sets of grades

The threshold is 0.60. The saved data has one judgment for each answer.

| Model | Grades | Score of the majority | Decision | Scores in the passes | Decisions in the passes | Answers with unequal judgments | Agreement with the saved grades |
| --- | --- | --- | --- | --- | --- | --- | --- |
| gpt-oss-120b | Saved | 0.48 | NO GO | - | - | - | - |
| gpt-oss-120b | One-word prompt | 0.49 | NO GO | 0.49, 0.49, 0.51, 0.48, 0.49 | NO GO, NO GO, NO GO, NO GO, NO GO | 3 of 100 | 99 of 100 |
| gpt-oss-120b | JSON prompt | 0.52 | NO GO | 0.52, 0.53, 0.53, 0.52, 0.53 | NO GO, NO GO, NO GO, NO GO, NO GO | 2 of 100 | 96 of 100 |
| kimi-k2.5 | Saved | 0.66 | GO | - | - | - | - |
| kimi-k2.5 | One-word prompt | 0.66 | GO | 0.66, 0.67, 0.66, 0.67, 0.66 | GO, GO, GO, GO, GO | 2 of 100 | 98 of 100 |
| kimi-k2.5 | JSON prompt | 0.73 | GO | 0.71, 0.73, 0.72, 0.73, 0.72 | GO, GO, GO, GO, GO | 5 of 100 | 93 of 100 |
| minimax-m2.5 | Saved | 0.64 | GO | - | - | - | - |
| minimax-m2.5 | One-word prompt | 0.65 | GO | 0.65, 0.65, 0.65, 0.65, 0.65 | GO, GO, GO, GO, GO | 0 of 100 | 99 of 100 |
| minimax-m2.5 | JSON prompt | 0.66 | GO | 0.65, 0.66, 0.65, 0.66, 0.66 | GO, GO, GO, GO, GO | 1 of 100 | 98 of 100 |

## Reference answers

The table gives the number of answers in each cell.

| Reference answer | Answers | Changed by the JSON prompt | Of these, INCORRECT again | CORRECT: saved, one-word, JSON | Unequal judgments: one-word, JSON | Agreement with the saved grades: one-word, JSON | Agreement of one-word with JSON |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Decimal below 1, for example `0.1` for 10% | 27 | 5 | 5 | 6, 6, 11 | 1, 4 | 27, 22 | 22 |
| Excel date number, for example `45444` | 3 | 1 | 1 | 0, 0, 1 | 0, 0 | 3, 2 | 2 |
| List with a literal `\n` | 24 | 4 | 1 | 20, 23, 24 | 2, 1 | 21, 20 | 23 |
| Other | 246 | 3 | 3 | 152, 151, 155 | 2, 3 | 245, 243 | 242 |

## Settings

| Setting | JSON prompt | One-word prompt |
| --- | --- | --- |
| Judge model, requested | `Qwen/Qwen3-235B-A22B-Instruct-2507` | `Qwen/Qwen3-235B-A22B-Instruct-2507` |
| Judge model, returned | Qwen/Qwen3-235B-A22B-Instruct-2507 | Qwen/Qwen3-235B-A22B-Instruct-2507 |
| Endpoint | https://api.deepinfra.com/v1/openai | https://api.deepinfra.com/v1/openai |
| Run dates (UTC) | 2026-11-23 | 2026-11-24 |
| Temperature | 0.0 | 0.0 |
| Maximum output tokens | 4096 | 1024 |
| Seed | none sent | none sent |
| Prompt source | https://github.com/sdv1708/evalscope-pruning at `67fbe5e092a4739d23f5d8cc95319d8b19dc1a24`, json-contract | https://github.com/modelscope/evalscope v1.4.2 at `457dc8cbc2539aca173b4a71bcb29e352804d4af`, one-word |
| Prompts SHA-256 | `c1ca698f66eeded19c7e144c6f5431440525ee1d3cffaeb98df179a084bae563` | `4afca4cfe2793438fa330662f9a2ba0bd5415499d5629c0074cc5274b036277b` |
| Approval | https://github.com/sdv1708/ai-model-benchmark/issues/76#issuecomment-7115460027 | https://github.com/sdv1708/ai-model-benchmark/issues/88#issuecomment-7119429423 |
| Estimate SHA-256 | `5bf6a1484cb293351dca31620052182fc239058ba7bc6d3c2706c213c78b1655` | `fe15a9ab687f64d325b7d36dd21700548aec92fb3e39d1f7d4594d8132fa87de` |

## Replies and cost

- 0 of 1,500 one-word judgments come from a reply that is not exactly CORRECT or INCORRECT. The old parser looks for the word CORRECT in any reply.
- The run made 1,500 requests. 0 replies were empty. 0 requests had no usable reply. The run rejected 0 replies. None of these became INCORRECT. The run repeated these requests, and `judgments.jsonl` keeps all of them.
- The tokens were 428,575 input and 5,097 output. 0 requests had no token count.
- The cost was at most $0.0414 at the prices of the estimate. The limit was $0.50.

## Limits

- One run on another day does not separate the prompt from the endpoint, the precision, and the date of the saved judgments. The saved reviews record no endpoint and no precision.
- The two prompts also have different maximum output tokens. These are the defaults of the two EvalScope versions.
- The saved data has one judgment for each answer. A majority of 5 judgments can differ from one judgment of the same judge.
- The comparison shows which grades agree. It does not show which grades are correct.
- The temperature was 0.0. All one-word judgments ran on the dates above.
- EvalScope grades an empty reply and a transport error as INCORRECT. This run rejects them.
- Policy v1 and the recorded outputs of #76 do not change.
