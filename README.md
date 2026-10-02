# Telegram Giftcode Bot — Browser-Only

Bot theo dõi các kênh Telegram, trích xuất giftcode từ text/spoiler/OCR và nhập code qua trình duyệt Edge/Chromium kết nối CDP. Bot **không dùng HTTP/API để submit code** và không tự giải CAPTCHA.

## Tính năng chính

- Theo dõi nhiều channel Telegram bằng numeric `chat_id`.
- Trích xuất code từ caption, spoiler, text và media/OCR.
- Hỗ trợ 7 domain: `tangquaqq88.com`, `hi88-freecode.pages.dev`, `livemm88.net`, `rr88code.com`, `xx88code.com`, `gg88live.tv`, `o8code.com`.
- Tab pool riêng theo domain/account.
- Giới hạn concurrency, rate limit và account round-robin.
- Dashboard realtime hiển thị trạng thái submit, phản hồi raw và latency.
- Durable inbox dùng SQLite/WAL để phục hồi sau restart hoặc mất kết nối.

## Retry độc lập theo domain/account

Mỗi lượt fanout được lưu thành một `telegram_inbox_item` riêng trong bảng `telegram_inbox_items`. Item có trạng thái, số lần thử, backoff và lỗi gần nhất độc lập.

Nếu một domain gặp lỗi hạ tầng, chỉ item của domain đó được retry. Những domain đã hoàn tất không bị replay và bot không cần trích xuất lại toàn bộ Telegram message.

Các trạng thái chính gồm `pending`, `processing`, `completed`, `failed`, `PENDING_VERIFICATION` và `SITE_UI_CHANGED`.

## Xử lý HI88 và RR88

### HI88 Turnstile

Khi Turnstile chưa hoàn tất, bot giữ nguyên page, không reload widget, không coi đây là `INFRA_FAILURE` hoặc thất bại nghiệp vụ, trả trạng thái `PENDING_VERIFICATION` và trì hoãn work-item theo backoff.

### RR88 input/UI

Khi không tìm thấy ô nhập code, bot reload trang RR88 một lần, wake tab, scroll và chạy lại input discovery. Nếu vẫn không có input, trả `SITE_UI_CHANGED` và không retry vô hạn.

## Latency metrics

Mỗi submit browser ghi `navigation_ms`, `input_fill_ms`, `challenge_wait_ms`, `result_wait_ms`, `cleanup_ms` và `total_submit_ms`. Dashboard hiển thị phase latency trong cột `Latency phases`; log runtime ghi dòng `[METRIC] submit ... latency={...}`.

## Cấu trúc module

| File | Vai trò |
|---|---|
| `main_script.py` | Entrypoint, Telegram ingress, worker và orchestration |
| `browser_engine.py` | Tab pool, selector, submit, Cloudflare và result detection |
| `browser_site_profiles.py` | Selector, timeout và timing theo từng site |
| `durable_inbox.py` | SQLite inbox và durable work-item lifecycle |
| `media_download_manager.py` | Download media multipart, retry và resume |
| `image_code_extractor.py` | OCR ảnh/video |
| `dashboard.py` | Dashboard realtime và metrics |
| `queue_manager.py` | Queue limit, drop handling và backpressure |
| `database.py` | Lịch sử code/account/submission |
| `config.py` | Đọc `.env` và cấu hình runtime |
| `tests/test_domain_retry_integration.py` | Integration tests retry và HI88/RR88 status |

## Cài đặt và chạy test

Yêu cầu Python 3.11+, Edge/Chromium chạy với CDP và các package trong `requirements.txt`.

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
python3 tests/test_domain_retry_integration.py
```

Kiểm tra compile và static findings:

```bash
python3 -m py_compile *.py tests/test_domain_retry_integration.py
python3 -m compileall -q .
ruff check browser_engine.py main_script.py dashboard.py durable_inbox.py tests/test_domain_retry_integration.py --select F821,F841
```

Các test bao phủ retry độc lập theo domain, không replay domain đã hoàn tất, retry limit, HI88 `PENDING_VERIFICATION` và RR88 `SITE_UI_CHANGED`.

## Vận hành an toàn

Không khởi động bot production khi chưa kiểm tra Edge CDP và `.env`. Backup database trước khi deploy schema mới:

```bash
cp data/telegram_inbox.db data/telegram_inbox.db.backup
```

Kiểm tra schema work-item:

```sql
SELECT name FROM sqlite_master
WHERE type = 'table' AND name = 'telegram_inbox_items';
```

Khi site đổi UI, cập nhật `browser_site_profiles.py` trước khi tăng retry. Theo dõi riêng `PENDING_VERIFICATION`, `SITE_UI_CHANGED`, `INFRA_FAILURE` và latency phase thay vì chỉ nhìn tổng RTT.

## Bảo mật

Không đưa các file sau vào ZIP/phát hành công khai: `.env`, `*.session`, `*.session-journal`, `*.db`, `*.log`, `__pycache__/` và Edge profile/cache. Template cấu hình an toàn nằm trong `.env.example`.

## Kiểm tra nhanh

```bash
python3 tests/test_durable_inbox.py
python3 -m compileall -q .
```

Test không submit giftcode thật; cần Edge/Chromium CDP và môi trường test riêng
để xác minh submit browser end-to-end.

## Trạng thái kiểm thử gần nhất

- Integration tests: **5/5 PASS** trong một vòng.
- Stability test: **20/20 vòng PASS**, tương đương **100/100 test case PASS**.
- Python compile/compileall: **PASS**.
- Ruff checks `F821,F841`: **PASS**.
- Không submit code thật trong các test.
