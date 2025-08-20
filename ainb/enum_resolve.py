import typing

class EnumEntry(typing.NamedTuple):
    """
    Enum resolve table entry
    """

    patch_offset: int = 0   # offset to patch
    classname: str = ""     # enum classname
    value_name: str = ""    # enum value name