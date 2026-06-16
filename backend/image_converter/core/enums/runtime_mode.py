"""The two ways the bootstrapper can run: CLI or web server."""

from enum import Enum


class RuntimeMode(Enum):
    CLI = "cli"
    WEB = "web"

    @classmethod
    def from_arg(cls, value: str | None) -> "RuntimeMode":
        """Resolve the CLI argument string to a mode. Defaults to WEB when absent."""
        if value is None:
            return cls.WEB
        try:
            return cls(value)
        except ValueError as exc:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(
                f"unknown runtime mode '{value}', expected one of: {valid}"
            ) from exc
