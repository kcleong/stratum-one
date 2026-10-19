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

Since TEMPCOMP_SINCE, frequency_ppm is already compensated. Those samples are skipped unless
--comp-log gives chronyd's tempcomp.log, from which the raw frequency is rebuilt as
frequency_ppm + COMP_SIGN * comp. COMP_SIGN is unset until --check-sign has shown which sign
reproduces the existing table; host/tempcomp_refit.sh wraps the whole refit.

    python3 host/tempcomp_fit.py --since 2026-10-09T20:30 --dry-run
    python3 host/tempcomp_fit.py --comp-log tempcomp.log --check-sign
"""

import argparse
import bisect
import datetime as dt
import json
import statistics
import sys
import urllib.request

BIN_C = 0.5
MIN_SAMPLES = 5
SENTINELS_MC = (20000, 80000)
TEMPCOMP_SINCE = dt.datetime(2026, 10, 17, 16, 51).timestamp()   # local time, chrony restart
COMP_SIGN = -1     # from --check-sign 2026-10-19: rms diff -1 0.105, +1 0.260 ppm (4 bins only)


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


def read_comp_log(path):
    """tempcomp.log lines: date time(UTC) temp comp; header lines are skipped."""
    times, comps = [], []
    with open(path) as f:
        for line in f:
            parts = line.split()
            if len(parts) != 4 or not parts[0][:1].isdigit():
                continue
            t = dt.datetime.fromisoformat(f"{parts[0]}T{parts[1]}+00:00").timestamp()
            times.append(t)
            comps.append(float(parts[3]))
    return times, comps


def add_comp(rows, log, sign):
    """Raw frequency for compensated rows: mean comp over each history bucket."""
    times, comps = log
    width = statistics.median(b["t"] - a["t"] for a, b in zip(rows, rows[1:])) if len(rows) > 1 else 300
    width = max(width, 60)   # the log has one line per 30 s; 5 s raw samples would mostly miss it
    out = []
    for r in rows:
        if r["t"] < TEMPCOMP_SINCE:
            out.append(r)
            continue
        i, j = bisect.bisect_left(times, r["t"]), bisect.bisect_left(times, r["t"] + width)
        if i == j:
            continue   # no log coverage (restart, truncated log)
        out.append(dict(r, frequency_ppm=r["frequency_ppm"] + sign * statistics.fmean(comps[i:j])))
    return out


def fit(rows):
    bins = {}
    for r in rows:
        bins.setdefault(round(r["cpu_temp_c"] / BIN_C) * BIN_C, []).append(r["frequency_ppm"])
    freq = {round(t * 1000): statistics.median(v) for t, v in bins.items() if len(v) >= MIN_SAMPLES}
    if len(freq) < 2:
        return None
    t_ref = round(round(statistics.median(r["cpu_temp_c"] for r in rows) / BIN_C) * BIN_C * 1000)
    f_ref = freq.get(t_ref, statistics.median(freq.values()))
    return {t: -(f - f_ref) for t, f in freq.items()}


def overlap_shift(old, new):
    overlap = sorted(set(old) & set(new))
    shift = statistics.median(old[t] - new[t] for t in overlap) if overlap else 0.0
    return overlap, shift


def check_sign(rows, log, old):
    """Fit compensated data with sign 0 (as is), +1 and -1; the right sign matches the old table."""
    rows = [r for r in rows if r["t"] >= TEMPCOMP_SINCE]
    for sign in (0, 1, -1):
        new = fit(add_comp(rows, log, sign) if sign else rows)
        if not new:
            sys.exit("not enough compensated data yet")
        overlap, shift = overlap_shift(old, new)
        rms = (statistics.fmean((old[t] - new[t] - shift) ** 2 for t in overlap) ** 0.5
               if overlap else float("nan"))
        spread = max(new.values()) - min(new.values())
        label = {0: "as is (no rebuild)", 1: "COMP_SIGN = +1", -1: "COMP_SIGN = -1"}[sign]
        print(f"{label:20} {len(overlap)} bins vs table: rms diff {rms:.3f} ppm, fitted spread {spread:.3f} ppm")
    print("Sign 0 spread should be small (tempcomp works); the sign with the lowest rms diff "
          "reproduces the table -> set COMP_SIGN to it.")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--minutes", type=int,
                    help="history to fetch (default: back to --since, else 7 days; shorter = finer buckets)")
    ap.add_argument("--since", type=dt.datetime.fromisoformat, help="ignore samples before (local time)")
    ap.add_argument("--until", type=dt.datetime.fromisoformat, help="ignore samples after (local time)")
    ap.add_argument("-o", "--output", default="chrony-tempcomp.points", help="points file, merged if present")
    ap.add_argument("--comp-log", help="chronyd's tempcomp.log: rebuild raw frequency after TEMPCOMP_SINCE")
    ap.add_argument("--check-sign", action="store_true", help="find COMP_SIGN (needs --comp-log)")
    ap.add_argument("--dry-run", action="store_true", help="print, do not write")
    args = ap.parse_args()

    since = args.since.timestamp() if args.since else 0
    until = args.until.timestamp() if args.until else float("inf")
    minutes = args.minutes or (int((dt.datetime.now().timestamp() - since) / 60) + 10 if since else 10080)
    rows = [r for r in load_history(args.url, minutes)
            if since <= r["t"] <= until and r.get("cpu_temp_c") and r.get("frequency_ppm")]
    old = read_points(args.output)

    if args.check_sign:
        if not args.comp_log:
            sys.exit("--check-sign needs --comp-log")
        check_sign(rows, read_comp_log(args.comp_log), old)
        return
    if args.comp_log:
        if COMP_SIGN is None:
            sys.exit("COMP_SIGN is not set yet: run --check-sign and set it in this script")
        rows = add_comp(rows, read_comp_log(args.comp_log), COMP_SIGN)
    else:
        skipped = sum(1 for r in rows if r["t"] >= TEMPCOMP_SINCE)
        rows = [r for r in rows if r["t"] < TEMPCOMP_SINCE]
        if skipped:
            print(f"skipped {skipped} compensated samples (no --comp-log)", file=sys.stderr)
    if not rows:
        sys.exit("no samples in range")

    new = fit(rows)
    if not new:
        sys.exit("fewer than 2 temperature bins with enough samples")
    overlap, shift = overlap_shift(old, new)
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
