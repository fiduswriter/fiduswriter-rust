**This project is not currently under development. Instead, rust has been incorporated into the main Fidus Writer backend (most notably with prosemirror-rs).**

# Fidus Writer Rust Server Connector

This Django app provides REST API endpoints for a companion Rust WebSocket server.
The Rust server handles real-time collaboration (diffs, selections, chat) while
Django remains responsible for persistence, authentication, and access control.

## Architecture

```
Browser  <──WebSocket──>  Rust WS Server  <──REST──>  Django (this app)
                              │
                              └── In-memory docs, diff fan-out, version mgmt
```

Django endpoints are called by the Rust server (not the browser directly) for:

- **Auth / access rights** – `POST /api/rust/check_access/`
- **Session init** – `POST /api/rust/init_session/` (returns document content)
- **Document save** – `POST /api/rust/save_doc/`
- **Image metadata** – `POST /api/rust/update_images/`

## Enabling the plugin

Add the app to your `configuration.py`:

```python
INSTALLED_APPS += ["rust"]
```

If you prefer the endpoints under `/api/document/` instead of `/api/rust/`,
import the views in `document/urls.py` or wire them via `EXTRA_URLS` in
`configuration.py`.

## Shared helpers

All database operations used by both the legacy WebSocket consumer and these
new REST views live in `document/helpers/document_store.py` so that logic is
not duplicated between the Python and Rust collaboration paths.
