from pathlib import Path

from app.config import Settings


def test_defaults_use_public_sample_vault():
    settings = Settings(_env_file=None)

    assert settings.vault_path == Path("sample_vault")
    assert settings.vault_name == "个人知识库示例"
    assert settings.index_path == Path("data/index.json")


def test_environment_can_select_a_real_vault(monkeypatch, tmp_path):
    monkeypatch.setenv("VAULT_PATH", str(tmp_path))
    monkeypatch.setenv("VAULT_NAME", "我的知识库")

    settings = Settings(_env_file=None)

    assert settings.vault_path == tmp_path
    assert settings.vault_name == "我的知识库"
