from unittest.mock import patch

from icloudphotonator.__main__ import _early_fda_registration_probe


def test_probe_skips_first_path_on_permission_error_and_succeeds_on_second() -> None:
    """First candidate raises PermissionError -> continue, second opens successfully."""
    fake_fd = 42
    open_results = [PermissionError(13, "denied"), fake_fd, fake_fd]

    def fake_open(path, flags):
        result = open_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    with patch("os.open", side_effect=fake_open) as mock_open, \
         patch("os.read", return_value=b"") as mock_read, \
         patch("os.close") as mock_close:
        _early_fda_registration_probe()

    assert mock_open.call_count == 2
    mock_read.assert_called_once_with(fake_fd, 1)
    mock_close.assert_called_once_with(fake_fd)


def test_probe_returns_after_first_successful_open() -> None:
    """First candidate opens successfully -> read + close called, function returns."""
    fake_fd = 7

    with patch("os.open", return_value=fake_fd) as mock_open, \
         patch("os.read", return_value=b"x") as mock_read, \
         patch("os.close") as mock_close:
        _early_fda_registration_probe()

    assert mock_open.call_count == 1
    mock_read.assert_called_once_with(fake_fd, 1)
    mock_close.assert_called_once_with(fake_fd)


def test_probe_returns_cleanly_when_all_paths_missing() -> None:
    """All candidates raise FileNotFoundError -> function returns without crashing."""
    with patch("os.open", side_effect=FileNotFoundError(2, "missing")) as mock_open, \
         patch("os.read") as mock_read, \
         patch("os.close") as mock_close:
        _early_fda_registration_probe()

    assert mock_open.call_count == 3
    mock_read.assert_not_called()
    mock_close.assert_not_called()
