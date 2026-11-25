from conftest import assistant, user

from claude_buddy.parser import NO_TITLE, extract_prompt, parse_session


def test_typical_vscode_session(write_session):
    f = write_session([
        {"type": "mode", "mode": "normal", "sessionId": "x"},
        user([{"type": "text", "text": "<ide_opened_file>The user opened a.py</ide_opened_file>"},
              {"type": "text", "text": "Fix the\nlogin bug"}], 1),
        assistant("m1", {"type": "thinking", "thinking": "..."}, 2),
        assistant("m1", {"type": "text", "text": "Looking at it"}, 2),
        assistant("m1", {"type": "tool_use", "id": "t1", "name": "Read", "input": {}}, 2),
        user([{"type": "tool_result", "tool_use_id": "t1", "content": "..."}], 3, toolUseResult={}),
        assistant("m2", {"type": "text", "text": "Done"}, 4),
        user("<system-reminder>injected</system-reminder>", 5, isMeta=True),
        {"type": "ai-title", "aiTitle": "Login fix"},
    ])
    s = parse_session(f)
    assert s.title == "Fix the login bug"
    assert s.message_count == 3                  # 1 prompt + 2 replies (m1 grouped)
    assert s.last_activity.isoformat() == "2026-11-20T10:05:00+00:00"
    assert s.cwd == "C:\\dev\\demo" and s.project_name == "demo"
    assert s.entrypoint == "cli" and s.session_id == "11111111-aaaa"


def test_pasted_content_is_unwrapped():
    rec = user('<pasted_content id="ab12">\nBuild an app\n</pasted_content id="ab12">', 1)
    assert extract_prompt(rec) == ("Build an app", False)


def test_slash_command_loses_to_plain_prompt(write_session):
    f = write_session([
        user("<command-message>model</command-message>\n<command-name>/model</command-name>\n"
             "<command-args>opus</command-args>", 1),
        user("<local-command-stdout>Set model</local-command-stdout>", 2),
        user("real question", 3),
    ])
    s = parse_session(f)
    assert s.title == "real question"
    assert s.message_count == 2                  # command + prompt; stdout ignored


def test_command_only_session_uses_command_as_title(write_session):
    f = write_session([user("<command-name>/init</command-name><command-args></command-args>", 1)])
    assert parse_session(f).title == "/init"


def test_fallback_titles(write_session):
    f = write_session([{"type": "ai-title", "aiTitle": "AI"}, {"type": "custom-title", "customTitle": "Mine"}])
    assert parse_session(f).title == "Mine"
    g = write_session([{"type": "summary", "summary": "Old"}], sid="2")
    assert parse_session(g).title == "Old"
    h = write_session([{"type": "mode"}], sid="3")
    assert parse_session(h).title == NO_TITLE


def test_interrupt_marker_and_image_refs(write_session):
    f = write_session([user("[Request interrupted by user]", 1), user("[Image #1]Hola equipo", 2)])
    s = parse_session(f)
    assert s.title == "Hola equipo" and s.message_count == 1


def test_image_only_prompt_counts_without_title(write_session):
    f = write_session([user([{"type": "image", "source": {}}], 1), user("then text", 2)])
    s = parse_session(f)
    assert s.message_count == 2 and s.title == "then text"


def test_corrupt_lines_are_skipped_and_reported(write_session):
    f = write_session([user("hello", 1)], raw_lines=['{"type": "user", broken', "[1, 2]"])
    warnings: list[str] = []
    s = parse_session(f, warn=warnings.append)
    assert s.title == "hello" and s.message_count == 1
    assert len(warnings) == 1 and "2 línea(s)" in warnings[0]


def test_no_timestamps_falls_back_to_mtime(write_session):
    f = write_session([{"type": "mode", "mode": "normal"}])
    assert parse_session(f).last_activity.tzinfo is not None


def test_sidechain_and_api_errors_ignored(write_session):
    f = write_session([
        user("main", 1),
        user("sub", 2, isSidechain=True),
        {**assistant("e", {"type": "text", "text": "API Error"}, 3), "isApiErrorMessage": True},
    ])
    assert parse_session(f).message_count == 1


def test_first_cwd_is_project_dir(write_session):
    f = write_session([user("a", 1), {**user("b", 2), "cwd": "C:\\dev\\demo\\sub"}])
    assert parse_session(f).cwd == "C:\\dev\\demo"
