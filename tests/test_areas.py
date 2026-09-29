"""多区域框选：保存 / 启停 / 改名 / 合并筛选 / 显示标注。"""

from pathlib import Path

import pytest
from PIL import Image

from mchanhua.app import Application
from mchanhua.autoregion import filter_area_lines
from mchanhua.config import Config, load_config, save_config
from mchanhua.geometry import Region
from mchanhua.ocr.base import OcrLine, OcrResult
from mchanhua.pipeline import PipelineResult
from mchanhua.ui.window import ResultWindow
from tests.fakes import DecodingTranslator, FakeGrabber, FakeWindow, wait_for

MONITOR = Region(0, 0, 2560, 1440)


def _result(lines: list[OcrLine]) -> OcrResult:
    return OcrResult(lines=lines, elapsed_ms=3.0, backend="fake")


# ---- 配置里的区域管理 ----


def test_add_area_names_them_in_order():
    config = Config()
    assert config.regions.add_area(Region(10, 20, 100, 50)) == "区域1"
    assert config.regions.add_area(Region(30, 40, 200, 60)) == "区域2"

    assert config.regions.areas == ["区域1", "区域2"]
    assert config.regions.fixed_region("区域2").to_csv() == "30,40,200,60"


def test_next_area_name_skips_taken_names():
    config = Config()
    config.regions.add_area(Region(1, 1, 10, 10), name="区域1")
    config.regions.add_area(Region(2, 2, 10, 10), name="区域3")

    assert config.regions.next_area_name() == "区域2"


def test_enable_and_disable_areas():
    config = Config()
    config.regions.add_area(Region(1, 1, 10, 10), name="区域1")
    config.regions.add_area(Region(2, 2, 10, 10), name="区域2")

    config.regions.set_area_enabled("区域1", False)

    assert config.regions.areas == ["区域2"]
    assert [name for name, _ in config.regions.enabled_areas()] == ["区域2"]
    assert config.regions.fixed_region("区域1") is not None      # 只是停用，没删

    config.regions.set_area_enabled("区域1", True)
    assert config.regions.areas == ["区域2", "区域1"]            # 重新启用放到末尾


def test_remove_and_rename_area():
    config = Config()
    config.regions.add_area(Region(1, 1, 10, 10), name="区域1")
    config.regions.add_area(Region(2, 2, 10, 10), name="区域2")

    config.regions.rename_area("区域1", "物品提示")
    assert config.regions.areas == ["物品提示", "区域2"]
    assert config.regions.fixed_region("物品提示").to_csv() == "1,1,10,10"

    with pytest.raises(ValueError):
        config.regions.rename_area("区域2", "物品提示")          # 重名要报错

    config.regions.remove_area("区域2")
    assert config.regions.areas == ["物品提示"]
    assert config.regions.fixed_region("区域2") is None


def test_areas_round_trip_including_chinese_keys(workdir: Path):
    config = Config()
    config.regions.add_area(Region(100, 200, 300, 90), name="物品提示")
    config.regions.add_area(Region(400, 900, 800, 120), name="区域2")
    config.regions.set_area_enabled("区域2", False)

    path = save_config(config, workdir / "config.toml")
    text = path.read_text(encoding="utf-8")
    loaded = load_config(path)

    assert '"物品提示" = "100,200,300,90"' in text       # 中文键必须带引号，否则 TOML 解析不了
    assert loaded.regions.areas == ["物品提示"]
    assert loaded.regions.fixed_region("区域2").to_csv() == "400,900,800,120"


# ---- 多区域筛行与合并 ----


def test_filter_area_lines_groups_and_dedupes():
    ocr = _result([
        OcrLine("Steel Ingot", Region(120, 130, 200, 24)),        # 区域1
        OcrLine("Redstone Dust", Region(120, 170, 220, 24)),      # 区域1
        OcrLine("You shouldn't be here.", Region(600, 900, 400, 26)),  # 区域2
        OcrLine("共享的一行", Region(300, 250, 120, 24)),          # 两个区域都会命中
    ])
    # 区域2 和区域1 有重叠，"共享的一行"两边都命中 → 只算给先出现的区域1
    areas = [("区域1", Region(100, 100, 400, 200)), ("区域2", Region(250, 100, 800, 900))]

    lines, labels = filter_area_lines(ocr, MONITOR, areas)

    assert [line.text for line in lines] == [
        "Steel Ingot", "Redstone Dust", "共享的一行", "You shouldn't be here.",
    ]
    assert labels == ["区域1", "区域1", "区域1", "区域2"]


def test_filter_area_lines_keeps_area_order():
    ocr = _result([
        OcrLine("上面的字", Region(100, 100, 120, 24)),
        OcrLine("下面的字", Region(100, 900, 120, 24)),
    ])
    areas = [("下面那块", Region(50, 850, 400, 200)), ("上面那块", Region(50, 50, 400, 200))]

    _lines, labels = filter_area_lines(ocr, MONITOR, areas)

    assert labels == ["下面那块", "上面那块"]                  # 跟用户的区域顺序一致


