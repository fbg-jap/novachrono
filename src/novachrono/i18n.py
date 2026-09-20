from typing import Final

DEFAULT_LOCALE: Final = "de_DE"

SUPPORTED_LOCALES: Final = (
    "de_DE",
    "en_US",
)

_TRANSLATIONS: Final = {
    "de_DE": {
        "weather.title": "WETTER",
        "mail.title": "E-MAIL",
    },
    "en_US": {
        "weather.title": "WEATHER",
        "mail.title": "MAIL",
    },
}


def translate(
    key: str,
    *,
    locale: str,
) -> str:
    """Return a translated UI string."""

    translations = _TRANSLATIONS.get(locale, _TRANSLATIONS[DEFAULT_LOCALE])
    return translations.get(key, key)
