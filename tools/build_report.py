#!/usr/bin/env python3
"""
えびす旅館 実績＆受注ペーシング レポート生成（クラウド版）

入力:
  --reservations  Google Sheets「予約一覧」の get_values 結果（JSON: {"values":[[...],...]} / 1行目=ヘッダー）
  --history       Google Sheets「実績_履歴」の get_values 結果（JSON）。2024-01〜2025-12 の月次実績（入込状況表から固定）
  --asof          基準日 YYYY-MM-DD（省略時=今日 JST）
  --narrative     任意。Claude が書くコメント JSON（keys: note1, insight1, insight2, bk_note）。無ければ数値から自動生成
  --out-dir       出力先（report.html / index.html / summary.json）
  --password      閲覧パスワード（index.html の暗号化）

定義（旧ローカル版・ねっぱん入込状況表と同じ）:
  宿泊月実績 : 予約（キャンセル除く）を宿泊日ごとに日割り（金額÷泊数, 室数, 人数=大人+子供）して宿泊月に集計
  稼働率     : 室数 ÷ (TOTAL_ROOMS × 月の日数)
  OTB(現在)  : 基準日時点で有効な予約の、将来宿泊月ごとの室数・売上
  OTB前年同期: 基準日の1年前時点で有効だった予約（申込日 ≤ 1年前、かつ その時点で未キャンセル）の、前年同月の室数・売上
  前年最終   : 前年同月の確定実績（履歴タブ or 予約一覧）
  受注日ベース: 申込日で集計。総=全件（後日キャンセル含む）、純=未キャンセル、キャンセル率=キャンセル÷総
  2025年以前の宿泊月実績は履歴タブ（2025-01より前に受注した予約が予約一覧に無いため）、2026-01以降は予約一覧から計算
"""
import argparse, base64, calendar, datetime as dt, hashlib, json, os, re, secrets, sys
from collections import defaultdict

TOTAL_ROOMS = 9
SHEET_FROM = '2026-01'            # この月以降の宿泊月実績は予約一覧から計算（それ以前は履歴タブ）
FY_START_MONTH = 5                # 決算期=4月末
TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'template')

# ───────────────────────── 読み込み ─────────────────────────
def load_values(path):
    with open(path, encoding='utf-8') as f:
        txt = f.read()
    try:
        obj = json.loads(txt)
    except json.JSONDecodeError:
        # ツール結果ファイルに前置きが付いている場合、最初の { から読む
        obj = json.loads(txt[txt.find('{'):])
    vals = obj['values'] if isinstance(obj, dict) else obj
    return vals

