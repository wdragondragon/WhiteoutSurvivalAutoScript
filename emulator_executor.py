# emulator_executor.py
import os
import subprocess
import tempfile
import time
from typing import Union, List, Optional, Tuple

import cv2
import numpy as np

import config_manager
import log_util


class EmulatorExecutor:
    def __init__(self, adb_path, name, device_name, action_gate=None, before_input_action=None):
        self.adb_path = adb_path
        self.name = name
        self.device_name = device_name
        self.action_gate = action_gate
        self.before_input_action = before_input_action
        self._in_before_input_action = False

    def _run_adb(self, cmd_args):
        full_cmd = [self.adb_path, "-s", self.device_name] + cmd_args
        result = subprocess.run(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        return result.stdout.decode(errors="ignore")

    def _before_input(self, action_name):
        if self._in_before_input_action:
            if self.action_gate:
                self.action_gate.wait_before_action(self.name, action_name)
            return
        self._in_before_input_action = True
        try:
            if self.before_input_action:
                self.before_input_action(action_name)
        finally:
            self._in_before_input_action = False
        if self.action_gate:
            self.action_gate.wait_before_action(self.name, action_name)

    def screenshot(self, retries=3, retry_interval=0.2):
        last_error = None
        for _ in range(retries):
            result = subprocess.run(
                [self.adb_path, "-s", self.device_name, "exec-out", "screencap", "-p"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.returncode != 0:
                last_error = result.stderr.decode("utf-8", errors="ignore")
                time.sleep(retry_interval)
                continue

            raw = result.stdout.replace(b'\r\r\n', b'\n')
            img_array = np.frombuffer(raw, dtype=np.uint8)
            image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if image is not None:
                return image
            last_error = "图像解码失败"
            time.sleep(retry_interval)
        raise RuntimeError(f"ADB 截图失败: {last_error}")

    def click(self, x, y):
        self._before_input("click")
        self._run_adb(["shell", "input", "tap", str(x), str(y)])

    def swipe(self, x1, y1, x2, y2, duration_ms=300):
        self._before_input("swipe")
        self._run_adb([
            "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration_ms)
        ])

    def press_back(self):
        self._before_input("press_back")
        self._run_adb(["shell", "input", "keyevent", "4"])

    def input_text(self, text):
        self._before_input("input_text")
        escaped = str(text).replace(" ", "%s")
        self._run_adb(["shell", "input", "text", escaped])

    def clear_text(self, count=6):
        self._before_input("clear_text_move_end")
        self._run_adb(["shell", "input", "keyevent", "123"])
        for _ in range(count):
            self._before_input("clear_text_delete")
            self._run_adb(["shell", "input", "keyevent", "67"])

    def get_screen_size(self):
        image = self.screenshot()
        height, width = image.shape[:2]
        return width, height

    def click_ratio(self, x_ratio, y_ratio):
        width, height = self.get_screen_size()
        x = int(width * x_ratio)
        y = int(height * y_ratio)
        self.click(x, y)
        return x, y

    def tap_and_wait(self, x, y, wait_seconds=0.5):
        self.click(x, y)
        time.sleep(wait_seconds)

    def save_debug_screenshot(self, prefix="screenshot"):
        image = self.screenshot()
        debug_dir = os.path.join(tempfile.gettempdir(), "whiteout_survival_auto_script")
        os.makedirs(debug_dir, exist_ok=True)
        path = os.path.join(debug_dir, f"{prefix}_{int(time.time())}.png")
        cv2.imwrite(path, image)
        return path

    def find_and_click_text(self, target_text, lang='chi_sim'):
        import pytesseract
        img = self.screenshot()
        # 灰度化提升识别率
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        data = pytesseract.image_to_data(gray, lang=lang, output_type=pytesseract.Output.DICT)
        for i in range(len(data['text'])):
            text = data['text'][i].strip()
            if target_text in text:
                x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                center_x = x + w // 2
                center_y = y + h // 2
                log_util.log.print(f"找到文本 [{text}]，点击位置：({center_x}, {center_y})")
                self.click(center_x, center_y)
                return True

        log_util.log.print(f"未找到文本 [{target_text}]")
        return False

    def find_and_click_button(self, template_path="buttons/button1.png", threshold=config_manager.MATCH_THRESHOLD):
        return self.click_template(template_path, threshold=threshold)

    def click_template(self,
                       template_path: Union[str, List[str]],
                       threshold: float = config_manager.MATCH_THRESHOLD,
                       region: Optional[Tuple[int, int, int, int]] = None,
                       wait_seconds: float = 0.3) -> bool:
        x, y, find = self.find_img(template_path, threshold=threshold, region=region)
        if not find:
            return False
        self.click(x, y)
        if wait_seconds:
            time.sleep(wait_seconds)
        return True

    def wait_until_found(self,
                         template_path: Union[str, List[str]],
                         timeout: float = 5.0,
                         interval: float = 0.5,
                         threshold: float = config_manager.MATCH_THRESHOLD,
                         region: Optional[Tuple[int, int, int, int]] = None
                         ) -> Tuple[Optional[int], Optional[int], bool]:
        end_time = time.time() + timeout
        while time.time() < end_time:
            x, y, find = self.find_img(template_path, threshold=threshold, region=region, log_missing=False)
            if find:
                return x, y, True
            time.sleep(interval)
        return None, None, False

    def find_img(self,
                 template_path: Union[str, List[str]],
                 threshold: float = config_manager.MATCH_THRESHOLD,
                 region: Optional[Tuple[int, int, int, int]] = None,
                 log_missing: bool = True,
                 ) -> Tuple[Optional[int], Optional[int], bool]:
        img_rgb = self.screenshot()
        if img_rgb is None:
            log_util.log.print(f"[{self.name}] 截图失败")
            return None, None, False

        offset_x = 0
        offset_y = 0
        if region:
            x1, y1, x2, y2 = region
            img_rgb = img_rgb[y1:y2, x1:x2]
            offset_x = x1
            offset_y = y1
        img_gray = cv2.cvtColor(img_rgb, cv2.COLOR_BGR2GRAY)
        # img_gray = cv2.Canny(cv2.cvtColor(img_rgb, cv2.COLOR_BGR2GRAY), 50, 200)

        if isinstance(template_path, str):
            template_path = [template_path]

        for path in template_path:
            template = cv2.imread(path)
            if template is None:
                if log_missing:
                    log_util.log.print(f"[{self.name}] 模板图像读取失败: {path}")
                continue
            if template.shape[0] > img_gray.shape[0] or template.shape[1] > img_gray.shape[1]:
                continue

            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            # template_gray = cv2.Canny(cv2.cvtColor(template, cv2.COLOR_BGR2GRAY), 50, 200)
            res = cv2.matchTemplate(img_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= threshold:
                top_left = max_loc
                h, w = template.shape[:2]
                center_x = offset_x + top_left[0] + w // 2
                center_y = offset_y + top_left[1] + h // 2
                # log_util.log.print(f"[{self.name}] 图片坐标: ({center_x}, {center_y})，相似度: {max_val:.2f}")
                return center_x, center_y, True

        return None, None, False
