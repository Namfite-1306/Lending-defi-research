# Triển khai A–E: kỳ mục tiêu đến 30/09/2026

## Phạm vi và nơi lưu

- Dữ liệu mục tiêu: Ethereum mainnet, UTC `[2023-01-27, 2026-10-01)`.
- Aave V3 Pool; Compound III Comet USDC; Morpho Blue. Đây không phải mọi market Compound hoặc mọi phiên bản Morpho.
- Pilot gốc giữ nguyên tại `data/runs/stress_20250203_smoke`.
- Bản mở rộng và bằng chứng: `data/runs/expansion_20260930`.
- Báo cáo Excel: `../outputs/defi-data-expansion/Bao_cao_data_A_E_RQ1_7.xlsx`.

## Chạy và tái lập

Dùng Python >=3.9. Chỉ đọc RPC, không có thao tác ký hoặc gửi giao dịch.

```
python -m unittest discover -s tests -v
python -m defi_data.expansion history --minutes 20 --workers 3 --chunk 1000
python -m defi_data.expansion enrich
python -m defi_data.expansion window
python -m defi_data.expansion versions
python -m defi_data.expansion_report
```

Đặt `ETH_RPC_URLS` trong môi trường nếu có nguồn archive đủ năng lực; không ghi key vào mã hoặc báo cáo. Các nguồn công khai đã thử trả nhiều khoảng lịch sử rỗng bất thường hoặc giới hạn tốc độ. Không có tài khoản/API trả phí nào được mua hoặc tự tạo.

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

## Nguồn

- https://aave.com/docs/aave-v3/smart-contracts/pool
- https://github.com/aave-dao/aave-v3-origin
- https://github.com/compound-finance/comet
- https://github.com/morpho-org/morpho-blue
- https://www.bankofcanada.ca/wp-content/uploads/2026/04/sap2026-13.pdf
- https://arxiv.org/html/2512.11363v1 liên kết DOI Zenodo 17898640; API trả HTTP 404 trong lần thử. Không có dữ liệu Zenodo nào được nhập và chưa xác minh được khả năng tải trực tiếp từ DOI.
