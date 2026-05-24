import cv2

import log_util
from task_helpers.constants import (
    BASE_SCREEN_HEIGHT,
    BASE_SCREEN_WIDTH,
    MARCH_QUEUE_ROW_BASE_Y,
    MAX_ACTIVE_MARCHES,
)
from task_helpers.screen import (
    _click_base,
    _find_templates,
    _march_queue_asset,
    _march_queue_templates,
    _region_from_ratio,
    _template_matches_image,
)


def _get_active_march_count(executor):
    image = executor.emulator_executor.screenshot()
    height, width = image.shape[:2]
    roi = image[int(height * 0.11):int(height * 0.32), 0:int(width * 0.40)]
    if roi.size == 0:
        return 0

    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = (((hsv[:, :, 0] > 45) & (hsv[:, :, 0] < 85) &
             (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 120)).astype("uint8")) * 255
    num_labels, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    count = 0
    for index in range(1, num_labels):
        _, _, component_width, component_height, area = stats[index]
        if component_width >= 20 and component_height >= 4 and area >= 60:
            count += 1
    return count


def _show_wild_march_queue_panel(executor):
    for _ in range(2):
        _, _, visible = _find_templates(
            executor,
            [_march_queue_asset("wild_queue_panel_anchor.png")],
            threshold=0.76,
            region=_region_from_ratio(executor.emulator_executor, 0.0, 0.16, 0.68, 0.32),
        )
        if visible:
            return True

        _click_base(executor, 8, 348, wait_seconds=0.4)
        _click_base(executor, 207, 168, wait_seconds=0.5)

    _, _, visible = _find_templates(
        executor,
        [_march_queue_asset("wild_queue_panel_anchor.png")],
        threshold=0.76,
        region=_region_from_ratio(executor.emulator_executor, 0.0, 0.16, 0.68, 0.32),
    )
    return visible


def _close_march_queue_panel(executor):
    _click_base(executor, 292, 346, wait_seconds=0.3)


def _classify_march_queue_row(row_image):
    icon_region = row_image[6:38, 4:42]
    if _template_matches_image(
            row_image,
            _march_queue_templates("rally_icon.png"),
            threshold=0.72,
    ):
        return "beast"

    if _template_matches_image(
            row_image,
            _march_queue_templates("rally_status_icon.png", "rally_status_text.png", "rally_text.png"),
            threshold=0.84,
    ):
        return "beast"

    if _template_matches_image(
            icon_region,
            _march_queue_templates(
                "gather_meat_icon.png",
                "gather_wood_icon.png",
                "gather_coal_icon.png",
                "gather_iron_icon.png",
                "gather_alliance_meat_icon.png",
                "gather_alliance_wood_icon.png",
                "gather_alliance_coal_icon.png",
                "gather_alliance_iron_icon.png",
            ),
            threshold=0.70,
    ):
        return "gather"

    if _template_matches_image(
            row_image,
            _march_queue_templates("gather_status_text.png"),
            threshold=0.84,
    ):
        return "gather"

    return "unknown"


def _summarize_march_queue_image(image):
    summary = {"total": 0, "gather": 0, "beast": 0, "unknown": 0}
    height, width = image.shape[:2]
    for base_y in MARCH_QUEUE_ROW_BASE_Y:
        y1 = int(height * base_y / BASE_SCREEN_HEIGHT)
        y2 = int(height * (base_y + 44) / BASE_SCREEN_HEIGHT)
        x1 = int(width * 6 / BASE_SCREEN_WIDTH)
        x2 = int(width * 276 / BASE_SCREEN_WIDTH)
        row = image[y1:y2, x1:x2]
        if row.size == 0:
            continue

        hsv = cv2.cvtColor(row, cv2.COLOR_BGR2HSV)
        green_pixels = int(((hsv[:, :, 0] > 45) & (hsv[:, :, 0] < 85) &
                            (hsv[:, :, 1] > 80) & (hsv[:, :, 2] > 100)).sum())
        if green_pixels < 25:
            continue

        queue_type = _classify_march_queue_row(row)
        summary["total"] += 1
        summary[queue_type] += 1
    return summary


def _get_march_queue_summary(executor):
    if not _show_wild_march_queue_panel(executor):
        fallback_count = _get_active_march_count(executor)
        return {"total": fallback_count, "gather": 0, "beast": 0, "unknown": fallback_count}

    image = executor.emulator_executor.screenshot()
    summary = _summarize_march_queue_image(image)
    _close_march_queue_panel(executor)
    return summary


def _should_skip_for_active_limit(executor, limit, label, queue_type=None):
    queue_summary = _get_march_queue_summary(executor)
    active_count = queue_summary["total"]
    summary_detail = (
        f"挖矿={queue_summary.get('gather', 0)}, "
        f"巨兽={queue_summary.get('beast', 0)}, "
        f"未识别={queue_summary.get('unknown', 0)}"
    )

    if queue_type is not None:
        if active_count >= MAX_ACTIVE_MARCHES:
            log_util.log.print(
                f"[{executor.emulator_name}] 当前出征队列 {active_count}/{MAX_ACTIVE_MARCHES} "
                f"已达到游戏行军上限，跳过本轮（{summary_detail}）"
            )
            return True
        typed_count = queue_summary.get(queue_type, 0)
        typed_label = label
        if queue_type == "beast" and queue_summary.get("unknown", 0):
            typed_count += queue_summary["unknown"]
            typed_label = f"{label}(含未识别)"
        if typed_count >= limit:
            log_util.log.print(
                f"[{executor.emulator_name}] 当前{typed_label}队列 {typed_count}/{limit} "
                f"已达到配置数量，跳过本轮（{summary_detail}）"
            )
            return True
        log_util.log.print(
            f"[{executor.emulator_name}] 当前出征队列 {active_count}/{MAX_ACTIVE_MARCHES}，"
            f"{typed_label}队列 {typed_count}/{limit}，继续尝试{label}（{summary_detail}）"
        )
        return False

    shared_limit = executor.state.get("active_march_shared_limit")
    active_limit = int(shared_limit) if shared_limit else limit
    active_limit = max(1, min(active_limit, MAX_ACTIVE_MARCHES))
    limit_label = "共享行军上限" if shared_limit else f"配置{label}数量"

    if active_count >= active_limit:
        log_util.log.print(f"[{executor.emulator_name}] 当前出征队列 {active_count}/{active_limit} 已达到{limit_label}，跳过本轮")
        return True

    log_util.log.print(f"[{executor.emulator_name}] 当前出征队列 {active_count}/{active_limit}，继续尝试{label}")
    return False


def _should_skip_for_active_marches(executor, formation_indices):
    return _should_skip_for_active_limit(executor, len(formation_indices), "巨兽", queue_type="beast")
