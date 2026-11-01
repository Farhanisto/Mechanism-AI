"""Settings tolerate the CORS origin formats people paste into Railway."""

from app.config import DEFAULT_CORS_ORIGINS, Settings


def _settings(monkeypatch, value: str) -> Settings:
    monkeypatch.setenv("MECHANISM_AI_CORS_ORIGINS", value)
    return Settings(_env_file=None)


def test_cors_origins_accepts_a_json_array(monkeypatch) -> None:
    settings = _settings(monkeypatch, '["https://web.up.railway.app"]')
    assert settings.cors_origins == ["https://web.up.railway.app"]


def test_cors_origins_accepts_a_bare_url(monkeypatch) -> None:
    settings = _settings(monkeypatch, "https://web.up.railway.app")
    assert settings.cors_origins == ["https://web.up.railway.app"]


def test_cors_origins_accepts_single_quotes_and_commas(monkeypatch) -> None:
    settings = _settings(
        monkeypatch, "['https://a.example', 'https://b.example/']"
    )
    assert settings.cors_origins == ["https://a.example", "https://b.example"]


def test_cors_origins_empty_falls_back_to_the_local_default(monkeypatch) -> None:
    settings = _settings(monkeypatch, "")
    assert settings.cors_origins == DEFAULT_CORS_ORIGINS


def test_cors_origins_still_accepts_a_list() -> None:
    settings = Settings(_env_file=None, cors_origins=["https://a.example"])
    assert settings.cors_origins == ["https://a.example"]
