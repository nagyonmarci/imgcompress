import argparse

from backend.image_converter.core.enums.runtime_mode import RuntimeMode


def parse_arguments() -> tuple[RuntimeMode, list[str]]:
    parser = argparse.ArgumentParser(
        description="imgcompress – image compression CLI & web app"
    )

    subparsers = parser.add_subparsers(
        dest="mode",
        metavar="{cli,web}",
    )

    subparsers.add_parser(RuntimeMode.CLI.value, help="Run CLI mode", add_help=False)
    subparsers.add_parser(RuntimeMode.WEB.value, help="Run web app", add_help=False)

    args, remaining = parser.parse_known_args()
    mode = RuntimeMode.from_arg(args.mode)

    return mode, remaining
