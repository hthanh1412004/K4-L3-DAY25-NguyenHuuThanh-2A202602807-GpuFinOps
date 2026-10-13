# NimbusAI — GPU Cost Optimization Report

**Period:** monthly

**Baseline spend:** $27,133

**Optimized spend:** $14,639

**Projected savings:** $12,494  (**46%**)

## Savings by lever

| Lever | Savings (USD) |
|---|---|
| Inference (cascade/cache/batch) | $1,199 |
| Purchasing (spot/reserved) | $10,040 |
| Right-size util-lies | $655 |
| Kill idle GPUs | $600 |

## Sustainability

- Energy per reference query: 0.24 Wh
- Carbon per reference query: 0.091 gCO2e
- Cleanest region: europe-north1
- Cheapest electricity region: us-east-wa

_Figures are June-2026 as-of snapshots; re-baseline before acting._

## Phạm vi và phương pháp

Dữ liệu tổng hợp seed=25, snapshot minh họa tháng 06/2026; không phải giá thị trường hiện tại. 7 loại GPU, 264 mẫu telemetry (11 GPU × 24 giờ), 2.400 request và 8 workload. M2 là một ngày traffic; M3/M5 và carbon là kịch bản lặp 30 ngày, cố ý không dùng cột days. Không lấy số mẫu trong Guide.md làm số đo. Kết quả trước khi sửa được lưu trong baseline_results.json.

Baseline chính xác: **$27,133.22/tháng**; optimized: **$14,639.22/tháng**; tiết kiệm **$12,494.00 (46.05%)**. Bốn lever trong bảng đầu được làm tròn USD rồi cộng; các bảng inference dưới đây giữ số thực.

Tổng M5 là dự phóng của mô hình lab: inference API và GPU workload được coi là hai khoản riêng; right-sizing/idle là cơ hội bổ sung trên GPU-hours. CSV không liên kết gpu_id với job_id, nên chưa chứng minh các khoản này độc lập trong hóa đơn thực. Không cộng thêm tiết kiệm điện vào GPU rental vì giá thuê có thể đã bao gồm điện.

## M1 — GPU-Util lie và idle

| GPU | Util (%) | MFU | MBU |
| --- | --- | --- | --- |
| gpu-h100-4 | 98.2 | 0.194 | 0.207 |
| gpu-a10g-1 | 96.9 | 0.268 | 0.302 |

gpu-h100-4 có util cao nhất. Util phản ánh thời gian kernel hoạt động; MFU đo achieved/peak FLOPs. Memory stall, đồng bộ và kernel nhỏ có thể khiến GPU bận nhưng tạo ít FLOPs. Telemetry chưa đủ để khẳng định nguyên nhân; cần profiler để kiểm tra. MBU thấp cũng không tự chứng minh memory-bound, cần arithmetic intensity và roofline.

gpu-h100-5 idle 8 giờ/ngày: 8 × $2.50 = **$20.00/ngày**, **$600.00/tháng**, bằng 2.21% baseline M5. Right-size gợi ý H100→A100 ($511.20/tháng) và A10G→L4 ($144/tháng), tổng $655.20 trước làm tròn. Đây là giả định giữ throughput; cần kiểm tra VRAM, bandwidth và latency trước khi triển khai. Phần chưa sử dụng FLOPs không đồng nghĩa toàn bộ tiền có thể thu hồi.

## M2 — Unit economics và đóng góp từng đòn bẩy

| Bước | USD/ngày | USD/1M-token |
| --- | --- | --- |
| Baseline | 48.8742 | 6.4880 |
| Cascade | 11.4756 | 1.5234 |
| Cache + writes | 10.6946 | 1.4197 |
| Batch | 8.9001 | 1.1815 |

Cùng **7,533,027 input+output token/ngày**; cached input là một phần của input, không cộng lần hai. Inference giảm 81.79%.

| Lever tuần tự | Tiết kiệm USD/ngày | USD/30 ngày |
| --- | --- | --- |
| Cascade | 37.3985 | 1121.96 |
| Cache + writes | 0.7810 | 23.43 |
| Batch | 1.7946 | 53.84 |

