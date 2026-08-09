
import json, os, logging
from typing import List, Dict, Any, Optional
from .checks import AVAILABLE_CHECKS, CheckResult, check_schema_presence
from .report import render_html

logger = logging.getLogger("jester_watchdog")
handler = logging.FileHandler(os.environ.get("JESTER_WATCHDOG_LOGFILE", "jester_watchdog.log"), encoding="utf-8")
fmt = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
handler.setFormatter(fmt)
if not logger.handlers:
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

def load_jsonl(path: str, limit: Optional[int]=None) -> List[Dict[str,Any]]:
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line: continue
            try:
                out.append(json.loads(line))
            except Exception as e:
                logger.error("Failed to parse JSONL at line %d: %s", i+1, e)
            if limit and len(out) >= limit:
                break
    return out

def run_watchdog(
    inputs: List[str],
    required_keys: Optional[list]=None,
    jaccard_prompt_thresh: float=0.9,
    jaccard_output_thresh: float=0.85,
    sample_cap: int=300
) -> Dict[str,Any]:
    # Load all records from all inputs
    records = []
    for p in inputs:
        if not os.path.exists(p):
            logger.error("Input not found: %s", p)
            continue
        logger.info("Loading %s", p)
        records.extend(load_jsonl(p))
    meta = {"num_records": len(records), "inputs": inputs}
    logger.info("Loaded %d records", len(records))

    results: List[CheckResult] = []

    # Optional schema check
    if required_keys:
        results.append(check_schema_presence(records, required_keys=required_keys))

    # Other checks
    for chk in AVAILABLE_CHECKS:
        if chk.__name__ == "check_schema_presence":
            continue
        # Many checks use default thresholds; expose overrides later if needed
        res = chk(records)
        results.append(res)
        logger.info("Check %s -> %s", res.name, res.level)

    # Aggregate report
    result_dicts = [r.to_dict() for r in results]
    return {"results": result_dicts, "meta": meta}

def write_reports(output_prefix: str, result: Dict[str,Any]) -> Dict[str,str]:
    json_path = f"{output_prefix}.json"
    html_path = f"{output_prefix}.html"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    # Reconstruct CheckResult objects to pass to renderer
    objs = []
    for r in result["results"]:
        cr = CheckResult(r["name"], r["level"], r["message"], r.get("extra", {}), r.get("indices", []))
        objs.append(cr)
    html = render_html(objs, result["meta"])
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    return {"json": json_path, "html": html_path}
