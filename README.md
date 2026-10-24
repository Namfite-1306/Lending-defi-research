# Nghiên cứu RQ7: Thiết kế tham số thanh lý và đánh đổi chính sách

Tài liệu và mã nguồn bàn giao của **Thành viên 6** cho Câu hỏi nghiên cứu số 7 (RQ7). Thư mục này hoạt động độc lập, đọc dữ liệu snapshot local, không crawl lại, không gọi RPC và không làm thay đổi dữ liệu gốc của nhóm. Yêu cầu Python >= 3.11 với hai thư viện tính toán: NumPy và SciPy.

Đối tượng nghiên cứu: **Aave V3 Ethereum Core Pool** tại block snapshot **21,762,264** với tổng dư nợ khảo sát là **$20,720,453.26 USD**.

---

## 1. Cài đặt và kiểm tra nhanh

Mở PowerShell trong thư mục gốc của dự án:

```powershell
# 1. Kích hoạt môi trường và thiết lập UTF-8
.\.venv\Scripts\Activate.ps1
$env:PYTHONIOENCODING = "utf-8"

# 2. Chạy bộ kiểm thử tự động xác thực dữ liệu và logic tài chính
python -m unittest RQ7/test_rq7_policy_sensitivity.py
```

Kết quả kiểm tra đạt chuẩn khi màn hình in ra:
```text
....
----------------------------------------------------------------------
Ran 4 tests in 0.002s

OK
```
Bộ test kiểm tra 4 điều kiện ràng buộc: các file đầu ra tồn tại đầy đủ, các tham số chính sách nằm trong miền xác định hợp lệ ($0 < CF \le 1$, $0 \le Bonus < 1$), các chỉ số tài chính không âm, và dữ liệu bao phủ đầy đủ 3 mức cú sốc thị trường.

---

## 2. Cách chạy mô hình và tái lập kết quả

### Cách 1: Chạy mô hình độ nhạy độc lập của Thành viên 6 (Khuyên dùng)
Dành cho việc kiểm tra nhanh và xuất lại các bảng số liệu trọng tâm:

```powershell
python RQ7/rq7_policy_sensitivity.py
```
Script tự động đọc kết quả lưới, lọc 6 kịch bản chính sách tiêu biểu ($S0 \rightarrow S5$), tính toán các chỉ số thiệt hại và cập nhật trực tiếp vào [sensitivity_results.csv](sensitivity_results.csv).

### Cách 2: Chạy lại toàn bộ engine mô phỏng 81 kịch bản từ pipeline hệ thống
Dành cho Người 1 (Trưởng nhóm) khi muốn tích hợp và thẩm định lại toàn bộ hệ thống lớn:

```powershell
# Chạy mô phỏng lưới 81 kịch bản trên dữ liệu snapshot on-chain
python -m defi_models rq7 --data-run data/runs/recovery_20261020 --config RQ7/rq7_policy.json --allow-exploratory

# Kiểm định chất lượng số học của đợt chạy mới nhất
$latestRun = (Get-ChildItem -Directory results | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
python scripts/validate_model_run.py $latestRun
```

---

## 3. Cấu trúc thư mục bàn giao

Toàn bộ gói bàn giao nằm gọn trong thư mục `RQ7/`:

| Tên tệp | Định dạng | Mục đích sử dụng |
|---|---|---|
| `README.md` | Markdown | Tài liệu hướng dẫn sử dụng, phương pháp luận và báo cáo nghiên cứu tổng hợp (tệp này). |
| `policy_scenarios.csv` | CSV | Bảng định nghĩa đặc tả 6 kịch bản chính sách trọng tâm ($S0$ đến $S5$). |
| `sensitivity_results.csv` | CSV | Bảng kết quả phân tích độ nhạy định lượng (6 kịch bản $\times$ 3 mức shock = 18 dòng). |
| `policy_grid_81_scenarios.csv` | CSV | Toàn bộ dữ liệu mô phỏng lưới 81 kịch bản đầy đủ kèm nhãn Pareto (`pareto_nondominated`). |
| `summary_validation.json` | JSON | Siêu dữ liệu kiểm định xác nhận snapshot và tính toàn vẹn số học của mô hình (`passed: true`). |
| `rq7_policy.json` | JSON | File cấu hình tham số thí nghiệm (độ sâu DEX $100M, gas $20, dải $CF$, $Bonus$, $LT$). |
| `rq7_policy_sensitivity.py` | Python | Mã nguồn độc lập thực thi tính toán độ nhạy và tạo bảng so sánh. |
| `test_rq7_policy_sensitivity.py` | Python | Bộ kiểm thử tự động (Unit Test) xác thực logic mô hình. |

---

## 4. Thiết kế thí nghiệm và Phương pháp đo lường

