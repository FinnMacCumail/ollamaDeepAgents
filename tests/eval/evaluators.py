"""Evaluators for the NetBox model-matrix evaluation harness.

Three evaluators, each addressing a distinct quality dimension. Same signature
across the matrix — every model produces uniform DeepAgents-shaped traces, so
these score consistently regardless of which model variant is under test
(per the research doc §4 reframing).

1. `entity_coverage` — code-based. Fraction of `expected_entities` from the
   dataset's reference_output that appear in the answer string. Deterministic,
   no LLM cost. Strong signal for "did the model actually find the things it
   was asked about?" without requiring exhaustive reference answers (NetBox
   state changes; pinning full answers would create constant churn).

2. `completeness_judge` — LLM-as-judge. A separate model reads the question
   and answer and scores completeness 0.0-1.0 with a one-line rationale.
   Catches semantic issues entity-coverage misses (e.g. answer mentions DM-Akron
   but gives wrong counts).

3. `tool_call_efficiency` — trajectory metric over `run.outputs` / the trace.
   Counts tool calls. Lower is better — fewer round-trips for the same answer
   indicates better planning. Useful for spotting the "model that keeps
   re-querying" failure mode without manually reading traces.

Judge-model selection: defaults to `gpt-oss:20b` (local, NOT in the default
matrix — keeps the judge external to the models being judged, avoiding
self-judgment bias). Override via `EVAL_JUDGE_MODEL` env var. Swap to
Anthropic Sonnet or a stronger cloud judge if budget allows; current pick
optimises for "available without extra subscription" and "outside the matrix".
"""

from __future__ import annotations

import json
import os
import re

# v0.2 evaluator signature: (inputs, outputs, reference_outputs) -> dict
# See: https://docs.langchain.com/langsmith/define-evaluators


def entity_coverage(
    inputs: dict,
    outputs: dict,
    reference_outputs: dict,
) -> dict:
    """Fraction of expected entities found in the answer.

    Case-insensitive substring match. Punctuation-tolerant (e.g. "Jimbob's"
    matches "Jimbobs Banking"). Score = matched / total.
    """
    expected: list[str] = reference_outputs.get("expected_entities") or []
    answer: str = outputs.get("answer", "") or ""

    if not expected:
        return {
            "key": "entity_coverage",
            "score": None,
            "comment": "No expected entities defined for this example",
        }

    normalized_answer = _normalize(answer)
    hits = [e for e in expected if _normalize(e) in normalized_answer]
    missed = [e for e in expected if e not in hits]
    score = len(hits) / len(expected)

    comment = f"{len(hits)}/{len(expected)} entities matched"
    if missed:
        comment += f"; missing: {', '.join(missed[:5])}"
    return {"key": "entity_coverage", "score": score, "comment": comment}


def _normalize(s: str) -> str:
    """Lowercase + strip punctuation for tolerant substring matching."""
    return re.sub(r"[^a-z0-9 ]+", "", s.lower())


_JUDGE_PROMPT = """You are scoring the completeness of an answer to a NetBox infrastructure question.

QUESTION:
{question}

ANSWER:
{answer}

EXPECTED ENTITIES (the answer should reference these facts):
{expected}

Score the answer's COMPLETENESS on a 0.0 to 1.0 scale:
- 1.0 = answers all parts of the question, references the expected entities, provides specific values
- 0.5 = partially answers, missing some aspects or specific values
- 0.0 = does not answer the question, or wholly wrong

Respond with JSON only, no prose around it:
{{"score": <float 0.0-1.0>, "rationale": "<one sentence>"}}
"""


_judge_model = None


def _get_judge_model():
    """Lazy-build the judge model so import is free and the matrix can
    swap judges via env without re-importing."""
    global _judge_model
    if _judge_model is None:
        from src.agents.ollama_config import create_ollama_model
        judge_name = os.getenv("EVAL_JUDGE_MODEL", "gpt-oss:20b")
        _judge_model = create_ollama_model(judge_name, validate=False)
    return _judge_model


def completeness_judge(
    inputs: dict,
    outputs: dict,
    reference_outputs: dict,
) -> dict:
    """LLM-as-judge completeness score 0.0-1.0."""
    question = inputs.get("question", "")
    answer = outputs.get("answer", "") or ""
    expected = reference_outputs.get("expected_entities") or []

    if not answer.strip():
        return {
            "key": "completeness",
            "score": 0.0,
            "comment": "Empty answer",
        }

    prompt = _JUDGE_PROMPT.format(
        question=question,
        answer=answer,
        expected="\n".join(f"- {e}" for e in expected) or "(none specified)",
    )

    model = _get_judge_model()
    try:
        response = model.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        # Tolerate models that wrap JSON in fences or prose
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {
                "key": "completeness",
                "score": None,
                "comment": f"Judge returned no JSON: {text[:120]}",
            }
        parsed = json.loads(match.group(0))
        score = float(parsed.get("score", 0.0))
        rationale = str(parsed.get("rationale", ""))[:200]
        return {"key": "completeness", "score": score, "comment": rationale}
    except Exception as e:
        return {
            "key": "completeness",
            "score": None,
            "comment": f"Judge call failed: {type(e).__name__}: {e}",
        }


def tool_call_efficiency(
    inputs: dict,
    outputs: dict,
    reference_outputs: dict,
) -> dict:
    """Count of tool calls used to produce the answer.

    The target wrapper in `run_matrix.py` populates `outputs["tool_call_count"]`
    from the final agent state. Lower is better. Reported as raw count so the
    LangSmith UI can sort the leaderboard on it directly; no normalisation
    here — different query categories have different floors and normalising
    would hide that.
    """
    count = outputs.get("tool_call_count")
    if count is None:
        return {
            "key": "tool_calls",
            "score": None,
            "comment": "tool_call_count not captured in outputs",
        }
    return {
        "key": "tool_calls",
        "score": float(count),
        "comment": f"{count} tool call{'s' if count != 1 else ''}",
    }


ALL_EVALUATORS = [entity_coverage, completeness_judge, tool_call_efficiency]
