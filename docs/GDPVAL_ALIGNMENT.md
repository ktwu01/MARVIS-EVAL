# GDPVAL Alignment Notes

This repo uses the public OpenAI GDPVAL dataset as the concrete reference point for professional deliverable benchmarks. GDPVAL-MM is not publicly available, so Mavis-Eval treats it as directional only and does not assume access to its locked cases.

## Public GDPVAL Schema

The Hugging Face dataset exposes these fields:

| GDPVAL field | Mavis-Eval field |
|---|---|
| `task_id` | `case_id` plus optional external provenance |
| `sector` | `professional_context.economic_sector` |
| `occupation` | `professional_context.occupation` |
| `prompt` | `user_instruction` |
| `reference_files`, `reference_file_urls`, `reference_file_hf_uris` | `reference_assets` and `input_assets` |
| `deliverable_files`, `deliverable_file_urls`, `deliverable_file_hf_uris` | `target_deliverables`, `gold_reference_path`, and comparison artifacts |
| `rubric_pretty`, `rubric_json` | `rubric_items` plus weighted `rubric` dimensions |

## What Mavis-Eval Borrows

| Requirement | GDPVAL lesson | Repo location |
|---|---|---|
| Benchmark split dimensions | Sector, occupation, work activity, deliverable type, file modality, expert value | `PRD.md` sections 2.5, 3, 4 |
| Per-sample fields | Prompt + reference files + expected deliverable + point rubric | `schemas/case.schema.json`, `mavis_eval/schema.py`, `PRD.md` section 5 |
| Final deliverable pass/fail | Score the actual work product, with critical requirements that cannot be offset by style | `PRD.md` section 6, `mavis_eval/evaluator.py` |
| Agent process evaluation | Require inspection of generated artifacts and use scaffolding to catch formatting failures | `PRD.md` section 7 |
| Judge prompt design | Use evidence-bound rubric scoring and GDPVAL-style blind pairwise comparison | `prompts/deliverable_judge_v1.0.txt`, `prompts/pairwise_expert_judge_v1.0.txt` |
| Sample quality assurance | Expert-created/reviewed tasks, model-in-loop linting as advisory, human responsibility for final acceptance | `PRD.md` section 9 |
| Regression and horizontal comparison | Pairwise win/tie/loss against human, prior, and competitor deliverables in addition to pass rates | `PRD.md` section 10, `mavis_eval/reporting.py` |

## Mavis-Specific Extensions

GDPVAL's public tasks are strong for professional deliverable quality, but they are mostly one-shot and precisely specified. Mavis-Eval extends the design with:

- Multimodal I/O beyond file attachments: screenshots, UI state, audio/video-derived inputs, browser state, and local workspaces.
- Stateful execution checks: filesystem, DOM, app state, mocked services, forbidden tools, and safety redlines.
- Ambiguity and clarification cases, where asking the user is the expected behavior.
- Trajectory diagnostics for tool use, recovery, loops, evidence grounding, and pre-submission artifact inspection.
- Release regression gates using deterministic pass/fail, confidence intervals, McNemar signal, and slice regressions.

References:

- GDPVAL dataset: https://huggingface.co/datasets/openai/gdpval
- GDPVAL paper: https://arxiv.org/abs/2510.04374
- GDPVAL blog: https://openai.com/index/gdpval/
