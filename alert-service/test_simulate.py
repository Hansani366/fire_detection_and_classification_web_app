"""Drive the simulated-fire path over HTTP, in-process.

    python3 -m pytest test_simulate.py -q      (needs fastapi + httpx)

WHAT THIS IS ACTUALLY GUARDING. A canned scenario is only worth anything if it
goes through the same checks a live detection does. The temptation with a demo
endpoint is to hand back a pre-written paragraph, and a pre-written paragraph
would still print "5 of 5 supported" in a demonstration while proving nothing at
all. So the assertions below are about the CHECK, not about the text:

  * every scenario's evidence must genuinely support its own description, which
    is asserted by demanding zero withheld claims -- report.py decided that, not
    scenarios.py;
  * the material claim must resolve against the fuel classifier rather than go
    unsupported, which is only true if the verdict was stored BEFORE the report
    was built (see intake.handle_simulation);
  * a scenario deliberately broken in the test must produce a withheld claim,
    which is what shows the first assertion was not passing by construction.
"""
import os, sys, tempfile
os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(), 'alert.db')
os.environ['SITE_KEY'] = 'industrial'
os.environ['CLEAR_AFTER_SECONDS'] = '999'   # nothing here should auto-resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
import app as service
import scenarios

FAILED = []


def check(label, cond, detail=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + ('' if cond else '  <- ' + str(detail)))
    if not cond:
        FAILED.append(label)


def test_simulated_fires():
  before = len(FAILED)
  with TestClient(service.app) as c:
      cat = c.get('/api/simulate/scenarios').json()['scenarios']
      check('catalogue lists every scenario',
            {s['name'] for s in cat} == set(scenarios.NAMES), cat)
      check('the two classes that cannot be lit indoors are both offered',
            {'gas', 'liquid'} <= {s['name'] for s in cat})

      # Each scenario in its own zone, so none of them lands on another's still
      # open incident and gets deduped into it.
      zones = {'solid': 'fabric-store', 'gas': 'boiler', 'liquid': 'warehouse'}

      for name in scenarios.NAMES:
          r = c.post('/api/simulate',
                     json={'fuel': name, 'zoneId': zones[name], 'occupancy': 3})
          check(f'[{name}] 200', r.status_code == 200, r.text[:160])
          if r.status_code != 200:
              continue
          b = r.json()
          rep = b['report']
          sr = rep['situationReport']

          check(f'[{name}] an incident was opened', b['created'] is True, b)
          check(f'[{name}] the payload says it is simulated', b['simulated'] is True)
          check(f'[{name}] the fuel verdict is stored',
                rep['classification']['fuelType'] == scenarios.get(name)['fuel'],
                rep['classification'])
          check(f'[{name}] the verdict is stamped, so the timeline has a fuel step',
                any('Fuel identified' in t['what'] for t in rep['timeline']),
                [t['what'] for t in rep['timeline']])
          check(f'[{name}] extinguisher guidance came back',
                bool(rep['classification']['response']))

          # THE ONE THAT MATTERS. The material claim is graded against the fuel
          # verdict read off the incident row. If the report were built before
          # the classification (the obvious ordering, and the wrong one), this
          # would be 'unsupported' for every scenario and nobody would notice,
          # because an unsupported claim is still released.
          material = next((cl for cl in sr['claims'] if cl['id'] == 'material'), None)
          check(f'[{name}] material is checked against the classifier',
                material is not None and material['category'] == 'supported',
                material)

          check(f'[{name}] nothing was withheld — the evidence agrees with itself',
                sr['grounding']['contradicted'] == 0, sr['withheld'])
          check(f'[{name}] the people claim matches the head-count it was opened with',
                any(cl['id'] == 'people' and cl['category'] == 'supported'
                    for cl in sr['claims']))
          check(f'[{name}] an escape route was generated',
                rep['route'] is not None, rep.get('routeError'))

      # --- one fire is one incident ---------------------------------------
      again = c.post('/api/simulate',
                     json={'fuel': 'gas', 'zoneId': 'boiler', 'occupancy': 3}).json()
      check('a second simulation in a burning zone reuses the open incident',
            again['reusedExistingIncident'] is True and again['created'] is False, again)

      # --- resolve puts it on the reports page -----------------------------
      done = c.post('/api/simulate',
                    json={'fuel': 'solid', 'zoneId': 'finishing',
                          'occupancy': 2, 'resolve': True}).json()
      hist = c.get('/api/history').json()
      check('a resolved simulation appears in history',
            any(h['id'].replace('h_', '') == done['incidentId'] for h in hist),
            [h['id'] for h in hist])

      # --- bad input --------------------------------------------------------
      check('an unknown fuel is refused',
            c.post('/api/simulate', json={'fuel': 'plasma'}).status_code == 400)
      # An unknown zone falls back to the site default rather than failing, so
      # the dashboard's one hard-coded zone id works on both site files. The
      # response has to say so, or the report names a room nobody asked for.
      fell = c.post('/api/simulate', json={'fuel': 'gas', 'zoneId': 'nowhere'})
      check('an unknown zone falls back to the site default',
            fell.status_code == 200 and fell.json()['zoneId'] == 'fabric-store',
            fell.text[:160])
      check('and the response names the zone that was asked for',
            fell.json()['requestedZoneId'] == 'nowhere', fell.json().get('requestedZoneId'))

  assert len(FAILED) == before, FAILED[before:]


def test_the_grounding_check_can_still_fail():
    """The control for the assertions above.

    "Nothing was withheld" is only evidence that the scenarios are consistent if
    a withholding is possible in the first place. Feed report.py the gas scene
    against the solid fuel verdict and the material claim must be contradicted.
    Without this, a grounding check that had quietly stopped running would pass
    the whole file.
    """
    before = len(FAILED)
    import report as situation

    gas = scenarios.get('gas')
    built = situation.build(
        gas['scene'],
        {**gas['evidence'], 'fuelType': 'solid_combustible', 'occupancy': 0},
        {'id': 'boiler', 'name': 'Boiler Room', 'floor': 'Main floor'})
    material = next(c for c in built['claims'] if c['id'] == 'material')
    check('a mismatched fuel verdict contradicts the material claim',
          material['category'] == 'contradicted', material)
    check('and the contradicted claim is withheld from the released text',
          'propane' not in built['text'], built['text'])
    assert len(FAILED) == before, FAILED[before:]


if __name__ == '__main__':
    test_simulated_fires()
    test_the_grounding_check_can_still_fail()
    print('\n' + ('ALL PASS' if not FAILED else f'{len(FAILED)} FAILED'))
