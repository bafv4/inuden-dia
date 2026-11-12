# 発車標（page/board.html）のLEDの字の表を作る・読む
#
# 表は page/ledfont16.txt（3色LED・縦16点）と page/ledfont24.txt（フルカラーLED・縦24点）。盤面はこの表の点だけで描く。
# 書き方（手で直してよい）：
#   @ U+6771 東          ← 字の見出し。U+ のあとが字の番号（これで字を決める）、その次は見やすいように字そのもの
#   ....#...........     ← 縦の点数ぶんの行。# が光る点、. が消えている点。行の長さ＝その字の送り幅（字ごとに違ってよい）
#   見出しの末尾に「大」があれば、時刻・番線の大きい数字。「手」があれば手で直した字（作り直しても上書きしない）。
#
# 作り方（data で）: PYTHONPATH=../src python ../src/ledfont.py cyc3_375_720_135_300_855_c.pkl [--redo]
#   board.py でページを書き出し → 画面を出さない Edge でページを「字の表を作る」モード（board.html?ledgen=ポート）で開く
#   → ページが盤面に出る字をすべて洗い出し、点にして送ってくる
#   → ビットマップ字体（fonts/ の BDF。下の BDF）に入っている字は字体の点に置き換える
#   → 表にない字だけを足す（--redo なら「手」のない字をすべて作り直す）→ もう一度 board.py で書き出す。
#   字体：縦16点＝東雲16（漢字・かな）・Helvetica 14 75dpi（英数）・Helvetica 12 100dpi（大きい数字。14は画が2点で漢字より太く見えた）、
#         縦24点＝縁架ドットゴシック24（漢字・かな。ないものはあゆ20ゴシックを右へ1点太らせて）・Helvetica 18 100dpi（英数・大きい数字）。使用条件は fonts/ の各フォルダの LICENSE・COPYING。
#   字体に入っていない字は、ページがフォント（漢字・かなは Noto Sans JP 300、英数は Roboto Condensed 400）を細線化して作った点を使う
#   （board_tmpl.html の ledGlyph）。
import os, sys, re, json, subprocess, tempfile, threading, time, http.server

SIZES = (16, 24)
HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "..", "page")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
HEAD = """# 犬電 発車標 LEDの字（縦{n}点・{name}）。盤面はこの表の点だけで描く。
# 「@ U+番号 字」の下に{n}行。# が光る点、. が消えている点。行の長さ＝送り幅。
# 見出しの末尾の「大」は時刻・番線の大きい数字、「手」は手で直した字（src/ledfont.py で作り直しても上書きしない）。
# 作り方・直し方は src/ledfont.py の先頭を見る。
"""
NAME = {16: "3色LED", 24: "フルカラーLED"}


def load(path, n):
    """表を読む → {(種類 'n'|'b', 字の番号): {"rows": [...], "w": 幅, "hand": bool}}"""
    out = {}
    if not os.path.exists(path): return out
    cur = None
    for ln, line in enumerate(open(path, encoding="utf-8"), 1):
        line = line.rstrip("\n")
        if not line or line.startswith("#") and not re.fullmatch(r"[#.]+", line): continue
        if line.startswith("@"):
            tk = line.split()
            cp = int(tk[1][2:], 16)
            v = "b" if "大" in tk[3:] else "n"
            cur = out[(v, cp)] = {"rows": [], "hand": "手" in tk[3:]}
            continue
        if cur is None or not re.fullmatch(r"[#.]+", line):
            raise SystemExit(f"{path}:{ln} 読めない行: {line!r}")
        cur["rows"].append(line)
    for (v, cp), g in out.items():
        if len(g["rows"]) != n or len({len(r) for r in g["rows"]}) != 1:
            raise SystemExit(f"{path}: U+{cp:04X} {chr(cp)!r} の行数・行の長さがそろっていない（縦{n}行・同じ長さ）")
        g["w"] = len(g["rows"][0])
    return out


