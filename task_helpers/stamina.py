import os

import cv2
import numpy as np

import log_util
from task_helpers.constants import BEAST_RALLY_ASSET_DIR
from task_helpers.navigation import _return_home_or_wild
from task_helpers.screen import (
    _asset,
    _click_base,
    _click_templates,
    _region_from_base,
    _region_from_ratio,
)


def _is_stamina_dialog_visible(executor):
    from task_helpers.screen import _find_templates

    _, _, found = _find_templates(
        executor,
        [
            _asset("stamina_not_enough_title.png"),
            _asset("stamina_can_item.png"),
            _asset("use_stamina_can_button.png"),
        ],
        threshold=0.72,
        region=_region_from_ratio(executor.emulator_executor, 0.08, 0.18, 0.92, 0.86),
    )
    return found


def _looks_like_modal_dialog(executor):
    image = executor.emulator_executor.screenshot()
    height, width = image.shape[:2]
    x1, y1, x2, y2 = (
        int(width * 0.08),
        int(height * 0.20),
        int(width * 0.92),
        int(height * 0.82),
    )
    crop = image[y1:y2, x1:x2]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    blue_pixels = int(((hsv[:, :, 0] > 85) & (hsv[:, :, 0] < 120) & (hsv[:, :, 1] > 35) & (hsv[:, :, 2] > 80)).sum())
    bright_pixels = int((hsv[:, :, 2] > 170).sum())
    return blue_pixels > 8000 and bright_pixels > 15000


BUILTIN_DIGIT_PATTERNS = {
    "0": [
        ".####.",
        "######",
        "##..##",
        "##..##",
        "##..##",
        "##..##",
        "######",
        ".####.",
    ],
    "1": [
        "..##..",
        ".###..",
        "..##..",
        "..##..",
        "..##..",
        "..##..",
        ".####.",
        ".####.",
    ],
    "2": [
        ".####.",
        "######",
        "#...##",
        "...###",
        "..###.",
        ".###..",
        "#####.",
        "######",
    ],
    "3": [
        "#####.",
        "######",
        "....##",
        "..####",
        "..####",
        "....##",
        "######",
        "#####.",
    ],
    "4": [
        "....#.",
        "..###.",
        "..###.",
        ".####.",
        "##..#.",
        "######",
        "######",
        "...###",
    ],
    "5": [
        "######",
        "######",
        "##....",
        "#####.",
        ".#####",
        "....##",
        "######",
        "#####.",
    ],
    "6": [
        ".####.",
        "#####.",
        "##....",
        "#####.",
        "######",
        "##..##",
        "######",
        ".####.",
    ],
    "7": [
        "####.",
        "#####",
        "...##",
        "...#.",
        "..##.",
        "..##.",
        ".##..",
        ".##..",
    ],
    "8": [
        "..##..",
        ".####.",
        "##..#.",
        "#####.",
        "#####.",
        "##..##",
        "##..##",
        "#####.",
    ],
    "9": [
        "##....",
        "####..",
        "##..##",
        "##..##",
        "######",
        "....##",
        "#.####",
        "#####.",
    ],
}


def _normalize_digit_mask(mask, size=(16, 20)):
    points = cv2.findNonZero(mask)
    if points is None:
        return None
    x, y, w, h = cv2.boundingRect(points)
    digit = mask[y:y + h, x:x + w]
    return cv2.resize(digit, size, interpolation=cv2.INTER_NEAREST)


def _digit_pattern_to_mask(pattern):
    height = len(pattern)
    width = max(len(row) for row in pattern)
    mask = np.zeros((height, width), dtype="uint8")
    for y, row in enumerate(pattern):
        for x, value in enumerate(row):
            if value != ".":
                mask[y, x] = 255
    return mask


