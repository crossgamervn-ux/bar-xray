# Hiển thị và minimap PIP — engine 2026.07.04

AX đã nối với DLL v2 qua ax_control.py và shared memory (không còn gọi
fullview.exe đời đầu). Bấm AX trên AutoHeal để bật/tắt; chỉ hiển thị trạng thái
sau phản hồi backend. Sau cập nhật widget dùng /luaui reload; nếu AX đang bị
tắt trong cấu hình, bật lại trong danh sách widget F11.

Đã kiểm tra yêu cầu qua TCP loopback: OFF/ON đổi cả full_view và full_read,
giữ ctrl_team rồi khôi phục trạng thái ban đầu. Kết quả ax-v2-validation.json.
Lần kiểm tra AX này chưa có unit trong danh sách vẽ; chưa xác nhận trực quan.

Chỉ dùng với SHA256 được kiểm tra trong engine_support.py.

## Bản v2

`refresh_view_v2.py on` / `refresh_view_v2.py off` nạp
`native/view_refresh_v2.dll` khi cần, rồi gửi yêu cầu qua shared memory.
Callback `GetRenderFeaturesDrawFlagChanged` (RVA 0x14A0E0) chạy trên cùng
thread với bridge AutoDodge, ngoài synced context, thực hiện:

1. Cập nhật gu->spectatingFullView.
2. Gọi CLuaUI::UpdateTeams() (RVA 0x113570).
3. Gọi CUnitDrawerData::PlayerChanged() (RVA 0x3C2950) để cập nhật icon.

Không dùng fullview.py đời đầu cho PIP: công cụ đó chỉ đổi cờ.
Bridge AutoDodge phải chạy để DLL xác minh thread. Yêu cầu hết hạn sau 3 giây.
DLL v2 chỉ xử lý khi có yêu cầu; không tự bật lại khi vào trận khác.

## PIP

`data/LuaUI/Widgets/gui_pip.lua` là lớp nạp bản gốc từ archive game bằng
VFS.ZIP, rồi điều chỉnh đúng một nhánh lọc mặc định để tôn trọng fullview.
Không thay đổi chế độ xem LOS hoặc theo dõi người chơi được chọn riêng.
Nếu mẫu mã nguồn không khớp duy nhất, dùng nguyên bản và ghi thông báo.
Sau khi cài cần `/luaui reload`. Log thành công:
`[PIP local] Engine view compatibility loaded`.

## Bằng chứng đã đo

PID 6820, thread 22924: DLL v2 trả status 0; icon không hợp lệ 1 -> 0.
LuaUI full_read 0 -> 1; read_team/read_ally_team -> -2.
spectating vẫn 0, ctrl_team/select_team vẫn 0.
Log xác nhận PIP đã nạp lớp điều chỉnh. Người dùng xác nhận icon đã hiện trên minimap sau /luaui reload. Sau reload, full_read vẫn 1 và read_team/read_ally_team vẫn -2.

Chẩn đoán: `inspect_luaui.py`, `inspect_render.py`.
Kết quả: `refresh-v2-result.json`, `luaui-diagnostic.json`.

## Bổ sung 2026-10-05
AX có vòng phủ/đạn antinuke và bảng income nhỏ bên phải. Income đã chuyển sang DLL riêng; xem [INCOME_VI.md](INCOME_VI.md). Không suy ra thay đổi hiển thị local đồng nghĩa LOS simulation thay đổi, hoặc chứng minh khán giả/client khác thấy cùng giao diện.
