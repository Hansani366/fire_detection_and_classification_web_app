"""Drive every endpoint over HTTP, in-process.

The closest thing to running the service without Docker: this exercises route
registration, serialisation and the async paths, none of which the module-level
tests touch. A typo in a decorator or a serializer would otherwise surface for
the first time at container start.

    python3 -m pytest test_api.py -q      (needs fastapi + httpx)

The watchdog interval is shortened at the top so the resolved state can be
observed; with the 30s default a test asserting "the zone is clear again" is
really asserting that 30 seconds have passed.
"""
import os, sys, tempfile, time
os.environ['DB_PATH'] = os.path.join(tempfile.mkdtemp(), 'alert.db')
os.environ['SITE_KEY'] = 'industrial'
# The auto-clear watchdog normally waits 30s of quiet before resolving an
# incident and returning the zone to clear. Shorten it so a test can observe the
# resolved state instead of asserting against a zone that is still burning.
os.environ['CLEAR_AFTER_SECONDS'] = '0'
os.environ['WATCHDOG_INTERVAL'] = '1'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi.testclient import TestClient
import app as service

FAILED = []


def check(label, cond, detail=''):
    print(('  PASS  ' if cond else '  FAIL  ') + label + ('' if cond else '  <- ' + str(detail)))
    if not cond:
        FAILED.append(label)


