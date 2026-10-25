# H1: bảng kết quả chính theo quý

Joint ETH/BTC shock20%, factor-family1:1. Eligible-debt share dùng tổng nợ sau shock; baseline debt là nợ risk trước shock. Không phải realized liquidations. Knot là piecewise-linear descriptive knot trên grid1 điểm %.

| Quý | Ví còn nợ | Baseline risk debt, tỷUSD | Eligible-debt share ở shock20% | Share-knot |
|---|---:|---:|---:|---:|
| 2023Q1 | 1,664 | 0.3498 | 0.578% | 17% |
| 2023Q2 | 2,829 | 0.6935 | 5.135% | 14% |
| 2023Q3 | 4,721 | 1.0942 | 4.487% | 26% |
| 2023Q4 | 6,599 | 1.9336 | 3.925% | 29% |
| 2024Q1 | 8,339 | 4.4515 | 4.792% | 34% |
| 2024Q2 | 10,947 | 6.2904 | 4.392% | 22% |
| 2024Q3 | 13,892 | 6.3267 | 2.408% | 22% |
| 2024Q4 | 16,346 | 11.4045 | 3.238% | 32% |
| 2025Q1 | 18,419 | 9.1115 | 6.999% | 25% |
| 2025Q2 | 22,572 | 13.6940 | 1.493% | 27% |
| 2025Q3 | 27,612 | 21.2033 | 2.635% | 30% |
| 2025Q4 | 28,128 | 17.2091 | 3.814% | 26% |
| 2026Q1 | 29,688 | 13.2190 | 3.079% | 28% |

Nguồn: evidence/H1_baseline.csv, H1_stress_curves.csv, H1_breakpoints.csv. Mỗi bảng nguồn có hash trong provenance.json; giữ precision đầy đủ trong CSV. Không dùng13quý để suy luận biến động hằng ngày hoặc coi mỗi grid point là quan sát độc lập.