import os
import sys
import time
import json
import mimetypes
import requests

API_KEY = os.environ.get("YOUCAM_API_KEY")

BASE_URL = "https://yce-api-01.makeupar.com"

WRIST_PHOTO_PATH = "tryon/wrist_photo.png"
PRODUCT_PHOTO_PATH = "tryon/wristly_render.png"

POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 120

OUTPUT_PATH = "tryon/wristly_tryon_result.jpg"


def register_file(path: str) -> tuple[str, str, dict]:
    """Register a local image and return (file_id, upload_url)."""

    content_type, _ = mimetypes.guess_type(path)
    content_type = content_type or "image/png"

    file_size = os.path.getsize(path)
    file_name = os.path.basename(path)

    url = f"{BASE_URL}/s2s/v2.0/file/2d-vto/bracelet"

    body = {
        "files": [
            {
                "content_type": content_type,
                "file_name": file_name,
                "file_size": file_size,
            }
        ]
    }

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=30,
    )

    if not response.ok:
        print("File registration failed:")
        print(response.text)
        response.raise_for_status()

    data = response.json()

    print("[register_file]")
    print(json.dumps(data, indent=2)[:2000])

    # Perfect Corp V2 file APIs return the registered file
    # and its presigned upload URL.
    files = data["data"]["files"]
    file_entry = files[0]

    file_id = file_entry["file_id"]

    upload_request = file_entry["requests"][0]
    upload_url = upload_request["url"]
    upload_headers = upload_request["headers"]

    return file_id, upload_url, upload_headers

    return file_id, upload_url


def upload_file(
    upload_url: str,
    upload_headers: dict,
    path: str,
) -> None:
    with open(path, "rb") as file:
        response = requests.put(
            upload_url,
            headers=upload_headers,
            data=file,
            timeout=60,
        )

    if not response.ok:
        print("File upload failed:")
        print(response.text)
        response.raise_for_status()

    print(f"Uploaded: {path}")

    if not response.ok:
        print("File upload failed:")
        print(response.text)
        response.raise_for_status()

    print(f"Uploaded: {path}")


def create_task(src_file_id: str, ref_file_id: str) -> str:
    """Create the YouCam Bracelet Virtual Try-On task."""

    url = f"{BASE_URL}/s2s/v2.0/task/2d-vto/bracelet"

    body = {
        "src_file_id": src_file_id,
        "source_info": {
            "name": src_file_id
        },
        "ref_file_urls": [],
        "ref_file_ids": [
            ref_file_id
        ],
        "refmsk_file_urls": [],
        "refmsk_file_ids": [],
        "object_infos": [
            {
                "name": ref_file_id,
                "parameter": {
                    "bracelet_need_remove_background": False,
                    "bracelet_wearing_location": 0,
                    "bracelet_shadow_intensity": 0.3,
                    "bracelet_ambient_light_intensity": 1
                }
            }
        ]
    }

    print("[create_task] Request:")
    print(json.dumps(body, indent=2))

    response = requests.post(
        url,
        headers={
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json",
        },
        json=body,
        timeout=30,
    )

    if not response.ok:
        print("Task creation failed:")
        print(response.text)
        response.raise_for_status()

    data = response.json()

    print("[create_task] Response:")
    print(json.dumps(data, indent=2))

    task_id = data["data"]["task_id"]

    print(f"Task ID: {task_id}")

    return task_id


def poll_task(task_id: str) -> dict:
    """Poll until the Bracelet VTO task succeeds or fails."""

    url = f"{BASE_URL}/s2s/v2.0/task/2d-vto/bracelet/{task_id}"

    headers = {
        "Authorization": f"Bearer {API_KEY}"
    }

    waited = 0

    while waited < POLL_TIMEOUT_SECONDS:

        response = requests.get(
            url,
            headers=headers,
            timeout=30,
        )

        if not response.ok:
            print("Task polling failed:")
            print(response.text)
            response.raise_for_status()

        data = response.json()

        print(
            f"[poll_task] {waited}s:"
        )
        print(json.dumps(data, indent=2)[:2000])

        task_data = data.get("data", {})

        status = (
            task_data.get("task_status")
            or task_data.get("status")
            or data.get("task_status")
            or data.get("status")
        )

        if status == "success":
            return data

        if status == "error":
            raise RuntimeError(
                "YouCam task failed:\n"
                + json.dumps(data, indent=2)
            )

        time.sleep(POLL_INTERVAL_SECONDS)
        waited += POLL_INTERVAL_SECONDS

    raise TimeoutError(
        f"Task {task_id} did not finish within "
        f"{POLL_TIMEOUT_SECONDS} seconds."
    )


def find_result_url(data: dict) -> str | None:
    """Try the common result URL locations returned by VTO APIs."""

    task_data = data.get("data", {})

    candidates = [
        task_data.get("result_url"),
        task_data.get("image_url"),
        data.get("result_url"),
        data.get("image_url"),
    ]

    results = task_data.get("results")

    if isinstance(results, list):
        for result in results:
            if isinstance(result, dict):
                candidates.extend(
                    [
                        result.get("url"),
                        result.get("result_url"),
                        result.get("image_url"),
                    ]
                )

    for url in candidates:
        if isinstance(url, str) and url.startswith("http"):
            return url

    return None


def download_result(result_data: dict, out_path: str) -> None:
    """Download the generated YouCam result image."""

    result_url = (
        result_data
        .get("data", {})
        .get("results", {})
        .get("url")
    )

    if not result_url:
        print("Could not find a result image URL.")
        print("Full response:")
        print(json.dumps(result_data, indent=2))
        return

    print("Downloading result image...")

    response = requests.get(result_url, timeout=60)
    response.raise_for_status()

    with open(out_path, "wb") as f:
        f.write(response.content)

    print(f"Saved result image to: {out_path}")


def main() -> None:

    if not API_KEY:
        print("YOUCAM_API_KEY is not set.")
        print()
        print('Run:')
        print('$env:YOUCAM_API_KEY = "YOUR_KEY"')
        sys.exit(1)

    for path in (
        WRIST_PHOTO_PATH,
        PRODUCT_PHOTO_PATH,
    ):
        if not os.path.exists(path):
            print(f"Missing file: {path}")
            sys.exit(1)

    src_file_id, src_upload_url, src_upload_headers = register_file(
        WRIST_PHOTO_PATH
    )

    upload_file(
    src_upload_url,
    src_upload_headers,
        WRIST_PHOTO_PATH,
    )

    print()
    print("Registering Wristly product image...")
    ref_file_id, ref_upload_url, ref_upload_headers = register_file(
        PRODUCT_PHOTO_PATH
    )

    upload_file(
        ref_upload_url,
        ref_upload_headers,
        PRODUCT_PHOTO_PATH,
        )

    print()
    print("Creating Bracelet Virtual Try-On task...")

    task_id = create_task(
        src_file_id,
        ref_file_id,
    )

    print(f"Task ID: {task_id}")
    print()
    print("Processing...")

    result = poll_task(task_id)

    download_result(result, OUTPUT_PATH)


if __name__ == "__main__":
    main()