def save(path, n, tb):
    def disp(cp):
        c = chr(cp)
        return {" ": "（空白）", "\u3000": "（全角空白）"}.get(c, c)
    L = [HEAD.format(n=n, name=NAME[n])]
    for (v, cp) in sorted(tb, key=lambda k: (k[0] == "b", k[1])):
        g = tb[(v, cp)]
        flags = (" 大" if v == "b" else "") + (" 手" if g.get("hand") else "")
        L.append(f"@ U+{cp:04X} {disp(cp)}{flags}\n" + "\n".join(g["rows"]) + "\n")
    open(path, "w", encoding="utf-8").write("\n".join(L))


# ---- 点の字体（fonts/ に置く BDF か、点の形の輪郭でできた TrueType。LED表示器用の点の字をそのまま使う）
# 字の種類ごとに字体を決める：cjk＝漢字・かな・全角の記号、lat＝英数（半角）、big＝時刻・番線の大きい数字。
# 並べた字体は前のものを先に使う（前の字体に入っていない字・空の字だけ次の字体から取る）。
# どの字体にもない字は、ページがフォントから作った点（board_tmpl.html の ledGlyph）を使う。
FONTS = os.path.join(HERE, "..", "fonts")
BDF = {16: {"cjk": "shinonome/shnmk16.bdf",        # 東雲フォント 16点ゴシック（Public Domain）
            "lat": "adobe-75dpi/helvR14.bdf",      # X11 の Helvetica 14（75dpi。字ごとに幅が違う）
            "big": "adobe-100dpi/helvR12.bdf"},    # 同 12（100dpi。数字の高さ12点・画は1点で東雲16の漢字と同じ太さ）
       24: {"cjk": ["enka-dot-gothic-24/EnkaDotGothic24.ttf",   # 縁架ドットゴシック24（OFL 1.1。漢字は1269字だけ）
                    "ayu/k20gm.bdf"],              # あゆ 20点ゴシック（Public Domain。縁架にない字。縦24点の真ん中に置く）
            "lat": "adobe-100dpi/helvR18.bdf",     # Helvetica 18（100dpi）
            "big": "adobe-100dpi/helvR18.bdf"}}
BOLD = {"ayu/k20gm.bdf"}                           # 右へ1点太らせる（光る点の右隣も光らせる。幅は1点ふえる）。線が1点で細すぎるので


def read_bdf(path):
    """BDF → ({字: (送り幅, (幅, 高さ, 左のずれ, 下のずれ), [行の 0/1])}, FONT_ASCENT, FONT_DESCENT)"""
    out = {}; reg = ""; asc = dsc = 0
    lines = open(path, encoding="latin-1").read().split("\n"); i = 0
    while i < len(lines):
        L = lines[i].strip()
        if L.startswith("CHARSET_REGISTRY"): reg = L.split('"')[1]
        elif L.startswith("FONT_ASCENT"): asc = int(L.split()[1])
        elif L.startswith("FONT_DESCENT"): dsc = int(L.split()[1])
        elif L.startswith("STARTCHAR"):
            enc = dw = bb = None; rows = []
            while True:
                i += 1; L = lines[i].strip()
                if L.startswith("ENCODING"): enc = int(L.split()[1])
                elif L.startswith("DWIDTH"): dw = int(L.split()[1])
                elif L.startswith("BBX"): bb = tuple(int(v) for v in L.split()[1:5])
                elif L == "BITMAP":
                    while True:
                        i += 1; L = lines[i].strip()
                        if L == "ENDCHAR": break
                        rows.append(bin(int(L, 16))[2:].zfill(len(L) * 4)[:bb[0]])
                    break
            ch = None
            if enc is None or enc < 0: pass
            elif reg.startswith("JISX0208"):                         # JIS の区点 → EUC-JP として読む
                try: ch = bytes([(enc >> 8) | 0x80, (enc & 0xFF) | 0x80]).decode("euc_jp")
                except UnicodeDecodeError: ch = None
            else: ch = chr(enc)                                      # ISO8859-1
            if ch: out[ch] = (dw, bb, rows)
        i += 1
    return out, asc, dsc


