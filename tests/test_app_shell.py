from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.state.golden_case import load_golden_case
from src.state.browser_history import (
    HISTORY_CATALOG_KEY,
    HISTORY_COMMAND_KEY,
    build_project_record,
)
from src.state.session import ACTIVE_PAGE_KEY, PROJECT_KEY


def test_streamlit_shell_starts_without_exception() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"

    app = AppTest.from_file(str(app_path)).run(timeout=10)

    assert not app.exception
    assert any("Industry Analyst OS" in item.value for item in app.markdown)
    assert any(
        "你的专属AI行业分析师：洞察未来趋势与竞争格局，发现市场机会，找到增长路径。"
        in item.value
        for item in app.markdown
    )
    assert any("需要填写" in item.value for item in app.markdown)
    assert any("仅供浏览" in item.value for item in app.markdown)
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


def test_project_home_continue_uses_queued_navigation_without_state_error() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path))
    app.session_state[PROJECT_KEY] = load_golden_case().model_dump(mode="json")
    app.session_state[ACTIVE_PAGE_KEY] = "home"
    app.run(timeout=10)

    next(
        button for button in app.button if button.label == "继续 Research Studio"
    ).click().run(timeout=10)

    assert not app.exception
    assert app.segmented_control[0].label == "工作模式"


def test_sidebar_exposes_row_level_finish_and_delete_controls() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    project = load_golden_case()
    record = build_project_record(project, "research_studio")
    app = AppTest.from_file(str(app_path))
    app.session_state[PROJECT_KEY] = project.model_dump(mode="json")
    app.session_state[ACTIVE_PAGE_KEY] = "research_studio"
    app.session_state[HISTORY_CATALOG_KEY] = {
        "projects": [record],
        "folders": [],
    }
    app.run(timeout=10)

    labels = {button.label for button in app.button}
    assert not app.exception
    assert "终止研究" in labels
    assert "删除项目" in labels
    assert "存档项目" not in labels
    assert "立即结束研究" not in labels
    assert not any(expander.label == "项目管理" for expander in app.expander)


def test_sidebar_finish_queues_termination_and_clears_active_project() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    project = load_golden_case()
    record = build_project_record(project, "research_studio")
    app = AppTest.from_file(str(app_path))
    app.session_state[PROJECT_KEY] = project.model_dump(mode="json")
    app.session_state[ACTIVE_PAGE_KEY] = "research_studio"
    app.session_state[HISTORY_CATALOG_KEY] = {
        "projects": [record],
        "folders": [],
    }
    app.run(timeout=10)

    next(button for button in app.button if button.label == "终止研究").click().run(
        timeout=10
    )

    assert not app.exception
    assert app.session_state[HISTORY_COMMAND_KEY]["type"] == "finish"
    assert app.session_state[HISTORY_COMMAND_KEY]["project_id"] == project.project_id
    assert PROJECT_KEY not in app.session_state


def test_sidebar_delete_requires_confirmation_and_queues_delete() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    project = load_golden_case()
    record = build_project_record(project, "research_studio")
    app = AppTest.from_file(str(app_path))
    app.session_state[PROJECT_KEY] = project.model_dump(mode="json")
    app.session_state[ACTIVE_PAGE_KEY] = "research_studio"
    app.session_state[HISTORY_CATALOG_KEY] = {
        "projects": [record],
        "folders": [],
    }
    app.run(timeout=10)

    delete_button = next(button for button in app.button if button.label == "删除项目")
    assert delete_button.disabled is True
    next(
        checkbox
        for checkbox in app.checkbox
        if checkbox.label == "确认删除此项目及其全部研究记录"
    ).check().run(timeout=10)
    next(button for button in app.button if button.label == "删除项目").click().run(
        timeout=10
    )

    assert not app.exception
    assert app.session_state[HISTORY_COMMAND_KEY]["type"] == "delete"
    assert app.session_state[HISTORY_COMMAND_KEY]["project_id"] == project.project_id
    assert PROJECT_KEY not in app.session_state
