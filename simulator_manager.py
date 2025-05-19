# simulator_manager.py
import os
import subprocess

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

    def get_running_indices(self):
        result = subprocess.run([self.ldconsole_path, "list2"], capture_output=True, text=True)
        if result.returncode != 0:
            return []
        lines = result.stdout.strip().splitlines()
        indices = []
        for line in lines:
            parts = line.strip().split(",")
            if parts and parts[0].isdigit():
                indices.append(int(parts[0]))
        return indices

    def get_all_emulators(self):
        result = subprocess.run([self.ldconsole_path, "list2"], capture_output=True, text=True)
        if result.returncode != 0:
            raise Exception("获取设备列表出错")
        devices_info_list = result.stdout.strip().splitlines()

        running_devices_name = subprocess.run(
            [self.adb_path, "devices"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if running_devices_name.returncode != 0:
            raise Exception("获取正在运行的设备出错")
        running_devices_info_arr = [b.decode('utf-8').strip() for b in
                                    running_devices_name.stdout.strip().splitlines()[1:] if b.decode('utf-8').strip()]
        running_devices_name_arr = [devices_info.strip().split()[0] for devices_info in running_devices_info_arr]
        emulators = []
        running_devices_index = 0
        for line in devices_info_list:
            parts = [p.strip() for p in line.strip().split(",") if p.strip()]
            emulator_status = EmulatorStatus()
            emulator_status.index = int(parts[0])
            emulator_status.name = parts[1]
            emulator_status.run_status = int(parts[4])
            emulator_status.height = int(parts[7])
            emulator_status.width = int(parts[8])
            emulator_status.dpi = int(parts[9])
            if emulator_status.is_running() and running_devices_index < len(running_devices_name_arr):
                emulator_status.device_name = running_devices_name_arr[running_devices_index]
                running_devices_index += 1
            emulators.append(emulator_status)
        return emulators

    def save_screenshot(self, image, index):
        os.makedirs("screenshots", exist_ok=True)
        path = os.path.join("screenshots", f"screenshot_index{index}.png")
        cv2.imwrite(path, image)
        return path
