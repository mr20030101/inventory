"""Builds the main window offscreen and visits every page."""
import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from inventory_app.sample_data import load_sample_data  # noqa: E402
from inventory_app.ui import theme  # noqa: E402
from inventory_app.ui.main_window import PAGES, MainWindow  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("theme_name", ["light", "dark"])
def test_every_page_renders(app, repo, tmp_path, theme_name):
    load_sample_data(repo)
    theme.apply(app, theme_name)
    window = MainWindow(repo, tmp_path / "test.db")
    window.show()
    for i in range(len(PAGES)):
        window._go(i)
        app.processEvents()
        assert not window.grab().isNull()
    window._global_search("mouse")
    assert window.products.table.source.rowCount() == 1
    window._toggle_theme()
    window.close()
