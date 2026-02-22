Testing
=======

Quick instructions to run the unit tests locally.

1. Create and activate a virtual environment (recommended):

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
# source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install --upgrade pip
pip install -r engine/requirements.txt
```

3. Run tests:

```bash
cd engine
pytest -q
```

Notes:
- Tests run under the `engine` folder to avoid touching repo data files.
- If you prefer separate dev deps, add a `requirements-dev.txt`.