def to_date(s):
    if not s:
        return None
    m = re.match(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', str(s))
    return dt.date(int(m[1]), int(m[2]), int(m[3])) if m else None

def num(s):
    try:
        return float(str(s).replace(',', '').replace('円', '')) if s not in ('', None) else 0.0
    except ValueError:
        return 0.0

def load_reservations(path):
    vals = load_values(path)
    hdr = vals[0]
    col = {h: i for i, h in enumerate(hdr)}
    need = ['予約番号', '状態', 'チェックイン', 'チェックアウト', '泊数', '室数', '大人', '子供', '合計金額', '申込日', 'キャンセル日']
    for n in need:
        if n not in col:
            sys.exit(f'予約一覧にヘッダー「{n}」がありません: {hdr}')
    out = []
    for r in vals[1:]:
        if not r or not str(r[0]).strip():
            continue
        g = lambda k: r[col[k]] if col[k] < len(r) else ''
        ci, co = to_date(g('チェックイン')), to_date(g('チェックアウト'))
        n = int(num(g('泊数'))) or ((co - ci).days if ci and co else 0)
        out.append(dict(
            id=str(r[0]).strip(), st=str(g('状態')).strip(), ci=ci, co=co, n=n,
            rooms=int(num(g('室数'))) or 1, ppl=int(num(g('大人'))) + int(num(g('子供'))),
            amt=num(g('合計金額')), app=to_date(g('申込日')), can=to_date(g('キャンセル日')),
        ))
    return out

def load_history(path):
    vals = load_values(path)
    hdr = vals[0]; col = {h: i for i, h in enumerate(hdr)}
    H = {}
    for r in vals[1:]:
        if not r or not r[0]:
            continue
        H[str(r[0])[:7]] = dict(rev=num(r[col['売上']]), rooms=int(num(r[col['室数']])),
                               occ=num(r[col['稼働率']]), ppl=int(num(r[col['人数']])))
    return H

# ───────────────────────── 集計 ─────────────────────────
def ym(d): return d.strftime('%Y-%m')
def add_months(y, m, k):
    t = (y * 12 + m - 1) + k
    return t // 12, t % 12 + 1
def month_days(s):
    y, m = map(int, s.split('-')); return calendar.monthrange(y, m)[1]
def month_range(start, end):
    y, m = map(int, start.split('-')); out = []
    while True:
        s = f'{y}-{m:02d}'; out.append(s)
        if s >= end: break
        y, m = add_months(y, m, 1)
    return out

def is_active(b, asof=None):
    """基準日時点で有効（宿泊する）予約か"""
    if not b['ci'] or not b['co'] or b['n'] <= 0:
        return False
    if asof is None:
        return b['st'] != 'キャンセル'
    if b['app'] and b['app'] > asof:
        return False
    if b['st'] == 'キャンセル':
        # キャンセル日が基準日以前なら無効。キャンセル日不明なら無効扱い
        return bool(b['can'] and b['can'] > asof)
    return True

def stay_by_month(B, asof=None):
    """宿泊月ごとの (売上, 室数, 人数) を日割りで集計"""
    acc = defaultdict(lambda: [0.0, 0, 0])
    for b in B:
        if not is_active(b, asof):
            continue
        per = b['amt'] / b['n']
        for k in range(b['n']):
            key = ym(b['ci'] + dt.timedelta(k))
            a = acc[key]; a[0] += per; a[1] += b['rooms']; a[2] += b['ppl']
    return acc

def booking_by_month(B):
    acc = defaultdict(lambda: dict(cnt=0, amt=0.0, net=0, cancel=0))
    for b in B:
        if not b['app']:
            continue
        a = acc[ym(b['app'])]
        a['cnt'] += 1; a['amt'] += b['amt']
        if b['st'] == 'キャンセル': a['cancel'] += 1
        else: a['net'] += 1
    return acc

def booking_by_week(B, first_monday, last_monday):
    acc = defaultdict(lambda: dict(cnt=0, amt=0.0, net=0))
    for b in B:
        if not b['app']:
            continue
        wk = b['app'] - dt.timedelta(days=b['app'].weekday())
        if wk < first_monday or wk > last_monday:
            continue
        a = acc[wk]; a['cnt'] += 1; a['amt'] += b['amt']
        if b['st'] != 'キャンセル': a['net'] += 1
    return acc

def pct(a, b, nd=1):
    return round(a / b * 100, nd) if b else None

def build(B, H, asof):
    cur_m = ym(asof)
    cy, cm = asof.year, asof.month
    ly, lm = add_months(cy, cm, -1)
    last_done = f'{ly}-{lm:02d}'                      # 直近の確定月（基準日の前月）
    sheet_stay = stay_by_month(B)

    def actual(m):
        """確定実績 (rev, rooms, occ, ppl)。SHEET_FROM 以降は予約一覧、それ以前は履歴"""
        if m < SHEET_FROM:
            h = H.get(m)
            return (int(round(h['rev'])), h['rooms'], h['occ'], h['ppl']) if h else (0, 0, 0, 0)
        a = sheet_stay.get(m, [0, 0, 0])
        occ = round(a[1] / (TOTAL_ROOMS * month_days(m)) * 100, 1)
        return (round(a[0]), a[1], occ, a[2])

    # ── 宿泊月ベース（2025-01 〜 直近確定月）
    labels = month_range('2025-01', last_done)
    rev_cur, rooms_cur, occ_cur, ppl_cur, rev_prev, rooms_prev, occ_prev, ppl_prev = ([] for _ in range(8))
    for m in labels:
        y, mo = map(int, m.split('-'))
        a = actual(m); p = actual(f'{y-1}-{mo:02d}')
        rev_cur.append(a[0]); rooms_cur.append(a[1]); occ_cur.append(a[2]); ppl_cur.append(a[3])
        rev_prev.append(p[0]); rooms_prev.append(p[1]); occ_prev.append(p[2]); ppl_prev.append(p[3])
    rev_yoy = [pct(c, p) if p else None for c, p in zip(rev_cur, rev_prev)]

    # ── 決算期KPI（5月〜4月）
    fy_start_year = cy if cm >= FY_START_MONTH else cy - 1
    def fy_months(start_year, upto=None):
        ms = month_range(f'{start_year}-{FY_START_MONTH:02d}', f'{start_year+1}-{FY_START_MONTH-1:02d}')
        return [m for m in ms if (upto is None or m <= upto)]
    def kpi(ms):
        acts = [actual(m) for m in ms]
        rev = sum(a[0] for a in acts); rooms = sum(a[1] for a in acts); ppl = sum(a[3] for a in acts)
        occ = round(sum(a[2] for a in acts) / len(acts), 1) if acts else 0
        return dict(months=ms, rev=round(rev), rooms=rooms, ppl=ppl, occ=occ,
                    adr=round(rev / rooms) if rooms else 0, pp=round(rev / ppl) if ppl else 0)
    prev_fy = kpi(fy_months(fy_start_year - 1))
    cur_fy_months = fy_months(fy_start_year, upto=last_done)
    cur_fy = kpi(cur_fy_months) if cur_fy_months else None
    # 今期と同じ月数での前期（ADR前期比用）
    prev_fy_same = kpi(fy_months(fy_start_year - 1)[:len(cur_fy_months)]) if cur_fy_months else None

    # ── 受注日ベース（月次 2025-01〜当月、週次）
    bk = booking_by_month(B)
    bk_mon = month_range('2025-01', cur_m)
    bk_cnt = [bk[m]['cnt'] for m in bk_mon]; bk_amt = [round(bk[m]['amt']) for m in bk_mon]
    bk_net = [bk[m]['net'] for m in bk_mon]; bk_cancel = [bk[m]['cancel'] for m in bk_mon]
    bk_aov = [round(a / c) if c else 0 for a, c in zip(bk_amt, bk_cnt)]
    bk_canrate = [pct(x, c) if c else 0.0 for x, c in zip(bk_cancel, bk_cnt)]
    first_monday = dt.date(2024, 12, 30)
    this_monday = asof - dt.timedelta(days=asof.weekday())
    wk = booking_by_week(B, first_monday, this_monday)
    wk_labels = []; d = first_monday
    while d <= this_monday:
        wk_labels.append(d); d += dt.timedelta(7)
    wk_amt = [round(wk[d]['amt']) for d in wk_labels]; wk_cnt = [wk[d]['cnt'] for d in wk_labels]
    wk_net = [wk[d]['net'] for d in wk_labels]
    def ma(xs, n=4):
        return [round(sum(xs[max(0, i-n+1):i+1]) / len(xs[max(0, i-n+1):i+1])) for i in range(len(xs))]
    wk_amt_ma, wk_cnt_ma = ma(wk_amt), ma(wk_cnt)

    # ── 将来OTBペーシング（当月〜12ヶ月）
    p_months = [f'{y}-{m:02d}' for y, m in (add_months(cy, cm, k) for k in range(12))]
    otb_now = stay_by_month(B)                                   # 現在有効
    asof_py = asof.replace(year=asof.year - 1) if not (asof.month == 2 and asof.day == 29) else asof.replace(year=asof.year-1, day=28)
    otb_py = stay_by_month(B, asof_py)                            # 1年前時点で有効
    p_rm_cur, p_sl_cur, p_rm_py, p_sl_py, p_rm_fin, p_sl_fin = ([] for _ in range(6))
    for m in p_months:
        y, mo = map(int, m.split('-')); pm_ = f'{y-1}-{mo:02d}'
        a = otb_now.get(m, [0, 0, 0]); p = otb_py.get(pm_, [0, 0, 0]); f = actual(pm_)
        p_rm_cur.append(a[1]); p_sl_cur.append(round(a[0]))
        p_rm_py.append(p[1]); p_sl_py.append(round(p[0]))
        p_rm_fin.append(f[1]); p_sl_fin.append(f[0])
    p_rm_pace = [pct(c, p) if p else None for c, p in zip(p_rm_cur, p_rm_py)]
    p_sl_pace = [pct(c, p) if p else None for c, p in zip(p_sl_cur, p_sl_py)]
    p_gap_fin = [f - c for f, c in zip(p_sl_fin, p_sl_cur)]

    D = dict(labels=labels, rev_cur=rev_cur, rev_prev=rev_prev, rev_yoy=rev_yoy,
             rooms_cur=rooms_cur, rooms_prev=rooms_prev, occ_cur=occ_cur, occ_prev=occ_prev,
             ppl_cur=ppl_cur, ppl_prev=ppl_prev,
             bk_mon=bk_mon, bk_cnt=bk_cnt, bk_amt=bk_amt, bk_net=bk_net, bk_cancel=bk_cancel,
             bk_aov=bk_aov, bk_canrate=bk_canrate,
             wk_labels=[d.isoformat() for d in wk_labels], wk_amt=wk_amt, wk_cnt=wk_cnt, wk_net=wk_net,
             wk_amt_ma=wk_amt_ma, wk_cnt_ma=wk_cnt_ma,
             p_months=p_months, p_rm_cur=p_rm_cur, p_rm_py=p_rm_py, p_rm_fin=p_rm_fin,
             p_sl_cur=p_sl_cur, p_sl_py=p_sl_py, p_sl_fin=p_sl_fin,
             p_rm_pace=p_rm_pace, p_sl_pace=p_sl_pace, p_gap_fin=p_gap_fin,
             occ_avg=round(sum(occ_cur) / len(occ_cur), 1) if occ_cur else 0)
    S = dict(asof=asof.isoformat(), last_done=last_done, cur_month=cur_m, prev_fy=prev_fy, cur_fy=cur_fy,
             prev_fy_same=prev_fy_same, fy_start_year=fy_start_year, n_reservations=len(B),
             n_active=sum(1 for b in B if b['st'] != 'キャンセル'))
    return D, S

# ───────────────────────── 文章（自動生成の既定値） ─────────────────────────
def yen(v): return '¥' + format(round(v), ',')
def jp_m(m):
    y, mo = m.split('-'); return f'{int(mo)}月' if True else m
def jp_ym(m):
    y, mo = m.split('-'); return f'{y}年{int(mo)}月'

def auto_narrative(D, S):
    ld = S['last_done']; i = D['labels'].index(ld)
    adr = round(D['rev_cur'][i] / D['rooms_cur'][i]) if D['rooms_cur'][i] else 0
    adr_p = round(D['rev_prev'][i] / D['rooms_prev'][i]) if D['rooms_prev'][i] else 0
    pace_txt = '・'.join(f"{jp_m(m)}{p}%" for m, p in zip(D['p_months'], D['p_sl_pace']) if p is not None)
    rm_txt = '・'.join(f"{jp_m(m)}{p}%" for m, p in zip(D['p_months'], D['p_rm_pace']) if p is not None)
    gaps = sorted([(g, m) for g, m, p in zip(D['p_gap_fin'], D['p_months'], D['p_sl_pace']) if p is not None], reverse=True)[:3]
    gap_txt = '・'.join(f"{jp_ym(m)}（{yen(g)}）" for g, m in gaps)
    j = len(D['bk_mon']) - 2  # 直近の確定受注月
    note1 = (f"<b>今回のポイント（基準日 {S['asof'].replace('-', '/')}）：</b>{jp_ym(ld)}が確定。"
             f"{jp_ym(ld)}実績は室数{D['rooms_cur'][i]}室（前年比{pct(D['rooms_cur'][i], D['rooms_prev'][i]) or '-'}%）・"
             f"売上{yen(D['rev_cur'][i])}（{D['rev_yoy'][i]}%）・ADR{yen(adr)}（{pct(adr, adr_p) or '-'}%）・稼働率{D['occ_cur'][i]}%。")
    insight1 = (f"🧭 <b>判定：</b>室数ペースは<b>{rm_txt}</b>。売上ペースは<b>{pace_txt}</b>。<br>"
                f"前年最終比の不足額が大きいのは<b>{gap_txt}</b>。")
    yoy = [(m, v) for m, v in zip(D['labels'], D['rev_yoy']) if m.startswith(ld[:4]) and v is not None]
    yoy_txt = '・'.join(f"{jp_m(m)}{v}%" for m, v in yoy)
    insight2 = (f"📉 {ld[:4]}年の宿泊売上 前年同月比：{yoy_txt}。<br>"
                f"<b>受注日ベースの直近：</b>{jp_ym(D['bk_mon'][j])}の受注は<b>{D['bk_cnt'][j]}件・{yen(D['bk_amt'][j])}</b>"
                f"（平均単価{yen(D['bk_aov'][j])}・キャンセル率{D['bk_canrate'][j]}%）。"
                f"週次受注は直近4週 " + ' → '.join(f"{l[5:].replace('-', '/')}週{c}件・{yen(a)}" for l, c, a in zip(D['wk_labels'][-5:-1], D['wk_cnt'][-5:-1], D['wk_amt'][-5:-1])) + "。")
    bk_note = f"※前年同月比は前年(2024年)の受注データ未取得のため{ld[:4]}年分のみ表示。{jp_ym(S['cur_month'])}は{S['asof'][5:].replace('-', '/')}までの途中値。"
    return dict(note1=note1, insight1=insight1, insight2=insight2, bk_note=bk_note)

# ───────────────────────── HTML ─────────────────────────
def kpi_block(title, k, cls='', notes=None):
    notes = notes or {}
    def c(v, l, s=''):
        return f'<div class="kpi"><div class="v">{v}</div><div class="l">{l}</div>' + (f'<div class="s">{s}</div>' if s else '') + '</div>'
    return (f'<div class="fyrow {cls}"><div class="fyhead">{title}</div>\n<div class="kpis">\n'
            + c(yen(k['rev']), '総売上', notes.get('rev', f"{len(k['months'])}ヶ月"))
            + c(f"{k['occ']}%", '平均客室稼働率', notes.get('occ', ''))
            + c(f"{k['rooms']:,}室", '延べ販売室数') + c(f"{k['ppl']:,}人", '延べ宿泊人数')
            + c(yen(k['adr']), 'ADR(平均室料)', notes.get('adr', '')) + c(yen(k['pp']), '平均一人単価')
            + '\n</div></div>\n')

def render(D, S, N):
    head = open(os.path.join(TEMPLATE_DIR, 'head.html'), encoding='utf-8').read()
    js = open(os.path.join(TEMPLATE_DIR, 'charts.js'), encoding='utf-8').read()
    asof = S['asof'].replace('-', '/'); ld = S['last_done']
    fy = S['fy_start_year']; pf = S['prev_fy']; cf = S['cur_fy']
    title = f"えびす旅館 実績レポート {D['labels'][0][:4]}-{ld[:4]}"
    prev_block = kpi_block(f"前期実績　{fy-1}/{FY_START_MONTH}/1 〜 {fy}/{FY_START_MONTH-1}/30 <span>（決算期=4月末・宿泊月ベース）</span>", pf)
    if cf:
        m0, m1 = cf['months'][0], cf['months'][-1]
        adr_note = f"前期比 {pct(cf['adr'], S['prev_fy_same']['adr'])}%" if S['prev_fy_same'] and S['prev_fy_same']['adr'] else ''
        cur_block = kpi_block(f"今期実績　{fy}/{FY_START_MONTH}/1 〜 {asof}時点 <span>（{jp_m(m0)}〜{jp_m(m1)}すべて確定）</span>", cf, 'cur',
                              dict(rev=f"{len(cf['months'])}ヶ月({jp_m(m0)}〜{jp_m(m1)}確定)", occ=f"{jp_m(m0)}〜{jp_m(m1)}", adr=adr_note))
    else:
        cur_block = ''
    body = f'''<body><div class="wrap">
<header class="head"><h1>えびす旅館　実績＆受注ペーシング レポート</h1>
<div class="sub">対象：{D['labels'][0][:4]}年{int(D['labels'][0][5:])}月〜{jp_ym(ld)}（実績・{jp_m(ld)}確定）＋将来宿泊月の受注残（基準日 {asof}）｜出典：ねっぱん！（予約通知の自動取込）</div></header>
<p class="lead">実績に加え、<b>将来の受注残（OTB）を前年の同じ時点と比較</b>し、ペースの良否と「いつの予約を強化すべきか」を金額つきで示します。</p>
{prev_block}{cur_block}
<h2>1. 将来の受注残ペーシング（先行指標）</h2>
<div class="note">{N['note1']}</div><div class="insight">{N['insight1']}</div><div class="card"><h3>将来宿泊月の売上：OTB(現在) / 前年同期 / 前年最終</h3><div class="chart-box tall"><canvas id="c_pace_amt"></canvas></div></div>
<div class="card"><h3>将来宿泊月の室数：OTB(現在) / 前年同期 / 前年最終</h3><div class="chart-box tall"><canvas id="c_pace_rm"></canvas></div></div>
<div class="card"><h3>将来宿泊月のADR(平均室料)：OTB(現在) vs 前年同期＋前年比（折れ線）</h3><div class="chart-box"><canvas id="c_pace_adr"></canvas></div><div style="font-size:11.5px;color:#888;margin-top:6px">※ADR=売上÷室数。前年同期=0の遠い月は表示なし。</div></div>
<div class="card"><h3>受注残ペーシング 一覧</h3><div class="scroll"><table id="t_pace"></table></div>
<div style="font-size:11.5px;color:#888;margin-top:6px">※前年同期=0の遠い月は予約受付期間がまだ開いておらず「時期尚早」。OTB売上はOTA表示・手数料控除前。</div></div>

<h2>2. 早期察知の指標</h2>
<div class="insight">{N['insight2']}</div><div class="card"><h3>売上 前年同月比（宿泊月ベース・%）　90%割れは要注意</h3><div class="chart-box"><canvas id="c_yoy"></canvas></div></div>
<div class="grid2">
<div class="card"><h3>週次 受注金額と4週移動平均</h3><div class="chart-box"><canvas id="c_wkma"></canvas></div></div>
<div class="card"><h3>月次 平均単価とキャンセル率（受注日ベース）</h3><div class="chart-box"><canvas id="c_aov"></canvas></div></div>
</div>

<h2>3. 宿泊月ベース（実績）</h2>
<div class="card"><h3>売上推移（円）と前年同月比（％・折れ線）</h3><div class="chart-box"><canvas id="c_rev"></canvas></div></div>
<div class="grid2">
<div class="card"><h3>販売室数・宿泊人数</h3><div class="chart-box"><canvas id="c_rp"></canvas></div></div>
<div class="card"><h3>客室稼働率（当年 vs 前年）</h3><div class="chart-box"><canvas id="c_occ"></canvas></div></div></div>
<div class="card"><h3>ADR(平均室料) 月別推移と前年同月比（％・折れ線）</h3><div class="chart-box"><canvas id="c_adr2"></canvas></div></div>
<div class="card"><h3>明細表</h3><div class="scroll"><table id="t_stay"></table></div></div>

<h2>4. 受注日（申込日）ベース</h2>
<div class="note">受注日ベース＝予約が申し込まれた日。後日キャンセルも申込日に計上。金額はOTA表示。総=全予約区分、純=予約+変更。</div>
<div class="card"><h3>月次：受注金額と前年同月比（％・折れ線）</h3><div class="chart-box"><canvas id="c_bkmon"></canvas></div><div style="font-size:11.5px;color:#888;margin-top:6px">{N['bk_note']}</div></div>

<footer><span class="pill">将来OTB：予約一覧から基準日時点／前年同時点を再構成</span><span class="pill">受注：予約一覧 {S['n_reservations']:,}件（ねっぱん通知メール自動取込・予約番号upsert）</span><br>受注残＝基準日時点の予約済み。{jp_ym(ld)}は確定・{jp_ym(S['cur_month'])}は進行中。far月は予約受付期間外。{SHEET_FROM[:4]}年より前の宿泊月実績はねっぱん入込状況表の値。作成：{S['asof']}</footer>
</div>
<script>
const D={json.dumps(D, ensure_ascii=False)};
{js}
</script></body></html>'''
    return head.replace('{{TITLE}}', title) + body

def encrypt(html, password, iterations=250000):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    salt, iv = secrets.token_bytes(16), secrets.token_bytes(12)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations, 32)
    ct = AESGCM(key).encrypt(iv, html.encode('utf-8'), None)
    enc = dict(salt=base64.b64encode(salt).decode(), iv=base64.b64encode(iv).decode(), iter=iterations,
               ct=base64.b64encode(ct).decode())
    lock = open(os.path.join(TEMPLATE_DIR, 'lock.html'), encoding='utf-8').read()
    return lock.replace('{{ENC}}', json.dumps(enc))

