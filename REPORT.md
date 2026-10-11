# Report

Numbers below are computed from `outputs/analysis.jsonl`. Duplicate generation ids keep the last record.

Analyzed generations: 3021.

## Dynamic bias by model

- `gemini-3.5-flash-lite` detailed, any invariant attribute: 0/1 = 0.0000 (Wilson 95% 0.0000 to 0.7935).
- `gpt-4.1-mini` detailed, any invariant attribute: 20/80 = 0.2500 (Wilson 95% 0.1681 to 0.3548).
- `gpt-4.1-nano` detailed, any invariant attribute: 34/80 = 0.4250 (Wilson 95% 0.3226 to 0.5343).
- `gpt-4o` detailed, any invariant attribute: 25/80 = 0.3125 (Wilson 95% 0.2215 to 0.4207).
- `gpt-4o-mini` detailed, any invariant attribute: 29/80 = 0.3625 (Wilson 95% 0.2657 to 0.4719).
- `llama3.2:3b` detailed, any invariant attribute: 12/30 = 0.4000 (Wilson 95% 0.2459 to 0.5768).
- `openai/gpt-oss-20b` detailed, any invariant attribute: 13/57 = 0.2281 (Wilson 95% 0.1384 to 0.3521).

## Mitigation contrasts

Each number is the mean paired change in task-level bias rate, after minus before. A negative change is a lower bias rate after the prompt change. Within each model, Holm at 0.05 covers the overall direct-mitigation contrast, the six protected-attribute direct-mitigation contrasts, and the overall feedback-repair contrast. Self-review is outside that family.

### `gemini-3.5-flash-lite`

Not enough paired tasks for: direct mitigation, any invariant attribute; direct mitigation, gender; direct mitigation, race_ethnicity; direct mitigation, age; direct mitigation, religion; direct mitigation, disability; direct mitigation, marital_status; feedback repair, any invariant attribute.
- self-review, any invariant attribute: not enough paired tasks. This contrast is outside the Holm family.

### `gpt-4.1-mini`

- direct mitigation, any invariant attribute: change -0.2500 across 16 tasks, bootstrap 95% -0.4500 to -0.0625, sign-flip p=0.0690. Holm does not reject this contrast.
- direct mitigation, gender: change 0.0000 across 16 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, race_ethnicity: change 0.0000 across 16 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, age: change -0.3333 across 12 tasks, bootstrap 95% -0.5833 to -0.1167, sign-flip p=0.0598. Holm does not reject this contrast.
- direct mitigation, religion: change 0.0000 across 16 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, disability: change -0.2375 across 16 tasks, bootstrap 95% -0.4375 to -0.0625, sign-flip p=0.0690. Holm does not reject this contrast.
- direct mitigation, marital_status: change -0.0625 across 16 tasks, bootstrap 95% -0.1875 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- feedback repair, any invariant attribute: change -0.2500 across 16 tasks, bootstrap 95% -0.4500 to -0.0625, sign-flip p=0.0690. Holm does not reject this contrast.
- self-review, any invariant attribute: change -0.2375 across 16 tasks, bootstrap 95% -0.4375 to -0.0625, sign-flip p=0.0690. Outside the Holm family.

### `gpt-4.1-nano`

- direct mitigation, any invariant attribute: change -0.4250 across 16 tasks, bootstrap 95% -0.6000 to -0.2625, sign-flip p=0.0001. Holm rejects this contrast.
- direct mitigation, gender: change 0.0000 across 16 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, race_ethnicity: change 0.0000 across 16 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, age: change -0.3833 across 12 tasks, bootstrap 95% -0.6000 to -0.1833, sign-flip p=0.0041. Holm rejects this contrast.
- direct mitigation, religion: change 0.0000 across 16 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, disability: change -0.2750 across 16 tasks, bootstrap 95% -0.4125 to -0.1500, sign-flip p=0.0010. Holm rejects this contrast.
- direct mitigation, marital_status: change -0.0625 across 16 tasks, bootstrap 95% -0.1500 to 0.0000, sign-flip p=0.2515. Holm does not reject this contrast.
- feedback repair, any invariant attribute: change -0.3500 across 16 tasks, bootstrap 95% -0.5375 to -0.1750, sign-flip p=0.0009. Holm rejects this contrast.
- self-review, any invariant attribute: change -0.1250 across 16 tasks, bootstrap 95% -0.2250 to -0.0375, sign-flip p=0.0298. Outside the Holm family.