def _load_digit_templates():
    digit_dir = os.path.join(BEAST_RALLY_ASSET_DIR, "digits")
    templates = {digit: [] for digit in "0123456789"}
    if os.path.isdir(digit_dir):
        for digit in "0123456789":
            path = os.path.join(digit_dir, f"{digit}.png")
            if not os.path.exists(path):
                continue
            image = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
            if image is None:
                continue
            _, mask = cv2.threshold(image, 127, 255, cv2.THRESH_BINARY)
            normalized = _normalize_digit_mask(mask)
            if normalized is not None:
                templates[digit].append(normalized)

    for digit, pattern in BUILTIN_DIGIT_PATTERNS.items():
        normalized = _normalize_digit_mask(_digit_pattern_to_mask(pattern))
        if normalized is not None:
            templates[digit].append(normalized)

    return {digit: masks for digit, masks in templates.items() if masks}


def _split_digit_group(mask, start, end):
    group_width = end - start
    if group_width <= 7:
        return [(start, end)]

    column_counts = (mask[:, start:end] > 0).sum(axis=0)
    midpoint = group_width // 2
    left = max(3, midpoint - 3)
    right = min(group_width - 3, midpoint + 3)
    if left > right:
        return [(start, end)]

    split_candidates = range(left, right + 1)
    split_at = min(split_candidates, key=lambda index: column_counts[index])
    absolute_split = start + split_at
    if column_counts[split_at] <= 1:
        left_group = (start, absolute_split)
        right_group = (absolute_split + 1, end)
    else:
        left_group = (start, absolute_split)
        right_group = (absolute_split, end)

    result = []
    for group_start, group_end in (left_group, right_group):
        if group_end - group_start <= 0:
            continue
        result.extend(_split_digit_group(mask, group_start, group_end))
    return result


def _segment_digit_groups(mask):
    column_has_digit = mask.sum(axis=0) > 0
    groups = []
    start = None
    for index, active in enumerate(column_has_digit):
        if active and start is None:
            start = index
        elif not active and start is not None:
            groups.extend(_split_digit_group(mask, start, index))
            start = None
    if start is not None:
        groups.extend(_split_digit_group(mask, start, len(column_has_digit)))
    return groups


def _read_stamina_can_count(executor):
    templates = _load_digit_templates()
    if not templates:
        return None

    image = executor.emulator_executor.screenshot()
    x1, y1, x2, y2 = _region_from_base(executor.emulator_executor, 66, 335, 96, 352)
    roi = image[y1:y2, x1:x2]
    if roi.size == 0:
        return None

    roi = cv2.resize(roi, (30, 17), interpolation=cv2.INTER_AREA)
    blue, green, red = cv2.split(roi)
    mask = (((blue > 170) & (green > 170) & (red > 170)).astype("uint8")) * 255
    groups = _segment_digit_groups(mask)

    digits = []
    for start, end in groups:
        candidate = mask[:, start:end]
        points = cv2.findNonZero(candidate)
        if points is None:
            continue
        _, y, w, h = cv2.boundingRect(points)
        area = int((candidate > 0).sum())
        if w < 3 or h < 6 or area < 12:
            continue

        normalized = _normalize_digit_mask(candidate)
        if normalized is None:
            continue

        best_digit = None
        best_score = 0.0
        for digit, digit_templates in templates.items():
            for template in digit_templates:
                intersection = int(((normalized > 0) & (template > 0)).sum())
                union = int(((normalized > 0) | (template > 0)).sum())
                score = intersection / union if union else 0.0
                if score > best_score:
                    best_digit = digit
                    best_score = score
        if best_digit is None or best_score < 0.28:
            return None
        digits.append(best_digit)

    if not digits:
        return None
    try:
        return int("".join(digits))
    except ValueError:
        return None


def _close_stamina_dialog(executor):
    if _is_stamina_dialog_visible(executor) or _looks_like_modal_dialog(executor):
        if not _click_templates(
            executor,
            [_asset("stamina_close_x.png"), _asset("close_x.png")],
            threshold=0.72,
            region=_region_from_ratio(executor.emulator_executor, 0.82, 0.06, 1.0, 0.16),
            wait_seconds=1.0,
        ):
            _click_base(executor, 416, 84, wait_seconds=1.0)


