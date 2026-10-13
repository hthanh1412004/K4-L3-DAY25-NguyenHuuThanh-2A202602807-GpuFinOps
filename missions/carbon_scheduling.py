"""Extension 5: compare identical interruptible GPU work across five regions."""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type
from finops.sustainability import REGION_CARBON, REGION_PRICE_KWH, carbon_g, energy_cost_usd


def run(verbose: bool = True, days: int = 30) -> dict:
    """30-day recurring scenario matches M3; days in CSV are not used here.

    Rated GPU watts, no PUE/network/CPU or spot rework. Same GPU-hours everywhere.
    Electricity is an explanatory component, not an extra GPU rental discount.
    """
    if days <= 0:
        raise ValueError("days must be positive")
    cat = catalog_by_type()
    cheapest = min(REGION_PRICE_KWH, key=REGION_PRICE_KWH.get)
    cleanest = min(REGION_CARBON, key=REGION_CARBON.get)
    jobs = []
    for j in load_csv("workloads.csv"):
        if not int(num(j["interruptible"])):
            continue
        hours = num(j["hours_per_day"]) * days * num(j["num_gpus"])
        wh = hours * num(cat[j["gpu_type"]]["watts"])
        before, after = carbon_g(wh, "us-east-1"), carbon_g(wh, cleanest)
        jobs.append({"job_id": j["job_id"], "gpu_type": j["gpu_type"],
                     "gpu_hours": hours, "wh": wh, "before_g": before,
                     "after_g": after, "saved_g": before - after})
    total_wh = sum(j["wh"] for j in jobs)
    regions = [{"region": r, "usd_per_kwh": REGION_PRICE_KWH[r],
                "g_per_kwh": REGION_CARBON[r], "electricity_usd": energy_cost_usd(total_wh, r),
                "carbon_g": carbon_g(total_wh, r)} for r in REGION_CARBON]
    result = {"days": days, "jobs": jobs, "regions": regions, "total_wh": total_wh,
              "cheapest": cheapest, "cleanest": cleanest,
              "saved_g": sum(j["saved_g"] for j in jobs)}
    if verbose:
        print(f"== Carbon scheduling ({days}-day recurring scenario) ==")
        for j in jobs:
            print(f"{j['job_id']}: {j['before_g']:,.0f} -> {j['after_g']:,.0f} gCO2e")
        print(f"Cheapest: {cheapest}; cleanest: {cleanest}; saved: {result['saved_g']:,.0f} gCO2e")
    return result


if __name__ == "__main__":
    run()
