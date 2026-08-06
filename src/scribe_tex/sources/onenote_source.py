"""OneNoteSource: future Graph-backed page-image fetcher (not implemented).

The Microsoft Graph OneNote API cannot return handwritten ink as text or
strokes, but CAN return page images via the page /preview endpoint and the
img data-fullres-src resource endpoint
(GET /me/onenote/resources/{id}/$value). A future implementation would
authenticate (delegated OAuth2, scope Notes.Read), resolve a page by
course/date, download those PNGs, and return them here so the rest of the
pipeline is unchanged.
"""
from __future__ import annotations
from pathlib import Path

from .base import register


class OneNoteSource:
    def fetch_pages(self, ref: str) -> list[Path]:
        raise NotImplementedError(
            "OneNoteSource is a future seam; use source='file' for now."
        )


register("onenote", OneNoteSource)
