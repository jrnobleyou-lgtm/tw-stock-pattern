"""盤整區間與四種型態判定引擎（台股 / 美股共用）。

區間規則（2026-11 與使用者討論後的版本）：
  - 長度 10～60 根（約 2 週到 3 個月）。
  - 上緣、下緣都要至少「碰到」2 次（波段高/低點），兩次至少隔 5 根，價差在 1.5% 以內。
  - 高低差上限依股性：近 60 日平均每日振幅 ≥ 3%（波動大）→ 25%，否則 20%。
  - 區間內最高／最低（含影線）不可超出上下緣 5% 以上。
  - 收盤可小幅越界（3% 內），但不能連續 2 天收在上下緣之外。
  - 區間不能跨過一次突破或跌破：區間內若有連 3 日收盤站上之前那段的最高價（或跌破最低價），
    ，就代表股價已經走出新的一段，舊區間到那裡結束。
  - 太斜不算盤整：區間內收盤趨勢線從頭到尾的漲跌超過框高度的 6 成；或區間內收盤趨勢線漲或跌 ≥ 10% 且走得很穩（R² ≥ 0.75），沿著上升／下降趨勢線走。
  - 突破：收盤站上上緣且量達區間均量 1.5 倍 → 突破訊號（第 1 日）；3 日內收回上緣之下 = 假突破，區間繼續；
          連 3 日守在上緣之上 = 突破確認（壓力轉支撐），區間結束，之後跌回也不再接回。
          沒帶量但收盤離開區間 → 區間結束，標示「無量突破待追蹤」，不算轉強。
  - 跌破：收盤跌破下緣；3 日內站回 = 假跌破；連續 3 日收在下緣之下 = 區間失效。
  - 失效的區間以紫色保留 20 個交易日，之後不再畫。
"""
from __future__ import annotations

SWING_K = 2          # 波段高低點：左右各 2 根內最高/最低
MIN_BARS = 10
MAX_RANGE = 0.20       # 波動小的股票
MAX_RANGE_VOL = 0.25   # 波動大的股票（近 60 日平均每日振幅 ≥ VOL_AMP）
VOL_AMP = 0.03
STEP_TOL = 0.0          # 收盤超過之前那段的最高／最低價就算（連 3 日）
RISE_PCT = 0.10        # 趨勢通道：區間內趨勢線漲跌幅 ≥ 10%
TREND_RATIO = 0.6      # 趨勢線從頭到尾的漲跌 > 框高度的 6 成：太斜，是趨勢不是盤整
RISE_R2 = 0.75         # 且走得很穩（直線貼合度 R² ≥ 0.75）→ 不算盤整
STEP_DAYS = 3          # 區間內若有連 3 日收盤站上（或跌破）之前那段的最高價（最低價），代表已經突破／跌破，區間不能跨過去
TOUCH_TOL = 0.015
TOUCH_GAP = 5
WINDOWS = (60,)
VOL_MULT = 1.5
CONFIRM_DAYS = 3
SIGNAL_LIFE = 20     # 訊號日起算天數（訊號日為第 1 日）
STRONG_WINDOW = 3    # 突破後幾個交易日內算「轉強」（使用者指定 3 日）
RALLY_PCT = 0.20      # 3 日內由近期低點反彈幅度達 20% 算轉強
WEAK_DAYS = 3        # 連續幾日收在 5、10 日線之下算「走弱」


