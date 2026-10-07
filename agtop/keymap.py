"""Make letter shortcuts work on non-Latin keyboard layouts.

A terminal sends characters, not physical key positions. With a Russian
layout the J key sends "о", so a binding for "j" never fires. This maps
each character back to the Latin letter on the same key of a QWERTY
keyboard. It covers the Russian, Ukrainian and Belarusian layouts.
"""

from typing import Optional

# Physical QWERTY key → the Cyrillic letters other layouts put there.
_KEYS = {
    "q": "й", "w": "ц", "e": "у", "r": "к", "t": "е", "y": "н", "u": "г",
    "i": "ш", "o": "щў", "p": "з", "a": "ф", "s": "ыі", "d": "в", "f": "а",
    "g": "п", "h": "р", "j": "о", "k": "л", "l": "д", "z": "я", "x": "ч",
    "c": "с", "v": "м", "b": "и", "n": "т", "m": "ь",
}

LATIN_FOR = {
    letter: latin for latin, letters in _KEYS.items() for letter in letters
}
LATIN_FOR.update({letter.upper(): latin.upper() for letter, latin in list(LATIN_FOR.items())})


def latin_key(key: str) -> Optional[str]:
    """The Latin key in the same position, or None when no mapping applies."""
    return LATIN_FOR.get(key)
