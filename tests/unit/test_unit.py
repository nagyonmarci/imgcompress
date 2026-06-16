from backend.image_converter.infrastructure.logger import Logger
from backend.image_converter.presentation.cli.app import _output_results
from tests.test_utils import capture_stdout, capture_logger_output
from backend.image_converter.application.dtos import ConversionSummary, PageProcessingResult
import pytest

@pytest.fixture
def mock_logger():
    """
    Returns a Logger instance for testing.
    Debug=True for color output (if desired), and JSON mode off by default.
    """
    return Logger(debug=True, json_output=False)

def test_When_OutputResultsRunsInJsonMode_Expect_SummarySerialized():
    """
    Test that output_results prints valid JSON when json_output=True,
    capturing the printed JSON via capture_stdout.
    """
    logger = Logger(debug=False, json_output=True)
    logger.logs = []
    results = [
        PageProcessingResult(
            file="test1.jpg",
            source="/mock/source/test1.jpg",
            destination="/mock/destination/test1.jpg",
            original_width=2000,
            resized_width=800,
            is_successful=True,
        ),
        PageProcessingResult(
            file="test2.jpg",
            source="/mock/source/test2.jpg",
            destination="/mock/destination/test2.jpg",
            original_width=3000,
            resized_width=800,
            is_successful=True,
        ),
    ]

    summary = ConversionSummary(processed_pages=results, errors_count=0)
    output = capture_stdout(_output_results, summary, logger, True, False)

    import json
    output_json = json.loads(output)
    expected_json = {
        "status": "complete",
        "conversion_results": {
            "files": [
                {
                    "file": "test1.jpg",
                    "source": "/mock/source/test1.jpg",
                    "destination": "/mock/destination/test1.jpg",
                    "original_width": 2000,
                    "resized_width": 800,
                    "is_successful": True,
                    "error": None,
                },
                {
                    "file": "test2.jpg",
                    "source": "/mock/source/test2.jpg",
                    "destination": "/mock/destination/test2.jpg",
                    "original_width": 3000,
                    "resized_width": 800,
                    "is_successful": True,
                    "error": None,
                },
            ],
            "file_processing_summary": {
                "total_files_count": 2,
                "successful_files_count": 2,
                "failed_files_count": 0,
            },
        },
    }
    assert output_json == expected_json


def test_When_OutputResultsRunsInTextModeWithErrors_Expect_FailuresLogged():
    """
    Test that output_results logs plain text when json_output=False,
    capturing logger-based messages via capture_logger_output.
    """
    logger = Logger(debug=True, json_output=False)
    logger.logs = []

    results = [
        PageProcessingResult(
            file="test1.jpg",
            source="/mock/source/test1.jpg",
            destination="/mock/destination/test1.jpg",
            original_width=2000,
            resized_width=800,
            is_successful=True,
        ),
        PageProcessingResult(
            file="test2.jpg",
            source="/mock/source/test2.jpg",
            destination="/mock/destination/test2.jpg",
            original_width=None,
            resized_width=None,
            is_successful=False,
            error="Mock failure",
        ),
    ]

    summary = ConversionSummary(processed_pages=results, errors_count=1)
    output = capture_logger_output(_output_results, summary, logger, False, True)
    assert "Summary: 2 file(s) processed, 1 error(s)." in output
    assert "Failed: test2.jpg - Error: Mock failure" in output

def test_When_DebugModeEnabled_Expect_LogsBypassStorage(mock_logger):
    """
    Test debug mode logs different levels but doesn't store them 
    in json_output=False mode.
    """
    logger = mock_logger
    logger.debug = True

    logger.log("Mock: Debug - Debugging info...", "debug")
    logger.log("Mock: Info - Just an info message.", "info")
    logger.log("Mock: Warning - Heads up!", "warning")
    logger.log("Mock: Error - occurred!", "error")

    assert len(logger.logs) == 0
