import json
import os

QUEUE_FILE = "upload_queue.json"


def add_to_queue(clips: list[dict]):
    queue = load_queue()
    queue.extend(clips)
    _save(queue)
    print(f"Kuyruğa {len(clips)} klip eklendi. Toplam: {len(queue)}")


def load_queue() -> list[dict]:
    if not os.path.exists(QUEUE_FILE):
        return []
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return []


def pop_batch(n: int) -> list[dict]:
    queue = load_queue()
    batch = queue[:n]
    remaining = queue[n:]
    _save(remaining)
    return batch


def queue_size() -> int:
    return len(load_queue())


def _save(queue: list):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, ensure_ascii=False, indent=2)
