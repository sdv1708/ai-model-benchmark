# Handout B | Why this matters and how to use it

For developers, test engineers, product and customer teams | 23 October 2026

**Change the customer conversation.** Ask "Does this model meet your agreed coding and long-document requirements?" and show a repeatable decision with its evidence. The pruners support shorter tests, but today's defended setting keeps **315/315 coding and 100/100 long-context questions: 0% pruned**. No smaller tested set passed every check; no time or cost saving is established.

**Try it tomorrow.** In the installed, pinned EvalScope fork ([setup and live commands](ISSUE_25_GUIDE.md)), run this synthetic practice workflow in PowerShell with a fresh output directory; no provider key is needed:

```powershell
python examples/aa_lcr_pruned/smoke.py --compare --work-dir outputs/handout-b
python -m evalscope_ext.tools.compare_runs `
  --full outputs/handout-b/full --pruned outputs/handout-b/pruned --threshold 0.8
```

**Read the decision, not just the score.** Practice gives 12 full / 3 retained questions, both scoring 100%, yet the subset is **inconclusive** at the example 80% requirement: untested answers allow 25-100%. For real runs, agree requirements first; use the linked coding/long-context setup and replace these paths with matching saved runs. GO means the whole bound meets the requirement; NO GO means all of it falls below; otherwise collect more evidence. Command exit 0 means comparison completed. GO is conditional benchmark evidence, not a deployment guarantee; long-context judge variability remains unmeasured.

**If images are next.** The proposed full-MMMU probe deliberately covers tiny text, charts and diagrams, then compares original images with human-checked, answer-preserving degradations and text controls. This exposes specific visual weaknesses a random sample can miss. It measures visual-path sensitivity, not encoder causality; today's demo is synthetic, with no live-model conclusion.

**Why a PM cares.** Set honest acceptance criteria, budget validation work, and identify image-workflow risks before promising a rollout. Sell traceable evidence today; validate savings on fresh models before promising them.

Evidence: [retention decision](../docs/issue-17-evidence.md) | [comparison contract](../docs/issue-21-evidence.md) | [visual probe and limits](MMMU_HARNESS.md).
