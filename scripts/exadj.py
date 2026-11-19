"""上市股除權息還原（11/19 Opus 審查：上市官方日資料沒有「次日參考價」，除權息日到週日之間漲跌幅、型態、指標都用沒還原的價格算）。
做法：證交所日資料有「收盤」與「漲跌價差」，昨日參考價＝收盤－漲跌價差；若和我們存的昨收差 >0.04%，就是今天除權息（或減資、分割），
係數 k＝參考價／昨收，直接寫進 adjust.csv（和上櫃、盤中算法同一個定義）。
防誤判：漲跌價差剛好 0.0 但收盤跟昨收差很多的（資料異常），只有在證交所「除權息預告表」有列才採用。"""


def twse_adjust(rows, prev_close, d, exdate_codes=(), have=()):
    """rows＝證交所 STOCK_DAY_ALL 列（dict：Code、ClosingPrice、Change）；prev_close＝{代號: (日期, 收盤)}；
    d＝這批資料的日期（YYYY-MM-DD）；exdate_codes＝預告表裡除權息日＝d 的代號；have＝已有 (代號, 日期)。回傳 [[代號, d, k], ...]"""
    out = []
    ex = set(exdate_codes)
    for r in rows:
        c = r.get("Code", "")
        if len(c) != 4 or not c.isdigit() or c not in prev_close or (c, d) in have:
            continue
        pd, pc = prev_close[c]
        if pd >= d or pc <= 0:
            continue
        try:
            cl = float(str(r["ClosingPrice"]).replace(",", "")); ch = float(str(r["Change"]).replace(",", ""))
        except (ValueError, KeyError):
            continue
        if cl <= 0:
            continue
        ref = cl - ch
        if ref <= 0 or abs(ref / pc - 1) <= 4e-4:
            continue
        if ch == 0 and c not in ex:
            continue
        out.append([c, d, round(ref / pc, 6)])
    return out
