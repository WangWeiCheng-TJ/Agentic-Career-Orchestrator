import os
import glob
import json
import sys
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

from dotenv import load_dotenv
from termcolor import colored, cprint
import google.generativeai as genai
from tqdm import tqdm

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from src.agents.triage import TriageAgent

# === CONFIG ===
load_dotenv()
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = os.getenv("MODEL_NAME", "gemini-1.5-flash")

DIR_DOSSIERS = "/app/data/processed/dossiers"
DIR_PENDING  = "/app/data/processed/pending_council"
DIR_TRASH    = "/app/data/processed/trash"
PATH_PROFILE = "/app/data/personal/profile.md"

MAX_WORKERS  = 3
MAX_WORKERS = os.getenv("MAX_WORKERS", 5)
FORCE_UPDATE = os.getenv("FORCE_UPDATE", "false").lower() == "true"
TEST_LIMIT = None

os.makedirs(DIR_PENDING, exist_ok=True)
os.makedirs(DIR_TRASH,   exist_ok=True)

AGGRESSIVE_INSTRUCTION = (
    "\n\n[SYSTEM ERROR]: Your previous JSON output was REJECTED."
    "\nReason: The experts gave lazy one-word explanations."
    "\nCorrection: You MUST rewrite the 'note' field for ALL experts."
    "\nRule: The 'note' must be a COMPLETE SENTENCE (at least 15 words) explaining the score."
    "\nExample: Instead of 'Helpful', write 'Candidate\\'s C++ experience aligns well with the latency requirements.'"
)


def parse_args():
    parser = argparse.ArgumentParser(description="Phase 2 Triage Agent")
    parser.add_argument("--input-dir",    default=DIR_DOSSIERS, help="Directory containing dossier JSON files")
    parser.add_argument("--pending-dir",  default=DIR_PENDING,  help="Directory for PASS dossiers")
    parser.add_argument("--trash-dir",    default=DIR_TRASH,    help="Directory for FAIL dossiers")
    parser.add_argument("--test-limit", type=int, default=TEST_LIMIT, help="Only process first N dossiers")
    parser.add_argument("--max-workers",  type=int, default=MAX_WORKERS, help="Number of parallel workers")
    parser.add_argument("--force-update", action="store_true", default=FORCE_UPDATE, help="Re-run even if already processed")
    return parser.parse_args()


def load_profile() -> str:
    if not os.path.exists(PATH_PROFILE):
        cprint(f"❌ Profile not found at {PATH_PROFILE}. Please create it before running Phase 2.", "red")
        sys.exit(1)
    with open(PATH_PROFILE, 'r', encoding='utf-8') as f:
        return f.read()


def already_processed(filename: str, pending_dir: str, trash_dir: str) -> bool:
    return (
        os.path.exists(os.path.join(pending_dir, filename)) or
        os.path.exists(os.path.join(trash_dir,   filename))
    )


def triage_worker(filepath: str, user_profile_text: str, pending_dir: str, trash_dir: str, force_update: bool) -> dict:
    filename = os.path.basename(filepath)

    if already_processed(filename, pending_dir, trash_dir) and not force_update:
        return {"status": "skipped", "filename": filename}

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            dossier = json.load(f)

        role    = dossier.get('basic_info', {}).get('role',    'Unknown')
        company = dossier.get('basic_info', {}).get('company', 'Unknown')

        # worker 內自己初始化，避免 shared state 問題
        model = genai.GenerativeModel(MODEL_NAME)
        agent = TriageAgent(model)

        result   = agent.evaluate(dossier, user_profile_text)
        decision = result.get('decision', 'PASS').upper()
        reason   = result.get('reason', 'No reason provided')
        referral = result.get('referral_analysis', {})

        # 補強短 note
        if decision == "PASS" and len(referral.get("E1", {}).get('note', '')) < 20:
            rerun    = agent.evaluate(dossier, user_profile_text, AGGRESSIVE_INSTRUCTION)
            referral = rerun.get('referral_analysis', {})
            result   = rerun
            tqdm.write(colored(f"  🔄 Regenerated referral for: {filename}", "magenta"))

        dossier['triage_result'] = result

        target_dir = pending_dir if decision == "PASS" else trash_dir
        target_path = os.path.join(target_dir, filename)
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(dossier, f, indent=2, ensure_ascii=False)

        return {
            "status":   "pass" if decision == "PASS" else "fail",
            "filename": filename,
            "company":  company,
            "role":     role,
            "reason":   reason,
            "referral": referral,
        }

    except Exception as e:
        return {"status": "error", "filename": filename, "error": str(e)}


