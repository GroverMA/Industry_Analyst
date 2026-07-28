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
    assert not app.segmented_control
    assert any("高级分析师工作台（企业战略项目）" in item.value for item in app.markdown)
    assert any(button.label == "接入或审核企业一手数据" for button in app.button)
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
    assert not app.segmented_control
    assert any("高级分析师工作台（企业战略项目）" in item.value for item in app.markdown)


def test_strategy_workspace_opens_enterprise_upload_without_widget_state_error() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)
    next(button for button in app.button if button.label == "加载案例展示").click().run(
        timeout=10
    )

    next(
        button for button in app.button if button.label == "接入或审核企业一手数据"
    ).click().run(timeout=10)

    assert not app.exception
    assert any(item.value == "B. 分层上传脱敏企业文件" for item in app.subheader)
    assert app.file_uploader[0].label == "选择一个或多个文件"


def test_home_only_shows_strategy_intent_when_strategy_support_is_enabled() -> None:
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)

    labels = {item.label for item in app.text_area}
    assert "需要支持的业务决策（可选）" not in labels
    assert "企业战略意图（必填）" not in labels

    next(toggle for toggle in app.toggle if toggle.label == "进入企业战略决策支持模式").set_value(
        True
    ).run(timeout=10)

    labels = {item.label for item in app.text_area}
    assert "企业战略意图（必填）" in labels
    assert "需要支持的业务决策（可选）" not in labels


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
