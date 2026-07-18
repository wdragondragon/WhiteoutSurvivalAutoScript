# simulator_manager.py
import os
import subprocess
import locale
import time

import cv2


class EmulatorStatus:
    def __init__(self):
        self.index = 0
        self.name = None
        self.run_status = -1
        self.height = 0
        self.width = 0
        self.dpi = 0
        self.device_name = None

    def is_running(self):
        return self.run_status == 1


class EmulatorManager:
    def __init__(self, adb_path, ldconsole_path):
        self.adb_path = adb_path
        self.ldconsole_path = ldconsole_path
        self.last_adb_connect_detail = ""

    @staticmethod
    def expected_adb_tcp_port(index):
        return 5555 + int(index) * 2

    @classmethod
    def expected_adb_connect_address(cls, index):
        return f"127.0.0.1:{cls.expected_adb_tcp_port(index)}"

    @classmethod
    def expected_adb_device_name(cls, index):
        return cls.expected_adb_connect_address(index)

    @classmethod
    def expected_adb_device_names(cls, index):
        index = int(index)
        return [
            cls.expected_adb_connect_address(index),
            f"emulator-{5554 + index * 2}",
        ]

    @staticmethod
    def _decode_output(data):
        for encoding in (locale.getpreferredencoding(False), "utf-8", "gbk"):
            try:
                return data.decode(encoding)
            except UnicodeDecodeError:
                continue
        return data.decode(errors="ignore")

    def _adb_devices(self):
        errors = []
        for attempt in range(2):
            try:
                devices = self._adb_devices_once()
                self.last_adb_connect_detail = ""
                return devices
            except Exception as e:
                errors.append(str(e))
                if attempt == 0:
                    errors.append(self._restart_adb_server())
                    time.sleep(0.5)
        raise Exception("获取正在运行的设备出错: " + "；".join(error for error in errors if error))

    def _adb_devices_once(self):
        try:
            running_devices_name = subprocess.run(
                [self.adb_path, "devices"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=8,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            raise Exception(f"执行 adb devices 失败: {e}")

        if running_devices_name.returncode != 0:
            output = (
                self._decode_output(running_devices_name.stdout) +
                self._decode_output(running_devices_name.stderr)
            ).strip()
            if not output:
                output = "无输出"
            raise Exception(f"adb devices 返回码 {running_devices_name.returncode}: {output}")

        devices = {}
        for line in running_devices_name.stdout.strip().splitlines()[1:]:
            devices_info = self._decode_output(line).strip()
            if not devices_info:
                continue
            parts = devices_info.split()
            if len(parts) >= 2:
                devices[parts[0]] = parts[1]
        return devices

    def _restart_adb_server(self):
        messages = []
        for command in ("kill-server", "start-server"):
            try:
                result = subprocess.run(
                    [self.adb_path, command],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    timeout=8,
                )
                output = (self._decode_output(result.stdout) + self._decode_output(result.stderr)).strip()
                if not output:
                    output = f"返回码 {result.returncode}"
                messages.append(f"adb {command}: {output}")
            except (OSError, subprocess.TimeoutExpired) as e:
                messages.append(f"adb {command} 失败: {e}")
        return "已尝试重启 ADB server（" + "；".join(messages) + "）"

    def _adb_device_names(self):
        return [name for name, status in self._adb_devices().items() if status == "device"]

    def disconnect_adb_device(self, index):
        disconnected = False
        for candidate in self.expected_adb_device_names(index):
            disconnected = self._disconnect_adb_target(candidate) or disconnected
        return disconnected

    def _disconnect_adb_target(self, target):
        try:
            subprocess.run(
                [self.adb_path, "disconnect", target],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=5,
            )
            return True
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _connect_adb_address(self, address):
        try:
            result = subprocess.run(
                [self.adb_path, "connect", address],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired) as e:
            return f"adb connect {address} 超时或失败: {e}"

        output = (self._decode_output(result.stdout) + self._decode_output(result.stderr)).strip()
        if not output:
            output = f"adb connect {address} 返回码 {result.returncode}"
        return output

    def expected_adb_statuses(self, index):
        try:
            devices = self._adb_devices()
        except Exception as e:
            return {"error": str(e)}

        return {
            candidate: devices.get(candidate)
            for candidate in self.expected_adb_device_names(index)
        }

    def expected_adb_status_text(self, index):
        statuses = self.expected_adb_statuses(index)
        if "error" in statuses:
            return f"ADB 状态获取失败: {statuses['error']}"

        parts = []
        for candidate, status in statuses.items():
            parts.append(f"{candidate}={status or '未连接'}")
        return ", ".join(parts)

    def connect_adb_device(self, index):
        self.last_adb_connect_detail = ""
        candidates = self.expected_adb_device_names(index)
        try:
            devices = self._adb_devices()
        except Exception as e:
            self.last_adb_connect_detail = f"获取 ADB 设备列表失败: {e}"
            return None

        for candidate in candidates:
            if devices.get(candidate) == "device":
                return candidate

        stale_candidates = [candidate for candidate in candidates if candidate in devices]
        if stale_candidates:
            for candidate in stale_candidates:
                self._disconnect_adb_target(candidate)
            self.last_adb_connect_detail = f"已清理陈旧 ADB 连接: {', '.join(stale_candidates)}"

        address = self.expected_adb_connect_address(index)
        connect_outputs = []
        for attempt in range(2):
            connect_outputs.append(self._connect_adb_address(address))
            try:
                devices = self._adb_devices()
            except Exception as e:
                self.last_adb_connect_detail = f"获取 ADB 设备列表失败: {e}"
                return None

            for candidate in candidates:
                if devices.get(candidate) == "device":
                    return candidate

            stale_candidates = [
                candidate for candidate in candidates
                if candidate in devices and devices.get(candidate) != "device"
            ]
            if stale_candidates:
                for candidate in stale_candidates:
                    self._disconnect_adb_target(candidate)
                if attempt == 0:
                    time.sleep(0.5)

        status_text = self.expected_adb_status_text(index)
        self.last_adb_connect_detail = f"{'; '.join(connect_outputs)}；当前 {status_text}"
        return None

    def start_emulator(self, index):
        try:
            subprocess.Popen(
                [self.ldconsole_path, "launch", "--index", str(index)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return True
        except OSError:
            return False

    def stop_emulator(self, index):
        try:
            result = subprocess.run(
                [self.ldconsole_path, "quit", "--index", str(index)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.disconnect_adb_device(index)
            return result.returncode == 0
        except OSError:
            return False

    def get_running_indices(self):
        result = subprocess.run(
            [self.ldconsole_path, "list2"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            return []
        lines = self._decode_output(result.stdout).strip().splitlines()
        indices = []
        for line in lines:
            parts = line.strip().split(",")
            if parts and parts[0].isdigit():
                indices.append(int(parts[0]))
        return indices

    def get_all_emulators(self):
        result = subprocess.run(
            [self.ldconsole_path, "list2"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        if result.returncode != 0:
            raise Exception("获取设备列表出错")
        devices_info_list = self._decode_output(result.stdout).strip().splitlines()

        try:
            running_devices_name_arr = self._adb_device_names()
        except Exception as e:
            self.last_adb_connect_detail = f"获取 ADB 设备列表失败，已降级刷新模拟器列表: {e}"
            running_devices_name_arr = []

        emulators = []
        for line in devices_info_list:
            parts = [p.strip() for p in line.strip().split(",") if p.strip()]
            if len(parts) < 10 or not parts[0].isdigit():
                continue
            emulator_status = EmulatorStatus()
            emulator_status.index = int(parts[0])
            emulator_status.name = parts[1]
            emulator_status.run_status = int(parts[4])
            emulator_status.height = int(parts[7])
            emulator_status.width = int(parts[8])
            emulator_status.dpi = int(parts[9])
            for expected_device in self.expected_adb_device_names(emulator_status.index):
                if expected_device in running_devices_name_arr:
                    emulator_status.device_name = expected_device
                    if not emulator_status.is_running():
                        emulator_status.run_status = 1
                    break
            emulators.append(emulator_status)

        return emulators

    def save_screenshot(self, image, index):
        os.makedirs("screenshots", exist_ok=True)
        path = os.path.join("screenshots", f"screenshot_index{index}.png")
        cv2.imwrite(path, image)
        return path
