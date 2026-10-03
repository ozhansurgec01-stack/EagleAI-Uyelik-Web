#!/usr/bin/env python3

import argparse
import base64
import json
import os
import socket
import time
import urllib.error
import urllib.request


FAABLE_API_URL = os.environ.get(
    "EAGLE_SMS_API_URL",
    "https://eagleai-uyelik-web-0hglr.faable.link",
).rstrip("/")

WORKER_TOKEN = os.environ.get("SMS_WORKER_TOKEN", "").strip()

SMSGATE_URL = os.environ.get("SMSGATE_URL", "").strip().rstrip("/")
SMSGATE_USER = os.environ.get("SMSGATE_USER", "sms").strip()
SMSGATE_PASSWORD = os.environ.get("SMSGATE_PASSWORD", "")

POLL_SECONDS = float(os.environ.get("SMS_WORKER_POLL_SECONDS", "3"))
HTTP_TIMEOUT = float(os.environ.get("SMS_WORKER_HTTP_TIMEOUT", "15"))


def local_gateway_url():
    if SMSGATE_URL:
        return SMSGATE_URL

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        sock.connect(("8.8.8.8", 80))
        local_ip = sock.getsockname()[0]
    finally:
        sock.close()

    return f"http://{local_ip}:8080"


def http_json(url, method="GET", body=None, headers=None):
    request_headers = dict(headers or {})

    data = None

    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")

    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT) as response:
            raw = response.read().decode("utf-8", errors="replace")

            if not raw:
                return response.status, {}

            return response.status, json.loads(raw)

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"raw": raw}

        raise RuntimeError(
            f"HTTP {exc.code} {url}: {payload}"
        ) from exc


def worker_headers():
    if not WORKER_TOKEN:
        raise RuntimeError("SMS_WORKER_TOKEN tanımlı değil.")

    return {
        "Authorization": f"Bearer {WORKER_TOKEN}",
    }


def next_job():
    status, data = http_json(
        f"{FAABLE_API_URL}/api/sms/worker/next",
        headers=worker_headers(),
    )

    if status != 200 or not data.get("ok"):
        raise RuntimeError(f"Faable job alma hatası: {data}")

    return data.get("job")


def report_result(job_id, status, error=None):
    body = {
        "job_id": job_id,
        "status": status,
    }

    if error:
        body["error"] = str(error)[:1000]

    http_json(
        f"{FAABLE_API_URL}/api/sms/worker/result",
        method="POST",
        body=body,
        headers=worker_headers(),
    )


def send_to_gateway(job):
    gateway_url = local_gateway_url()

    if not SMSGATE_PASSWORD:
        raise RuntimeError("SMSGATE_PASSWORD tanımlı değil.")

    credentials = f"{SMSGATE_USER}:{SMSGATE_PASSWORD}".encode("utf-8")
    basic_auth = base64.b64encode(credentials).decode("ascii")

    body = {
        "phoneNumbers": [job["phone"]],
        "textMessage": {
            "text": job["message"],
        },
    }

    status, data = http_json(
        f"{gateway_url}/messages",
        method="POST",
        body=body,
        headers={
            "Authorization": f"Basic {basic_auth}",
        },
    )

    if status < 200 or status >= 300:
        raise RuntimeError(
            f"SMS Gateway HTTP {status}: {data}"
        )

    return gateway_url, data


def process_once():
    job = next_job()

    if not job:
        print("Kuyruk boş.")
        return False

    job_id = job.get("id")

    if not job_id:
        raise RuntimeError(f"Geçersiz job: {job}")

    print(
        f"Job #{job_id} alındı: "
        f"uye_id={job.get('uye_id')} "
        f"telefon={job.get('phone')}"
    )

    try:
        gateway_url, response = send_to_gateway(job)

        report_result(job_id, "sent")

        print(
            f"Job #{job_id} gönderildi. "
            f"Gateway={gateway_url} "
            f"Response={response}"
        )

        return True

    except Exception as exc:
        error = str(exc)

        print(
            f"Job #{job_id} GÖNDERİLEMEDİ: {error}"
        )

        try:
            report_result(job_id, "failed", error)
            print(f"Job #{job_id} failed olarak bildirildi.")
        except Exception as report_exc:
            print(
                f"Job #{job_id} sonucu Faable'a bildirilemedi: "
                f"{report_exc}"
            )

        return False


def main():
    parser = argparse.ArgumentParser(
        description="EagleAI SMS Gateway worker"
    )

    parser.add_argument(
        "--once",
        action="store_true",
        help="Kuyruktan en fazla bir SMS işle ve çık.",
    )

    args = parser.parse_args()

    if args.once:
        process_once()
        return

    print("EagleAI SMS worker başladı.")
    print(f"Faable API: {FAABLE_API_URL}")
    print(f"Gateway: {SMSGATE_URL or 'otomatik yerel IP'}")
    print(f"Polling: {POLL_SECONDS:g} saniye")

    while True:
        try:
            process_once()
        except KeyboardInterrupt:
            print("\nWorker durduruldu.")
            break
        except Exception as exc:
            print(f"Worker hatası: {exc}")

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
