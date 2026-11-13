"""幾何形態、K 線短線反轉、止跌反彈偵測（日 K，截至最後一根）。

每個幾何形態回傳 dict：
  kind   形態名稱         dir  bull / bear / neutral
  status confirmed（頸線剛被突破/跌破，break_day 為第幾日）/ near（接近頸線）/ forming / old（已突破超過 3 日）
  pts    關鍵點 [[idx, price], ...]（畫圖用）       neck  頸線價（水平）或 None
全部是規則近似，標示為「系統判斷」。
"""
from __future__ import annotations
import math

BREAK_WINDOW = 3     # 頸線突破後幾日內算「剛成立」


# ───────────────────────── 基礎工具 ─────────────────────────
def zigzag(B, a, e, pct):
    """以反轉幅度 pct 取波段高低點。回傳 [(idx, price, 'H'|'L')]，最後一個為暫定（尚未確認）。"""
    piv = []
    hi_i = lo_i = a
    direction = 0
    cur = a
    for i in range(a + 1, e + 1):
        h, l = B[i]["h"], B[i]["l"]
        if direction == 0:
            if h > B[hi_i]["h"]:
                hi_i = i
            if l < B[lo_i]["l"]:
                lo_i = i
            if B[hi_i]["h"] >= B[lo_i]["l"] * (1 + pct) and hi_i != lo_i:
                if lo_i < hi_i:
                    piv.append((lo_i, B[lo_i]["l"], "L"))
                    direction, cur = 1, hi_i
                else:
                    piv.append((hi_i, B[hi_i]["h"], "H"))
                    direction, cur = -1, lo_i
        elif direction == 1:
            if h > B[cur]["h"]:
                cur = i
            elif l <= B[cur]["h"] * (1 - pct):
                piv.append((cur, B[cur]["h"], "H"))
                direction, cur = -1, i
        else:
            if l < B[cur]["l"]:
                cur = i
            elif h >= B[cur]["l"] * (1 + pct):
                piv.append((cur, B[cur]["l"], "L"))
                direction, cur = 1, i
    if direction == 1:
        piv.append((cur, B[cur]["h"], "H"))
    elif direction == -1:
        piv.append((cur, B[cur]["l"], "L"))
    return piv


def _first_break(B, start, T, level, up):
    """start 之後第一根收盤突破（up=True 站上 / False 跌破）level 的索引，沒有則 None。"""
    for j in range(start + 1, T + 1):
        if (B[j]["c"] > level) if up else (B[j]["c"] < level):
            return j
    return None


def _status(B, T, start, neck, up, near=0.03):
    """依頸線判斷狀態。回傳 (status, break_day)。"""
    j = _first_break(B, start, T, neck, up)
    c = B[T]["c"]
    if j is not None:
        day = T - j + 1
        # 突破後又回到頸線另一側 → 視為失敗
        if (up and c < neck * 0.98) or ((not up) and c > neck * 1.02):
            return "failed", day
        return ("confirmed" if day <= BREAK_WINDOW else "old"), day
    if (up and c >= neck * (1 - near)) or ((not up) and c <= neck * (1 + near)):
        return "near", None
    return "forming", None


def _quad_fit(y):
    """二次曲線擬合 y = a x² + b x + c，回傳 (a, b, c, r2)。"""
    n = len(y)
    xs = range(n)
    Sx = sum(xs); Sx2 = sum(x * x for x in xs); Sx3 = sum(x ** 3 for x in xs); Sx4 = sum(x ** 4 for x in xs)
    Sy = sum(y); Sxy = sum(x * v for x, v in zip(xs, y)); Sx2y = sum(x * x * v for x, v in zip(xs, y))
    M = [[Sx4, Sx3, Sx2, Sx2y], [Sx3, Sx2, Sx, Sxy], [Sx2, Sx, n, Sy]]
    for i in range(3):                                   # 高斯消去
        p = max(range(i, 3), key=lambda r: abs(M[r][i]))
        M[i], M[p] = M[p], M[i]
        if abs(M[i][i]) < 1e-12:
            return None
        for r in range(i + 1, 3):
            f = M[r][i] / M[i][i]
            M[r] = [M[r][k] - f * M[i][k] for k in range(4)]
    c = M[2][3] / M[2][2]
    b = (M[1][3] - M[1][2] * c) / M[1][1]
    a = (M[0][3] - M[0][2] * c - M[0][1] * b) / M[0][0]
    mean = Sy / n
    ss_tot = sum((v - mean) ** 2 for v in y)
    ss_res = sum((v - (a * x * x + b * x + c)) ** 2 for x, v in zip(xs, y))
    return a, b, c, (1 - ss_res / ss_tot) if ss_tot > 0 else 0.0


