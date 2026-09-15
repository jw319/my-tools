#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对照实验：水平型因子做「滚动标准化(z-score)」是否能提升次日方向预测力"""
import sys, warnings
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

from model import load, build_features, asof, FRED_LAG
from sklearn.linear_model import RidgeCV, LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.metrics import roc_auc_score


def zscore(s, win=250):
    return (s - s.rolling(win).mean()) / s.rolling(win).std()


def make_features(fut, mac, variant):
    px = fut.pivot(index="date", columns="symbol", values="close").sort_index()
    gold = px["GC"].dropna()
    idx = gold.index
    f = pd.DataFrame(index=idx); f["gold"] = gold
    f["mom_1d"] = gold.pct_change(1); f["mom_5d"] = gold.pct_change(5); f["mom_20d"] = gold.pct_change(20)
    f["ma_gap_20"] = gold / gold.rolling(20).mean() - 1
    f["ma_gap_60"] = gold / gold.rolling(60).mean() - 1
    f["vol_20d"] = gold.pct_change().rolling(20).std()
    d = gold.diff()
    up = d.clip(lower=0).rolling(14).mean(); dn = (-d.clip(upper=0)).rolling(14).mean()
    f["rsi_14"] = (100 - 100/(1+up/dn.replace(0,np.nan)))/100
    f["dist_high_20"] = gold / gold.rolling(20).max() - 1

    silver, copper = px["SI"], px["HG"]
    gs, gc = np.log(gold/silver), np.log(gold/copper)
    f["d_gold_silver_5d"] = gs.diff(5)

    macw = mac.pivot(index="date", columns="series", values="value").sort_index()
    A = pd.DataFrame({sid: asof(macw[sid], idx, FRED_LAG.get(sid,1)) for sid in macw.columns}, index=idx)
    def chg(c, n=5):
        s = A[c]
        if c in ("DFII10","DGS10","DGS2","T10Y2Y","T10YIE","VIXCLS","BAMLH0A0HYM2"): return s.diff(n)
        return s.pct_change(n)
    f["d_realyield_5d"] = chg("DFII10"); f["d_dxy_5d"] = chg("DTWEXBGS")
    f["d_vix_5d"] = chg("VIXCLS");        f["d_breakeven_5d"] = chg("T10YIE")
    f["d_oil_5d"] = chg("DCOILWTICO");    f["d_spx_5d"] = chg("SP500")
    f["term_spread"] = A["T10Y2Y"]/100

    if variant == "level":              # 原始水平
        f["realyield_level"] = A["DFII10"]/100
        f["gold_silver"] = gs; f["gold_copper"] = gc
        f["dxy_level"] = np.log(A["DTWEXBGS"])
        feats = ["d_realyield_5d","d_dxy_5d","d_vix_5d","d_breakeven_5d","d_oil_5d","d_spx_5d",
                 "term_spread","realyield_level","gold_silver","d_gold_silver_5d","gold_copper",
                 "dxy_level","mom_1d","mom_5d","mom_20d","ma_gap_20","ma_gap_60","vol_20d",
                 "rsi_14","dist_high_20"]
    else:                               # 滚动标准化
        f["realyield_z"] = zscore(A["DFII10"])
        f["gold_silver_z"] = zscore(gs); f["gold_copper_z"] = zscore(gc)
        f["dxy_z"] = zscore(np.log(A["DTWEXBGS"]))
        feats = ["d_realyield_5d","d_dxy_5d","d_vix_5d","d_breakeven_5d","d_oil_5d","d_spx_5d",
                 "term_spread","realyield_z","gold_silver_z","d_gold_silver_5d","gold_copper_z",
                 "dxy_z","mom_1d","mom_5d","mom_20d","ma_gap_20","ma_gap_60","vol_20d",
                 "rsi_14","dist_high_20"]

    f["target_ret"] = np.log(gold.shift(-1)/gold)
    f["target_dir"] = (f["target_ret"] > 0).astype(int)
    return f, feats


def wf_eval(f, feats, c_log=0.05):
    ok = f.dropna(subset=feats+["target_ret"]).copy()
    n = len(ok); min_train = max(400, min(750, int(n*0.3)))
    rows = []; mr = mc = None
    for i in range(min_train, n):
        if (i-min_train) % 21 == 0:
            tr = ok.iloc[:i]
            mr = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-1,3,30))).fit(tr[feats], tr["target_ret"])
            mc = make_pipeline(StandardScaler(), LogisticRegression(C=c_log, max_iter=2000)).fit(tr[feats], tr["target_dir"])
        x = ok[feats].iloc[[i]]
        rows.append({"d": ok.index[i], "pr": float(mr.predict(x)[0]),
                     "pp": float(mc.predict_proba(x)[0][1]),
                     "a": ok["gold"].iloc[i], "an": ok["target_price"] if "target_price" in ok else ok["gold"].iloc[i]*np.exp(ok["target_ret"].iloc[i])})
    w = pd.DataFrame(rows).set_index("d")
    act_up = (w["an"] > w["a"]).astype(int)
    hit = ((w["pr"] > 0) == (act_up == 1)).astype(int)
    resid = w["pr"] - np.log(w["an"]/w["a"])
    return {"acc": hit.mean(), "auc": roc_auc_score(act_up, w["pp"]),
            "ic": w["pr"].corr(np.log(w["an"]/w["a"])), "n": n,
            "mae": (w["an"]-w["a"]*np.exp(w["pr"])).abs().mean(),
            "mae_naive": (w["an"]-w["a"]).abs().mean(), "sigma": resid.std(),
            "logloss": None, "w": w}


if __name__ == "__main__":
    fut, mac = load()
    print(f"{'方案':<28}{'样本':>6}{'方向准确率':>11}{'AUC':>8}{'IC':>8}{'MAE':>9}{'朴素MAE':>9}")
    print("-"*79)
    for variant, label in [("level","A. 原始水平值(当前)"), ("z","B. 滚动标准化 z-score(250d)")]:
        f, feats = make_features(fut, mac, variant)
        r = wf_eval(f, feats)
        print(f"{label:<28}{r['n']:>6}{r['acc']:>10.1%}{r['auc']:>8.3f}{r['ic']:>8.3f}{r['mae']:>9.2f}{r['mae_naive']:>9.2f}")
