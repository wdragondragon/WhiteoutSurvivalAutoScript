import subprocess
import cv2
import numpy as np
import time
from PIL import Image
from io import BytesIO
from config import *


def adb_cmd(index, command):
    """执行雷电控制台 adb 命令"""
    full_command = [LD_CONSOLE, "adb", "--index", str(index), "--command", command]
    result = subprocess.run(full_command, stdout=subprocess.PIPE)
    return result


def get_screenshot(index):
    """获取指定模拟器截图"""
    result = adb_cmd(index, "exec-out screencap -p")
    if result.returncode != 0:
        raise Exception(f"模拟器 {index} 截图失败")
    image = Image.open(BytesIO(result.stdout))
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def find_button(image, template_path, threshold=MATCH_THRESHOLD):
    """图像匹配按钮位置"""
    template = cv2.imread(template_path)
    result = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    if max_val >= threshold:
        h, w = template.shape[:2]
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2
        return (center_x, center_y), max_val
    return None, max_val


def adb_click(index, x, y):
    """点击指定坐标"""
    adb_cmd(index, f"shell input tap {x} {y}")
    print(f"[模拟器 {index}] 点击：({x}, {y})")


def process_simulator(index):
    """处理单个模拟器实例"""
    try:
        print(f"\n▶ 处理模拟器实例 {index}")
        image = get_screenshot(index)
        for template in BUTTON_IMAGES:
            coord, score = find_button(image, template)
            if coord:
                print(f"  识别到按钮 {template} 匹配度：{score:.3f}")
                adb_click(index, *coord)
            else:
                print(f"  未识别到按钮 {template}，得分：{score:.3f}")
    except Exception as e:
        print(f"[错误] 模拟器 {index}: {e}")


def main_loop():
    print("🔁 开始自动点击循环...")
    while True:
        for index in SIMULATOR_INDEX_LIST:
            process_simulator(index)
        time.sleep(LOOP_INTERVAL)


if __name__ == "__main__":
    main_loop()
