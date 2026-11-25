from conftest import user

from claude_buddy.cli import main
from claude_buddy.scanner import scan_sessions


def test_missing_root_warns(tmp_path):
    result = scan_sessions(tmp_path / "nope")
    assert result.sessions == [] and "No existe" in result.warnings[0]


def test_sorted_newest_first_and_skips_subagents(write_session, tmp_path):
    old = write_session([user("old", 1)], sid="old")
    write_session([user("new", 9)], folder="c--dev-other", sid="new")
    sub = old.parent / "old" / "subagents"
    sub.mkdir(parents=True)
    (sub / "agent-x.jsonl").write_text('{"type":"user"}\n', encoding="utf-8")

    result = scan_sessions(tmp_path / "projects")
    assert [s.session_id for s in result.sessions] == ["new", "old"]
    assert result.warnings == []


def test_unreadable_file_does_not_stop_scan(write_session, tmp_path):
    write_session([user("ok", 1)], sid="ok")
    bad = tmp_path / "projects" / "C--dev-demo" / "bad.jsonl"
    bad.mkdir()                                   # a directory named *.jsonl cannot be opened
    result = scan_sessions(tmp_path / "projects")
    assert [s.session_id for s in result.sessions] == ["ok"]
    assert any("bad.jsonl" in w for w in result.warnings)


def test_cli_runs(write_session, tmp_path, capsys):
    write_session([user("hola mundo", 1)])
    assert main(["--dir", str(tmp_path / "projects")]) == 0
    out = capsys.readouterr().out
    assert "hola mundo" in out and "1 sesiones en 1 proyectos" in out


def test_cli_hides_empty_sessions(write_session, tmp_path, capsys):
    write_session([user("hola", 1)])
    write_session([{"type": "mode"}], sid="empty")
    main(["--dir", str(tmp_path / "projects")])
    assert "1 vacías ocultas" in capsys.readouterr().out
    main(["--all", "--dir", str(tmp_path / "projects")])
    assert "2 sesiones" in capsys.readouterr().out
