"""Format-specific image encoders, plus a small dispatch table used in place
of the old IImageConverter/BaseImageConverter/ImageConverterFactory class
hierarchy. Each `encode_*` function takes raw image bytes and returns
encoded bytes; `convert_and_save` wraps an encoder to write to disk and
return ConversionDetails, matching the previous converter.convert()
contract.
"""
import math
import os
import traceback
from io import BytesIO
from tempfile import NamedTemporaryFile

from PIL import Image, ImageOps
from fpdf import FPDF

from backend.image_converter.application.dtos import ConversionDetails
from backend.image_converter.core.enums.image_format import ImageFormat
from backend.image_converter.core.exceptions import ConversionError
from backend.image_converter.core.internals.rembg_config import load_rembg_model_name
from backend.image_converter.domain.pdf_presets import PdfPreset
from backend.image_converter.infrastructure.logger import Logger


def _normalize_for_jpeg(img: Image.Image) -> Image.Image:
    """
    Ensure deterministic, JPEG-safe pixel data:
    - apply EXIF orientation
    - flatten alpha onto white
    - convert to RGB (handles P/CMYK/L/etc.)
    """
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    if img.mode in ("RGBA", "LA"):
        # composite over white
        background = Image.new("RGB", img.size, (255, 255, 255))
        alpha = img.getchannel("A")
        background.paste(img.convert("RGB"), mask=alpha)
        img = background
    elif img.mode not in ("RGB",):
        # Convert everything else to RGB
        img = img.convert("RGB")

    return img


def encode_jpeg(image_data: bytes, quality: int) -> bytes:
    with Image.open(BytesIO(image_data)) as img:
        img = _normalize_for_jpeg(img)
        out = BytesIO()
        img.save(
            out,
            format="JPEG",
            quality=int(quality),
            optimize=True,
            progressive=True,
            subsampling="4:2:0",
        )
        return out.getvalue()


def encode_png(image_data: bytes) -> bytes:
    with Image.open(BytesIO(image_data)) as img:
        buffer = BytesIO()
        img.save(buffer, "PNG")
        return buffer.getvalue()


def encode_ico(image_data: bytes) -> bytes:
    """
    Converts raw image bytes to a valid ICO file, preserving alpha,
    but includes *only* one resolution.

    The caller is expected to resize the image_data to the desired
    dimension before calling encode_ico.
    """
    with Image.open(BytesIO(image_data)) as img:
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        buffer = BytesIO()
        img.save(buffer, format="ICO")
        return buffer.getvalue()


def _encode_to_avif(image_data: bytes, quality: int) -> bytes:
    with Image.open(BytesIO(image_data)) as img:
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA")
        buffer = BytesIO()
        img.save(buffer, format="AVIF", quality=quality)
        return buffer.getvalue()


def encode_avif(image_data: bytes, quality: int) -> bytes:
    return _encode_to_avif(image_data, quality)


def _strip_metadata_and_normalize(image_data: bytes, output_format: str) -> bytes:
    with Image.open(BytesIO(image_data)) as image:
        output_buffer = BytesIO()
        image.save(output_buffer, format=output_format)
        return output_buffer.getvalue()


_rembg_sessions: dict[str, object] = {}


def _get_background_removal_session(model_name: str):
    if model_name not in _rembg_sessions:
        from rembg import new_session
        _rembg_sessions[model_name] = new_session(model_name)
    return _rembg_sessions[model_name]


def _remove_background(image_data: bytes, model_name: str | None) -> bytes:
    from rembg import remove
    resolved_model_name = model_name or load_rembg_model_name()
    return remove(
        image_data,
        session=_get_background_removal_session(resolved_model_name),
        post_process_mask=True,
        alpha_matting=False,
    )


def encode_rembg_png(image_data: bytes, model_name: str | None = None) -> bytes:
    raw_output = _remove_background(image_data, model_name)
    return _strip_metadata_and_normalize(raw_output, output_format="PNG")


