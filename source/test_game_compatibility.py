"""Regressions grounded in the installed build 25347683 enums and equipment."""
import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest

from gear_view import catalog_data, select_sections
from lock_library import LockLibrary, selected_indices
from overlay_feed import OverlayFeed
from overlay_markers import marker_slots
import test_auto_recycle as recycle_fixture


def gear(name='冰原腰带', index=0, quality=4, tier=10, skill=73, locked=False):
    return {'index': index, 'item': {
        '物品类型': 1, 'ID': index + 900, '数量': 1, '难度': 2, '锁定': locked,
        '名字': name, '品质': quality, '等阶': tier, '技能1': skill,
        '基础属性': {}, '特殊属性': {}, '极品属性': {},
    }}


class OfficialCatalogTests(unittest.TestCase):
    def test_perfect_is_four_and_fine_is_not_perfect(self):
        rows = catalog_data()['equipment']
        for value, label in ((0, '普通'), (1, '破损'), (2, '陈旧'), (3, '精良'), (4, '完美')):
            with self.subTest(value=value, label=label):
                candidate = gear(quality=value)['item']
                self.assertTrue(LockLibrary(rows, {'qualities': [label]}).matches(candidate))
                self.assertEqual(LockLibrary(rows, {'qualities': ['完美']}).matches(candidate), value == 4)
        self.assertFalse(LockLibrary(rows, {'qualities': ['完美']}).matches(gear(quality=5)['item']))

    def test_new_equipment_can_be_selected_by_stable_key_and_live_value(self):
        config = {'schema': 2, 'rules': [{
            'qualities': ['完美'], 'quality_tiers': [10],
            'equipment_keys': ['10:7:冰原腰带'], 'upper': True, 'upper_ids': [73],
        }]}
        self.assertEqual(selected_indices([gear()], config), {0})
        for change in (dict(quality=3), dict(tier=9), dict(skill=0), dict(skill=9)):
            with self.subTest(change=change):
                self.assertEqual(selected_indices([gear(**change)], config), set())

    def test_official_set_membership_is_used_instead_of_name_prefix(self):
        rows = catalog_data()['equipment']
        for name, tier, belongs in (('冰原腰带', 10, True), ('雷云法袍', 9, True),
                                    ('星陨戒指', 10, False), ('灭世甲', 10, False),
                                    ('冥墟头盔', 10, False)):
            with self.subTest(name=name):
                candidate = gear(name=name, tier=tier)['item']
                for mode, wanted in (('set', belongs), ('non_set', not belongs)):
                    self.assertEqual(LockLibrary(rows, {'keep_all': True, 'set_mode': mode}).matches(candidate), wanted)

    def test_selected_new_upper_skills_include_belt_and_boots_only_at_chosen_tier(self):
        items = [gear(index=0), gear(name='冰原长靴', index=1, skill=9)]
        selected = select_sections({'items': items}, [], {'legendary_pairs': ['10:7', '10:8']})
        self.assertEqual([x['index'] for x in selected['legendary']], [0, 1])
        self.assertEqual(select_sections({'items': items}, [], {'legendary_pairs': ['9:7', '9:8']})['legendary'], [])
        items[0]['item']['技能1'] = 0
        items[0]['item']['极品属性'] = {'技能1': 73}
        self.assertEqual([x['index'] for x in select_sections({'items': items}, [],
            {'legendary_pairs': ['10:7', '10:8']})['legendary']], [1])