### Dải tham số khảo sát
Khảo sát 3 tham số cốt lõi của giao thức Aave V3:
* **Tỷ lệ xử lý tối đa (Close Factor - $CF$):** $\{0.25, 0.50, 1.00\}$ (cho phép thanh lý 25%, 50% hoặc 100% nợ trong 1 lần).
* **Thưởng thanh lý (Liquidation Bonus - $LB$):** $\{0.03, 0.05, 0.08\}$ (mức chiết khấu cho bot thanh lý: 3%, 5%, 8%).
* **Dịch chuyển ngưỡng an toàn ($\Delta LT$):** $\{-0.03, 0.00, +0.03\}$ (nới lỏng 3%, giữ nguyên, hoặc siết chặt 3%).
* **Cú sốc giá thị trường (Shock):** $\{10\%, 20\%, 30\%\}$ (giá ETH/BTC giảm 10%, 20%, 30%).

Tổng không gian trạng thái: $3 \times 3 \times 3 \times 3 = 81$ kịch bản mô phỏng.

### Các chỉ số tài chính đo lường
1. **Tổn thất của người vay (`borrower_collateral_seized_usd`):** Tổng giá trị tài sản thế chấp bị tịch thu và bán thanh lý.
2. **Nợ xấu giao thức (`protocol_shortfall_usd`):** Chênh lệch giá trị kế toán khi tài sản thế chấp không đủ bù đắp nợ vay.
3. **Tác động giá trên DEX (`price_impact_pct`):** Trượt giá tích lũy tối đa khi bot thanh lý bán tài sản ra thị trường AMM (hệ số tác động căn bậc hai, độ sâu $100M USD).
4. **Lợi nhuận ròng của bot thanh lý (`liquidator_profit_usd`):** Doanh thu từ Bonus thanh lý trừ đi chi phí trượt giá DEX và phí gas on-chain.
5. **Sàng lọc tối ưu Pareto (`pareto_nondominated`):** Kịch bản được coi là tối ưu Pareto nếu không tồn tại kịch bản nào khác có cùng mức shock mà tốt hơn ở cả ba mục tiêu: giảm nợ xấu, giảm tịch thu thế chấp và giảm trượt giá DEX.

---

## 5. Bảng kết quả thực nghiệm và Đường biên Pareto

### 6 Kịch bản chính sách trọng tâm (Trích xuất từ `sensitivity_results.csv`)

| Kịch bản | Tên | Mức Shock | Close Factor | Bonus | LT Shift | Thế chấp mất ($) | Nợ xấu ($) | Trượt giá DEX | Lãi Bot ($) | Pareto Optimal |
| :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **S0** | Co_so (Chuẩn Aave V3) | 10% | 50% | 5% | 0% | 169,332.07 | 0.00 | 0.206% | 7,313.74 | Không |
| **S0** | Co_so (Chuẩn Aave V3) | 20% | 50% | 5% | 0% | 534,506.56 | 2,933.89 | 0.283% | 23,113.14 | Không |
| **S0** | Co_so (Chuẩn Aave V3) | 30% | 50% | 5% | 0% | 16,408,266.16 | 58,688.65 | 1.997% | 635,854.84 | Không |
| **S1** | Thuong_thap (Bonus 3%) | 10% | 50% | 3% | 0% | 158,245.74 | 0.00 | 0.199% | 3,917.46 | Không |
| **S1** | Thuong_thap (Bonus 3%) | 20% | 50% | 3% | 0% | 510,511.13 | 976.65 | 0.274% | 12,691.46 | Không |
| **S1** | Thuong_thap (Bonus 3%) | 30% | 50% | 3% | 0% | 16,105,807.67 | 48,546.56 | 1.978% | 327,208.66 | ✔ **ĐẠT** |
| **S2** | Thuong_cao (Bonus 8%) | 10% | 50% | 8% | 0% | 174,170.13 | 0.00 | 0.209% | 12,130.31 | Không |
| **S2** | Thuong_cao (Bonus 8%) | 20% | 50% | 8% | 0% | 541,314.48 | 11,407.77 | 0.283% | 37,803.00 | Không |
| **S2** | Thuong_cao (Bonus 8%) | 30% | 50% | 8% | 0% | 20,939,643.30 | 73,183.54 | 2.268% | 1,384,997.45 | Không |
| **S3** | Nguong_than_trong (LT +3%) | 10% | 50% | 5% | +3% | 16,027.18 | 0.00 | 0.063% | 690.06 | Không |
| **S3** | Nguong_than_trong (LT +3%) | 20% | 50% | 5% | +3% | 462,633.51 | 2,933.89 | 0.283% | 19,941.55 | Không |
| **S3** | Nguong_than_trong (LT +3%) | 30% | 50% | 5% | +3% | 16,408,266.16 | 58,688.65 | 1.997% | 635,854.84 | Không |
| **S4** | Xu_ly_nhieu_hon (CF 100%) | 10% | 100% | 5% | 0% | 322,636.95 | 0.00 | 0.284% | 13,878.97 | Không |
| **S4** | Xu_ly_nhieu_hon (CF 100%) | 20% | 100% | 5% | 0% | 607,379.72 | 2,618.53 | 0.283% | 26,185.54 | Không |
| **S4** | Xu_ly_nhieu_hon (CF 100%) | 30% | 100% | 5% | 0% | 21,695,371.75 | 58,194.46 | 2.299% | 724,834.53 | Không |
| **S5** | Bao_ve_nguoi_vay (CF 25%) | 10% | 25% | 3% | +3% | 13,756.66 | 0.00 | 0.059% | 317.25 | ✔ **ĐẠT** |
| **S5** | Bao_ve_nguoi_vay (CF 25%) | 20% | 25% | 3% | +3% | 410,838.27 | 950.22 | 0.268% | 10,014.13 | ✔ **ĐẠT** |
| **S5** | Bao_ve_nguoi_vay (CF 25%) | 30% | 25% | 3% | +3% | 14,727,720.72 | 48,771.35 | 1.891% | 342,103.00 | ✔ **ĐẠT** |

