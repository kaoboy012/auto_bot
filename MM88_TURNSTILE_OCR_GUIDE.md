# MM88 — Edge/Turnstile và tối ưu OCR

## Giới hạn quan trọng

Không có cơ chế bypass hoặc né Cloudflare Turnstile trong bản này. Turnstile là bước xác minh do website kiểm soát; bot chỉ giữ nguyên trang, ghi nhận trạng thái chờ và nhường worker cho tin mới.

## Cấu hình Edge đúng cách

1. Dùng **Edge thật** với profile cố định, không dùng InPrivate.
2. Đóng mọi Edge khác đang dùng cùng profile trước khi khởi động Edge CDP.
3. Khởi động Edge với cổng CDP loopback:

   ```text
   msedge.exe --remote-debugging-port=9222 --user-data-dir="D:\AutoBot\edge_bot_profile"
   ```

4. Mở từng website trong Edge, chờ trang tải hoàn tất và thực hiện Turnstile thủ công nếu website yêu cầu.
5. Giữ nguyên IP/mạng, User-Agent, timezone và profile trong suốt phiên. Không đổi proxy giữa các lượt.
6. Không chặn JavaScript, cookie, iframe `challenges.cloudflare.com` hoặc request Turnstile. Không chạy nhiều instance cùng một profile.
7. Chỉ sau khi trang báo xác minh thành công mới để bot tiếp tục nhập mã.

`STEALTH_JS_ENABLED=false` đã được đặt để không ghi đè fingerprint của Edge thật. Đây là thay đổi tương thích, không phải bypass.

## Hành vi khi Turnstile treo

- Bot không reload trang và không gửi lại cùng mã liên tục.
- Item đang chờ được kết thúc để không chặn mã Telegram mới.
- Mã nhận trong lúc website chưa xác minh có thể hết hạn; đây là giới hạn của mã khuyến mãi, không thể khắc phục bằng retry.
- Sau khi xác minh thủ công, mã mới sẽ được xử lý trên tab đã xác minh.

## Tối ưu OCR đã bật

| Thông số | Giá trị mới | Mục đích |
|---|---:|---|
| `MAX_CONCURRENT_OCR` | `2` | Hai ảnh/video có thể OCR đồng thời |
| `MAX_CONCURRENT_MEDIA_DOWNLOADS` | `4` | Tăng throughput tải media |
| `FAST_TELEGRAM_DOWNLOAD` | `true` | Dùng multipart download cho file đủ lớn |
| `FAST_DOWNLOAD_WORKERS` | `6` | Số worker tải multipart |
| `FAST_DOWNLOAD_CHUNK_KB` | `512` | Kích thước chunk cân bằng tốc độ/RAM |
| `MAX_CONCURRENT_SUBMITS_PER_DOMAIN` | `2` | Hai tab submit/domain |

Các bảo vệ `PAUSE_OCR_ON_HIGH_CPU=true`, ngưỡng RAM và giới hạn kích thước file vẫn giữ nguyên. Không nên tăng thêm nếu máy không có RAM/CPU dự phòng.

## Kiểm tra sau khi restart

Theo dõi log các dòng:

```text
[Telegram accepted] ... ingress_to_durable_ms=...
[OCR-TIMING] ... download_ms=... ocr_ms=...
[Browser] SUBMIT ...
PENDING_VERIFICATION ...
```

Mục tiêu là ingress khoảng vài ms, OCR xử lý song song có giới hạn, và không còn chuỗi retry cùng một mã khi `PENDING_VERIFICATION`.
