# Fairness testing of LLM-generated code

A harness that asks a language model to write a Python decision function, then checks whether that function depends on a protected attribute.

Two people in a test pair differ in one attribute and nothing else. If the pair is labeled `invariant`, the output should stay the same. That is the counterfactual in Huang et al., ACM TOSEM 2025 ([10.1145/3724117](https://doi.org/10.1145/3724117)). The four credit tasks may use age; those pairs are labeled `may_legitimately_differ` and are stored but not counted. A change on `zip_code`, `first_name`, or `native_language` is stored on its own and is not counted either. A rewrite that only breaks the decision fails the sanity check for that task.

Profiles are synthetic. The labels in `tasks/legitimate_use.csv` are research categories tied to the US sources named there. They are not a legal finding. The metric is not demographic parity or equalized odds.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

Copy `.env.example` to `.env` for the Groq model. Local models use Ollama, one loaded at a time. Context is capped at 4096 tokens (`num_ctx_cap` in `config.yaml`).

## Commands

`python run.py` loads the config, checks the 16 tasks and the label table, and exits. It does not call a model.

| Command | What it does |
| --- | --- |
| `python run.py --pilot` | One local sample of `loan_eligibility`. |
| `python run.py --e2e` | Seven Groq calls: every prompt variant, one sample, `loan_eligibility` only. Writes `outputs/e2e/`. Does not start Ollama. |
| `python run.py --generate` | Full grid. 16 tasks, 3 models, 5 samples, 7 variants: 1,680 calls. Resumes from `outputs/generations.jsonl`. |

Generated JSONL, extracted code, and figures are gitignored. CI runs `pytest` only.

## Layout

- `tasks/` — decisions and the legitimate-use table
- `prompts/` — terse, detailed, role, direct mitigation, proxy, self-review, feedback repair
- `analysis/` — extraction, AST scan, counterfactual grid, subprocess sandbox, rates
- `models/` — Ollama, and an OpenAI-compatible client pointed at Groq
- `docs/design.md` — what is counted, and what is left out

## Limits

The sandbox is a subprocess with a timeout, an import allowlist, and resource limits. It is not a boundary against a hostile program. The AST scan misses computed keys, `getattr`, and nested functions. Every task uses `def task(person: dict)`, which is narrower than the free-form prompts in Huang et al.

## References

- Huang, D., Zhang, J. M., Bu, Q., Xie, X., Chen, J., and Cui, H. Bias Testing and Mitigation in LLM-based Code Generation. ACM TOSEM, 2025. https://doi.org/10.1145/3724117 . Code: https://github.com/huangd1999/CBS
- Segura, S., Fraser, G., Sánchez, A. B., and Ruiz-Cortés, A. A Survey on Metamorphic Testing. IEEE TSE, 42(9), 805–824, 2016. https://doi.org/10.1109/TSE.2016.2532875
- Wilson, E. B. Probable inference, the law of succession, and statistical inference. JASA, 22(158), 209–212, 1927. https://doi.org/10.1080/01621459.1927.10502953
- Holm, S. A simple sequentially rejective multiple test procedure. Scandinavian Journal of Statistics, 6(2), 65–70, 1979.
