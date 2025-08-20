import typing

from ainb.expression.common import ExpressionReader
from ainb.expression.instruction import (
    InstType,
    InstructionBase,
    EndInstruction,
    StoreInstruction,
    NegateInstruction,
    LogicalNotInstruction,
    AdditionInstruction,
    SubtractionInstruction,
    MultiplicationInstruction,
    DivisionInstruction,
    ModulusInstruction,
    IncrementInstruction,
    DecrementInstruction,
    ScalarMultiplicationInstruction,
    ScalarDivisionInstruction,
    LeftShiftInstruction,
    RightShiftInstruction,
    LessThanInstruction,
    LessThanEqualInstruction,
    GreaterThanInstruction,
    GreaterThanEqualInstruction,
    EqualityInstruction,
    InequalityInstruction,
    ANDInstruction,
    XORInstruction,
    ORInstruction,
    LogicalANDInstruction,
    LogicalORInstruction,
    CallFunctionInstruction,
    JumpIfZeroInstruction,
    JumpInstruction
)

DECODING_TABLE: typing.Final[typing.Dict[InstType, typing.Type[InstructionBase]]] = {
    InstType.END : EndInstruction,
    InstType.STR : StoreInstruction,
    InstType.NEG : NegateInstruction,
    InstType.NOT : LogicalNotInstruction,
    InstType.ADD : AdditionInstruction,
    InstType.SUB : SubtractionInstruction,
    InstType.MUL : MultiplicationInstruction,
    InstType.DIV : DivisionInstruction,
    InstType.MOD : ModulusInstruction,
    InstType.INC : IncrementInstruction,
    InstType.DEC : DecrementInstruction,
    InstType.VMS : ScalarMultiplicationInstruction,
    InstType.VDS : ScalarDivisionInstruction,
    InstType.LSH : LeftShiftInstruction,
    InstType.RSH : RightShiftInstruction,
    InstType.LST : LessThanInstruction,
    InstType.LTE : LessThanEqualInstruction,
    InstType.GRT : GreaterThanInstruction,
    InstType.GTE : GreaterThanEqualInstruction,
    InstType.EQL : EqualityInstruction,
    InstType.NEQ : InequalityInstruction,
    InstType.AND : ANDInstruction,
    InstType.XOR : XORInstruction,
    InstType.ORR : ORInstruction,
    InstType.LAN : LogicalANDInstruction,
    InstType.LOR : LogicalORInstruction,
    InstType.CFN : CallFunctionInstruction,
    InstType.JZE : JumpIfZeroInstruction,
    InstType.JMP : JumpInstruction,
}

def disassemble(reader: ExpressionReader) -> InstructionBase:
    """
    Disassembles a single instruction (8 bytes)
    """
    return DECODING_TABLE[InstType(reader.read_u8())]._read(reader)