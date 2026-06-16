from flask import Request

from backend.image_converter.application.dtos import CompressionFormData
from backend.image_converter.core.enums.image_format import ImageFormat
from backend.image_converter.core.exceptions import ConversionError
from backend.image_converter.core.internals.utilities import is_file_supported
from backend.image_converter.infrastructure.logger import Logger


def extract_form_data(request: Request, logger: Logger) -> CompressionFormData:
    uploaded_files = request.files.getlist("files[]")
    allowed_files = [f for f in uploaded_files if is_file_supported(f.filename)]
    unsupported_files = [f for f in uploaded_files if not is_file_supported(f.filename)]

    if unsupported_files:
        unsupported_names = ", ".join(f.filename for f in unsupported_files)
        raise ConversionError(f"Unsupported file types: {unsupported_names}")

    raw_format = request.form.get("format", ImageFormat.JPEG.value).lower()
    try:
        image_format = ImageFormat.from_string(raw_format)
    except ValueError as e:
        raise ConversionError(str(e)) from None

    return CompressionFormData(
        uploaded_files=tuple(allowed_files),
        quality=_parse_quality(request.form.get("quality", "85"), logger),
        width=_parse_width(request.form.get("width", ""), logger),
        image_format=image_format,
        target_size_kb=_parse_target_size_kb(request.form.get("target_size_kb", ""), logger),
        use_rembg=_parse_bool(request.form.get("use_rembg")),
        pdf_preset=request.form.get("pdf_preset", "").strip(),
        pdf_scale=request.form.get("pdf_scale", "").strip(),
        pdf_margin_mm=_parse_margin_mm(request.form.get("pdf_margin_mm", ""), logger),
        pdf_paginate=_parse_bool(request.form.get("pdf_paginate")),
    )


def _parse_quality(value: str, logger: Logger) -> int:
    try:
        q = int(value)
        if not (1 <= q <= 100):
            raise ValueError
        return q
    except ValueError:
        logger.log(f"Invalid quality '{value}'. Using default 85.", "warning")
        return 85


def _parse_width(value: str, logger: Logger) -> int | None:
    if not value.strip():
        return None
    try:
        w = int(value)
        if w <= 0:
            raise ValueError
        return w
    except ValueError:
        logger.log(f"Invalid width '{value}'. Not resizing.", "warning")
        return None


def _parse_target_size_kb(value: str, logger: Logger) -> int | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        kb = int(value)
        if kb <= 0:
            raise ValueError
        return kb
    except ValueError:
        logger.log(f"Invalid target_size_kb '{value}'. Ignoring.", "warning")
        return None


def _parse_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_margin_mm(value: str, logger: Logger) -> float:
    if value is None:
        return 10.0
    value = value.strip()
    if not value:
        return 10.0
    try:
        mm = float(value)
        if mm < 0:
            mm = 0.0
        if mm > 30:
            mm = 30.0
        return mm
    except ValueError:
        logger.log(f"Invalid pdf_margin_mm '{value}'. Using default 10.", "warning")
        return 10.0
