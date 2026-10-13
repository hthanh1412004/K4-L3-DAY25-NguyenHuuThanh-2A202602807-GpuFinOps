"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}

# Assumptions, not observations: CSV has no prefix IDs, read counts or write fees.
CACHE_READS = 4.0
CACHE_WRITE_MULTIPLIER = 1.25  # additional write USD/1M = 1.25 * input price


def optimized_request_cost(row, avg_cache_reads: float = CACHE_READS,
                           use_cache: bool = True, use_batch: bool = True) -> float:
    """Shared M2/M4 pricing, including amortized writes outside batch discount."""
    inp, out = int(num(row["input_tokens"])), int(num(row["output_tokens"]))
    pin, pout = MODEL_PRICES[row["route_tier"]]
    batch = use_batch and bool(int(num(row["is_batch"])))
    write_price = pin * CACHE_WRITE_MULTIPLIER
    worth_it = pricing.cache_is_worth_it(avg_cache_reads, write_price,
                                        price_in_per_m=pin * (0.5 if batch else 1))
    cached = min(inp, max(0, int(num(row["cached_input_tokens"])))) if use_cache and worth_it else 0
    write_cost = cached / 1e6 * write_price / avg_cache_reads if cached else 0.0
    return pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=batch) + write_cost


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    base_cost = opt_cost = cascade_cost = cache_cost = original_opt_cost = 0.0
    total_tokens = 0
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        total_tokens += inp + out
        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)
        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[r["route_tier"]]
        original_opt_cost += pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=is_batch)
        cascade_cost += optimized_request_cost(r, use_cache=False, use_batch=False)
        cache_cost += optimized_request_cost(r, use_batch=False)
        opt_cost += optimized_request_cost(r)

    stages = [{"stage": name, "daily_usd": cost,
               "per_m": pricing.dollars_per_million(cost, total_tokens)}
              for name, cost in [("Baseline", base_cost), ("Cascade", cascade_cost),
                                 ("Cache + writes", cache_cost), ("Batch", opt_cost)]]
    scenarios = []
    for reads in (1, 2, 4, 10):
        cost = sum(optimized_request_cost(r, reads) for r in rows)
        scenarios.append({"reads": reads, "daily_usd": cost,
                          "per_m": pricing.dollars_per_million(cost, total_tokens)})

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")
        for s in stages:
            print(f"  {s['stage']}: ${s['daily_usd']:.4f}/day, ${s['per_m']:.4f}/1M-token")
        for s in scenarios:
            print(f"  Cache reads/write={s['reads']}: ${s['daily_usd']:.4f}/day")

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
        "baseline_daily_exact": base_cost, "optimized_daily_exact": opt_cost,
        "original_optimized_daily": original_opt_cost, "stages": stages,
        "cache_scenarios": scenarios,
    }


if __name__ == "__main__":
    run()
