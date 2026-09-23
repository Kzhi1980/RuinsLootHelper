"""Regressions for preserving invalid restrictions and withholding recycling."""
import copy
import datetime as dt
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import tkinter as tk
import unittest

import test_auto_recycle as recycle_fixture
from lock_library import selected_indices
from overlay_settings import Settings
from overlay_feed import OverlayFeed


RULE = {'name': '完美T6魔法门槛', 'enabled': True, 'qualities': ['完美'],
        'quality_tiers': [10], 'equipment_keys': ['10:1:霄引'],
        'thresholds': {'10:1:霄引': {'旧字段魔法上限': 90}}}


class RecycleRuleSafetyTests(unittest.TestCase):
    setUp = recycle_fixture.RecycleClientTests.setUp
    send = recycle_fixture.RecycleClientTests.send
    snapshot = recycle_fixture.RecycleClientTests.snapshot
    full_bag = recycle_fixture.RecycleClientTests.full_bag
    state = recycle_fixture.RecycleClientTests.state

    def bag(self, rules):
        sample = self.full_bag()
        self.client = type(self.client)()
        sample.current['items'][0]['item'].update(
            名字='霄引', 等阶=10, 品质=4, 锁定=False, 基础属性={'魔法上限': 52})
        sample.current['backpack_slot_states'][0] = [1, False]
        sample.sections.clear()
        sample.settings['lock_library'] = copy.deepcopy(rules)
        self.send(sample)
        return sample

    def test_invalid_rule_never_authorizes_recycle_even_with_no_matching_slots(self):
        cases = [
            RULE,
            dict(RULE, qualities=['完美', '未知品质']),
            {'qualities': 4}, {'qualities': None, 'keep_all': True},
            {'qualities': ['完美'], 'upper': 'true'},
            {'qualities': ['完美'], 'equipment_keys': ['过期装备']},
            {'qualities': ['完美'], 'thresholds': []},
            None,
        ]
        for rule in cases:
            with self.subTest(rule=rule):
                sample = self.bag({'schema': 2, 'rules': [rule]})
                request = self.send(sample, self.state())
                self.assertIsNone(request['recycle'])
                self.assertEqual(request['recycle_wait'], 'invalid_lock_rules')
                self.assertTrue(request['lock_rule_errors'])

    def test_invalid_rule_cancels_a_previous_recycle_proof(self):
        sample = self.full_bag()
        self.assertIsNotNone(self.send(sample, self.state())['recycle'])
        sample.settings['lock_library'] = {'schema': 2, 'rules': [RULE]}
        request = self.send(sample, self.state())
        self.assertIsNone(request['recycle'])
        self.assertIsNone(self.client.recycle_command)
        self.assertIsNone(self.client.recycle_key)

    def test_malformed_rule_container_is_not_an_empty_rule_list(self):
        for config in (None, [], {'schema': 2, 'rules': None}, {'schema': 2},
                       {'schema': 99, 'rules': []}):
            with self.subTest(config=config):
                sample = self.bag(config)
                self.assertIsNone(self.send(sample, self.state())['recycle'])

    def test_legacy_invalid_rule_is_not_dropped_during_migration(self):
        sample = self.bag({'qualities': None})
        request = self.send(sample, self.state())
        self.assertIsNone(request['recycle'])
        self.assertEqual(request['recycle_wait'], 'invalid_lock_rules')

    def test_disabled_invalid_rule_does_not_block_a_deliberate_opt_out(self):
        sample = self.bag({'schema': 2, 'rules': [dict(RULE, enabled=False)]})
        self.assertIsNotNone(self.send(sample, self.state())['recycle'])

    def test_valid_rules_still_lock_but_cannot_override_an_invalid_rule(self):
        valid = {'qualities': ['完美'], 'quality_tiers': [10]}
        sample = self.bag({'schema': 2, 'rules': [valid, RULE]})
        request = self.send(sample, self.state())
        self.assertEqual([command['index'] for command in request['locks']], [0])
        self.assertIsNone(request['recycle'])
        self.assertEqual(request['recycle_wait'], 'invalid_lock_rules')

    def test_fixing_rule_still_requires_lock_readback_before_recycle(self):
        sample = self.bag({'schema': 2, 'rules': [RULE]})
        self.assertIsNone(self.send(sample, self.state())['recycle'])
        sample.settings['lock_library']['rules'][0]['thresholds'] = {'10:1:霄引': {'魔法上限': 50}}
        request = self.send(sample, self.state())
        self.assertEqual([command['index'] for command in request['locks']], [0])
        self.assertIsNone(request['recycle'])
        sample.current['items'][0]['item']['锁定'] = True
        sample.current['backpack_slot_states'][0][1] = True
        request = self.send(sample, self.state())
        self.assertEqual(request['recycle']['protected'], [0])

    def test_cached_protection_carries_validation_failures(self):
        sample = self.bag({'schema': 2, 'rules': [RULE]})
        sample = replace(sample, protected_slots=frozenset(), protection_errors=('规则无效',))
        request = self.send(sample, self.state())
        self.assertIsNone(request['recycle'])
        self.assertEqual(request['lock_rule_errors'], ['规则无效'])

    def test_file_worker_rechecks_rule_edits_without_inventory_changes(self):
        sample = self.bag({'schema': 2, 'rules': [RULE]})
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            def write(name, value):
                (directory / name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf8')
            write('continuous-status.json', dict(sample.status, status='watching',
                heartbeat_utc=dt.datetime.now(dt.timezone.utc).isoformat()))
            write('current-loot.json', dict(sample.current, status='watching'))
            write('feature-status.json', sample.ui)
            write('loot-filter-rules.json', [])
            write('loot-overlay-settings.json', sample.settings)
            feed = OverlayFeed(directory, start=False)
            try:
                feed.poll()
                self.assertEqual(feed.snapshot.protected_slots, frozenset())
                self.assertTrue(feed.snapshot.protection_errors)
                self.assertIsNone(self.send(feed.snapshot, self.state())['recycle'])
                feed.poll()  # The cached result must retain its invalid status.
                self.assertTrue(feed.snapshot.protection_errors)
                sample.settings['lock_library']['rules'][0]['thresholds'] = {'10:1:霄引': {'魔法上限': 50}}
                feed.submit('loot-overlay-settings.json', sample.settings)
                feed.poll()
                self.assertEqual(feed.snapshot.protection_errors, ())
                self.assertEqual(feed.snapshot.protected_slots, frozenset({0}))
                request = self.send(feed.snapshot, self.state())
                self.assertIsNone(request['recycle'])
                self.assertEqual(request['recycle_wait'], 'waiting_for_locks')
            finally:
                feed.close()


class SettingsRuleSafetyTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.dialogs = []
        self.addCleanup(self.cleanup)
        self.files = {'loot-filter-rules.json': []}
        files = self.files
        class Host:
            def read_file(self, name, default=None): return copy.deepcopy(files.get(name, default))
            def write_file(self, name, value): files[name] = copy.deepcopy(value)
        self.host = Host()
        self.host.root = self.root

    def cleanup(self):
        for dialog in self.dialogs:
            dialog.cancel()
        self.root.destroy()

    def open(self, config):
        self.files['loot-overlay-settings.json'] = {'native': {'lock': True}, 'lock_library': copy.deepcopy(config)}
        dialog = Settings(self.host, show=False)
        self.dialogs.append(dialog)
        return dialog

    def test_unrelated_save_preserves_invalid_threshold_and_does_not_broaden_matches(self):
        config = {'schema': 2, 'rules': [RULE]}
        dialog = self.open(config)
        self.assertEqual(dialog.lock_library.values()['lock_library'], config)
        self.assertIn('无效', dialog.lock_library.rule_description.cget('text'))
        dialog.transparent.set(True)
        dialog.apply()
        saved = self.files['loot-overlay-settings.json']['lock_library']
        self.assertEqual(saved, config)
        sample = [{'index': 0, 'item': {'物品类型': 1, '名字': '霄引', '等阶': 10,
                   '品质': 4, '基础属性': {'魔法上限': 52}}}]
        self.assertEqual(selected_indices(sample, saved), set())
        self.assertTrue(self.files['loot-overlay-settings.json']['transparent_background'])

    def test_switching_rules_preserves_unknown_values_without_crashing(self):
        rules = [dict(RULE, thresholds={'10:1:霄引': {'魔法上限': '坏数值'}},
                      qualities=['完美', '未知品质'], set_mode='失效范围'),
                 dict(RULE, name='第二条', quality_tiers=[10, 99]), None]
        config = {'schema': 2, 'rules': rules}
        editor = self.open(config).lock_library
        for index in (1, 2, 0): editor.select_rule(index)
        self.assertEqual(editor.values()['lock_library'], config)

    def test_saving_a_different_threshold_preserves_the_unresolved_one(self):
        editor = self.open({'schema': 2, 'rules': [RULE]}).lock_library
        editor.set_threshold('9:1:追风', {'魔法上限': 100})
        rule = editor.values()['lock_library']['rules'][0]
        self.assertEqual(rule['thresholds']['10:1:霄引'], RULE['thresholds']['10:1:霄引'])
        self.assertEqual(rule['thresholds']['9:1:追风'], {'魔法上限': 100})

    def test_explicit_threshold_repair_replaces_only_that_equipment_restriction(self):
        editor = self.open({'schema': 2, 'rules': [RULE]}).lock_library
        editor.set_threshold('10:1:霄引', {'魔法上限': 90})
        saved = editor.values()['lock_library']['rules'][0]
        self.assertEqual(saved['thresholds'], {'10:1:霄引': {'魔法上限': 90}})
        self.assertEqual(saved['qualities'], ['完美'])
        self.assertNotIn('无效', editor.rule_description.cget('text'))

    def test_disabling_invalid_rule_preserves_its_conditions(self):
        editor = self.open({'schema': 2, 'rules': [RULE]}).lock_library
        editor.rule_enabled.set(False)
        saved = editor.values()['lock_library']['rules'][0]
        self.assertEqual(saved, dict(RULE, enabled=False))

    def test_malformed_config_is_preserved_until_explicitly_rebuilt(self):
        for config in ([], None, {'schema': 2, 'rules': None}, {'schema': 99, 'rules': []}):
            with self.subTest(config=config):
                editor = self.open(config).lock_library
                self.assertEqual(editor.values()['lock_library'], config)
                editor.delete_rule()
                editor.quality_vars['完美'].set(True)
                self.assertEqual(editor.values()['lock_library']['rules'][0]['qualities'], ['完美'])


if __name__ == '__main__':
    unittest.main()
