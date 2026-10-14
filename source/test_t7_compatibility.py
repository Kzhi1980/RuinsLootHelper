"""T7 fixtures checked against installed Steam build 25669660."""
import copy
import tkinter as tk
import unittest

from gear_view import catalog_data, select_sections, DEFAULT_RULES
from lock_library import selected_indices
from pickup_library import EquipmentLibrary
from overlay_settings import Settings
from test_game_compatibility import gear


class T7CatalogTests(unittest.TestCase):
    def test_new_equipment_and_sets_can_be_selected_by_official_identity(self):
        library = EquipmentLibrary(catalog_data()['equipment'])
        expected = {
            '神兵擎天': (1, '力量'), '神兵镇魔': (1, '魔法'), '神兵赤玄': (1, '精神'),
            '火焰之手': (5, '控火'), '操纵者之链': (4, '自爆'),
            '唤雷指环': (6, ''), '风刺指环': (6, ''), '御魔护符': (10, ''),
            '恶魔护符': (10, ''), '恶魔之角': (9, ''),
        }
        actual = {row['name']: (row['type_id'], row.get('set_name', ''))
                  for row in library.find(tier=11)}
        self.assertEqual(actual, expected)
        self.assertEqual([row['key'] for row in library.find(tier=11, set_name='控火')],
                         ['11:5:火焰之手'])

    def test_t7_perfect_set_and_threshold_conditions_all_apply_together(self):
        config = {'schema': 2, 'rules': [{
            'qualities': ['完美'], 'quality_tiers': [11], 'set_mode': 'set',
            'equipment_keys': ['11:1:神兵镇魔'],
            'thresholds': {'11:1:神兵镇魔': {'魔法上限': 90}},
        }]}
        item = gear(name='神兵镇魔', tier=11, skill=0)
        item['item']['基础属性'] = {'魔法上限': 90}
        self.assertEqual(selected_indices([item], config), {0})
        for field, value in (('品质', 3), ('等阶', 10), ('名字', '唤雷指环'),
                             ('基础属性', {'魔法上限': 89}),
                             ('基础属性', {'攻击上限': 180})):
            with self.subTest(field=field, value=value):
                candidate = copy.deepcopy(item)
                candidate['item'][field] = value
                self.assertEqual(selected_indices([candidate], config), set())

    def test_t7_perfect_scope_keeps_set_and_non_set_separate(self):
        items = [gear(name='神兵擎天', tier=11, index=0),
                 gear(name='唤雷指环', tier=11, index=1),
                 gear(name='冰原腰带', tier=10, index=2),
                 gear(name='风刺指环', tier=11, quality=3, index=3)]
        for mode, wanted in (('all', {0, 1}), ('set', {0}), ('non_set', {1})):
            with self.subTest(mode=mode):
                rules = {'schema': 2, 'rules': [{
                    'qualities': ['完美'], 'quality_tiers': [11], 'set_mode': mode}]}
                self.assertEqual(selected_indices(items, rules), wanted)

    def test_t7_upper_skill_matches_only_selected_tier_part_and_position(self):
        items = [gear(name='唤雷指环', tier=11, skill=68, index=0),
                 gear(name='风刺指环', tier=11, skill=92, index=1),
                 gear(name='火焰之手', tier=11, skill=74, index=2),
                 gear(name='冰原戒指', tier=10, skill=68, index=3)]
        settings = {'legendary_pairs': ['11:6']}
        self.assertEqual([r['index'] for r in select_sections({'items': items}, [], settings)['legendary']], [0, 1])
        items[0]['item']['技能1'] = 0
        items[0]['item']['极品属性'] = {'技能1': 68}
        self.assertEqual([r['index'] for r in select_sections({'items': items}, [], settings)['legendary']], [1])
        rule = {'schema': 2, 'rules': [{'qualities': ['完美'], 'quality_tiers': [11],
                 'equipment_keys': ['11:6:风刺指环'], 'upper': True, 'upper_ids': [92]}]}
        self.assertEqual(selected_indices(items, rule), {1})


class T7SettingsTests(unittest.TestCase):
    def test_t7_choices_save_and_reload_without_widening_existing_selections(self):
        root = tk.Tk()
        root.withdraw()
        files = {'loot-filter-rules.json': copy.deepcopy(DEFAULT_RULES),
                 'loot-overlay-settings.json': {'legendary_pairs': ['10:1'],
                  'lock_library': {'schema': 2, 'rules': [
                      {'name': '原有规则', 'qualities': ['完美'], 'quality_tiers': [10]}]}}}
        class Host:
            def read_file(self, name, default=None):
                return copy.deepcopy(files.get(name, default))
            def write_file(self, name, value):
                files[name] = value
        host = Host()
        host.root = root
        dialog = reopened = None
        try:
            dialog = Settings(host, show=False)
            self.assertEqual([key for key, var in dialog.pair_vars.items() if var.get()], ['10:1'])
            self.assertIn('11:6', dialog.pair_vars)
            self.assertIn(11, dialog.lock_library.quality_tier_vars)
            self.assertFalse(dialog.lock_library.quality_tier_vars[11].get())
            dialog.window.after_cancel(dialog.center_job)
            dialog.center_job = None
            dialog.features.select(str(dialog.filter_page))
            dialog.tabs.select(str(dialog.legend_tab))
            dialog.window.geometry('720x520+-10000+-10000')
            dialog.window.deiconify()
            root.update()
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            for widget in descendants(dialog.legend_tab):
                if isinstance(widget, tk.Canvas):
                    widget.yview_moveto(1)
                    widget.xview_moveto(1)
            root.update()
            check = next(widget for widget in descendants(dialog.legend_tab)
                         if isinstance(widget, tk.Checkbutton) and
                         str(widget.cget('variable')) == str(dialog.pair_vars['11:10']))
            bounds = (check.winfo_rootx(), check.winfo_rooty(),
                      check.winfo_rootx() + check.winfo_width(),
                      check.winfo_rooty() + check.winfo_height())
            ancestor = check.master
            while ancestor != dialog.window:
                self.assertGreaterEqual(bounds[0], ancestor.winfo_rootx())
                self.assertGreaterEqual(bounds[1], ancestor.winfo_rooty())
                self.assertLessEqual(bounds[2], ancestor.winfo_rootx() + ancestor.winfo_width())
                self.assertLessEqual(bounds[3], ancestor.winfo_rooty() + ancestor.winfo_height())
                ancestor = ancestor.master
            dialog.choose_pairs('t7')
            self.assertEqual({key for key, var in dialog.pair_vars.items() if var.get()},
                             {f'11:{i}' for i in range(1, 11)})
            self.assertIn('T7', dialog.pair_count.cget('text'))
            dialog.lock_library.quality_tier_vars[10].set(False)
            dialog.lock_library.quality_tier_vars[11].set(True)
            dialog.apply()
            self.assertEqual(files['loot-overlay-settings.json']['lock_library']['rules'][0]['quality_tiers'], [11])
            reopened = Settings(host, show=False)
            self.assertTrue(reopened.pair_vars['11:6'].get())
            self.assertFalse(reopened.pair_vars['10:1'].get())
            self.assertTrue(reopened.lock_library.quality_tier_vars[11].get())
        finally:
            for window in (dialog, reopened):
                if window and window.window.winfo_exists():
                    window.cancel()
            root.destroy()


if __name__ == '__main__':
    unittest.main()
