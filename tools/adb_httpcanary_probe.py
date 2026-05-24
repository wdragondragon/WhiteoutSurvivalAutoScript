import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime
from pathlib import Path


DEFAULT_ADB = r"E:\leidian\LDPlayer9\adb.exe"
CANARY_CACHE = "/sdcard/Android/data/com.guoshi.httpcanary/cache"
TEXT_BYTES_RE = re.compile(rb"[A-Za-z_][A-Za-z0-9_./:-]{2,40}")
SENSITIVE_RE = re.compile(
    r"(token|authorization|cookie|session|openid|open_id|device_id|android_id|guid|"
    r"passport|mobile|id_card|pi|email|client_id|signature|content-md5|log_id)",
    re.IGNORECASE,
)


def run_adb(adb, device, args, binary=False):
    cmd = [adb]
    if device:
        cmd += ["-s", device]
    cmd += args
    if binary:
        return subprocess.check_output(cmd)
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="ignore")
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"adb command failed: {' '.join(cmd)}")
    return result.stdout


def shell(adb, device, command):
    return run_adb(adb, device, ["shell", command])


def now_tag():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def screencap(adb, device, output_path):
    data = run_adb(adb, device, ["exec-out", "screencap", "-p"], binary=True)
    Path(output_path).write_bytes(data)
    return {"path": str(Path(output_path).resolve()), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def list_canary_files(adb, device):
    out = shell(
        adb,
        device,
        f"find {CANARY_CACHE} -maxdepth 2 -type f \\( -name 'tcp_*.tcpcy' -o -name 'http_req_*.hcy' -o -name 'http_res_*.hcy' \\) -exec ls -l {{}} \\;",
    )
    files = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 8:
            continue
        path = parts[-1]
        try:
            size = int(parts[4])
        except ValueError:
            continue
        files[path] = {
            "size": size,
            "date": " ".join(parts[5:8]),
            "kind": Path(path).suffix.lstrip("."),
            "ip": extract_ip(path),
        }
    return files


def extract_ip(path):
    match = re.search(r"/cache/([^/]+)/", path)
    return match.group(1) if match else ""


def read_range(adb, device, path, offset, count):
    if count <= 0:
        return b""
    # tail -c +N uses 1-based offsets; head limits without creating a local raw dump.
    command = f"tail -c +{offset + 1} '{path}' | head -c {count}"
    return run_adb(adb, device, ["exec-out", "sh", "-c", command], binary=True)


def varint(n):
    out = []
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            break
    return bytes(out)


def value_patterns(label, value, integer_widths):
    result = {
        f"{label}_ascii": str(value).encode("ascii"),
        f"{label}_varint": varint(value),
    }
    if 2 in integer_widths and 0 <= value <= 0xFFFF:
        result[f"{label}_u16_le"] = value.to_bytes(2, "little")
        result[f"{label}_u16_be"] = value.to_bytes(2, "big")
    if 4 in integer_widths and 0 <= value <= 0xFFFFFFFF:
        result[f"{label}_u32_le"] = value.to_bytes(4, "little")
        result[f"{label}_u32_be"] = value.to_bytes(4, "big")
    return result


def build_patterns(target):
    patterns = {}
    if target.get("player_id"):
        patterns.update(value_patterns("player_id", int(target["player_id"]), {4}))
    if target.get("x") is not None:
        patterns.update(value_patterns("x", int(target["x"]), {2, 4}))
    if target.get("y") is not None:
        patterns.update(value_patterns("y", int(target["y"]), {2, 4}))
    return patterns


def find_pattern_hits(data, patterns, max_hits=20):
    hits = {}
    for name, pat in patterns.items():
        positions = []
        start = 0
        while pat:
            idx = data.find(pat, start)
            if idx < 0:
                break
            positions.append(idx)
            start = idx + 1
            if len(positions) >= max_hits:
                break
        if positions:
            hits[name] = {"hex": pat.hex(" "), "positions": positions, "count_at_least": len(positions)}
    return hits


def adjacent_coord_hits(data, x, y, max_hits=20):
    if x is None or y is None:
        return {}
    x_patterns = value_patterns("x", int(x), {2, 4})
    y_patterns = value_patterns("y", int(y), {2, 4})
    result = {}
    for x_name, x_pat in x_patterns.items():
        for y_name, y_pat in y_patterns.items():
            for pair_name, pair_pat in (
                (f"{x_name}+{y_name}", x_pat + y_pat),
                (f"{y_name}+{x_name}", y_pat + x_pat),
            ):
                positions = []
                start = 0
                while pair_pat:
                    idx = data.find(pair_pat, start)
                    if idx < 0:
                        break
                    positions.append(idx)
                    start = idx + 1
                    if len(positions) >= max_hits:
                        break
                if positions:
                    result[pair_name] = {"hex": pair_pat.hex(" "), "positions": positions, "count_at_least": len(positions)}
    return result


def redacted_strings(data, max_items=80):
    counts = {}
    for match in TEXT_BYTES_RE.finditer(data):
        text = match.group(0).decode("utf-8", errors="ignore")
        if not text or SENSITIVE_RE.search(text):
            continue
        if ":" in text and re.search(r":[A-Za-z0-9+/=_-]{12,}", text):
            continue
        if re.fullmatch(r"[0-9a-fA-F]{12,}", text):
            continue
        if re.fullmatch(r"[A-Za-z0-9+/]{20,}={0,2}", text):
            continue
        counts[text] = counts.get(text, 0) + 1
    return [
        {"text": text, "count": count}
        for text, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:max_items]
    ]


