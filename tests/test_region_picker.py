"""框选遮罩：不抢焦点（游戏不弹菜单）、键盘框选、鼠标框选、确认/取消。"""

import pytest

tk = pytest.importorskip("tkinter")

from mchanhua.geometry import Region  # noqa: E402
from mchanhua.ui.region_picker import (  # noqa: E402
    DEFAULT_BOX,
    KEY_STEP,
    RegionPicker,
    pick_region,
)

SCREEN = Region(0, 0, 2560, 1440)


def _picker():
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - 无图形环境
        pytest.skip(f"没有可用的图形环境：{exc}")
    root.withdraw()
    picker = RegionPicker(SCREEN, root)
    picker.root.update_idletasks()
    return picker, root


def _finish(picker, root):
    """跑完一次框选：内部靠 after 轮询，这里手动把队列喂进去。"""
    try:
        picker._install_hook()          # 只装钩子逻辑，测试里不用真的按键
    except Exception:
        pass
    return picker


def test_overlay_does_not_take_focus():
    """关键回归：遮罩不能抢焦点，否则游戏会失焦弹菜单挡住字幕。"""

    picker = RegionPicker(SCREEN, None)
    try:
        assert picker.root.overrideredirect() is True      # 无边框、不激活
        assert picker.root.grab_current() is None          # 没有独占输入
        assert picker.root.attributes("-topmost") in (1, "1", True)
    finally:
        picker.close()


