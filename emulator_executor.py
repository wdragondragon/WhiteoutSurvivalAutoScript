# emulator_executor.py
import subprocess

import cv2
import numpy as np

import config_manager


class EmulatorExecutor:
    def __init__(self, adb_path, name, device_name):
        self.adb_path = adb_path
        self.name = name
        self.device_name = device_name

    def _run_adb(self, cmd_args):
        full_cmd = [self.adb_path, "-s", self.device_name] + cmd_args
        result = subprocess.run(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return result.stdout.decode(errors="ignore")

    def screenshot(self):
        result = subprocess.run(
            [self.adb_path, "-s", self.device_name, "exec-out", "screencap", "-p"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        if result.returncode != 0:
            raise RuntimeError(f"ADB 截图失败：{result.stderr.decode('utf-8')}")

        raw = result.stdout.replace(b'\r\r\n', b'\n')
        img_array = np.frombuffer(raw, dtype=np.uint8)
        image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if image is None:
            raise RuntimeError("图像解码失败")
        return image

    def click(self, x, y):
        self._run_adb(["shell", "input", "tap", str(x), str(y)])

    def find_and_click_button(self, template_path="buttons/button1.png", threshold=config_manager.MATCH_THRESHOLD):
        img_rgb = self.screenshot()
        template = cv2.imread(template_path)

        if img_rgb is None or template is None:
            print(f"[{self.name}] 图像读取失败")
            return False

        res = cv2.matchTemplate(img_rgb, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)

        if max_val >= threshold:
            top_left = max_loc
            h, w = template.shape[:2]
            center_x, center_y = top_left[0] + w // 2, top_left[1] + h // 2
            print(f"[{self.name}] 发现按钮，点击坐标: ({center_x}, {center_y})")
            self.click(center_x, center_y)
            return True
        else:
            print(f"[{self.name}] 未识别到按钮")
            return False
