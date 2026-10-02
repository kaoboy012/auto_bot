
## Phân tích log ngày 02/10/2026

Log cho thấy Telegram ingress hoạt động nhanh: `Telegram accepted` chỉ mất khoảng 1.5–2.4 ms. OCR video XX88 cũng không phải điểm nghẽn chính: file 25.7 MB tải khoảng 0.68 giây, OCR khoảng 0.67 giây, tổng khoảng 1.74 giây và đã trích được 5 mã.

Nút thắt là browser submit. Các mã HI88/QQ88 liên tục gặp `Turnstile verification pending`, có lượt giữ worker từ 3 đến 18 giây rồi retry lại cùng mã. Với MM88, tài khoản `kaoboy012` và `dad131` đều trả thông báo đã đạt giới hạn; cơ chế cũ vẫn đưa item quay lại queue. Vì domain worker xử lý tuần tự theo queue, mã mới bị xếp sau item cũ hoặc item captcha, đến lúc nhập thì đã hết hạn.

Bản sửa mới kết thúc item ngay khi Turnstile đang chờ xác minh thủ công, kết thúc item khi toàn bộ tài khoản đã đạt giới hạn, và chỉ retry khoảng 1 giây khi tài khoản đang tạm bận bởi worker khác. Đồng thời `MAX_CONCURRENT_SUBMITS_PER_DOMAIN` được đặt thành 2, khớp hai tab MM88.
