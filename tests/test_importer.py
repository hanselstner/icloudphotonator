import click

from pathlib import Path

from icloudphotonator.importer import PhotoImporter, find_photo_libraries


def test_find_photo_libraries_searches_common_directories(
    tmp_path: Path,
    monkeypatch,
) -> None:
    pictures_dir = tmp_path / "Pictures"
    shared_dir = tmp_path / "Shared"
    pictures_dir.mkdir()
    shared_dir.mkdir()
    private_library = pictures_dir / "Private.photoslibrary"
    shared_library = shared_dir / "Family.photoslibrary"
    private_library.mkdir()
    shared_library.mkdir()
    (pictures_dir / "ignore.txt").write_text("x", encoding="utf-8")

    monkeypatch.setattr("icloudphotonator.importer.PICTURES_LIBRARY_DIR", pictures_dir)
    monkeypatch.setattr("icloudphotonator.importer.SHARED_LIBRARY_DIR", shared_dir)

    assert find_photo_libraries() == [private_library, shared_library]


def test_import_batch_uses_osxphotos_library_api_and_parses_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    file_paths = [tmp_path / "a.jpg", tmp_path / "b.jpg"]
    album = "Kristins iPhone"
    library = tmp_path / "Shared.photoslibrary"
    library.mkdir()

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
    result = importer.import_batch(file_paths, report_dir=tmp_path, album=album, library=library)

    assert captured["files_or_dirs"] == tuple(str(path) for path in file_paths)
    assert captured["album"] == (album,)
    assert captured["skip_dups"] is True
    assert captured["auto_live"] is True
    assert captured["exiftool"] is True
    assert captured["no_progress"] is True
    assert captured["library"] == str(library)
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


def test_import_batch_returns_descriptive_error_for_empty_abort_exception(
    tmp_path: Path,
    monkeypatch,
) -> None:
    file_paths = [tmp_path / "a.jpg"]

    def fake_import_cli(**kwargs) -> None:
        raise click.exceptions.Abort()

    monkeypatch.setattr(PhotoImporter, "_verify_osxphotos", lambda self: None)
    monkeypatch.setattr(PhotoImporter, "_get_import_cli", lambda self: fake_import_cli)

    importer = PhotoImporter()
    result = importer.import_batch(file_paths, report_dir=tmp_path)

    assert result.success is False
    assert result.error_count == len(file_paths)
    assert result.errors == [
        {
            "file": "",
            "error": "osxphotos aborted — möglicherweise fehlt exiftool (https://exiftool.org/)",
        }
    ]