from tools.config_store import load_config, save_config


def test_load_config_returns_empty_dict_when_file_missing(tmp_path):
    assert load_config(str(tmp_path / "missing.json")) == {}


def test_save_then_load_round_trips(tmp_path):
    path = str(tmp_path / "config.json")
    save_config(path, {"webhook_url": "https://example.com/n8n"})

    assert load_config(path) == {"webhook_url": "https://example.com/n8n"}
