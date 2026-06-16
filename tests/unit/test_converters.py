import pytest
from io import BytesIO

from PIL import Image

from backend.image_converter.application.dtos import ConversionDetails
from backend.image_converter.core.converters import convert_and_save, get_encoder, encode_rembg_png
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

def test_When_ImageContainsTransparency_Expect_JpegConverterFlattensAlpha(sample_rgba_png, tmp_path, mock_logger):
    """
    Ensure JPEG encoding composites alpha over white.
    """
    source_path = "/fake/source.png"
    dest_path = str(tmp_path / "out.jpg")

    result = convert_and_save(ImageFormat.JPEG, sample_rgba_png, source_path, dest_path, quality=80, logger=mock_logger)
    assert isinstance(result, ConversionDetails)
    assert result.destination == dest_path


    with open(dest_path, "rb") as f:
        output_data = f.read()
    with Image.open(BytesIO(output_data)) as out_img:
        assert out_img.mode == "RGB"

        assert out_img.size == (64, 64)

def test_When_ImageContainsTransparency_Expect_PngConverterPreservesAlpha(sample_rgba_png, tmp_path, mock_logger):
    """
    Ensure PNG encoding preserves alpha channel.
    """
    source_path = "/fake/source.png"
    dest_path = str(tmp_path / "out.png")

    result = convert_and_save(ImageFormat.PNG, sample_rgba_png, source_path, dest_path, quality=80, logger=mock_logger)
    assert isinstance(result, ConversionDetails)
    assert result.destination == dest_path

    with open(dest_path, "rb") as f:
        output_data = f.read()
    with Image.open(BytesIO(output_data)) as out_img:
        assert out_img.mode == "RGBA"
        assert out_img.size == (64, 64)


def test_When_RembgRequested_Expect_FactoryReturnsRembgEncoder(mock_logger, monkeypatch):
    import sys
    from unittest.mock import MagicMock
    monkeypatch.setitem(sys.modules, "rembg", MagicMock())

    encoder = get_encoder(ImageFormat.PNG, 80, use_rembg=True)
    assert encoder.__name__ == "<lambda>"


def test_When_RembgConverts_Expect_PngWithAlpha(sample_rgba_png, tmp_path, mock_logger, monkeypatch):
    sample_path = tmp_path / "test_image.png"
    sample_path.write_bytes(sample_rgba_png)
    image_data = sample_path.read_bytes()

    def fake_new_session(model_name: str):
        return {"model": model_name}

    def fake_remove(data, session, post_process_mask, alpha_matting):
        assert data == image_data
        assert post_process_mask is True
        assert alpha_matting is False
        buffer = BytesIO()
        img = Image.new("RGBA", (32, 32), (255, 0, 0, 128))
        img.save(buffer, format="PNG")
        return buffer.getvalue()

    import sys
    from unittest.mock import MagicMock
    mock_rembg = MagicMock()
    mock_rembg.new_session = fake_new_session
    mock_rembg.remove = fake_remove
    monkeypatch.setitem(sys.modules, "rembg", mock_rembg)

    out_data = encode_rembg_png(image_data, model_name="u2net")
    dest_path = tmp_path / "out.png"
    dest_path.write_bytes(out_data)

    with Image.open(dest_path) as out_img:
        assert out_img.mode == "RGBA"


def test_When_FormatIsValid_Expect_ImageFormatResolved():
    assert ImageFormat.from_string("jpeg") == ImageFormat.JPEG


def test_When_FormatIsUnsupported_Expect_ValueErrorRaised():
    with pytest.raises(ValueError, match="Unsupported image format"):
        ImageFormat.from_string("unsupported_format")
