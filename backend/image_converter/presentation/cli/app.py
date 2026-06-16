import json
import os
import sys
import traceback

from backend.image_converter.application.compress_images_usecase import CompressImagesUseCase
from backend.image_converter.application.dtos import (
    CompressRequest,
    ConversionOutputDto,
    ConversionResultsDto,
    ConversionSummary,
    FileProcessingSummary,
)
from backend.image_converter.application.payload_expander_factory import create_payload_expander
from backend.image_converter.core.enums.image_format import ImageFormat
from backend.image_converter.core.enums.log_level import LogLevel
from backend.image_converter.core.exceptions import ConversionError
from backend.image_converter.core.internals.utilities import is_file_supported
from backend.image_converter.domain.image_resizer import ImageResizer
from backend.image_converter.infrastructure.local_storage import FileItem, LocalStorage
from backend.image_converter.infrastructure.logger import Logger
from backend.image_converter.presentation.cli.argument_parser import parse_arguments
from dataclasses import asdict


def _build_items(source: str) -> list[FileItem]:
    if os.path.isfile(source):
        name = os.path.basename(source)
        stem, _ = os.path.splitext(name)
        return [FileItem(path=source, name=name, stem=stem)]
    if os.path.isdir(source):
        items = []
        for name in os.listdir(source):
            path = os.path.join(source, name)
            if os.path.isfile(path) and is_file_supported(path):
                stem, _ = os.path.splitext(name)
                items.append(FileItem(path=path, name=name, stem=stem))
        return items
    raise ConversionError(f"Source path '{source}' is neither file nor directory.")


def _output_results(summary: ConversionSummary, logger: Logger, json_output: bool, debug: bool) -> None:
    """Output final results either in JSON or plain text."""
    if json_output:
        summary_payload = FileProcessingSummary(
            total_files_count=len(summary.processed_pages),
            successful_files_count=len([r for r in summary.processed_pages if r.is_successful]),
            failed_files_count=len([r for r in summary.processed_pages if not r.is_successful]),
        )

        results_payload = ConversionResultsDto(
            files=list(summary.processed_pages),
            file_processing_summary=summary_payload,
        )

        response = ConversionOutputDto(
            status="complete",
            conversion_results=results_payload,
            logs=logger.logs if debug else None,
        )

        response_dict = {k: v for k, v in asdict(response).items() if v is not None}
        print(json.dumps(response_dict, indent=4))
    else:
        message = f"Summary: {len(summary.processed_pages)} file(s) processed, {summary.errors_count} error(s)."
        logger.log(message, LogLevel.INFO.value)
        for result in summary.processed_pages:
            if not result.is_successful:
                error_message = f"Failed: {result.file} - Error: {result.error}"
                logger.log(error_message, LogLevel.ERROR.value)


def main(argv=None):
    """Main entry point of the script."""

    args = parse_arguments(argv)
    logger = Logger(debug=args.debug, json_output=args.json_output)

    # Validate: --remove-background only works with PNG or AVIF format
    if args.remove_background and args.format.upper() not in ["PNG", "AVIF"]:
        logger.log(
            "Error: --remove-background can only be used with --format png or --format avif",
            "error"
        )
        sys.exit(1)

    try:
        image_format = ImageFormat.from_string(args.format.upper())
        pdf_preset = args.pdf_preset
        pdf_scale = args.pdf_scale
        pdf_margin_mm = args.pdf_margin_mm
        pdf_paginate = args.pdf_paginate
        if image_format != ImageFormat.PDF:
            pdf_preset = None
            pdf_scale = "fit"
            pdf_margin_mm = None
            pdf_paginate = False

        os.makedirs(args.destination, exist_ok=True)
        items = _build_items(args.source)

        resizer = ImageResizer()
        storage = LocalStorage(logger=logger)
        payload_expander = create_payload_expander(logger)
        use_case = CompressImagesUseCase(logger, resizer, storage, payload_expander)

        req = CompressRequest(
            source_folder=args.source,
            dest_folder=args.destination,
            image_format=image_format,
            quality=args.quality,
            width=args.width,
            target_size=None,
            use_rembg=args.remove_background,
            pdf_preset=pdf_preset,
            pdf_scale=pdf_scale,
            pdf_margin_mm=pdf_margin_mm,
            pdf_paginate=pdf_paginate,
        )

        result = use_case.execute_items(items, req)

        summary = ConversionSummary(
            processed_pages=result.page_results,
            errors_count=sum(not r.is_successful for r in result.page_results),
        )
        _output_results(summary, logger, args.json_output, args.debug)
    except Exception:
        tb = traceback.format_exc()
        logger.log(f"A fatal error occurred during processing:\n{tb}", "error")
        sys.exit(1)

if __name__ == '__main__':
    main()
