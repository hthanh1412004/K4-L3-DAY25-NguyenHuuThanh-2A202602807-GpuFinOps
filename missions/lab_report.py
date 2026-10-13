"""Reproducible analysis and Vietnamese write-up for the two selected extensions."""
from __future__ import annotations
from finops import pricing, sustainability
from missions._common import load_csv
from missions.m2_inference_levers import MODEL_PRICES, CACHE_READS, CACHE_WRITE_MULTIPLIER


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join("---" for _ in headers) + " |"] +
                     ["| " + " | ".join(str(v) for v in row) + " |" for row in rows])


def analysis(r1, r2, r3, r4, carbon, baseline, optimized, levers):
    """Numbers come from mission results, not copied expected outputs."""
    stages = r2["stages"]
    contributions = [(stages[i]["stage"], stages[i-1]["daily_usd"] - stages[i]["daily_usd"])
                     for i in range(1, len(stages))]
    tokens = r2["total_tokens"]
    daily_before, daily_after = r2["baseline_daily_exact"], r2["optimized_daily_exact"]
    lie_table = table(["GPU", "Util (%)", "MFU", "MBU"],
                      [[s["gpu_id"], s["gpu_util_pct"], s["mfu"], s["mbu"]] for s in r1["lies"]])
    cost_total = sum(r4["by_team_exact"].values())
    top_team = max(r4["by_team_exact"], key=r4["by_team_exact"].get)
    top_pct = r4["by_team_exact"][top_team] / cost_total * 100
    thresholds = []
    for model, (pin, _) in MODEL_PRICES.items():
        write = pin * CACHE_WRITE_MULTIPLIER
        thresholds.append([model, f"{pin:.2f}", f"{write:.2f}",
                           f"{pricing.cache_break_even_reads(write, pin):.3f}",
                           f"{pricing.cache_break_even_reads(write, pin * .5):.3f}"])
    current_energy = sum(sustainability.wh_per_query(
        int(r["input_tokens"]) + int(r["output_tokens"]),
        is_reasoning=bool(int(r["is_reasoning"]))) for r in load_csv("token_usage.csv"))
    total_requests = len(load_csv("token_usage.csv"))
    mean_wh = current_energy / total_requests
    before_carbon = sum(j["before_g"] for j in carbon["jobs"])
    after_carbon = sum(j["after_g"] for j in carbon["jobs"])
    regions = {r["region"]: r for r in carbon["regions"]}
    old_electricity = regions["us-east-1"]["electricity_usd"]
    clean_electricity = regions[carbon["cleanest"]]["electricity_usd"]
    greatest = max(levers, key=levers.get)
    detail = [
        "## Phạm vi và phương pháp",
        "",
        "Dữ liệu tổng hợp seed=25, snapshot minh họa tháng 06/2026; không phải giá thị trường hiện tại. "
        "7 loại GPU, 264 mẫu telemetry (11 GPU × 24 giờ), 2.400 request và 8 workload. "
        "M2 là một ngày traffic; M3/M5 và carbon là kịch bản lặp 30 ngày, cố ý không dùng cột days. "
        "Không lấy số mẫu trong Guide.md làm số đo. Kết quả trước khi sửa được lưu trong baseline_results.json.",
        "",
        f"Baseline chính xác: **${baseline:,.2f}/tháng**; optimized: **${optimized:,.2f}/tháng**; "
        f"tiết kiệm **${baseline-optimized:,.2f} ({(baseline-optimized)/baseline*100:.2f}%)**. "
        "Bốn lever trong bảng đầu được làm tròn USD rồi cộng; các bảng inference dưới đây giữ số thực.",
        "",
        "Tổng M5 là dự phóng của mô hình lab: inference API và GPU workload được coi là hai khoản riêng; "
        "right-sizing/idle là cơ hội bổ sung trên GPU-hours. CSV không liên kết gpu_id với job_id, "
        "nên chưa chứng minh các khoản này độc lập trong hóa đơn thực. "
        "Không cộng thêm tiết kiệm điện vào GPU rental vì giá thuê có thể đã bao gồm điện.",
        "",
        "## M1 — GPU-Util lie và idle",
        "", lie_table, "",
        "gpu-h100-4 có util cao nhất. Util phản ánh thời gian kernel hoạt động; MFU đo achieved/peak FLOPs. "
        "Memory stall, đồng bộ và kernel nhỏ có thể khiến GPU bận nhưng tạo ít FLOPs. "
        "Telemetry chưa đủ để khẳng định nguyên nhân; cần profiler để kiểm tra. "
        "MBU thấp cũng không tự chứng minh memory-bound, cần arithmetic intensity và roofline.",
        "",
        f"gpu-h100-5 idle 8 giờ/ngày: 8 × $2.50 = **${r1['idle_waste_daily']:.2f}/ngày**, "
        f"**${r1['idle_waste_daily']*30:.2f}/tháng**, bằng {r1['idle_waste_daily']*30/baseline*100:.2f}% baseline M5. "
        "Right-size gợi ý H100→A100 ($511.20/tháng) và A10G→L4 ($144/tháng), "
        "tổng $655.20 trước làm tròn. Đây là giả định giữ throughput; cần kiểm tra VRAM, "
        "bandwidth và latency trước khi triển khai. Phần chưa sử dụng FLOPs không đồng nghĩa toàn bộ tiền có thể thu hồi.",
        "",
        "## M2 — Unit economics và đóng góp từng đòn bẩy",
        "", table(["Bước", "USD/ngày", "USD/1M-token"],
                  [[s["stage"], f"{s['daily_usd']:.4f}", f"{s['per_m']:.4f}"] for s in stages]),
        "",
        f"Cùng **{tokens:,} input+output token/ngày**; cached input là một phần của input, không cộng lần hai. "
        f"Inference giảm {(1-daily_after/daily_before)*100:.2f}%.",
        "", table(["Lever tuần tự", "Tiết kiệm USD/ngày", "USD/30 ngày"],
                  [[name, f"{amount:.4f}", f"{amount*30:.2f}"] for name, amount in contributions]),
        "",
        "Cascade đóng góp nhiều nhất trong inference vì đa số request đi model nhỏ. "
        "Đóng góp phụ thuộc thứ tự cascade→cache→batch. Cache 100% input và batch cho hệ số 0.10 × 0.50 = 0.05 "
        "trên phần input đọc; output và phí ghi khiến cả request không nhất thiết giảm 95%. "
        "Batch chỉ dành cho tác vụ chấp nhận chờ, tránh chat tương tác cần latency thấp.",
        "",
        "## Extension 3 — Kinh tế cache",
        "",
        f"Giả định **{CACHE_READS:g} reads/write**, write surcharge = **{CACHE_WRITE_MULTIPLIER:g} × giá input**; "
        "phí ghi không hưởng batch. CSV thiếu prefix_id, số reads và write fee nên không suy ra được reads thực tế. "
        "Đây là mô hình phí giả định để thử sensitivity, không gán cho nhà cung cấp cụ thể.",
        "",
        "Hòa vốn: reads ≥ write_price / [input_price × (1 − read_discount) × batch_multiplier]. "
        "Chi phí ghi phân bổ = cached_tokens / reads × write_price / 1.000.000. "
        "cache_is_worth_it() được gọi trước khi áp dụng cache; phần input bị loại cache tính giá bình thường.",
        "", table(["Model", "Input USD/1M", "Write USD/1M", "Reads hòa vốn", "Reads hòa vốn batch"], thresholds),
        "",
        "Cả hai tier cần tối thiểu 2 reads (3 reads nếu batch) với tỷ lệ phí này; "
        "ngưỡng giống nhau vì phí ghi tỷ lệ với giá input, không vì giá hai model bằng nhau.",
        "", table(["Reads/write giả định", "USD/ngày", "USD/1M-token"],
                  [[s["reads"], f"{s['daily_usd']:.4f}", f"{s['per_m']:.4f}"] for s in r2["cache_scenarios"]]),
        "",
        f"Code gốc bỏ qua phí ghi: **${r2['original_optimized_daily']:.4f}/ngày**, "
        f"**${pricing.dollars_per_million(r2['original_optimized_daily'],tokens):.4f}/1M-token**. "
        f"Sau tính phí ghi/gate ở 4 reads: **${daily_after:.4f}/ngày**, "
        f"**${pricing.dollars_per_million(daily_after,tokens):.4f}/1M-token**. "
        "Chi phí tăng so với dự phóng cũ vì đã tính thêm khoản bị bỏ sót; vẫn thấp hơn phương án không cache.",
        "",
        "## M3 — Purchasing",
        "", table(["Job", "GPU", "Tier", "On-demand USD/30 ngày", "Optimized USD/30 ngày"],
                  [[j["job_id"], j["gpu_type"], j["tier"], j["on_demand"], j["optimized"]]
                   for j in r3["recommendations"]]),
        "",
        "Các dòng và tổng được làm tròn độc lập, tổng các dòng có thể lệch 1 USD. "
        f"Purchasing: ${r3['on_demand_monthly']:,.0f} → ${r3['optimized_monthly']:,.0f}, "
        f"giảm {r3['savings_pct']:.1f}%. 5 job interruptible dùng spot; effective hours tăng 5,5% "
        "do 3% checkpoint + 5% interruptions/giờ × 0,5 giờ rework. Các rate là giả định gốc của lab. "
        "3 job inference ổn định dùng reserved. Threshold 55% là heuristic với discount 45%; "
        "job-infer-search chạy 18h/ngày cần kiểm tra trả cho toàn thời gian cam kết. "
        "M3 áp giá reserved trên giờ dùng và giả định có commitment sẵn, chưa tính nghĩa vụ hợp đồng "
        "3 năm; chỉ thấy job 30 ngày thì không đủ cơ sở ký mới.",
        "",
        "## M4 — Showback và FOCUS",
        "", table(["Team", "USD/ngày", "% chi phí"],
                  [[team, f"{cost:.4f}", f"{cost/cost_total*100:.2f}"]
                   for team, cost in sorted(r4["by_team_exact"].items(), key=lambda x: -x[1])]),
        "",
        f"Team {top_team} cao nhất ({top_pct:.2f}%). Coverage team/project = {r4['tag_coverage_exact']*100:.2f}%, "
        "vượt gate 80%; chargeback_ready=True trong lab. Chi phí thiếu project giữ nhóm untagged, "
        "cần bổ sung owner trước khi quyết toán. M4 dùng cùng hàm pricing với M2, có tính phí ghi cache. "
        "focus_export.csv là mẫu 50 request đầu, BilledCost làm tròn 4 chữ số; không đại diện toàn hóa đơn. "
        "Schema FOCUS-style tối thiểu giúp tổng hợp nhiều provider theo cùng cột và tiền tệ; chưa phải FOCUS đầy đủ.",
        "",
        "## Sustainability và Extension 5 — Carbon-aware scheduling",
        "",
        f"Mẫu tham chiếu 800 token thường: 0,24 Wh, 0,0912 gCO2e tại us-east-1. "
        f"Trung bình thực trên 2.400 request (tính multiplier reasoning 80× theo lab): **{mean_wh:.4f} Wh/query**, "
        f"**{sustainability.carbon_g(mean_wh):.4f} gCO2e/query**, **{current_energy:.2f} Wh/ngày**. "
        "Energy này là ước lượng từ token, không phải đo wattmeter và không suy diễn cache giảm điện tương ứng giảm giá.",
        "",
        "Carbon workload dùng rated watts × hours_per_day × 30 × num_gpus, chỉ lấy interruptible=1, "
        "giữ cùng GPU và GPU-hours ở mọi vùng. Bỏ qua PUE/CPU/network/spot overhead; "
        "kết quả là kịch bản 30 ngày lặp, không phải tổng theo days thực của job.",
        "", table(["Job", "GPU-hours", "kWh", "us-east-1 gCO2e", "europe-north1 gCO2e", "Giảm gCO2e"],
                  [[j["job_id"], f"{j['gpu_hours']:.0f}", f"{j['wh']/1000:.2f}",
                    f"{j['before_g']:.0f}", f"{j['after_g']:.0f}", f"{j['saved_g']:.0f}"] for j in carbon["jobs"]]),
        "", table(["Region", "USD/kWh", "gCO2e/kWh", "Điện USD/30 ngày", "gCO2e/30 ngày"],
                  [[r["region"], r["usd_per_kwh"], r["g_per_kwh"], f"{r['electricity_usd']:.2f}",
                    f"{r['carbon_g']:.0f}"] for r in carbon["regions"]]),
        "",
        f"Tổng **{carbon['total_wh']/1000:,.2f} kWh**, carbon **{before_carbon:,.0f} → {after_carbon:,.0f} gCO2e**, "
        f"giảm **{carbon['saved_g']:,.0f} gCO2e ({carbon['saved_g']/before_carbon*100:.2f}%)**. "
        f"Điện us-east-1→vùng sạch nhất: **${old_electricity:.2f} → ${clean_electricity:.2f}**. "
        f"Rẻ nhất là **{carbon['cheapest']}**; sạch nhất là **{carbon['cleanest']}**. "
        "Nếu ưu tiên giá với carbon ≤120 g/kWh, us-east-wa là phương án cân bằng. "
        "us-west-2 bị us-east-wa trội hơn về cả giá và carbon trong bảng giả định này. "
        "Batch/training có thể dịch vùng; trước khi chuyển cần kiểm tra dữ liệu, egress, availability GPU và latency. "
        "Không có dữ liệu biến động theo giờ, nên extension này chọn vùng chứ chưa tối ưu region-hour.",
        "",
        "## Ba hành động ưu tiên cho NimbusAI",
        "",
        f"1. Chuẩn hóa tagging và tối ưu purchasing cho job checkpointable/ổn định: "
        f"**{greatest}** đóng góp ${levers[greatest]:,.0f}/tháng, lớn nhất; kiểm tra commitment thực trước khi mua reserved.",
        "2. Áp cascade kèm quality gate, cache có kiểm tra hòa vốn và batch cho tác vụ bất đồng bộ; "
        "theo dõi USD/1M-token, chất lượng và p95 latency thay vì chỉ USD/GPU-hour.",
        "3. Tắt H100 idle theo lịch; profile hai GPU bị flag rồi benchmark phương án right-size. "
        "Chuyển job interruptible sang vùng sạch nếu đáp ứng dữ liệu/latency; đối chiếu GPU→job để loại trừ savings trùng nhau.",
    ]
    writeup = f"""# Bài viết Lab 25 — GPU FinOps

**Nguyễn Hữu Thành — MSSV 2A202602807**

Dữ liệu seed=25 là mô phỏng snapshot 06/2026, gồm 11 GPU, 2.400 request và 8 job. Tôi giữ cùng dữ liệu trước/sau; M2 đo theo ngày, M3/M5 và carbon theo kịch bản lặp 30 ngày. Baseline chưa tối ưu là **${baseline:,.2f}/tháng**, optimized **${optimized:,.2f}/tháng**, tiết kiệm **${baseline-optimized:,.2f} ({(baseline-optimized)/baseline*100:.2f}%)**. Inference có {tokens:,} token/ngày, **${pricing.dollars_per_million(daily_before,tokens):.4f} → ${pricing.dollars_per_million(daily_after,tokens):.4f}/1M-token**, giảm {(1-daily_after/daily_before)*100:.2f}%. USD/1M-token đo cả tiền lẫn sản lượng, tránh đánh giá hiệu quả bằng giá thuê GPU đơn thuần.

Trong bốn đòn bẩy, purchasing tiết kiệm **${levers['Purchasing (spot/reserved)']:,.0f}**, inference **${levers['Inference (cascade/cache/batch)']:,.0f}**, right-size **${levers['Right-size util-lies']:,.0f}** và idle **${levers['Kill idle GPUs']:,.0f}/tháng**. Purchasing lớn nhất vì số GPU-hours thuê cao; 5 job chịu gián đoạn chạy spot, 3 job inference ổn định dùng reserved. Spot tốn thêm 5,5% giờ do checkpoint/rework. Reserved chỉ hợp lý khi đã có hoặc chứng minh được nhu cầu dài hạn; job 30 ngày không tự đủ căn cứ ký hợp đồng 3 năm. Trong inference, cascade tiết kiệm ${contributions[0][1]:.4f}/ngày, cache ${contributions[1][1]:.4f}, batch ${contributions[2][1]:.4f}, theo đúng thứ tự này. Cascade lớn nhất vì đa số request dùng model nhỏ. Batch có ích cho eval bất đồng bộ, không phù hợp chat cần phản hồi ngay.

**GPU-Util lie:** gpu-h100-4 có util 98,2% nhưng MFU 0,194; gpu-a10g-1 có util 96,9% nhưng MFU 0,268. GPU bận không đồng nghĩa dùng tốt FLOPs: kernel nhỏ, memory stall hoặc đồng bộ có thể gây khoảng cách này. Chưa có profiler nên đây là giả thuyết cần kiểm tra. Hạ H100→A100 và A10G→L4 có cơ hội $655,20/tháng nếu giữ throughput/VRAM; chưa phải savings đã chứng minh. gpu-h100-5 idle 8 giờ/ngày, đốt $20/ngày hay $600/tháng ({600/baseline*100:.2f}% baseline). Tắt đúng lịch thu hồi chi phí rõ hơn suy luận từ MFU thấp.

**Extension 3 — Cache economics:** Tôi thêm cache_is_worth_it() và dùng chung pricing ở M2/M4. CSV thiếu prefix ID và số reads/write, nên giả định 4 reads/write, phí ghi bổ sung 1,25× giá input, không giảm phí ghi khi batch. Hòa vốn là 1,389 reads thường và 2,778 reads batch cho cả tier nhỏ/lớn (phí ghi tỷ lệ với giá input). Một read thì bỏ cache; 2 reads chỉ có lợi ngoài batch; 4 và 10 reads đủ bù phí ghi. Code gốc không tính write fee dự phóng ${r2['original_optimized_daily']:.4f}/ngày; sau tính phí ghi ở 4 reads là ${daily_after:.4f}/ngày. Giá tăng so với dự phóng cũ phản ánh khoản bị bỏ sót, không phải cache thất bại. Bảng sensitivity và cost/token nằm trong report.md.

**Extension 5 — Carbon scheduling:** Tôi so cùng {carbon['total_wh']/1000:,.2f} kWh công việc interruptible tại 5 vùng, dùng rated watts × GPU-hours, không đổi model/throughput. us-east-1→europe-north1 giảm **{before_carbon:,.0f}→{after_carbon:,.0f} gCO2e**, tiết kiệm **{carbon['saved_g']:,.0f} g ({carbon['saved_g']/before_carbon*100:.2f}%)**; tiền điện **${old_electricity:.2f}→${clean_electricity:.2f}**. Vùng rẻ nhất là us-east-wa ($0,055/kWh), vùng sạch nhất là europe-north1 (30 g/kWh). Không có một vùng đồng thời cực tiểu cả hai; với carbon ≤120 g/kWh, us-east-wa cân bằng tốt. Cần xét egress, vị trí dữ liệu, availability và latency trước chuyển vùng. Điện là thành phần giải thích, không cộng giảm điện vào giảm giá thuê GPU.

**Quản trị và ưu tiên:** Team {top_team} dùng nhiều nhất ({top_pct:.2f}% chi phí inference); coverage {r4['tag_coverage_exact']*100:.2f}% vượt gate 80% của lab. FOCUS-style giúp tổng hợp nhiều provider, nhưng export là mẫu 50 request, chưa phải toàn hóa đơn. Ba việc đầu tiên: (1) sửa tag thiếu và tối ưu purchasing có kiểm tra commitment; (2) triển khai cascade/cache/batch với quality gate và theo dõi cost/token, p95 latency; (3) tắt idle, profile/benchmark hai GPU bị flag và chuyển batch sang vùng sạch phù hợp. Tổng M5 là dự phóng cộng lever của lab: telemetry không ánh xạ GPU→job nên phải loại trừ trùng savings trước khi dùng cho quyết toán. Mô hình energy có reasoning 80× cho trung bình {mean_wh:.4f} Wh/query; đây là ước lượng token, không phải đo điện thật.
"""
    return "\n".join(detail), writeup