# ───────────────────────── 雙底 / 雙頂 ─────────────────────────
def double_bottom_top(B, T, P):
    out = []
    for k in range(len(P) - 2):
        (i1, p1, t1), (i2, p2, t2), (i3, p3, t3) = P[k], P[k + 1], P[k + 2]
        last = k + 2
        if t1 == "L" and t3 == "L" and min(B[j]["l"] for j in range(i3, T + 1)) < min(p1, p3) * 0.97:
            # 原本的 W 會因為之後又破更低而失敗時：若中間小反彈沒碰到頸線就又破底，第二個底改用這段最低點（例：3374 的 11/04→11/06）
            j = k + 2
            while j + 2 < len(P) and P[j + 1][1] < p2 * 0.97 and P[j + 2][2] == "L":
                j += 2
                if P[j][1] < p3:
                    i3, p3, last = P[j][0], P[j][1], j
        if i3 < T - 45 or i3 - i1 < 10:
            continue
        if last == len(P) - 1:
            continue                                 # 第二個頂／底還在走（價格還沒從那裡反轉），不能算成形
        if t1 == "L" and t3 == "L":              # 雙重底
            gap = abs(p1 - p3) / min(p1, p3)
            if gap > 0.12 or (p2 - max(p1, p3)) / max(p1, p3) < 0.08:
                continue                                 # 兩底差 4% 內＝標準雙重底；4–12%＝不對稱（醜一點的 W）
            if min(B[j]["l"] for j in range(i3, T + 1)) < min(p1, p3) * 0.97:
                continue
            st, d = _status(B, T, i3, p2, True)
            if last != k + 2 and st not in ("confirmed", "near"):
                continue                                 # 用延伸後的第二個底：只在接近或突破頸線時才標（避免雜訊）
            if gap > 0.04:
                if st not in ("confirmed", "near"):
                    continue                             # 不對稱的只在接近或突破頸線時才標，避免太多雜訊
                pre = [[P[k - 1][0], P[k - 1][1]]] if k > 0 and P[k - 1][2] == "H" else []
                out.append({"kind": "雙重底（不對稱）", "dir": "bull", "status": st, "day": d, "neck": p2, "key_i": i3,
                            "pts": pre + [[i1, p1], [i2, p2], [i3, p3]] + ([[T, B[T]["c"]]] if T > i3 else [])})
                continue
            pre = [[P[k - 1][0], P[k - 1][1]]] if k > 0 and P[k - 1][2] == "H" else []   # 畫成完整的 W：前一個高點 → 底 → 頸 → 底 → 現在
            out.append({"kind": "雙重底", "dir": "bull", "status": st, "day": d, "neck": p2, "key_i": i3,
                        "pts": pre + [[i1, p1], [i2, p2], [i3, p3]] + ([[T, B[T]["c"]]] if T > i3 else [])})
        elif t1 == "H" and t3 == "H":            # 雙重頂
            if abs(p1 - p3) / max(p1, p3) > 0.04 or (min(p1, p3) - p2) / min(p1, p3) < 0.08:
                continue
            if max(B[j]["h"] for j in range(i3, T + 1)) > max(p1, p3) * 1.03:
                continue
            st, d = _status(B, T, i3, p2, False)
            pre = [[P[k - 1][0], P[k - 1][1]]] if k > 0 and P[k - 1][2] == "L" else []   # 畫成完整的 M
            out.append({"kind": "雙重頂", "dir": "bear", "status": st, "day": d, "neck": p2, "key_i": i3,
                        "pts": pre + [[i1, p1], [i2, p2], [i3, p3]] + ([[T, B[T]["c"]]] if T > i3 else [])})
    return out


