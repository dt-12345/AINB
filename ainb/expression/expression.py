import typing

from ainb.expression.common import ExpressionReader, ExpressionWriter, ExpressionPreProcessError
from ainb.expression.instruction import InstType, InstDataType, InstructionBase, Sizes
from ainb.expression.parser import parse_instruction
from ainb.expression.write_context import ExpressionWriteContext
from ainb.utils import JSONType

class Expression:
    """
    Class representing an expression
    """

    __slots__ = ["setup_command", "main_command", "input_datatype", "output_datatype"]

    def __init__(self) -> None:
        self.setup_command: typing.List[InstructionBase] = []
        self.main_command: typing.List[InstructionBase] = []

        self.input_datatype: InstDataType = InstDataType.NONE
        self.output_datatype: InstDataType = InstDataType.NONE
    
    @classmethod
    def _read(cls, reader: ExpressionReader, instructions: typing.List[InstructionBase]) -> "Expression":
        expr: Expression = cls()
        setup_base_index: int = reader.read_s32()
        if reader.version > 1:
            setup_inst_count: int = reader.read_u32()
            if setup_base_index != -1:
                expr.setup_command = instructions[setup_base_index:setup_base_index+setup_inst_count]
        else:
            if setup_base_index != -1:
                for i in range(setup_base_index, len(instructions)):
                    s_inst: InstructionBase = instructions[i]
                    expr.setup_command.append(s_inst)
                    if s_inst.get_type() == InstType.END:
                        break

        main_base_index: int = reader.read_s32()
        if reader.version > 1:
            main_inst_count: int = reader.read_u32()
            expr.main_command = instructions[main_base_index:main_base_index+main_inst_count]
        else:
            for i in range(main_base_index, len(instructions)):
                m_inst: InstructionBase = instructions[i]
                expr.main_command.append(m_inst)
                if m_inst.get_type() == InstType.END:
                    break

        # can be calculated later
        global_mem_usage: int = reader.read_u32()
        local32_mem_usage: int = reader.read_u16()
        local64_mem_usage: int = reader.read_u16()

        expr.output_datatype = InstDataType(reader.read_u16())
        expr.input_datatype = InstDataType(reader.read_u16())

        # TODO: verify input/output types match with actual instructions

        return expr
    
    @staticmethod
    def _format_instruction(instruction: InstructionBase, addr: int) -> str:
        return f"{addr:#06x}    {instruction.format()}"

    @staticmethod
    def _format_instructions(instructions: typing.List[InstructionBase]) -> str:
        return "\n".join(f"        {Expression._format_instruction(inst, i * 8)}" for i, inst in enumerate(instructions))

    @staticmethod
    def _format_instructions_single_indent(instructions: typing.List[InstructionBase]) -> str:
        return "\n".join(f"    {Expression._format_instruction(inst, i * 8)}" for i, inst in enumerate(instructions))
    
    def _format(self) -> str:
        if self.setup_command:
            return f"    .setup\n{self._format_instructions(self.setup_command)}\n    .main\n{self._format_instructions(self.main_command)}\n"
        else:
            return f"    .main\n{self._format_instructions(self.main_command)}\n"
    
    def format(self) -> str:
        """
        Returns a formatted string of the expression
        """
        if self.setup_command:
            return f".setup\n{self._format_instructions_single_indent(self.setup_command)}\n.main\n{self._format_instructions_single_indent(self.main_command)}\n"
        else:
            return f".main\n{self._format_instructions_single_indent(self.main_command)}\n"
    
    def _as_dict(self, index: int) -> JSONType:
        if self.setup_command:
            return {
                "Expression Index" : index,
                "Input Type" : self.input_datatype.name,
                "Output Type" : self.output_datatype.name,
                "Setup" : [self._format_instruction(inst, i * 8) for i, inst in enumerate(self.setup_command)],
                "Main" : [self._format_instruction(inst, i * 8) for i, inst in enumerate(self.main_command)],
            }
        else:
            return {
                "Expression Index" : index,
                "Input Type" : self.input_datatype.name,
                "Output Type" : self.output_datatype.name,
                "Main" : [self._format_instruction(inst, i * 8) for i, inst in enumerate(self.main_command)],
            }
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "Expression":
        expr: Expression = cls()
        expr.input_datatype = InstDataType[data["Input Type"]]
        expr.output_datatype = InstDataType[data["Output Type"]]
        if "Setup" in data:
            expr.setup_command = [
                parse_instruction(inst) for inst in data["Setup"]
            ]
        expr.main_command = [
            parse_instruction(inst) for inst in data["Main"]
        ]
        return expr
    
    def _write(self, writer: ExpressionWriter, ctx: ExpressionWriteContext, index: int) -> None:
        writer.write_s32(ctx.base_setup_indices[index])
        if ctx.version > 1:
            writer.write_u32(len(self.setup_command))
        writer.write_s32(ctx.base_indices[index])
        if ctx.version > 1:
            writer.write_u32(len(self.main_command))
        writer.write_u32(ctx.global_mem_sizes[index])
        writer.write_u16(ctx.local32_mem_sizes[index])
        writer.write_u16(ctx.local64_mem_sizes[index])
        writer.write_u16(self.output_datatype.value)
        writer.write_u16(self.input_datatype.value)

    def _write_instructions(self, writer: ExpressionWriter, ctx: ExpressionWriteContext) -> None:
        for inst in self.setup_command:
            inst._write(writer, ctx)
        for inst in self.main_command:
            inst._write(writer, ctx)
    
    @staticmethod
    def _process_instructions(ctx: ExpressionWriteContext, cmds: typing.List[InstructionBase], is_setup: bool = False) -> Sizes:
        if is_setup:
            if cmds:
                ctx.base_setup_indices.append(ctx.instruction_count)
            else:
                ctx.base_setup_indices.append(-1)
        else:
            ctx.base_indices.append(ctx.instruction_count)
        size: Sizes = Sizes()
        for inst in cmds:
            ctx.instruction_count += 1
            inst._preprocess(ctx, size)
        return size

    def _preprocess(self, ctx: ExpressionWriteContext) -> None:
        main_size: Sizes = self._process_instructions(ctx, self.main_command)
        setup_size: Sizes = self._process_instructions(ctx, self.setup_command, True)
        ctx.global_mem_sizes.append(max(main_size.global_mem, setup_size.global_mem))
        ctx.local32_mem_sizes.append(max(main_size.local32_mem, setup_size.local32_mem))
        ctx.local64_mem_sizes.append(max(main_size.local64_mem, setup_size.local64_mem))
        ctx.io_mem_sizes.append(max(main_size.io_mem, setup_size.io_mem))

        if ctx.version < 2:
            if self.setup_command:
                if self.setup_command[-1].get_type() != InstType.END:
                    raise ExpressionPreProcessError("The last instruction in a setup expression must be END")
            if self.main_command[-1].get_type() != InstType.END:
                raise ExpressionPreProcessError("The last instruction in a main expression must be END")