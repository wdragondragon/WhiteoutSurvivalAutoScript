# simulator_manager.py
import os
import subprocess

import cv2

from executor import EmulatorExecutor


class EmulatorManager:
    def __init__(self, adb_path, ldconsole_path):
        self.adb_path = adb_path
        self.ldconsole_path = ldconsole_path

    def get_running_indices(self):
        result = subprocess.run([self.ldconsole_path, "runningList2"], capture_output=True, text=True)
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().splitlines()
        indices = []
        for line in lines:
            parts = line.strip().split(",")
            if parts and parts[0].isdigit():
                indices.append(int(parts[0]))
        return indices

    def get_running_emulators(self):
        result = subprocess.run([self.ldconsole_path, "runningList2"], capture_output=True, text=True)
        if result.returncode != 0:
            return []
        emulators = []
        for line in result.stdout.strip().splitlines():
            parts = [p.strip() for p in line.strip().split(",") if p.strip()]
            if parts and parts[0].isdigit():
                emulators.append(f"{parts[0]},{parts[1]}")
        return emulators

    def get_index_name_map(self):
        indices = self.get_running_indices()
        if not indices:
            raise RuntimeError("未检测到运行中的模拟器")

        result = subprocess.run(
            [self.ldconsole_path, "adb", "--index", str(indices[0]), "--command", "\"devices\""],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if result.returncode != 0:
            raise RuntimeError("无法获取设备名")

        lines = result.stdout.strip().splitlines()[1:]
        names = [b.decode('utf-8').strip() for b in lines if b.decode('utf-8').strip()]
        index_name_map = {}

        for i in range(min(len(indices), len(names))):
            parts = names[i].split()
            if parts:
                index_name_map[indices[i]] = parts[0]
        return index_name_map

    def get_screenshot(self, device_name):
        executor = EmulatorExecutor(adb_path=self.adb_path, emulator_name=device_name)
        return executor.screenshot()

    def save_screenshot(self, image, index):
        os.makedirs("screenshots", exist_ok=True)
        path = os.path.join("screenshots", f"screenshot_index{index}.png")
        cv2.imwrite(path, image)
        return path
