"""Phase 4: chat engine (fake SDK client), live transcript rendering and buddy states."""

import os
import threading
from datetime import UTC, datetime
from pathlib import Path

import pytest
from claude_agent_sdk.types import (
    AssistantMessage, ResultMessage, StreamEvent, TextBlock, ToolResultBlock, ToolUseBlock, UserMessage,
)

from claude_buddy.chat import ChatEngine, ChatEvent, tool_activity
from claude_buddy.models import SessionInfo


def make_session(cwd: Path, sid: str = "sess-1") -> SessionInfo:
    return SessionInfo(sid, cwd / f"{sid}.jsonl", "folder", str(cwd), "t", datetime.now(UTC), 1, "cli")


def result(sid: str = "sess-1", is_error: bool = False, text: str | None = None) -> ResultMessage:
    return ResultMessage(subtype="error_during_execution" if is_error else "success", duration_ms=1,
                         duration_api_ms=1, is_error=is_error, num_turns=1, session_id=sid,
                         total_cost_usd=0.0123, result=text)


def delta(text: str) -> StreamEvent:
    return StreamEvent(uuid="u", session_id="sess-1",
                       event={"type": "content_block_delta", "delta": {"type": "text_delta", "text": text}})


class FakeClient:
    instances: list["FakeClient"] = []
    script: list = []

    def __init__(self, options: dict) -> None:
        self.options = options
        self.queries: list[str] = []
        self.disconnected = False
        FakeClient.instances.append(self)

    async def connect(self) -> None: ...

    async def query(self, prompt: str) -> None:
        self.queries.append(prompt)

    async def receive_response(self):
        for item in FakeClient.script:
            if callable(item):                         # e.g. ask for a permission mid-turn
                item = await item(self)
            if item is not None:
                yield item

    async def interrupt(self) -> None: ...

    async def set_permission_mode(self, mode: str) -> None: ...

    async def disconnect(self) -> None:
        self.disconnected = True


def run_turn(engine_events: list, engine: ChatEngine, session: SessionInfo, prompt: str,
             on_event=None) -> list[ChatEvent]:
    done = threading.Event()
    engine_events.clear()

    def collect(ev: ChatEvent) -> None:
        engine_events.append(ev)
        if on_event:
            on_event(ev)
        if ev.kind == "busy" and not ev.data["busy"]:
            done.set()

    engine._emit = collect
    engine.send(session, prompt)
    assert done.wait(5), "turn did not finish"
    return list(engine_events)


@pytest.fixture
def engine():
    FakeClient.instances.clear()
    eng = ChatEngine(lambda ev: None, client_factory=FakeClient, options_factory=lambda **kw: kw)
    yield eng
    eng.close()


def kinds(events: list[ChatEvent]) -> list[str]:
    return [e.kind for e in events if e.kind not in ("activity",)]


def test_streams_text_tools_and_result(engine, tmp_path):
    FakeClient.script = [
        delta("Hola "), delta("mundo"),
        AssistantMessage(content=[TextBlock("Hola mundo")], model="m"),
        AssistantMessage(content=[ToolUseBlock("t1", "Read", {"file_path": str(tmp_path / "a.py")})], model="m"),
        UserMessage(content=[ToolResultBlock("t1", "no such file", True)]),
        result(),
    ]
    events = run_turn([], engine, make_session(tmp_path), "¿qué tal?")
    assert kinds(events) == ["busy", "text_delta", "text_delta", "text", "tool", "tool_error", "result", "busy"]
    by_kind = {e.kind: e for e in events}
    assert by_kind["tool"].text == "Read · a.py"
    assert by_kind["result"].data["cost"] == 0.0123

    client = FakeClient.instances[0]
    assert client.queries == ["¿qué tal?"]
    assert client.options["resume"] == "sess-1" and client.options["cwd"] == str(tmp_path)
    assert client.options["include_partial_messages"] is True


def test_reuses_connection_for_same_session(engine, tmp_path):
    FakeClient.script = [result()]
    session = make_session(tmp_path)
    run_turn([], engine, session, "uno")
    run_turn([], engine, session, "dos")
    assert len(FakeClient.instances) == 1 and FakeClient.instances[0].queries == ["uno", "dos"]
    run_turn([], engine, make_session(tmp_path, "otra"), "tres")
    assert len(FakeClient.instances) == 2 and FakeClient.instances[0].disconnected


