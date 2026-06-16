from dataclasses import dataclass

from backend.image_converter.core.exceptions import ConversionError


@dataclass(frozen=True)
class PdfPreset:
    size: tuple[int, int] | None
    margin_mm: float = 0.0
    auto_rotate: bool = False


PDF_PRESETS: dict[str, PdfPreset] = {
    "original": PdfPreset(size=None, margin_mm=0.0, auto_rotate=False),
    "a4-auto": PdfPreset(size=(595, 842), margin_mm=10.0, auto_rotate=True),
    "a4-portrait": PdfPreset(size=(595, 842), margin_mm=10.0, auto_rotate=False),
    "a4-landscape": PdfPreset(size=(842, 595), margin_mm=10.0, auto_rotate=False),
    "letter-auto": PdfPreset(size=(612, 792), margin_mm=10.0, auto_rotate=True),
    "letter-portrait": PdfPreset(size=(612, 792), margin_mm=10.0, auto_rotate=False),
    "letter-landscape": PdfPreset(size=(792, 612), margin_mm=10.0, auto_rotate=False),
    "mobile-portrait": PdfPreset(size=(1080, 1920), margin_mm=0.0, auto_rotate=False),
    "mobile-landscape": PdfPreset(size=(1920, 1080), margin_mm=0.0, auto_rotate=False),
}

PDF_SCALE_MODES = {"fit", "fill"}


def resolve_pdf_preset(value: str | None) -> PdfPreset:
    key = value.strip().lower().replace("_", "-").replace(" ", "-") if value else "original"
    key = key or "original"
    if key not in PDF_PRESETS:
        raise ConversionError(f"Unsupported PDF preset: '{value}'")
    return PDF_PRESETS[key]


def resolve_pdf_scale(value: str | None) -> str:
    key = value.strip().lower() if value else "fit"
    key = key or "fit"
    if key not in PDF_SCALE_MODES:
        raise ConversionError(f"Unsupported PDF scale mode: '{value}'")
    return key
