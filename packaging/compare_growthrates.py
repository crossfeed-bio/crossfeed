"""Compare grownet's `easylinear` with the reference, R's `growthrates::fit_easylinear`, curve by curve.

The module docstring of `grownet.rates` states how the two agree, with counts. Those counts were taken by
hand twice and went stale twice (342, then a recount on a different selection of curves, found on #286 and
in review), so the comparison that produces them lives here, where anyone can run it again:

    python packaging/compare_growthrates.py SMGDB00000004 SMGDB00000005

It reads the studies from mGrowthDB (through the usual cache) and needs R with `growthrates` installed;
without R it stops with exit code 2 rather than skipping, since a comparison that did not run says nothing.

**The curves it takes:** every measurement context of every bioreplicate that is not an average, in the
studies named, counted by the kind of subject (`strain`, `metabolite`, or whatever else mGrowthDB records).
Each curve falls in exactly one class:

* `both`: both give a rate; they must agree to 1e-12, relative for a rate above 1 and absolute below it,
  and any that does not is a failure;
* `neither`: neither gives a rate;
* `departure 1`: the steepest window rose and grownet's refit came out <= 0, so grownet gives no rate
  where `growthrates` returns the negative number (Karoline, 2026-10-12, on #229 (a));
* `departure 2`: a value <= 0; `growthrates` refuses the curve, grownet drops those points (#229 (b));
* `departure 2+1`: both at once: `growthrates` refuses the curve for a value <= 0, and grownet, having
  dropped those points, finds its refit <= 0 and gives no rate, so neither has a rate;
* `departure 3`: no rising window; `growthrates` fits nothing ("no positively growing segment"), grownet
  returns its steepest slope, which is <= 0;
* `other`: anything else, which is a failure, because it is a departure nobody has named.

Exit code 0 when every curve is in a named class and every `both` agrees, 1 otherwise, 2 when R is missing.
"""
from __future__ import annotations

import csv
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

CLASSES = ("both", "neither", "departure 1", "departure 2", "departure 2+1", "departure 3", "other")
AGREE = 1e-12

R_SCRIPT = r"""
suppressMessages(library(growthrates))
d <- read.csv(commandArgs(trailingOnly = TRUE)[1])
out <- do.call(rbind, lapply(split(d, d$curve), function(s) {
  s <- s[order(s$time), ]
  warned <- ""
  rate <- tryCatch(withCallingHandlers({
      f <- fit_easylinear(s$time, s$y, h = 5, quota = 0.95)
      unname(coef(f)["mumax"])
    }, warning = function(w) { warned <<- conditionMessage(w); invokeRestart("muffleWarning") }),
    error = function(e) { if (warned == "") warned <<- conditionMessage(e); NA })
  data.frame(curve = s$curve[1], rate = rate, message = substr(warned, 1, 80))
}))
write.csv(out, commandArgs(trailingOnly = TRUE)[2], row.names = FALSE)
"""


def classify(grownet_rate, grownet_why: str, r_rate, r_message: str) -> str:
    """The class of one curve, from what each implementation gave."""
    if grownet_rate is not None and r_rate is not None:
        return "both"
    if grownet_rate is None and r_rate is None:
        both_named = "refit" in (grownet_why or "") and "y must be positive" in (r_message or "")
        return "departure 2+1" if both_named else "neither"
    if grownet_rate is None:
        return "departure 1" if "refit" in (grownet_why or "") and r_rate <= 0 else "other"
    if "y must be positive" in (r_message or ""):
        return "departure 2"
    if "no positively growing segment" in (r_message or "") and grownet_rate <= 0:
        return "departure 3"
    return "other"


def curves(client, studies) -> list:
    """(curve id, study, kind, times, values, grownet rate or None, why) for every curve the doc counts."""
    from grownet.rates import RateUnavailable, easylinear_fit
    out = []
    for sid in studies:
        for exp in client.study_experiments(sid):
            for stub in exp.get("bioreplicates") or []:
                rep = client.get_bioreplicate(stub["id"])
                if rep.get("isAverage"):
                    continue
                for ctx in rep.get("measurementContexts") or []:
                    series = client.get_measurement_series(ctx["id"])
                    times, values = [p[0] for p in series], [p[1] for p in series]
                    try:
                        rate, why = easylinear_fit(times, values, 5, 0.95)["rate"], ""
                    except (RateUnavailable, ValueError) as e:
                        rate, why = None, str(e)
                    kind = (ctx.get("subject") or {}).get("type") or ctx.get("subjectType") or "unknown"
                    out.append((ctx["id"], sid, kind, times, values, rate, why))
    return out


def main(studies: list) -> int:
    rscript = shutil.which("Rscript")
    if not rscript:
        print("compare_growthrates: Rscript not found; the comparison needs R with growthrates", file=sys.stderr)
        return 2
    from grownet.mgrowthdb import MGrowthDBClient
    rows = curves(MGrowthDBClient(), studies)
    with tempfile.TemporaryDirectory() as tmp:
        long, script, answer = Path(tmp) / "curves.csv", Path(tmp) / "fit.R", Path(tmp) / "r.csv"
        with long.open("w", newline="") as fh:
            writer = csv.writer(fh)
            writer.writerow(["curve", "time", "y"])
            for cid, _sid, _kind, times, values, _rate, _why in rows:
                writer.writerows((cid, t, y) for t, y in zip(times, values, strict=True))
        script.write_text(R_SCRIPT)
        done = subprocess.run([rscript, str(script), str(long), str(answer)], capture_output=True, text=True)
        if done.returncode != 0:
            print(f"compare_growthrates: R failed: {done.stderr.strip()[-300:]}", file=sys.stderr)
            return 2
        r = {row["curve"]: row for row in csv.DictReader(answer.open())}
    table, differ, others, gaps = Counter(), [], [], []
    for cid, sid, kind, _t, _v, rate, why in rows:
        got = r.get(str(cid)) or {"rate": "NA", "message": "no answer from R"}
        r_rate = None if got["rate"] in ("", "NA") else float(got["rate"])
        cls = classify(rate, why, r_rate, got["message"])
        table[(cls, kind)] += 1
        if cls == "both":
            gaps.append(abs(rate - r_rate))
            if gaps[-1] > AGREE * max(1.0, abs(r_rate)):
                differ.append((cid, rate, r_rate))
        if cls == "other":
            others.append((cid, sid, kind, rate, r_rate, why[:60], got["message"][:60]))
    kinds = sorted({kind for _cls, kind in table})
    print(f"{len(rows)} curves of {', '.join(studies)} (bioreplicates that are not averages)")
    print("class".ljust(14) + "".join(k.rjust(12) for k in kinds) + "total".rjust(8))
    for cls in CLASSES:
        print(cls.ljust(14) + "".join(str(table[(cls, k)]).rjust(12) for k in kinds)
              + str(sum(table[(cls, k)] for k in kinds)).rjust(8))
    print(f"largest difference where both fit: {max(gaps) if gaps else 0:.3g}")
    for item in differ:
        print(f"  DIFFER: {item}")
    for item in others:
        print(f"  UNNAMED: {item}")
    return 1 if differ or others else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or ["SMGDB00000004", "SMGDB00000005"]))
