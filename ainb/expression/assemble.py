from ainb.expression.common import ExpressionWriter
from ainb.expression.instruction import InstructionBase, InstType

def assemble(inst: InstructionBase, writer: ExpressionWriter) -> None:
    """
    Assembles a single instruction and writes it out to the stream
    """
    raise NotImplementedError()