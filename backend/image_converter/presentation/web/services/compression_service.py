import os
import shutil
import time
import traceback
from werkzeug.utils import secure_filename

from backend.image_converter.application.compress_images_usecase import CompressImagesUseCase
from backend.image_converter.application.dtos import (
    CompressionFormData,
    CompressionResponse,
    CompressRequest,
)
from backend.image_converter.core.enums.image_format import ImageFormat
from backend.image_converter.core.exceptions import ConversionError
from backend.image_converter.domain.pdf_presets import resolve_pdf_preset, resolve_pdf_scale
from backend.image_converter.domain.units import TargetSize, to_bytes


class CompressionService:
    def __init__(self, logger, use_case: CompressImagesUseCase, temp_folder_service):
        self.logger = logger
        self.use_case = use_case
        self.temp_folder_service = temp_folder_service

    def create_all_files_zip(self, folder_param: str) -> str:
        folder_path = self.temp_folder_service.get_validated_path(folder_param)

        if not folder_path:
            raise ConversionError("Invalid or unauthorized folder.")

        try:
            zip_name = f"converted_{int(time.time())}.zip"
            zip_path = os.path.join(self.temp_folder_service.temp_dir, zip_name)
            shutil.make_archive(zip_path[:-4], "zip", root_dir=folder_path)
            return zip_name
        except Exception:
            self.logger.log(f"ZIP creation error: {traceback.format_exc()}", "error")
            raise ConversionError("Failed to create archive.") from None

    def compress(self, form_data: CompressionFormData) -> CompressionResponse:
        fmt = form_data.image_format

        pdf_preset = form_data.pdf_preset
        pdf_scale = form_data.pdf_scale
        pdf_margin_mm = form_data.pdf_margin_mm
        pdf_paginate = form_data.pdf_paginate
        if fmt == ImageFormat.PDF:
            preset = resolve_pdf_preset(pdf_preset)
            pdf_scale = resolve_pdf_scale(pdf_scale)
            if preset.size is None:
                pdf_preset = None
                pdf_margin_mm = None
                pdf_paginate = False
        else:
            pdf_preset = None
            pdf_scale = "fit"
            pdf_margin_mm = None
            pdf_paginate = False

        src: str | None = None
        dst: str | None = None
        dest_ready = False

        try:
            src = self.temp_folder_service.create_temp_dir(prefix="source_")
            dst = self.temp_folder_service.create_temp_dir(prefix="converted_")

            self._save_uploaded_files(form_data.uploaded_files, src)

            target: TargetSize | None = None
            if form_data.target_size_kb:
                target = TargetSize(
                    bytes=to_bytes(float(form_data.target_size_kb), unit="KB", system="IEC")
                )

            req = CompressRequest(
                source_folder=src,
                dest_folder=dst,
                image_format=fmt,
                quality=form_data.quality,
                width=form_data.width,
                target_size=target,
                use_rembg=form_data.use_rembg,
                pdf_preset=pdf_preset,
                pdf_scale=pdf_scale,
                pdf_margin_mm=pdf_margin_mm,
                pdf_paginate=pdf_paginate,
            )

            result = self.use_case.execute(req)

            if not result.processed_files:
                raise ConversionError(f"Image processing failed: {'; '.join(result.errors)}")

            converted = [f for f in os.listdir(dst) if os.path.isfile(os.path.join(dst, f))]
            if not converted:
                raise ConversionError("No files were converted")

            dest_ready = True
            return CompressionResponse(
                converted_files=converted,
                dest_folder=dst,
                process_summary=result,
            )

        except ConversionError:
            raise
        except Exception:
            self.logger.log(
                f"Unexpected compression failure: {traceback.format_exc()}",
                "error",
            )
            raise ConversionError("Unexpected compression failure.") from None
        finally:
            if src:
                shutil.rmtree(src, ignore_errors=True)
            if dst and not dest_ready:
                shutil.rmtree(dst, ignore_errors=True)

    def _save_uploaded_files(self, files, folder: str) -> None:
        try:
            os.makedirs(folder, exist_ok=True)
            for file in files:
                name = secure_filename(file.filename or "upload")
                if not name:
                    continue
                path = os.path.join(folder, name)
                with open(path, "wb") as f:
                    while True:
                        chunk = file.stream.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
                self.logger.log(f"Saved file: {path}", "info")
        except Exception:
            self.logger.log(f"Failed saving upload: {traceback.format_exc()}", "error")
            raise ConversionError("Failed to save uploaded files.") from None