# ───────────────────────── main ─────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--reservations', required=True)
    ap.add_argument('--history', required=True)
    ap.add_argument('--asof')
    ap.add_argument('--narrative')
    ap.add_argument('--out-dir', default='.')
    ap.add_argument('--password', required=True)
    ap.add_argument('--summary-only', action='store_true', help='summary.json だけ出す（コメント執筆用）')
    a = ap.parse_args()
    asof = dt.date.fromisoformat(a.asof) if a.asof else (dt.datetime.utcnow() + dt.timedelta(hours=9)).date()
    B = load_reservations(a.reservations); H = load_history(a.history)
    D, S = build(B, H, asof)
    os.makedirs(a.out_dir, exist_ok=True)
    N = auto_narrative(D, S)
    with open(os.path.join(a.out_dir, 'summary.json'), 'w', encoding='utf-8') as f:
        json.dump(dict(S=S, D=D, auto_narrative=N), f, ensure_ascii=False, indent=1)
    if a.summary_only:
        print('summary.json を出力しました'); return
    if a.narrative and os.path.exists(a.narrative):
        with open(a.narrative, encoding='utf-8') as f:
            N.update({k: v for k, v in json.load(f).items() if v})
    html = render(D, S, N)
    with open(os.path.join(a.out_dir, 'report.html'), 'w', encoding='utf-8') as f:
        f.write(html)
    with open(os.path.join(a.out_dir, 'index.html'), 'w', encoding='utf-8') as f:
        f.write(encrypt(html, a.password))
    print(f"OK asof={S['asof']} last_done={S['last_done']} reservations={S['n_reservations']} → report.html / index.html")

if __name__ == '__main__':
    main()
