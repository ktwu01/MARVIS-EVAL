# Mavis-Eval

Mavis 是 MiniMax 最新发布的 Agent 产品，定位为面向真实用户任务的个人 AI 助理，能够在开放任务中理解用户目标、规划执行路径，并通过多步操作完成交付。
请你完成一版面向 Mavis 的多模态 I/O 任务 benchmark 交付，用于评估它在真实用户任务中的端到端完成能力。
请交付：
1. benchmark 设计基本拆分维度
2.每条样本应包含的字段说明
3.最终交付物合格判定方式
4.Agent 执行过程评估方式
5.Judge Agent 的 prompt 设计
6.评测集本身的样本质量保障方式
7.使用该 benchmark 进行 Mavis 版本回归拦截和横向对比的方法

为了更清晰的展示你的benchmark，请提供不小于10条的样例case，尽可能多的覆盖你设计的各维度。

Mavis-Eval is an MVP implementation of the benchmark described in `PRD.md`: a regression-ready multimodal I/O benchmark for evaluating whether Mavis completes realistic personal-assistant tasks end to end.

The current implementation includes:

- Case schema validation for versioned benchmark samples.
- Deterministic executable assertions for files, CSV/JSON artifacts, mocked state, trajectory tools, frozen URLs, and forbidden actions.
- Gated final evaluation that combines assertion results with an external judge-agent JSON result.
- Judge evidence-package generation that excludes hidden model reasoning.
- Aggregate reporting with Wilson confidence intervals.
- Prior-vs-new comparison with bootstrap CI and McNemar signal.
- PRD-derived seed cases covering more than 10 scenarios and modalities.

## Quick Start

Run the test suite:

```bash
python3 -m unittest discover -s tests
```

Validate the seed cases:

```bash
python3 -m mavis_eval validate cases/examples
```

List available cases:

```bash
python3 -m mavis_eval list-cases cases/examples
```

Evaluate a run directory deterministically:

```bash
python3 -m mavis_eval evaluate cases/examples/smoke_seed_cases.json \
  --case-id web_research_001 \
  --run-dir runs/web_research_001 \
  --deterministic-only \
  --out reports/web_research_001.json
```

Build a judge payload for semantic scoring:

```bash
python3 -m mavis_eval judge-payload cases/examples/smoke_seed_cases.json \
  --case-id web_research_001 \
  --run-dir runs/web_research_001 \
  --out judge_payloads/web_research_001.json
```

Combine deterministic assertions with a judge result:

```bash
python3 -m mavis_eval evaluate cases/examples/smoke_seed_cases.json \
  --case-id web_research_001 \
  --run-dir runs/web_research_001 \
  --judge-result judge_results/web_research_001.json \
  --out reports/web_research_001.json
```

Aggregate reports:

```bash
python3 -m mavis_eval report reports --out reports/summary.json
```

Compare a new run against a prior run:

```bash
python3 -m mavis_eval compare --prior reports/prior --new reports/new --out reports/comparison.json
```

## Run Directory Contract

Each agent run should be materialized under a run directory:

```text
runs/<case_id>/
  trajectory.jsonl
  output/
  state/
```

The trajectory is captured by the external evaluation harness from actual tool invocations. It should include tool calls, arguments, observations, state diffs, cost, and latency. It should not include hidden reasoning or agent-written self-justification.

## Important Files

- `PRD.md`: product and benchmark design spec.
- `mavis_eval/`: Python harness.
- `cases/examples/smoke_seed_cases.json`: initial seed case manifest.
- `schemas/case.schema.json`: JSON Schema artifact for external validators.
- `docs/ASSERTION_DSL.md`: deterministic assertion reference.
- `prompts/deliverable_judge_v1.0.txt`: canonical semantic judge prompt.
- `prompts/visual_judge_v1.0.txt`: visual final-state judge prompt.

## Current Scope

This is a local MVP harness. It does not launch Mavis, provision containers, call judge models, or wrap production tools itself. Those integrations should feed run artifacts, trajectory logs, and judge JSON results into this package.
