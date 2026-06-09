from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_suppliers_are_database_managed():
    config = (ROOT / "app" / "config.py").read_text(encoding="utf-8")
    database = (ROOT / "app" / "database.py").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "SUPPLIER_IDS =" not in config
    assert "seed_env_suppliers" not in database
    assert "SUPPLIER_IDS=" not in env_example

def test_supplier_admin_callbacks_exist():
    handlers = (ROOT / "app" / "handlers.py").read_text(encoding="utf-8")
    keyboards = (ROOT / "app" / "keyboards.py").read_text(encoding="utf-8")
    for callback in (
        "admin:add_supplier",
        "admin:remove_supplier",
        "admin:bind_supplier",
        "admin:unbind_supplier",
        "admin:supplier_action_cancel",
    ):
        assert callback in handlers
        assert callback in keyboards or callback == "admin:unbind_supplier"
