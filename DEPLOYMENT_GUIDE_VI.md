# Hướng dẫn cấu hình và triển khai candidate an toàn (Windows)

Candidate là **source code**, không chứa `.env`, session Telegram, SQLite database, log hay Edge profile. Không giải nén rồi xóa/thay toàn bộ thư mục production. Candidate này đã vượt 18 test source-level trên sandbox; vẫn cần kiểm tra trên máy Windows của bạn trước cutover.

## 1. Nguyên tắc an toàn trước khi bắt đầu

- Thực hiện trong maintenance window, với quyền quản trị máy phù hợp. Chỉ chạy **một bot** tại một thời điểm. Không để hai tiến trình dùng chung Telegram session, SQLite DB, Edge profile hoặc cổng CDP `9222`.
- Không gửi `.env`, `API_HASH`, token, mã đăng nhập/2FA, `*.session`, database hay Edge profile qua chat/email. Không đưa `.env` vào Git hoặc archive phát hành.
- Giữ Edge CDP chỉ trên loopback: `127.0.0.1`. Cổng CDP cho phép điều khiển trình duyệt; không bind ra LAN/Internet, không port-forward và không mở inbound firewall cho cổng `9222`.
- Không đổi các ngưỡng concurrency/rate limit trong cùng lần cập nhật. Giữ nguyên cấu hình production hiện tại, nhất là chat filters, per-domain limits và chế độ phục hồi inbox.
- Bot có thể tự submit code. Không dùng nguồn Telegram production hoặc giftcode thật để “test” lần đầu; hãy dùng môi trường/channel/site thử nghiệm được phép, hoặc chỉ kiểm tra compile/test trước khi cutover.

## 2. Chuẩn bị archive và staging

1. Tải `telegram_giftcode_bot_optimized_candidate.zip` về máy chạy bot. Có thể xác minh SHA-256 bằng PowerShell:

   ```powershell
   Get-FileHash .\telegram_giftcode_bot_optimized_candidate.zip -Algorithm SHA256
   ```

   So với checksum đã gửi cùng file. Nếu không khớp, dừng và tải lại.

2. Giải nén vào thư mục staging riêng, ví dụ:

   ```powershell
   Expand-Archive .\telegram_giftcode_bot_optimized_candidate.zip D:\AutoBot_stage
   $src = 'D:\AutoBot_stage\optimized_candidate'
   ```

3. README yêu cầu Python 3.11+. Kiểm tra bản Python sẽ dùng:

   ```powershell
   py -3.11 --version
   ```

4. Cài và chạy kiểm tra trong staging — **không chạy `run.bat` tại đây**:

   ```powershell
   Set-Location $src
   py -3.11 -m venv .venv312
   .\.venv312\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
   .\.venv312\Scripts\python.exe -m pip install -r requirements.txt
   .\.venv312\Scripts\python.exe -m pip install pytest
   .\.venv312\Scripts\python.exe -m pytest -q
   .\.venv312\Scripts\python.exe -m compileall -q .
   ```

   `pytest` chỉ cần cho bước kiểm tra; nó không được pin trong `requirements.txt`. Kỳ vọng test pass trước khi tiếp tục. Không chạy `main_script.py` trong staging với production `.env`, session, database hay profile.

## 3. Kiểm tra cấu hình production hiện có

Ưu tiên **giữ nguyên `.env` đang chạy ổn định**; không thay bằng `.env.example` rỗng. Nếu thật sự cần dựng `.env` mới, sao chép `.env.example` rồi chỉ điền các giá trị được quản lý cục bộ:

- `API_ID` và `API_HASH`: thông tin Telethon của tài khoản/bot được ủy quyền. `SESSION_NAME` phải khớp tên session hiện tại; file session là thông tin xác thực nhạy cảm.
- `ALERT_BOT_TOKEN`, `ALERT_CHAT_ID`, `SUBMIT_SUCCESS_NOTIFY` và `SUBMIT_SUCCESS_CHAT_ID`: xác nhận đúng nơi nhận cảnh báo/thông báo. Candidate mặc định bật submit-success notification; nếu không muốn gửi thông báo, đặt lựa chọn này có chủ đích và kiểm tra lại trước khi chạy.
- Chat/channel IDs: đối chiếu `CHANNEL_CONFIG` trong `config.py` với đúng nguồn được phép. Candidate mặc định bật `TELEGRAM_FILTER_AT_SOURCE`; giữ nguyên danh sách filter đang hoạt động. Các biến `QQ88_CHAT_IDS`/`HI88_CHAT_IDS` để trống sẽ dùng cấu hình suy ra từ source.
- `DATABASE_PATH` và `TELEGRAM_INBOX_DB_PATH`: giữ nguyên đường dẫn DB hiện tại. Mặc định là `data/code_history.db` và `data/telegram_inbox.db` tính từ thư mục project.
- `TELEGRAM_INBOX_RECOVERY_MODE`, `TELEGRAM_CATCH_UP` và các biến retry: giữ nguyên chính sách hiện dùng; thay đổi có thể làm các inbox cũ được replay hoặc bị bỏ qua.
- Edge/CDP: `EDGE_CDP_HOST=127.0.0.1`; `EDGE_CDP_PORT` phải khớp `CDP_PORT=9222` trong `run.bat`. `EDGE_PROFILE_DIR`, `EDGE_PROFILE_NAME` và `EDGE_EXECUTABLE_PATH` phải đúng máy. `run.bat` hiện mặc định dùng `D:\AutoBot\edge_bot_profile` và Edge ở một trong hai đường dẫn cài đặt Windows tiêu chuẩn.
- Nếu `.env` hiện có per-domain rate-limit như `QQ88_REQUESTS_PER_MINUTE`, `QQ88_MAX_BURST`, `HI88_*`, `MM88_*`, `RR88_*`, `XX88_*`, `GG88_*` hoặc `O8_*`, giữ nguyên. Nếu thiếu, code dùng giá trị global làm fallback. Không tăng rate/concurrency chỉ vì candidate đã pass test.

Không dán các giá trị bí mật vào tài liệu triển khai hoặc gửi cho người khác; chỉnh file trực tiếp trên máy chạy bot và giới hạn quyền đọc Windows cho tài khoản vận hành.

## 4. Dừng bot và sao lưu nhất quán

1. Tại cửa sổ bot production hiện tại, nhấn **Ctrl+C một lần** và đợi log `Shutting down...` rồi `Done`/`Stopped`. Không dùng `taskkill /F` trừ khi đã xác nhận graceful stop bị treo và chấp nhận rủi ro xử lý dở.
2. Xác nhận bot đã dừng. Đóng đúng cửa sổ Edge do bot dùng. Không đóng Edge/profile nếu còn tác vụ khác đang dùng nó.
3. Khi bot và Edge đã dừng, sao lưu **toàn bộ thư mục project** ra volume/thư mục riêng có quyền truy cập hạn chế. Ví dụ:

   ```powershell
   $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
   $backup = "D:\AutoBot_backups\$stamp"
   New-Item -ItemType Directory -Force $backup | Out-Null
   robocopy D:\AutoBot "$backup\AutoBot" /E /COPY:DAT /R:1 /W:1
   ```

   Mã thoát `robocopy` từ 0 đến 7 thường là thành công/có khác biệt đã sao chép; kiểm tra summary cuối lệnh. Bản sao này chứa secrets/session/profile, vì vậy không đặt ở thư mục chia sẻ công khai. Đảm bảo backup có `.env`, session theo `SESSION_NAME` (`*.session*`), các DB ở đúng đường dẫn trong `.env` cùng sidecar `-wal`/`-shm` nếu còn, `logs`, và `edge_bot_profile`. Nếu DB/profile nằm ngoài `D:\AutoBot`, sao lưu riêng các đường dẫn đó.

## 5. Cutover source mà không xóa runtime data

Candidate archive giải nén thành `$src`; `run.bat` mặc định trỏ tới `D:\AutoBot`. Sau khi staging test pass và bot đã dừng:

1. Nếu thư mục production không phải `D:\AutoBot`, sửa `BOT_DIR`, `EDGE_PROFILE_DIR`, `EDGE_PROFILE_NAME`, `EDGE_EXE` và cổng trong `run.bat` cho đúng môi trường. Đảm bảo `.env` có cùng Edge host/port/profile path. Không đổi CDP bind khỏi `127.0.0.1`.
2. Nếu production dùng `.venv312`, đổi tên venv cũ để giữ đường lui trước khi cài venv mới:

   ```powershell
   if (Test-Path D:\AutoBot\.venv312) {
       Rename-Item D:\AutoBot\.venv312 ".venv312_pre_candidate_$stamp"
   }
   ```

   Nếu hiện chỉ có `venv`, giữ nguyên; `run.bat` sẽ ưu tiên `.venv312` mới khi có.