def sma(vals, n):
    out = [None] * len(vals)
    s = 0.0
    for i, v in enumerate(vals):
        s += v
        if i >= n:
            s -= vals[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def _swings(B, a, e, is_high):
    k = SWING_K
    key = "h" if is_high else "l"
    f = max if is_high else min
    res = []
    for i in range(max(a, k), e - k + 1):
        if B[i][key] == f(B[j][key] for j in range(i - k, i + k + 1)):
            res.append(i)
    return res


def _edge(B, idxs, is_high):
    """回傳 (邊界價, 碰觸點索引) 或 None。"""
    key = "h" if is_high else "l"
    order = sorted(idxs, key=lambda i: B[i][key], reverse=is_high)
    for i in order:
        p = B[i][key]
        partners = [j for j in idxs if abs(j - i) >= TOUCH_GAP and
                    ((p - B[j][key]) if is_high else (B[j][key] - p)) <= TOUCH_TOL * p
                    and ((p - B[j][key]) if is_high else (B[j][key] - p)) >= 0]
        if partners:
            touches = sorted([i] + partners)
            return p, touches
    return None


MAX_WICK = float(__import__("os").environ.get("BOX_MAX_WICK", "0.05"))       # 區間內最高／最低價超出上下緣的容許幅度；超過就不是盤整
OUT_TOL = 0.03       # 收盤越過邊界的容許幅度；超過就視為已脫離區間
OUT_RUN = 2          # 連續幾根收在邊界外，視為已脫離區間


def _fail_end(B, i, e, hi):
    """帶量突破日 i 之後的 2 根（含 i 共 3 日）內若有收盤收回上緣之下 → 假突破，回傳收回那天的索引；
    連 3 日都守在上緣之上 → 突破確認，回傳 None（區間到此結束）。"""
    for k in range(i + 1, min(e, i + CONFIRM_DAYS - 1) + 1):
        if B[k]["c"] <= hi:
            return k
    return None if e >= i + CONFIRM_DAYS - 1 else e     # 還沒滿 3 天：暫時不算結束


def _closes_ok(B, s, e, hi, lo):
    """區間內的收盤檢查，通過時回傳區間均量，否則 None。
    - 個別小幅越界（沒有帶量）不影響區間。
    - 帶量站上上緣 = 突破訊號：之後若在 20 日內連 3 日收回上緣之下（突破失效），
      區間恢復，這段不算脫離；否則區間在此之前就結束。
    - 越界超過 3%、或連續 3 根越界，區間失效。"""
    run, vsum, cnt, i = 0, 0.0, 0, s
    while i <= e:
        c = B[i]["c"]
        if cnt >= 3 and c > hi and B[i]["v"] >= VOL_MULT * (vsum / cnt):
            j = _fail_end(B, i, e, hi)
            if j is None:
                return None
            if j >= e and B[e]["c"] > hi:
                return None                         # 突破還在進行中，交給 scan_after 判斷
            i, run = j, 0
            continue
        if c > hi * (1 + OUT_TOL) or c < lo * (1 - OUT_TOL):
            return None
        run = run + 1 if (c > hi or c < lo) else 0
        if run >= OUT_RUN:
            return None
        vsum += B[i]["v"]
        cnt += 1
        i += 1
    return vsum / cnt if cnt else None


def _has_step(B, s, e):
    """區間 [s, e] 內，從第 MIN_BARS 根起，若有連續 STEP_DAYS 日收盤都高於「之前那段」的最高價，
    或都低於之前那段的最低價，就是中途突破／跌破過。"""
    hi = max(B[i]["h"] for i in range(s, s + MIN_BARS))
    lo = min(B[i]["l"] for i in range(s, s + MIN_BARS))
    up = dn = 0
    for k in range(s + MIN_BARS, e + 1):
        c = B[k]["c"]
        up = up + 1 if c > hi * (1 + STEP_TOL) else 0
        dn = dn + 1 if c < lo * (1 - STEP_TOL) else 0
        if up >= STEP_DAYS or dn >= STEP_DAYS:
            return True
        if up == 0: hi = max(hi, B[k]["h"])
        if dn == 0: lo = min(lo, B[k]["l"])
    return False


def _rising_channel(B, s, e, height):
    """沿著上升或下降趨勢線穩定走（漲跌幅大且很貼近一條直線）就不算盤整。"""
    n = e - s + 1
    cs = [B[s + k]["c"] for k in range(n)]
    mx = (n - 1) / 2; my = sum(cs) / n
    sxx = sum((x - mx) ** 2 for x in range(n)) or 1
    k = sum((x - mx) * (y - my) for x, y in enumerate(cs)) / sxx
    ss = sum((y - my) ** 2 for y in cs)
    if not ss:
        return False
    r2 = 1 - sum((y - (my + k * (x - mx))) ** 2 for x, y in enumerate(cs)) / ss
    change = abs(k * (n - 1))
    return change > TREND_RATIO * height or (change / my >= RISE_PCT and r2 >= RISE_R2)


def _amp(B, e, n=60):
    """近 n 日平均每日振幅（最高－最低）／前一日收盤。"""
    a = max(1, e - n + 1)
    v = [(B[i]["h"] - B[i]["l"]) / B[i - 1]["c"] for i in range(a, e + 1) if B[i - 1]["c"] > 0]
    return sum(v) / len(v) if v else 0.0


def _box_in_window(B, a, e):
    max_rng = MAX_RANGE_VOL if _amp(B, e) >= VOL_AMP else MAX_RANGE
    sh = _swings(B, a, e, True)
    sl = _swings(B, a, e, False)
    shs, sls = set(sh), set(sl)
    for s in sorted(shs | sls):
        if e - s + 1 < MIN_BARS:
            break
        prev = B[max(0, s - 20):s]
        if not prev:
            continue
        lower = sum(1 for x in prev if x["c"] < B[s]["c"])
        rising = lower > len(prev) / 2
        if rising and s not in shs:
            continue
        if (not rising) and s not in sls:
            continue
        th = _edge(B, [i for i in sh if s <= i <= e], True)
        tl = _edge(B, [i for i in sl if s <= i <= e], False)
        if not th or not tl:
            continue
        hi, lo = th[0], tl[0]
        if hi <= lo or (hi - lo) / lo > max_rng:
            continue
        if max(B[i]["h"] for i in range(s, e + 1)) > hi * (1 + MAX_WICK) or min(B[i]["l"] for i in range(s, e + 1)) < lo * (1 - MAX_WICK):
            continue                                    # 區間內曾大幅衝出上下緣（漲快跌快），不算盤整
        if _has_step(B, s, e) or _rising_channel(B, s, e, hi - lo):
            continue                                    # 中途已經突破或跌破過一次，舊區間到那裡就結束，不能和新的一段合成一個框
        avg = _closes_ok(B, s, e, hi, lo)
        if avg is None:
            continue
        return {"s": s, "e": e, "hi": hi, "lo": lo,
                "touch_hi": th[1], "touch_lo": tl[1], "avgvol": avg}
    return None


def find_box(B, e):
    for L in WINDOWS:
        a = max(0, e - L + 1)
        if e - a + 1 < MIN_BARS:
            continue
        box = _box_in_window(B, a, e)
        if box:
            return box
    return None


def scan_after(B, box, b, T):
    """box 結束於 b-1，B[b] 為第一根跳出區間的 K。回傳事件 dict。"""
    hi, lo = box["hi"], box["lo"]
    c = B[b]["c"]
    ev = {"b": b, "day": T - b + 1}
    if c > hi:
        sig = B[b]["v"] >= VOL_MULT * box["avgvol"]
        ev.update(dir="up", signal=sig)
        after = [B[i]["c"] for i in range(b + 1, min(b + CONFIRM_DAYS, T) + 1)]
        if any(x <= hi for x in after):
            ev["state"] = "false_breakout"
        elif T >= b + CONFIRM_DAYS:
            ev["state"] = "confirmed"
        else:
            ev["state"] = "confirming"
        run = 0
        for i in range(b, T + 1):
            run = run + 1 if B[i]["c"] <= hi else 0
            if run >= CONFIRM_DAYS and ev["state"] != "false_breakout":
                ev["state"] = "failed"
        if ev["day"] > SIGNAL_LIFE:
            ev["expired"] = True
    elif c < lo:
        ev.update(dir="down", signal=False)
        after = [B[i]["c"] for i in range(b + 1, min(b + CONFIRM_DAYS - 1, T) + 1)]
        run = 1
        for i in range(b + 1, T + 1):
            if B[i]["c"] < lo:
                run += 1
            else:
                break
        if any(x >= lo for x in after):
            ev["state"] = "false_breakdown"
        elif run >= CONFIRM_DAYS:
            ev["state"] = "breakdown_confirmed"           # 連 3 日收在下緣之下＝區間失效
        else:
            ev["state"] = "breakdown_pending"
        if ev["day"] > SIGNAL_LIFE:
            ev["expired"] = True
    else:
        return None
    return ev


def current_box(B, T, lookback=20):
    """回傳 (box, event)。event 為 None 表示價格仍在區間內（整理中）。"""
    box = find_box(B, T)
    if box:
        return box, None
    for e in range(T - 1, max(T - lookback, MIN_BARS) - 1, -1):
        box = find_box(B, e)
        if not box:
            continue
        ev = scan_after(B, box, e + 1, T)
        if ev:
            return box, ev
    return None, None


def classify(B, ma5, ma10, ma20, ma60, T, box, ev):
    """回傳 (state, tags, sub)。state ∈ 轉強/型態好/走弱/盤整。

    sub：走弱的細分（回檔走弱 / 破底走弱），或型態好的「多頭回檔」。
    """
    c = B[T]["c"]
    tags = []

    def above_both(i):
        return bool(ma5[i] and ma10[i] and B[i]["c"] > ma5[i] and B[i]["c"] > ma10[i])

    def below_both(i):
        return bool(ma5[i] and ma10[i] and B[i]["c"] < ma5[i] and B[i]["c"] < ma10[i])

    def bull_at(i):
        j = max(i - 3, 0)
        return bool(ma20[i] is not None and ma20[j] is not None and ma5[i] and ma10[i]
                    and B[i]["c"] > ma5[i] > ma10[i] > ma20[i]
                    and ma20[i] > ma20[j])

    def recent_bull(end, n=10):
        return any(bull_at(i) for i in range(end, max(end - n, 0), -1))

    # 連續收在 5、10 日線之下的天數
    weak_run = 0
    for i in range(T, -1, -1):
        if below_both(i):
            weak_run += 1
        else:
            break
    weak = weak_run >= WEAK_DAYS

    # 波段回檔幅度：近 30 根最高點，往前 60 根內的最低點為波段起點
    seg = range(max(T - 29, 0), T + 1)
    h_idx = max(seg, key=lambda i: B[i]["h"])
    H = B[h_idx]["h"]
    L = min(B[i]["l"] for i in range(max(h_idx - 60, 0), h_idx + 1))
    retrace = (H - c) / (H - L) if H > L else 0.0

    # 站回：剛由「5/10 日線之下」或「多頭回檔」重新站上 5、10 日線（3 個交易日內）
    recovered = False
    if above_both(T):
        r = None
        for i in range(T, max(T - STRONG_WINDOW, 0), -1):
            if above_both(i) and not above_both(i - 1):
                r = i
                break
        if r is not None:
            run = 0
            for j in range(r - 1, -1, -1):
                if below_both(j):
                    run += 1
                else:
                    break
            dipped = bool(ma5[r - 1] and B[r - 1]["c"] < ma5[r - 1]) and recent_bull(r - 1, 12)
            under10 = sum(1 for j in range(max(r - 10, 0), r) if ma10[j] and B[j]["c"] < ma10[j])
            if run >= WEAK_DAYS or under10 >= 3:
                recovered = True
                tags.append("站回5/10日線")
            elif dipped:
                recovered = True
                tags.append("多頭回檔後站回5日線")

    breakout = False
    if ev and ev.get("dir") == "up" and ev.get("signal") and ev["state"] in ("confirming", "confirmed") \
            and ev["day"] <= STRONG_WINDOW and not ev.get("expired"):
        breakout = True
        tags.append("突破第1根" if ev["day"] == 1 else f"突破第{ev['day']}日")
        if ev["state"] == "confirmed":
            tags.append("壓力轉支撐")
    if ev and ev.get("dir") == "up" and not ev.get("signal") and ev.get("state") in ("confirming", "confirmed") and not ev.get("expired"):
        tags.append("無量突破待追蹤")
    if ev and ev.get("state") == "failed":
        tags.append("突破失效")
    if ev and ev.get("state") == "false_breakout":
        tags.append("假突破")

    # 急漲：近 3 個交易日內由近期低點（含 3 天前）反彈 ≥ 20%
    low3 = min(B[i]["l"] for i in range(max(T - 3, 0), T + 1))
    rally = low3 > 0 and c / low3 - 1 >= RALLY_PCT
    if rally:
        tags.append(f"3日急漲{(c / low3 - 1) * 100:.0f}%")
    # 跌破區間：連 3 日收在下緣之下才算（區間失效）；之後只要收盤站回下緣之上就不再算跌破
    bd = bool(ev and ev.get("state") == "breakdown_confirmed" and not ev.get("expired"))
    breakdown = bd and box is not None and c < box["lo"]
    if breakdown:
        tags.append("跌破區間")
    elif bd:
        tags.append("站回區間")

    bull = bull_at(T)
    in_box = box is not None and ev is None
    if in_box and c >= box["hi"] * 0.97:
        tags.append("準備突破")

    # 多頭回檔（觀察）：跌破 5 日線但仍守 10 日線、多頭結構未壞、回檔不到波段一半
    below5_run = 0
    for i in range(T, -1, -1):
        if ma5[i] and B[i]["c"] < ma5[i]:
            below5_run += 1
        else:
            break
    pullback = bool(
        ma5[T] and ma10[T] and ma20[T] and c < ma5[T] and c > ma10[T]
        and ma10[T] > ma20[T] and ma20[T] > ma20[max(T - 5, 0)]
        and retrace <= 0.5 and recent_bull(T - below5_run, 10))

    prior_bull = False
    if weak:
        start = T - weak_run + 1
        k = start - 1
        prior_bull = recent_bull(k, 20) or bool(ma60[k] and B[k]["c"] > ma60[k])

    sub = None
    if breakout or recovered or rally:
        state = "轉強"                              # 突破、站回 5/10 日線、3 日急漲 ≥ 20%：優先於走弱
    elif breakdown:
        state, sub = "走弱", "破底走弱"            # 區間下緣被跌破確認：最差
    elif weak and not in_box and prior_bull:
        state, sub = "走弱", "回檔走弱"            # 強勢多頭回檔後，5/10 日線都守不住
        tags.append(f"連{weak_run}日在5/10日線下")
    elif bull:
        state = "型態好"
    elif pullback:
        state, sub = "型態好", "多頭回檔"          # 還沒走弱，觀察能否站回 5 日線
        tags.append(f"5日線下第{below5_run}天・回檔{retrace * 100:.0f}%")
    elif in_box:
        state = "盤整"
    elif weak or (ma20[T] is not None and c < ma20[T] and ma20[T] < ma20[max(T - 3, 0)]):
        state, sub = "走弱", "破底走弱"            # 沒區間也不是強勢回檔：空頭走勢
        tags.append("空頭排列")
    else:
        state = "盤整"
        tags.append("均線糾結")
    if sub:
        tags.insert(0, sub)
    return state, tags, sub


BULL_REV = {"雙重底", "雙重底（不對稱）", "頭肩底", "V形底", "圓弧底", "下降楔形", "島型反轉底"}
BEAR_REV = {"雙重頂", "頭肩頂", "V形頂", "圓弧頂", "上升楔形", "島型反轉頂"}
BULL_SETUP = {"杯柄", "圓弧底", "雙重底", "雙重底（不對稱）", "頭肩底", "上升三角形", "下降楔形"}


def apply_patterns(state, tags, sub, geo):
    """用幾何形態調整四種型態。
    頂部反轉成立（頸線剛被跌破）→ 走弱；底部反轉/杯柄突破（頸線剛被突破）→ 轉強。"""
    # 「單日島型」只標示、不改變四種型態
    bear = [g for g in geo if g["status"] == "confirmed" and g["dir"] == "bear" and not g["kind"].startswith("單日")]
    bull = [g for g in geo if g["status"] == "confirmed" and g["dir"] == "bull" and not g["kind"].startswith("單日")]
    bear.sort(key=lambda g: g["day"] or 99)
    bull.sort(key=lambda g: g["day"] or 99)
    if bear and (not bull or (bear[0]["day"] or 99) < (bull[0]["day"] or 99)):
        g = bear[0]
        state, sub = "走弱", sub if state == "走弱" and sub == "破底走弱" else "回檔走弱"
        tags = [t for t in tags if t != "多頭回檔"]
        tags.append(f"{g['kind']}跌破" if g["neck"] else g["kind"])
    elif bull:
        g = bull[0]
        if state in ("走弱", "盤整", "型態好") or sub:
            state, sub = "轉強", None
            tags = [t for t in tags if t not in ("破底走弱", "回檔走弱", "空頭排列", "均線糾結")]
        tags.append(f"{g['kind']}突破" if g["neck"] else g["kind"])
    for g in geo:
        if g["status"] == "confirmed" and g["kind"].startswith("單日島型"):
            tags.append(g["kind"])
        if g["status"] == "confirmed" and "島型" in g["kind"] and g.get("volup"):
            tags.append("島型量增確認")
    for g in geo:
        if g["status"] in ("near", "forming") and g["kind"] in BULL_SETUP:
            tags.append(f"{g['kind']}{'接近頸線' if g['status'] == 'near' else '成形中'}")
    setup = any(g["status"] in ("near", "forming") and g["kind"] in ("杯柄", "圓弧底") for g in geo) \
        or "準備突破" in tags
    if state == "盤整" and setup:
        tags.append("蓄勢待發")
    return state, tags, sub
