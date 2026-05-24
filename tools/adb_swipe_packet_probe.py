import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from adb_httpcanary_probe import (
    DEFAULT_ADB,
    adjacent_coord_hits,
    ensure_dir,
    list_canary_files,
    read_range,
    redacted_strings,
    run_adb,
    screencap,
    shell,
    value_patterns,
)


FIELD_RE = re.compile(
    rb"(coord|coordinate|pos|position|map|world|player|role|uid|city|castle|"
    rb"mine|resource|gather|tile|target|monster|x_|y_|loc|location|"
    rb"\xe5\x9d\x90\xe6\xa0\x87|\xe7\x9f\xbf|\xe8\xb5\x84\xe6\xba\x90)",
    re.IGNORECASE,
)


def now_tag():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def parse_swipe(spec):
    parts = spec.split(":")
    if len(parts) not in (5, 6):
        raise ValueError("swipe format: label:x1:y1:x2:y2[:duration_ms]")
    label, x1, y1, x2, y2 = parts[:5]
    duration = int(parts[5]) if len(parts) == 6 else 700
    return {
        "label": label,
        "x1": int(x1),
        "y1": int(y1),
        "x2": int(x2),
        "y2": int(y2),
        "duration_ms": duration,
    }


def parse_range(spec):
    parts = [int(part) for part in spec.split(":")]
    if len(parts) != 4:
        raise ValueError("coord range format: min_x:max_x:min_y:max_y")
    min_x, max_x, min_y, max_y = parts
    if min_x > max_x or min_y > max_y:
        raise ValueError("invalid coordinate range")
    return min_x, max_x, min_y, max_y


def pair_hits_in_range(data, coord_range, max_hits=30):
    min_x, max_x, min_y, max_y = coord_range
    hits = []
    encoders = [
        ("u16le", lambda n: n.to_bytes(2, "little")),
        ("u16be", lambda n: n.to_bytes(2, "big")),
        ("u32le", lambda n: n.to_bytes(4, "little")),
        ("u32be", lambda n: n.to_bytes(4, "big")),
        ("ascii_comma", lambda n: str(n).encode("ascii")),
    ]
    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            for enc_name, enc in encoders:
                if enc_name == "ascii_comma":
                    patterns = [
                        (f"{enc_name}:{x},{y}", f"{x},{y}".encode("ascii")),
                        (f"{enc_name}:{x}:{y}", f"{x}:{y}".encode("ascii")),
                        (f"{enc_name}:{x} {y}", f"{x} {y}".encode("ascii")),
                    ]
                else:
                    xp = enc(x)
                    yp = enc(y)
                    patterns = [
                        (f"{enc_name}:x,y:{x},{y}", xp + yp),
                        (f"{enc_name}:y,x:{y},{x}", yp + xp),
                    ]
                for name, pattern in patterns:
                    start = 0
                    while True:
                        idx = data.find(pattern, start)
                        if idx < 0:
                            break
                        hits.append({"pattern": name, "hex": pattern.hex(" "), "position": idx})
                        start = idx + 1
                        if len(hits) >= max_hits:
                            return hits
    return hits


def field_hits(data):
    result = {}
    for match in FIELD_RE.finditer(data):
        key = match.group(0).decode("utf-8", errors="ignore").lower()
        result[key] = result.get(key, 0) + 1
    return [{"text": key, "count": count} for key, count in sorted(result.items(), key=lambda item: (-item[1], item[0]))]