# ───────────────────────── 頭肩底 / 頭肩頂 ─────────────────────────
def head_shoulders(B, T, P):
    out = []
    for k in range(len(P) - 4):
        seg = P[k:k + 5]
        (i1, p1, t1), (i2, p2, _), (i3, p3, _), (i4, p4, _), (i5, p5, _) = seg
        if i5 < T - 50 or i5 - i1 < 20:
            continue
        # 頸線：兩個反向波段點連線，外推到 T
        slope = (p4 - p2) / (i4 - i2)
        neck_T = p4 + slope * (T - i4)
        if t1 == "L":                            # 頭肩底：L H L(頭) H L
            if not (p3 < min(p1, p5) * 0.97 and abs(p1 - p5) / ((p1 + p5) / 2) <= 0.08
                    and abs(p2 - p4) / ((p2 + p4) / 2) <= 0.06):
                continue
            up = True
            j = None
            for x in range(i5 + 1, T + 1):
                if B[x]["c"] > p4 + slope * (x - i4):
                    j = x
                    break
            kind, d = "頭肩底", "bull"
        else:                                    # 頭肩頂：H L H(頭) L H
            if not (p3 > max(p1, p5) * 1.03 and abs(p1 - p5) / ((p1 + p5) / 2) <= 0.08
                    and abs(p2 - p4) / ((p2 + p4) / 2) <= 0.06):
                continue
            up = False
            j = None
            for x in range(i5 + 1, T + 1):
                if B[x]["c"] < p4 + slope * (x - i4):
                    j = x
                    break
            kind, d = "頭肩頂", "bear"
        c = B[T]["c"]
        if j is not None:
            day = T - j + 1
            failed = (up and c < neck_T * 0.98) or ((not up) and c > neck_T * 1.02)
            st = "failed" if failed else ("confirmed" if day <= BREAK_WINDOW else "old")
        else:
            day = None
            near = (up and c >= neck_T * 0.97) or ((not up) and c <= neck_T * 1.03)
            st = "near" if near else "forming"
        out.append({"kind": kind, "dir": d, "status": st, "day": day, "neck": round(neck_T, 2),
                    "pts": [[i, p] for i, p, _ in seg]})
    return out


# ───────────────────────── V 形底 / V 形頂 ─────────────────────────
def v_shape(B, T):
    out = []
    a = max(0, T - 14)
    lo_i = min(range(a, T + 1), key=lambda i: B[i]["l"])
    hi_i = max(range(a, T + 1), key=lambda i: B[i]["h"])
    # V 形底
    if lo_i < T:
        s = max(0, lo_i - 15)
        top_i = max(range(s, lo_i + 1), key=lambda i: B[i]["h"])
        drop = (B[top_i]["h"] - B[lo_i]["l"]) / B[top_i]["h"]
        reb = (B[T]["c"] - B[lo_i]["l"]) / (B[top_i]["h"] - B[lo_i]["l"]) if B[top_i]["h"] > B[lo_i]["l"] else 0
        if drop >= 0.15 and lo_i - top_i <= 12 and reb >= 0.5 and T - lo_i <= 15:
            out.append({"kind": "V形底", "dir": "bull", "status": "confirmed" if reb >= 0.5 and T - lo_i <= 5 else "old",
                        "day": T - lo_i + 1, "neck": None,
                        "pts": [[top_i, B[top_i]["h"]], [lo_i, B[lo_i]["l"]], [T, B[T]["c"]]]})
    # V 形頂
    if hi_i < T:
        s = max(0, hi_i - 15)
        bot_i = min(range(s, hi_i + 1), key=lambda i: B[i]["l"])
        rise = (B[hi_i]["h"] - B[bot_i]["l"]) / B[bot_i]["l"]
        fall = (B[hi_i]["h"] - B[T]["c"]) / (B[hi_i]["h"] - B[bot_i]["l"]) if B[hi_i]["h"] > B[bot_i]["l"] else 0
        if rise >= 0.15 and hi_i - bot_i <= 12 and fall >= 0.5 and T - hi_i <= 15:
            out.append({"kind": "V形頂", "dir": "bear", "status": "confirmed" if T - hi_i <= 5 else "old",
                        "day": T - hi_i + 1, "neck": None,
                        "pts": [[bot_i, B[bot_i]["l"]], [hi_i, B[hi_i]["h"]], [T, B[T]["c"]]]})
    return out