def test_permission_round_trip(engine, tmp_path):
    async def ask(client):
        decision = await client.options["can_use_tool"]("Bash", {"command": "rm -rf build"}, None)
        return AssistantMessage(content=[TextBlock(f"decision={decision.behavior}")], model="m")

    FakeClient.script = [ask, result()]
    answer = lambda ev: ev.kind == "permission" and engine.answer_permission(ev.data["id"], False)
    events = run_turn([], engine, make_session(tmp_path), "borra", on_event=answer)
    perm = next(e for e in events if e.kind == "permission")
    assert perm.text == "Bash · rm -rf build" and perm.data["tool"] == "Bash"
    assert any(e.kind == "text" and e.text == "decision=deny" for e in events)
    assert ("waiting" in [e.text for e in events if e.kind == "activity"])


def test_missing_project_folder_is_an_error(engine, tmp_path):
    events = run_turn([], engine, make_session(tmp_path / "gone"), "hola")
    assert any(e.kind == "error" and "ya no existe" in e.text for e in events)
    assert FakeClient.instances == []


def test_fork_to_new_session_id_is_reported(engine, tmp_path):
    FakeClient.script = [result(sid="nuevo")]
    events = run_turn([], engine, make_session(tmp_path), "hola")
    assert any(e.kind == "session" and e.text == "nuevo" for e in events)


def test_tool_activity_mapping():
    assert tool_activity("Read") == "reading"
    assert tool_activity("Grep") == "searching"
    assert tool_activity("Bash") == "running"
    assert tool_activity("Edit") == "writing"
    assert tool_activity("mcp__x__y") == "running"


# --- Qt side -----------------------------------------------------------------
@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_transcript_view_streaming(qapp):
    from claude_buddy.transcript import Entry
    from claude_buddy.ui.transcript_view import TranscriptView

    view = TranscriptView()
    view.show_placeholder("Cargando…")
    view.append_entry(Entry("user", "pregunta"))
    view.stream_text("**neg")
    view.stream_text("rita**")
    assert "**negrita**" in view.toPlainText()
    view.finish_text("**negrita**")
    text = view.toPlainText()
    assert "Cargando" not in text and "negrita" in text and "**" not in text
    view.append_entry(Entry("tool", "Bash · ls"))
    assert text.count("Claude") == view.toPlainText().count("Claude") == 1   # one header per run


def test_panel_chat_flow(qapp, tmp_path):
    from PySide6.QtWidgets import QMenu

    from claude_buddy.ui.mascot import Mascot
    from claude_buddy.ui.panel import Panel

    (tmp_path / "sess-1.jsonl").write_text("", encoding="utf-8")
    session = make_session(tmp_path)
    panel = Panel(Mascot(), QMenu())
    sent = []
    panel.chat_send.connect(lambda s, t, m: sent.append((s.session_id, t, m)))
    panel.open_session(session)
    assert panel._chat._banner.isVisibleTo(panel)                  # file just written: warn

    panel._chat._input.setPlainText("continúa")
    panel._chat._submit()
    assert sent == [("sess-1", "continúa", panel._chat.mode)]
    assert "continúa" in panel._view.toPlainText()

    for ev in [ChatEvent("busy", "sess-1", data={"busy": True}), ChatEvent("text_delta", "sess-1", "Va"),
               ChatEvent("text", "sess-1", "Vale"), ChatEvent("permission", "sess-1", "Bash · ls", {"id": "p1"}),
               ChatEvent("result", "sess-1", data={"is_error": False, "cost": 0.01}),
               ChatEvent("busy", "sess-1", data={"busy": False})]:
        panel.on_chat_event(ev)
    assert "Vale" in panel._view.toPlainText()
    assert "Listo" in panel._chat._status.text()
    assert not panel._chat._perm.isVisibleTo(panel)                # cleared when the turn ends
    panel.on_chat_event(ChatEvent("text", "otra-sesion", "no debe salir"))
    assert "no debe salir" not in panel._view.toPlainText()


def test_mascot_priorities(qapp):
    from claude_buddy.ui.mascot import Mascot

    m = Mascot()
    m.set_state("writing")
    m.flash("done", 10_000)
    assert m.state == "done"
    m.set_override("dragged")
    assert m.state == "dragged"
    m.set_override(None)
    m._end_flash()
    assert m.state == "writing" and m.base_state == "writing"