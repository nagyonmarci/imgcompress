import sys
import pytest
from backend.image_converter.core.exceptions import ConversionError
from backend.image_converter.infrastructure.logger import Logger
from backend.image_converter.core.enums.image_format import ImageFormat
from unittest.mock import MagicMock

def test_rembg_is_lazy_loaded(monkeypatch):
    from backend.image_converter.core import converters as converters_mod

    assert not hasattr(converters_mod, "new_session")
    monkeypatch.delitem(sys.modules, "rembg", raising=False)
    assert "rembg" not in sys.modules

    assert "rembg" not in sys.modules
    monkeypatch.setitem(sys.modules, "rembg", MagicMock())

    converters_mod._get_background_removal_session("u2net")
    assert "rembg" in sys.modules
    
def test_pdfium_is_lazy_loaded(monkeypatch):
    from backend.image_converter.infrastructure.pdf_page_extractor import PdfPageExtractor
    import backend.image_converter.infrastructure.pdf_page_extractor as pdf_mod
    assert not hasattr(pdf_mod, "pdfium")
    
    monkeypatch.delitem(sys.modules, "pypdfium2", raising=False)
    
    extractor = PdfPageExtractor()
    assert "pypdfium2" not in sys.modules
    monkeypatch.setitem(sys.modules, "pypdfium2", MagicMock())
    with pytest.raises(ConversionError):
        extractor.rasterize_pages(b"data")

    assert "pypdfium2" in sys.modules

def test_psd_tools_is_lazy_loaded(monkeypatch):
    from backend.image_converter.infrastructure.psd_renderer import PsdRenderer
    import backend.image_converter.infrastructure.psd_renderer as psd_mod
    assert not hasattr(psd_mod, "PSDImage")
    
    monkeypatch.delitem(sys.modules, "psd_tools", raising=False)
    
    renderer = PsdRenderer(Logger(False))
    assert "psd_tools" not in sys.modules
    
    monkeypatch.setitem(sys.modules, "psd_tools", MagicMock())
    renderer.render("test.psd", b"data")
    
    assert "psd_tools" in sys.modules
