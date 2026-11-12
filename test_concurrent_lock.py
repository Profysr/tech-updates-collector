"""Concurrent-writer test: two processes hammer cursors.txt through store_lock()."""
import os
import sys
import time
from multiprocessing import Process

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))
from _lock import store_lock  # noqa: E402
from _textio import read_text, write_text  # noqa: E402

CURSORS = os.path.join(os.environ["TECH_UPDATES_ROOT"], "state", "cursors.txt")
N = 50


def worker(tag):
    for _ in range(N):
        with store_lock():
            d = dict(line.split("=", 1) for line in read_text(CURSORS).strip().split("\n"))
            d["a"] = str(int(d["a"]) + 1)
            time.sleep(0.005)  # widen the race window
            write_text(CURSORS, "\n".join(k + "=" + v for k, v in d.items()) + "\n")


if __name__ == "__main__":
    write_text(CURSORS, "a=0\nb=2\n")
    procs = [Process(target=worker, args=(i,)) for i in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join()
    final = read_text(CURSORS)
    print(final)
    expected = f"a={2 * N}\nb=2"
    print("PASS" if final.strip() == expected else f"FAIL: expected {expected}")
