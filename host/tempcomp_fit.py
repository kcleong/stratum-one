#!/usr/bin/env python3
"""Fit a chrony tempcomp points file from the api's history (frequency vs CPU temperature).

Bins `frequency_ppm` by `cpu_temp_c` (0.5 °C), takes the median per bin and writes
`temp_mC comp_ppm` lines with comp = -(F(T) - F_ref): a positive comp makes chronyd run
the clock faster, and this crystal runs faster when warmer. F_ref is the bin at the
median temperature, so comp is ~0 at the usual temperature.

With an existing points file the fit is merged: new bins replace old ones, old bins outside
the new data are kept (history.db only holds 30 days), so the table grows across seasons.
The new fit is shifted onto the old table by the median difference of the overlapping bins.
Flat sentinel points at 20 and 80 °C stop chronyd's linear extrapolation outside the data.

Only fit data taken WITHOUT tempcomp active (or before it was enabled, see --since/--until):
with tempcomp on, frequency_ppm no longer shows the crystal's raw temperature dependence.

    python3 host/tempcomp_fit.py --since 2026-10-09T20:30 -o chrony-tempcomp.points
"""

import argparse
import datetime as dt
import json
import statistics
import sys
import urllib.request

BIN_C = 0.5
MIN_SAMPLES = 5
SENTINELS_MC = (20000, 80000)


def load_history(url, minutes):
    with urllib.request.urlopen(f"{url}/api/history?minutes={minutes}", timeout=60) as resp:
        return json.load(resp)


def read_points(path):
    points = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.split("#", 1)[0].split()
                if len(line) == 2:
                    points[int(line[0])] = float(line[1])
    except FileNotFoundError:
        pass
    for s in SENTINELS_MC:
        points.pop(s, None)
    return points


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--minutes", type=int,
                    help="history to fetch (default: back to --since, else 7 days; shorter = finer buckets)")
    ap.add_argument("--since", type=dt.datetime.fromisoformat, help="ignore samples before (local time)")
    ap.add_argument("--until", type=dt.datetime.fromisoformat, help="ignore samples after (local time)")
    ap.add_argument("-o", "--output", default="chrony-tempcomp.points", help="points file, merged if present")
    ap.add_argument("--dry-run", action="store_true", help="print, do not write")
    args = ap.parse_args()

    since = args.since.timestamp() if args.since else 0
    until = args.until.timestamp() if args.until else float("inf")
    minutes = args.minutes or (int((dt.datetime.now().timestamp() - since) / 60) + 10 if since else 10080)
    rows = [r for r in load_history(args.url, minutes)
            if since <= r["t"] <= until and r.get("cpu_temp_c") and r.get("frequency_ppm")]
    if not rows:
        sys.exit("no samples in range")

    bins = {}
    for r in rows:
        bins.setdefault(round(r["cpu_temp_c"] / BIN_C) * BIN_C, []).append(r["frequency_ppm"])
    freq = {round(t * 1000): statistics.median(v) for t, v in bins.items() if len(v) >= MIN_SAMPLES}
    if len(freq) < 2:
        sys.exit("fewer than 2 temperature bins with enough samples")

    t_ref = round(round(statistics.median(r["cpu_temp_c"] for r in rows) / BIN_C) * BIN_C * 1000)
    f_ref = freq.get(t_ref, statistics.median(freq.values()))
    new = {t: -(f - f_ref) for t, f in freq.items()}

    old = read_points(args.output)
    overlap = sorted(set(old) & set(new))
    shift = statistics.median(old[t] - new[t] for t in overlap) if overlap else 0.0
    merged = dict(old)
    merged.update({t: c + shift for t, c in new.items()})

    temps = sorted(merged)
    lo, hi = temps[0], temps[-1]
    span_h = (rows[-1]["t"] - rows[0]["t"]) / 3600
    print(f"{len(rows)} samples over {span_h:.0f} h, temp {min(r['cpu_temp_c'] for r in rows):.1f}"
          f"-{max(r['cpu_temp_c'] for r in rows):.1f} °C; {len(new)} new bins, {len(old)} old,"
          f" {len(overlap)} overlapping (shift {shift:+.3f} ppm)", file=sys.stderr)
    outside = sum(1 for r in rows if not lo / 1000 - BIN_C <= r["cpu_temp_c"] <= hi / 1000 + BIN_C)
    if outside:
        print(f"warning: {outside} samples outside the table's {lo / 1000:.1f}-{hi / 1000:.1f} °C",
              file=sys.stderr)

    # chronyd reads every line as two numbers: no comments in this file.
    lines = [f"{SENTINELS_MC[0]} {merged[lo]:.4f}"]
    lines += [f"{t} {merged[t]:.4f}" for t in temps]
    lines.append(f"{SENTINELS_MC[1]} {merged[hi]:.4f}")
    text = "\n".join(lines) + "\n"
    if args.dry_run:
        print(text, end="")
    else:
        with open(args.output, "w") as f:
            f.write(text)
        print(f"wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
