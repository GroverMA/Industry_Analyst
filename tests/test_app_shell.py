from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_shell_starts_without_exception() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"

    app = AppTest.from_file(str(app_path)).run(timeout=10)

    assert not app.exception
    assert any("Industry Analyst OS" in item.value for item in app.markdown)
    assert not any(item.value == "恢复已有研究项目" for item in app.subheader)


def test_case_opens_single_page_research_studio() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)

    next(button for button in app.button if button.label == "加载案例展示").click().run(
        timeout=10
    )

    assert not app.exception
    assert app.segmented_control[0].label == "工作模式"
    assert app.segmented_control[0].options == ["快速通用报告", "高级分析师工作台"]
    assert any(button.label == "AI分析研究需求并生成市场描述" for button in app.button)
    assert any(button.label == "新建研究" for button in app.button)
