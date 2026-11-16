from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_demo_screen_and_button():
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    assert not app.exception
    assert "Gemini не подключён" in app.warning[0].value
    assert len(app.json) == 1
    app.button(key="show_demo").click().run()
    assert not app.exception
    assert len(app.json) == 2
    assert "не ответ Gemini" in app.info[0].value
    assert '"mode": "demo"' in app.json[1].value
