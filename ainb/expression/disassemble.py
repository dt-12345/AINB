from ainb.expression.common import ExpressionReader
from ainb.expression.instruction import (
    InstType,
    InstructionBase,
    INSTRUCTION_TABLE,
)

def disassemble(reader: ExpressionReader) -> InstructionBase:
    """
    Disassembles a single instruction (8 bytes)
    """
    return INSTRUCTION_TABLE[InstType(reader.read_u8())]._read(reader)