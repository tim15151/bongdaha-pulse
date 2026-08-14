# bongdaha-pulse

Synthetic browser pulse cho `https://bongdaha.com`.

## GitHub Secrets bắt buộc

- `PROXY_HOST`
- `PROXY_USER`
- `PROXY_PASS`

## Nhận diện synthetic

Traffic được đánh dấu:

- `utm_source=github`
- `utm_medium=synthetic`
- `utm_campaign=bongdaha_pulse`
- Header cùng domain: `X-BongDaHa-Pulse: github-synthetic`

## Cách chạy

Vào **Actions → BongDaHa Pulse → Run workflow**.

Manual test mặc định chỉ chạy 3 lượt. Scheduled run chạy 8 lần/ngày, mỗi lần 7–12 lượt, tương đương khoảng 56–96 lượt/ngày.

## Log cần nhìn

Ví dụ:

`HTTP=200 | GA_HIT=YES | GA_REQ=1 | blocked=35`

- `HTTP=200`: trang tải được.
- `GA_HIT=YES`: browser đã phát hiện request Google Analytics collect.
- `GA_HIT=NO`: trang vẫn có thể tải bình thường nhưng GA tag chưa fire, bị consent chặn, hoặc site chưa gắn GA.
