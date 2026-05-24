import threading
import time

from PyQt5.QtCore import QThread, pyqtSignal

from emulator_executor import EmulatorExecutor
from execution_config import normalize_emulator_settings, normalize_execution_settings
from serial_action_gate import SerialActionGate
from simulator_manager import EmulatorManager
from task_runtime import TaskExecutor


class BatchExecutionThread(QThread):
    log_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()

    def __init__(
            self,
            selected_names,
            task_configs,
            emulator_settings,
            execution_settings,
            adb_path,
            ldconsole_path,
            fallback_config_name="",
    ):
        super().__init__()
        self.selected_names = list(selected_names)
        self.task_configs = task_configs
        self.emulator_settings = emulator_settings
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

    def _make_batches(self):
        batch_size = max(1, int(self.execution_settings.get("batch_size", 1)))
        return [
            self.selected_names[index:index + batch_size]
            for index in range(0, len(self.selected_names), batch_size)
        ]

    def _run_batch_loop(self):
        batches = self._make_batches()
        if not batches:
            return

        while self._is_running:
            for batch_index, batch_names in enumerate(batches, start=1):
                if not self._is_running:
                    break
                self.log_signal.emit(f"开始执行第 {batch_index}/{len(batches)} 批: {', '.join(batch_names)}")
                ready_emulators = self._start_and_wait_batch(batch_names)
                if ready_emulators:
                    self._run_batch_once(ready_emulators)
                self._stop_batch(batch_names)
                self._sleep_interruptible(float(self.execution_settings.get("batch_between_delay_sec", 3.0)))

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

    def _start_and_wait_batch(self, batch_names):
        with self._lock:
            self._active_batch_names = set(batch_names)

        emulators_by_name = {emu.name: emu for emu in self._safe_get_all_emulators()}
        for name in batch_names:
            emulator = emulators_by_name.get(name)
            if not emulator:
                self.log_signal.emit(f"[批次启动] 未找到 {name}")
                continue
            if emulator.is_running():
                self.log_signal.emit(f"[批次启动] {name} 已运行")
                continue
            if self.manager.start_emulator(emulator.index):
                self.log_signal.emit(f"[批次启动] 已发送启动命令: {name}")
            else:
                self.log_signal.emit(f"[批次启动] 启动失败: {name}")

        timeout = int(self.execution_settings.get("batch_start_timeout_sec", 180))
        deadline = time.time() + timeout
        ready = {}
        while self._is_running and time.time() < deadline:
            emulators_by_name = {emu.name: emu for emu in self._safe_get_all_emulators()}
            ready = {
                name: emulators_by_name[name]
                for name in batch_names
                if name in emulators_by_name and emulators_by_name[name].is_running() and emulators_by_name[name].device_name
            }
            if len(ready) == len(batch_names):
                break
            self._sleep_interruptible(2.0)

        missing = [name for name in batch_names if name not in ready]
        for name in missing:
            self.log_signal.emit(f"[批次启动] {name} 等待上线超时，跳过本轮")
        return [ready[name] for name in batch_names if name in ready]

    def _run_batch_once(self, emulators):
        worker_threads = []
        for emulator in emulators:
            worker = threading.Thread(target=self._run_once_worker, args=(emulator,), daemon=True)
            worker_threads.append(worker)
            worker.start()

        while self._is_running and any(worker.is_alive() for worker in worker_threads):
            time.sleep(0.2)

        if not self._is_running:
            self._close_active_executors()

        for worker in worker_threads:
            worker.join(timeout=5)

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
        emulator_runtime_settings = normalize_emulator_settings(self.emulator_settings.get(emulator.name, {}))
        runtime_options = self.execution_settings.copy()
        runtime_options.update(emulator_runtime_settings)
        emulator_executor = EmulatorExecutor(
            self.adb_path,
            emulator.name,
            emulator.device_name,
            action_gate=self.action_gate,
        )
        executor = TaskExecutor(emulator_executor=emulator_executor, runtime_options=runtime_options)
        with self._lock:
            self._active_executors[emulator.name] = executor
        return executor

    def _unregister_executor(self, emulator_name):
        with self._lock:
            self._active_executors.pop(emulator_name, None)

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
            time.sleep(min(0.2, end_time - time.time()))