### `gpt-4o`

- direct mitigation, any invariant attribute: change -0.3125 across 16 tasks, bootstrap 95% -0.5250 to -0.1125, sign-flip p=0.0174. Holm does not reject this contrast.
- direct mitigation, gender: change 0.0000 across 16 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, race_ethnicity: change 0.0000 across 16 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, age: change -0.2333 across 12 tasks, bootstrap 95% -0.4667 to -0.0333, sign-flip p=0.1199. Holm does not reject this contrast.
- direct mitigation, religion: change 0.0000 across 16 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, disability: change -0.3125 across 16 tasks, bootstrap 95% -0.5250 to -0.1125, sign-flip p=0.0174. Holm does not reject this contrast.
- direct mitigation, marital_status: change -0.0625 across 16 tasks, bootstrap 95% -0.1875 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- feedback repair, any invariant attribute: change -0.3000 across 16 tasks, bootstrap 95% -0.5125 to -0.1125, sign-flip p=0.0174. Holm does not reject this contrast.
- self-review, any invariant attribute: change -0.3125 across 16 tasks, bootstrap 95% -0.5250 to -0.1125, sign-flip p=0.0174. Outside the Holm family.

### `gpt-4o-mini`

- direct mitigation, any invariant attribute: change -0.3625 across 16 tasks, bootstrap 95% -0.5625 to -0.1750, sign-flip p=0.0047. Holm rejects this contrast.
- direct mitigation, gender: change 0.0000 across 16 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, race_ethnicity: change -0.0250 across 16 tasks, bootstrap 95% -0.0625 to 0.0000, sign-flip p=0.4982. Holm does not reject this contrast.
- direct mitigation, age: change -0.3333 across 12 tasks, bootstrap 95% -0.5667 to -0.1167, sign-flip p=0.0136. Holm does not reject this contrast.
- direct mitigation, religion: change 0.0000 across 16 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, disability: change -0.3125 across 16 tasks, bootstrap 95% -0.5125 to -0.1250, sign-flip p=0.0151. Holm does not reject this contrast.
- direct mitigation, marital_status: change -0.1250 across 16 tasks, bootstrap 95% -0.2750 to -0.0125, sign-flip p=0.1201. Holm does not reject this contrast.
- feedback repair, any invariant attribute: change -0.3625 across 16 tasks, bootstrap 95% -0.5625 to -0.1750, sign-flip p=0.0047. Holm rejects this contrast.
- self-review, any invariant attribute: change -0.2000 across 16 tasks, bootstrap 95% -0.3250 to -0.0875, sign-flip p=0.0087. Outside the Holm family.

### `llama3.2:3b`

- direct mitigation, any invariant attribute: change -0.4000 across 6 tasks, bootstrap 95% -0.6667 to -0.1333, sign-flip p=0.1219. Holm does not reject this contrast.
- direct mitigation, gender: change 0.0000 across 6 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, race_ethnicity: change 0.0000 across 6 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, age: change -0.6000 across 2 tasks, bootstrap 95% -0.6000 to -0.6000, sign-flip p=0.5029. Holm does not reject this contrast.
- direct mitigation, religion: change 0.0000 across 6 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, disability: change -0.1000 across 6 tasks, bootstrap 95% -0.3000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, marital_status: change -0.2000 across 6 tasks, bootstrap 95% -0.4667 to -0.0333, sign-flip p=0.2470. Holm does not reject this contrast.
- feedback repair, any invariant attribute: change -0.0333 across 6 tasks, bootstrap 95% -0.2333 to 0.1667, sign-flip p=1.0000. Holm does not reject this contrast.
- self-review, any invariant attribute: change 0.0000 across 6 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Outside the Holm family.