# ---- 控制器：多区域一次翻 ----


class _OcrWithTwoAreas:
    name = "fake-ocr"

    def recognize(self, image):
        return _result([
            OcrLine("Steel Ingot", Region(120, 130, 200, 24)),
            OcrLine("You shouldn't be here.", Region(600, 900, 400, 26)),
        ])


def _app(workdir: Path, ocr=None) -> Application:
    config_path = save_config(Config(), workdir / "config.toml")
    config = load_config(config_path)
    return Application(
        config,
        config_path=config_path,
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=ocr or _OcrWithTwoAreas(),
        window=FakeWindow(),
    )


def test_multiple_areas_translate_in_one_go(workdir: Path):
    app = _app(workdir)
    app.translator = DecodingTranslator()
    app.config.regions.add_area(Region(100, 100, 400, 200), name="区域1")
    app.config.regions.add_area(Region(500, 800, 700, 300), name="区域2")

    app.perform_translate()                   # 等价于按 Ctrl+Alt
    messages = wait_for(app, "result")
    result = next(message[1] for message in messages if message[0] == "result")

    assert app.grabber.requests[-1].to_csv() == "0,0,2560,1440"   # 整屏只抓一次
    assert result.source_lines == ["Steel Ingot", "You shouldn't be here."]
    assert result.line_areas == ["区域1", "区域2"]
    assert result.translated_count == 2


def test_disabled_area_is_not_translated(workdir: Path):
    app = _app(workdir)
    app.translator = DecodingTranslator()
    app.config.regions.add_area(Region(100, 100, 400, 200), name="区域1")
    app.config.regions.add_area(Region(500, 800, 700, 300), name="区域2")
    app.config.regions.set_area_enabled("区域2", False)

    app.perform_translate()
    messages = wait_for(app, "result")
    result = next(message[1] for message in messages if message[0] == "result")

    assert result.source_lines == ["Steel Ingot"]
    assert result.line_areas == ["区域1"]


# ---- 小窗显示：标注区域 1、区域 2 ----


def test_labels_helper_inserts_area_titles():
    lines = ["钢锭", "红石粉", "你不该来这里。"]
    labels = ["区域1", "区域1", "区域2"]

    assert ResultWindow._with_area_labels(lines, labels) == [
        "［区域1］", "钢锭", "红石粉", "［区域2］", "你不该来这里。",
    ]


def test_labels_helper_keeps_single_area_output_clean():
    assert ResultWindow._with_area_labels(["钢锭"], []) == ["钢锭"]
    assert ResultWindow._with_area_labels(["钢锭"], [""]) == ["钢锭"]


def test_window_shows_area_titles():
    import pytest as _pytest

    tk = _pytest.importorskip("tkinter")
    try:
        window = ResultWindow(Config())
    except tk.TclError as exc:  # pragma: no cover
        _pytest.skip(f"没有可用的图形环境：{exc}")
    try:
        window.show_result(
            PipelineResult(
                source_lines=["Steel Ingot", "Redstone Dust"],
                output_lines=["钢锭", "红石粉"],
                line_areas=["区域1", "区域2"],
            )
        )
        window.root.update_idletasks()

        translated = window.target.get("1.0", "end").strip()
        source = window.source.get("1.0", "end").strip()
        assert "［区域1］" in translated and "［区域2］" in translated
        assert "［区域1］" in source and "［区域2］" in source
        assert "2 个区域" in window.status_text()
    finally:
        window.root.destroy()


# ---- 框选时的撤销（Delete）与真实区域名 ----


def test_pick_areas_can_delete_just_created_area(workdir: Path, monkeypatch):
    """Alt+V 框选时：Enter 存一个、Delete 撤掉刚框的那个，遮罩上显示的是真实名字。"""

    app = _app(workdir)
    seen_names: list[list[str]] = []

    def fake_pick(_monitor, _parent, existing=None, on_accept=None, on_remove=None):
        on_accept(Region(10, 20, 100, 50))
        on_accept(Region(200, 300, 120, 60))
        seen_names.append([name for name, _ in existing])

        on_remove()                                    # Delete：撤掉第二个
        seen_names.append([name for name, _ in existing])
        return None

    monkeypatch.setattr("mchanhua.app.pick_region", fake_pick)
    app.perform_select_region()

    assert seen_names == [["区域1", "区域2"], ["区域1"]]      # 名字是真名，不是"第 2 个"
    assert app.config.regions.area_names() == ["区域1"]
    assert load_config(Path(app.config_path)).regions.area_names() == ["区域1"]   # 删除也落盘


def test_delete_without_new_area_does_nothing(workdir: Path, monkeypatch):
    app = _app(workdir)
    app.config.regions.add_area(Region(1, 1, 10, 10), name="旧区域")

    def fake_pick(_monitor, _parent, existing=None, on_accept=None, on_remove=None):
        on_remove()                                    # 还没框就按 Delete：删掉最后一个（旧区域）
        return None

    monkeypatch.setattr("mchanhua.app.pick_region", fake_pick)
    app.perform_select_region()

    assert app.config.regions.area_names() == []               # 允许删掉以前存的区域
    assert load_config(Path(app.config_path)).regions.area_names() == []


