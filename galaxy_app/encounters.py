"""Named starting conditions for the existing mutual-gravity engine.

These profiles set initial conditions only. Their names do not promise a
merger, a bridge, or any particular future galaxy shape.
"""
from __future__ import annotations

import math
from typing import Mapping, Any


PHYSICAL_KEYS = ('impact', 'speed', 'massratio', 'inclination', 'spin', 'isolated')


def _config(impact=1.6, speed=.9, massratio=1., inclination=25., spin=1,
            isolated=False):
    return dict(impact=impact, speed=speed, massratio=massratio,
                inclination=inclination, spin=spin, isolated=isolated)


PRESETS = (
    dict(id='sidepass', label='مرور جانبي', name='Side pass',
         description='مرور متقارب بين مجرّتين متشابهتين؛ راقب تغيّر الأذرع والنجوم عند اللقاء.',
         config=_config()),
    dict(id='slowclose', label='اقتراب بطيء', name='Slow approach',
         description='بداية أبطأ ومرور أقرب؛ قارن كيف يغيّر زمن التفاعل شكل المجرّتين.',
         config=_config(impact=.65, speed=.65, inclination=20.)),
    dict(id='fastflyby', label='عبور سريع', name='Fast flyby',
         description='بداية أسرع ومسافة مرور أوسع؛ قارنها بالاقتراب البطيء.',
         config=_config(impact=2.6, speed=1.65)),
    dict(id='unequalmass', label='مجرّة كبيرة وأخرى أصغر', name='Unequal galaxies',
         description='المجرّة ب أقل كتلة؛ راقب اختلاف استجابة المجرّتين للجاذبية.',
         config=_config(impact=1.8, speed=.85, massratio=.6)),
    dict(id='tilted', label='لقاء مائل', name='Tilted encounter',
         description='قرص المجرّة ب مائل أكثر؛ دوّر الكاميرا لاستكشاف البنية الثلاثية الأبعاد.',
         config=_config(inclination=65.)),
    dict(id='retrograde', label='دوران متعاكس', name='Opposite rotation',
         description='المجرّة ب تدور بالاتجاه المعاكس؛ قارن أثر اتجاه الدوران على البنية الناتجة.',
         config=_config(spin=-1)),
    dict(id='isolated', label='مجرّة منفردة', name='Isolated galaxy',
         description='تجربة مقارنة بمجرّة واحدة: شاهد حركتها من دون جاذبية مجرّة ثانية.',
         config=_config(inclination=0., isolated=True)),
)


def get_preset(preset_id: str) -> dict[str, Any]:
    """Return an independent preset, so UI edits cannot mutate the catalogue."""
    for preset in PRESETS:
        if preset['id'] == preset_id:
            return {**preset, 'config':dict(preset['config'])}
    raise KeyError(f'Unknown encounter preset: {preset_id}')


def apply_preset(config: Mapping[str, Any], preset_id: str) -> dict[str, Any]:
    """Replace physical conditions while retaining quality, seed and renderer."""
    return {**config, **get_preset(preset_id)['config']}


def match_config(config: Mapping[str, Any]) -> str:
    """Identify a profile by its physical controls, ignoring quality and seed.

    Slider values are quantized to hundredths for impact/speed/mass and whole
    degrees for inclination. Tolerances absorb only floating-point roundoff;
    a meaningful slider change selects ``custom`` rather than a nearby profile.
    """
    if not all(key in config for key in PHYSICAL_KEYS):
        return 'custom'
    try:
        numeric={key:float(config[key]) for key in PHYSICAL_KEYS[:-1]}
        if not all(math.isfinite(value) for value in numeric.values()):
            return 'custom'
        spin=-1 if numeric['spin'] < 0 else 1
        for preset in PRESETS:
            expected=preset['config']
            if (bool(config['isolated']) == expected['isolated'] and
                    spin == expected['spin'] and
                    all(math.isclose(numeric[key], expected[key], rel_tol=0., abs_tol=1e-8)
                        for key in ('impact','speed','massratio','inclination'))):
                return preset['id']
    except (TypeError, ValueError, OverflowError):
        pass
    return 'custom'
