"""Neutral appearance variants for the Designer-defined shell.

Archived HTML is never restyled. Keep Designer's light stylesheet as the source
of layout rules; replace its color tokens when the user selects dark mode.
"""
import re
from pathlib import Path

DARK_COLORS = {
    "#f8f8f6": "#101010", "#292929": "#e7e7e7", "#efefed": "#181818",
    "#cececa": "#404040", "#566446": "#4b6945", "#f1f1ee": "#222222",
    "#e9ecdf": "#293629", "#e3e8d6": "#273624", "#435435": "#d6e7ce",
    "#92928e": "#777777", "#d7dfc8": "#40563a", "#f4f4f1": "#141414",
    "#737370": "#aaaaaa", "#36442b": "#d6e7ce", "#e3e3df": "#303030",
    "#41413e": "#dddddd",
    "#dededb": "#303030", "#b7c4a7": "#52644a", "#879b76": "#8ca37b",
    "#4b5a3d": "#5b7b53", "#414f35": "#42633c",
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
    return stylesheet + "\nQPushButton#savePageButton, QPushButton#captureButton { color: #ffffff; } QLabel#brandLabel { color: #b6d1aa; }"
