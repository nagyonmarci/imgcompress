from __future__ import annotations

from functools import cache
import importlib.util
import socket
from pathlib import Path

from PIL import Image

from backend.image_converter.config import settings


@cache
def load_supported_formats() -> tuple[str, ...]:
    pillow_formats = {
        ext.lower()
        for ext, fmt in Image.registered_extensions().items()
        if fmt.upper() in Image.OPEN
    }

    supported = set(pillow_formats)
    supported.update(settings.get().formats.custom_pipeline_extensions)

    if importlib.util.find_spec("pillow_heif") is not None:
        supported.update({".heic", ".heif"})

    return tuple(sorted(supported))


def is_file_supported(file_path: str | Path) -> bool:
    return Path(file_path).suffix.lower() in load_supported_formats()


supported_extensions = load_supported_formats()


def has_internet() -> bool:
    try:
        socket.create_connection(("1.1.1.1", 53), timeout=1).close()
        return True
    except OSError:
        return False