# 朝ダイヤを画面上で手直しするための小さなサーバー。列車を横にずらす・停車を延ばす・徐行させる操作を受けて、
# 時刻の計算と競合の判定は既存のプログラム（sched / ops / morning）でやり直して返す。OR-Tools は要らない。
# 使い方（どのフォルダからでも）:
#   python src/editor.py                         … 既定の案（下の DEFAULT）を開く
#   python src/editor.py "ラベル=extras_xxx.pkl" …   … data にある pickle（extras.pkl と同じ形）を指定して開く
#   → ブラウザで http://127.0.0.1:8765/ を開く。止めるときは Ctrl+C。
# 環境変数: PORT（既定 8765） PATTERN（日中パターンの pickle。既定は採用案）
# 保存ボタンは data/extras_手直し_<名前>.pkl に書く（ほかのファイルは上書きしない）。
import sys, os, json, pickle, re, threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "..", "data"); PAGE = os.path.join(HERE, "..", "page")
os.chdir(DATA); sys.path.insert(0, HERE)
ARGS = [a for a in sys.argv[1:] if "=" in a]
PORT = int(os.environ.get("PORT", "8765")); PK = os.environ.get("PATTERN", "cyc3_375_720_135_300_855_c.pkl")
sys.argv = ["compare_extras.py", PK]
import compare_extras as CE
from morning_run import *
import net
DEFAULT = [("案3 待ち優先・既存は不変", "extras_案3_待ち最小.pkl"), ("案6 待ち優先・既存も作り直し", "extras_案6_待避作り直し_待ち優先.pkl"),
           ("案7 間隔優先・既存は不変", "extras_案7_間隔優先_既存不変.pkl"), ("案8 間隔優先・既存も作り直し", "extras_案8_間隔優先_待避作り直し.pkl")]
LOCK = threading.Lock()
def state_of(t): return (t.dep0, dict(t.hold), dict(t.slow))
class Plan:
    def __init__(s, label, fn):
        s.label, s.file = label, fn; s.tr = pickle.load(open(fn, "rb"))[0]; s.hist = []
        for t in s.tr:
            if getattr(t, "slow", None) is None: t.slow = {}       # 古い pickle の列車
            t.compute(); t.orig = state_of(t); t.edited = False
    def json(s):
        d = CE.summ(s.label, s.file, s.tr)
        d["trains"] = [o for _, o in d.pop("dia")]
        for o in d["trains"]:
            t = s.tr[o["i"]]; o["dsh"] = t.dep0 - t.orig[0]       # 元からの発車のずれ
        d["nhist"] = len(s.hist); d["nedit"] = sum(1 for t in s.tr if t.edited)
        return d
    def set(s, t, st):
        t.dep0, t.hold, t.slow = st[0], dict(st[1]), dict(st[2]); t.edited = state_of(t) != t.orig; t.compute()
    def edit(s, i, shift=0, hold=None, slow=None):
        t = s.tr[i]; old = state_of(t); h = dict(t.hold); sl = dict(t.slow)
        for x, v in (hold or {}).items():        # 停車を延ばす：途中の停車駅だけ
            if x in t.route and x not in (t.o, t.d) and t.is_stop(x):
                v = max(0, int(v) // 15 * 15)
                if v: h[x] = v
                else: h.pop(x, None)
        for x, v in (slow or {}).items():        # 徐行：その駅へ着く手前の1駅間
            if x in t.route[1:]:
                v = max(0, int(v) // 15 * 15)
                if v: sl[x] = v
                else: sl.pop(x, None)
        new = (t.dep0 + int(shift) // 15 * 15, h, sl)
        if new != old: s.hist.append((i, old)); s.set(t, new)
    def undo(s):
        if s.hist: i, old = s.hist.pop(); s.set(s.tr[i], old)
    def reset(s):
        for t in s.tr:
            if t.edited: s.set(t, t.orig)
        s.hist = []
    def save(s, name):
        name = re.sub(r"[^\w\-ぁ-んァ-ヶ一-龠ー]", "_", name.strip())[:40] or "無題"
        fn = f"extras_手直し_{name}.pkl"
        pickle.dump((s.tr, [], [t for t in s.tr if getattr(t, "extra", False)]), open(fn, "wb"))
        return fn
PLANS = [Plan(*a.split("=", 1)) for a in ARGS] or [Plan(l, f) for l, f in DEFAULT if os.path.exists(f)]
def page():
    D = {"pats": [p.json() for p in PLANS], "t0": CE.DW[0], "t1": CE.DW[1], "single": [list(x) for x in net.SINGLE],
         "main": [[s, k, s in CE.MAJ_M] for s, k in net.MAIN], "hasu": [[s, k, s in CE.MAJ_H] for s, k in net.HASU]}
    tmpl = open(os.path.join(PAGE, "editor_tmpl.html"), encoding="utf-8").read()
    return tmpl.replace("__DATA__", json.dumps(D, ensure_ascii=False).replace("</", "<\\/"))
class H(BaseHTTPRequestHandler):
    def send(s, code, body, ctype="application/json; charset=utf-8"):
        b = body.encode("utf-8"); s.send_response(code); s.send_header("Content-Type", ctype); s.send_header("Content-Length", str(len(b)))
        s.send_header("Cache-Control", "no-store"); s.end_headers(); s.wfile.write(b)
    def do_GET(s):
        if s.path.split("?")[0] != "/": return s.send(404, "{}")
        with LOCK: s.send(200, page(), "text/html; charset=utf-8")
    def do_POST(s):
        try:
            q = json.loads(s.rfile.read(int(s.headers.get("Content-Length", "0"))) or b"{}"); p = PLANS[int(q.get("p", 0))]; out = {}
            with LOCK:
                if s.path == "/api/edit": p.edit(int(q["i"]), q.get("shift", 0), q.get("hold"), q.get("slow"))
                elif s.path == "/api/undo": p.undo()
                elif s.path == "/api/reset": p.reset()
                elif s.path == "/api/save": out["saved"] = p.save(str(q.get("name", "")))
                else: return s.send(404, "{}")
                out["pat"] = p.json()
            s.send(200, json.dumps(out, ensure_ascii=False))
        except Exception as e:
            s.send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))
    def log_message(s, *a): pass
if __name__ == "__main__":
    print(f"開いた案: {[p.label for p in PLANS]}\nブラウザで http://127.0.0.1:{PORT}/ を開いてください（止めるときは Ctrl+C）", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
