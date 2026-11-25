"""Phase 2: index cache, search, dates, grouping, sprites and a Qt smoke test."""

import os
from datetime import UTC, datetime, timedelta

import pytest
from conftest import user

from claude_buddy.models import group_by_project
from claude_buddy.scanner import SessionIndex, newest_mtime
from claude_buddy.search import fold, matches
from claude_buddy.timefmt import relative
from claude_buddy.ui import sprites


def test_index_reparses_only_changed_files(write_session, tmp_path, monkeypatch):
    a = write_session([user("first", 1)], sid="a")
    write_session([user("second", 2)], sid="b")
    index = SessionIndex(tmp_path / "projects")
    calls: list[str] = []
    import claude_buddy.scanner as scanner
    real = scanner.parse_session
    monkeypatch.setattr(scanner, "parse_session", lambda p, warn=None: calls.append(p.stem) or real(p, warn))

    assert len(index.refresh().sessions) == 2 and sorted(calls) == ["a", "b"]
    calls.clear()
    index.refresh()
    assert calls == []                                   # nothing changed
    a.write_text(a.read_text(encoding="utf-8") + '{"type": "mode"}\n', encoding="utf-8")
    index.refresh()
    assert calls == ["a"]
    a.unlink()
    assert [s.session_id for s in index.refresh().sessions] == ["b"]


def test_newest_mtime(write_session, tmp_path):
    assert newest_mtime(tmp_path / "missing") is None
    write_session([user("x", 1)])
    assert newest_mtime(tmp_path / "projects") is not None


def test_search_ignores_case_and_accents():
    hay = fold("La aplicación 8D/NC — Brazo_robotico")
    assert matches("APLICACION", hay)
    assert matches("brazo 8d", hay)
    assert not matches("brazo kinect", hay)


def test_relative_dates():
    now = datetime(2026, 11, 24, 12, 0).astimezone()
    assert relative(now - timedelta(seconds=10), now) == "ahora"
    assert relative(now - timedelta(minutes=5), now) == "hace 5 min"
    assert relative(now - timedelta(hours=2), now).startswith("hoy ")
    assert relative(now - timedelta(days=1), now).startswith("ayer ")
    assert relative(now - timedelta(days=30), now) == "25 oct"
    assert relative(datetime(2025, 1, 3, tzinfo=UTC), now).endswith("2025")


def test_group_by_project_orders_by_newest(write_session, tmp_path):
    write_session([user("old", 1)], sid="old")
    write_session([{**user("new", 9), "cwd": "C:\\dev\\other"}], folder="c--dev-other", sid="new")
    write_session([user("mid", 5)], sid="mid")
    sessions = SessionIndex(tmp_path / "projects").refresh().sessions
    groups = group_by_project(sessions)
    assert [g.name for g in groups] == ["other", "demo"]
    assert [s.session_id for s in groups[1].sessions] == ["mid", "old"]


@pytest.mark.parametrize("state", list(sprites.STATES))
@pytest.mark.parametrize("accessory", list(sprites.ACCESSORIES))
def test_sprite_frames_are_valid(state, accessory):
    allowed = set(sprites.palette("terracotta")) | {"."}
    for i in range(sprites.STATES[state].frames):
        grid = sprites.frame(state, i, accessory)
        assert len(grid) == 16 and all(len(row) == 16 for row in grid)
        assert set("".join(grid)) <= allowed


def test_idle_is_lively():
    frames = [sprites.frame("idle", i) for i in range(sprites.STATES["idle"].frames)]
    assert len(set(frames)) >= 4                                     # look around, blink, hop
    assert any(f[2] != sprites.BODY[2] or f[14] != sprites.BODY[14] for f in frames)   # hop moves rows


def test_new_states_exist():
    for state in ("searching", "running", "waiting", "greeting", "dragged", "hover"):
        assert len({sprites.frame(state, i) for i in range(sprites.STATES[state].frames)}) >= 1