Cascade đóng góp nhiều nhất trong inference vì đa số request đi model nhỏ. Đóng góp phụ thuộc thứ tự cascade→cache→batch. Cache 100% input và batch cho hệ số 0.10 × 0.50 = 0.05 trên phần input đọc; output và phí ghi khiến cả request không nhất thiết giảm 95%. Batch chỉ dành cho tác vụ chấp nhận chờ, tránh chat tương tác cần latency thấp.

## Extension 3 — Kinh tế cache

Giả định **4 reads/write**, write surcharge = **1.25 × giá input**; phí ghi không hưởng batch. CSV thiếu prefix_id, số reads và write fee nên không suy ra được reads thực tế. Đây là mô hình phí giả định để thử sensitivity, không gán cho nhà cung cấp cụ thể.

Hòa vốn: reads ≥ write_price / [input_price × (1 − read_discount) × batch_multiplier]. Chi phí ghi phân bổ = cached_tokens / reads × write_price / 1.000.000. cache_is_worth_it() được gọi trước khi áp dụng cache; phần input bị loại cache tính giá bình thường.

| Model | Input USD/1M | Write USD/1M | Reads hòa vốn | Reads hòa vốn batch |
| --- | --- | --- | --- | --- |
| small | 0.20 | 0.25 | 1.389 | 2.778 |
| large | 3.00 | 3.75 | 1.389 | 2.778 |

Cả hai tier cần tối thiểu 2 reads (3 reads nếu batch) với tỷ lệ phí này; ngưỡng giống nhau vì phí ghi tỷ lệ với giá input, không vì giá hai model bằng nhau.

| Reads/write giả định | USD/ngày | USD/1M-token |
| --- | --- | --- |
| 1 | 9.6586 | 1.2822 |
| 2 | 9.3067 | 1.2355 |
| 4 | 8.9001 | 1.1815 |
| 10 | 8.6508 | 1.1484 |

Code gốc bỏ qua phí ghi: **$8.4846/ngày**, **$1.1263/1M-token**. Sau tính phí ghi/gate ở 4 reads: **$8.9001/ngày**, **$1.1815/1M-token**. Chi phí tăng so với dự phóng cũ vì đã tính thêm khoản bị bỏ sót; vẫn thấp hơn phương án không cache.

## M3 — Purchasing

| Job | GPU | Tier | On-demand USD/30 ngày | Optimized USD/30 ngày |
| --- | --- | --- | --- | --- |
| job-train-llm | H100 | spot | 12000 | 7596 |
| job-train-embed | A100 | spot | 2148 | 1393 |
| job-finetune | H100 | spot | 900 | 570 |
| job-infer-chat | A10G | reserved | 4320 | 2592 |
| job-infer-rag | A100 | reserved | 3866 | 2160 |
| job-infer-search | L4 | reserved | 1728 | 972 |
| job-dev-sandbox | A10G | spot | 480 | 203 |
| job-batch-eval | H100 | spot | 225 | 142 |

Các dòng và tổng được làm tròn độc lập, tổng các dòng có thể lệch 1 USD. Purchasing: $25,667 → $15,627, giảm 39.1%. 5 job interruptible dùng spot; effective hours tăng 5,5% do 3% checkpoint + 5% interruptions/giờ × 0,5 giờ rework. Các rate là giả định gốc của lab. 3 job inference ổn định dùng reserved. Threshold 55% là heuristic với discount 45%; job-infer-search chạy 18h/ngày cần kiểm tra trả cho toàn thời gian cam kết. M3 áp giá reserved trên giờ dùng và giả định có commitment sẵn, chưa tính nghĩa vụ hợp đồng 3 năm; chỉ thấy job 30 ngày thì không đủ cơ sở ký mới.

## M4 — Showback và FOCUS

| Team | USD/ngày | % chi phí |
| --- | --- | --- |
| assistant | 2.8157 | 31.64 |
| search | 2.5179 | 28.29 |
| eval | 1.8102 | 20.34 |
| rag | 1.7563 | 19.73 |