def read_ttf(path, n):
    """点の字の TrueType（1点＝1em/n の正方形の輪郭でできたもの）→ read_bdf と同じ形。
    点の中心が輪郭の内側（巻き数が0でない）なら光らせる。複合グリフ（ほかの字を組み合わせた字）は読まない"""
    import struct
    b = open(path, "rb").read()
    U = lambda f, o: struct.unpack_from(">" + f, b, o)
    T = {}
    for i in range(U("H", 4)[0]):
        tag, _, off, ln = U("4sIII", 12 + 16 * i); T[tag.decode("latin-1")] = off
    upem = U("H", T["head"] + 18)[0]; lfmt = U("h", T["head"] + 50)[0]
    asc, dsc = U("hh", T["hhea"] + 4); nhm = U("H", T["hhea"] + 34)[0]
    ng = U("H", T["maxp"] + 4)[0]
    d = upem / n
    if d != int(d): raise SystemExit(f"{path}: 1点の大きさが割り切れない（{upem}/{n}）")
    loca = [U("I", T["loca"] + 4 * i)[0] if lfmt else U("H", T["loca"] + 2 * i)[0] * 2 for i in range(ng + 1)]
    adv = lambda gi: U("H", T["hmtx"] + 4 * min(gi, nhm - 1))[0]
    cmap = {}                                                        # 字の番号 → グリフ
    for i in range(U("H", T["cmap"] + 2)[0]):
        pid, eid, off = U("HHI", T["cmap"] + 4 + 8 * i); o = T["cmap"] + off; fmt = U("H", o)[0]
        if fmt == 12:
            for k in range(U("I", o + 12)[0]):
                s, e, g0 = U("III", o + 16 + 12 * k)
                for c in range(s, e + 1): cmap.setdefault(c, g0 + c - s)
        elif fmt == 4:
            sc = U("H", o + 6)[0] // 2; eo = o + 14; so = eo + 2 * sc + 2; do = so + 2 * sc; ro = do + 2 * sc
            for k in range(sc):
                e, s, dl, ro_ = U("H", eo + 2 * k)[0], U("H", so + 2 * k)[0], U("h", do + 2 * k)[0], U("H", ro + 2 * k)[0]
                for c in range(s, e + 1):
                    if c == 0xFFFF: continue
                    if ro_ == 0: g = (c + dl) & 0xFFFF
                    else:
                        g = U("H", ro + 2 * k + ro_ + 2 * (c - s))[0]
                        if g: g = (g + dl) & 0xFFFF
                    if g: cmap.setdefault(c, g)
    def contours(gi):
        o = T["glyf"] + loca[gi]
        if loca[gi + 1] == loca[gi]: return []
        nc = U("h", o)[0]
        if nc < 0: return None
        ends = [U("H", o + 10 + 2 * k)[0] for k in range(nc)]; npt = ends[-1] + 1
        p = o + 10 + 2 * nc; p += 2 + U("H", p)[0]
        fl = []
        while len(fl) < npt:
            f = b[p]; p += 1; fl.append(f)
            if f & 8: r = b[p]; p += 1; fl.extend([f] * r)
        def coords(short, same):
            nonlocal p; v = 0; out = []
            for f in fl:
                if f & short: dv = b[p]; p += 1; v += dv if f & same else -dv
                elif not f & same: v += U("h", p)[0]; p += 2
                out.append(v)
            return out
        xs = coords(2, 16); ys = coords(4, 32)
        cs = []; s = 0
        for e in ends: cs.append(list(zip(xs[s:e + 1], ys[s:e + 1]))); s = e + 1
        return cs
    out = {}; skip = 0
    top = asc                                                        # 1行目の上の縁（em の単位）
    for cp, gi in cmap.items():
        cs = contours(gi)
        if cs is None: skip += 1; continue
        w = round(adv(gi) / d)
        rows = []
        for j in range(n):
            py = top - (j + .5) * d; r = ""
            for i in range(w):
                px = (i + .5) * d; wn = 0
                for c in cs:
                    for k in range(len(c)):
                        (x0, y0), (x1, y1) = c[k], c[(k + 1) % len(c)]
                        if y0 <= py < y1 and (x1 - x0) * (py - y0) - (px - x0) * (y1 - y0) > 0: wn += 1
                        elif y1 <= py < y0 and (x1 - x0) * (py - y0) - (px - x0) * (y1 - y0) < 0: wn -= 1
                r += "1" if wn else "0"
            rows.append(r)
        out[chr(cp)] = (w, (w, n, 0, -round(-dsc / d) if dsc < 0 else 0), rows)
    if skip: print(f"  {os.path.basename(path)}: 複合グリフ {skip} 字は読まなかった")
    return out, round(asc / d), round(-dsc / d)


