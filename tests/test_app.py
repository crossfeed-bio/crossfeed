"""The self-contained program's entry (#26): double-click opens the page, arguments are the command line."""
from crossfeed import app


def test_no_arguments_or_options_alone_open_the_local_page():
    assert app.arguments([]) == ["gui"]
    assert app.arguments(["--no-browser"]) == ["gui", "--no-browser"]
    assert app.arguments(["--port", "8765"]) == ["gui", "--port", "8765"]


def test_a_command_is_passed_through():
    assert app.arguments(["derive", "SMGDB00000004", "--live"]) == ["derive", "SMGDB00000004", "--live"]
    assert app.arguments(["--help"]) == ["--help"]


def test_a_stopping_message_stays_on_screen_when_double_clicked(monkeypatch, capsys):
    # a port in use raises SystemExit with a message; double-clicked, the window waits for Enter
    def refuse(args):
        raise SystemExit("grownet gui: cannot use port 8765 (Address already in use).")
    monkeypatch.setattr(app, "main", refuse)
    waited = []
    assert app.run([], wait=waited.append) == 1
    assert "cannot use port 8765" in capsys.readouterr().out and waited == ["Press Enter to close this window."]
    # from a terminal, with arguments, it returns at once
    waited.clear()
    assert app.run(["gui", "--port", "8765"], wait=waited.append) == 1 and waited == []


def test_an_unexpected_error_is_shown_not_lost(monkeypatch, capsys):
    def boom(args):
        raise RuntimeError("something broke")
    monkeypatch.setattr(app, "main", boom)
    waited = []
    assert app.run([], wait=waited.append) == 1
    assert "RuntimeError: something broke" in capsys.readouterr().err and waited