Team assistant cao nhất (31.64%). Coverage team/project = 91.79%, vượt gate 80%; chargeback_ready=True trong lab. Chi phí thiếu project giữ nhóm untagged, cần bổ sung owner trước khi quyết toán. M4 dùng cùng hàm pricing với M2, có tính phí ghi cache. focus_export.csv là mẫu 50 request đầu, BilledCost làm tròn 4 chữ số; không đại diện toàn hóa đơn. Schema FOCUS-style tối thiểu giúp tổng hợp nhiều provider theo cùng cột và tiền tệ; chưa phải FOCUS đầy đủ.

## Sustainability và Extension 5 — Carbon-aware scheduling

Mẫu tham chiếu 800 token thường: 0,24 Wh, 0,0912 gCO2e tại us-east-1. Trung bình thực trên 2.400 request (tính multiplier reasoning 80× theo lab): **13.1980 Wh/query**, **5.0153 gCO2e/query**, **31675.31 Wh/ngày**. Energy này là ước lượng từ token, không phải đo wattmeter và không suy diễn cache giảm điện tương ứng giảm giá.

Carbon workload dùng rated watts × hours_per_day × 30 × num_gpus, chỉ lấy interruptible=1, giữ cùng GPU và GPU-hours ở mọi vùng. Bỏ qua PUE/CPU/network/spot overhead; kết quả là kịch bản 30 ngày lặp, không phải tổng theo days thực của job.

| Job | GPU-hours | kWh | us-east-1 gCO2e | europe-north1 gCO2e | Giảm gCO2e |
| --- | --- | --- | --- | --- | --- |
| job-train-llm | 4800 | 3360.00 | 1276800 | 100800 | 1176000 |
| job-train-embed | 1200 | 480.00 | 182400 | 14400 | 168000 |
| job-finetune | 360 | 252.00 | 95760 | 7560 | 88200 |
| job-dev-sandbox | 480 | 72.00 | 27360 | 2160 | 25200 |
| job-batch-eval | 90 | 63.00 | 23940 | 1890 | 22050 |

| Region | USD/kWh | gCO2e/kWh | Điện USD/30 ngày | gCO2e/30 ngày |
| --- | --- | --- | --- | --- |
| us-east-1 | 0.12 | 380 | 507.24 | 1606260 |
| us-west-2 | 0.07 | 120 | 295.89 | 507240 |
| europe-north1 | 0.09 | 30 | 380.43 | 126810 |
| europe-central2 | 0.18 | 660 | 760.86 | 2789820 |
| us-east-wa | 0.055 | 90 | 232.49 | 380430 |

Tổng **4,227.00 kWh**, carbon **1,606,260 → 126,810 gCO2e**, giảm **1,479,450 gCO2e (92.11%)**. Điện us-east-1→vùng sạch nhất: **$507.24 → $380.43**. Rẻ nhất là **us-east-wa**; sạch nhất là **europe-north1**. Nếu ưu tiên giá với carbon ≤120 g/kWh, us-east-wa là phương án cân bằng. us-west-2 bị us-east-wa trội hơn về cả giá và carbon trong bảng giả định này. Batch/training có thể dịch vùng; trước khi chuyển cần kiểm tra dữ liệu, egress, availability GPU và latency. Không có dữ liệu biến động theo giờ, nên extension này chọn vùng chứ chưa tối ưu region-hour.

## Ba hành động ưu tiên cho NimbusAI

1. Chuẩn hóa tagging và tối ưu purchasing cho job checkpointable/ổn định: **Purchasing (spot/reserved)** đóng góp $10,040/tháng, lớn nhất; kiểm tra commitment thực trước khi mua reserved.
2. Áp cascade kèm quality gate, cache có kiểm tra hòa vốn và batch cho tác vụ bất đồng bộ; theo dõi USD/1M-token, chất lượng và p95 latency thay vì chỉ USD/GPU-hour.
3. Tắt H100 idle theo lịch; profile hai GPU bị flag rồi benchmark phương án right-size. Chuyển job interruptible sang vùng sạch nếu đáp ứng dữ liệu/latency; đối chiếu GPU→job để loại trừ savings trùng nhau.