def summarize_delta(data, target):
    patterns = build_patterns(target)
    return {
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "pattern_hits": find_pattern_hits(data, patterns),
        "adjacent_coord_hits": adjacent_coord_hits(data, target.get("x"), target.get("y")),
        "redacted_string_counts": redacted_strings(data),
    }


def diff_files(adb, device, before, after, target, max_delta_bytes):
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
        summary = summarize_delta(data, target)
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


def parse_target(spec):
    # label[:player_id[:x[:y[:tap_x[:tap_y]]]]]
    parts = spec.split(":")
    target = {"label": parts[0]}
    keys = ["player_id", "x", "y", "tap_x", "tap_y"]
    for key, value in zip(keys, parts[1:]):
        if value != "":
            target[key] = int(value)
    return target


def sample_target(adb, device, out_dir, target, wait_seconds, max_delta_bytes):
    label = target["label"]
    safe_label = re.sub(r"[^A-Za-z0-9_.-]+", "_", label)
    sample_dir = Path(out_dir) / f"{now_tag()}_{safe_label}"
    ensure_dir(sample_dir)

    before = list_canary_files(adb, device)
    before_screen = screencap(adb, device, sample_dir / "before.png")

    tapped = False
    if target.get("tap_x") is not None and target.get("tap_y") is not None:
        shell(adb, device, f"input tap {target['tap_x']} {target['tap_y']}")
        tapped = True
        time.sleep(wait_seconds)

    detail_screen = screencap(adb, device, sample_dir / "detail.png")
    after = list_canary_files(adb, device)
    deltas = diff_files(adb, device, before, after, target, max_delta_bytes)

    if tapped:
        shell(adb, device, "input keyevent 4")
        time.sleep(1)
        after_back_screen = screencap(adb, device, sample_dir / "after_back.png")
    else:
        after_back_screen = None

    report = {
        "target": target,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "wait_seconds": wait_seconds,
        "screenshots": {
            "before": before_screen,
            "detail": detail_screen,
            "after_back": after_back_screen,
        },
        "deltas": deltas,
    }
    report_path = sample_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path, report


def main():
    parser = argparse.ArgumentParser(description="ADB screenshot + HttpCanary delta probe for local observation.")
    parser.add_argument("--adb", default=os.environ.get("ADB_PATH", DEFAULT_ADB))
    parser.add_argument("--device", default=os.environ.get("ADB_DEVICE", "emulator-5616"))
    parser.add_argument("--out", default="probe_runs")
    parser.add_argument("--wait", type=float, default=4.0)
    parser.add_argument("--max-delta-bytes", type=int, default=262144)
    parser.add_argument("--target", action="append", required=True, help="label[:player_id[:x[:y[:tap_x[:tap_y]]]]]")
    args = parser.parse_args()

    run_dir = Path(args.out) / now_tag()
    ensure_dir(run_dir)
    device_info = {
        "device": args.device,
        "wm_size": shell(args.adb, args.device, "wm size").strip(),
        "focus": shell(args.adb, args.device, "dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp'").strip(),
    }
    (run_dir / "device.json").write_text(json.dumps(device_info, ensure_ascii=False, indent=2), encoding="utf-8")

    reports = []
    for spec in args.target:
        target = parse_target(spec)
        report_path, report = sample_target(args.adb, args.device, run_dir, target, args.wait, args.max_delta_bytes)
        reports.append(
            {
                "label": target["label"],
                "report": str(report_path.resolve()),
                "delta_files": len(report["deltas"]),
                "delta_bytes": sum(item["delta_size"] for item in report["deltas"]),
                "pattern_hit_files": [
                    item["path"]
                    for item in report["deltas"]
                    if item["pattern_hits"] or item["adjacent_coord_hits"]
                ],
            }
        )

    summary = {"run_dir": str(run_dir.resolve()), "reports": reports}
    (run_dir / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
