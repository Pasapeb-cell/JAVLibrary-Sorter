from javsorter.config.settings import Settings


def test_load_missing_file_returns_defaults(tmp_path):
    settings = Settings.load(tmp_path / "settings.json")

    assert settings.last_source_folder == ""
    assert settings.sort_in_place is False
    assert "Actress" in settings.enabled_categories


def test_save_and_load_roundtrip(tmp_path):
    path = tmp_path / "settings.json"
    original = Settings(
        last_source_folder="C:/videos",
        last_library_folder="C:/library",
        sort_in_place=True,
        enabled_categories=["Actress", "Studio"],
        dev_mode_dialog_acknowledged=True,
    )

    original.save(path)
    loaded = Settings.load(path)

    assert loaded == original


def test_load_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{not valid json", encoding="utf-8")

    settings = Settings.load(path)

    assert settings == Settings()


def test_load_ignores_unknown_fields(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"last_source_folder": "C:/x", "some_future_field": 123}', encoding="utf-8")

    settings = Settings.load(path)

    assert settings.last_source_folder == "C:/x"