def bdf_rows(g, N, base, width=None, bold=False):
    """字を縦 N 点の行へ置く。base＝ベースラインの位置（上から何点目の下の縁か）。左にはみ出す字は右へ寄せる"""
    dw, (w, h, xo, yo), rows = g
    sh = max(0, -xo)
    W = width or max(dw + sh, xo + sh + w, 1) + (1 if bold else 0)
    grid = [["."] * W for _ in range(N)]
    for r, bits in enumerate(rows):
        y = base - (yo + h) + r
        if 0 <= y < N:
            for c, b in enumerate(bits):
                x = xo + sh + c
                if b == "1" and 0 <= x < W:
                    grid[y][x] = "#"
                    if bold and x + 1 < W: grid[y][x + 1] = "#"
    return ["".join(r) for r in grid]


def from_bdf(n):
    """縦 n 点の盤面に使う BDF の字 → {('n'|'b', 字の番号): {"rows", "w", "hand": False}}"""
    out = {}; src = {}
    rd = lambda p: read_ttf(os.path.join(FONTS, p), n) if p.endswith(".ttf") else read_bdf(os.path.join(FONTS, p))
    fs = {k: rd(p) for k, p in BDF[n].items() if k != "cjk"}
    def mid(gl, ref):                                                # 基準の字の上端〜下端を縦の真ん中に置くベースライン
        top = max(gl[c][1][1] + gl[c][1][3] for c in ref if c in gl)
        bot = min(gl[c][1][3] for c in ref if c in gl)
        return (n - (top - bot)) // 2 + top
    cj = BDF[n]["cjk"]
    for p in reversed(cj if isinstance(cj, list) else [cj]):       # 後の字体から入れて、前の字体で上書きする
        gl, asc, dsc = rd(p); base = asc + (n - asc - dsc) // 2
        for ch, g in gl.items():
            if ord(ch) < 0x80: continue
            if ch not in " 　" and "1" not in "".join(g[2]): continue        # 空の字（字体に入っていない字）は使わない
            out[("n", ord(ch))] = bdf_rows(g, n, base, bold=p in BOLD); src[("n", ord(ch))] = p
    gl, _, _ = fs["lat"]; base = mid(gl, "Hgjpqy")
    for ch, g in gl.items(): out[("n", ord(ch))] = bdf_rows(g, n, base)
    gl, _, _ = fs["big"]; base = mid(gl, "0123456789"); w0 = gl["0"][0]
    for ch in "0123456789:":
        if ch in gl: out[("b", ord(ch))] = bdf_rows(gl[ch], n, base, w0 if ch.isdigit() else None)
    return {k: {"rows": r, "w": len(r[0]), "hand": False, "src": src.get(k)} for k, r in out.items()}


