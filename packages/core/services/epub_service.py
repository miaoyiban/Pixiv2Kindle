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
from packages.core.utils.pixiv_layout import render_ruby, strip_ruby
from packages.core.utils.sanitizer import safe_title

# Resolve the template directory once.
_TEMPLATE_DIR = str(Path(__file__).resolve().parent.parent / "templates")


def _split_pages(blocks: list[BilingualBlock]) -> list[list[BilingualBlock]]:
    """Group blocks into pages, starting a new page at each page/chapter item."""
    pages: list[list[BilingualBlock]] = [[]]
    for b in blocks:
        if b.kind in ("page", "chapter") and pages[-1]:
            pages.append([])
        if b.kind != "page":
            pages[-1].append(b)
    return pages


class EpubService:
    """Build EPUB files from :class:`PixivNovel` and blocks."""

    def __init__(self, *, temp_dir: str = "./tmp") -> None:
        self._temp_dir = temp_dir
        self._jinja = Environment(
            loader=FileSystemLoader(_TEMPLATE_DIR),
            autoescape=True,
        )
        # Escapes HTML, renders pixiv ruby, and turns \n into <br/>.
        self._jinja.filters["nl2br"] = render_ruby

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

        # ── Pages ──────────────────────────────────────
        # Each [newpage] / [chapter:] starts a new XHTML file: Kindle always
        # breaks the page between files, while CSS page-break is unreliable.
        template = self._jinja.get_template("chapter.xhtml.j2")
        docs: list[epub.EpubHtml] = []
        toc: list[epub.EpubHtml] = []
        for n, page in enumerate(_split_pages(blocks), start=1):
            chapter_block = next((b for b in page if b.kind == "chapter"), None)
            heading = (
                strip_ruby(chapter_block.translated or chapter_block.source)
                if chapter_block
                else novel.title
            )
            html = template.render(
                title=novel.title,
                author=novel.author_name,
                language=language,
                blocks=page,
                first_page=(n == 1),
            )
            doc = epub.EpubHtml(
                title=heading,
                file_name=f"page_{n:03d}.xhtml",
                lang=language,
            )
            doc.set_content(html.encode("utf-8"))
            doc.add_item(style)
            book.add_item(doc)
            docs.append(doc)
            if n == 1 or chapter_block:
                toc.append(doc)

        # ── Navigation ─────────────────────────────────
        book.toc = toc
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ["nav", *docs]

        # ── Write ──────────────────────────────────────
        out_dir = ensure_temp_dir(self._temp_dir)
        filename = f"[pixiv][novel_{novel.novel_id}]_{safe_title(novel.title)}.epub"
        out_path = out_dir / filename

        epub.write_epub(str(out_path), book, {})
        logger.info("EPUB written: {} ({} bytes)", out_path, out_path.stat().st_size)
        return str(out_path)
