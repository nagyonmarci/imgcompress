from dataclasses import dataclass
from typing import Iterable

from backend.image_converter.infrastructure.pdf_page_extractor import PdfPageExtractor
from backend.image_converter.infrastructure.psd_renderer import PsdRenderer


@dataclass
class PagePayload:
    data: bytes
    page_index: int | None
    label: str


class FilePayloadExpander:
    """
    Normalizes supported upload containers into raster payloads for conversion.
    """

    def __init__(self, pdf_extractor: PdfPageExtractor, psd_renderer: PsdRenderer):
        self.pdf_extractor = pdf_extractor
        self.psd_renderer = psd_renderer

    def expand(self, source_name: str, data: bytes) -> Iterable[PagePayload]:
        if self._is_pdf(source_name):
            return self._expand_pdf_payloads(source_name, data)
        if self._is_psd(source_name):
            return self._expand_psd_payload(source_name, data)
        return [self._build_single_payload(source_name, data)]

    @staticmethod
    def _is_pdf(source_name: str) -> bool:
        return source_name.lower().endswith(".pdf")

    @staticmethod
    def _is_psd(source_name: str) -> bool:
        return source_name.lower().endswith(".psd")

    def _expand_pdf_payloads(self, source_name: str, data: bytes) -> Iterable[PagePayload]:
        pdf_pages = self.pdf_extractor.rasterize_pages(data, source_name)

        def payload_generator():
            for index, page in enumerate(pdf_pages, start=1):
                yield PagePayload(
                    data=page,
                    page_index=index,
                    label=f"{source_name} (page {index})",
                )

        return payload_generator()

    def _expand_psd_payload(self, source_name: str, data: bytes) -> Iterable[PagePayload]:
        rendered = self.psd_renderer.render(source_name, data)

        payload = PagePayload(
            data=rendered,
            page_index=None,
            label=source_name,
        )
        return [payload]

    @staticmethod
    def _build_single_payload(source_name: str, data: bytes) -> PagePayload:
        return PagePayload(data=data, page_index=None, label=source_name)
