import dataclasses

@dataclasses.dataclass(slots=True)
class Transition:
    """
    A transition command entry where the root node of the current context is swapped
    """

    # 0 = state end transition
    # 1 = generic transition
    transition_type: int = 0
    update_post_calc: bool = False
    command_name: str = ""