def tohex(rows):
    """点の並び → 1行ずつ4点を16進1文字にしたもの（幅を4の倍数に切り上げ）"""
    out = []
    for r in rows:
        r = r + "." * (-len(r) % 4)
        out.extend("%X" % int(r[i:i + 4].replace("#", "1").replace(".", "0"), 2) for i in range(0, len(r), 4))
    return "".join(out)


def generate(port=8779, timeout=300):
    """画面を出さない Edge でページを開き、送られてくる点の並びを受け取る"""
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            got["b"] = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
            self.send_response(200); self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers()

        def log_message(self, *a): pass

    srv = None
    for p in range(port, port + 10):                 # 使っているポートは避ける
        try: srv = http.server.HTTPServer(("127.0.0.1", p), H); port = p; break
        except OSError: continue
    if srv is None: raise SystemExit("受け口のポートが空いていない")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = "file:///" + os.path.abspath(os.path.join(PAGE, "board.html")).replace("\\", "/") + f"?ledgen={port}"
    prof = tempfile.mkdtemp(prefix="ledfont_edge_")
    pr = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--user-data-dir=" + prof, url],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    try:
        while "b" not in got and time.time() - t0 < timeout: time.sleep(0.3)
    finally:
        pr.kill(); srv.shutdown()
    if "b" not in got: raise SystemExit("ページから字が届かなかった（時間切れ）")
    res = {n: {} for n in SIZES}
    for line in got["b"].split("\n"):
        n, v, cp, w, rows = line.split("\t")
        res[int(n)][(v, int(cp, 16))] = {"rows": rows.split("/"), "w": int(w), "hand": False}
    print(f"ページから届いた字 {sum(len(x) for x in res.values())}（{time.time() - t0:.0f}秒）")
    return res


def run_board(argv):
    env = dict(os.environ, PYTHONPATH=HERE, PYTHONIOENCODING="utf-8")
    r = subprocess.run([sys.executable, os.path.join(HERE, "board.py")] + argv, env=env, capture_output=True, text=True, encoding="utf-8")
    if r.returncode: print(r.stdout, r.stderr); raise SystemExit("board.py が失敗した")
    for line in r.stdout.splitlines():
        if line.startswith(("LEDの字", "書き出し")): print("  board.py:", line)


if __name__ == "__main__":
    redo = "--redo" in sys.argv
    argv = [a for a in sys.argv[1:] if a != "--redo"]
    run_board(argv)                                   # 字を洗い出すのは最新のページで
    new = generate()
    for n in SIZES:                                   # 字体に入っている字は字体の点に置き換える
        bd = from_bdf(n); rest = []
        for k in new[n]:
            if k in bd: new[n][k] = bd[k]
            else: rest.append(chr(k[1]) + ("(大)" if k[0] == "b" else ""))
        print(f"縦{n}点：字体から {len(new[n]) - len(rest)} 字・フォントから作った字 {len(rest)}", "".join(rest))
        cj = BDF[n]["cjk"]
        if isinstance(cj, list):
            for p in cj[1:]:
                sub = "".join(chr(k[1]) for k in new[n] if new[n][k].get("src") == p)
                if sub: print(f"  {cj[0]} になく {p} から取った字：{sub}（手で直すなら表で「手」を付ける）")
    for n in SIZES:
        path = os.path.join(PAGE, f"ledfont{n}.txt")
        old = load(path, n); tb = dict(old); add = upd = 0
        for k, g in new[n].items():
            if k not in old: tb[k] = g; add += 1
            elif redo and not old[k].get("hand") and old[k]["rows"] != g["rows"]: tb[k] = g; upd += 1
        save(path, n, tb)
        print(f"縦{n}点：表 {len(tb)} 字（足した {add}・作り直した {upd}・手で直した字 {sum(1 for g in tb.values() if g.get('hand'))}）→ {os.path.relpath(path)}")
    run_board(argv)
