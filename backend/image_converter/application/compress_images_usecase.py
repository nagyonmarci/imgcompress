from typing import Iterable

from PIL import Image
from io import BytesIO

from .dtos import CompressRequest, CompressResult, PageProcessingResult
from backend.image_converter.domain.size_targeting import find_best_quality_under_target
from backend.image_converter.domain.units import TargetSize
from backend.image_converter.core.enums.image_format import ImageFormat
from backend.image_converter.core.converters import convert_and_save, get_encoder
from backend.image_converter.core.exceptions import ConversionError
from backend.image_converter.application.file_payload_expander import FilePayloadExpander
from backend.image_converter.domain.pdf_presets import resolve_pdf_preset, resolve_pdf_scale, PdfPreset
from backend.image_converter.infrastructure.local_storage import FileItem

class CompressImagesUseCase:
    def __init__(
        self,
        logger,
        resizer,
        storage,
        payload_expander: FilePayloadExpander,
    ):
        self.logger = logger
        self.resizer = resizer
        self.storage = storage
        self.payload_expander = payload_expander

    def execute(self, req: CompressRequest) -> CompressResult:
        return self.execute_items(self.storage.iter_files(req.source_folder), req)

    def execute_items(self, items: Iterable[FileItem], req: CompressRequest) -> CompressResult:
        """Like execute(), but takes an explicit iterable of FileItem instead of
        listing req.source_folder via storage (used by callers that need custom
        file selection, e.g. the CLI's single-file/filtered-directory modes)."""
        processed, errors, page_results = [], [], []
        new_ext = req.image_format.get_file_extension()
        pdf_preset: PdfPreset | None = None
        pdf_scale = "fit"
        pdf_margin_mm = None
        pdf_paginate = False
        if req.image_format == ImageFormat.PDF and req.pdf_preset:
            try:
                preset = resolve_pdf_preset(req.pdf_preset)
                if preset.size is not None:
                    pdf_preset = preset
                    pdf_margin_mm = req.pdf_margin_mm
                    pdf_paginate = req.pdf_paginate

                pdf_scale = resolve_pdf_scale(req.pdf_scale)
            except ConversionError as e:
                return CompressResult(processed_files=[], errors=[str(e)])

        for item in items:
            try:
                original = self.storage.read_bytes(item.path)
                page_payloads = self.payload_expander.expand(item.name, original)
            except Exception as e:
                errors.append(f"{item.name}: {e}")
                continue

            # page_payloads is now an iterable (generator for PDFs) to save memory
            for payload in page_payloads:
                dest_name = self._build_dest_name(item.stem, new_ext, payload.page_index)
                dest_path = self.storage.build_dest_path(req.dest_folder, dest_name)
                page_label = payload.label
                original_width = None
                new_width = None
                try:
                    with Image.open(BytesIO(payload.data)) as temp_img:
                        original_width, _ = temp_img.size
                    new_width = original_width

                    if pdf_preset and req.image_format == ImageFormat.PDF:
                        data = payload.data
                    else:
                        data = self._resize_if_needed(payload.data, req.width)
                        if req.width and req.width > 0:
                            with Image.open(BytesIO(data)) as resized_img:
                                new_width, _ = resized_img.size

                    if req.target_size and req.image_format in [ImageFormat.JPEG, ImageFormat.AVIF]:
                        target = TargetSize(req.target_size.bytes)
                        target_bytes = target.soft_limit

                        def encoder(q: int, d: bytes) -> bytes:
                            return get_encoder(req.image_format, q)(d)

                        q, out, size = find_best_quality_under_target(encoder, data, target_bytes)

                        if not target.within_tolerance(len(out)):
                            self.logger.log(
                                f"{page_label}: best={q} still {len(out)} bytes over tolerance for {target.bytes}.",
                                "warn"
                            )

                        self.storage.write_bytes(dest_path, out)
                        processed.append(dest_name)
                        page_results.append(self._build_page_result(
                            dest_name, item.path, dest_path, original_width, new_width, True, None
                        ))
                    else:
                        result = convert_and_save(
                            req.image_format,
                            data,
                            source_path=item.path,
                            dest_path=dest_path,
                            quality=req.quality,
                            logger=self.logger,
                            use_rembg=req.use_rembg,
                            pdf_preset=pdf_preset,
                            pdf_scale=pdf_scale,
                            pdf_margin_mm=pdf_margin_mm,
                            pdf_paginate=pdf_paginate,
                        )
                        processed.append(dest_name)
                        page_results.append(self._build_page_result(
                            dest_name, item.path, result.destination, original_width, new_width, True, None
                        ))
                except Exception as e:
                    errors.append(f"{page_label}: {e}")
                    page_results.append(self._build_page_result(
                        dest_name, item.path, dest_path, None, None, False, str(e)
                    ))

        return CompressResult(processed_files=processed, errors=errors, page_results=page_results)

    @staticmethod
    def _build_page_result(
        file: str,
        source: str,
        destination: str,
        original_width: int | None,
        resized_width: int | None,
        is_successful: bool,
        error: str | None,
    ) -> PageProcessingResult:
        return PageProcessingResult(
            file=file,
            source=source,
            destination=destination,
            original_width=original_width,
            resized_width=resized_width,
            is_successful=is_successful,
            error=error,
        )

    def _resize_if_needed(self, data: bytes, width: int | None) -> bytes:
        if width and width > 0:
            return self.resizer.resize_image(data, width)
        return data


    @staticmethod
    def _build_dest_name(stem: str, extension: str, page_index: int | None) -> str:
        if page_index is None:
            return stem + extension
        return f"{stem}_page-{page_index}{extension}"
