"""Run additional meaningful checks without modifying the original tests/ suite."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from finops.pricing import cache_is_worth_it, cache_break_even_reads, request_cost
from missions import carbon_scheduling, m2_inference_levers as m2, m4_allocation as m4


class ExtensionChecks(unittest.TestCase):
    def test_cache_low_high_and_exact_break_even(self):
        for price in (.2, 3.):
            write = 1.25 * price
            self.assertFalse(cache_is_worth_it(1, write, price_in_per_m=price))
            self.assertTrue(cache_is_worth_it(4, write, price_in_per_m=price))
            boundary = cache_break_even_reads(write, price)
            self.assertTrue(cache_is_worth_it(boundary, write, price_in_per_m=price))
            self.assertFalse(cache_is_worth_it(boundary - .001, write, price_in_per_m=price))

    def test_batch_changes_gate_and_write_is_not_discounted(self):
        row = dict(input_tokens=1000, output_tokens=200, cached_input_tokens=800,
                   is_batch=1, route_tier="large")
        self.assertAlmostEqual(m2.optimized_request_cost(row, 2),
                               request_cost(1000, 200, 3., 15., batch=True))
        expected = request_cost(1000, 200, 3., 15., cached_in=800, batch=True) + 800/1e6*3.75/4
        self.assertAlmostEqual(m2.optimized_request_cost(row, 4), expected)

    def test_invalid_cache_inputs(self):
        for reads in (-1, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                cache_is_worth_it(reads, 1)
        for write, price, discount in [(-1, 1, .1), (1, -1, .1), (1, 1, 1.1), (float("nan"), 1, .1)]:
            with self.assertRaises(ValueError):
                cache_break_even_reads(write, price, discount)
        self.assertFalse(cache_is_worth_it(0, 0))
        self.assertFalse(cache_is_worth_it(10, 1, read_discount=1))
        self.assertTrue(cache_is_worth_it(1, 0))

    def test_cache_policy_never_costs_more_than_uncached(self):
        from missions._common import load_csv
        for row in load_csv("token_usage.csv"):
            for reads in (0, 1, 2, 4, 10):
                self.assertLessEqual(m2.optimized_request_cost(row, reads),
                                     m2.optimized_request_cost(row, reads, use_cache=False) + 1e-12)

    def test_m2_m4_reconcile_and_levers_telescope(self):
        result = m2.run(False)
        allocation = m4.run(False)
        self.assertAlmostEqual(sum(allocation["by_team_exact"].values()), result["optimized_daily_exact"])
        costs = [s["daily_usd"] for s in result["stages"]]
        self.assertEqual(costs, sorted(costs, reverse=True))
        self.assertAlmostEqual(sum(costs[i-1]-costs[i] for i in range(1, len(costs))), costs[0]-costs[-1])

    def test_carbon_work_energy_and_regions(self):
        result = carbon_scheduling.run(False)
        self.assertEqual(len(result["jobs"]), 5)
        first = next(j for j in result["jobs"] if j["job_id"] == "job-train-llm")
        self.assertEqual(first["gpu_hours"], 20*30*8)
        self.assertEqual(first["wh"], 20*30*8*700)
        self.assertAlmostEqual(first["before_g"], first["wh"]/1000*380)
        self.assertAlmostEqual(result["saved_g"], result["total_wh"]/1000*(380-30))
        self.assertEqual(result["cheapest"], "us-east-wa")
        self.assertEqual(result["cleanest"], "europe-north1")
        for region in result["regions"]:
            self.assertAlmostEqual(region["carbon_g"], result["total_wh"]/1000*region["g_per_kwh"])
            self.assertAlmostEqual(region["electricity_usd"], result["total_wh"]/1000*region["usd_per_kwh"])
        self.assertAlmostEqual(carbon_scheduling.run(False, days=15)["total_wh"], result["total_wh"]/2)
        with self.assertRaises(ValueError):
            carbon_scheduling.run(False, days=0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
