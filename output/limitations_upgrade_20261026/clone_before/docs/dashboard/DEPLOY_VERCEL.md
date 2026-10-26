# Deploy dashboard lên Vercel

## Nguyên nhân và cách sửa

Lỗi `PYTHON_ENTRYPOINT_NOT_FOUND` xuất hiện khi Vercel nhận dự án là Python nhưng không tìm được HTTP entrypoint phù hợp. `python -m defi_live` hiện khởi động HTTP server, collector và các job nền liên tục; nó không phải một serverless entrypoint sẵn dùng.

Bản sửa dùng Vercel cho giao diện tĩnh và một Node request adapter, giữ Python worker ở môi trường chạy liên tục. `vercel.json` đặt framework là Other (`null`), build bằng Node, xuất `public/`. Không cần cài Python/NumPy/SciPy trên Vercel. API nghiên cứu và 7 RQ là JSON tĩnh để tránh giới hạn 4,5 MB của Vercel Functions; các payload này hiện lớn hơn ngưỡng đó.

Nguồn chính thức: [Python runtime](https://vercel.com/docs/functions/runtimes/python), [cấu hình vercel.json](https://vercel.com/docs/project-configuration/vercel-json), [giới hạn Functions](https://vercel.com/docs/functions/limitations#request-body-size).

## Các file phải push

Giữ repository root là thư mục có `vercel.json` và `package.json`. Push các thay đổi trong `api/`, `scripts/deployment/`, `deployment/snapshot/`, `defi_live/web/`, `defi_live/server.py`, các test/docs mới và `.vercelignore`. Gói snapshot nén khoảng 2 MB, phải được đưa lên Git; nó khác các thư mục `data/` và `results/` đang bị ignore. Không push `.env`, API key, `.venv`, `public`, `tmp` hoặc raw dataset.

Nếu chỉ push code mà bỏ `deployment/snapshot`, build sẽ cố ý thất bại vì không đủ evidence, thay vì deploy một dashboard trắng hoặc số liệu giả. `public/` được tạo ở build, không cần commit.

## Thiết lập trên Vercel

1. Chọn đúng repository và branch chứa bản sửa. Root Directory là repository root (`.`), không trỏ vào `defi_live`, `apps/streamlit` hay `defi_live/web`.
2. Framework Preset chọn **Other**, bỏ preset Python/FastAPI/Flask cũ nếu project đang giữ. Cấu hình trong `vercel.json` là nguồn chính.
3. Build Command: `node scripts/deployment/build_vercel.mjs`. Output Directory: `public`. Không dùng `python -m defi_live`, `streamlit run ...`, `npm start` hay `pip install ...` làm build command.
4. Không cần Install Command; dự án deploy không có npm dependency. Nếu Vercel đang lưu override cũ, tắt override hoặc để trống theo `vercel.json`.
5. Redeploy commit mới, bỏ build cache ở lần đầu. Đọc log phải thấy `Static dashboard built: public/; historical evidence verified`.
6. Mở `/start`, `/research`, `/lab`, `/validation`, `/guide`; kiểm tra `/api/deployment`, `/api/research` và `/api/lab/data` trả JSON. Route JSON lớn được phục vụ từ static output, không chạy qua Function.

Chưa có build cloud được xác nhận chỉ từ kiểm tra local. Nếu project vẫn giữ lỗi Python sau khi push đúng commit, kiểm tra Root Directory, Framework Preset và build override trước; ảnh lỗi cũ không chứng minh commit sửa đã được deploy.

## Hai chế độ hoạt động

**Chưa cấu hình backend:** xem/lọc/tải evidence lịch sử và 7 RQ; xem các cascade đã tính. Nhãn hiển thị “Vercel · kết quả lịch sử”. Không chép status/prices/models live cũ lên rồi gắn fresh. What-if bị khóa có giải thích, lựa chọn live bị khóa; đây chưa phải bản real-time hoàn chỉnh.

**Có backend chạy liên tục:** đặt biến server-side `DEFI_BACKEND_URL=https://<hostname-backend>` trên Vercel, rồi redeploy. Không đặt localhost/127.0.0.1: Vercel không thể gọi máy cá nhân bằng địa chỉ loopback. Nếu reverse proxy backend có bearer authentication, đặt thêm `DEFI_BACKEND_TOKEN` ở environment server; token không đưa vào JavaScript hoặc Git. Code Python hiện chưa thực thi bearer authentication, nên cần cấu hình kiểm tra token ở reverse proxy hoặc thêm cơ chế xác thực trước khi mở backend ra Internet.

Backend phải dùng cùng bộ kết quả lịch sử/snapshot với gói deploy. UI kiểm tra block lịch sử của kết quả what-if trước khi hiển thị để tránh so kết quả khác snapshot. Worker cần checkpoint, một process sở hữu job, storage bền vững và giới hạn truy cập/tần suất; adapter không lưu job trong bộ nhớ của Vercel. Endpoint `/api/status` quyết định freshness thực, không dựa vào việc đã có biến môi trường.

Bản sửa chưa tạo máy chủ, tunnel, tài khoản, nguồn RPC trả phí hoặc mở port public. Đưa backend public là bước triển khai riêng cần chọn host và cấu hình truy cập cụ thể. Trong lúc đó, bản local 8790 vẫn chạy collector/what-if như trước.

## Cập nhật gói lịch sử

Sau khi có kết quả được audit và chấp thuận, chạy từ repo với môi trường nghiên cứu và dashboard local đang hoạt động:

```powershell
python scripts/deployment/export_snapshot.py --base http://127.0.0.1:8790
node scripts/deployment/build_vercel.mjs
node --test tests/deployment.test.cjs
```

Exporter chỉ nhận nguồn loopback, yêu cầu đủ 13 quý trong kỳ đã chốt và đủ 7 RQ; loại dữ liệu live, che đường dẫn local và trường bí mật có tên xác định. Manifest ghi hash của từng file nén và thời điểm export. Build kiểm tra hash trước khi xuất JSON. Chạy exporter không thay dataset và không refit mô hình. Review nội dung gói trước khi public nếu nghiên cứu có thêm nguồn riêng trong tương lai.

Muốn xem local theo đúng hai phần static/adapter: `node scripts/deployment/preview_vercel.cjs`, mặc định cổng 8791. Đây là preview của adapter, không thay thế phép kiểm build cloud Vercel.