def test_delete_removes_previous_session_area_too(workdir: Path, monkeypatch):
    """Delete 不再只管"刚框的"：以前存的区域也能删（用户就是这么被卡住的）。"""

    app = _app(workdir)
    app.config.regions.add_area(Region(1, 1, 10, 10), name="区域1")      # 上次会话存的
    save_config(app.config, Path(app.config_path))
    seen: list[list[str]] = []

    def fake_pick(_monitor, _parent, existing=None, on_accept=None, on_remove=None):
        seen.append([name for name, _ in existing])       # 遮罩上能看到旧区域
        on_remove()                                       # 直接按 Delete
        seen.append([name for name, _ in existing])
        assert existing == []                             # 遮罩上的黄线也同步没了
        return None

    monkeypatch.setattr("mchanhua.app.pick_region", fake_pick)
    app.perform_select_region()

    assert seen == [["区域1"], []]
    assert app.config.regions.area_names() == []
    assert load_config(Path(app.config_path)).regions.area_names() == []


# ---- 用完即清：退出清空 + 被强杀后下次启动补清 ----


def test_areas_are_cleared_when_program_exits(workdir: Path):
    app = _app(workdir)
    app.config.regions.add_area(Region(10, 20, 100, 50), name="区域1")
    app.config.regions.add_area(Region(30, 40, 120, 60), name="区域2")
    save_config(app.config, Path(app.config_path))

    removed = app.clear_areas_on_exit()

    assert removed == 2
    assert app.config.regions.area_names() == []
    # 配置文件的 [regions.fixed] 也要真的空掉
    text = Path(app.config_path).read_text(encoding="utf-8")
    assert '"区域1"' not in text
    assert 'areas = []' in text


def test_leftover_areas_are_cleared_on_next_start(workdir: Path):
    """上次被强杀（没走到退出逻辑）时，启动时补一次清空。"""

    config_path = save_config(Config(), workdir / "config.toml")
    config = load_config(config_path)
    config.regions.add_area(Region(1, 2, 30, 40), name="残留区域")
    save_config(config, config_path)

    reloaded = load_config(config_path)
    assert reloaded.regions.area_names() == ["残留区域"]      # 文件里确实还留着

    app = Application(
        reloaded,
        config_path=config_path,
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=_OcrWithTwoAreas(),
        window=FakeWindow(),
    )

    assert app.config.regions.area_names() == []              # 启动就补清了
    assert load_config(config_path).regions.area_names() == []


def test_clear_on_exit_can_be_turned_off(workdir: Path):
    """想留着区域继续用，就把 clear_on_exit 关掉。"""

    config_path = save_config(Config(), workdir / "config.toml")
    config = load_config(config_path)
    config.regions.clear_on_exit = False
    config.regions.add_area(Region(1, 2, 30, 40), name="要留下的区域")

    app = Application(
        config,
        config_path=config_path,
        use_hotkeys=False,
        grabber=FakeGrabber(),
        ocr=_OcrWithTwoAreas(),
        window=FakeWindow(),
    )

    assert app.config.regions.area_names() == ["要留下的区域"]
    assert app.clear_areas_on_exit() == 0
    assert app.config.regions.area_names() == ["要留下的区域"]


# ---- 设置里的"选区"页 ----


def test_settings_areas_page_lists_and_manages(workdir: Path, monkeypatch):
    import pytest as _pytest

    tk = _pytest.importorskip("tkinter")
    from mchanhua.ui.settings_window import SettingsWindow

    path = save_config(Config(), workdir / "config.toml")
    config = load_config(path)
    config.regions.add_area(Region(100, 200, 300, 90), name="物品提示")
    config.regions.add_area(Region(400, 900, 800, 120), name="区域2")
    config.regions.set_area_enabled("区域2", False)
    # "删除全部"会先确认，测试里直接同意
    monkeypatch.setattr(
        "mchanhua.ui.settings_window.messagebox.askyesno", lambda *a, **k: True
    )

    try:
        window = SettingsWindow(config)
    except tk.TclError as exc:  # pragma: no cover
        _pytest.skip(f"没有可用的图形环境：{exc}")
    try:
        assert "选区" in window._pages
        labels = [
            child.cget("text")
            for row in window._area_rows.winfo_children()
            for child in row.winfo_children()
            if hasattr(child, "cget")
        ]
        assert "物品提示" in labels and "区域2" in labels
        assert any("100,200,300,90" == text for text in labels)

        window._set_area_enabled("区域2", True)          # 勾上就启用
        assert config.regions.areas == ["物品提示", "区域2"]
        assert "区域2" in load_config(path).regions.areas   # 立刻落盘

        window._remove_area("物品提示")
        assert config.regions.area_names() == ["区域2"]
        assert load_config(path).regions.fixed_region("物品提示") is None

        window._clear_areas()                            # 清空（这里没有确认框拦截）
        assert config.regions.area_names() == []
    finally:
        window.root.destroy()
