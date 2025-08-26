import enum

from ainb.utils import IntEnumEx, JSONType

class ParamType(IntEnumEx):
    """
    Parameter type enum
    """

    Int = 0
    Bool = 1
    Float = 2
    String = 3
    Vector3F = 4
    Pointer = 5

class VectorComponent(enum.Enum):
    """
    Vector component enum
    """

    NONE = 0
    X = 1
    Y = 2
    Z = 3

class ParamFlag(int):
    """
    Common parameter flags
    """

    def is_pulse_tls(self) -> bool:
        """
        Returns True if this parameter should pulse AIMgr's TLS slot with 0x80000001 when set
        """
        return self & 0x800000 != 0
    
    # this is definitely wrong but I don't have anything else to call it so whatever
    def is_output(self) -> bool:
        """
        Returns True if this parameter has bit 0 of its pointer set

        Note this method name is definitely wrong
        """
        return self & 0x1000000 != 0
    
    def is_expression(self) -> bool:
        """
        Returns True if this parameter derives its value from an expression
        """
        return self & 0xc2000000 == 0xc2000000
    
    def is_blackboard(self) -> bool:
        """
        Returns True if this parameter derives its value from a blackboard parameter
        """
        return self & 0xc2000000 != 0xc2000000 and self & 0xc2000000 != 0
    
    def get_vector_component(self) -> VectorComponent:
        """
        Returns the vector component (X, Y, Z, or NONE) associated with this parameter

        Only for use with f32 blackboard parameters

        If the component is NONE -> the parameter's value is from an f32 blackboard parameter

        Otherwise -> the parameter's value is from the corresponding component of a vec3f blackboard parameter
        """
        return VectorComponent(self >> 0x1a & 3)
    
    def get_index(self) -> int:
        """
        Returns the index associated with this parameter (only used for expressions and blackboard parameters)
        """
        return self & 0xffff
    
    def set_pulse_tls(self, b: bool = True) -> "ParamFlag":
        """
        Set pulse TLS flag
        """
        return ParamFlag(self & 0xff7fffff | int(b) << 0x17)
    
    def set_output(self, b: bool = True) -> "ParamFlag":
        """
        Returns whether or not this parameter has bit 0 of its pointer set

        Note this method name is definitely wrong
        """
        return ParamFlag(self & 0xfeffffff | int(b) << 0x18)
    
    def set_expression(self, b: bool = True) -> "ParamFlag":
        """
        Set expression flag
        """
        return ParamFlag(self & 0x3dffffff | (0xc2000000 if b else 0))
    
    def set_blackboard(self, b: bool = True) -> "ParamFlag":
        """
        Set blackboard flag
        """
        return ParamFlag(self & 0x3dffffff | (0x80000000 if b else 0))
    
    def set_vector_component(self, comp: VectorComponent) -> "ParamFlag":
        """
        Set vector component flag
        """
        return ParamFlag(self & 0xf3ffffff | comp.value << 0x1a)

    def set_index(self, index: int) -> "ParamFlag":
        """
        Set index flag
        """
        return ParamFlag(self & 0xffff0000 | index)

    def _as_dict(self) -> JSONType:
        output: JSONType = {
            "Flags" : [],
        }
        if self.is_pulse_tls():
            output["Flags"].append("Pulse TLS")
        if self.is_output():
            output["Flags"].append("Is Output")
        if self.is_expression():
            output["Expression Index"] = self.get_index()
        elif self.is_blackboard():
            output["Blackboard Index"] = self.get_index()
            comp: VectorComponent = self.get_vector_component()
            if comp != VectorComponent.NONE:
                output["Vector Component"] = comp.name
        return output
    
    @classmethod
    def _from_dict(cls, data: JSONType) -> "ParamFlag":
        flag: ParamFlag = cls()
        if "Pulse TLS" in data["Flags"]:
            flag = flag.set_pulse_tls()
        if "Is Output" in data["Flags"]:
            flag = flag.set_output()
        if "Expression Index" in data:
            flag = flag.set_expression()
            flag = flag.set_index(data["Expression Index"])
        elif "Blackboard Index" in data:
            flag = flag.set_blackboard()
            flag = flag.set_index(data["Blackboard Index"])
            if "Vector Component" in data:
                flag = flag.set_vector_component(VectorComponent[data["Vector Component"]])
        return flag