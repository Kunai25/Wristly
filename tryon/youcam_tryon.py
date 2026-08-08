"""
YouCam (Perfect Corp) Watch Virtual Try-On — Wristly demo script
==================================================================

WHY THIS RUNS ON YOUR MACHINE, NOT MINE:
My sandbox's network can't reach yce-api-01.makeupar.com. Same deal
as arduino-cli/Wokwi — I write it, you run it.

WHAT'S CONFIRMED vs. WHAT'S AN EDUCATED GUESS
-----------------------------------------------
Confirmed (from your notes + Perfect Corp's public docs for the
sibling Shoes / Beard-style / Face-swap APIs, which share this exact
V2.0 pattern):
  - Base URL: https://yce-api-01.makeupar.com
  - Auth: `Authorization: Bearer YOUR_API_KEY` header
  - Flow: POST /s2s/v2.0/file/<category> to register a file
          -> response gives a file_id + a presigned upload URL
          -> PUT the raw image bytes to that URL
          -> POST /s2s/v2.0/task/<category> with the file_id(s) to
             start the AI task -> response gives a task_id
          -> GET /s2s/v2.0/task/<category>/<task_id> repeatedly
             until status is "success" or "error"

NOT confirmed — I could not load Perfect Corp's Watch-specific
reference page (it's JS-rendered and needs your logged-in console
session). These are educated guesses based on the identical Shoes
API, which uses `src_file_id`/`src_file_url` for the user photo and
`ref_file_id`/`ref_file_url` for the product photo:
  - CATEGORY = "watch"            (could be "watch-try-on" or similar)
  - The exact JSON field names in the /task/watch body

BEFORE SPENDING REAL API UNITS:
Open https://docs.perfectcorp.com/develop/api_playground (or use the
"Ask AI" button on docs.perfectcorp.com) and confirm the CATEGORY
string and the task body field names below. Everything else in this
script should work as-is once those two things are right.
"""

import os
import sys
import time
import json
import mimetypes
import requests

# ── CONFIG ──────────────────────────────────────────────────────────
API_KEY = os.environ.get("YOUCAM_API_KEY", "PASTE_YOUR_API_KEY_HERE")
BASE_URL = "https://yce-api-01.makeupar.com"

# UNCONFIRMED — verify this against the Watch endpoint docs/playground
CATEGORY = "watch"

# Paths to your two local images
WRIST_PHOTO_PATH = "wrist_photo.jpg"      # back of wrist, all 5 fingers, unobstructed
PRODUCT_PHOTO_PATH = "wristly_render.jpg"  # the clean isolated product render

POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 120
OUTPUT_PATH = "wristly_tryon_result.jpg"


# ── STEP 1: register a file, get file_id + upload URL ───────────────
def register_file(path: str) -> tuple[str, str]:
    """POST /s2s/v2.0/file/<category> -> (file_id, upload_url)"""
    content_type, _ = mimetypes.guess_type(path)
    content_type = content_type or "image/jpeg"
    file_size = os.path.getsize(path)
    file_name = os.path.basename(path)

    url = f"{BASE_URL}/s2s/v2.0/file/{CATEGORY}"
    body = {
        "files": [
            {
                "content_type": content_type,
                "file_name": file_name,
                "file_size": file_size,
            }
        ]
    }
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"[register_file] {file_name} -> {json.dumps(data)[:300]}")

    # UNCONFIRMED response shape — adjust the two lines below once you
    # see the real response. Perfect Corp's other file APIs return
    # something like: {"result": {"files": [{"file_id": "...", "url": "..."}]}}
    file_entry = data["result"]["files"][0]
    file_id = file_entry["file_id"]
    upload_url = file_entry["url"]
    return file_id, upload_url


# ── STEP 2: upload the raw bytes to the presigned URL ────────────────
def upload_file(upload_url: str, path: str) -> None:
    with open(path, "rb") as f:
        resp = requests.put(upload_url, data=f, timeout=60)
    resp.raise_for_status()
    print(f"[upload_file] uploaded {path} -> status {resp.status_code}")


# ── STEP 3: create the AI task ───────────────────────────────────────
def create_task(src_file_id: str, ref_file_id: str) -> str:
    """POST /s2s/v2.0/task/<category> -> task_id

    UNCONFIRMED body shape. Modeled on the Shoes API, which uses:
      { "src_file_id": "...", "ref_file_id": "..." }
    (src = the person/wrist photo, ref = the product photo)
    Some sibling APIs (face-swap) instead use a nested
    "payload": {"file_sets": {"src_ids": [...], "ref_ids": [...]}}
    shape — if the flat version below 404s or 400s, try that shape.
    """
    url = f"{BASE_URL}/s2s/v2.0/task/{CATEGORY}"
    body = {
        "src_file_id": src_file_id,
        "ref_file_id": ref_file_id,
    }
    resp = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    print(f"[create_task] -> {json.dumps(data)[:300]}")

    # UNCONFIRMED — adjust once you see the real response shape
    task_id = data["data"]["task_id"]
    return task_id


# ── STEP 4: poll until done ──────────────────────────────────────────
def poll_task(task_id: str) -> dict:
    url = f"{BASE_URL}/s2s/v2.0/task/{CATEGORY}/{task_id}"
    headers = {"Authorization": f"Bearer {API_KEY}"}

    waited = 0
    while waited < POLL_TIMEOUT_SECONDS:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("data", {}).get("status") or data.get("status")
        print(f"[poll_task] status={status} ({waited}s elapsed)")

        if status == "success":
            return data
        if status == "error":
            raise RuntimeError(f"Task failed: {json.dumps(data)}")

        time.sleep(POLL_INTERVAL_SECONDS)
        waited += POLL_INTERVAL_SECONDS

    raise TimeoutError(f"Task {task_id} did not finish within {POLL_TIMEOUT_SECONDS}s")


# ── STEP 5: download the result image ────────────────────────────────
def download_result(result_data: dict, out_path: str) -> None:
    # UNCONFIRMED field name for the result URL — commonly
    # data["data"]["result_url"] or a list under "results"
    result_url = (
        result_data.get("data", {}).get("result_url")
        or result_data.get("data", {}).get("results", [{}])[0].get("url")
    )
    if not result_url:
        print("Could not find a result URL automatically. Full response:")
        print(json.dumps(result_data, indent=2))
        return

    resp = requests.get(result_url, timeout=60)
    resp.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(resp.content)
    print(f"Saved result image to {out_path}")


def main():
    if API_KEY == "PASTE_YOUR_API_KEY_HERE":
        print("Set YOUCAM_API_KEY as an environment variable, or edit API_KEY above.")
        sys.exit(1)

    for p in (WRIST_PHOTO_PATH, PRODUCT_PHOTO_PATH):
        if not os.path.exists(p):
            print(f"Missing file: {p} — update the path constants at the top of this script.")
            sys.exit(1)

    print("Registering wrist photo...")
    src_file_id, src_upload_url = register_file(WRIST_PHOTO_PATH)
    upload_file(src_upload_url, WRIST_PHOTO_PATH)

    print("Registering product photo...")
    ref_file_id, ref_upload_url = register_file(PRODUCT_PHOTO_PATH)
    upload_file(ref_upload_url, PRODUCT_PHOTO_PATH)

    print("Creating try-on task...")
    task_id = create_task(src_file_id, ref_file_id)

    print("Polling for result...")
    result_data = poll_task(task_id)

    download_result(result_data, OUTPUT_PATH)


if __name__ == "__main__":
    main()
