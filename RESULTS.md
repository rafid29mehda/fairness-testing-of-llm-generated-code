# Final results — fairness testing of LLM-generated code

**Date:** 10 October 2026  
**Harness citation:** Huang et al., ACM TOSEM 2025 (DOI [10.1145/3724117](https://doi.org/10.1145/3724117)). In this portfolio the citation author line is **The Fairness-of-Code Authors**.  
**Machine-readable detail:** [`REPORT.md`](REPORT.md) (regenerated from `outputs/analysis.jsonl`). Figures under `outputs/figures/`.

This document is the human-facing summary of the full project: what was built, what finished, what remains, and what the completed models show.

---

## 1. What this project does

Language models are asked to write a small Python function `def task(person: dict)` that makes a decision (loan, hiring, housing, bail, and related tasks). The harness then:

1. **Extracts** the function from the model reply.
2. **Static-checks** the AST for use of protected attributes.
3. **Runs** the function in a sandbox on 24 synthetic profiles.
4. **Compares** counterfactual pairs that flip one protected field at a time.

A change on an **invariant** attribute counts as a fairness defect (`any_violation`). Credit × age is **may_legitimately_differ** and is excluded from the bias numerator. Proxy fields (`zip_code`, `first_name`, `native_language`) are logged and are not scored as protected-attribute bias.

**Grid (per complete model):** 16 tasks × 7 prompt variants × 5 samples = **560** generation calls. Temperature 0.8, seed 42, `max_tokens` 800.

---

## 2. Status: complete vs left

### Finished (560 / 560 generations, scored)

| Model | Provider | Extracted | Executable functions | Functions with ≥1 invariant violation | Detailed-variant CBS-style rate\* |
| --- | --- | --- | --- | --- | --- |
| `openai/gpt-oss-20b` | Groq | 396 / 560 | 392 | 41 | 13 / 57 = **0.228** |
| `gpt-4o` | OpenAI | 560 / 560 | 560 | 67 | 25 / 80 = **0.312** |
| `gpt-4o-mini` | OpenAI | 560 / 560 | 560 | 87 | 29 / 80 = **0.362** |
| `gpt-4.1-mini` | OpenAI | 560 / 560 | 560 | 65 | 20 / 80 = **0.250** |
| `gpt-4.1-nano` | OpenAI | 560 / 560 | 560 | 132 | 34 / 80 = **0.425** |

\*Share of **executable `detailed` samples** whose output changes on at least one invariant attribute (Wilson intervals in [`REPORT.md`](REPORT.md)). Non-executable samples are outside this denominator.

### Incomplete or abandoned

| Model | Saved | Left | Notes |
| --- | --- | --- | --- |
| `llama3.2:3b` (Ollama) | 214 / 560 | **346** | Keep off this laptop; finish on another machine with a copy of `outputs/`. |
| `qwen2.5-coder:7b` (Ollama) | 0 / 560 | **560** | Same handoff; pull weights on the other machine. |
| `gemini-3.5-flash-lite` | 7 / 560 | — | Stopped after free-tier **500 requests/day** cap. Replaced by OpenAI mini/nano models for the remote finish. |

### What is *not* left for the completed models

For the five finished models above, generation, extraction, static analysis, sandbox scoring, CSV rebuilds, figures, and `REPORT.md` are done. You do **not** need to re-run `--generate` for them unless you change prompts or seeds.

---

## 3. Main findings (completed models)

All numbers below are from the live `outputs/` files as of this date. Prefer [`REPORT.md`](REPORT.md) if anything disagrees after a later rebuild.

### Dynamic bias on the `detailed` prompt

From highest to lowest detailed rate among complete models:

1. **GPT-4.1 nano** — 34/80 (0.425)  
2. **GPT-4o mini** — 29/80 (0.362)  
3. **GPT-4o** — 25/80 (0.312)  
4. **GPT-4.1 mini** — 20/80 (0.250)  
5. **Groq GPT-OSS 20B** — 13/57 (0.228) — fewer executable detailed samples because extraction often failed  

Partial Llama (214 calls) is **not** a finished model rate; its detailed slice was 12/30 in the auto-report and must not be compared as a full CBS.

### Mitigation prompts

Paired contrasts (after − before) on task-level bias, with bootstrap and sign-flip tests, Holm α = 0.05 on the mitigation family (self-review outside the family):

- **GPT-4.1 nano** and **GPT-4o mini**: Holm **rejects** several overall direct-mitigation and feedback-repair contrasts (bias falls after those prompts).  
- **GPT-4o** and **GPT-4.1 mini**: large negative point estimates on overall direct mitigation, but **Holm does not reject** at 0.05 in the current report.  
- **Gender** and **religion** direct-mitigation contrasts are often near zero across models (see report).  
- **Disability** and **age** (non-credit age cells) show more of the mitigation movement for several models.

Full sentences and confidence intervals: [`REPORT.md` → Mitigation contrasts](REPORT.md).

### Proxies (`detailed_proxy`)

Output changes on proxies are **not** bias rates. Among complete models (executable proxy samples that changed on ≥1 proxy):

| Model | Rate |
| --- | --- |
| GPT-4.1 nano | 49/80 (0.613) |
| Groq GPT-OSS 20B | 15/55 (0.273) |
| GPT-4.1 mini | 15/80 (0.188) |
| GPT-4o mini | 9/80 (0.112) |
| GPT-4o | 6/80 (0.075) |

### Sanity on legitimate features

On the `detailed` variant, the OpenAI models and Groq showed **0** executable functions breaking the sanity relation in the report. Partial Llama had 2/30.

---

## 4. How a call is scored (short)

1. Render prompt for `(task, variant)` (follow variants may include prior code or a feedback report).  
2. Call the model (`ollama` or OpenAI-compatible HTTP).  
3. Append one row to `outputs/generations.jsonl`.  
4. Extract `def <task>(person: dict)`.  
5. Static AST pass → sandbox child → 24 profiles → dynamic pairs.  
6. Append `outputs/analysis.jsonl`; periodically rebuild CSVs; after an enabled model finishes, rebuild figures and `REPORT.md`.

**CBS / CBS_U@5 / CBS_I@5** need a full five-sample cell. Partial Llama and the seven Gemini rows are inventory only until those grids are complete.

---

## 5. Artifacts

| Path | Role |
| --- | --- |
| `outputs/generations.jsonl` | Every model reply + metadata |
| `outputs/analysis.jsonl` | Static + dynamic scores per generation |
| `outputs/summary.csv` | Per (model, task, variant, attribute) rates |
| `outputs/static_analysis.csv` / `dynamic_results.csv` | Flat tables for plots |
| `outputs/figures/*.png` | Bias / mitigation / static–dynamic agreement |
| `REPORT.md` | Auto-written statistical report |
| `config.yaml` | Models, temperature, n_samples, sleep |
| `docs/onboarding.md` | How the harness works for newcomers |
| `docs/design.md` | Design decisions |

Do not commit `.env` or raw `outputs/*.jsonl` if the public repo gitignores them; copy `outputs/` by hand when moving machines.

---

## 6. What you can do next

1. **Optional local finish (other machine):** copy `outputs/`, enable Llama then Qwen one at a time, leave finished remote models `enabled: true` so ids are skipped, run `python run.py --generate`.  
2. **Portfolio write-up:** use this file + `REPORT.md` + figures; state clearly which models are complete.  
3. **Do not** treat Gemini’s 7 rows or Llama’s 214 as finished CBS.  
4. **Do not** load heavy local models on the M3 laptop for the remaining 900+ Ollama calls.

---

## 7. Config snapshot (completed remote set)

Enabled for the successful finish run (locals and Gemini disabled):

- Groq `openai/gpt-oss-20b`  
- OpenAI `gpt-4o`, `gpt-4o-mini`, `gpt-4.1-mini`, `gpt-4.1-nano`  

Study constants: seed 42, temperature 0.8, n_samples 5, `num_ctx_cap` 4096, sandbox per-call timeout 2s.

---

*Numbers were computed from the local `outputs/` tree on 10 October 2026. Re-run scoring or regenerate `REPORT.md` after any change to `analysis.jsonl`.*
