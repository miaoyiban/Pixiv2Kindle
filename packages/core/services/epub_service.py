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

# Long novels are automatically split into multiple EPUB chapters
# for better navigation on Kindle (via TOC).
_BLOCKS_PER_CHAPTER = 50

# Chinese numeral lookup for chapter titles.
_CN_NUMERALS = [
    "", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
]


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

    @staticmethod
    def _split_into_chapters(
        blocks: list[BilingualBlock],
        max_per_chapter: int,
    ) -> list[list[BilingualBlock]]:
        """Partition *blocks* into chapter-sized groups."""
        if len(blocks) <= max_per_chapter:
            return [blocks]
        chapters: list[list[BilingualBlock]] = []
        for i in range(0, len(blocks), max_per_chapter):
            chapters.append(blocks[i : i + max_per_chapter])
        return chapters

    @staticmethod
    def _chapter_title(novel_title: str, index: int, total: int) -> str:
        """Return the display title for a chapter.

        Single-chapter books use the novel title as-is.
        Multi-chapter books append '— 第N部'.
        """
        if total <= 1:
            return novel_title
        if index < len(_CN_NUMERALS):
            label = f"第{_CN_NUMERALS[index]}部"
        else:
            label = f"第{index}部"
        return f"{novel_title} — {label}"

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

        # ── Chapters ──────────────────────────────────
        chapter_groups = self._split_into_chapters(blocks, _BLOCKS_PER_CHAPTER)
        template = self._jinja.get_template("chapter.xhtml.j2")
        epub_chapters: list[epub.EpubHtml] = []

        for idx, chapter_blocks in enumerate(chapter_groups, 1):
            ch_title = self._chapter_title(
                novel.title, idx, len(chapter_groups)
            )
            html = template.render(
                title=ch_title,
                author=novel.author_name if idx == 1 else None,
                language=language,
                blocks=chapter_blocks,
            )

            chapter = epub.EpubHtml(
                title=ch_title,
                file_name=f"chapter_{idx:02d}.xhtml",
                lang=language,
            )
            chapter.set_content(html.encode("utf-8"))
            chapter.add_item(style)
            book.add_item(chapter)
            epub_chapters.append(chapter)

        if len(chapter_groups) > 1:
            logger.info(
                "[epub] Long novel split into {} chapters ({} blocks total)",
                len(chapter_groups),
                len(blocks),
            )

        # ── Navigation ─────────────────────────────────
        book.toc = epub_chapters
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ["nav"] + epub_chapters

        # ── Write ──────────────────────────────────────
        out_dir = ensure_temp_dir(self._temp_dir)
        filename = f"[pixiv][novel_{novel.novel_id}]_{safe_title(novel.title)}.epub"
        out_path = out_dir / filename

        epub.write_epub(str(out_path), book, {})
        logger.info("EPUB written: {} ({} bytes)", out_path, out_path.stat().st_size)
        return str(out_path)
