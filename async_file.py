"""Small async context manager for opening and closing local binary files off-loop."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import BinaryIO


@asynccontextmanager
async def open_binary_async(path: str | Path) -> AsyncIterator[BinaryIO]:
    """Open a local file in a worker thread and close it without blocking the loop."""
    file = await asyncio.to_thread(open, path, "rb")
    try:
        yield file
    finally:
        await asyncio.to_thread(file.close)
