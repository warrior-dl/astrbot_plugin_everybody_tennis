MATCH_TYPE_SINGLES = "singles"
MATCH_TYPE_DOUBLES = "doubles"


def match_type_label(match_type: str) -> str:
    if match_type == MATCH_TYPE_DOUBLES:
        return "双打"
    return "单打"
