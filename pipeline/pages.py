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

    def _find(self, run: tuple, at_or_after: int) -> Optional[int]:
        """The first place `run` occurs at or after `at_or_after`; failing that, anywhere (chunks can repeat boilerplate)."""
        places = self.runs.get(run)
        if not places:
            return None
        k = bisect_left(places, at_or_after)
        return places[k] if k < len(places) else places[0]

    def locate(self, chunk_text: str, cursor: int = 0) -> Optional[tuple]:
        """(first page, last page, word position of the chunk's start) or None when the chunk cannot be found.

        `cursor` is where the previous chunk of this document started, so repeated phrases resolve to the right copy."""
        words = tokens(chunk_text)
        if len(words) < RUN or not self.words:
            return None
        start = None
        for k in range(0, min(len(words) - RUN + 1, TRIES * STEP), STEP):
            found = self._find(tuple(words[k : k + RUN]), cursor)
            if found is not None:
                start = max(found - k, 0)
                break
        if start is None:
            return None
        end = min(start + len(words) - 1, len(self.words) - 1)
        for back in range(0, min(len(words) - RUN + 1, TRIES * STEP), STEP):
            k = len(words) - RUN - back
            found = self._find(tuple(words[k : k + RUN]), start)
            if found is not None and found >= start:
                end = min(found + RUN - 1 + back, len(self.words) - 1)
                break
        first, last = self.page_of[start], self.page_of[end]
        return (first, max(first, last), start)
