"""Integration tests against the actual MCP process. No V Rising installation needed."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
DOTNET = 'dotnet'


def bridge_dll():
    """The built bridge, whichever target framework it was compiled for."""
    built = sorted((ROOT / 'src/Bridge/bin/Release').glob('*/VampireCompanion.Mcp.dll'),
                   key=lambda p: p.stat().st_mtime)
    if not built:
        raise SystemExit('Passerelle non compilée : lance dotnet build sur src/Bridge.')
    return built[-1]


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.now = dt.datetime.now(dt.timezone.utc)
        stamp = self.now.isoformat()
        self.snapshot = {
            'schemaVersion': 1, 'sessionId': 'synthetic-test-session',
            'capturedAt': stamp, 'connected': True,
            'inventories': [
                {'id': 'bag', 'name': 'Sac', 'kind': 'player', 'observedAt': stamp,
                 'observing': True, 'items': [{'guid': 11, 'name': 'Bois', 'amount': 90}]},
                {'id': 'chest', 'name': 'Coffre', 'kind': 'container', 'observedAt': stamp,
                 'observing': False, 'items': [{'guid': 11, 'name': 'Bois', 'amount': 500}]}],
            'recipes': [{'guid': 22, 'name': 'Planche', 'unlocked': True,
                         'inputs': [{'guid': 11, 'name': 'Bois', 'amount': 100}],
                         'outputs': [{'guid': 33, 'name': 'Planche', 'amount': 1}]}],
            'stations': [{'id': 'station', 'name': 'Scierie de test', 'observing': True,
                          'observedAt': stamp, 'matchingFloor': True, 'confinedRoom': True,
                          'recipes': [22], 'queue': [], 'effectiveRecipes': [
                              {'guid': 22, 'source': 'workstation_ui', 'seconds': 15,
                               'inputs': [{'guid': 11, 'name': 'Bois', 'amount': 75}]}]}]
        }
        self.save()
        self.process = subprocess.Popen(
            [DOTNET, str(bridge_dll()), '--data-dir', str(self.directory)], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        self.seq = 0
        result = self.rpc('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                        'clientInfo': {'name': 'test', 'version': '1'}})
        self.assertEqual(result['result']['protocolVersion'], '2025-06-18')

    def tearDown(self):
        self.process.stdin.close()
        self.process.wait(timeout=5)
        self.assertEqual(self.process.returncode, 0, self.process.stderr.read())
        self.process.stdout.close()
        self.process.stderr.close()
        self.temp.cleanup()

    def save(self):
        (self.directory / 'snapshot.json').write_text(json.dumps(self.snapshot), encoding='utf-8')

    def rpc(self, method, params=None):
        self.seq += 1
        message = {'jsonrpc': '2.0', 'id': self.seq, 'method': method, 'params': params or {}}
        self.process.stdin.write(json.dumps(message) + '\n')
        self.process.stdin.flush()
        reply = json.loads(self.process.stdout.readline())
        self.assertEqual(reply['id'], self.seq)
        return reply

    def tool(self, name, **args):
        result = self.rpc('tools/call', {'name': name, 'arguments': args})['result']
        self.assertFalse(result['isError'], result)
        return json.loads(result['content'][0]['text'])

    def test_tool_discovery_and_notifications(self):
        self.process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        self.process.stdin.flush()
        tools = self.rpc('tools/list')['result']['tools']
        self.assertEqual(len(tools), 19)
        self.assertTrue(all(t['annotations']['readOnlyHint'] for t in tools))

    def test_filters_and_pagination(self):
        result = self.tool('find_stock', query='bois', limit=1)['data']
        self.assertEqual(result['total'], 2)
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['nextOffset'], 1)
        result = self.tool('find_stock', query='bois', offset=1)['data']['results'][0]
        self.assertEqual(result['state'], 'last_observed')

    def test_effective_station_costs_and_cached_exclusion(self):
        plan = self.tool('plan_craft', recipeGuid=22, stationId='station', batches=2)['data']
        self.assertEqual(plan['materials'][0]['needed'], 150)
        self.assertEqual(plan['materials'][0]['missing'], 60)
        self.assertFalse(plan['canCraft'])
        self.assertEqual(plan['seconds'], 30)

    def test_cached_estimates_never_confirm(self):
        plan = self.tool('plan_craft', recipeGuid=22, stationId='station', batches=2, includeCached=True)['data']
        self.assertTrue(plan['materialsSufficient'])
        self.assertIsNone(plan['canCraft'])
        self.assertFalse(plan['canConfirm'])

    def test_dead_game_does_not_report_live_stock(self):
        self.snapshot['capturedAt'] = (self.now - dt.timedelta(minutes=1)).isoformat()
        self.save()
        result = self.tool('find_stock')
        self.assertFalse(result['fresh'])
        self.assertTrue(all(r['state'] == 'last_observed' for r in result['data']['results']))

    def test_unverified_costs_and_unknown_unlock_never_confirm(self):
        self.snapshot['stations'][0]['effectiveRecipes'][0]['source'] = 'refinement_ui_multiplier; rounding_requires_ingame_validation'
        self.save()
        self.assertIsNone(self.tool('plan_craft', recipeGuid=22, stationId='station')['data']['canCraft'])
        self.snapshot['stations'][0]['effectiveRecipes'][0]['source'] = 'workstation_ui'
        self.snapshot['recipes'][0]['unlocked'] = None
        self.save()
        self.assertFalse(self.tool('plan_craft', recipeGuid=22, stationId='station')['data']['canConfirm'])

    def test_unknown_costs_are_not_fabricated(self):
        self.snapshot['stations'][0]['effectiveRecipes'] = []
        self.save()
        self.assertFalse(self.tool('plan_craft', recipeGuid=22, stationId='station')['data']['canConfirm'])

    def test_refresh_timeout_is_explicit(self):
        result = self.tool('refresh')
        self.assertFalse(result['refreshed'])
        self.assertTrue((self.directory / 'request.json').exists())

    def test_refresh_acknowledgement_and_session_replacement(self):
        def reply():
            request = self.directory / 'request.json'
            for _ in range(100):
                if request.exists():
                    self.snapshot['requestId'] = json.loads(request.read_text())['id']
                    self.snapshot['sessionId'] = 'new-test-session'
                    self.snapshot['inventories'] = []
                    self.save()
                    return
                time.sleep(.01)
        worker = threading.Thread(target=reply)
        worker.start()
        try:
            self.assertTrue(self.tool('refresh')['refreshed'])
        finally:
            worker.join(timeout=2)
        result = self.tool('find_stock')
        self.assertEqual(result['sessionId'], 'new-test-session')
        self.assertEqual(result['data']['total'], 0)

    def test_stock_totals_keep_memory_separate(self):
        totals = self.tool('summarize_stock', query='bois')['data']['results'][0]
        self.assertEqual(totals['observedNow'], 90)
        self.assertEqual(totals['lastObserved'], 500)
        self.assertEqual(totals['recentContainers'], 1)
        self.snapshot['capturedAt'] = (self.now - dt.timedelta(minutes=1)).isoformat()
        self.save()
        totals = self.tool('summarize_stock')['data']['results'][0]
        self.assertEqual(totals['observedNow'], 0)
        self.assertEqual(totals['lastObserved'], 590)

    def test_stale_observation_with_fresh_heartbeat(self):
        self.snapshot['inventories'][0]['observedAt'] = (self.now - dt.timedelta(minutes=1)).isoformat()
        self.snapshot['stations'][0]['observedAt'] = (self.now - dt.timedelta(minutes=1)).isoformat()
        self.save()
        self.assertEqual(self.tool('find_stock', query='bois')['data']['results'][0]['state'], 'last_observed')
        self.assertIsNone(self.tool('plan_craft', recipeGuid=22, stationId='station')['data']['canCraft'])
        self.assertEqual(self.tool('summarize_stock')['data']['results'][0]['observedNow'], 0)

    def test_project_shares_stock_once_across_targets(self):
        target = dict(recipeGuid=22, stationId='station', batches=1)
        result = self.tool('plan_project', targets=[target, target])['data']
        self.assertEqual(result['materials'][0]['needed'], 150)
        self.assertEqual(result['materials'][0]['missing'], 60)
        self.assertFalse(result['materialsSufficient'])
        self.assertEqual(result['sequentialWorkSeconds'], 30)
        result = self.tool('plan_project', targets=[target, target], includeCached=True)['data']
        self.assertTrue(result['materialsSufficient'])
        self.assertFalse(result['reliableIngredientsCheck'])

    def test_project_unknown_costs_and_unlocks(self):
        self.snapshot['stations'][0]['effectiveRecipes'] = []
        self.snapshot['recipes'][0]['unlocked'] = None
        self.save()
        result = self.tool('plan_project', targets=[dict(recipeGuid=22, stationId='station')])['data']
        self.assertFalse(result['completeCosts'])
        self.assertIsNone(result['materialsSufficient'])
        self.assertIsNone(result['sequentialWorkSeconds'])
        self.assertEqual(len(result['blockers']), 2)

    def test_project_does_not_reuse_future_outputs(self):
        self.snapshot['recipes'].append({'guid': 44, 'name': 'Meuble', 'unlocked': True,
            'inputs': [{'guid': 33, 'name': 'Planche', 'amount': 1}], 'outputs': []})
        self.snapshot['stations'][0]['recipes'].append(44)
        self.snapshot['stations'][0]['effectiveRecipes'].append({'guid': 44,
            'source': 'workstation_ui', 'seconds': 5, 'inputs': [{'guid': 33, 'name': 'Planche', 'amount': 1}]})
        self.save()
        result = self.tool('plan_project', targets=[dict(recipeGuid=22, stationId='station'),
            dict(recipeGuid=44, stationId='station')])['data']
        self.assertEqual(next(m for m in result['materials'] if m['guid'] == 33)['missing'], 1)

    def test_comparison_cost_savings_and_capacity(self):
        result = self.tool('compare_recipe_stations', recipeGuid=22)['data']['results'][0]
        self.assertEqual(result['maxBatchesByIngredients'], 1)
        self.assertEqual(result['materials'][0]['savedPerBatch'], 25)
        self.assertTrue(result['costsVerified'])
        result = self.tool('compare_recipe_stations', recipeGuid=22, includeCached=True)['data']['results'][0]
        self.assertEqual(result['maxBatchesByIngredients'], 7)

    def test_duplicate_ingredients_are_combined(self):
        self.snapshot['stations'][0]['effectiveRecipes'][0]['inputs'].append({'guid': 11, 'name': 'Bois', 'amount': 75})
        self.save()
        result = self.tool('compare_recipe_stations', recipeGuid=22)['data']['results'][0]
        self.assertEqual(result['maxBatchesByIngredients'], 0)
        self.assertEqual(self.tool('plan_craft', recipeGuid=22, stationId='station')['data']['materials'][0]['missing'], 60)

    def test_comparison_unknown_costs_not_zero_or_free(self):
        self.snapshot['stations'][0]['effectiveRecipes'] = []
        self.save()
        result = self.tool('compare_recipe_stations', recipeGuid=22)['data']['results'][0]
        self.assertIsNone(result['maxBatchesByIngredients'])
        self.assertIsNone(result['materials'])
        self.assertFalse(result['costsAvailable'])

    def test_station_audit_unknown_is_not_missing(self):
        self.snapshot['stations'][0]['matchingFloor'] = False
        self.snapshot['stations'][0]['confinedRoom'] = None
        self.save()
        result = self.tool('audit_stations')['data']['results'][0]
        self.assertEqual(len(result['checks']), 2)
        result = self.tool('get_overview')['data']['stations']
        self.assertEqual(result['missingFloorAtLastObservation'], 1)
        self.assertEqual(result['missingRoomAtLastObservation'], 0)
        self.assertEqual(result['unknownBonuses'], 1)

    def test_container_search_accents_and_distance(self):
        self.snapshot['inventories'][1]['name'] = 'Réserve'
        self.snapshot['inventories'][1]['position'] = [3, 0, 4]
        self.snapshot['player'] = {'name': 'Test', 'position': [0, 0, 0], 'details': {}}
        self.save()
        result = self.tool('list_containers', query='reserve')['data']['results'][0]
        self.assertEqual(result['distanceFromPlayer'], 5)
        self.assertEqual(result['state'], 'last_observed')
        result = self.tool('list_containers', query='bois', limit=1)['data']
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['nextOffset'], 1)

    def test_new_tools_reject_invalid_inputs_and_recover(self):
        for name, args in [('plan_project', {'targets': []}),
                           ('plan_project', {'targets': [None]}),
                           ('plan_project', {'targets': [{'recipeGuid': 22, 'stationId': 'station', 'batches': '2'}]}),
                           ('compare_recipe_stations', {'recipeGuid': 999}),
                           ('summarize_stock', {'limit': 'bad'})]:
            result = self.rpc('tools/call', {'name': name, 'arguments': args})['result']
            self.assertTrue(result['isError'], result)
        self.assertIn('data', self.tool('get_overview'))

    def shared(self, **overrides):
        self.snapshot['sharedInventory'] = dict(managerId='castle-a', observedAt=self.now.isoformat(),
            accessible=True, instanceCount=2, items=[{'guid': 11, 'name': 'Bois', 'amount': 500}])
        self.snapshot['sharedInventory'].update(overrides)
        self.snapshot['sharedInventoryStatus'] = 'observed'
        self.save()

    def test_shared_inventory_read_without_chests(self):
        self.snapshot['inventories'] = []
        self.shared()
        result = self.tool('get_shared_inventory', query='bois')['data']
        self.assertTrue(result['availableNow'])
        self.assertEqual(result['items']['results'][0]['amount'], 500)
        self.assertEqual(self.tool('summarize_stock')['data']['results'][0]['observedNow'], 500)

    def test_shared_dedup_in_all_calculators(self):
        self.snapshot['inventories'][1]['observing'] = True
        self.shared()
        result = self.tool('summarize_stock')
        self.assertEqual(result['data']['results'][0]['observedNow'], 590)
        self.assertEqual(result['accounting']['excludedContainers'], 1)
        plan = self.tool('plan_craft', recipeGuid=22, stationId='station', batches=10, includeCached=True)['data']
        self.assertEqual(plan['materials'][0]['missing'], 160)
        project = self.tool('plan_project', targets=[dict(recipeGuid=22, stationId='station', batches=10)])['data']
        self.assertEqual(project['materials'][0]['missing'], 160)
        comparison = self.tool('compare_recipe_stations', recipeGuid=22)['data']['results'][0]
        self.assertEqual(comparison['maxBatchesByIngredients'], 7)
        sources = self.tool('find_stock', query='bois')['data']['results']
        self.assertEqual(len(sources), 3)
        self.assertFalse(next(x for x in sources if x['inventoryId'] == 'chest')['includedInTotals'])

    def test_shared_leaving_territory_retains_only_memory(self):
        self.shared(accessible=False)
        self.snapshot['sharedInventoryStatus'] = 'no_character_connection'
        self.save()
        result = self.tool('get_shared_inventory')['data']
        self.assertFalse(result['availableNow'])
        self.assertEqual(result['state'], 'last_observed')
        totals = self.tool('summarize_stock')['data']['results'][0]
        self.assertEqual(totals['observedNow'], 90)
        self.assertEqual(totals['lastObserved'], 500)
        plan = self.tool('plan_craft', recipeGuid=22, stationId='station', batches=2)['data']
        self.assertEqual(plan['materials'][0]['missing'], 60)

    def test_shared_stale_and_disconnected(self):
        self.shared(observedAt=(self.now - dt.timedelta(minutes=1)).isoformat())
        self.assertFalse(self.tool('get_shared_inventory')['data']['availableNow'])
        self.shared()
        self.snapshot['connected'] = False
        self.save()
        self.assertFalse(self.tool('get_shared_inventory')['data']['availableNow'])
        self.assertEqual(self.tool('summarize_stock')['data']['results'][0]['observedNow'], 0)

    def test_shared_unknown_and_empty_are_distinct(self):
        self.assertEqual(self.tool('get_shared_inventory')['data']['state'], 'unknown')
        self.shared(items=[])
        result = self.tool('get_shared_inventory')['data']
        self.assertTrue(result['availableNow'])
        self.assertEqual(result['items']['total'], 0)
        self.assertEqual(self.tool('summarize_stock')['data']['results'][0]['lastObserved'], 0)

    def test_shared_castle_switch_replaces_previous_totals(self):
        self.shared()
        self.shared(managerId='castle-b', items=[{'guid': 11, 'name': 'Bois', 'amount': 10}])
        self.assertEqual(self.tool('summarize_stock')['data']['results'][0]['observedNow'], 100)
        self.assertEqual(self.tool('get_shared_inventory')['data']['managerId'], 'castle-b')

    def character(self):
        """Synthetic character state. PhysicalPower is 100 with 50 explained by gear and
        buffs, so the remaining 50 must show up as unexplained rather than be hidden."""
        self.snapshot['schemaVersion'] = 2
        self.snapshot['stats'] = {'unreadable': ['UnknownStruct'], 'values': [
            {'field': 'PhysicalPower', 'label': 'Puissance physique', 'value': 100.0},
            {'field': 'SpellPower', 'label': 'Puissance magique', 'value': 80.0},
            {'field': 'PhysicalCriticalStrikeChance',
             'label': 'Chance de coup critique physique', 'value': 0.2},
            {'field': 'PhysicalCriticalStrikeDamage',
             'label': 'Dégâts de coup critique physique', 'value': 1.5},
            {'field': 'MovementSpeed', 'label': 'Vitesse de déplacement', 'value': 0.0},
            {'field': 'a', 'label': None, 'value': 0.35}]}
        self.snapshot['blood'] = {'typeGuid': 7, 'typeName': 'Guerrier', 'quality': 87.5,
                                  'amount': 62.0, 'maxAmount': None}
        self.snapshot['equipment'] = [
            {'slot': 'WeaponSlot', 'guid': 101, 'name': 'Épée de test', 'durability': 90.0,
             'maxDurability': 100.0, 'legendaryTier': 2, 'infusionGuid': 5,
             'infusionName': 'Illusion', 'bonusSource': 'item_instance',
             'statMods': [{'guid': 9, 'name': 'Mod de test', 'power': 0.4}],
             'bonuses': [{'stat': 'PhysicalPower', 'label': 'Puissance physique',
                          'value': 30.0, 'modification': 'AddToBase'}]},
            {'slot': 'RingSlot', 'guid': 102, 'name': 'Anneau de test', 'durability': None,
             'maxDurability': None, 'legendaryTier': None, 'infusionGuid': None,
             'infusionName': None, 'bonusSource': 'item_prefab', 'statMods': [],
             'bonuses': [{'stat': 'PhysicalPower', 'label': 'Puissance physique',
                          'value': 12.0, 'modification': 'AddToBase'},
                         {'stat': 'SpellCriticalStrikeChance', 'label': None,
                          'value': 0.05, 'modification': 'AddToBase'}]},
            {'slot': 'CloakSlot', 'guid': 0, 'name': 'aucun', 'durability': None,
             'maxDurability': None, 'legendaryTier': None, 'infusionGuid': None,
             'infusionName': None, 'bonuses': [], 'bonusSource': 'empty_slot', 'statMods': []}]
        self.snapshot['buffs'] = [
            {'guid': 201, 'name': 'Potion de test', 'totalSeconds': 600.0,
             'remainingSeconds': 120.0, 'permanent': False,
             'bonuses': [{'stat': 'PhysicalPower', 'label': 'Puissance physique',
                          'value': 8.0, 'modification': 'AddToBase'}]},
            {'guid': 202, 'name': 'Bonus de sang', 'totalSeconds': None,
             'remainingSeconds': None, 'permanent': True,
             'bonuses': [{'stat': 'MovementSpeed', 'label': 'Vitesse de déplacement',
                          'value': 0.1, 'modification': 'Multiply'}]}]
        self.snapshot['spells'] = [
            {'index': 0, 'groupGuid': 301, 'groupName': 'Boule de sang', 'modsReadable': True,
             'mods': [{'guid': 401, 'name': 'Joyau de test', 'power': 0.75}]},
            {'index': 1, 'groupGuid': 302, 'groupName': 'Voile', 'modsReadable': False,
             'mods': []}]
        self.snapshot['capabilities'] = {'stats': 'observed', 'buffs': 'observed'}
        self.save()

    def test_character_keeps_zero_stats_and_invents_no_blood_maximum(self):
        self.character()
        data = self.tool('get_character')['data']
        self.assertEqual(data['state'], 'observed_now')
        self.assertEqual(data['stats']['total'], 6)
        self.assertEqual(data['stats']['results'][0]['field'], 'PhysicalCriticalStrikeChance')
        last = self.tool('get_character', offset=5)['data']['stats']['results'][0]
        self.assertEqual(last['field'], 'MovementSpeed')
        self.assertEqual(last['value'], 0.0)
        self.assertEqual(data['unreadableStatFields'], ['UnknownStruct'])
        self.assertEqual(data['blood']['qualityPercent'], 87.5)
        self.assertIsNone(data['blood']['amountPercent'])
        self.assertIsNotNone(data['blood']['note'])
        self.assertEqual(data['equipment']['filled'], 2)
        self.assertEqual(data['buffs']['temporary'], 1)
        self.assertIsNone(data['spells'][1]['jewels'])

    def test_contributions_are_never_added_on_top_of_final_stats(self):
        self.character()
        data = self.tool('explain_stat', query='PhysicalPower')['data']
        self.assertEqual(data['finalValue'], 100.0)
        self.assertEqual(data['contributionCount'], 3)
        self.assertTrue(data['additiveOnly'])
        self.assertEqual(data['sumOfContributions'], 50.0)
        self.assertEqual(data['unexplainedRemainder'], 50.0)
        self.assertFalse(next(c for c in data['contributions'] if c['origin'] == 'RingSlot')['reliable'])

    def test_mixed_modification_types_are_not_summed(self):
        self.character()
        data = self.tool('explain_stat', query='vitesse de déplacement')['data']
        self.assertEqual(data['finalValue'], 0.0)
        self.assertFalse(data['additiveOnly'])
        self.assertIsNone(data['sumOfContributions'])
        self.assertIsNone(data['unexplainedRemainder'])

    def test_obfuscated_stat_is_reported_as_unlinked_not_as_zero(self):
        self.character()
        data = self.tool('explain_stat', query='SpellCriticalStrikeChance')['data']
        self.assertIsNone(data['finalValue'])
        self.assertEqual(data['contributionCount'], 1)
        self.assertTrue(any('obfusqu' in note for note in data['notes']))

    def test_equipment_marks_prefab_bonuses_and_empty_slots(self):
        self.character()
        data = self.tool('get_equipment')['data']
        weapon = next(s for s in data['slots']['results'] if s['slot'] == 'WeaponSlot')
        self.assertEqual(weapon['durabilityPercent'], 90.0)
        self.assertEqual(weapon['legendaryTier'], 2)
        self.assertEqual(weapon['infusion'], 'Illusion')
        self.assertTrue(weapon['bonusesReliable'])
        ring = next(s for s in data['slots']['results'] if s['slot'] == 'RingSlot')
        self.assertFalse(ring['bonusesReliable'])
        self.assertIn('modèle', ring['note'])
        cloak = next(s for s in data['slots']['results'] if s['slot'] == 'CloakSlot')
        self.assertFalse(cloak['equipped'])
        self.assertFalse(data['spells'][1]['jewelsReadable'])
        self.assertIsNotNone(data['spells'][1]['note'])

    def test_buffs_separate_permanent_from_expiring(self):
        self.character()
        results = self.tool('get_buffs')['data']['buffs']['results']
        self.assertEqual(results[0]['name'], 'Potion de test')
        self.assertEqual(results[0]['remainingSeconds'], 120.0)
        self.assertTrue(results[1]['permanent'])
        self.assertIsNone(results[1]['remainingSeconds'])

    def test_damage_without_supplied_inputs_returns_no_number(self):
        self.character()
        data = self.tool('estimate_damage', kind='physical')['data']
        self.assertFalse(data['certain'])
        self.assertEqual(data['observed']['power'], 100.0)
        self.assertEqual(data['critMultiplier']['value'], 1.5)
        self.assertEqual(data['critMultiplier']['alternative'], 2.5)
        self.assertAlmostEqual(data['critMultiplier']['expectedPerHitMultiplier'], 1.1)
        self.assertIsNone(data['estimate']['hitWithoutCrit'])
        self.assertIsNone(data['estimate']['damagePerSecond'])
        self.assertEqual(len(data['missingInputs']), 2)

    def test_damage_uses_supplied_coefficient_and_interval(self):
        self.character()
        data = self.tool('estimate_damage', kind='physical', coefficient=2,
                         intervalSeconds=1.5)['data']
        self.assertEqual(data['estimate']['hitWithoutCrit'], 200.0)
        self.assertEqual(data['estimate']['averageHitWithCrit'], 220.0)
        self.assertAlmostEqual(data['estimate']['damagePerSecond'], 146.67, places=2)
        self.assertEqual(data['missingInputs'], [])
        self.assertFalse(data['certain'])
        plain = self.tool('estimate_damage', kind='physical', coefficient=2,
                          includeCrit=False)['data']
        self.assertIsNone(plain['estimate']['averageHitWithCrit'])

    def test_damage_reports_a_missing_stat_instead_of_assuming_zero(self):
        self.character()
        data = self.tool('estimate_damage', kind='spell', coefficient=2)['data']
        self.assertEqual(data['observed']['power'], 80.0)
        self.assertIsNone(data['observed']['criticalChance'])
        self.assertEqual(data['estimate']['hitWithoutCrit'], 160.0)
        self.assertIsNone(data['estimate']['averageHitWithCrit'])
        self.assertTrue(any('SpellCriticalStrikeChance' in m for m in data['missingInputs']))
        for args in [{'kind': 'melee'}, {'kind': 'physical', 'coefficient': 0},
                     {'kind': 'physical', 'intervalSeconds': -1}]:
            self.assertTrue(self.rpc('tools/call', {'name': 'estimate_damage',
                                                    'arguments': args})['result']['isError'])

    def test_old_snapshot_reports_absence_rather_than_empty_values(self):
        data = self.tool('get_character')['data']
        self.assertFalse(data['blood']['available'])
        self.assertEqual(data['stats']['total'], 0)
        self.assertEqual(data['equipment']['slots'], 0)
        self.assertTrue(self.rpc('tools/call', {'name': 'estimate_damage',
                                                'arguments': {'kind': 'physical'}})['result']['isError'])

    def test_unknown_schema_version_is_refused(self):
        self.snapshot['schemaVersion'] = 3
        self.save()
        result = self.rpc('tools/call', {'name': 'get_character', 'arguments': {}})['result']
        self.assertTrue(result['isError'])
        self.assertIn('version', result['content'][0]['text'].lower())

    def test_errors_and_recovery(self):
        bad = self.rpc('tools/call', {'name': 'plan_craft', 'arguments': {'recipeGuid': 22, 'stationId': 'station', 'batches': -1}})
        self.assertTrue(bad['result']['isError'])
        self.assertEqual(self.rpc('missing-method')['error']['code'], -32601)
        self.process.stdin.write('broken json\n')
        self.process.stdin.flush()
        self.assertEqual(json.loads(self.process.stdout.readline())['error']['code'], -32700)
        self.assertIn('result', self.rpc('ping'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dotnet', default='dotnet')
    opts, rest = parser.parse_known_args()
    DOTNET = opts.dotnet
    subprocess.run([DOTNET, 'build', str(ROOT / 'src/Bridge/VampireCompanion.Mcp.csproj'),
                    '-c', 'Release', '-v', 'quiet'], check=True)
    unittest.main(argv=['test_bridge.py'] + rest)
