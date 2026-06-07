from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_single_handlers_module_only():
    assert (ROOT / "app" / "handlers.py").is_file()
    assert not (ROOT / "app" / "handlers").exists()

def test_single_entrypoint():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert 'python", "-m", "app.bot"' in dockerfile
    assert "startCommand: python -m app.bot" in render
    assert "app.main" not in dockerfile
    assert "app.main" not in render

def test_no_secrets_or_runtime_junk():
    assert not (ROOT / ".env").exists()
    assert not (ROOT / ".venv").exists()
    assert not (ROOT / "bot.db").exists()

def test_visual_module_is_connected():
    handlers = (ROOT / "app" / "handlers.py").read_text(encoding="utf-8")
    assert "from app.visual_ui_v32 import" in handlers
    assert "category_asset" in handlers
    assert "product_caption" in handlers