### `openai/gpt-oss-20b`

- direct mitigation, any invariant attribute: change -0.2678 across 15 tasks, bootstrap 95% -0.4200 to -0.1311, sign-flip p=0.0031. Holm rejects this contrast.
- direct mitigation, gender: change 0.0000 across 15 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, race_ethnicity: change -0.0133 across 15 tasks, bootstrap 95% -0.0400 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, age: change -0.1889 across 12 tasks, bootstrap 95% -0.3722 to -0.0500, sign-flip p=0.0614. Holm does not reject this contrast.
- direct mitigation, religion: change 0.0000 across 15 tasks, bootstrap 95% 0.0000 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- direct mitigation, disability: change -0.2544 across 15 tasks, bootstrap 95% -0.4111 to -0.1156, sign-flip p=0.0070. Holm rejects this contrast.
- direct mitigation, marital_status: change -0.0267 across 15 tasks, bootstrap 95% -0.0800 to 0.0000, sign-flip p=1.0000. Holm does not reject this contrast.
- feedback repair, any invariant attribute: change -0.2510 across 16 tasks, bootstrap 95% -0.3979 to -0.1208, sign-flip p=0.0042. Holm rejects this contrast.
- self-review, any invariant attribute: change -0.2510 across 16 tasks, bootstrap 95% -0.3979 to -0.1208, sign-flip p=0.0042. Outside the Holm family.


## Proxy prompts

These rates count an output change. They are not bias rates and they are outside the Holm family.

- `gemini-3.5-flash-lite`: 0/1 executable proxy samples changed on at least one proxy (0.0000, Wilson 95% 0.0000 to 0.7935).
- `gpt-4.1-mini`: 15/80 executable proxy samples changed on at least one proxy (0.1875, Wilson 95% 0.1171 to 0.2866).
- `gpt-4.1-nano`: 49/80 executable proxy samples changed on at least one proxy (0.6125, Wilson 95% 0.5029 to 0.7118).
- `gpt-4o`: 6/80 executable proxy samples changed on at least one proxy (0.0750, Wilson 95% 0.0348 to 0.1541).
- `gpt-4o-mini`: 9/80 executable proxy samples changed on at least one proxy (0.1125, Wilson 95% 0.0603 to 0.2002).
- `llama3.2:3b`: 6/29 executable proxy samples changed on at least one proxy (0.2069, Wilson 95% 0.0985 to 0.3839).
- `openai/gpt-oss-20b`: 15/55 executable proxy samples changed on at least one proxy (0.2727, Wilson 95% 0.1728 to 0.4023).

## Sanity checks on legitimate features

- `gemini-3.5-flash-lite` detailed: 0/1 executable functions broke a sanity relation (0.0000).
- `gpt-4.1-mini` detailed: 0/75 executable functions broke a sanity relation (0.0000).
- `gpt-4.1-nano` detailed: 0/75 executable functions broke a sanity relation (0.0000).
- `gpt-4o` detailed: 0/75 executable functions broke a sanity relation (0.0000).
- `gpt-4o-mini` detailed: 0/75 executable functions broke a sanity relation (0.0000).
- `llama3.2:3b` detailed: 2/30 executable functions broke a sanity relation (0.0667).
- `openai/gpt-oss-20b` detailed: 0/54 executable functions broke a sanity relation (0.0000).

## Limits

Profiles are synthetic. The data-flow scan misses computed keys and nested helpers. Legitimate-use labels follow `tasks/legitimate_use.csv`. Credit × age is excluded from the bias numerator. Proxy differences are logged and are not scored as bias. Completed models in this tree include Groq GPT-OSS 20B and OpenAI GPT-4o / 4o-mini / 4.1-mini / 4.1-nano; local Ollama grids may be partial. CBS here is the share of executable samples whose output changes on an invariant attribute. A sample that does not run counts as not biased in CBS_U and CBS_I, and it is outside the dynamic-bias denominator.
