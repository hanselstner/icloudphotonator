# Contributing to iCloudPhotonator

Thank you for your interest in contributing to iCloudPhotonator! 🎉

## Development Setup

1. **Install Python 3.13+** and [uv](https://docs.astral.sh/uv/)
2. **Clone the repo**:
   ```bash
   git clone https://github.com/hanselstner/icloudphotonator.git
   cd icloudphotonator
   ```
3. **Install dependencies**:
   ```bash
   uv sync
   ```
4. **Run tests**:
   ```bash
   uv run python -m pytest tests/ -q
   ```

## Running the App

```bash
uv run python -m icloudphotonator
```

> **Note:** The GUI requires macOS with customtkinter support.

## Building the macOS App

```bash
uv run pyinstaller --noconfirm --clean iCloudPhotonator.spec
open dist/iCloudPhotonator.app
```

## Code Style

- **Python 3.13+** — use modern syntax and type hints
- **pytest** for all tests
- **All UI strings** via i18n (`from icloudphotonator.i18n import t`)
- Locale files are in `icloudphotonator/locales/` (JSON format)
- Keep functions focused and well-documented

## Project Structure

```
icloudphotonator/
├── ui/              # GUI (customtkinter) and bridge to backend
├── locales/         # i18n translation files (en.json, de.json)
├── orchestrator.py  # Main import workflow
├── scanner.py       # File discovery and classification
├── staging.py       # Local staging for network files
├── throttle.py      # Adaptive batching and cooldowns
├── dedup.py         # Hash-based duplicate detection
├── resilience.py    # Retry logic and network monitoring
├── settings.py      # Persistent user settings
├── i18n.py          # Internationalization module
└── ...
tests/               # Test suite (216+ tests)
```

## Pull Requests

1. **Fork** the repository
2. **Create a feature branch** (`git checkout -b feature/my-feature`)
3. **Write tests** for your changes
4. **Run the full test suite** to make sure nothing is broken
5. **Submit a Pull Request** with a clear description of your changes

## Reporting Issues

- Use GitHub Issues to report bugs or request features
- Include your macOS version, Python version, and steps to reproduce
- Attach relevant log output from `~/.icloudphotonator/icloudphotonator.log`

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

