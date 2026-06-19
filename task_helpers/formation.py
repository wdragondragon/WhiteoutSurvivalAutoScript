import cv2
import time

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


def _remove_icon_region_from_ratio(executor, slot_index):
    width, height = executor.emulator_executor.get_screen_size()
    _, y1, x2, _ = _slot_region_from_ratio(executor, slot_index)
    return (
        max(0, x2 - int(width * 0.12)),
        max(0, y1 + int(height * 0.03)),
        min(width, x2 + int(width * 0.08)),
        min(height, y1 + int(height * 0.10)),
    )


def _hero_slot_has_hero(executor, slot_index):
    icon_region = _remove_icon_region_from_ratio(executor, slot_index)
    _, _, remove_icon_found = _find_templates(
        executor,
        [_asset("hero_remove_icon.png")],
        threshold=0.68,
        region=icon_region,
    )
    if remove_icon_found:
        return True
    return False


def _hero_slot_is_blue(executor, slot_index):
    image = executor.emulator_executor.screenshot()
    x1, y1, x2, y2 = _slot_region_from_ratio(executor, slot_index)
    crop = image[y1:y2, x1:x2]
    if crop.size == 0:
        return False

    height, width = crop.shape[:2]
    indicator = crop[
        int(height * 0.20):int(height * 0.42),
        int(width * 0.18):int(width * 0.52),
    ]
    if indicator.size == 0:
        return False

    hsv = cv2.cvtColor(indicator, cv2.COLOR_BGR2HSV)
    blue_pixels = int(((hsv[:, :, 0] >= 88) & (hsv[:, :, 0] <= 122) &
                       (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 90)).sum())
    purple_or_gold_pixels = int((
        (((hsv[:, :, 0] >= 125) & (hsv[:, :, 0] <= 165)) |
         ((hsv[:, :, 0] >= 8) & (hsv[:, :, 0] <= 34))) &
        (hsv[:, :, 1] > 70) & (hsv[:, :, 2] > 90)
    ).sum())
    area = indicator.shape[0] * indicator.shape[1]
    blue_ratio = blue_pixels / max(1, area)
    warm_ratio = purple_or_gold_pixels / max(1, area)
    return blue_ratio >= 0.25 and blue_ratio >= warm_ratio * 1.35


def _remove_hero_slot(executor, slot_index):
    region = _remove_icon_region_from_ratio(executor, slot_index)
    if _click_templates(
        executor,
        [_asset("hero_remove_icon.png")],
        threshold=0.68,
        region=region,
        wait_seconds=0.4,
    ):
        return True

    remove_positions = [(148, 201), (267, 201), (386, 201)]
    x, y = remove_positions[min(slot_index, len(remove_positions) - 1)]
    _click_base(executor, x, y, wait_seconds=0.4)
    _sleep_while_running(executor, 0.4)
    return True


def _keep_only_blue_gather_heroes(executor):
    removed = 0
    for _ in range(len(GATHER_HERO_SLOT_REGIONS)):
        removed_this_pass = False
        for slot_index in range(len(GATHER_HERO_SLOT_REGIONS)):
            if not _hero_slot_has_hero(executor, slot_index):
                continue
            if _hero_slot_is_blue(executor, slot_index):
                continue
            log_util.log.print(f"[{executor.emulator_name}] 移除第 {slot_index + 1} 个非蓝色采集英雄")
            _remove_hero_slot(executor, slot_index)
            removed += 1
            removed_this_pass = True
            break
        if not removed_this_pass:
            break
    if removed:
        log_util.log.print(f"[{executor.emulator_name}] 已移除 {removed} 个非蓝色采集英雄")
    else:
        log_util.log.print(f"[{executor.emulator_name}] 未发现需要移除的非蓝色采集英雄")
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
    missing_slots = []
    for slot_index in range(len(GATHER_HERO_SLOT_REGIONS)):
        if not _hero_slot_has_hero(executor, slot_index):
            missing_slots.append(slot_index + 1)
    if not missing_slots:
        return True

    missing_text = ",".join(str(index) for index in missing_slots)
    log_util.log.print(f"[{executor.emulator_name}] 当前编队英雄不完整，缺少槽位: {missing_text}")
    return False


def _crop_by_ratio(image, left, top, right, bottom):
    height, width = image.shape[:2]
    return image[
        int(height * top):int(height * bottom),
        int(width * left):int(width * right),
    ]


def _mask_ratio(mask):
    if mask.size == 0:
        return 0.0
    return float(mask.sum()) / float(mask.size)


def _blue_ui_ratio(image):
    if image.size == 0:
        return 0.0
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    blue_mask = (
        (hsv[:, :, 0] >= 90) &
        (hsv[:, :, 0] <= 122) &
        (hsv[:, :, 1] > 45) &
        (hsv[:, :, 2] > 120)
    )
    return _mask_ratio(blue_mask)


def _pale_panel_ratio(image):
    if image.size == 0:
        return 0.0
    pale_mask = (
        (image[:, :, 0] > 150) &
        (image[:, :, 1] > 170) &
        (image[:, :, 2] > 170)
    )
    return _mask_ratio(pale_mask)


def _looks_like_formation_image(image):
    if image is None or image.size == 0:
        return False

    march_button_region = _crop_by_ratio(image, 0.55, 0.90, 0.98, 0.995)
    formation_tabs_region = _crop_by_ratio(image, 0.02, 0.06, 0.98, 0.13)
    troop_rows_region = _crop_by_ratio(image, 0.00, 0.48, 1.00, 0.82)

    return (
        _blue_ui_ratio(march_button_region) >= 0.30 and
        _blue_ui_ratio(formation_tabs_region) >= 0.25 and
        _pale_panel_ratio(troop_rows_region) >= 0.20
    )


def _looks_like_formation_screen(executor):
    image = executor.emulator_executor.screenshot()
    return _looks_like_formation_image(image)


def _is_formation_visible(executor):
    _, _, found = _find_templates(
        executor,
        [_asset("march_button.png"), _asset("formation_anchor.png")],
        threshold=0.74,
    )
    return found or _looks_like_formation_screen(executor)


def _wait_formation_visible(executor, timeout=6.0):
    end_time = time.time() + max(0.0, timeout)
    while executor.run_status:
        if _is_formation_visible(executor):
            return True
        if time.time() >= end_time:
            break
        _sleep_while_running(executor, 0.3)
    return False
