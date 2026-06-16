from io import BytesIO

from backend.image_converter.core.exceptions import ConversionError


class PsdRenderer:
    def __init__(self, logger):
        self.logger = logger

    def render(self, source_name: str, data: bytes) -> bytes:
        try:
            from psd_tools import PSDImage
        except ImportError:
            raise ConversionError("psd-tools is not installed; cannot process PSD files.") from None

        try:
            psd = PSDImage.open(BytesIO(data))
            flattened = psd.composite()
            if flattened is None:
                raise ValueError(f"{source_name}: PSD contains no composite data")

            if flattened.mode not in ("RGB", "RGBA", "L", "LA"):
                if "A" in flattened.getbands():
                    flattened = flattened.convert("RGBA")
                else:
                    flattened = flattened.convert("RGB")

            buffer = BytesIO()
            flattened.save(buffer, format="PNG", optimize=False, compress_level=6)
            return buffer.getvalue()
        except Exception as exc:
            self.logger.log(f"Failed to render PSD '{source_name}': {exc!r}", "error")
            raise ConversionError("PSD could not be rendered.") from None