@pytest.fixture(scope="module")
def qapp(tmp_path_factory):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    # Keep test settings out of the real registry / config dir
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path_factory.mktemp("settings")))
    QApplication.setOrganizationName("ClaudeBuddyTests")
    QApplication.setApplicationName("ClaudeBuddyTests")
    return QApplication.instance() or QApplication([])


def test_panel_placement():
    from PySide6.QtCore import QRect, QSize

    from claude_buddy.ui.panel import Panel
    avail, size = QRect(0, 0, 1920, 1032), QSize(440, 640)
    tray = QRect(1598, 1032, 32, 48)                       # below the work area (taskbar)
    assert Panel.place(tray, size, avail).y() == avail.bottom() - 8 - 640     # above, clamped
    pet_top_left = QRect(20, 20, 96, 96)                    # no room above -> below
    assert Panel.place(pet_top_left, size, avail).y() == pet_top_left.bottom() + 8
    pet_mid_left = QRect(20, 500, 96, 96)                   # no room above/below/left -> right
    assert Panel.place(pet_mid_left, QSize(440, 1000), avail).x() == pet_mid_left.right() + 8


def test_desktop_buddy_click_and_drag(qapp):
    from PySide6.QtCore import QPoint, QSettings, Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QMenu

    from claude_buddy.ui.desktop_buddy import DesktopBuddy
    from claude_buddy.ui.mascot import Mascot

    pet = DesktopBuddy(Mascot(), QMenu(), size=96)
    pet.show()
    clicks: list[bool] = []
    pet.clicked.connect(lambda: clicks.append(True))

    QTest.mouseClick(pet, Qt.MouseButton.LeftButton, pos=QPoint(48, 48))
    assert clicks == [True]

    start = pet.pos()
    QTest.mousePress(pet, Qt.MouseButton.LeftButton, pos=QPoint(48, 48))
    QTest.mouseMove(pet, QPoint(48 - 60, 48 - 40))
    QTest.mouseRelease(pet, Qt.MouseButton.LeftButton, pos=QPoint(48 - 60, 48 - 40))
    assert clicks == [True]                                 # a drag is not a click
    assert pet.pos() != start
    assert QSettings().value("mascot/pos") == pet.pos()

    pet.set_size(128)
    assert pet.width() == 128


def test_hide_and_show_mascot_from_menu(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))     # don't scan real sessions
    from claude_buddy.app import Buddy

    buddy = Buddy(qapp)
    texts = lambda: [a.text() for a in buddy.menu.actions()]
    assert buddy.desktop.isVisible() and "Ocultar mascota" in texts()

    buddy._desktop_action.trigger()
    assert not buddy.desktop.isVisible() and "Mostrar mascota" in texts()
    buddy.shutdown()

    again = Buddy(qapp)                                        # choice survives a restart
    assert not again.desktop.isVisible()
    assert "Mostrar mascota" in [a.text() for a in again.menu.actions()]
    again._desktop_action.trigger()
    assert again.desktop.isVisible()
    again.shutdown()


def test_panel_smoke(qapp, write_session, tmp_path):
    from PySide6.QtWidgets import QMenu

    from claude_buddy.ui.mascot import Mascot
    from claude_buddy.ui.panel import Panel

    write_session([user("arreglar impresión", 1)], sid="a")
    write_session([{**user("brazo robot", 2), "cwd": "C:\\dev\\Brazo"}], folder="c--dev-Brazo", sid="b")
    mascot = Mascot()
    panel = Panel(mascot, QMenu())
    panel.set_result(SessionIndex(tmp_path / "projects").refresh())
    assert "2 sesiones · 2 proyectos" in panel._status.text()

    panel._search.setText("impresion")
    assert panel._visible_session_count() == 1
    panel._search.setText("nada que coincida")
    assert "Sin resultados" in panel._empty.text()

    assert not mascot.pixmap(48).isNull() and not mascot.icon().isNull()
    mascot.set_skin("mint", "wizard")
    mascot.set_state("writing")
    assert mascot.state == "writing"