def _claim_free_stamina(executor):
    log_util.log.print(f"[{executor.emulator_name}] 优先尝试领取免费体力")
    if not _click_templates(
        executor,
        [_asset("free_stamina_claim_button.png")],
        threshold=0.72,
        region=_region_from_ratio(executor.emulator_executor, 0.60, 0.24, 0.96, 0.38),
        wait_seconds=1.0,
    ):
        _click_base(executor, 362, 248, wait_seconds=1.0)
    _close_stamina_dialog(executor)
    return True


def _handle_stamina_shortage(
        executor,
        use_stamina_can,
        stamina_can_reserve_count,
        use_diamond_for_stamina,
        try_free_stamina,
):
    if not (_is_stamina_dialog_visible(executor) or _looks_like_modal_dialog(executor)):
        return False

    if try_free_stamina:
        return _claim_free_stamina(executor)

    stamina_can_blocked = False
    stamina_can_block_reason = None
    if use_stamina_can:
        can_count = _read_stamina_can_count(executor)
        if can_count is None and stamina_can_reserve_count > 0:
            path = executor.emulator_executor.save_debug_screenshot("stamina_can_count_unknown")
            stamina_can_block_reason = "未能识别背包体力罐头数量，已配置保留数量，停止使用罐头"
            log_util.log.print(f"[{executor.emulator_name}] {stamina_can_block_reason}，截图: {path}")
            stamina_can_blocked = True
        elif can_count is not None and can_count <= stamina_can_reserve_count:
            stamina_can_block_reason = (
                f"背包体力罐头数量 {can_count} 小于等于保留数量 {stamina_can_reserve_count}，不再使用"
            )
            log_util.log.print(f"[{executor.emulator_name}] {stamina_can_block_reason}")
            stamina_can_blocked = True
        else:
            log_util.log.print(f"[{executor.emulator_name}] 体力不足，尝试使用背包体力罐头")
            if not _click_templates(
                executor,
                [_asset("use_stamina_can_button.png")],
                threshold=0.72,
                region=_region_from_ratio(executor.emulator_executor, 0.60, 0.30, 0.96, 0.48),
                wait_seconds=1.0,
            ):
                _click_base(executor, 362, 327, wait_seconds=1.0)
            _close_stamina_dialog(executor)
            return True

    if use_diamond_for_stamina:
        log_util.log.print(f"[{executor.emulator_name}] 体力不足，允许钻石购买体力，尝试购买")
        if not _click_templates(
            executor,
            [_asset("buy_stamina_with_diamond_button.png")],
            threshold=0.72,
            region=_region_from_ratio(executor.emulator_executor, 0.60, 0.42, 0.96, 0.62),
            wait_seconds=1.0,
        ):
            _click_base(executor, 362, 417, wait_seconds=1.0)
        if _looks_like_modal_dialog(executor):
            if not _click_templates(
                executor,
                [_asset("confirm_button.png"), _asset("ok_button.png")],
                threshold=0.72,
                region=_region_from_ratio(executor.emulator_executor, 0.42, 0.55, 0.95, 0.82),
                wait_seconds=1.0,
            ):
                _click_base(executor, 318, 493, wait_seconds=1.0)
        _close_stamina_dialog(executor)
        return True

    if stamina_can_blocked or not use_stamina_can:
        path = executor.emulator_executor.save_debug_screenshot("stamina_not_enough")
        if stamina_can_block_reason:
            message = f"体力不足，{stamina_can_block_reason}，且未允许钻石购买"
        elif not use_stamina_can:
            message = "体力不足，未启用背包体力罐头，且未允许钻石购买"
        else:
            message = "体力不足，背包体力罐头未能使用，且未允许钻石购买"
        log_util.log.print(f"[{executor.emulator_name}] {message}，截图: {path}")
        _return_home_or_wild(executor)
        return False
    return False
