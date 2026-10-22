# Triển khai A–E: kỳ mục tiêu đến 30/09/2026

**Lưu ý:** đây là luồng expansion cũ, không phải lệnh chạy mô hình. Bản sửa crawl/RPC: [README_CRAWL.md](README_CRAWL.md). Chạy RQ bằng dữ liệu recovery: [README_MODELS.md](README_MODELS.md). Không cần crawl lại để chạy mô hình offline.

## Phạm vi và nơi lưu

- Dữ liệu mục tiêu: Ethereum mainnet, UTC `[2023-01-27, 2026-10-01)`.
- Aave V3 Pool; Compound III Comet USDC; Morpho Blue. Đây không phải mọi market Compound hoặc mọi phiên bản Morpho.
- Pilot gốc giữ nguyên tại `data/runs/stress_20250203_smoke`.
- Bản mở rộng và bằng chứng: `data/runs/expansion_20260930`.
- Báo cáo Excel: `../outputs/defi-data-expansion/Bao_cao_data_A_E_RQ1_7.xlsx`.

## Chạy và tái lập

Dùng Python >=3.11. Chỉ đọc RPC, không có thao tác ký hoặc gửi giao dịch.

```
python -m unittest discover -s tests -v
python -m defi_data.expansion history --minutes 20 --workers 3 --chunk 1000
python -m defi_data.expansion enrich
python -m defi_data.expansion window
python -m defi_data.expansion versions
python -m defi_data.expansion_report
```

Đặt `ETH_RPC_URLS` trong môi trường nếu có nguồn archive đủ năng lực; không ghi key vào mã hoặc báo cáo. Các nguồn công khai đã thử trả nhiều khoảng lịch sử rỗng bất thường hoặc giới hạn tốc độ. Không có tài khoản/API trả phí nào được mua hoặc tự tạo.

### Khi `enrich` báo `-32601: rpc method is not whitelisted`

Đây là endpoint từ chối phương thức JSON-RPC `eth_call`; chưa phải bằng chứng getter `getUserEMode` của hợp đồng bị lỗi. Cấu hình mặc định cũ dùng Blast + Flashbots. Lỗi từ endpoint cuối có thể che mất lỗi rate-limit/network của endpoint trước, nên traceback cũ chưa cho biết đầy đủ nguyên nhân từng nguồn.

Đã đổi mặc định sang Blast, dRPC và MEV Blocker; giá trị `ETH_RPC_URLS` do người dùng đặt vẫn được ưu tiên. RPC client giữ lỗi của từng nguồn theo số thứ tự endpoint, thử lại khi có lỗi mạng/rate-limit tạm thời và bỏ qua phương thức mà một nguồn đã từ chối `-32601` trong cùng phiên client. Không thay lịch sử bằng `latest`, không đổi lỗi E-mode thành mode 0, không cache lỗi. URL/key không xuất hiện trong phần chẩn đoán.

`enrich` kiểm tra chain ID và một `eth_call` tại block snapshot trước khi quét cohort. Tiến trình ghi `status`, `phase` và lỗi vào `data/runs/expansion_20260930/enrichment_status.json`; lỗi RPC ở CLI kết thúc với exit code 1 và thông báo theo bước, không chỉ một traceback thiếu ngữ cảnh.

Chạy lại trong PowerShell:

```powershell
$env:ETH_RPC_URLS = 'https://eth-mainnet.public.blastapi.io,https://eth.drpc.org,https://rpc.mevblocker.io'
python -m defi_data.expansion enrich
```

Kiểm tra ngày 22/10/2026: cả ba nguồn trên trả được single historical `getUserEMode` tại block 21762264; Flashbots trả lỗi HTTP trong cùng lần probe. Bản client mới đã đọc thành công batch E-mode của 3 ví thật tại block này trên chain ID 1, dùng cache tạm riêng. **56/56 test offline đạt**, gồm 10 test mới về quyền phương thức, HTTP error, retry/fallback và trạng thái `enrich`. Chưa xác nhận toàn bộ các bước `enrich` hoặc coverage toàn kỳ; khả năng phục vụ RPC công khai có thể thay đổi.

