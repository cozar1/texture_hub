# Texture Hub

A small Flask-based web app for browsing and uploading textures (Aseprite files, images).

## Overview

Texture Hub organizes texture assets and provides a simple web UI to view, upload, and manage collections. The project includes a lightweight Flask app (`app.py`) with templates and static assets.

## Prerequisites

- Python 3.8+ (3.10+ recommended)
- Git (optional)

## Quick setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
```

On Windows (PowerShell):

```powershell
.\.venv\Scripts\Activate.ps1
```

On Windows (cmd):

```cmd
.\.venv\Scripts\activate.bat
```

2. Install dependencies (Flask is likely required):

```bash
pip install flask
# or, if you have a requirements file:
pip install -r requirements.txt
```

3. Run the app:

```bash
python app.py
```

By default, Flask will bind to `http://127.0.0.1:5000/` unless `app.py` configures otherwise.

## Project Structure

- `app.py` - application entrypoint
- `templates/` - Jinja2 HTML templates for pages
- `static/` - CSS, images, and other static assets
- `textures.aseprite` - example or source Aseprite file (binary)
- `instance/` - (Flask instance folder) runtime data
- `tests.txt` - lightweight test notes or steps

## Notes

- If your app expects other Python packages, create a `requirements.txt` with `pip freeze > requirements.txt` after installing them.
- The `templates/` folder contains pages such as `upload.html`, `texture.html`, and `collection.html` which are good starting points for customization.

## Contributing

1. Fork the repo
2. Create a feature branch
3. Open a pull request with a clear description of changes

## License

Specify a license for this project if you intend to share it publicly (for example, MIT).

---

If you want, I can: add a `requirements.txt`, expand run instructions, or include Docker support. Which would you like next?