def run_triage(args):
    force_msg = " [FORCE_UPDATE]" if args.force_update else ""
    cprint(f"\n🚑 [Phase 2] FULL RECONNAISSANCE TRIAGE{force_msg}", "cyan", attrs=['bold', 'reverse'])

    if not API_KEY:
        cprint("❌ API Key missing.", "red")
        sys.exit(1)

    genai.configure(api_key=API_KEY)

    user_profile_text = load_profile()
    cprint(f"✅ Profile loaded from {PATH_PROFILE}", "green")

    files = sorted(glob.glob(os.path.join(args.input_dir, "*_dossier.json")))
    if not files:
        cprint(f"😴 No dossiers found in {args.input_dir}.", "yellow")
        return

    if args.force_update:
        candidate_files = files
    else:
        candidate_files = [
            fp for fp in files
            if not already_processed(os.path.basename(fp), args.pending_dir, args.trash_dir)
        ]

    target_files = candidate_files[:args.test_limit] if args.test_limit else candidate_files

    cprint(f"📂 Found {len(files)} dossiers. Pending {len(candidate_files)}. Processing {len(target_files)}...", "white")
    print("-" * 40)

    if not target_files:
        cprint("✅ Nothing to do. All dossiers already triaged.", "green")
        return

    stats = {"pass": 0, "fail": 0, "skipped": 0, "error": 0}

    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        futures = {
            executor.submit(
                triage_worker,
                fp,
                user_profile_text,
                args.pending_dir,
                args.trash_dir,
                args.force_update
            ): fp
            for fp in target_files
        }

        pbar = tqdm(as_completed(futures), total=len(futures), desc="🩺 Triaging", unit="job")
        for future in pbar:
            result = future.result()
            status = result["status"]
            stats[status] = stats.get(status, 0) + 1
            pbar.set_postfix(**{k: v for k, v in stats.items() if v > 0})

            if status == "skipped":
                tqdm.write(colored(f"⏭️  SKIP: {result['filename']}", "blue"))

            elif status == "error":
                tqdm.write(colored(f"⚠️  ERROR [{result['filename']}]: {result['error']}", "red"))

            elif status == "pass":
                tqdm.write(colored(f"\n✅ PASS: {result['company']} - {result['role']}", "green", attrs=['bold']))
                referral = result.get("referral", {})
                for i in range(1, 9):
                    eid   = f"E{i}"
                    data  = referral.get(eid, {})
                    score = data.get('relevance', 0)
                    note  = data.get('note', 'N/A')
                    color = "cyan" if score >= 7 else "dark_grey"
                    icon  = "🔥" if score >= 7 else "▫️"
                    tqdm.write(colored(f"  {icon} [{eid}] Rel: {score}/10 | {note}", color))

            elif status == "fail":
                tqdm.write(colored(f"🗑️  FAIL: {result['company']} - {result['role']}", "red"))
                tqdm.write(colored(f"   Reason: {result['reason']}", "dark_grey"))

    cprint("\n🎉 Phase 2 Complete.", "magenta", attrs=['bold'])
    cprint(f"  ✅ Pending Council : {stats.get('pass',    0)}", "green")
    cprint(f"  🗑️  Trashed         : {stats.get('fail',    0)}", "red")
    cprint(f"  ⏭️  Skipped         : {stats.get('skipped', 0)}", "blue")
    cprint(f"  ⚠️  Errors          : {stats.get('error',   0)}", "yellow")


if __name__ == "__main__":
    args = parse_args()
    cprint(args.test_limit)
    run_triage(args)