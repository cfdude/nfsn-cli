import pytest

from nfsn_cli.config import ConfigError, load_credentials, parse_env_text, write_template


def test_parse_env_text_handles_comments_exports_and_quotes():
    values = parse_env_text(
        """
        # a comment

        NFSN_LOGIN=testuser
        export NFSN_API_KEY="quoted-key"
        MALFORMED
        """
    )
    assert values["NFSN_LOGIN"] == "testuser"
    assert values["NFSN_API_KEY"] == "quoted-key"
    assert "MALFORMED" not in values


def test_environment_variables_win(monkeypatch, tmp_path):
    monkeypatch.setenv("NFSN_LOGIN", "from-env")
    monkeypatch.setenv("NFSN_API_KEY", "env-key")
    path = tmp_path / "credentials"
    path.write_text("NFSN_LOGIN=from-file\nNFSN_API_KEY=file-key\n")

    credentials, warnings = load_credentials(path)

    assert credentials.login == "from-env"
    assert warnings == []


def test_file_is_used_when_environment_is_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("NFSN_LOGIN", raising=False)
    monkeypatch.delenv("NFSN_API_KEY", raising=False)
    path = tmp_path / "credentials"
    path.write_text("NFSN_LOGIN=from-file\nNFSN_API_KEY=file-key\n")
    path.chmod(0o600)

    credentials, warnings = load_credentials(path)

    assert (credentials.login, credentials.api_key) == ("from-file", "file-key")
    assert warnings == []


def test_permissive_mode_produces_a_warning(monkeypatch, tmp_path):
    monkeypatch.delenv("NFSN_LOGIN", raising=False)
    monkeypatch.delenv("NFSN_API_KEY", raising=False)
    path = tmp_path / "credentials"
    path.write_text("NFSN_LOGIN=a\nNFSN_API_KEY=b\n")
    path.chmod(0o644)

    _credentials, warnings = load_credentials(path)

    assert any("chmod 600" in warning for warning in warnings)


def test_missing_file_explains_how_to_fix_it(monkeypatch, tmp_path):
    monkeypatch.delenv("NFSN_LOGIN", raising=False)
    monkeypatch.delenv("NFSN_API_KEY", raising=False)
    with pytest.raises(ConfigError, match="nfsn init"):
        load_credentials(tmp_path / "absent")


def test_blank_values_are_reported(monkeypatch, tmp_path):
    monkeypatch.delenv("NFSN_LOGIN", raising=False)
    monkeypatch.delenv("NFSN_API_KEY", raising=False)
    path = tmp_path / "credentials"
    path.write_text("NFSN_LOGIN=\nNFSN_API_KEY=\n")
    with pytest.raises(ConfigError, match="NFSN_LOGIN, NFSN_API_KEY"):
        load_credentials(path)


def test_write_template_creates_a_0600_file(tmp_path):
    path = write_template(tmp_path / "nested" / "credentials")
    assert path.exists()
    assert path.stat().st_mode & 0o777 == 0o600
    assert "NFSN_API_KEY=" in path.read_text()


def test_write_template_refuses_to_clobber(tmp_path):
    path = tmp_path / "credentials"
    path.write_text("NFSN_LOGIN=existing\n")
    with pytest.raises(ConfigError, match="refusing to overwrite"):
        write_template(path)
    assert path.read_text() == "NFSN_LOGIN=existing\n"
