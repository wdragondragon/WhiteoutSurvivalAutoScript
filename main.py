import subprocess
import time

import numpy as np
import cv2
import os

ADB_PATH = r"C:\leidian\LDPlayer9\adb.exe"
LDCONSOLE_PATH = r"C:\leidian\LDPlayer9\ldconsole.exe"


def get_all_device_indices():
    result = subprocess.run([LDCONSOLE_PATH, "runningList2"], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("ldconsole runningList2 执行失败")

    lines = result.stdout.strip().splitlines()
    indices = []
    for line in lines:
        parts = line.strip().split(",")
        if parts and parts[0].isdigit():
            indices.append(int(parts[0]))
    return indices


def get_all_device_names():
    indices = get_all_device_indices()
    if len(indices) == 0:
        raise RuntimeError("先运行一台模拟器")
    index = indices[0]
    result = subprocess.run(
        [LDCONSOLE_PATH, "adb", "--index", str(index), "--command", "devices"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if result.returncode != 0:
        raise Exception("获取模拟器设备名失败")
    lines = result.stdout.strip().splitlines()
    indices_name_map = {}
    lines = lines[1:]
    lines = [b.decode('utf-8').strip() for b in lines if b.decode('utf-8').strip() != '']
    for i in range(len(lines)):
        parts = lines[i].strip().split()
        indices_name_map[indices[i]] = parts[0]
    print(indices_name_map)
    return indices_name_map


def get_screenshot(device_name):
    result = subprocess.run(
        [ADB_PATH, "-s", device_name, "exec-out", "screencap", "-p"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    if result.returncode != 0:
        raise Exception(f"ADB 截图失败: {result.stderr.decode('utf-8')}")

    # 修复换行
    raw = result.stdout.replace(b'\r\r\n', b'\n')
    img_array = np.frombuffer(raw, dtype=np.uint8)
    image = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if image is None:
        raise Exception("图像解码失败")
    return image


def save_screenshot(image, filename="screenshot_fixed.png"):
    os.makedirs("screenshots", exist_ok=True)
    path = os.path.join("screenshots", filename)
    cv2.imwrite(path, image)
    print(f"✅ 保存成功：{path}")


def find_button_and_click(device_index, device_name, screenshot, template_path, threshold=0.8):
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

        # 使用 ldconsole adb 点击（替代 adb shell input tap）
        cmd = [
            LDCONSOLE_PATH, "adb", "--index", str(device_index),
            "--command", f"shell input tap {center_x} {center_y}"
        ]
        click_result = subprocess.run(cmd, capture_output=True, text=True)
        if click_result.returncode != 0:
            raise Exception(f"点击失败: {click_result.stderr}")
        print(f"设备{device_index}点击成功")
        return True
    else:
        print(f"设备{device_index}未找到按钮，匹配度不足")
        return False


def main_loop(template_path, interval=2):
    while True:
        index_to_device = get_all_device_names()
        print("现正在运行模拟器列表:", index_to_device)
        for device_index, device_name in index_to_device.items():
            try:
                screenshot = get_screenshot(device_name)
                find_button_and_click(device_index, device_name, screenshot, template_path)
            except Exception as e:
                print(f"设备{device_name}出错: {e}")
        print(f"等待{interval}秒后继续...")
        time.sleep(interval)


if __name__ == "__main__":
    TEMPLATE_PATH = "buttons/button1.png"  # 你按钮的模板图片路径
    main_loop(TEMPLATE_PATH)
