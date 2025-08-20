from ainb.expression.expression import Expression, ExpressionModule
from ainb.expression.instruction import InstructionBase

def parse_instruction(text: str) -> InstructionBase:
    """
    Parses a single instruction
    """
    raise NotImplementedError()

def parse_expression(text: str) -> Expression:
    """
    Parses a single expression
    """
    raise NotImplementedError()

def parse_module(text: str) -> ExpressionModule:
    """
    Parses expression assembly source into an expression module
    """
    raise NotImplementedError()