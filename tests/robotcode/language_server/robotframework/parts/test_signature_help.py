import asyncio
from pathlib import Path

import pytest
import yaml
from pytest_regtest import RegTestFixture
from robotcode.core.lsp.types import (
    Position,
    SignatureHelpContext,
    SignatureHelpTriggerKind,
)
from robotcode.language_server.common.text_document import TextDocument
from robotcode.language_server.robotframework.protocol import (
    RobotLanguageServerProtocol,
)

from tests.robotcode.language_server.robotframework.tools import (
    GeneratedTestData,
    generate_test_id,
    generate_tests_from_source_document,
)


@pytest.mark.parametrize(
    ("test_document", "data"),
    generate_tests_from_source_document(Path(Path(__file__).parent, "data/tests/signature_help.robot")),
    indirect=["test_document"],
    ids=generate_test_id,
    scope="module",
)
@pytest.mark.usefixtures("protocol")
@pytest.mark.asyncio()
async def test(
    regtest: RegTestFixture,
    protocol: RobotLanguageServerProtocol,
    test_document: TextDocument,
    data: GeneratedTestData,
) -> None:
    result = await asyncio.wait_for(
        protocol.robot_signature_help.collect(
            protocol.robot_signature_help,
            test_document,
            Position(line=data.line, character=data.character),
            SignatureHelpContext(trigger_kind=SignatureHelpTriggerKind.INVOKED, is_retrigger=False),
        ),
        60,
    )
    regtest.write(
        yaml.dump(
            {
                "data": data,
                "result": result if result else result,
            }
        )
    )