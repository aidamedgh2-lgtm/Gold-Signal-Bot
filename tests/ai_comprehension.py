"""Controlled visual comprehension test for the PDF strategy."""
import io, json, math, os
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from services.gemini_http import generate_json

MODEL = os.environ.get("GEMINI_VISION_MODEL", "gemini-3.5-flash-lite")
OUT = Path("ai_comprehension_results")
OUT.mkdir(exist_ok=True)
RULES = """
PDF pages 3-4: sideways/choppy/oscillating movement scores 0 and is avoided;
diagonal directional movement scores 1 and is commonly corrective;
vertical/rocket-like strong impulse scores 2 and is the preferred movement.
These are three distinct visual classes: diagonal is not sideways.
User's project clarification: a diagonal higher-timeframe move is provisional,
not automatically rejected. It is confirmed only by at least one lower timeframe
showing a sharp impulse in the same direction and approximately the same price
area. A lower-timeframe diagonal does not confirm it. Sideways is rejected.
Exact candle timing alignment is not required. Do not invent ATR/OHLC thresholds.
"""

def path(kind, base=100):
    return [base + (0.65*math.sin(i*1.45)+0.25*math.sin(i*2.8) if kind=="sideways"
            else 0.22*i+0.12*math.sin(i*1.2) if kind=="diagonal"
            else (0 if i<32 else (i-31)*1.7)) for i in range(42)]

def draw(ax, kind, base=100, title=""):
    c = path(kind, base); o = [c[0]]+c[:-1]
    for i,(a,b) in enumerate(zip(o,c)):
        ax.vlines(i,min(a,b)-.1,max(a,b)+.1,linewidth=1)
        ax.add_patch(Rectangle((i-.28,min(a,b)),.56,max(abs(a-b),.025),
                               fill=(b>=a),alpha=.65,linewidth=.5))
    ax.set_title(title); ax.set_xlim(-1,len(c)); ax.grid(True,alpha=.2); ax.set_ylabel("Price")

def render(kind):
    fig,ax=plt.subplots(figsize=(10,4),dpi=120); draw(ax,kind,title=kind.upper())
    fig.tight_layout(); b=io.BytesIO(); fig.savefig(b,format="png"); plt.close(fig); return b.getvalue()

def render_pair(parent,child,child_base):
    fig,axs=plt.subplots(2,1,figsize=(10,7),dpi=120,sharey=True)
    draw(axs[0],parent,100,"Higher timeframe"); draw(axs[1],child,child_base,"Lower timeframe")
    fig.tight_layout(); b=io.BytesIO(); fig.savefig(b,format="png"); plt.close(fig); return b.getvalue()

def call(prompt,img,schema,tokens=300):
    return generate_json(prompt+"\n\nPDF and user rules:\n"+RULES,img,schema,
                         os.environ["GEMINI_API_KEY"],MODEL,timeout=60,max_output_tokens=tokens)

def main():
    if not os.environ.get("GEMINI_API_KEY"): raise SystemExit("GEMINI_API_KEY missing")
    single_schema={"type":"object","properties":{
        "departure":{"type":"string","enum":["sideways","diagonal","sharp","uncertain"]},
        "evidence":{"type":"string"}},"required":["departure","evidence"],"additionalProperties":False}
    pair_schema={"type":"object","properties":{
        "parent_departure":{"type":"string","enum":["sideways","diagonal","sharp","uncertain"]},
        "child_departure":{"type":"string","enum":["sideways","diagonal","sharp","uncertain"]},
        "same_price_area":{"type":"boolean"},"confirmation":{"type":"boolean"},
        "evidence":{"type":"string"}},
        "required":["parent_departure","child_departure","same_price_area","confirmation","evidence"],
        "additionalProperties":False}
    out=[]
    for kind in ("sideways","diagonal","sharp"):
        r=call("Classify the dominant visible departure shape in this single candlestick chart. Return its class and visual evidence.",render(kind),single_schema)
        out.append({"case":"single_"+kind,"expected":kind,"actual":r.get("departure"),
                    "pass":r.get("departure")==kind,"evidence":r.get("evidence")})
    pair_cases=[
        ("diagonal_parent_sharp_child_same_area","diagonal","sharp",100,True),
        ("diagonal_parent_diagonal_child_same_area","diagonal","diagonal",100,False),
        ("diagonal_parent_sharp_child_different_area","diagonal","sharp",120,False)]
    for name,parent,child,base,expected in pair_cases:
        prompt=("Classify both panels. Does the lower timeframe confirm the higher-timeframe candidate? "
                "Confirmation requires a sharp lower-timeframe impulse, same direction, approximately "
                "same price area. A diagonal lower timeframe does not confirm. Judge same_price_area "
                "from the shared price scale; no ATR/OHLC thresholds.")
        r=call(prompt,render_pair(parent,child,base),pair_schema,350)
        passed=(r.get("parent_departure")==parent and r.get("child_departure")==child
                and r.get("same_price_area") is (base==100)
                and r.get("confirmation") is expected)
        out.append({"case":name,"expected_parent":parent,"actual_parent":r.get("parent_departure"),
                    "expected_child":child,"actual_child":r.get("child_departure"),
                    "expected_same_price_area":base==100,"actual_same_price_area":r.get("same_price_area"),
                    "expected_confirmation":expected,"actual_confirmation":r.get("confirmation"),
                    "pass":passed,"evidence":r.get("evidence")})
    passed=sum(bool(x["pass"]) for x in out)
    report={"model":MODEL,"passed":passed,"total":len(out),
            "scope":"controlled synthetic-chart comprehension; not historical backtest or profitability",
            "results":out}
    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"report.md").write_text("# AI comprehension: %s/%s passed\n\n"%(passed,len(out))+
        "\n".join("## %s — %s\n%s"%(x["case"],"PASS" if x["pass"] else "FAIL",
        json.dumps(x,ensure_ascii=False,indent=2)) for x in out),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if passed!=len(out): raise SystemExit("AI comprehension gate failed: %s/%s"%(passed,len(out)))
if __name__=="__main__": main()
