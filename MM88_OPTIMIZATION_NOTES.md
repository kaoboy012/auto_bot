# MM88 bot — tối ưu định tuyến và độ trễ

## Đã sửa

1. **Allowlist domain chủ động**
   - `ACTIVE_DOMAINS=hi88,qq88,o8`
   - Chỉ giữ các channel có URL thuộc HI88, QQ88 hoặc O8.
   - Đặt một domain duy nhất, ví dụ `ACTIVE_DOMAINS=hi88`, để chỉ chạy HI88.
   - Đặt hai domain, ví dụ `ACTIVE_DOMAINS=hi88,qq88`, để chạy đồng thời hai domain.

2. **Chặn KJC fan-out ngoài allowlist**
   - Nhánh broadcast spoiler không còn tự đẩy code sang các domain không được bật.

3. **Spoiler fast path**
   - `SPOILER_FAST_PATH=true` làm mã spoiler hợp lệ được đưa vào queue ngay, không quét tiếp caption/plain-text trước khi submit.
   - Offset Telegram được đọc theo UTF-16, nên emoji và ký tự tiếng Việt phía trước spoiler không làm lệch vị trí.

4. **Giảm nhịp drain inbox**
   - `TELEGRAM_INBOX_DRAIN_INTERVAL=0.05`; ingress mới vẫn đánh thức drain loop ngay bằng event.

## Cấu hình domain

- Chạy HI88 + QQ88 + O8: `ACTIVE_DOMAINS=hi88,qq88,o8`
- Chạy hai domain: `ACTIVE_DOMAINS=hi88,qq88`
- Chạy một domain: `ACTIVE_DOMAINS=hi88` hoặc `qq88` hoặc `o8`

Sau khi đổi `ACTIVE_DOMAINS`, phải khởi động lại bot để `CHANNEL_CONFIG`, Telegram handler và domain workers được tạo lại theo allowlist mới.

## Kiểm tra đã thực hiện

- `python3 -m py_compile *.py`
- Xác nhận chỉ còn 3 host HI88/QQ88/O8 trong `CHANNEL_CONFIG`.
- Kiểm tra spoiler UTF-16 với emoji phía trước mã.
- Kiểm tra spoiler fast path trả mã ngay.
- Kiểm tra KJC broadcast trả 0 item khi các domain KJC không nằm trong allowlist.
