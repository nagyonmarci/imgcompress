from io import BytesIO

import pytest
from PIL import Image

from backend.image_converter.config import settings
from backend.image_converter.core.exceptions import ConversionError
from backend.image_converter.core.internals.utilities import supported_extensions
from backend.image_converter.infrastructure.pdf_page_extractor import PdfPageExtractor
from backend.image_converter.application.file_payload_expander import FilePayloadExpander

SAMPLE_PDF = "tests/sample-images/imgcompress_screenshot.pdf"


def test_When_LoadingSupportedExtensions_Expect_AllExtraFormatsIncluded():
    for extra in settings.get().formats.custom_pipeline_extensions:
        assert extra in supported_extensions


def test_When_PdfPageExtractorProcessesSample_Expect_PageRendered():
    extractor = PdfPageExtractor(dpi=144)
    with open(SAMPLE_PDF, "rb") as f:
        data = f.read()

    pages = list(extractor.rasterize_pages(data, "imgcompress_screenshot.pdf"))
    assert len(pages) == 1
    page_bytes = pages[0]
    with Image.open(BytesIO(page_bytes)) as img:
        assert img.width > 0
        assert img.height > 0


def test_When_PdfiumRaisesRuntimeError_Expect_ExtractorFailure(monkeypatch):
    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    import pypdfium2
    monkeypatch.setattr(pypdfium2, "PdfDocument", boom)

    class _RecordingLogger:
        def __init__(self):
            self.messages = []

        def log(self, message, level):
            self.messages.append((message, level))

    logger = _RecordingLogger()
    extractor = PdfPageExtractor(logger=logger)

    with pytest.raises(ConversionError, match="PDF could not be rendered."):
        extractor.rasterize_pages(b"", "broken.pdf")

    assert any(
        "boom" in message and "broken.pdf" in message
        for message, _ in logger.messages
    )


class DummyRenderer:
    def render(self, source_name, data):
        return data


def test_When_ExpandingPdfPayload_Expect_PageMetadataCreated(monkeypatch):
    fake_pages = [b"a", b"b"]

    class DummyExtractor:
        def rasterize_pages(self, data, source_hint):
            return fake_pages

    expander = FilePayloadExpander(DummyExtractor(), DummyRenderer())
    payloads = list(expander.expand("demo.pdf", b"bytes"))
    assert len(payloads) == 2
    assert payloads[0].label == "demo.pdf (page 1)"
    assert payloads[0].page_index == 1


def test_When_ExtractorFails_Expect_PayloadExpansionFailure(monkeypatch):
    class DummyExtractor:
        def rasterize_pages(self, data, source_hint):
            raise ConversionError("invalid pdf")

    expander = FilePayloadExpander(DummyExtractor(), DummyRenderer())
    with pytest.raises(ConversionError, match="invalid pdf"):
        expander.expand("demo.pdf", b"bytes")


def test_When_FileIsNonPdf_Expect_ExpanderReturnsOriginalPayload():
    expander = FilePayloadExpander(PdfPageExtractor(), DummyRenderer())
    payloads = expander.expand("image.png", b"bytes")
    assert len(payloads) == 1
    assert payloads[0].label == "image.png"
    assert payloads[0].page_index is None
