"""框选遮罩：Esc / 右键取消、拖拽出选区。"""

import time

import pytest

tk = pytest.importorskip("tkinter")

from mchanhua.geometry import Region  # noqa: E402
from mchanhua.ui.region_picker import (  # noqa: E402
    DEFAULT_BOX,
    KEY_STEP,
    pick_region,
)

SCREEN = Region(0, 0, 2560, 1440)


def _root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:  # pragma: no cover - 无图形环境
        pytest.skip(f"没有可用的图形环境：{exc}")
    root.withdraw()
    return root


def _run_with(window_actions, timeout: float = 6.0):
    """弹出遮罩，用 after 模拟用户操作，返回 pick_region 的结果。"""

    def on_ready(overlay):
        overlay.update()                      # 先让遮罩真的显示出来，事件才送得进去
        overlay.after(int(timeout * 1000), overlay.destroy)   # 兜底：卡住也要退出
        for delay, action in window_actions:
            overlay.after(delay, lambda a=action: a(overlay))

    return pick_region(SCREEN, _root(), on_ready=on_ready)


def test_escape_cancels_picking():
    """按 Esc 退出选框（以前遮罩拿不到焦点，Esc 根本没反应）。"""

    result = _run_with([(60, lambda w: w.event_generate("<Escape>", when="now"))])

    assert result is None


def test_right_click_cancels_picking():
    result = _run_with([(60, lambda w: w.event_generate("<ButtonPress-3>", x=100, y=100, when="now"))])

    assert result is None


def test_dragging_returns_region():
    def drag(widget):
        canvas = widget.winfo_children()[0]
        canvas.event_generate("<ButtonPress-1>", x=100, y=120, when="now")
        canvas.event_generate("<B1-Motion>", x=500, y=420, when="now")
        canvas.event_generate("<ButtonRelease-1>", x=500, y=420, when="now")

    result = _run_with([(60, drag)])

    assert result is not None
    # 遮罩是全屏的，逻辑坐标会按屏幕缩放换成物理坐标；这里屏幕就是 2560x1440
    assert result.width >= 380 and result.height >= 280


def test_simple_click_cancels_picking():
    """点一下不拖：取消（老行为，别退化）。"""

    def click(widget):
        canvas = widget.winfo_children()[0]
        canvas.event_generate("<ButtonPress-1>", x=200, y=200, when="now")
        canvas.event_generate("<ButtonRelease-1>", x=200, y=200, when="now")

    assert _run_with([(60, click)]) is None


def test_overlay_takes_keyboard_focus_and_grab():
    """回归：遮罩必须抢焦点并 grab，否则 Esc 送不到它这里。"""

    captured: dict = {}

    def on_ready(overlay):
        captured["grab"] = overlay.grab_current() == overlay
        captured["focus"] = overlay.focus_get() is not None
        overlay.after(50, overlay.destroy)

    pick_region(SCREEN, _root(), on_ready=on_ready)
    time.sleep(0)          # 让 after 回调跑完（pick_region 内部已 wait_window）

    assert captured["grab"] is True


# ---- 游戏锁住鼠标时的键盘框选（《我的世界》准心场景）----


def test_arrow_keys_move_the_box_then_enter_accepts():
    """鼠标被游戏锁死时，用方向键挪框、Enter 确认也能框出选区。"""

    def press(widget, *keys):
        for key in keys:
            widget.event_generate(f"<{key}>", when="now")
        widget.event_generate("<Return>", when="now")

    base = _run_with([(60, lambda w: press(w, "Right"))])
    shifted = _run_with([(60, lambda w: press(w, "Right", "Right", "Right", "Down"))])

    assert base is not None and shifted is not None
    assert shifted.x > base.x                      # 往右挪了
    assert shifted.y > base.y                      # 也往下挪了
    assert shifted.width == base.width             # 尺寸不变（只是平移）
    assert shifted.height == base.height


def test_ctrl_arrow_resizes_the_box():
    def press(widget, ctrl_times: int):
        widget.event_generate("<Right>", when="now")            # 先让框出现
        for _ in range(ctrl_times):
            widget.event_generate("<Control-Right>", when="now")
        widget.event_generate("<Return>", when="now")

    base = _run_with([(60, lambda w: press(w, 0))])
    wider = _run_with([(60, lambda w: press(w, 5))])

    assert base is not None and wider is not None
    assert wider.width > base.width                # 右边界被拉宽
    assert wider.x == base.x                       # 左边界不动


def test_enter_without_any_box_does_nothing():
    """没按过方向键就按 Enter：不产生选区（也不能崩）。"""

    result = _run_with([
        (60, lambda w: w.event_generate("<Return>", when="now")),
        (600, lambda w: w.event_generate("<Escape>", when="now")),
    ])

    assert result is None