def encode_rembg_avif(image_data: bytes, quality: int, model_name: str | None = None) -> bytes:
    raw_output = _remove_background(image_data, model_name)
    return _encode_to_avif(raw_output, quality)


def _normalize_for_pdf(img: Image.Image) -> Image.Image:
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass

    if img.mode in ("RGBA", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        alpha = img.getchannel("A")
        background.paste(img.convert("RGB"), mask=alpha)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    return img


def _mm_to_pt(mm: float) -> float:
    return mm * 72.0 / 25.4


def _crop_to_aspect(img: Image.Image, target_ratio: float) -> Image.Image:
    img_ratio = img.width / img.height
    if img_ratio > target_ratio:
        new_width = int(round(img.height * target_ratio))
        left = max(0, (img.width - new_width) // 2)
        return img.crop((left, 0, left + new_width, img.height))
    new_height = int(round(img.width / target_ratio))
    top = max(0, (img.height - new_height) // 2)
    return img.crop((0, top, img.width, top + new_height))


def _output_pdf(pdf: FPDF) -> bytes:
    output = pdf.output()
    if isinstance(output, (bytes, bytearray)):
        return bytes(output)
    return output.encode("latin-1")


def _render_pdf(
    pdf: FPDF,
    img: Image.Image,
    x: float,
    y: float,
    w: float,
    h: float,
    return_bytes: bool = True,
) -> bytes:
    tmp_path = None
    try:
        with NamedTemporaryFile(delete=False, suffix=".png") as tmp:
            tmp_path = tmp.name
            img.save(tmp, format="PNG")
        pdf.image(tmp_path, x=x, y=y, w=w, h=h)
        if return_bytes:
            return _output_pdf(pdf)
        return b""
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def _encode_pdf_original(img: Image.Image) -> bytes:
    page_w, page_h = img.size
    pdf = FPDF(unit="pt", format=(page_w, page_h))
    pdf.add_page()
    return _render_pdf(pdf, img, x=0, y=0, w=page_w, h=page_h)


def _encode_pdf_paginated(
    img: Image.Image,
    page_w: float,
    page_h: float,
    inner_w: float,
    inner_h: float,
    margin_pt: float,
) -> bytes:
    scale = inner_w / img.width
    if scale <= 0:
        raise ValueError("Invalid scale for PDF pagination.")
    slice_height_px = inner_h / scale
    if slice_height_px <= 0:
        raise ValueError("Invalid slice height for PDF pagination.")

    page_count = max(1, math.ceil(img.height / slice_height_px))
    pdf = FPDF(unit="pt", format=(page_w, page_h))

    for page_index in range(page_count):
        top_px = page_index * slice_height_px
        bottom_px = min((page_index + 1) * slice_height_px, img.height)
        top_i = int(round(top_px))
        bottom_i = int(round(bottom_px))
        if bottom_i <= top_i:
            continue
        slice_img = img.crop((0, top_i, img.width, bottom_i))
        target_h = (bottom_px - top_px) * scale

        pdf.add_page()
        _render_pdf(
            pdf,
            slice_img,
            x=margin_pt,
            y=margin_pt,
            w=inner_w,
            h=target_h,
            return_bytes=False,
        )

    return _output_pdf(pdf)


def _encode_pdf_with_preset(
    img: Image.Image,
    pdf_preset: PdfPreset,
    pdf_scale: str,
    pdf_margin_mm: float | None,
    pdf_paginate: bool,
) -> bytes:
    page_w, page_h = pdf_preset.size
    if pdf_preset.auto_rotate:
        img_is_landscape = img.width > img.height
        page_is_landscape = page_w > page_h
        if img_is_landscape != page_is_landscape:
            page_w, page_h = page_h, page_w

    margin_mm = pdf_margin_mm if pdf_margin_mm is not None else pdf_preset.margin_mm
    margin_pt = _mm_to_pt(margin_mm)
    inner_w = page_w - (2 * margin_pt)
    inner_h = page_h - (2 * margin_pt)
    if inner_w <= 0 or inner_h <= 0:
        raise ValueError("PDF margin is too large for the page size.")

    if pdf_paginate:
        return _encode_pdf_paginated(img, page_w, page_h, inner_w, inner_h, margin_pt)

    if pdf_scale == "fill":
        img = _crop_to_aspect(img, inner_w / inner_h)
        target_w = inner_w
        target_h = inner_h
        offset_x = margin_pt
        offset_y = margin_pt
    else:
        scale = min(inner_w / img.width, inner_h / img.height)
        target_w = img.width * scale
        target_h = img.height * scale
        offset_x = margin_pt + (inner_w - target_w) / 2
        offset_y = margin_pt + (inner_h - target_h) / 2

    pdf = FPDF(unit="pt", format=(page_w, page_h))
    pdf.add_page()
    return _render_pdf(pdf, img, x=offset_x, y=offset_y, w=target_w, h=target_h)


def encode_pdf(
    image_data: bytes,
    pdf_preset: PdfPreset | None = None,
    pdf_scale: str = "fit",
    pdf_margin_mm: float | None = None,
    pdf_paginate: bool = False,
) -> bytes:
    with Image.open(BytesIO(image_data)) as img:
        img = _normalize_for_pdf(img)
        if pdf_preset and pdf_preset.size:
            return _encode_pdf_with_preset(img, pdf_preset, pdf_scale, pdf_margin_mm, pdf_paginate)
        return _encode_pdf_original(img)


def get_encoder(
    image_format: ImageFormat,
    quality: int,
    use_rembg: bool = False,
    pdf_preset: PdfPreset | None = None,
    pdf_scale: str = "fit",
    pdf_margin_mm: float | None = None,
    pdf_paginate: bool = False,
):
    """Return a zero/one-arg callable `encode(image_data: bytes) -> bytes` for
    the given format, mirroring what ImageConverterFactory.create_converter(...)
    .encode_to_bytes used to provide."""
    match (image_format, use_rembg):
        case (ImageFormat.JPEG, _):
            return lambda data: encode_jpeg(data, quality)
        case (ImageFormat.PNG, True):
            return lambda data: encode_rembg_png(data)
        case (ImageFormat.PNG, False):
            return lambda data: encode_png(data)
        case (ImageFormat.ICO, _):
            return lambda data: encode_ico(data)
        case (ImageFormat.AVIF, True):
            return lambda data: encode_rembg_avif(data, quality)
        case (ImageFormat.AVIF, False):
            return lambda data: encode_avif(data, quality)
        case (ImageFormat.PDF, _):
            return lambda data: encode_pdf(
                data,
                pdf_preset=pdf_preset,
                pdf_scale=pdf_scale,
                pdf_margin_mm=pdf_margin_mm,
                pdf_paginate=pdf_paginate,
            )
        case _:
            raise ConversionError(f"Unsupported output format: {image_format.value}")


def convert_and_save(
    image_format: ImageFormat,
    image_data: bytes,
    source_path: str,
    dest_path: str,
    quality: int,
    logger: Logger,
    use_rembg: bool = False,
    pdf_preset: PdfPreset | None = None,
    pdf_scale: str = "fit",
    pdf_margin_mm: float | None = None,
    pdf_paginate: bool = False,
) -> ConversionDetails:
    """Encode image_data for image_format and write it to dest_path,
    mirroring the previous BaseImageConverter.convert() contract."""
    try:
        encoder = get_encoder(
            image_format,
            quality,
            use_rembg=use_rembg,
            pdf_preset=pdf_preset,
            pdf_scale=pdf_scale,
            pdf_margin_mm=pdf_margin_mm,
            pdf_paginate=pdf_paginate,
        )
        converted_data = encoder(image_data)
        with open(dest_path, "wb") as f:
            f.write(converted_data)

        logger.log(f"Successfully converted and saved to {dest_path}", "debug")

        return ConversionDetails(
            source=source_path,
            destination=dest_path,
            bytes_written=len(converted_data),
        )
    except Exception:
        error_traceback = traceback.format_exc()
        logger.log(f"Failed to convert image: {error_traceback}", "error")
        raise ConversionError(error_traceback) from None
