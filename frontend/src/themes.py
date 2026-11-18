"""Neutral appearance variants for the Designer-defined shell.

Archived HTML is never restyled. Keep Designer's light stylesheet as the source
of layout rules; replace its color tokens when the user selects dark mode.
"""
import re
from pathlib import Path

# Shared named colors for shell styles and theme conversion.
OFF_WHITE = "#f8f8f6"
NEAR_BLACK = "#101010"
CHARCOAL = "#292929"
PALE_GRAY = "#e7e7e7"
LIGHT_WARM_GRAY = "#efefed"
DEEP_CHARCOAL = "#181818"
WARM_GRAY_BORDER = "#cececa"
DARK_GRAY_BORDER = "#404040"
OLIVE = "#566446"
FOREST_GREEN = "#4b6945"
WARM_WHITE = "#f1f1ee"
DARK_GRAY = "#222222"
PALE_SAGE = "#e9ecdf"
DARK_SAGE = "#293629"
LIGHT_SAGE = "#e3e8d6"
DEEP_GREEN = "#273624"
DARK_OLIVE = "#435435"
PALE_GREEN = "#d6e7ce"
MUTED_WARM_GRAY = "#92928e"
MEDIUM_GRAY = "#777777"
SOFT_SAGE = "#d7dfc8"
MOSS_GREEN = "#40563a"
IVORY = "#f4f4f1"
INK = "#141414"
WARM_GRAY = "#737370"
SILVER = "#aaaaaa"
DEEP_OLIVE = "#36442b"
LIGHT_GRAY_BORDER = "#e3e3df"
CHARCOAL_BORDER = "#303030"
DARK_WARM_GRAY = "#41413e"
LIGHT_GRAY = "#dddddd"
PALE_WARM_GRAY = "#dededb"
MUTED_SAGE = "#b7c4a7"
MUTED_FOREST = "#52644a"
SAGE = "#879b76"
LIGHT_MOSS = "#8ca37b"
OLIVE_GREEN = "#4b5a3d"
LEAF_GREEN = "#5b7b53"
DEEP_OLIVE_GREEN = "#414f35"
DARK_FOREST = "#42633c"
WHITE = "#ffffff"
LIGHT_GREEN = "#b6d1aa"
BUTTON_CHARCOAL = "#1c1c1c"
BUTTON_GRAY_BORDER = "#3b3b3b"

# Map each light-theme hex color from the Designer stylesheet to its dark-theme
# equivalent. Only matching shell colors are replaced; archived HTML is untouched.
DARK_COLORS = {
    OFF_WHITE: NEAR_BLACK,
    CHARCOAL: PALE_GRAY,
    LIGHT_WARM_GRAY: DEEP_CHARCOAL,
    WARM_GRAY_BORDER: DARK_GRAY_BORDER,
    OLIVE: FOREST_GREEN,
    WARM_WHITE: DARK_GRAY,
    PALE_SAGE: DARK_SAGE,
    LIGHT_SAGE: DEEP_GREEN,
    DARK_OLIVE: PALE_GREEN,
    MUTED_WARM_GRAY: MEDIUM_GRAY,
    SOFT_SAGE: MOSS_GREEN,
    IVORY: INK,
    WARM_GRAY: SILVER,
    DEEP_OLIVE: PALE_GREEN,
    LIGHT_GRAY_BORDER: CHARCOAL_BORDER,
    DARK_WARM_GRAY: LIGHT_GRAY,
    PALE_WARM_GRAY: CHARCOAL_BORDER,
    MUTED_SAGE: MUTED_FOREST,
    SAGE: LIGHT_MOSS,
    OLIVE_GREEN: LEAF_GREEN,
    DEEP_OLIVE_GREEN: DARK_FOREST,
}


def stylesheet_for(light_stylesheet: str, mode: str) -> str:
    icon = Path(__file__).with_name("ui") / "icons" / ("chevron-dark.svg" if mode == "dark" else "chevron-light.svg")
    light_stylesheet = light_stylesheet.replace("url(icons/chevron-light.svg)", f'url("{icon.as_posix()}")')
    close_icon = icon.with_name("close-dark.svg" if mode == "dark" else "close-light.svg")
    light_stylesheet = light_stylesheet.replace("url(icons/close-light.svg)", 'url("%s")' % close_icon.as_posix())
    if mode != "dark":
        return light_stylesheet
    stylesheet = re.sub(r"#[0-9a-fA-F]{6}\b", lambda match: DARK_COLORS.get(match[0].lower(), match[0]), light_stylesheet)
    # Filled actions retain a dark olive surface with clearly readable text.
    return stylesheet + (
        f"\nQPushButton#savePageButton, QPushButton#captureButton {{ color: {WHITE}; }}"
        f" QLabel#brandLabel {{ color: {LIGHT_GREEN}; }}"
    )
