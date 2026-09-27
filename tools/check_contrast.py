"""给当前主题做对比度体检（WCAG 2.1 SC 1.4.3）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mchanhua.config import load_config  # noqa: E402
from mchanhua.ui.contrast import contrast_ratio, audit  # noqa: E402


def main() -> int:
    config = load_config()
    ui = config.ui
    print(f"主题：{config.loaded_from}")
    print(f"背景 {ui.background} / 面板 {ui.panel} / 正文 {ui.text} / 次级 {ui.text_dim} / 强调 {ui.accent}")
    print()
    rows = (
        ("正文 on 面板", ui.text, ui.panel),
        ("正文 on 背景", ui.text, ui.background),
        ("次级 on 面板", ui.text_dim, ui.panel),
        ("次级 on 背景", ui.text_dim, ui.background),
        ("白字 on 强调色", "#ffffff", ui.accent),
    )
    print("%-16s %8s  %s" % ("组合", "对比度", "结论"))
    for name, foreground, background in rows:
        ratio = contrast_ratio(foreground, background)
        verdict = "通过" if ratio >= 4.5 else ("大字通过" if ratio >= 3 else "不通过")
        print("%-16s %8.2f  %s" % (name, ratio, verdict))
    problems = audit(__import__("mchanhua.ui.theme", fromlist=["Theme"]).Theme.from_config(ui))
    print()
    print("需要提醒：" + ("；".join(problems) if problems else "无，全部达标"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
