import subprocess
import time

import cv2

from simulator_manager import EmulatorManager

ADB_PATH = r"C:\leidian\LDPlayer9\adb.exe"
LDCONSOLE_PATH = r"C:\leidian\LDPlayer9\ldconsole.exe"


def find_button_and_click(device_name, screenshot, template_path, threshold=0.8):
    # 读模板图
    template = cv2.imread(template_path, cv2.IMREAD_COLOR)
    if template is None:
        raise Exception("模板图片读取失败")

    res = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    print(f"设备{device_name}匹配度最高: {max_val}")

    if max_val >= threshold:
        top_left = max_loc
        h, w = template.shape[:2]
        center_x = top_left[0] + w // 2
        center_y = top_left[1] + h // 2

        print(f"点击坐标: ({center_x}, {center_y})")
        cmd = [
            ADB_PATH, "-s", device_name,
            "shell", "input", "tap", str(center_x), str(center_y)
        ]
        click_result = subprocess.run(cmd, capture_output=True, text=True)
        if click_result.returncode != 0:
            raise Exception(f"点击失败: {click_result.stderr}")
        print(f"设备{device_name}点击成功")
        return True
    else:
        print(f"设备{device_name}未找到按钮，匹配度不足")
        return False


def main_loop(template_path, interval=2):
    manager = EmulatorManager(ADB_PATH, LDCONSOLE_PATH)
    while True:
        index_to_device = manager.get_index_name_map()
        print("现正在运行模拟器列表:", index_to_device)
        for device_name in index_to_device.values():
            try:
                screenshot = manager.get_screenshot(device_name)
                find_button_and_click(device_name, screenshot, template_path)
            except Exception as e:
                print(f"设备{device_name}出错: {e}")
        print(f"等待{interval}秒后继续...")
        time.sleep(interval)


if __name__ == "__main__":
    TEMPLATE_PATH = "buttons/button1.png"  # 你按钮的模板图片路径
    main_loop(TEMPLATE_PATH)
