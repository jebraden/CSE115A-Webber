"""Reading preferences: runtime presentation only, never writes archived files."""
import json

DEFAULTS = {"zoom": "100%", "text_size": "12 pt", "font": "Sans serif", "spacing": "Normal"}
OPTIONS = {
    "zoom": ("75%", "90%", "100%", "110%", "125%", "150%", "175%", "200%"),
    "text_size": ("10 pt", "12 pt", "14 pt", "16 pt", "18 pt", "20 pt", "24 pt", "28 pt", "32 pt"),
    "font": ("Sans serif", "Serif", "Monospace"),
    "spacing": ("Normal", "Comfortable"),
}


def normalize_preferences(preferences):
    result = {}
    for key, default in DEFAULTS.items():
        value = preferences.get(key)
        if key in ("zoom", "text_size"):
            suffix, low, high = ("%", 75, 200) if key == "zoom" else (" pt", 10, 32)
            try:
                if not isinstance(value, str) or not value.endswith(suffix):
                    raise ValueError("Invalid size")
                number = int(value[:-len(suffix)])
                result[key] = f"{number}{suffix}" if low <= number <= high else default
            except (ValueError, TypeError):
                result[key] = default
        else:
            result[key] = value if value in OPTIONS[key] else default
    return result


def reading_script(preferences):
    """Reversible overrides calculated from the page's original computed styles.

    A page-local map records only attributes changed by Webber. Restore them
    before each recalculation so text never grows cumulatively on repeated use.
    """
    prefs = normalize_preferences(preferences)
    payload = json.dumps({"points": int(prefs["text_size"].split()[0]),
                          "font": {"Sans serif": "sans-serif", "Serif": "serif", "Monospace": "monospace"}[prefs["font"]],
                          "lineHeight": 1.8 if prefs["spacing"] == "Comfortable" else 1.5})
    return """(() => {
      const prefs = PAYLOAD;
      const key = '__webberReadingOverrides';
      const previous = window[key] || new Map();
      previous.forEach((properties, element) => {
        for (const [name, value, priority] of properties) {
          if (value) element.style.setProperty(name, value, priority);
          else element.style.removeProperty(name);
        }
      });
      const changes = new Map();
      window[key] = changes;
      const baseSize = parseFloat(getComputedStyle(document.body).fontSize) || 16;
      // Measure before changing any styles, avoiding inherited size inflation.
      const nodes = Array.from(document.querySelectorAll('body, body *')).filter(el =>
        !el.closest('script, style, svg, math, noscript') &&
        Array.from(el.childNodes).some(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim())
      ).map(el => { const css = getComputedStyle(el); return [el, parseFloat(css.fontSize)]; });
      nodes.forEach(([el, size]) => {
        const properties = [];
        const change = (name, value) => {
          properties.push([name, el.style.getPropertyValue(name), el.style.getPropertyPriority(name)]);
          el.style.setProperty(name, value, 'important');
        };
        if (prefs.points !== null && Number.isFinite(size)) change('font-size', `${size / baseSize * prefs.points}pt`);
        if (prefs.font) change('font-family', prefs.font);
        change('line-height', String(prefs.lineHeight));
        changes.set(el, properties);
      });
    })();""".replace("PAYLOAD", payload)
