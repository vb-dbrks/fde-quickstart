"""Serve the built React app (frontend/ builds into backend/static) with client-side routing support."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles

NOT_BUILT = "The frontend has not been built. Run `make build`, or use `make dev` and open the Vite dev server."


def mount_spa(app: FastAPI, static_dir: Path) -> None:
    """Register last: everything outside /api falls through to index.html."""
    root = static_dir.resolve()
    assets = root / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> Response:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
        requested = (root / path).resolve()
        if path and requested.is_file() and requested.is_relative_to(root):
            return FileResponse(requested)
        index = root / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-cache"})
        return PlainTextResponse(NOT_BUILT, status_code=status.HTTP_404_NOT_FOUND)
