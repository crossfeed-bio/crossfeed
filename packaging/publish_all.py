"""Derive the All network of mGrowthDB with the default settings, for the daily release asset (#96).

Run by .github/workflows/all-network.yml, which uploads the files it writes to the `all-network` release.
Usage: python packaging/publish_all.py OUT_DIR
Writes all_result.json (what the page and `grownet derive --all` read), all_network.json and all_report.txt.
"""
import json
import sys
from pathlib import Path

from grownet.gui import DEFAULTS, run_query
from grownet.mgrowthdb import MGrowthDBClient
from grownet.published import FILE, to_payload
from grownet.report import report_text


def main(out: str) -> int:
    result = run_query(MGrowthDBClient(), [], dict(DEFAULTS), all_studies=True, published=False)
    if result["errors"]:
        print("not published, the derivation had errors:", *result["errors"], sep="\n  ", file=sys.stderr)
        return 1
    folder = Path(out)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / FILE).write_text(json.dumps(to_payload(result)) + "\n", encoding="utf-8")
    (folder / "all_network.json").write_text(result["network"].to_json() + "\n", encoding="utf-8")
    (folder / "all_report.txt").write_text(report_text(result), encoding="utf-8")
    net = result["network"]
    print(f"All: {len(result['studies'])} studies, {len(net.nodes)} nodes, {len(net.edges)} arcs, "
          f"derived at {net.meta['derived_at']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
