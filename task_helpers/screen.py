import os
import time

import cv2

from app_paths import resolve_resource_path
from task_helpers.constants import (
    BASE_SCREEN_HEIGHT,
    BASE_SCREEN_WIDTH,
    BEAST_RALLY_ASSET_DIR,
    GATHER_ASSET_DIR,
    MARCH_QUEUE_ASSET_DIR,
)


def _asset(name):
    return os.path.join(BEAST_RALLY_ASSET_DIR, name)


def _gather_asset(name):
    return os.path.join(GATHER_ASSET_DIR, name)


def _march_queue_asset(name):
    return os.path.join(MARCH_QUEUE_ASSET_DIR, name)


def _march_queue_templates(*names):
    paths = []
    for name in names:
        path = _march_queue_asset(name)
        if os.path.exists(path):
            paths.append(path)
    return paths


def _existing_templates(*paths):
    result = []
    for path in paths:
        if isinstance(path, (list, tuple)):
            result.extend(_existing_templates(*path))
        elif path:
            resolved_path = resolve_resource_path(path)
            if os.path.exists(resolved_path):
                result.append(resolved_path)
    return result


def _sleep_while_running(executor, seconds):
    end_time = time.time() + max(0.0, seconds)
    while executor.run_status and time.time() < end_time:
        if hasattr(executor, "check_session_checkpoint"):
            executor.check_session_checkpoint()
        remaining = end_time - time.time()
        if remaining <= 0:
            break
        time.sleep(min(0.2, remaining))


def _base_to_ratio(x, y):
    return x / BASE_SCREEN_WIDTH, y / BASE_SCREEN_HEIGHT


def _click_base(executor, x, y, wait_seconds=0.5):
    x_ratio, y_ratio = _base_to_ratio(x, y)
    executor.emulator_executor.click_ratio(x_ratio, y_ratio)
    _sleep_while_running(executor, wait_seconds)


def _swipe_base(executor, x1, y1, x2, y2, duration_ms=300, wait_seconds=0.4):
    width, height = executor.emulator_executor.get_screen_size()
    executor.emulator_executor.swipe(
        int(width * x1 / BASE_SCREEN_WIDTH),
        int(height * y1 / BASE_SCREEN_HEIGHT),
        int(width * x2 / BASE_SCREEN_WIDTH),
        int(height * y2 / BASE_SCREEN_HEIGHT),
        duration_ms,
    )
    _sleep_while_running(executor, wait_seconds)


def _region_from_ratio(emulator_executor, left, top, right, bottom):
    width, height = emulator_executor.get_screen_size()
    return (
        int(width * left),
        int(height * top),
        int(width * right),
        int(height * bottom),
    )


def _region_from_base(emulator_executor, left, top, right, bottom):
    width, height = emulator_executor.get_screen_size()
    return (
        int(width * left / BASE_SCREEN_WIDTH),
        int(height * top / BASE_SCREEN_HEIGHT),
        int(width * right / BASE_SCREEN_WIDTH),
        int(height * bottom / BASE_SCREEN_HEIGHT),
    )


def _find_templates(executor, templates, threshold=0.82, region=None):
    paths = _existing_templates(*templates)
    if not paths:
        return None, None, False
    return executor.emulator_executor.find_img(paths, threshold=threshold, region=region, log_missing=False)


def _click_templates(executor, templates, threshold=0.82, region=None, wait_seconds=0.5):
    paths = _existing_templates(*templates)
    if not paths:
        return False
    clicked = executor.emulator_executor.click_template(
        paths,
        threshold=threshold,
        region=region,
        wait_seconds=0,
    )
    if clicked:
        _sleep_while_running(executor, wait_seconds)
    return clicked


def _wait_templates(executor, templates, timeout=5.0, threshold=0.82, region=None):
    paths = _existing_templates(*templates)
    if not paths:
        return None, None, False
    return executor.emulator_executor.wait_until_found(
        paths,
        timeout=timeout,
        threshold=threshold,
        region=region,
    )


def _template_matches_image(image, templates, threshold=0.76):
    paths = _existing_templates(templates)
    if not paths or image.size == 0:
        return False

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    for path in paths:
        template = cv2.imread(path)
        if template is None:
            continue
        if template.shape[0] > gray.shape[0] or template.shape[1] > gray.shape[1]:
            continue
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(gray, template_gray, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(result)
        if max_val >= threshold:
            return True
    return False
