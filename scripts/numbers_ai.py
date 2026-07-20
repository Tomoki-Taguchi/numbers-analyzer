#!/usr/bin/env python3
"""ナンバーズ AI予想（各位ごと）

- RandomForest: 位置pごとの10クラス多クラス分類 → 0-9の確率
- LSTM: 位置pごとの one-hot 系列分類 → 0-9の確率

いずれも決定的。RF は random_state=42、LSTM は torch.manual_seed(42) に加えて
torch.set_num_threads(1) でスレッド由来の加算順序のぶれを止めている
（seed 固定だけでは確率が1e-6ぶれ、僅差の予想が実行ごとに入れ替わった）。
モデル数はD(3〜4)本×2なので、ロト6(43本×2)より計算は軽い。
"""

from collections import Counter

RF_WINDOW = 20
LSTM_SEQ_LEN = 30
LSTM_EPOCHS = 50


def build_rf_features(draws, target_idx, p, D, W=RF_WINDOW):
    """draws[:target_idx] の履歴から (target_idx, p) の数字を当てる特徴ベクトル(~43次元)。"""
    seq = [draws[i]["digits"][p] for i in range(target_idx)]
    window = seq[-W:]
    feats = []

    # 1) 直近Wの数字列（正規化, 左パディング0.0）
    pad = [None] * (W - len(window)) + list(window)
    feats += [(v / 9.0 if v is not None else 0.0) for v in pad]

    # 2) 直近Wの数字別出現率
    c = Counter(window)
    m = max(1, len(window))
    feats += [c.get(d, 0) / m for d in range(10)]

    # 3) 数字別 drought（直近Wに無ければ 1.0）
    for d in range(10):
        since = None
        for j in range(len(window) - 1, -1, -1):
            if window[j] == d:
                since = len(window) - 1 - j
                break
        feats.append(min(since, W) / W if since is not None else 1.0)

    # 4) 補助: 直前の数字・引っ張りフラグ・直前抽選の合計値
    last_digit = seq[-1] if seq else 0
    pull_flag = 1.0 if len(seq) >= 2 and seq[-1] == seq[-2] else 0.0
    last_sum = sum(draws[target_idx - 1]["digits"]) / (9.0 * D) if target_idx >= 1 else 0.0
    feats += [last_digit / 9.0, pull_flag, last_sum]
    return feats


def predict_rf(draws, D, W=RF_WINDOW):
    """各位10クラスRFで次回の数字別確率を返す。"""
    from sklearn.ensemble import RandomForestClassifier

    n = len(draws)
    result = {}
    for p in range(D):
        X, y = [], []
        for idx in range(W, n):
            X.append(build_rf_features(draws, idx, p, D, W))
            y.append(draws[idx]["digits"][p])

        if len(X) < 30 or len(set(y)) < 2:
            result[str(p)] = {str(d): 0.1 for d in range(10)}
            continue

        clf = RandomForestClassifier(
            n_estimators=100, max_depth=8, random_state=42, n_jobs=-1
        )
        clf.fit(X, y)
        proba = clf.predict_proba([build_rf_features(draws, n, p, D, W)])[0]

        # clf.classes_ で0-9に逆マップ（学習期間に出なかった数字は0.0）
        # 並列集約による浮動小数点ノイズを吸収して決定的にするため6桁丸め
        scores = {str(d): 0.0 for d in range(10)}
        for cls, pr in zip(clf.classes_, proba):
            scores[str(int(cls))] = round(float(pr), 6)
        result[str(p)] = scores
    return {"per_position": result}


# ---- LSTM ----

def _lstm_available():
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


def predict_lstm(draws, D, seq_len=LSTM_SEQ_LEN, epochs=LSTM_EPOCHS):
    """各位 one-hot 系列LSTMで次回の数字別確率を返す。torch無ければ一様。"""
    if not _lstm_available():
        return {"per_position": {str(p): {str(d): 0.1 for d in range(10)} for p in range(D)}}

    import torch
    import torch.nn as nn

    # マルチスレッドだと加算の順序が実行ごとに変わり、確率が1e-6程度ぶれる。
    # そのぶれで僅差の候補が入れ替わり、同じ回号なのに予想が変わることがあるため
    # シングルスレッドに固定して加算順序を決定的にする。
    torch.set_num_threads(1)

    class NumbersLSTM(nn.Module):
        def __init__(self, input_size=10, hidden_size=32, num_layers=1):
            super().__init__()
            self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True)
            self.fc = nn.Linear(hidden_size, 10)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.fc(out[:, -1, :])

    def onehot(d):
        v = [0.0] * 10
        v[d] = 1.0
        return v

    n = len(draws)
    result = {}
    for p in range(D):
        seq = [dr["digits"][p] for dr in draws]
        if n <= seq_len + 5:
            result[str(p)] = {str(d): 0.1 for d in range(10)}
            continue

        X, Y = [], []
        for i in range(seq_len, n):
            X.append([onehot(v) for v in seq[i - seq_len:i]])
            Y.append(seq[i])
        torch.manual_seed(42)
        Xt = torch.tensor(X, dtype=torch.float32)
        Yt = torch.tensor(Y, dtype=torch.long)

        model = NumbersLSTM()
        opt = torch.optim.Adam(model.parameters(), lr=0.005)
        loss_fn = nn.CrossEntropyLoss()
        model.train()
        for _ in range(epochs):
            opt.zero_grad()
            logits = model(Xt)
            loss = loss_fn(logits, Yt)
            loss.backward()
            opt.step()

        model.eval()
        with torch.no_grad():
            last = torch.tensor([[onehot(v) for v in seq[-seq_len:]]], dtype=torch.float32)
            probs = torch.softmax(model(last)[0], dim=0).tolist()
        # 4桁丸め: set_num_threads(1) で消しきれない残留ノイズへの余裕。
        # 表示は「16.92%」等なので4桁で精度は足りる。
        result[str(p)] = {str(d): round(float(probs[d]), 4) for d in range(10)}
    return {"per_position": result}