def test_api_surface():
  with TestClient(service.app) as c:
      check('health', c.get('/health').json()['status'] == 'ok')
      check('site plan names the active site',
            c.get('/api/site/plan').json()['siteKey'] == 'industrial')

      c.post('/api/devices', json={'token': 'tok_1', 'label': 'phone'})
      c.post('/api/devices', json={'token': 'tok_2', 'label': 'phone2'})

      # --- fire -----------------------------------------------------------
      r = c.post('/api/test-alert', json={'zoneId': 'fabric-store'}).json()
      iid = r['incidentId']
      st = c.get('/api/state').json()
      inc = st['activeIncident']
      check('state carries the incident', inc is not None)
      check('severity + verification on the wire',
            inc['severity'] == 'fire' and inc['verification'] == 'confirmed', inc.get('severity'))
      check('route embedded in the incident', inc['route'] is not None)
      check('the fabric-store fire cuts the north door',
            'exit-north' in inc['route']['blockedExitIds'], inc['route']['blockedExitIds'])
      check('checkout block present and empty', inc['checkout']['checkedOut'] == 0)
      check('allClear is false during a fire', st['allClear'] is False)

      # --- situation report (RO3.1) ---------------------------------------
      # A scene where one claim is confirmed, one cannot be checked, and one is
      # flatly contradicted by the human detector.
      c.post('/api/events/clear', json={'zoneId': 'fabric-store'})
      time.sleep(1.6)
      c.post('/api/events/fire', json={
          'zoneId': 'dyeing', 'type': 'fire', 'confidence': 0.9,
          'description': 'Flames.', 'occupancy': 3,
          'scene': {'material': 'fabric rolls', 'materialFamily': 'solid',
                    'sizeBand': 'small', 'smokePresent': True,
                    'smokeColour': 'black', 'peopleVisible': False,
                    'description': 'Open flames among the rolls.'},
          'evidence': {'fireAreaRatio': 0.03, 'smokeBoxes': 2, 'gasLevel': 'warn'},
      })
      rep = c.get('/api/state').json()['activeIncident']['situationReport']
      check('a situation report is generated', rep is not None)
      ids = {cl['id']: cl['category'] for cl in rep['claims']}
      check('location is system-supplied and supported', ids.get('location') == 'supported', ids)
      check('smoke confirmed by the detector', ids.get('smoke') == 'supported', ids)
      check('"nobody present" is contradicted by the head-count',
            ids.get('people') == 'contradicted', ids)
      check('the contradicted claim is withheld from the released text',
            'people' not in rep['released'] and 'none visible' not in rep['text'], rep['text'])
      check('grounding figures are computed', rep['grounding']['groundingAccuracy'] is not None)
      check('the report announces it was validated before release',
            rep['validatedBeforeRelease'] is True)
      check('an unchecked material claim is marked, not dropped',
            ids.get('material') == 'unsupported' and 'material' in rep['released'], ids)
      c.post('/api/events/clear', json={'zoneId': 'dyeing'})
      time.sleep(1.6)
      r = c.post('/api/test-alert', json={'zoneId': 'fabric-store'}).json()
      iid = r['incidentId']

      # --- check-out ------------------------------------------------------
      a = c.post(f'/api/incidents/{iid}/checkout', json={'token': 'tok_1'}).json()
      b = c.post(f'/api/incidents/{iid}/checkout', json={'token': 'tok_1'}).json()
      check('a repeated check-out counts once', a['checkedOut'] == 1 and b['checkedOut'] == 1,
            (a, b))
      d = c.post(f'/api/incidents/{iid}/checkout', json={'token': 'tok_2'}).json()
      check('a second device counts', d['checkedOut'] == 2, d)
      check('a check-out with no token is refused',
            c.post(f'/api/incidents/{iid}/checkout', json={}).status_code == 400)
      check('state reflects the check-outs',
            c.get('/api/state').json()['activeIncident']['checkout']['checkedOut'] == 2)

      # --- delivery -------------------------------------------------------
      dl = c.post(f'/api/incidents/{iid}/delivered',
                  json={'token': 'tok_1', 'state': 'background'}).json()
      check('delivery round trip closes', dl['matched'] is True and dl['onewayMs'] >= 0, dl)
      unmatched = c.post(f'/api/incidents/{iid}/delivered', json={'token': 'nope'}).json()
      check('an unmatched acknowledgement is accepted, not an error',
            unmatched['matched'] is False)

      # --- route + report -------------------------------------------------
      rt = c.get(f'/api/incidents/{iid}/route').json()
      check('the route record carries the node path', len(rt['route']['pathNodes']) >= 2)
      check('route latency recorded', rt['latencyMs'] is not None)

      c.post('/api/events/clear', json={'zoneId': 'fabric-store'})
      time.sleep(1.6)   # let the auto-clear watchdog tick
      check('the zone returns to clear once the fire stops',
            c.get('/api/state').json()['allClear'] is True)
      rep = c.get(f'/api/incidents/{iid}/report').json()
      check('report carries both occupancy counts',
            rep['checkout']['checkedOut'] == 2 and 'peakOccupancy' in rep['checkout'])
      check('report carries delivery stats', rep['delivery']['acknowledged'] == 1, rep['delivery'])
      check('report timeline is populated', len(rep['timeline']) >= 1)

      # --- warning tier ---------------------------------------------------
      # A zone this test has not touched: a zone that recently cleared is inside
      # the 120s cooldown, and handle_warning honours it.
      w = c.post('/api/test-alert', json={'zoneId': 'warehouse', 'severity': 'warning'}).json()
      inc2 = c.get('/api/state').json()['activeIncident']
      check('a warning is severity=warning', inc2['severity'] == 'warning', inc2['severity'])
      check('a warning carries its readings', inc2['sensorSummary'] != '')
      check('a warning has no route', inc2['route'] is None)
      check('a warning does not turn the zone red',
            c.get('/api/state').json()['allClear'] is True)

      # --- gas danger -----------------------------------------------------
      c.post('/api/events/clear', json={'zoneId': 'warehouse'})
      time.sleep(1.6)
      c.post('/api/test-alert', json={'zoneId': 'boiler', 'severity': 'gas_danger'})
      inc3 = c.get('/api/state').json()['activeIncident']
      check('gas_danger is its own tier', inc3['severity'] == 'gas_danger', inc3['severity'])
      check('gas_danger is not claimed as VLM-verified',
            inc3['verification'] == 'not_applicable', inc3['verification'])
      check('gas_danger still gets a route', inc3['route'] is not None)

      # --- analysis -------------------------------------------------------
      an = c.get('/api/analysis/routes').json()
      check('route analysis returns rows', an['count'] >= 1, an['count'])
      check('hazard intersection rate is zero',
            an['summary']['hazardIntersectionRate'] == 0.0, an['summary'])
      check('validity rate is 1.0', an['summary']['validityRate'] == 1.0, an['summary'])
      dv = c.get('/api/analysis/delivery').json()
      check('delivery analysis returns a median', dv['summary']['p50Ms'] is not None, dv['summary'])
      check('extinguisher table still served', 'fuels' in c.get('/api/extinguishers').json())
      hist = c.get('/api/history').json()
      check('history lists the resolved fire', len(hist) >= 1, len(hist))
      check('history keeps what was burning', 'fuelType' in (hist[0] if hist else {}))

  assert not FAILED, FAILED

