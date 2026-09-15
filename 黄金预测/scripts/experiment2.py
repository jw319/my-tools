#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模型方案扫描：在走前式回测下比较不同模型/正则强度/特征子集"""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

from model import load, build_features, FEATURES, FACTOR_META
from experiment import wf_eval
from sklearn.linear_model import RidgeCV, LogisticRegression
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline

CORE = ["d_realyield_5d", "d_dxy_5d", "mom_5d", "mom_20d", "ma_gap_20",
        "vol_20d", "rsi_14", "gold_silver"]


def custom_wf(f, feats, clf_factory, seed=0):
    """通用走前式回测（只关心分类）"""
    ok = f.dropna(subset=feats + ["target_ret"]).copy()
    n = len(ok); min_train = max(400, min(750, int(n * 0.3)))
    rows = []
    mc = None
    for i in range(min_train, n):
        if (i - min_train) % 21 == 0:
            tr = ok.iloc[:i]
            mc = clf_factory()
            mc.fit(tr[feats], tr["target_dir"])
        x = ok[feats].iloc[[i]]
        rows.append({"pp": float(mc.predict_proba(x)[0][1]),
                     "a": ok["gold"].iloc[i],
                     "an": ok["gold"].iloc[i] * np.exp(ok["target_ret"].iloc[i])})
    w = pd.DataFrame(rows)
    act = (w["an"] > w["a"]).astype(int)
    pr = (w["pp"] > 0.5).astype(int)
    return (pr == act).mean(), w["pp"].shape[0]


if __name__ == "__main__":
    fut, mac = load()
    f = build_features(fut, mac)

    print("=== 分类模型扫描（方向准确率）===")
    print(f"{'方案':<42}{'样本':>7}{'方向准确率':>12}")
    print("-" * 62)

    variants = []
    for C in [0.005, 0.02, 0.05, 0.2, 1.0]:
        variants.append((f"Logistic C={C} (全因子)", FEATURES,
                         lambda C=C: make_pipeline(StandardScaler(),
                                   LogisticRegression(C=C, max_iter=3000))))
    variants.append(("GBDT (全因子, depth2)", FEATURES,
                     lambda: make_pipeline(StandardScaler(),
                       GradientBoostingClassifier(n_estimators=200, max_depth=2,
                                                  learning_rate=0.03, subsample=0.8, random_state=42))))
    variants.append(("GBDT (全因子, depth1 桩)", FEATURES,
                     lambda: make_pipeline(StandardScaler(),
                       GradientBoostingClassifier(n_estimators=300, max_depth=1,
                                                  learning_rate=0.03, subsample=0.8, random_state=42))))
    for C in [0.02, 0.2]:
        variants.append((f"Logistic C={C} (仅核心8因子)", CORE,
                         lambda C=C: make_pipeline(StandardScaler(),
                                   LogisticRegression(C=C, max_iter=3000))))

    best = None
    for name, feats, factory in variants:
        acc, n = custom_wf(f, feats, factory)
        flag = ""
        if best is None or acc > best[1]:
            best = (name, acc); flag = "  ← 当前最佳"
        print(f"{name:<42}{n:>7}{acc:>11.1%}{flag}")

    print(f"\n最佳：{best[0]}  {best[1]:.2%}")
