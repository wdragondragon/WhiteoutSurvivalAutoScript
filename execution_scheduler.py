import threading
import time

from PyQt5.QtCore import QThread, pyqtSignal

from emulator_executor import EmulatorExecutor
from execution_config import normalize_execution_settings
from serial_action_gate import SerialActionGate
from simulator_manager import EmulatorManager
from task_runtime import TaskExecutor


class BatchExecutionThread(QThread):
    log_signal = pyqtSignal(str)
    task_status_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal()

    def __init__(
            self,
            selected_names,
            task_configs,
            execution_settings,
            adb_path,
            ldconsole_path,
            fallback_config_name="",
    ):
        super().__init__()
        self.selected_names = list(selected_names)
        self.task_configs = task_configs
        self.execution_settings = normalize_execution_settings(execution_settings)
        self.adb_path = adb_path
        self.ldconsole_path = ldconsole_path
        self.fallback_config_name = fallback_config_name
        self._is_running = True
        self._active_executors = {}
        self._active_batch_names = set()
        self._lock = threading.Lock()
        self.manager = EmulatorManager(adb_path, ldconsole_path)
        self.action_gate = SerialActionGate(
            enabled=self.execution_settings.get("serial_actions_enabled", False),
            interval_sec=self.execution_settings.get("serial_action_interval_sec", 1.0),
        )

    def run(self):
        try:
            if not self.selected_names:
                self.log_signal.emit("未选择模拟器，调度结束")
                return
            if self.execution_settings.get("batch_enabled", False):
                self._run_batch_loop()
            else:
                self._run_continuous_loop()
        finally:
            self._close_active_executors()
            self.finished_signal.emit()

    def stop(self):
        self._is_running = False
        self._close_active_executors()
        if self.execution_settings.get("batch_enabled", False):
            self._stop_active_batch()

    def _run_batch_loop(self):
        max_online = max(1, int(self.execution_settings.get("batch_size", 1)))
        while self._is_running:
            self.log_signal.emit(f"开始执行本轮分批调度，最多同时在线 {max_online} 个模拟器")
            self._run_one_rolling_cycle(max_online)
            if self._is_running:
                self._sleep_interruptible(float(self.execution_settings.get("batch_between_delay_sec", 3.0)))

    def _run_one_rolling_cycle(self, max_online):
        pending_names = list(self.selected_names)
        starting = {}
        workers = {}

        while self._is_running and (pending_names or starting or workers):
            self._fill_online_slots(pending_names, starting, workers, max_online)
            self._promote_ready_starting_emulators(starting, workers)
            self._close_finished_workers(workers)
            self._sleep_interruptible(0.2)

        if not self._is_running:
            self._close_active_executors()
            self._stop_active_batch()
            for worker in list(workers.values()):
                worker.join(timeout=5)

    def _fill_online_slots(self, pending_names, starting, workers, max_online):
        while self._is_running and pending_names and len(starting) + len(workers) < max_online:
            name = pending_names.pop(0)
            emulator = self._launch_or_get_ready_emulator(name)
            if emulator:
                self._start_once_worker(emulator, workers)
            elif name in self._active_batch_names:
                starting[name] = time.time() + int(self.execution_settings.get("batch_start_timeout_sec", 180))

    def _launch_or_get_ready_emulator(self, name):
        emulators_by_name = {emu.name: emu for emu in self._safe_get_all_emulators()}
        emulator = emulators_by_name.get(name)
        if not emulator:
            self.log_signal.emit(f"[分批启动] 未找到 {name}，跳过")
            return None

        with self._lock:
            self._active_batch_names.add(name)

        if emulator.is_running() and emulator.device_name:
            self.log_signal.emit(f"[分批启动] {name} 已在线，开始执行")
            return emulator

        if emulator.is_running():
            self.log_signal.emit(f"[分批启动] {name} 已运行，等待 ADB 就绪")
            return None

        if self.manager.start_emulator(emulator.index):
            self.log_signal.emit(f"[分批启动] 已发送启动命令: {name}")
        else:
            self.log_signal.emit(f"[分批启动] 启动失败: {name}")
            with self._lock:
                self._active_batch_names.discard(name)
        return None

    def _promote_ready_starting_emulators(self, starting, workers):
        if not starting:
            return

        emulators_by_name = {emu.name: emu for emu in self._safe_get_all_emulators()}
        now = time.time()
        for name, deadline in list(starting.items()):
            emulator = emulators_by_name.get(name)
            if emulator and emulator.is_running() and emulator.device_name:
                starting.pop(name, None)
                self.log_signal.emit(f"[分批启动] {name} 已上线，开始执行")
                self._start_once_worker(emulator, workers)
                continue
            if now >= deadline:
                starting.pop(name, None)
                self.log_signal.emit(f"[分批启动] {name} 等待上线超时，关闭并跳过本轮")
                self._stop_and_wait_offline(name)

    def _start_once_worker(self, emulator, workers):
        worker = threading.Thread(target=self._run_once_worker, args=(emulator,), daemon=True)
        workers[emulator.name] = worker
        worker.start()

    def _close_finished_workers(self, workers):
        finished_names = []
        for name, worker in list(workers.items()):
            if worker.is_alive():
                continue
            worker.join(timeout=1)
            workers.pop(name, None)
            finished_names.append(name)
        for name in finished_names:
            if not self._stop_and_wait_offline(name):
                break

    def _stop_and_wait_offline(self, name):
        self._stop_batch([name])
        if self._wait_emulator_offline(name):
            return True
        self.log_signal.emit(f"[分批下线] {name} 未能确认下线，停止调度以避免超过同时在线数量")
        self._is_running = False
        return False

    def _wait_emulator_offline(self, name, timeout=30):
        end_time = time.time() + max(0.0, timeout)
        while self._is_running and time.time() < end_time:
            emulators_by_name = {emu.name: emu for emu in self._safe_get_all_emulators()}
            emulator = emulators_by_name.get(name)
            if not emulator or not emulator.is_running():
                return True
            self._sleep_interruptible(0.5)
        return False

    def _run_continuous_loop(self):
        emulators_by_name = {emu.name: emu for emu in self._safe_get_all_emulators()}
        worker_threads = []
        for name in self.selected_names:
            emulator = emulators_by_name.get(name)
            if not emulator:
                self.log_signal.emit(f"[启动{name}] 未找到模拟器，跳过")
                continue
            if not emulator.is_running() or not emulator.device_name:
                self.log_signal.emit(f"[启动{name}] 模拟器未运行或 ADB 未就绪，跳过")
                continue
            worker = threading.Thread(target=self._continuous_worker, args=(emulator,), daemon=True)
            worker_threads.append(worker)
            worker.start()

        if not worker_threads:
            self.log_signal.emit("没有可执行的运行中模拟器，调度结束")
            return

        while self._is_running and any(worker.is_alive() for worker in worker_threads):
            time.sleep(0.2)

    def _continuous_worker(self, emulator):
        executor = self._create_task_executor(emulator)
        try:
            while self._is_running and executor.run_status:
                task_config = self.task_configs.get(emulator.name)
                if not task_config:
                    self.log_signal.emit(f"[{emulator.name}] 未找到绑定配置，跳过")
                    return
                executor.execute_task_config(task_config)
                self.log_signal.emit(f"{emulator.name} 执行完毕，3秒后再次执行")
                self._sleep_interruptible(3.0)
        finally:
            self._unregister_executor(emulator.name)

    def _run_once_worker(self, emulator):
        executor = self._create_task_executor(emulator)
        try:
            task_config = self.task_configs.get(emulator.name)
            if not task_config:
                self.log_signal.emit(f"[{emulator.name}] 未找到绑定配置，跳过")
                return
            executor.execute_task_config(task_config)
            self.log_signal.emit(f"{emulator.name} 本轮任务执行完毕")
        finally:
            self._unregister_executor(emulator.name)

    def _create_task_executor(self, emulator):
        runtime_options = self.execution_settings.copy()
        emulator_executor = EmulatorExecutor(
            self.adb_path,
            emulator.name,
            emulator.device_name,
            action_gate=self.action_gate,
        )
        executor = TaskExecutor(
            emulator_executor=emulator_executor,
            runtime_options=runtime_options,
            task_status_callback=self._emit_task_status,
        )
        with self._lock:
            self._active_executors[emulator.name] = executor
        return executor

    def _emit_task_status(self, emulator_name, task_name):
        self.task_status_signal.emit(emulator_name, task_name or "")

    def _unregister_executor(self, emulator_name):
        with self._lock:
            self._active_executors.pop(emulator_name, None)
        self._emit_task_status(emulator_name, "")

    def _close_active_executors(self):
        with self._lock:
            executors = list(self._active_executors.values())
        for executor in executors:
            executor.close()

    def _stop_active_batch(self):
        with self._lock:
            batch_names = list(self._active_batch_names)
        self._stop_batch(batch_names)

    def _stop_batch(self, batch_names):
        emulators_by_name = {emu.name: emu for emu in self._safe_get_all_emulators()}
        for name in batch_names:
            emulator = emulators_by_name.get(name)
            if not emulator or not emulator.is_running():
                continue
            if self.manager.stop_emulator(emulator.index):
                self.log_signal.emit(f"[批次下线] 已发送关闭命令: {name}")
            else:
                self.log_signal.emit(f"[批次下线] 关闭失败: {name}")
        with self._lock:
            self._active_batch_names.difference_update(batch_names)

    def _safe_get_all_emulators(self):
        try:
            return self.manager.get_all_emulators()
        except Exception as e:
            self.log_signal.emit(f"获取模拟器列表失败: {e}")
            return []

    def _sleep_interruptible(self, seconds):
        end_time = time.time() + max(0.0, seconds)
        while self._is_running and time.time() < end_time:
            remaining = end_time - time.time()
            if remaining <= 0:
                break
            time.sleep(min(0.2, remaining))
