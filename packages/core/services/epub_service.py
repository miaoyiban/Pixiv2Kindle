"""EPUB generation service.

Uses *ebooklib* to create a valid .epub file from novel content
and (optionally) bilingual blocks.

Spec references: §13.1 – §13.6.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

from ebooklib import epub
from jinja2 import Environment, FileSystemLoader
from loguru import logger

from packages.core.domain.models import BilingualBlock, PixivNovel
from packages.core.exceptions import EpubBuildError
from packages.core.utils.file_utils import ensure_temp_dir
from packages.core.utils.sanitizer import safe_title

# Resolve the template directory once.
_TEMPLATE_DIR = str(Path(__file__).resolve().parent.parent / "templates")


class EpubService:
    """Build EPUB files from :class:`PixivNovel` and blocks."""

    def __init__(self, *, temp_dir: str = "./tmp") -> None:
        self._temp_dir = temp_dir
        self._jinja = Environment(
            loader=FileSystemLoader(_TEMPLATE_DIR),
            autoescape=True,
        )

    async def build(
        self,
        novel: PixivNovel,
        blocks: list[BilingualBlock],
    ) -> str:
        """Generate an EPUB and return the file path.

        The method is technically synchronous (ebooklib is sync) but
        declared async for protocol consistency.  The caller may wrap
        with ``asyncio.to_thread`` if needed for CPU-heavy books.
        """
        try:
            return self._build_sync(novel, blocks)
        except EpubBuildError:
            raise
        except Exception as exc:
            raise EpubBuildError(f"EPUB build failed: {exc}") from exc

    # ── Internal ───────────────────────────────────────

    def _build_sync(
        self,
        novel: PixivNovel,
        blocks: list[BilingualBlock],
    ) -> str:
        has_translation = any(b.translated for b in blocks)
        language = "ja"

        book = epub.EpubBook()
        book.set_identifier(f"pixiv-novel-{novel.novel_id}")
        book.set_title(novel.title)
        book.set_language(language)
        book.add_author(novel.author_name)

        # ── CSS ────────────────────────────────────────
        css_path = Path(_TEMPLATE_DIR) / "styles.css"
        css_content = css_path.read_text(encoding="utf-8")
        style = epub.EpubItem(
            uid="style",
            file_name="styles.css",
            media_type="text/css",
            content=css_content.encode("utf-8"),
        )
        book.add_item(style)

        # ── Chapter ────────────────────────────────────
        template = self._jinja.get_template("chapter.xhtml.j2")
        html = template.render(
            title=novel.title,
            author=novel.author_name,
            language=language,
            blocks=blocks,
        )

        chapter = epub.EpubHtml(
            title=novel.title,
            file_name="chapter_01.xhtml",
            lang=language,
        )
        chapter.set_content(html.encode("utf-8"))
        chapter.add_item(style)
        book.add_item(chapter)

        # ── Navigation ─────────────────────────────────
        book.toc = [chapter]
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ["nav", chapter]

        # ── Write ──────────────────────────────────────
        out_dir = ensure_temp_dir(self._temp_dir)
        filename = f"[pixiv][novel_{novel.novel_id}]_{safe_title(novel.title)}.epub"
        out_path = out_dir / filename

        epub.write_epub(str(out_path), book, {})
        logger.info("EPUB written: {} ({} bytes)", out_path, out_path.stat().st_size)
        return str(out_path)
