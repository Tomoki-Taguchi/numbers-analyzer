#!/usr/bin/env python3
"""LSTM非決定性の切り分け（一時ファイル・原因特定後に削除する）

  python _diag_determinism.py inproc   同一プロセス内で2回実行して比較
  python _diag_determinism.py once     1回分の出力をJSONで標準出力へ（別プロセス比較用）
  python _diag_determinism.py env      環境情報
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from numbers_common import GAMES, load_data  # noqa: E402

PERIOD = 600
GAME = "numbers3"


def _draws():
    return load_data(GAMES[GAME])[-PERIOD:]


def _diff(a, b):
    out = {}
    for p in a["per_position"]:
        d = {k: (a["per_position"][p][k], b["per_position"][p][k])
             for k in a["per_position"][p]
             if a["per_position"][p][k] != b["per_position"][p][k]}
        if d:
            out[p] = d
    return out


def cmd_env():
    import torch
    print("torch:", torch.__version__)
    print("get_num_threads:", torch.get_num_threads())
    print("get_num_interop_threads:", torch.get_num_interop_threads())
    for v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        print(f"{v}: {os.environ.get(v, '(unset)')}")
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    print("cpu:", line.split(":", 1)[1].strip())
                    break
    except OSError:
        pass


def cmd_inproc():
    from numbers_ai import predict_lstm
    draws = _draws()
    a = predict_lstm(draws, 3)
    b = predict_lstm(draws, 3)
    same = a == b
    print("同一プロセス内の再実行:", "一致" if same else "不一致")
    if not same:
        print("  差分:", json.dumps(_diff(a, b), ensure_ascii=False)[:600])
    return same


def cmd_once():
    from numbers_ai import predict_lstm
    print(json.dumps(predict_lstm(_draws(), 3), sort_keys=True))


def cmd_fingerprint():
    """CPUとLSTM出力のハッシュを出す。実行(マシン)をまたいで突き合わせる用。"""
    import hashlib
    from numbers_ai import predict_lstm
    cpu = "?"
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip()
                    break
    except OSError:
        pass
    blob = json.dumps(predict_lstm(_draws(), 3), sort_keys=True)
    print(f"FINGERPRINT cpu={cpu!r} sha256={hashlib.sha256(blob.encode()).hexdigest()[:16]}")


if __name__ == "__main__":
    {"env": cmd_env, "inproc": cmd_inproc, "once": cmd_once,
     "fingerprint": cmd_fingerprint}[sys.argv[1]]()
