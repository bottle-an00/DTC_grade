from tools.run_extraction_app import derive_output_paths, resolve_config


def test_resolve_config_prompts_only_for_missing_keys():
    prompts = []

    def fake_prompt(text):
        prompts.append(text)
        return "  entered-value  "

    config = {"webhook_url": "https://example.com/n8n"}
    resolve_config(config, fake_prompt)

    assert config["webhook_url"] == "https://example.com/n8n"  # untouched, already set
    assert config["teams_webhook_url"] == "entered-value"  # prompted and trimmed
    assert len(prompts) == 1  # webhook_url was already there, so only asked once


def test_resolve_config_prompts_for_both_when_empty():
    def fake_prompt(text):
        return "value"

    config = {}
    resolve_config(config, fake_prompt)

    assert config == {"webhook_url": "value", "teams_webhook_url": "value"}


def test_derive_output_paths_matches_the_chosen_sqlite_basename():
    output_json, report_path = derive_output_paths(r"C:\Users\me\Desktop\dtc_master.sqlite")

    assert output_json == r"C:\Users\me\Desktop\dtc_master_extraction.json"
    assert report_path == r"C:\Users\me\Desktop\dtc_master_report.txt"
