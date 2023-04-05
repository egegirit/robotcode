from dataclasses import dataclass
from enum import Enum, unique
from pathlib import Path
from typing import IO, Any, AnyStr, Callable, Dict, List, Optional, TypeVar, Union, cast

import click
import pluggy
from robotcode.core.dataclasses import as_json

__all__ = ["hookimpl", "CommonConfig", "pass_application"]

F = TypeVar("F", bound=Callable[..., Any])
hookimpl = cast(Callable[[F], F], pluggy.HookimplMarker("robotcode"))


@unique
class ColoredOutput(str, Enum):
    AUTO = "auto"
    YES = "yes"
    NO = "no"


@unique
class OutputFormat(str, Enum):
    TOML = "toml"
    JSON = "json"
    FLAT = "flat"

    def __str__(self) -> str:
        return self.value


@dataclass
class CommonConfig:
    config_files: Optional[List[Path]] = None
    profiles: Optional[List[str]] = None
    dry: bool = False
    verbose: bool = False
    colored_output: ColoredOutput = ColoredOutput.AUTO


class Application:
    def __init__(self) -> None:
        self.config = CommonConfig()

    @property
    def colored(self) -> bool:
        return self.config.colored_output in [ColoredOutput.AUTO, ColoredOutput.YES]

    def verbose(
        self,
        message: Union[str, Callable[[], Any], None],
        file: Optional[IO[AnyStr]] = None,
        nl: bool = True,
        err: bool = False,
    ) -> None:
        if self.config.verbose:
            click.secho(
                message() if callable(message) else message,
                file=file,
                nl=nl,
                err=err,
                color=self.colored,
                fg="bright_black",
            )

    def warning(
        self,
        message: Union[str, Callable[[], Any], None],
        file: Optional[IO[AnyStr]] = None,
        nl: bool = True,
        err: bool = False,
    ) -> None:
        click.secho(
            f"WARNING: {message() if callable(message) else message}",
            file=file,
            nl=nl,
            err=err,
            color=self.colored,
            fg="bright_yellow",
        )

    def print_dict(self, config: Dict[str, Any], format: OutputFormat) -> None:
        text = None
        if format == "toml":
            try:
                import tomli_w

                text = tomli_w.dumps(config)
            except ImportError:
                self.warning("Package 'tomli_w' is required to use TOML output. Using JSON format instead.")
                format = OutputFormat.JSON

        if text is None:
            text = as_json(config, indent=True)

        if not text:
            return

        if self.colored:
            try:
                from rich.console import Console
                from rich.syntax import Syntax

                Console().print(Syntax(text, format, background_color="default"))

                return
            except ImportError:
                if self.config.colored_output == ColoredOutput.YES:
                    self.warning('Package "rich" is required to use colored output.')

        click.echo(text)

        return


pass_application = click.make_pass_decorator(Application, ensure=True)