Bổ sung sau sửa `audit_qa`: **64/64 test offline đạt và audit pilot trực tiếp 15/15 nhóm đạt**. Audit đã dùng chung RPC client, nhận `ETH_RPC_URLS`, bắt buộc đọc mới khi `--live` và lưu nhóm lỗi thay vì dừng bằng thông báo `HTTPError,HTTPError`. Kết quả này xác nhận pilot 3 giờ, chưa chứng nhận toàn bộ run expansion/recovery.

Lần crawl lịch sử dài đã dừng để điều tra phản hồi rỗng. Các checkpoint là **bằng chứng truy vấn**, chưa chứng nhận lịch sử đủ hoặc thực sự không có sự kiện. Exporter hiện cố ý gắn `verified_coverage_fraction=0` và `complete=false`; chỉ thay cổng này sau đối chiếu receipt và nguồn độc lập. Đổi `--chunk` sẽ tạo lưới checkpoint khác; không cộng các lưới chồng nhau để đo coverage. Nên dùng run mới nếu đổi lưới khi tiếp tục toàn kỳ.

## Những cải thiện đã chạy thực tế

**A:** chốt hai block biên và hash, crawl có SQLite/checkpoint, xuất coverage và gaps, phân biệt trạng thái chưa xác minh. Borrower universe toàn kỳ vẫn chưa đủ vì nguồn lịch sử chưa đạt.

**B:** lấy ví có Borrow trong 7.200 block trước snapshot 21762264, chọn xác định 6 ví E-mode và 6 ví thường theo địa chỉ; không dùng việc họ bị thanh lý sau đó để chọn. Lấy balances, debt đã tích lũy, oracle, reserve configuration cùng block. Giải mã đúng outer offset của dynamic tuple E-mode; dùng collateral bitmap khi getter lịch sử hỗ trợ, dùng category cũ nếu không có bitmap; không xử lý custom category priceSource một cách ngầm định. Đối chiếu collateral/debt/HF sai số tương đối 1e-4. Một ví đã hết nợ vẫn nằm trong mẫu và được ghi rõ, không coi là vị thế đang vay.

Snapshot là trạng thái **cuối block**, không phải trạng thái ngay trước từng giao dịch trong block. Sáu checkpoint implementation/provider/oracle chỉ chứng minh các điểm đó; không phải toàn bộ lịch thay đổi cấu hình. Adapter E-mode được chứng minh cho snapshot 2025, không suy ra mọi phiên bản đến 2026 đều tương thích.

**C:** mở Borrow/Supply từ 01/02/2025 đến trước 06/02/2025, đối chiếu key của toàn bộ Borrow/Supply pilot để phát hiện thiếu dữ liệu; kiểm tra cửa sổ 6/24/48 giờ, thứ tự block/transaction/log và same-loan-token reborrow. Mỗi borrow chỉ giữ một motif sớm nhất mỗi cửa sổ để tránh đếm tích Descartes. Lưu `label_available_at`, `right_censored` và `verified_recursive=false`. Một motif tích cực quan sát được trước biên vẫn là ứng viên, nhưng các borrow chưa đủ horizon không được dùng làm mẫu âm. Nhãn chưa chứng minh flow và ownership; chưa có precision/recall hoặc nhóm đối chứng hợp lệ.

**D:** receipt mẫu gồm giao dịch thanh lý và ứng viên theo cửa sổ pilot, cap 40+40; lấy gasUsed/effectiveGasPrice, Swap V2/V3, token decimals, factory, lượng và execution ratio. Pool state tại block trước swap: V2 reserves hoặc V3 slot0/liquidity. Mỗi pool chưa xác minh factory/registry chỉ là pool tương thích signature. Không gán mọi swap thành bán collateral của liquidator. V3 thiếu tick bitmap/liquidityNet nên không đủ đường cong impact; pool đầu tiên tối đa 30, không đại diện toàn thị trường. Không có chi phí MEV/builder/hedging đầy đủ.

**E:** đọc collateral config và balances Compound; `idToMarketParams`, `market`, `position` Morpho theo market ID và cùng snapshot. Giữ Morpho borrow shares ở raw shares, chưa giả làm token/USD. Cần IRM accrual, virtual shares/assets, rounding và đối chiếu trước định giá. Mẫu ví được chọn từ hoạt động pilot nên chỉ dùng kiểm thử adapter, chưa đủ exposure network/cơ chế contagion.

## Cổng dùng mô hình

