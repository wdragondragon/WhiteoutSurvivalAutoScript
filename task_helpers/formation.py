import cv2

import log_util
from task_helpers.constants import GATHER_HERO_SLOT_REGIONS
from task_helpers.screen import (
    _asset,
    _click_base,
    _click_templates,
    _find_templates,
    _region_from_ratio,
    _sleep_while_running,
)


def _slot_region_from_ratio(executor, slot_index):
    left, top, right, bottom = GATHER_HERO_SLOT_REGIONS[slot_index]
    return _region_from_ratio(executor.emulator_executor, left, top, right, bottom)


def _hero_slot_has_hero(executor, slot_index):
    region = _slot_region_from_ratio(executor, slot_index)
    _, _, remove_icon_found = _find_templates(
        executor,
        [_asset("hero_remove_icon.png")],
        threshold=0.70,
        region=region,
    )
    if remove_icon_found:
        return True

    image = executor.emulator_executor.screenshot()
    x1, y1, x2, y2 = region
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return False
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    saturated_pixels = int(((hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 90)).sum())
    return saturated_pixels > 1200


def _hero_slot_is_blue(executor, slot_index):
    image = executor.emulator_executor.screenshot()
    x1, y1, x2, y2 = _slot_region_from_ratio(executor, slot_index)
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return False

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    blue_pixels = int(((hsv[:, :, 0] >= 88) & (hsv[:, :, 0] <= 122) &
                       (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 90)).sum())
    purple_or_gold_pixels = int((
        (((hsv[:, :, 0] >= 125) & (hsv[:, :, 0] <= 165)) |
         ((hsv[:, :, 0] >= 8) & (hsv[:, :, 0] <= 34))) &
        (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 90)
    ).sum())
    return blue_pixels >= max(80, purple_or_gold_pixels * 1.2)


def _remove_hero_slot(executor, slot_index):
    region = _slot_region_from_ratio(executor, slot_index)
    if _click_templates(
        executor,
        [_asset("hero_remove_icon.png")],
        threshold=0.70,
        region=region,
        wait_seconds=0.4,
    ):
        return True

    x1, y1, x2, _ = region
    executor.emulator_executor.click(x2 - 12, y1 + 12)
    _sleep_while_running(executor, 0.4)
    return True


def _keep_only_blue_gather_heroes(executor):
    removed = 0
    for slot_index in range(len(GATHER_HERO_SLOT_REGIONS)):
        if not _hero_slot_has_hero(executor, slot_index):
            continue
        if _hero_slot_is_blue(executor, slot_index):
            continue
        _remove_hero_slot(executor, slot_index)
        removed += 1
    if removed:
        log_util.log.print(f"[{executor.emulator_name}] 已移除 {removed} 个非蓝色采集英雄")
    return True


def _first_gather_hero_present(executor):
    return _hero_slot_has_hero(executor, 0)


def _select_formation(executor, formation_index):
    if formation_index < 1:
        formation_index = 1
    if formation_index > 8:
        log_util.log.print(f"[{executor.emulator_name}] 当前只支持直接选择 1-8 号编队，改用 8 号")
        formation_index = 8

    x = 38 + (formation_index - 1) * 45
    _click_base(executor, x, 75, wait_seconds=0.8)
    log_util.log.print(f"[{executor.emulator_name}] 已选择 {formation_index} 号编队")
    return formation_index


def _select_next_formation(executor, formation_indices, require_hero_for_march):
    key = f"formation_cursor:{','.join(str(index) for index in formation_indices)}"
    cursor = int(executor.state.get(key, 0)) % len(formation_indices)

    for offset in range(len(formation_indices)):
        list_index = (cursor + offset) % len(formation_indices)
        formation_index = formation_indices[list_index]
        _select_formation(executor, formation_index)

        if require_hero_for_march and not _has_hero(executor):
            log_util.log.print(f"[{executor.emulator_name}] {formation_index} 号编队未识别到英雄，跳过该编队")
            continue

        executor.state[key] = (list_index + 1) % len(formation_indices)
        return formation_index

    log_util.log.print(f"[{executor.emulator_name}] 配置的编队均未识别到英雄，结束本轮")
    return None


def _has_hero(executor):
    hero_region = _region_from_ratio(executor.emulator_executor, 0.08, 0.20, 0.92, 0.48)
    _, _, remove_icon_found = _find_templates(
        executor,
        [_asset("hero_remove_icon.png")],
        threshold=0.74,
        region=hero_region,
    )
    if remove_icon_found:
        return True

    image = executor.emulator_executor.screenshot()
    height, width = image.shape[:2]
    x1, y1, x2, y2 = (
        int(width * 0.08),
        int(height * 0.20),
        int(width * 0.92),
        int(height * 0.48),
    )
    crop = image[y1:y2, x1:x2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mean_saturation = float(hsv[:, :, 1].mean())
    orange_pixels = int(((hsv[:, :, 0] > 5) & (hsv[:, :, 0] < 35) & (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 120)).sum())
    return mean_saturation > 80 or orange_pixels > 5000


def _is_formation_visible(executor):
    _, _, found = _find_templates(
        executor,
        [_asset("march_button.png"), _asset("formation_anchor.png")],
        threshold=0.74,
    )
    return found