---

## 6. Phân tích đánh đổi kinh tế và Động cơ thanh lý

### Đánh đổi giữa các mức Close Factor (Tại cú sốc 30%)
So sánh 3 mức Close Factor khi giữ nguyên $Bonus = 3\%$ và $\Delta LT = +3\%$:

* **Close Factor = 25% (Kịch bản S5):** Giảm thiểu tối đa thiệt hại tài sản cho người vay (chỉ mất **$14.72M USD** thế chấp so với $21.29M USD khi thanh lý 100%). Đồng thời giảm áp lực xả hàng ra sàn AMM, trượt giá DEX chỉ ở mức **1.891%**. Nợ xấu giao thức chỉ chênh lệch $730 USD so với phương án xử lý triệt để.
* **Close Factor = 100% (Kịch bản S4):** Dọn sạch nợ nhanh nhất và đưa nợ xấu giao thức về mức thấp nhất tuyệt đối (**$48,041 USD**), nhưng người vay phải chịu thiệt hại nặng nề (mất **$21.29M USD**) và trượt giá DEX tăng vọt lên **2.277%**.

### Động cơ bên thanh lý và Bằng chứng loại bỏ Bonus 8%
So sánh các mức Bonus tại Shock = 20%, Close Factor = 50%, LT Shift = 0%:
* Mức **$Bonus = 3\%$** vẫn mang lại lợi nhuận ròng **$317,000 - $342,000 USD** cho bot tại cú sốc 30%, đủ lớn để bù đắp phí gas và rủi ro trượt giá, kích thích bot thanh lý kịp thời.
* Tăng Bonus lên **8%** làm lợi nhuận bot tăng gấp 3 lần ($12.6k $\rightarrow$ $37.8k), người vay mất thêm hơn $30,000 USD thế chấp, nhưng nợ xấu giao thức **không hề giảm** mà tăng lên **$11,407.77 USD** do trượt giá lớn kích hoạt điểm dừng sớm của bot.
* **Kết luận:** Mức $Bonus = 8\%$ bị loại hoàn toàn khỏi đường biên Pareto vì chỉ tạo ra sự chuyển giao của cải bất công cho bot thanh lý mà không tăng thêm mức độ an toàn cho giao thức.

---

## 7. Khuyến nghị chính sách cho Aave V3 và Tích hợp Người 1

1. **Khuyến nghị tham số:**
   * Trong điều kiện bình thường: Duy trì $Close\ Factor = 50\%$, $Bonus = 3\% - 5\%$.
   * Trong điều kiện thanh khoản mỏng hoặc thị trường sập giá sâu: Kích hoạt cơ chế động hạ $Close\ Factor$ xuống **$25\%$** nhằm giảm áp lực bán tháo dây chuyền và bảo vệ tài sản người vay.
   * Giữ trần Liquidation Bonus tối đa ở mức **$5\%$**, không tăng lên $8\%$.
2. **Hướng dẫn cho Người 1 (Tích hợp báo cáo chung):**
   * Bảng số liệu trong Mục 5 dùng để chèn trực tiếp vào Bảng đánh đổi chính sách của Báo cáo tổng thể.
   * File dữ liệu định lượng gốc nằm tại [sensitivity_results.csv](sensitivity_results.csv) và [policy_grid_81_scenarios.csv](policy_grid_81_scenarios.csv).

---

## 8. Giới hạn mô hình cần lưu ý

1. Mô phỏng dựa trên mô hình Stylized engine của Aave V3; mỗi hành động trả nợ theo rổ nợ tỷ lệ và tịch thu tài sản thế chấp lớn nhất khả dụng, chưa tái tạo chính xác cặp token đơn lẻ trong smart contract thực tế.
2. Hàm trượt giá căn bậc hai (square-root impact) với độ sâu thanh khoản $100M USD là giả định tham số độ nhạy, chưa hiệu chỉnh theo order-book lịch sử từng block.
3. Chỉ số `terminal_collateral_shortfall_usd` là thước đo kế toán của mô hình khi vị thế không còn đủ tài sản bảo đảm, không đồng nhất với nợ xấu được ghi nhận chính thức trên smart contract.
4. Kết quả Pareto chỉ so sánh các phương án chính sách trong cùng một mức cú sốc thị trường; không diễn giải thành tham số tối ưu toàn cục cho mọi điều kiện kinh tế vĩ mô.
