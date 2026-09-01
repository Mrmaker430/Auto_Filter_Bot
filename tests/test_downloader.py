import os
import pytest
from plugins.downloader import truncate_caption, MAX_CAPTION_LENGTH

def test_truncate_caption_short():
    text = "Short caption"
    assert truncate_caption(text) == text

def test_truncate_caption_exact():
    text = "A" * MAX_CAPTION_LENGTH
    assert truncate_caption(text) == text

def test_truncate_caption_long():
    text = "A" * (MAX_CAPTION_LENGTH + 50)
    truncated = truncate_caption(text)
    assert len(truncated) == MAX_CAPTION_LENGTH
    assert truncated.endswith("...")

def test_import_downloader():
    import plugins.downloader as downloader
    assert hasattr(downloader, "download_video")
    assert hasattr(downloader, "log_download_copy")