Chạy được lưới shock trên mẫu Aave đã qua đối chiếu; số dư nợ đủ điều kiện thanh lý không phải số tiền chắc chắn thực thi. RQ2 có mô tả Aave trong 3 giờ pilot. Không có RQ nào đủ dữ liệu cho kết luận toàn kỳ 2023–09/2026. Unit tests kiểm tra mã không chứng minh coverage hay độ chính xác của nhãn nghiên cứu.

Thứ tự cần hoàn tất: archive history → borrower universe & configuration timeline → snapshots nhiều ngày → flow labels & Morpho valuation → DEX replay/depth → calibrated cascade → policy experiments. Báo cáo ghi rõ phần đã đạt và phần chưa đạt; không có tác vụ nền tiếp tục sau bàn giao.

## Sửa lỗi 22/10/2026 và tạo lại đầu ra

Đã sửa sáu lỗi được tái hiện trong lần rà soát code:

| Phần | Hành vi sau sửa |
|---|---|
| Trace funding | Chỉ xác nhận nhánh WETH → ETH → mint khi có call unwrap thành công và dòng ETH tương ứng, không có native balance ban đầu/nguồn native khác trong nhánh. Case không chứng minh được giữ `unresolved`. Nhãn trace cũ được xác minh lại, có `funding_proof_version=2`. |
| Định giá liquidation | Chọn observation trước event theo `(block, transaction_index, log_index)`; không sắp cùng timestamp theo giá và không dùng update từ giao dịch sau. |
| Cổng extended window | Phải có pilot hoàn tất, hash `events.csv` hợp lệ, validation nội bộ đạt và Borrow/Supply sentinel không rỗng. Thiếu đầu vào hoặc thiếu log đối chiếu thì `passed=false`; lần chạy mới vô hiệu hóa trạng thái đạt cũ trước khi bắt đầu. |
| Tuổi giá Chainlink | Giữ `stamp`/updatedAt gốc để tính age; lưu riêng `available_stamp` là thời điểm observation khả dụng. Seed đọc trạng thái tại block được đánh dấu block-end, chưa dùng cho event trước đó trong cùng block. |
| Batch RPC | Retry từng item lỗi bằng single call qua các endpoint đã cấu hình, kể cả lỗi `4444`; giữ kết quả item thành công và không cache lỗi. Endpoint không hỗ trợ batch cũng có đường fallback single call. |
| Coverage | Hợp các checkpoint chồng nhau và cắt theo target trước khi tính số block/gaps. Cổng coverage xác minh của expansion vẫn chưa được nâng tự động. |

Giá xuất bởi `recovery_prices` có `schema_version=2`, `stamp`, `available_stamp`, `transaction_index`, `log_index`. Hourly panel có thêm `source_available_utc`; `source_update_utc` vẫn là thời điểm cập nhật giá gốc. `recovery_features` từ chối CSV giá cũ thiếu metadata này và yêu cầu chạy lại `recovery_prices`, tránh âm thầm tiếp tục dùng thứ tự/tuổi giá sai.

Sau khi có đủ dữ liệu lịch sử và endpoint hoạt động, tạo lại giá → model features → trace labels, rồi audit và khóa hashes mới. Không dùng kết quả định giá, nhãn funding hoặc freeze manifest cũ để xác nhận bản mới. Raw logs/checkpoint đã có không bị xóa bởi bản sửa code.

Đã chạy **46/46 test offline**, gồm 20 test hồi quy mới trong `tests/test_review_regressions.py`, có cả đường hợp lệ và đường phải chặn. Chưa chạy lại toàn bộ qua RPC thật; sửa code không cung cấp thêm archive history cho các endpoint đang prune.

Kế hoạch bàn giao Người 2 và lệnh chạy tiếp nằm ở [NEXT_STEPS_N2_RQ1_RQ4.md](NEXT_STEPS_N2_RQ1_RQ4.md).

## Nguồn

- https://aave.com/docs/aave-v3/smart-contracts/pool
- https://github.com/aave-dao/aave-v3-origin
- https://github.com/compound-finance/comet
- https://github.com/morpho-org/morpho-blue
- https://www.bankofcanada.ca/wp-content/uploads/2026/04/sap2026-13.pdf
- https://arxiv.org/html/2512.11363v1 liên kết DOI Zenodo 17898640; API trả HTTP 404 trong lần thử. Không có dữ liệu Zenodo nào được nhập và chưa xác minh được khả năng tải trực tiếp từ DOI.
