"""Allowlisted opt-in settings shared by the UI and native mailbox."""
SNOW_THEMES = {'米灰': 'beige', '灰绿': 'sage', '深灰': 'slate'}
WHIRLWIND_MODES = {'减弱': 'soft', '隐藏': 'hidden'}


def comfort_options(settings, usable=True):
    settings = settings if isinstance(settings, dict) else {}
    snow, whirl = settings.get('snow_theme'), settings.get('whirlwind_mode')
    return {
        'snow_theme': snow if usable and isinstance(snow, str) and snow in SNOW_THEMES.values() else 'off',
        'whirlwind_mode': whirl if usable and isinstance(whirl, str) and whirl in WHIRLWIND_MODES.values() else 'off',
        'fast_return': bool(usable and settings.get('fast_return') is True),
    }