class MatchingPipelineTests(unittest.TestCase):
    def test_hiding_locked_affixes_does_not_remove_rule_recycle_protection(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            item = gear(name='霄引', skill=64, locked=True)
            item['item']['极品属性'] = {'特殊属性': {'暴击伤害': 51}}
            settings = {'native': {'lock': True}, 'lock_library': {'schema': 2, 'rules': [
                {'qualities': ['完美'], 'quality_tiers': [10], 'upper': True, 'filter_sections': ['numeric']}]}}
            values = {'continuous-status.json': {'status': 'watching', 'game_pid': 123,
                          'heartbeat_utc': dt.datetime.now(dt.timezone.utc).isoformat()},
                      'current-loot.json': {'status': 'watching', 'items': [item]},
                      'loot-overlay-settings.json': settings,
                      'loot-filter-rules.json': [{'group': '特殊属性', 'field': '暴击伤害', 'min': 50, 'enabled': True}]}
            for name, value in values.items():
                (directory / name).write_text(json.dumps(value), encoding='utf8')
            feed = OverlayFeed(directory, start=False)
            try:
                feed.poll()
                self.assertEqual(feed.snapshot.sections['numeric'], [])
                self.assertEqual(feed.snapshot.protected_slots, frozenset({0}))
                self.assertEqual(marker_slots(feed.snapshot.sections, {}), [])
                item['item']['极品属性']['特殊属性']['暴击伤害'] = 49
                (directory / 'current-loot.json').write_text(json.dumps(values['current-loot.json']), encoding='utf8')
                feed.poll()
                self.assertEqual(feed.snapshot.protected_slots, frozenset())
            finally:
                feed.close()

    def test_rules_are_visible_without_affix_hits_and_moving_or_locking_updates_marks(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            def write(name, value):
                (directory / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf8')
            write('continuous-status.json', {'status': 'watching', 'game_pid': 123,
                'heartbeat_utc': dt.datetime.now(dt.timezone.utc).isoformat()})
            settings = {'native': {'lock': False}, 'lock_library': {'schema': 2, 'rules': [
                {'qualities': ['完美'], 'quality_tiers': [10], 'upper': True}]}}
            write('loot-overlay-settings.json', settings)
            write('loot-filter-rules.json', [])
            item = gear(name='霄引', skill=64)
            write('current-loot.json', {'status': 'watching', 'items': [item]})
            feed = OverlayFeed(directory, start=False)
            config = {'sections': {'numeric': False, 'legendary': False, 'lower': False}}
            try:
                feed.poll()
                self.assertEqual(marker_slots(feed.snapshot.sections, config), [0])
                self.assertEqual(feed.snapshot.protected_slots, frozenset({0}))
                item['index'] = 17
                write('current-loot.json', {'status': 'watching', 'items': [item]})
                feed.poll()
                self.assertEqual(marker_slots(feed.snapshot.sections, config), [17])
                item['item']['锁定'] = True
                write('current-loot.json', {'status': 'watching', 'items': [item]})
                feed.poll()
                self.assertEqual(marker_slots(feed.snapshot.sections, config), [])
                self.assertEqual(feed.snapshot.protected_slots, frozenset({17}))
                self.assertEqual(feed.read('loot-overlay-settings.json'), settings)
            finally:
                feed.close()

    def test_marker_rule_option_can_be_disabled_independently(self):
        sections = {'lock_library': [{'index': 8, 'locked': False}], 'numeric': [{'index': 4}]}
        self.assertEqual(marker_slots(sections, {}), [4, 8])
        self.assertEqual(marker_slots(sections, {'sections': {'lock_library': False}}), [4])


class PerfectRecycleProtectionTests(unittest.TestCase):
    setUp = recycle_fixture.RecycleClientTests.setUp
    send = recycle_fixture.RecycleClientTests.send
    snapshot = recycle_fixture.RecycleClientTests.snapshot
    full_bag = recycle_fixture.RecycleClientTests.full_bag
    state = recycle_fixture.RecycleClientTests.state

    def test_recycle_waits_for_perfect_rule_readback_and_keeps_protection(self):
        snapshot = self.full_bag()
        self.client = type(self.client)()
        snapshot.current['items'][0] = gear(name='霄引', skill=64)
        snapshot.current['backpack_slot_states'][0] = [1, False]
        snapshot.sections.clear()
        snapshot.settings['lock_library'] = {'schema': 2, 'rules': [
            {'qualities': ['完美'], 'quality_tiers': [10], 'upper': True}]}
        self.send(snapshot)
        request = self.send(snapshot, self.state())
        self.assertIsNone(request['recycle'])
        self.assertEqual(request.get('recycle_wait'), 'waiting_for_locks')
        self.assertEqual([x['index'] for x in request['locks']], [0])
        command = request['locks'][0]
        self.send(snapshot, self.state(acks=[{'id': command['id'], 'result': 'locked'}]))
        snapshot = copy.deepcopy(snapshot)
        snapshot.current['items'][0]['item']['锁定'] = True
        snapshot.current['backpack_slot_states'][0][1] = True
        request = self.send(snapshot, self.state())
        self.assertIsNotNone(request['recycle'], request.get('recycle_wait'))
        self.assertEqual(request['recycle']['protected'], [0])


if __name__ == '__main__':
    unittest.main()
