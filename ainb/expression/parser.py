import re

from ainb.expression.common import ExpressionParseError
from ainb.expression.instruction import (
    InstructionBase,
    InstType,
    INSTRUCTION_TABLE,
)

# this does not properly match custom function signatures, but those will be handled separate anyways
INSTRUCTION: re.Pattern[str] = re.compile(r"(?P<opcode>[a-zA-Z]{3})(\s+(?P<arguments>(?P<op1>.+?)(\s*,\s*(?P<op2>.+))?)?)?\s*$")

def parse_instruction(text: str) -> InstructionBase:
    """
    Parses a single instruction
    """
    match: re.Match[str] | None = re.search(INSTRUCTION, text)
    if match is None:
        raise ExpressionParseError(f"Failed to parse the following line: \"{text}\"")
    inst_type: InstType = InstType[match.group("opcode")]
    return INSTRUCTION_TABLE[inst_type]._parse(match)