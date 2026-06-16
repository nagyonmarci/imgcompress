from io import BytesIO
import pytest
from PIL import Image
from unittest.mock import MagicMock
import sys

from backend.image_converter.application.dtos import ConversionDetails
from backend.image_converter.core.converters import convert_and_save, get_encoder
from backend.image_converter.core.enums.image_format import ImageFormat
from backend.image_converter.infrastructure.logger import Logger

@pytest.fixture
def sample_rgba_png():
    """Create a 64x64 RGBA image in memory."""
    buf = BytesIO()
    img = Image.new("RGBA", (64, 64), (0, 255, 0, 128))
    img.save(buf, format="PNG")
    return buf.getvalue()

@pytest.fixture
def mock_logger():
    """A basic logger stub."""
    return Logger(debug=True, json_output=False)

def test_avif_converter_encodes_to_avif(sample_rgba_png, tmp_path, mock_logger):
    """Ensure AVIF encoding correctly saves as AVIF."""

    source_path = "/fake/source.png"
    dest_path = str(tmp_path / "out.avif")

    result = convert_and_save(ImageFormat.AVIF, sample_rgba_png, source_path, dest_path, quality=80, logger=mock_logger)

    assert isinstance(result, ConversionDetails)

    with Image.open(dest_path) as out_img:
        assert out_img.format == "AVIF"
        assert out_img.size == (64, 64)

def test_rembg_avif_converter_encodes_to_avif(sample_rgba_png, tmp_path, mock_logger, monkeypatch):
    """Ensure rembg-based AVIF encoding uses rembg and saves as AVIF."""

    # Mock rembg
    mock_rembg = MagicMock()
    mock_rembg.new_session.return_value = {"model": "u2net"}

    def fake_remove(data, session, post_process_mask, alpha_matting):
        buffer = BytesIO()
        img = Image.new("RGBA", (32, 32), (255, 0, 0, 128))
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    mock_rembg.remove = fake_remove
    monkeypatch.setitem(sys.modules, "rembg", mock_rembg)

    source_path = "/fake/source.png"
    dest_path = str(tmp_path / "out_rembg.avif")

    convert_and_save(
        ImageFormat.AVIF, sample_rgba_png, source_path, dest_path, quality=80, logger=mock_logger, use_rembg=True
    )

    with Image.open(dest_path) as out_img:
        assert out_img.format == "AVIF"
        assert out_img.size == (32, 32)
        assert out_img.mode == "RGBA"

def test_factory_returns_avif_converters(mock_logger):
    """Ensure get_encoder returns a usable encoder for AVIF (with/without rembg)."""
    # Without Rembg
    encoder = get_encoder(ImageFormat.AVIF, quality=80, use_rembg=False)
    assert callable(encoder)

    # With Rembg
    encoder_rembg = get_encoder(ImageFormat.AVIF, quality=80, use_rembg=True)
    assert callable(encoder_rembg)
