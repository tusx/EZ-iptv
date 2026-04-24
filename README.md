# EZ-iptv

Single-user Flask IPTV boilerplate for M3U playlists and Xtream Codes sources.

## Stack

- Flask for page delivery and JSON APIs
- SQLite for local persistence
- Bootstrap 5.3.8 for the UI
- Vanilla JavaScript modules for client-side data loading
- `hls.js` for browser HLS playback
- Podman for both development and deployment
- Gunicorn for production serving inside the container

## Features

- Add, edit, delete, and sync M3U and Xtream sources
- Browse live TV, movies, and series from a Bootstrap-based UI
- Serve HTML shells from Flask while loading catalog data from `/api/*`
- Store synced source metadata, categories, and media items in SQLite
- Resolve direct playback URLs without proxying media through Flask

## Container Workflow

```bash
./setup.dev.sh
```

Then open `http://127.0.0.1:8091`.

For a deployment-style run with Gunicorn:

```bash
./setup.deploy.sh
```

Both scripts use Podman and keep SQLite in `instance/app.db` on the host.

## Project Layout

```text
app/
  routes/      Flask blueprints for pages and API endpoints
  services/    IPTV sync, parsing, validation, serialization, playback
  static/      Bootstrap, hls.js, custom CSS, and JS modules
  templates/   HTML shells for library, settings, and watch pages
Dockerfile     Shared image for dev and deploy flows
setup.dev.sh   Podman dev runner with bind-mounted source code
setup.deploy.sh Podman deploy runner with Gunicorn
instance/      SQLite database (`app.db`) at runtime
```
