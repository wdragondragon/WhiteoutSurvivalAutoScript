# emulator_executor.py
import subprocess
from typing import Union, List, Optional, Tuple

import cv2
import numpy as np

import config_manager
import log_util


class EmulatorExecutor:
    def __init__(self, adb_path, name, device_name):
        self.adb_path = adb_path
        self.name = name
        self.device_name = device_name

    def _run_adb(self, cmd_args):
        full_cmd = [self.adb_path, "-s", self.device_name] + cmd_args
        result = subprocess.run(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                creationflags=subprocess.CREATE_NO_WINDOW)
        return result.stdout.decode(errors="ignore")

    def screenshot(self):
        result = subprocess.run(
            [self.adb_path, "-s", self.device_name, "exec-out", "screencap", "-p"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW
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
        x, y, find = self.find_img(template_path, threshold)
        if find:
            # log_util.log.print(f"[{self.name}] 点击坐标: ({x}, {y})")
            self.click(x, y)
            return True
        else:
            return False

    def find_img(self,
                 template_path: Union[str, List[str]],
                 threshold: float = config_manager.MATCH_THRESHOLD,
                 region: Optional[Tuple[int, int, int, int]] = None,
                 ) -> Tuple[Optional[int], Optional[int], bool]:
        img_rgb = self.screenshot()
        if img_rgb is None:
            log_util.log.print(f"[{self.name}] 截图失败")
            return None, None, False

        if region:
            x1, y1, x2, y2 = region
            img_rgb = img_rgb[y1:y2, x1:x2]
        cv2.imwrite("test.png", img_rgb)
        img_gray = cv2.cvtColor(img_rgb, cv2.COLOR_BGR2GRAY)
        # img_gray = cv2.Canny(cv2.cvtColor(img_rgb, cv2.COLOR_BGR2GRAY), 50, 200)

        if isinstance(template_path, str):
            template_path = [template_path]

        for path in template_path:
            template = cv2.imread(path)
            if template is None:
                log_util.log.print(f"[{self.name}] 模板图像读取失败: {path}")
                continue

            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            # template_gray = cv2.Canny(cv2.cvtColor(template, cv2.COLOR_BGR2GRAY), 50, 200)
            res = cv2.matchTemplate(img_gray, template_gray, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(res)
            if max_val >= threshold:
                top_left = max_loc
                h, w = template.shape[:2]
                center_x, center_y = top_left[0] + w // 2, top_left[1] + h // 2
                # log_util.log.print(f"[{self.name}] 图片坐标: ({center_x}, {center_y})，相似度: {max_val:.2f}")
                return center_x, center_y, True

        return None, None, False
