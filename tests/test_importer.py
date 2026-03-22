from pathlib import Path

from icloudphotonator.importer import PhotoImporter


def test_import_batch_uses_osxphotos_library_api_and_parses_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    file_paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]

    def fake_import_cli(**kwargs) -> None:
        captured.update(kwargs)
        Path(kwargs["report"]).write_text(
            "filepath,imported,error,error_message,uuid\n"
            f"{file_paths[0]},true,false,,uuid-1\n"
            f"{file_paths[1]},false,false,,\n",
            encoding="utf-8",
        )

    monkeypatch.setattr(PhotoImporter, "_verify_osxphotos", lambda self: None)
    monkeypatch.setattr(PhotoImporter, "_get_import_cli", lambda self: fake_import_cli)

    importer = PhotoImporter()
    result = importer.import_batch(file_paths, report_dir=tmp_path)

    assert captured["files_or_dirs"] == tuple(str(path) for path in file_paths)
    assert captured["skip_dups"] is True
    assert captured["auto_live"] is True
    assert captured["exiftool"] is True
    assert captured["no_progress"] is True
    assert result.success is True
    assert result.imported_count == 1
    assert result.skipped_count == 1
    assert result.error_count == 0
    assert result.errors == []
    assert result.report_path is not None
    assert result.report_path.exists()


def test_import_batch_returns_failure_when_api_raises_without_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    file_paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]

    def fake_import_cli(**kwargs) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(PhotoImporter, "_verify_osxphotos", lambda self: None)
    monkeypatch.setattr(PhotoImporter, "_get_import_cli", lambda self: fake_import_cli)

    importer = PhotoImporter()
    result = importer.import_batch(file_paths, report_dir=tmp_path)

    assert result.success is False
    assert result.imported_count == 0
    assert result.skipped_count == 0
    assert result.error_count == len(file_paths)
    assert result.errors == [{"file": "", "error": "boom"}]
    assert result.report_path is None