"""
Eval runner — measure tweet quality against a labeled benchmark.

Usage:
    python eval_runner.py                                  # full eval, current models
    python eval_runner.py --model openai/gpt-oss-20b       # override primary model
    python eval_runner.py --compare openai/gpt-oss-120b,llama-3.3-70b-versatile  # A/B side-by-side
    python eval_runner.py --report-only                    # rerun without regenerating (uses cached.json)

Reads bot/evals/tweet_eval.jsonl. For each entry:
  1. Generates a tweet/thread using generate_trend_thread()
  2. Runs intelligence.critique_text() on the output
  3. Scores against the entry's must_include / must_not_include checks
  4. Aggregates pass/fail + critic average

Output: console table + bot/evals/last_run.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Make sibling modules importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

# ruff: noqa: E402
import intelligence
import x_automation_bot as bot

EVAL_PATH    = Path(__file__).resolve().parent / "evals" / "tweet_eval.jsonl"
RESULTS_PATH = Path(__file__).resolve().parent / "evals" / "last_run.json"


def load_evals() -> list[dict]:
    if not EVAL_PATH.exists():
        print(f"Missing eval file: {EVAL_PATH}")
        sys.exit(1)
    return [json.loads(line) for line in EVAL_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


async def generate_for_entry(entry: dict, state: dict) -> str:
    """Run our normal trend-tweet generator on the entry."""
    topic = {
        "angle":      entry["angle"],
        "context":    entry["context"],
        "source_url": entry.get("source_url", ""),
    }
    thread = await bot.generate_trend_thread(topic, state)
    return "\n\n---\n\n".join(thread) if thread else ""


def structural_score(entry: dict, text: str) -> dict:
    """Pass/fail on the entry's must_include + must_not_include lists."""
    txt = (text or "").lower()
    pass_must     = [s for s in entry.get("must_include", [])     if s.lower() in txt]
    fail_must     = [s for s in entry.get("must_include", [])     if s.lower() not in txt]
    pass_must_not = [s for s in entry.get("must_not_include", []) if s.lower() not in txt]
    fail_must_not = [s for s in entry.get("must_not_include", []) if s.lower() in txt]

    total = len(entry.get("must_include", [])) + len(entry.get("must_not_include", []))
    hits  = len(pass_must) + len(pass_must_not)
    return {
        "missing_required":  fail_must,
        "forbidden_present": fail_must_not,
        "structural_score":  (hits / total * 10.0) if total else 10.0,
    }


async def run_eval(model_override: str | None = None) -> dict:
    if model_override:
        os.environ["GROQ_PRIMARY_MODEL"] = model_override
        # Force module reload of the model constant
        bot.GROQ_PRIMARY_MODEL = model_override

    evals = load_evals()
    print(f"\nRunning {len(evals)} evals with primary model: {bot.GROQ_PRIMARY_MODEL}\n")

    state: dict = {
        "stats": {"llm_calls_today": 0},
        "top_tweets": [],
        "bottom_tweets": [],
        "creator_intel": {"top_examples": []},
    }

    results = []
    for e in evals:
        t0 = time.time()
        text = await generate_for_entry(e, state)
        struct = structural_score(e, text)
        critic = await intelligence.critique_text(
            text, "tweet", bot.NICHE, bot.load_style_notes(),
            lambda u, s: bot.call_llm(u, s, state),
        )
        elapsed = time.time() - t0
        results.append({
            "id":              e["id"],
            "kind":            e.get("kind", "?"),
            "generated":       text,
            "critic":          critic,
            "structural":      struct,
            "elapsed_s":       round(elapsed, 2),
        })
        crit_score = critic.get("score", 0)
        flag = "PASS" if crit_score >= 7 and not struct["missing_required"] and not struct["forbidden_present"] else "FAIL"
        print(
            f"  [{flag}] {e['id']:18s} critic={crit_score:>2d}/10  "
            f"struct={struct['structural_score']:>4.1f}/10  "
            f"missing={len(struct['missing_required'])}  forbidden_hit={len(struct['forbidden_present'])}  "
            f"({elapsed:.1f}s)"
        )
        if struct["forbidden_present"]:
            print(f"      ! forbidden present: {struct['forbidden_present']}")
        if struct["missing_required"]:
            print(f"      ! missing required: {struct['missing_required']}")

    # Aggregate
    n = len(results)
    avg_critic = sum(r["critic"].get("score", 0) for r in results) / n if n else 0
    avg_struct = sum(r["structural"]["structural_score"] for r in results) / n if n else 0
    pass_count = sum(
        1 for r in results
        if r["critic"].get("score", 0) >= 7
        and not r["structural"]["missing_required"]
        and not r["structural"]["forbidden_present"]
    )

    summary = {
        "ran_at":          datetime.now(timezone.utc).isoformat(),
        "model":           bot.GROQ_PRIMARY_MODEL,
        "n":               n,
        "pass_count":      pass_count,
        "pass_rate":       round(pass_count / n * 100, 1) if n else 0,
        "avg_critic":      round(avg_critic, 2),
        "avg_structural":  round(avg_struct, 2),
        "results":         results,
    }

    print(f"\n=========================================================")
    print(f" Model: {bot.GROQ_PRIMARY_MODEL}")
    print(f" Pass rate:     {summary['pass_rate']}%   ({pass_count}/{n})")
    print(f" Critic avg:    {summary['avg_critic']}/10")
    print(f" Structural:    {summary['avg_structural']}/10")
    print(f"=========================================================\n")

    RESULTS_PATH.parent.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Full results: {RESULTS_PATH}\n")
    return summary


async def compare_models(models: list[str]) -> None:
    summaries = []
    for m in models:
        print(f"\n--- Evaluating {m} ---")
        s = await run_eval(m)
        summaries.append(s)
    print("\n=========================================================")
    print(" Comparison")
    print("=========================================================")
    print(f" {'Model':40s}  {'Pass%':>6s}  {'Critic':>7s}  {'Struct':>7s}")
    for s in summaries:
        print(f" {s['model']:40s}  {s['pass_rate']:>5.1f}%  {s['avg_critic']:>6.2f}  {s['avg_structural']:>6.2f}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="Override GROQ_PRIMARY_MODEL for the run")
    ap.add_argument("--compare", help="Comma-separated list of models to A/B")
    args = ap.parse_args()

    if args.compare:
        asyncio.run(compare_models([m.strip() for m in args.compare.split(",")]))
    else:
        asyncio.run(run_eval(args.model))


if __name__ == "__main__":
    main()