# ───────────────────────── 圓弧底 / 圓弧頂 ─────────────────────────
def rounded(B, T):
    out = []
    best = {}
    for W in (40, 60, 80, 100, 120):
        if T - W + 1 < 0:
            continue
        a0 = T - W + 1
        y = [B[i]["c"] for i in range(a0, T + 1)]
        fit = _quad_fit(y)
        if not fit:
            continue
        a, b, c, r2 = fit
        if abs(a) < 1e-9:
            continue
        xv = -b / (2 * a)
        if not (0.3 * W <= xv <= 0.7 * W) or r2 < 0.65 or (W - 1 - xv) < max(8, 0.2 * W):
            continue
        q = max(3, W // 10)
        left = sum(y[:q]) / q
        right = sum(y[-q:]) / q
        ext = min(y) if a > 0 else max(y)
        ext_i = a0 + (y.index(ext))
        if a > 0:                                                  # 圓弧底
            depth = (min(left, right) - ext) / min(left, right)
            broad = sum(1 for v in y if v < ext + 0.5 * (left - ext)) / W
            if depth < 0.08 or broad < 0.25 or right < ext * 1.05:
                continue
            key = "底"
        else:                                                      # 圓弧頂
            depth = (ext - max(left, right)) / ext
            broad = sum(1 for v in y if v > ext - 0.5 * (ext - left)) / W
            if depth < 0.08 or broad < 0.25 or right > ext * 0.95:
                continue
            key = "頂"
        if key not in best or r2 > best[key][0]:
            best[key] = (r2, W, a0, ext_i, left, right, depth, (a, b, c))
    for key, (r2, W, a0, ext_i, left, right, depth, abc) in best.items():
        c = B[T]["c"]
        qa, qb, qc = abc
        curve = [[a0 + k, qa * k * k + qb * k + qc] for k in sorted(set(list(range(0, W, max(1, W // 10))) + [W - 1]))]
        if key == "底":
            rim = left
            st = "confirmed" if c >= rim * 0.97 and T - ext_i >= W * 0.3 else "forming"
            if c >= rim * 0.97:
                # 站上左緣算完成，剛站上 3 日內才標 confirmed
                j = next((x for x in range(ext_i + 1, T + 1) if B[x]["c"] >= rim * 0.97), None)
                d = T - j + 1 if j is not None else None
                st = "confirmed" if d is not None and d <= BREAK_WINDOW else "old"
            else:
                d = None
                st = "near" if c >= rim * 0.9 else "forming"
            out.append({"kind": "圓弧底", "dir": "bull", "status": st, "day": d, "neck": round(rim, 2),
                        "pts": curve, "r2": round(r2, 2), "depth": round(depth, 3)})
        else:
            rim = left
            if c <= rim * 1.03:
                j = next((x for x in range(ext_i + 1, T + 1) if B[x]["c"] <= rim * 1.03), None)
                d = T - j + 1 if j is not None else None
                st = "confirmed" if d is not None and d <= BREAK_WINDOW else "old"
            else:
                d = None
                st = "forming"
            out.append({"kind": "圓弧頂", "dir": "bear", "status": st, "day": d, "neck": round(rim, 2),
                        "pts": curve, "r2": round(r2, 2), "depth": round(depth, 3)})
    return out


# ───────────────────────── 杯柄 ─────────────────────────
def cup_handle(B, T):
    if T < 45:
        return []
    lo = max(0, T - 24)
    hi = T - 3
    if hi <= lo:
        return []
    r = max(range(lo, hi + 1), key=lambda i: B[i]["h"])      # 右緣高點（柄頂）
    rim = B[r]["h"]
    best = None
    for W in (30, 45, 60, 80, 100, 120):
        a0 = r - W
        if a0 < 0:
            continue
        y = [B[i]["c"] for i in range(a0, r + 1)]
        fit = _quad_fit(y)
        if not fit:
            continue
        a, b, c, r2 = fit
        if a <= 0 or r2 < 0.65:
            continue
        xv = -b / (2 * a)
        if not (0.3 * W <= xv <= 0.7 * W):
            continue
        left_hi_i = max(range(a0, a0 + max(4, W // 5)), key=lambda i: B[i]["h"])
        left_rim = B[left_hi_i]["h"]
        bottom = min(B[i]["l"] for i in range(a0, r + 1))
        depth = (rim - bottom) / rim
        if not (0.12 <= depth <= 0.35) or not (0.92 <= rim / left_rim <= 1.08):
            continue
        if best is None or r2 > best[0]:
            best = (r2, W, a0, left_hi_i, bottom, depth, (a, b, c))
    if not best:
        return []
    r2, W, a0, left_hi_i, bottom, depth, (qa, qb, qc) = best
    handle_low = min(B[i]["l"] for i in range(r + 1, T + 1))
    hdepth = (rim - handle_low) / rim
    if not (0.01 <= hdepth <= min(0.5 * depth, 0.15)):
        return []
    c = B[T]["c"]
    brk = next((x for x in range(r + 1, T + 1) if B[x]["c"] > rim), None)
    if brk is not None:
        d = T - brk + 1
        st = "confirmed" if d <= BREAK_WINDOW else "old"
        if c < rim * 0.98:
            st = "failed"
    else:
        d = None
        st = "near" if c >= rim * 0.97 else "forming"
    hl = min(range(r + 1, T + 1), key=lambda i: B[i]["l"])
    curve = [[a0 + k, qa * k * k + qb * k + qc] for k in sorted(set(list(range(0, W, max(1, W // 10))) + [W]))]
    return [{"kind": "杯柄", "dir": "bull", "status": st, "day": d, "neck": round(rim, 2),
             "pts": curve + [[r, rim], [hl, B[hl]["l"]]],
             "r2": round(r2, 2), "depth": round(depth, 3), "hdepth": round(hdepth, 3)}]


# ───────────────────────── 三角形 / 楔形 ─────────────────────────
def _line(pts):
    """最小平方直線 (slope, intercept)，x 為索引。"""
    n = len(pts)
    sx = sum(x for x, _ in pts); sy = sum(y for _, y in pts)
    sxx = sum(x * x for x, _ in pts); sxy = sum(x * y for x, y in pts)
    den = n * sxx - sx * sx
    if den == 0:
        return 0.0, sy / n
    m = (n * sxy - sx * sy) / den
    return m, (sy - m * sx) / n


def triangles(B, T):
    a = max(0, T - 70)
    P = zigzag(B, a, T, 0.04)
    H = [(i, p) for i, p, t in P if t == "H" and i >= T - 60]
    L = [(i, p) for i, p, t in P if t == "L" and i >= T - 60]
    if len(H) < 2 or len(L) < 2 or len(H) + len(L) < 5:
        return []
    H, L = H[-4:], L[-4:]
    if max(H[-1][0], L[-1][0]) < T - 12 or min(H[0][0], L[0][0]) > T - 20:
        return []
    mh, bh = _line(H)
    ml, bl = _line(L)
    mean = sum(p for _, p in H + L) / len(H + L)
    su, sl = mh / mean * 100, ml / mean * 100            # %/根
    i0 = min(H[0][0], L[0][0])
    gap0 = (mh * i0 + bh) - (ml * i0 + bl)
    gapT = (mh * T + bh) - (ml * T + bl)
    if gap0 <= 0 or gapT <= 0 or gapT > gap0 * 0.8:       # 必須收斂
        return []
    up_T, lo_T = mh * T + bh, ml * T + bl
    kind = None
    if su <= -0.05 and sl >= 0.05:
        kind, d = "對稱三角形", "neutral"
    elif abs(su) < 0.05 and sl >= 0.05:
        kind, d = "上升三角形", "bull"
    elif su <= -0.05 and abs(sl) < 0.05:
        kind, d = "下降三角形", "bear"
    elif su > 0.03 and sl > 0.03 and sl > su:
        kind, d = "上升楔形", "bear"
    elif su < -0.03 and sl < -0.03 and su < sl:
        kind, d = "下降楔形", "bull"
    if not kind:
        return []
    c = B[T]["c"]
    up_brk = next((x for x in range(T - 2, T + 1) if B[x]["c"] > mh * x + bh), None)
    dn_brk = next((x for x in range(T - 2, T + 1) if B[x]["c"] < ml * x + bl), None)
    st, day = "forming", None
    if up_brk is not None:
        st, day = "confirmed", T - up_brk + 1
        d2 = "bull"
    elif dn_brk is not None:
        st, day = "confirmed", T - dn_brk + 1
        d2 = "bear"
    else:
        d2 = d
        if c >= up_T * 0.97 or c <= lo_T * 1.03:
            st = "near"
    return [{"kind": kind, "dir": d2, "status": st, "day": day, "neck": None,
             "pts": [[i, p] for i, p in sorted(H + L)],
             "lines": [[i0, mh * i0 + bh, T, up_T], [i0, ml * i0 + bl, T, lo_T]]}]


# ───────────────────────── 島型反轉 ─────────────────────────
def island(B, T):
    """島型反轉（參考 Titan FX 說明）：
    - 先向一個方向跳空，橫向整理形成「島嶼」，再向相反方向跳空；兩個缺口之間沒有價格重疊（島嶼被孤立）。
    - 頂部：向上跳空 → 島嶼 → 向下跳空（先前為上升趨勢），為賣出訊號；底部相反，為買入訊號。
    - 確認：第二個缺口之後價格要穩定在島嶼之外；回到島嶼內即視為失敗。
    - 成交量放大（缺口當天量 ≥ 前 20 日均量 1.5 倍）可靠度較高。
    - 停損參考：頂部放島嶼高點之上，底部放島嶼低點之下。回傳最近一個。"""
    out = []
    GAP = 0.005
    for a in range(max(21, T - 40), T):
        pre = B[a - 1]
        base = B[max(a - 9, 0)]["c"]
        v20 = sum(B[i]["v"] for i in range(a - 20, a)) / 20 or 1
        # ── 頂部：向上跳空
        if B[a]["l"] > pre["h"] * (1 + GAP) and pre["c"] > base * 1.05:
            for b in range(a + 1, min(T, a + 15) + 1):
                isl_low = min(B[i]["l"] for i in range(a, b))
                if isl_low <= pre["h"]:
                    break
                if B[b]["h"] < isl_low * (1 - GAP) and B[b]["h"] < B[b - 1]["l"]:
                    hi = max(B[i]["h"] for i in range(a, b))
                    held = all(B[i]["c"] < isl_low for i in range(b, T + 1))      # 之後仍在島嶼之下
                    out.append({"kind": "島型反轉頂", "dir": "bear", "a": a, "b": b, "hi": hi, "lo": isl_low, "stop": hi,
                                "held": held, "volup": max(B[a]["v"], B[b]["v"]) >= 1.5 * v20})
                    break
        # ── 底部：向下跳空
        if B[a]["h"] < pre["l"] * (1 - GAP) and pre["c"] < base * 0.95:
            for b in range(a + 1, min(T, a + 15) + 1):
                isl_hi = max(B[i]["h"] for i in range(a, b))
                if isl_hi >= pre["l"]:
                    break
                if B[b]["l"] > isl_hi * (1 + GAP) and B[b]["l"] > B[b - 1]["h"]:
                    lo = min(B[i]["l"] for i in range(a, b))
                    held = all(B[i]["c"] > isl_hi for i in range(b, T + 1))       # 之後仍在島嶼之上
                    out.append({"kind": "島型反轉底", "dir": "bull", "a": a, "b": b, "hi": isl_hi, "lo": lo, "stop": lo,
                                "held": held, "volup": max(B[a]["v"], B[b]["v"]) >= 1.5 * v20})
                    break
    res = []
    for kind in ("島型反轉頂", "島型反轉底"):
        c = [x for x in out if x["kind"] == kind]
        if not c:
            continue
        x = max(c, key=lambda z: z["b"])
        day = T - x["b"] + 1
        n_isl = x["b"] - x["a"]
        status = "confirmed" if (day <= BREAK_WINDOW and x["held"]) else ("failed" if not x["held"] else "old")
        # 單日島嶼若沒有量能確認，只標示、不改變四種型態
        kind_out = kind if (n_isl >= 2 or x["volup"]) else "單日" + kind
        res.append({"kind": kind_out, "dir": x["dir"], "status": status, "day": day, "neck": None,
                    "pts": [[x["a"], x["hi"]], [x["b"] - 1, x["hi"]]],
                    "rect": [x["a"], x["b"] - 1, x["hi"], x["lo"]], "stop": x["stop"], "volup": x["volup"]})
    return res


# ───────────────────────── 總入口 ─────────────────────────
def detect_geometry(B, T):
    res = []
    if T < 30:
        return res
    a = max(0, T - 150)
    for pct in (0.06, 0.10):
        P = zigzag(B, a, T, pct)
        res += double_bottom_top(B, T, P)
        res += head_shoulders(B, T, P)
    res += v_shape(B, T)
    res += rounded(B, T)
    res += cup_handle(B, T)
    res += triangles(B, T)
    res += island(B, T)
    # 去重（同形態保留最近、狀態較新的一個）
    uniq = {}
    for r in res:
        k = r["kind"]
        key = lambda x: x.get("key_i", x["pts"][-1][0])
        if k not in uniq or key(r) > key(uniq[k]):
            uniq[k] = r
    # 雙重底、雙重頂若用到同一段波段點（W 和 M 疊在一起），只留比較新的那個
    if uniq.get("雙重底") and uniq.get("雙重底（不對稱）"):
        uniq.pop("雙重底（不對稱）")                     # 有標準的就不要再畫不對稱的
    db, dt = uniq.get("雙重底") or uniq.get("雙重底（不對稱）"), uniq.get("雙重頂")
    if db and dt and set(map(tuple, db["pts"])) & set(map(tuple, dt["pts"])):
        uniq.pop("雙重頂" if db["key_i"] >= dt["key_i"] else db["kind"])
    return list(uniq.values())


# ───────────────────────── K 線短線反轉 ─────────────────────────
def _parts(b):
    body = abs(b["c"] - b["o"])
    rng = b["h"] - b["l"]
    up = b["h"] - max(b["o"], b["c"])
    lo = min(b["o"], b["c"]) - b["l"]
    return body, rng, up, lo


def candle_patterns(B, T):
    """回傳 [(名稱, 'bull'|'bear')]，皆為「最後一根」完成的形態。台股紅 K = 收>開。"""
    out = []
    if T < 6:
        return out
    b0, b1 = B[T], B[T - 1]
    body, rng, up, lo = _parts(b0)
    if rng <= 0:
        return out
    down_trend = B[T - 1]["c"] < B[T - 6]["c"] * 0.97
    up_trend = B[T - 1]["c"] > B[T - 6]["c"] * 1.03
    small = rng / b0["c"] >= 0.012
    # 傘形線（錘子）
    if small and body <= 0.35 * rng and lo >= 2 * max(body, 1e-9) and up <= 0.25 * rng:
        if down_trend:
            out.append(("傘形線", "bull"))
    # 倒錘子 / 流星線
    if small and body <= 0.35 * rng and up >= 2 * max(body, 1e-9) and lo <= 0.25 * rng:
        if down_trend:
            out.append(("倒錘子線", "bull"))
        elif up_trend:
            out.append(("流星線", "bear"))
    pb, prng, _, _ = _parts(b1)
    p_red, p_black = b1["c"] > b1["o"], b1["c"] < b1["o"]
    red, black = b0["c"] > b0["o"], b0["c"] < b0["o"]
    big_p = pb / b1["c"] >= 0.01
    # 吞沒
    if big_p and red and p_black and b0["o"] <= b1["c"] and b0["c"] >= b1["o"] and down_trend:
        out.append(("多頭吞沒", "bull"))
    if big_p and black and p_red and b0["o"] >= b1["c"] and b0["c"] <= b1["o"] and up_trend:
        out.append(("空頭吞沒", "bear"))
    # 刺透 / 烏雲蓋頂
    mid = (b1["o"] + b1["c"]) / 2
    if big_p and p_black and red and b0["o"] < b1["c"] and mid < b0["c"] < b1["o"] and down_trend:
        out.append(("刺透形態", "bull"))
    if big_p and p_red and black and b0["o"] > b1["c"] and b1["o"] < b0["c"] < mid and up_trend:
        out.append(("烏雲蓋頂", "bear"))
    # 啟明星 / 黃昏星（三根）
    b2 = B[T - 2]
    b2body = abs(b2["c"] - b2["o"])
    if T >= 7 and b2body / b2["c"] >= 0.01:
        mid2 = (b2["o"] + b2["c"]) / 2
        small1 = pb <= 0.4 * b2body
        if b2["c"] < b2["o"] and small1 and max(b1["o"], b1["c"]) <= b2["c"] * 1.005 and red and b0["c"] > mid2 \
                and B[T - 2]["c"] < B[T - 7]["c"] * 0.97:
            out.append(("啟明星", "bull"))
        if b2["c"] > b2["o"] and small1 and min(b1["o"], b1["c"]) >= b2["c"] * 0.995 and black and b0["c"] < mid2 \
                and B[T - 2]["c"] > B[T - 7]["c"] * 1.03:
            out.append(("黃昏星", "bear"))
        # 三隻烏鴉
        b3 = B[T - 2]
        if all(B[i]["c"] < B[i]["o"] and abs(B[i]["c"] - B[i]["o"]) / B[i]["c"] >= 0.01 for i in (T - 2, T - 1, T)) \
                and B[T]["c"] < B[T - 1]["c"] < B[T - 2]["c"] and up_trend:
            out.append(("三隻烏鴉", "bear"))
    return out


# ───────────────────────── 止跌反彈 ─────────────────────────
def rebound(B, T):
    """近期下跌後，在谷底止跌反彈。回傳 dict 或 None。"""
    if T < 25:
        return None
    a = T - 19
    low20 = min(B[i]["l"] for i in range(a, T + 1))
    lo_i = max(i for i in range(a, T + 1) if B[i]["l"] == low20)
    if lo_i < T - 2:                                   # 谷底必須是最近 3 天內形成
        return None
    peak = max(B[i]["h"] for i in range(a, lo_i + 1))
    drop = (peak - low20) / peak
    if drop < 0.10:
        return None
    c, o, h, l = B[T]["c"], B[T]["o"], B[T]["h"], B[T]["l"]
    prev_c = B[T - 1]["c"]
    bounce = (c - low20) / low20
    pos = (c - l) / (h - l) if h > l else 0.5
    # 今天要「收在近期谷底之上明顯的位置」且比昨天強
    if not (c > prev_c and bounce >= 0.02 and (c > o or pos >= 0.6)):
        return None
    vol5 = sum(B[i]["v"] for i in range(T - 5, T)) / 5
    cp = [n for n, d in candle_patterns(B, T) if d == "bull"]
    score = 0
    score += 1 if c > o else 0
    score += 1 if cp else 0
    score += 1 if vol5 and B[T]["v"] >= 1.2 * vol5 else 0
    score += 1 if c > B[T - 1]["h"] else 0               # 收復昨日高點
    return {"low": low20, "low_idx": lo_i, "drop": round(drop * 100, 1), "bounce": round(bounce * 100, 1),
            "pattern": cp, "vol_ratio": round(B[T]["v"] / vol5, 2) if vol5 else None, "score": score}
