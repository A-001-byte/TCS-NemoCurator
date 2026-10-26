"""Find which PDF pages a chunk of text came from.

Chunking works on the whole document's words, so the page break is gone by then. To get it back, a chunk's first and last
few words are looked up in the text of each page: the same words, in the same order, on a known page. Cleaning and healing
change some words (a repaired split word, a removed page header), so a chunk is located by any of several short word
runs near its start and near its end, not by its exact first word. A chunk that cannot be found gets no page rather than a
wrong one.
"""

import re
from bisect import bisect_left
from collections import defaultdict
from typing import Optional

TOKEN_RE = re.compile(r"[a-z0-9]+")
RUN = 6  # words in the run that is looked up
STEP = 3  # how far to slide the run when it is not found
TRIES = 6  # how many runs to try at each end of the chunk
SLACK = 60  # extra words allowed between a chunk's start and its end, beyond twice its length


def tokens(text: str) -> list:
    """Lower-case letters and digits only: punctuation and spacing differences between pages and chunks do not matter."""
    return TOKEN_RE.findall(text.lower())


class PageIndex:
    """The words of a document's pages, with the page each word is on (pages are numbered from 1)."""

    def __init__(self, pages: list):
        self.words, self.page_of = [], []
        for number, text in enumerate(pages, start=1):
            found = tokens(text)
            self.words += found
            self.page_of += [number] * len(found)
        self.runs = defaultdict(list)
        for i in range(len(self.words) - RUN + 1):
            self.runs[tuple(self.words[i : i + RUN])].append(i)

    def _find(self, run: tuple, at_or_after: int, limit: Optional[int] = None) -> Optional[int]:
        """The first place `run` occurs at or after `at_or_after`.

        Without `limit`, failing that, anywhere (chunks can repeat boilerplate). With `limit`, only places up to `limit`:
        the end of a chunk must be near its start, or a phrase repeated on a later page would stretch the chunk across
        hundreds of pages."""
        places = self.runs.get(run)
        if not places:
            return None
        k = bisect_left(places, at_or_after)
        if limit is not None:
            return places[k] if k < len(places) and places[k] <= limit else None
        return places[k] if k < len(places) else places[0]

    def _find_start(self, words: list, cursor: int, limit: Optional[int]) -> Optional[int]:
        """Where the chunk starts, found by any of several short runs near its beginning, or None."""
        for k in range(0, min(len(words) - RUN + 1, TRIES * STEP), STEP):
            found = self._find(tuple(words[k : k + RUN]), cursor, limit)
            if found is not None:
                return max(found - k, 0)
        return None

    def locate(self, chunk_text: str, cursor: int = 0) -> Optional[tuple]:
        """(first page, last page, word position of the chunk's start) or None when the chunk cannot be found.

        `cursor` is where the previous chunk of this document started, so repeated phrases resolve to the right copy."""
        words = tokens(chunk_text)
        if len(words) < RUN or not self.words:
            return None
        # Chunks are consecutive windows, so this one starts shortly after the previous one: look near the cursor first,
        # and only then anywhere in the document (a wrong far-away match would drag every later chunk with it).
        near = cursor + 4 * len(words) + SLACK
        start = self._find_start(words, cursor, near)
        if start is None:
            start = self._find_start(words, cursor, None)
        if start is None:
            return None
        end = min(start + len(words) - 1, len(self.words) - 1)
        # Cleaning and healing remove or add a few words, so the chunk's end is near start + its length, not exactly there.
        limit = start + 2 * len(words) + SLACK
        for back in range(0, min(len(words) - RUN + 1, TRIES * STEP), STEP):
            k = len(words) - RUN - back
            found = self._find(tuple(words[k : k + RUN]), start, limit)
            if found is not None:
                end = min(found + RUN - 1 + back, len(self.words) - 1)
                break
        first, last = self.page_of[start], self.page_of[end]
        return (first, max(first, last), start)
