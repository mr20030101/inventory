"""Drives the desktop client offscreen against the built-in server with demo data."""
import os
import sys
import warnings
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
warnings.filterwarnings("ignore", category=DeprecationWarning)

from PySide6.QtWidgets import QApplication, QComboBox, QLineEdit  # noqa: E402


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    os.environ["SAIMS_DATA_DIR"] = str(tmp_path_factory.mktemp("saims"))
    from saims.desktop.local_server import LocalServer
    srv = LocalServer(seed_demo=True)
    srv.start()
    yield srv
    srv.stop()


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def signed_in(server, username):
    from saims.desktop.api import Api
    api = Api(server.url)
    api.login(username, "demo1234")
    return api


def test_pages_follow_permissions(app, server):
    from saims.desktop.ui import theme
    from saims.desktop.ui.main_window import MainWindow
    theme.apply(app, "light")
    for username, expected in [("admin", 9), ("custodian", 7), ("teacher", 3), ("auditor", 8)]:
        w = MainWindow(signed_in(server, username))
        assert len(w.pages) == expected, username
        for i in range(len(w.pages)):
            w.go(i)
            app.processEvents()
        w.close()


def test_register_asset_through_form(app, server):
    from saims.desktop.ui.forms import FormDialog
    from saims.desktop.ui.pages.assets import AssetsPage
    api = signed_in(server, "custodian")
    page = AssetsPage(api)
    dialog = FormDialog(None, "Register", page._asset_fields(True), None, lambda v: api.post("/assets", v))
    dialog.widgets["name"].setText("Document camera")
    dialog.widgets["serial_number"].setText("DOC-CAM-001")
    dialog.widgets["acquisition_cost"].setText("249.99")
    rooms = dialog.widgets["room_id"]
    assert isinstance(rooms, QComboBox) and rooms.count() > 5
    rooms.setCurrentIndex(3)
    dialog._accept()
    assert dialog.result_value and dialog.result_value["asset_code"].startswith("HDS-")
    assert dialog.result_value["acquisition_cost"] == "249.99"
    # same serial again: the server refuses and the dialog shows the reason instead of closing
    again = FormDialog(None, "Register", page._asset_fields(True), None, lambda v: api.post("/assets", v))
    again.widgets["name"].setText("Duplicate")
    again.widgets["serial_number"].setText("DOC-CAM-001")
    again._accept()
    assert again.result_value is None and "already registered" in again.error.text()


def test_issue_beyond_stock_is_refused(app, server):
    from saims.desktop.api import ApiError
    api = signed_in(server, "custodian")
    item = next(i for i in api.get("/stock/items") if i["stock_state"] == "out")
    store = api.lookup("storage-locations")[0]
    with pytest.raises(ApiError) as exc:
        api.post("/stock/movements", {"movement_type": "ISSUE", "item_id": item["id"], "location_id": store["id"],
                                      "quantity": "1", "department_id": api.lookup("departments")[0]["id"]})
    assert exc.value.code == "insufficient_stock"


def test_teacher_cannot_register_assets(app, server):
    from saims.desktop.api import ApiError
    api = signed_in(server, "teacher")
    assert not api.can("assets.create")
    with pytest.raises(ApiError) as exc:
        api.post("/assets", {"name": "Sneaky"})
    assert exc.value.status == 403


def test_demo_data_is_consistent(server):
    api = signed_in(server, "admin")
    assert api.get("/stock/reconcile")["consistent"]
    assert len(api.get("/assets")) > 50
    assert api.get("/info")["demo"] is True