def test_box_starts_in_the_middle():
    picker, root = _picker()
    try:
        left, top, right, bottom = picker.box
        assert right - left == DEFAULT_BOX[0]
        assert bottom - top == DEFAULT_BOX[1]
        # 遮罩用的是 Tk 的逻辑屏幕尺寸（本机 125% 缩放 → 2048），居中即可
        assert abs((left + right) // 2 - picker.root.winfo_screenwidth() // 2) <= 2
        assert abs((top + bottom) // 2 - picker.root.winfo_screenheight() // 2) <= 2
    finally:
        picker.close()
        root.destroy()


def test_arrow_keys_move_the_box():
    picker, root = _picker()
    try:
        before = list(picker.box)
        picker.handle_key("right")
        picker.handle_key("down")
        left, top, right, bottom = picker.box
        assert left == before[0] + KEY_STEP
        assert top == before[1] + KEY_STEP
        assert right - left == before[2] - before[0]      # 只是平移
    finally:
        picker.close()
        root.destroy()


def test_shift_arrow_moves_finely():
    picker, root = _picker()
    try:
        before_left = picker.box[0]
        picker.handle_key("right", shift=True)
        assert picker.box[0] == before_left + 4
    finally:
        picker.close()
        root.destroy()


def test_ctrl_arrow_resizes_only_the_right_edge():
    picker, root = _picker()
    try:
        left, _, right, _ = picker.box
        picker.move_box("right", ctrl=True)
        picker.move_box("right", ctrl=True)
        assert picker.box[0] == left                       # 左边不动
        assert picker.box[2] == right + KEY_STEP * 2       # 右边拉宽
    finally:
        picker.close()
        root.destroy()


def test_enter_accepts_current_box():
    picker, root = _picker()
    try:
        picker.handle_key("enter")
        assert picker.result is not None
        assert picker._closed is True
        assert picker.result.width > 0 and picker.result.height > 0
    finally:
        picker.close()
        root.destroy()


def test_backspace_and_escape_cancel():
    """取消键：Backspace 最安全（Esc 在《我的世界》里会打开游戏菜单）。"""

    for key in ("backspace", "esc"):
        picker, root = _picker()
        try:
            picker.handle_key(key)
            assert picker.result is None
            assert picker._closed is True
        finally:
            picker.close()
            root.destroy()


# ---- 鼠标（默认能拖，按 M 可关掉）----


def test_mouse_drag_is_on_by_default_and_m_toggles_it():
    picker, root = _picker()
    try:
        assert picker.mouse_enabled is True       # 和以前一样：一按就能拖
        picker.handle_key("m")
        assert picker.mouse_enabled is False      # 游戏里可以关掉，免得点到游戏
        picker.handle_key("m")
        assert picker.mouse_enabled is True
    finally:
        picker.close()
        root.destroy()


def test_mouse_drag_picks_region():
    picker, root = _picker()
    try:
        picker.note_cursor(100, 120)              # 光标刚动过 → 允许拖动
        picker.apply_mouse(100, 120, True)
        picker.note_cursor(500, 420)
        picker.apply_mouse(500, 420, True)
        picker.apply_mouse(500, 420, False)

        assert picker.result is not None
        assert picker.result.width >= 380
        assert picker.result.height >= 280
    finally:
        picker.close()
        root.destroy()


def test_mouse_simple_click_does_not_pick():
    """点一下没拖：不算选区，遮罩继续留着。"""

    picker, root = _picker()
    try:
        picker.note_cursor(300, 300)
        picker.apply_mouse(300, 300, True)
        picker.apply_mouse(302, 301, False)

        assert picker.result is None
        assert picker._closed is False
    finally:
        picker.close()
        root.destroy()


def test_click_is_ignored_when_cursor_is_frozen():
    """鼠标被游戏锁住（光标长时间不动）时，别把点击当成拖框——否则会挖掉游戏里的方块。"""

    picker, root = _picker()
    try:
        picker._cursor_moved_at = 0               # 假装光标已经很久没动过
        picker.apply_mouse(400, 400, True)
        picker.apply_mouse(700, 700, True)
        picker.apply_mouse(700, 700, False)

        assert picker.mouse_blocked is True       # 判定为被锁
        assert picker.result is None
        assert picker._mouse_down is False        # 没有开始拖拽
        assert picker._closed is False            # 遮罩还在，等用户用键盘
    finally:
        picker.close()
        root.destroy()


def test_mouse_works_again_after_cursor_moves():
    picker, root = _picker()
    try:
        picker._cursor_moved_at = 0
        picker.apply_mouse(400, 400, True)
        assert picker.mouse_blocked is True

        picker.note_cursor(410, 410)              # 光标又动了
        assert picker.mouse_blocked is False
        picker.apply_mouse(410, 410, True)
        picker.note_cursor(600, 600)
        picker.apply_mouse(600, 600, True)
        picker.apply_mouse(600, 600, False)

        assert picker.result is not None
    finally:
        picker.close()
        root.destroy()


def test_pick_region_returns_none_when_cancelled():
    """走完整流程（on_ready 里直接确认/取消），拿到结果。"""

    def on_ready(picker):
        picker.root.after(50, lambda: picker.handle_key("backspace"))

    assert pick_region(SCREEN, _wrap_root(), on_ready=on_ready) is None


# ---- 连续框选（Alt+V 帧多个区域）----


def test_accept_mode_keeps_overlay_open_and_collects_regions():
    """连续模式：每按一次 Enter 交出一个区域，遮罩不关，可以接着框下一个。"""

    taken: list[Region] = []
    picker, root = _picker()
    try:
        picker.on_accept = taken.append
        screen = Region(0, 0, 2560, 1440)
        picker.physical_screen = screen

        picker.move_box("right")
        picker.handle_key("enter")             # 第一个
        assert picker._closed is False         # 遮罩还开着
        assert picker.accepted == 1

        picker.move_box("down")
        picker.handle_key("enter")             # 第二个
        assert picker.accepted == 2
        assert len(taken) == 2
        assert taken[0].x < taken[1].x or taken[0].y < taken[1].y

        picker.handle_key("backspace")         # 结束
        assert picker._closed is True
        assert picker.result is None
    finally:
        picker.close()
        root.destroy()


def test_existing_areas_are_drawn_on_the_overlay():
    """已保存的区域要画在遮罩上（黄色虚线 + 名字），方便避免重复框。"""

    picker, root = _picker()
    try:
        picker.existing = [("区域1", Region(100, 100, 400, 200))]
        picker._draw_existing()
        items = picker.canvas.find_withtag("existing")
        assert len(items) >= 2                 # 框 + 名字
    finally:
        picker.close()
        root.destroy()


def _wrap_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover
        pytest.skip(f"没有可用的图形环境：{exc}")
    root.withdraw()
    return root
