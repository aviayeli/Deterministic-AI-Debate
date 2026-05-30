# Prompt Engineering Log

This document records every system prompt and user-turn template used by the debate
agents, along with the rationale for each design decision and the iteration history.

---

## 1. PRO Agent System Prompt

**File:** `src/debate/agents/pro.py` — `_SYSTEM` constant (loaded via `settings.LLM_MODEL`)

**Current prompt (default topic):**
```
You are a PRO debater arguing that AI WILL replace software engineers.
Keep your arguments under 200 words to ensure complete JSON output.
You MUST respond with ONLY a raw JSON object — no markdown, no preamble, no explanation.
Output nothing except this exact structure:
{"claim_text": "<your argument>", "addressed_claim_ids": ["<id>", ...]}
```

**Per-topic variant (`_SUFFIX`):**
```
You are a PRO debater. Position: {topic} — AGREE. Keep your arguments under 200 words
to ensure complete JSON output. You MUST respond with ONLY a raw JSON object — no
markdown, no preamble.
Output: {"claim_text": "<your argument>", "addressed_claim_ids": ["<id>", ...]}
```

**Rationale:**
- **Structured output mandate**: The `addressed_claim_ids` field forces the agent to
  explicitly reference opponent claims, operationalising the responsiveness metric.
- **200-word cap**: Prevents token runaway and keeps costs deterministic; empirically
  found to be sufficient for a compelling single-round argument.
- **"No markdown, no preamble"**: Claude models tend to wrap JSON in code fences or add
  "Here is my response:". The explicit prohibition removes post-processing brittleness.
- **`temperature=0`**: Ensures deterministic output for identical inputs, which is the
  core architectural guarantee of the system.

**Iteration history:**
| Version | Change | Outcome |
|---|---|---|
| v0.1 | No word limit | Frequent JSON truncation at 4 096-token boundary |
| v0.2 | Added 200-word cap | Truncation eliminated; output fits in ~350 tokens |
| v0.3 | Added `addressed_claim_ids` | Responsiveness score became computable |
| v0.4 | Added per-topic `_SUFFIX` | Supports arbitrary topics from `config/topics.json` |

---

## 2. CON Agent System Prompt

**File:** `src/debate/agents/con.py` — `_SYSTEM` constant

**Current prompt (default topic):**
```
You are a CON debater arguing that AI will NOT replace software engineers.
Keep your arguments under 200 words to ensure complete JSON output.
You MUST respond with ONLY a raw JSON object — no markdown, no preamble, no explanation.
Output nothing except this exact structure:
{"claim_text": "<your argument>", "addressed_claim_ids": ["<id>", ...]}
```

**Per-topic variant (`_SUFFIX`):**
```
You are a CON debater. Position: {topic} — DISAGREE. Keep your arguments under 200 words
to ensure complete JSON output. You MUST respond with ONLY a raw JSON object — no
markdown, no preamble.
Output: {"claim_text": "<your argument>", "addressed_claim_ids": ["<id>", ...]}
```

**Rationale:** Mirror of the PRO prompt with inverted stance. Symmetric design ensures
evaluation fairness — neither agent has a structural advantage from prompt length or
instruction count.

---

## 3. User-Turn Template (both agents)

**File:** `src/debate/agents/pro.py` and `con.py` — inside `generate_claim()`

```
Round {round_number}. Opponent claims: {context}{search_ctx}
```

Where:
- `{round_number}`: 1-indexed round counter, gives the model temporal context.
- `{context}`: JSON-serialised windowed ledger (last `LEDGER_WINDOW` entries) from
  `LedgerManager.serialize_for_llm()`. Bounded to prevent O(n²) token growth.
- `{search_ctx}`: Optional background facts from the search tool (`" Background facts:
  {facts}"` or empty string). Injected only when a `search_tool` is attached.

**Rationale for windowed context:** Passing the full ledger would cause token costs to
grow quadratically with round count. The `LEDGER_WINDOW` (default 3) was selected via
the sensitivity analysis in `src/debate/sensitivity_runner.py` as the minimum window
that preserves coherent argumentative threading without runaway cost.

---

## 4. Prompt Engineering Principles Applied

| Principle | Implementation |
|---|---|
| **Explicit output format** | JSON schema specified verbatim in every prompt |
| **No ambiguity** | "ONLY a raw JSON object" — leaves no room for wrappers |
| **Failure recovery** | `_call_json()` retries up to 3× on parse failure before raising |
| **Determinism** | `temperature=0` on every LLM call; no sampling randomness |
| **Cost bounding** | `max_tokens=8192` ceiling + 200-word guidance in prompt |
| **Contextual grounding** | Opponent ledger serialised and injected each round |
| **Symmetry** | PRO and CON prompts are structurally identical; only stance differs |

---

## 5. Failed Approaches (for future reference)

| Approach | Problem |
|---|---|
| Chain-of-thought prompting ("think step by step") | Produced reasoning text before JSON, breaking `json.loads()` |
| Asking for confidence scores in output | Models invented non-calibrated scores; removed in favour of `evidence.quality_score` from schema |
| System prompt > 300 tokens | Increased cache miss rate; compressed to current form |
| Passing full ledger history | O(n²) token growth confirmed at round 8+ in benchmarks |
