import os
import re
from pathlib import Path

from semantic_version import Version


def replace_in_file(filename: Path, pattern: "re.Pattern[str]", to: str) -> None:
    text = filename.read_text()
    new = pattern.sub(to, text)
    filename.write_text(new)


def main() -> None:
    version = Version(os.environ["npm_package_version"])

    preview = version.minor % 2 != 0

    for f in ["robotcode/_version.py", "pyproject.toml"]:
        replace_in_file(
            Path(f),
            re.compile(r"""(^_*version_*\s*=\s*['"])([^'"]*)(['"])""", re.MULTILINE),
            rf"\g<1>{version or ''}{'-preview' if preview else ''}\g<3>",
        )

    for f in ["CHANGELOG.md"]:
        replace_in_file(
            Path(f),
            re.compile(r"^(\#*\s*)(\[Unreleased\])$", re.MULTILINE),
            rf"\g<1>\g<2>{os.linesep}- none so far{os.linesep}\g<1> {version or ''}",
        )


if __name__ == "__main__":
    main()