3. Copy code từ staging vào thư mục production **không dùng `/MIR`**. `/E` không xóa các file đích cũ; exclude venv/cache/log sinh trong staging:

   ```powershell
   robocopy $src D:\AutoBot /E /COPY:DAT /R:1 /W:1 `
     /XD "$src\.venv312" "$src\venv" "$src\__pycache__" `
         "$src\tests\__pycache__" "$src\.pytest_cache" "$src\logs"
   ```

   Candidate không mang theo `.env`, DB, session hay Edge profile; không xóa các file đó ở production. **Không dùng `Remove-Item`, `/PURGE` hay `/MIR`** cho thư mục đang chứa runtime state.
4. Trong `D:\AutoBot`, chạy `setup.bat` để tạo `.venv312` mới và cài requirements. Kiểm tra không có lỗi pip. Nếu setup fail, chưa chạy bot; sửa môi trường hoặc rollback venv/source.
5. Mở `.env` tại `D:\AutoBot` và xác nhận nó vẫn là file production đúng, không phải template rỗng. Không thay đổi các ngưỡng hoặc IDs nếu không có lý do đã kiểm tra.

## 6. Khởi động và kiểm tra sau cutover

1. Trước khi chạy, xác nhận không còn bot cũ, Edge cũ dùng profile này, hay listener cũ trên 9222. Không cho hai bản chạy đồng thời.
2. Chạy `D:\AutoBot\run.bat`. Script sẽ kiểm tra Edge CDP trên `127.0.0.1:9222`, tự mở Edge bằng profile cấu hình nếu chưa có, rồi chạy `main_script.py`. Lần đăng nhập Telethon đầu tiên có thể yêu cầu mã đăng nhập/2FA tại console — nhập trực tiếp trên máy, không chia sẻ mã.
3. Quan sát startup log: kết nối Telegram thành công, Edge/CDP kết nối được, database/inbox mở được, channel filters đúng, không có vòng restart/retry bất thường. Kiểm tra `logs\bot_activity.log` và các file log cấu hình trong `.env`.
4. Kiểm tra CDP chỉ lắng nghe loopback, ví dụ:

   ```powershell
   Get-NetTCPConnection -LocalPort 9222 -State Listen |
     Select-Object LocalAddress, LocalPort, OwningProcess
   ```

   `LocalAddress` phải là `127.0.0.1` (hoặc loopback tương đương), không phải `0.0.0.0` hay địa chỉ mạng ngoài.
5. Giai đoạn đầu theo dõi liên tục: `ingress_to_durable_ms`, queue depth, lỗi SQLite/locked, retry/inbox age, tab-acquire wait theo domain, `PENDING_VERIFICATION`, `SITE_UI_CHANGED`, `INFRA_FAILURE`, kết quả submit và CPU/RAM của Edge. Theo dõi ít nhất 30–60 phút tải đại diện trước khi điều chỉnh tuning. Nếu có hành vi submit ngoài dự kiến, dừng bot ngay bằng Ctrl+C.

## 7. Rollback

1. Nhấn Ctrl+C, đợi graceful shutdown, sau đó đóng đúng Edge process/profile của bot. Giữ nguyên DB/session/profile hiện tại để tránh mất message đã nhận sau cutover.
2. Khôi phục **source code cũ** từ `$backup\AutoBot` vào `D:\AutoBot`; không restore đè `.env`, `data`/DB, `logs`, `*.session*` hay Edge profile theo cách mù quáng. Đặc biệt không dùng `/MIR`. Nếu dùng bản backup đầy đủ để khôi phục code, loại trừ các thư mục runtime và xác nhận những file cấu hình/DB nào nằm ngoài các thư mục mặc định.
3. Đưa venv cũ về tên `D:\AutoBot\.venv312` (sau khi đổi tên hoặc di chuyển venv candidate ra chỗ khác). Nếu venv cũ không còn, chạy `setup.bat` với source cũ để dựng lại.
4. Chạy source cũ, xác nhận Telegram/Edge/DB hoạt động và rà lại các message phát sinh trong thời gian candidate chạy. Candidate không thay schema theo chủ ý của merge này, nhưng vẫn giữ lại backup DB; chỉ khôi phục DB cũ nếu đã đánh giá tác động mất các message mới và có kế hoạch replay/đối soát.

## 8. Những gì không nên làm

Không mở cổng CDP ra mạng; không khởi động hai bot song song; không thay `.env` bằng file template rỗng; không xóa inbox/database để “làm sạch”; không dùng giftcode thật để thử; không tăng concurrency/rate limit trước khi có số đo production; không xóa session hoặc Edge profile khi chưa sao lưu và biết rõ hậu quả.