def summarize_delta(data, coord_range):
    known_center = {"x": (coord_range[0] + coord_range[1]) // 2, "y": (coord_range[2] + coord_range[3]) // 2}
    return {
        "bytes": len(data),
        "field_hits": field_hits(data),
        "redacted_string_counts": redacted_strings(data, max_items=60),
        "center_coord_hits": adjacent_coord_hits(data, known_center["x"], known_center["y"]),
        "coord_pair_hits_in_range": pair_hits_in_range(data, coord_range),
    }


def diff_files(adb, device, before, after, coord_range, max_delta_bytes):
    deltas = []
    for path, meta in sorted(after.items()):
        old_size = before.get(path, {}).get("size", 0)
        new_size = meta["size"]
        if new_size <= old_size:
            continue
        delta_size = new_size - old_size
        fetch_size = min(delta_size, max_delta_bytes)
        fetch_offset = new_size - fetch_size
        data = read_range(adb, device, path, fetch_offset, fetch_size)
        summary = summarize_delta(data, coord_range)
        summary.update(
            {
                "path": path,
                "ip": meta.get("ip", ""),
                "kind": meta.get("kind", ""),
                "old_size": old_size,
                "new_size": new_size,
                "delta_size": delta_size,
                "analyzed_offset": fetch_offset,
                "analyzed_bytes": fetch_size,
            }
        )
        deltas.append(summary)
    return deltas


def run_swipe_sample(adb, device, out_dir, swipe, wait_seconds, coord_range, max_delta_bytes):
    sample_dir = Path(out_dir) / f"{now_tag()}_{re.sub(r'[^A-Za-z0-9_.-]+', '_', swipe['label'])}"
    ensure_dir(sample_dir)

    before_files = list_canary_files(adb, device)
    before_screen = screencap(adb, device, sample_dir / "before.png")

    shell(
        adb,
        device,
        f"input swipe {swipe['x1']} {swipe['y1']} {swipe['x2']} {swipe['y2']} {swipe['duration_ms']}",
    )
    time.sleep(wait_seconds)

    after_screen = screencap(adb, device, sample_dir / "after.png")
    after_files = list_canary_files(adb, device)
    deltas = diff_files(adb, device, before_files, after_files, coord_range, max_delta_bytes)

    report = {
        "swipe": swipe,
        "coord_range": {
            "min_x": coord_range[0],
            "max_x": coord_range[1],
            "min_y": coord_range[2],
            "max_y": coord_range[3],
        },
        "wait_seconds": wait_seconds,
        "screenshots": {"before": before_screen, "after": after_screen},
        "deltas": deltas,
    }
    report_path = sample_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path, report


def main():
    parser = argparse.ArgumentParser(description="Swipe map and inspect HttpCanary deltas for coordinate-like evidence.")
    parser.add_argument("--adb", default=os.environ.get("ADB_PATH", DEFAULT_ADB))
    parser.add_argument("--device", default=os.environ.get("ADB_DEVICE", "emulator-5616"))
    parser.add_argument("--out", default="probe_runs")
    parser.add_argument("--wait", type=float, default=4.0)
    parser.add_argument("--max-delta-bytes", type=int, default=262144)
    parser.add_argument("--coord-range", default="560:660:400:500")
    parser.add_argument("--swipe", action="append", required=True, help="label:x1:y1:x2:y2[:duration_ms]")
    args = parser.parse_args()

    run_dir = Path(args.out) / f"{now_tag()}_swipe"
    ensure_dir(run_dir)
    coord_range = parse_range(args.coord_range)
    device_info = {
        "device": args.device,
        "wm_size": shell(args.adb, args.device, "wm size").strip(),
        "focus": shell(args.adb, args.device, "dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp'").strip(),
    }
    (run_dir / "device.json").write_text(json.dumps(device_info, ensure_ascii=False, indent=2), encoding="utf-8")

    reports = []
    for spec in args.swipe:
        swipe = parse_swipe(spec)
        report_path, report = run_swipe_sample(
            args.adb, args.device, run_dir, swipe, args.wait, coord_range, args.max_delta_bytes
        )
        reports.append(
            {
                "label": swipe["label"],
                "report": str(report_path.resolve()),
                "delta_files": len(report["deltas"]),
                "delta_bytes": sum(item["delta_size"] for item in report["deltas"]),
                "files_with_field_hits": [
                    item["path"] for item in report["deltas"] if item["field_hits"]
                ],
                "files_with_coord_pair_hits": [
                    item["path"] for item in report["deltas"] if item["coord_pair_hits_in_range"]
                ],
            }
        )

    summary = {"run_dir": str(run_dir.resolve()), "reports": reports}
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
