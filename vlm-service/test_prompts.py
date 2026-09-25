"""The two detection settings, checked without calling Gemini.

What counts as a fire depends on the building: a candle is a fire in a
demonstration and an ordinary object in a canteen. The prompts differ in exactly
one clause, and these tests pin that -- if the nuisance guard or the JSON
contract ever drifts between the two, a measured difference between settings
would be a difference between two prompts rather than between two definitions.

Reads the source rather than importing it, so it runs with no GOOGLE_API_KEY:

    python3 -m pytest vlm-service/test_prompts.py -q
"""
import io
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
src = io.open(os.path.join(_HERE, 'main.py'), encoding='utf-8').read()
ns = {'FIRE_MODE_HOME': 'home', 'FIRE_MODE_INDUSTRIAL': 'industrial'}
exec(re.search(r'_MODE_CLAUSE = \{.*?\n\}\n', src, re.S).group(0), ns)
base = re.search(r'FIRE_PROMPT_BASE = """(.*?)"""', src, re.S).group(1)
clause = ns['_MODE_CLAUSE']
render = lambda m: base.replace("{mode_clause}", clause[m])

FAILED = []


def check(label, cond):
    print(('  PASS  ' if cond else '  FAIL  ') + label)
    if not cond:
        FAILED.append(label)


def test_detection_modes():

    check('home mode names candle and lighter',
          all(w in render('home').lower() for w in ('candle', 'lighter')))
    check('industrial mode excludes them from the alarm',
          'do NOT report those' in render('industrial'))
    check('industrial does not tell the model to report a candle',
          'however small' not in render('industrial'))
    check('the JSON contract is identical in both',
          all('{"detected": true, "type": "<one of: fire, smoke, both>"' in render(m)
              for m in ('home', 'industrial')))
    check('the nuisance guard is identical in both',
          all('AIRBORNE DUST' in render(m) and 'STEAM, VAPOUR' in render(m)
              for m in ('home', 'industrial')))
    check('the modes differ in exactly one clause',
          render('home').replace(clause['home'], '')
          == render('industrial').replace(clause['industrial'], ''))
    check('an unknown mode is documented to fall back to industrial',
          'resolved = mode if mode in _MODE_CLAUSE else FIRE_MODE_INDUSTRIAL' in src)
    check('substitution avoids str.format (the prompt contains JSON braces)',
          '.replace("{mode_clause}"' in src)
    assert not FAILED, FAILED

