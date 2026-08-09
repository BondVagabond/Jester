
import argparse, json, os
from .watchdog import run_watchdog, write_reports

def main():
    ap = argparse.ArgumentParser(description="Jester Watchdog CLI")
    ap.add_argument("--in", dest="inputs", nargs="+", required=True, help="One or more JSONL files to analyze")
    ap.add_argument("--out", dest="out", required=True, help="Output prefix (without extension)")
    ap.add_argument("--required-keys", nargs="*", default=["seed","prompt","assistant"], help="Top-level keys required in each record")
    ap.add_argument("--prompt-jaccard", type=float, default=0.9, help="Prompt ngram Jaccard threshold")
    ap.add_argument("--output-jaccard", type=float, default=0.85, help="Output ngram Jaccard threshold")
    ap.add_argument("--sample-cap", type=int, default=300, help="Max records to pairwise compare for similarity checks")
    args = ap.parse_args()

    res = run_watchdog(
        inputs=args.inputs,
        required_keys=args.required_keys,
        jaccard_prompt_thresh=args.prompt_jaccard,
        jaccard_output_thresh=args.output_jaccard,
        sample_cap=args.sample_cap,
    )
    paths = write_reports(args.out, res)
    print(json.dumps(paths))

if __name__ == "__main__":
    main()
