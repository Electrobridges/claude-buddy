"""Phase 3: building a readable history from a session file."""

import os

import pytest

from claude_buddy.transcript import load_transcript, tool_summary

CWD = "C:\\dev\\demo"


def rec(kind: str, uid: str, parent: str | None, content, minute: int = 0, **extra) -> dict:
    role = "user" if kind == "user" else "assistant"
    message = {"role": role, "content": content}
    if kind == "assistant":
        message["id"] = extra.pop("msg_id", uid)
    return {"type": kind, "uuid": uid, "parentUuid": parent, "cwd": CWD,
            "timestamp": f"2026-11-20T10:{minute:02d}:00.000Z", "message": message, **extra}


def kinds(path) -> list[tuple[str, str]]:
    return [(e.kind, e.text) for e in load_transcript(path).entries]


def test_conversation_with_tools(write_session):
    f = write_session([
        rec("user", "u1", None, "Arregla el login"),
        rec("assistant", "a1", "u1", [{"type": "thinking", "thinking": "hmm"}], msg_id="m1"),
        rec("assistant", "a2", "a1", [{"type": "text", "text": "Voy a mirar"}], msg_id="m1"),
        rec("assistant", "a3", "a2", [{"type": "tool_use", "id": "t1", "name": "Read",
                                        "input": {"file_path": CWD + "\\src\\login.py"}}], msg_id="m1"),
        rec("user", "r1", "a3", [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}], toolUseResult={}),
        rec("assistant", "a4", "r1", [{"type": "tool_use", "id": "t2", "name": "Bash",
                                        "input": {"command": "pytest -q"}}], msg_id="m2"),
        rec("user", "r2", "a4", [{"type": "tool_result", "tool_use_id": "t2", "is_error": True,
                                   "content": "1 failed\ntraceback..."}], toolUseResult="Error"),
        rec("assistant", "a5", "r2", [{"type": "text", "text": "**Listo**"}], msg_id="m3"),
    ])
    assert kinds(f) == [
        ("user", "Arregla el login"),
        ("assistant", "Voy a mirar"),
        ("tool", "Read · src\\login.py"),
        ("tool", "Bash · pytest -q"),
        ("error", "1 failed traceback..."),
        ("assistant", "**Listo**"),
    ]


def test_rewound_branch_is_hidden(write_session):
    f = write_session([
        rec("user", "u1", None, "primera versión"),
        rec("assistant", "a1", "u1", [{"type": "text", "text": "respuesta vieja"}]),
        rec("user", "u2", None, "versión editada"),          # user rewound and edited the prompt
        rec("assistant", "a2", "u2", [{"type": "text", "text": "respuesta nueva"}]),
    ])
    assert kinds(f) == [("user", "versión editada"), ("assistant", "respuesta nueva")]


def test_parallel_tool_errors_are_kept(write_session):
    f = write_session([
        rec("user", "u1", None, "lee dos archivos"),
        rec("assistant", "a1", "u1", [{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "a"}}], msg_id="m"),
        rec("assistant", "a2", "a1", [{"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "b"}}], msg_id="m"),
        rec("user", "r1", "a1", [{"type": "tool_result", "tool_use_id": "t1", "is_error": True, "content": "no existe"}],
            toolUseResult="Error"),                         # sibling branch: off the main chain
        rec("user", "r2", "a2", [{"type": "tool_result", "tool_use_id": "t2", "content": "ok"}], toolUseResult={}),
        rec("assistant", "a3", "r2", [{"type": "text", "text": "hecho"}]),
    ])
    assert ("error", "no existe") in kinds(f)
    assert kinds(f)[-1] == ("assistant", "hecho")


def test_compaction_keeps_earlier_part(write_session):
    f = write_session([
        rec("user", "u1", None, "antes"),
        rec("assistant", "a1", "u1", [{"type": "text", "text": "vale"}]),
        {"type": "system", "subtype": "compact_boundary", "uuid": "c1", "parentUuid": None,
         "logicalParentUuid": "a1", "timestamp": "2026-11-20T11:00:00.000Z"},
        rec("user", "s1", "c1", "resumen largo…", isCompactSummary=True),
        rec("user", "u2", "s1", "después"),
    ])
    assert kinds(f) == [("user", "antes"), ("assistant", "vale"),
                        ("notice", "Conversación compactada"), ("user", "después")]


def test_commands_interruptions_and_attachments(write_session):
    f = write_session([
        rec("user", "u1", None, "<command-name>/model</command-name><command-args>opus</command-args>"),
        rec("user", "u2", "u1", [{"type": "image", "source": {}}, {"type": "text", "text": "mira esto"}]),
        rec("user", "u3", "u2", [{"type": "text", "text": "[Request interrupted by user]"}]),
        rec("assistant", "a1", "u3", [{"type": "text", "text": "API Error: 500"}], isApiErrorMessage=True),
    ])
    assert kinds(f) == [("command", "/model opus"), ("user", "mira esto\n\n[1 adjunto]"),
                        ("notice", "Interrumpido por el usuario"), ("error", "API Error: 500")]


def test_tool_summary():
    assert tool_summary("Grep", {"pattern": "TODO", "path": "src"}) == "Grep · TODO"
    assert tool_summary("TodoWrite", {"todos": []}) == "TodoWrite · lista de tareas"
    assert tool_summary("mcp__github__create_issue", {"title": "x"}) == "github · create_issue"
    assert tool_summary("Write", {"file_path": "C:/dev/demo/a.txt"}, "C:\\dev\\demo") == "Write · a.txt"
    assert tool_summary("Unknown", None) == "Unknown"


def test_corrupt_lines_reported(write_session):
    f = write_session([rec("user", "u1", None, "hola")], raw_lines=["{not json"])
    t = load_transcript(f)
    assert [e.text for e in t.entries] == ["hola"] and "1 línea" in t.warnings[0]


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_panel_history_view(qapp, write_session, tmp_path):
    from PySide6.QtWidgets import QMenu

    from claude_buddy.scanner import SessionIndex
    from claude_buddy.ui.mascot import Mascot
    from claude_buddy.ui.panel import Panel

    f = write_session([rec("user", "u1", None, "pregunta"),
                       rec("assistant", "a1", "u1", [{"type": "text", "text": "| a | b |\n|---|---|\n| 1 | 2 |"}])])
    session = SessionIndex(tmp_path / "projects").refresh().sessions[0]
    panel = Panel(Mascot(), QMenu())
    requested = []
    panel.history_requested.connect(requested.append)

    panel.open_session(session)
    assert requested == [session] and panel.current_session is session
    panel.set_transcript(session, load_transcript(f))
    text = panel._view.toPlainText()
    assert "pregunta" in text and "Claude" in text and "1" in text

    panel.back_to_list()
    assert panel.current_session is None
    panel.set_transcript(session, load_transcript(f))      # late result after going back: ignored
    assert panel._view.toPlainText() == ""