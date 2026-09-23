"""Windows file contention and windowless worker failures from user diagnostics."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import copy
import ctypes as c
from ctypes import wintypes as w
import json
import msvcrt
from pathlib import Path
import queue
import tempfile
import threading
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from continuous_watch import ContinuousWatch, atomic_text
from release_runtime import Backend


@contextmanager
def held_file(path, share=3):
    kernel = c.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE]
    kernel.CreateFileW.restype = w.HANDLE
    kernel.CloseHandle.argtypes = [w.HANDLE]
    handle = kernel.CreateFileW(str(path), 0x80000000, share, None, 3, 0x80, None)
    if handle in (None, c.c_void_p(-1).value):
        raise c.WinError(c.get_last_error())
    closed = False
    def release():
        nonlocal closed
        if not closed:
            kernel.CloseHandle(handle)
            closed = True
    try:
        yield release
    finally:
        release()


class AtomicStatusTests(unittest.TestCase):
    def test_status_write_recovers_when_windows_reader_releases_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'feature-status.json'
            path.write_text('{}')
            with held_file(path) as release:
                timer = threading.Timer(.12, release)
                timer.start()
                try:
                    atomic_text(path, '{"status":"running"}')
                except PermissionError as exc:
                    self.fail(f'A short file hold should recover: {exc}')
                finally:
                    timer.join()
            self.assertEqual(json.loads(path.read_text()), {'status': 'running'})
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_locked_old_temp_file_does_not_block_new_publications(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'feature-status.json'
            old_temp = path.with_suffix('.json.tmp')
            old_temp.write_text('old temporary data')
            with held_file(old_temp, share=0):
                try:
                    atomic_text(path, '{"status":"running"}')
                except PermissionError as exc:
                    self.fail(f'Writer reused another publication temporary file: {exc}')
            self.assertEqual(old_temp.read_text(), 'old temporary data')
            self.assertEqual(json.loads(path.read_text()), {'status': 'running'})

    def test_failed_replace_preserves_last_snapshot_and_cleans_own_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'feature-status.json'
            path.write_text('{"original":true}')
            with held_file(path), self.assertRaises(PermissionError):
                atomic_text(path, '{"new":true}')
            self.assertEqual(json.loads(path.read_text()), {'original': True})
            self.assertEqual(list(Path(tmp).iterdir()), [path])

    def test_two_publications_never_share_the_same_temporary_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'feature-status.json'
            barrier = threading.Barrier(2)
            attempted = threading.local()
            original = Path.replace
            names = []
            def replace(source, destination):
                if not getattr(attempted, 'first', False):
                    attempted.first = True
                    names.append(source.name)
                    barrier.wait(timeout=3)
                return original(source, destination)
            with patch.object(Path, 'replace', replace), ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(atomic_text, path, json.dumps({'value': n})) for n in (1, 2)]
                failures = [future.exception() for future in futures if future.exception() is not None]
            self.assertEqual(failures, [])
            self.assertEqual(len(set(names)), 2)
            self.assertIn(json.loads(path.read_text())['value'], (1, 2))


class MonitorRecoveryTests(unittest.TestCase):
    def test_monitor_lock_is_released_even_if_final_publication_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            watch = SimpleNamespace(output=directory / 'continuous-status.json', handle=None,
                state=SimpleNamespace(clear=lambda: None), setup_source=lambda: None,
                observe=Mock(side_effect=InterruptedError()),
                publish=Mock(side_effect=PermissionError('feature-status.json is held')))
            caught = None
            try:
                ContinuousWatch.run(watch)
            except PermissionError as exc:
                caught = exc  # Retain the failing frame, as an error dialog would.
            self.assertIsNotNone(caught)
            with (directory / 'continuous.lock').open('r+b') as retry:
                try:
                    msvcrt.locking(retry.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    self.fail(f'Failure retained the monitor lock: {exc}')
                retry.seek(0)
                msvcrt.locking(retry.fileno(), msvcrt.LK_UNLCK, 1)

    def test_backend_recovers_after_status_file_access_returns(self):
        with tempfile.TemporaryDirectory() as tmp, patch('release_runtime.configure_runtime'):
            directory = Path(tmp)
            path = directory / 'feature-status.json'
            path.write_text('{}')
            backend = Backend('fixture.exe', directory)
            states = []
            backend.notify = lambda: states.append(copy.deepcopy(backend.state))
            with held_file(path) as release:
                def wait(_):
                    release()
                    return backend.stop.is_set()
                def monitor(*_):
                    def run():
                        backend.progress('watching', 123)
                        backend.stop.set()
                    return SimpleNamespace(run=run)
                with patch('release_runtime.running_games', return_value=[123]), \
                        patch('release_runtime.SessionProbe') as probe, \
                        patch('release_runtime.SessionWatch', side_effect=monitor), \
                        patch.object(backend.stop, 'wait', side_effect=wait):
                    probe.return_value.discover.return_value = ({'reflected_types': {}}, {})
                    try:
                        backend.run()
                    except PermissionError as exc:
                        self.fail(f'Status file contention escaped the recovery loop: {exc}')
            phases = [state['status'] for state in states]
            self.assertIn('waiting_for_files', phases)
            self.assertIn('watching', phases)
            self.assertEqual(phases[-1], 'stopped')
            self.assertEqual(next(s for s in states if s['status'] == 'waiting_for_files')['game_pid'], 0)

    def test_total_write_failure_still_reports_through_memory_and_closes_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp, patch('release_runtime.configure_runtime'):
            backend = Backend('fixture.exe', Path(tmp))
            states = []
            backend.notify = lambda: states.append(copy.deepcopy(backend.state))
            def wait(_): backend.stop.set()
            with patch('release_runtime.running_games', return_value=[]), \
                    patch('release_runtime.atomic_text', side_effect=PermissionError('folder denied')), \
                    patch.object(Path, 'write_text', side_effect=PermissionError('log denied')), \
                    patch.object(backend.stop, 'wait', side_effect=wait):
                try:
                    backend.run()
                except PermissionError as exc:
                    self.fail(f'Error reporting raised another error: {exc}')
            failed = next(s for s in states if s['status'] == 'waiting_for_files')
            self.assertIn('folder denied', failed['error'])
            self.assertEqual(failed['game_pid'], 0)

    def test_game_read_error_is_not_reported_as_status_file_failure(self):
        with tempfile.TemporaryDirectory() as tmp, patch('release_runtime.configure_runtime'):
            backend = Backend('fixture.exe', Path(tmp))
            states = []
            backend.notify = lambda: states.append(copy.deepcopy(backend.state))
            with patch('release_runtime.running_games', return_value=[123]), \
                    patch('release_runtime.SessionProbe') as probe, \
                    patch.object(backend.stop, 'wait', side_effect=lambda _: backend.stop.set()):
                probe.return_value.discover.side_effect = OSError(5, 'OpenProcess query/read access denied')
                backend.run()
            phases = [state['status'] for state in states]
            self.assertNotIn('waiting_for_files', phases)
            failed = next(s for s in states if s['status'] == 'waiting_for_backpack')
            self.assertIn('OpenProcess', failed['error'])

    def test_another_monitor_is_reported_without_killing_or_clearing_its_lock(self):
        with tempfile.TemporaryDirectory() as tmp, patch('release_runtime.configure_runtime'):
            directory = Path(tmp)
            backend = Backend('fixture.exe', directory)
            states = []
            backend.notify = lambda: states.append(copy.deepcopy(backend.state))
            watch = SimpleNamespace(output=directory / 'continuous-status.json')
            def wait(_): backend.stop.set()
            with (directory / 'continuous.lock').open('w+b') as owner:
                owner.write(b'0'); owner.flush(); owner.seek(0)
                msvcrt.locking(owner.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    with patch('release_runtime.running_games', return_value=[123]), \
                            patch('release_runtime.SessionProbe') as probe, \
                            patch('release_runtime.SessionWatch') as monitor, \
                            patch.object(backend.stop, 'wait', side_effect=wait):
                        probe.return_value.discover.return_value = ({'reflected_types': {}}, {})
                        monitor.return_value.run.side_effect = lambda: ContinuousWatch.run(watch)
                        backend.run()
                    self.assertIn('waiting_for_monitor', [state['status'] for state in states])
                    self.assertFalse(owner.closed)
                    owner.seek(0)
                    self.assertEqual(owner.read(1), b'0')
                finally:
                    owner.seek(0); msvcrt.locking(owner.fileno(), msvcrt.LK_UNLCK, 1)


class WorkerErrorTests(unittest.TestCase):
    def test_windowless_worker_exits_without_a_secondary_stderr_crash(self):
        from worker_process import reader_main
        for can_write_log in (True, False):
            with self.subTest(can_write_log=can_write_log), tempfile.TemporaryDirectory() as tmp:
                messages = queue.Queue()
                with patch('release_runtime.configure_runtime'), \
                        patch('release_runtime.Backend.run', side_effect=PermissionError('original file failure')), \
                        patch('sys.stderr', None):
                    if can_write_log:
                        with self.assertRaises(SystemExit) as caught:
                            reader_main('fixture.exe', tmp, threading.Event(), messages)
                    else:
                        with patch.object(Path, 'write_text', side_effect=PermissionError('log denied')):
                            with self.assertRaises(SystemExit) as caught:
                                reader_main('fixture.exe', tmp, threading.Event(), messages)
                self.assertEqual(caught.exception.code, 1)
                state = messages.get_nowait()
                self.assertEqual(state['status'], 'monitor_failed')
                self.assertEqual(state['game_pid'], 0)
                self.assertIn('original file failure', state['error'])
                if can_write_log:
                    self.assertIn('original file failure', Path(tmp, 'worker-error.txt').read_text(encoding='utf8'))

    def test_parent_preserves_failure_reason_and_restarts_only_its_child(self):
        from worker_process import ProcessBackend
        context = SimpleNamespace(Event=threading.Event, Queue=lambda maxsize: queue.Queue(maxsize))
        with patch('worker_process.mp.get_context', return_value=context):
            backend = ProcessBackend('fixture.exe', 'unused')
        backend.process = Mock(exitcode=1)
        backend.process.is_alive.return_value = False
        backend.messages.put({'status': 'monitor_failed', 'game_pid': 0, 'error': 'original failure'})
        with patch('worker_process.time.monotonic', return_value=100), patch.object(backend, 'start') as start:
            self.assertIn('original failure', backend.state['error'])
            start.assert_not_called()
        with patch('worker_process.time.monotonic', return_value=106), patch.object(backend, 'start') as start:
            backend.state
            start.assert_called_once_with()
            backend.process.join.assert_called_once_with(0)

    def test_reader_failure_blocks_fresh_but_incomplete_disk_snapshots(self):
        from overlay_feed import OverlayFeed
        from test_upgrade import fixture
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            fixture(directory)
            feed = OverlayFeed(directory, start=False)
            try:
                feed.poll()
                self.assertTrue(feed.snapshot.live)
                feed.set_reader_state({'status': 'waiting_for_files', 'game_pid': 0, 'error': 'file denied'})
                feed.poll()
                self.assertFalse(feed.snapshot.live)
                self.assertEqual(feed.snapshot.protected_slots, frozenset())
                self.assertEqual(feed.snapshot.error, 'file denied')
                feed.set_reader_state({'status': 'watching', 'game_pid': 123})
                feed.poll()
                self.assertTrue(feed.snapshot.live)
            finally:
                feed.close()


class PopupRefreshTests(unittest.TestCase):
    def test_reader_recovery_states_have_specific_visible_messages(self):
        from startup_window import reader_status_text
        self.assertIn('状态文件', reader_status_text({'status': 'waiting_for_files'}))
        self.assertIn('重试', reader_status_text({'status': 'waiting_for_files'}))
        self.assertIn('监控', reader_status_text({'status': 'waiting_for_monitor'}))

    def test_native_settings_keep_refreshing_with_tcl_popup_focus(self):
        from overlay_settings import Settings
        root = tk.Tk()
        root.withdraw()
        def read_file(name, default=None):
            return {'status': 'watching'} if name == 'continuous-status.json' else copy.deepcopy(default)
        host = SimpleNamespace(root=root, read_file=read_file, write_file=lambda *_: None,
                               reader_state={'status': 'waiting_for_files', 'game_pid': 0})
        dialog = Settings(host, show=False)
        combo = ttk.Combobox(dialog.window, values=['one', 'two'])
        popup = str(root.tk.call('ttk::combobox::PopdownWindow', str(combo)))
        focus = popup + '.f.l'
        self.assertTrue(root.tk.call('winfo', 'exists', focus))
        root.tk.call('rename', 'focus', 'recovery_original_focus')
        root.tk.eval('proc focus {args} {if {[llength $args] == 0} {return ' + focus +
                     '}; tailcall recovery_original_focus {*}$args}')
        try:
            native = dialog.native_settings
            if native.job:
                dialog.window.after_cancel(native.job)
            try:
                native.refresh()
            except KeyError as exc:
                self.fail(f'Native refresh stopped on Tcl popup: {exc}')
            self.assertTrue(native.job)
            self.assertTrue(root.tk.call('after', 'info', native.job))
            self.assertIn('状态文件', dialog.game_status.cget('text'))
            dialog.window.after_cancel(native.job)
            host.reader_state = {'status': 'watching', 'game_pid': 123}
            native.refresh()
            self.assertIn('已连接', dialog.game_status.cget('text'))
        finally:
            root.tk.call('rename', 'focus', '')
            root.tk.call('rename', 'recovery_original_focus', 'focus')
            dialog.cancel()
            root.destroy()


if __name__ == '__main__':
    unittest.main()
