#!/usr/bin/env python3
"""getColor() ↔ getLabel() consistentie (static/js/hrv.js).

Sinds de gelijktrekking (2026-06-07) moeten kleur en label exact hetzelfde zone-verhaal
vertellen: dezelfde grenzen 2/4/6/8. Deze test laadt hrv.js in node (CommonJS-export, met
window-shim voor getLabel) en verifieert dat getColor en getLabel bij elke grenswaarde
dezelfde zone teruggeven, met expliciete checks op de gemelde gevallen 5.9 / 6.0 / 6.1 / 7.0.
"""
import os, sys, json, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HRV = os.path.join(ROOT, 'static', 'js', 'hrv.js')

def main():
    try:
        subprocess.run(['node', '--version'], capture_output=True, check=True)
    except Exception:
        print("[SKIP] node niet beschikbaar — getColor-test overgeslagen", file=sys.stderr)
        sys.exit(0)
    script = "globalThis.window={SC_LANG:'nl'};\n" + "const HRV=require(" + json.dumps(HRV) + ");\n" + r"""
var LBL=["Zwaar belast","Belast","Licht belast","In balans","Veerkrachtig"];
var COL=["#c0392b","#e67e22","#f1c40f","#2ecc71","#27ae60"];
function lblIdx(r){return LBL.indexOf(HRV.getLabel(r));}
function colIdx(r){return COL.indexOf(HRV.getColor(r));}
var fail=0, pass=0;
[0,1.9,2.0,3.9,4.0,5.9,6.0,6.1,7.0,7.9,8.0,10].forEach(function(r){
  var a=colIdx(r), b=lblIdx(r); var ok=(a===b && a>=0);
  console.log((ok?"[PASS]":"[FAIL]")+" RI "+r+" colorZone="+a+" labelZone="+b+" ("+HRV.getColor(r)+" / "+HRV.getLabel(r)+")");
  ok?pass++:fail++;
});
function expect(r,hex){var ok=HRV.getColor(r)===hex; console.log((ok?"[PASS]":"[FAIL]")+" getColor("+r+")="+HRV.getColor(r)+" verwacht "+hex); ok?pass++:fail++;}
expect(5.9,"#f1c40f"); expect(6.0,"#2ecc71"); expect(6.1,"#2ecc71"); expect(7.0,"#2ecc71");
console.log("\ntest_getcolor: "+pass+" passed, "+fail+" failed");
process.exit(fail?1:0);
"""
    with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False, encoding='utf-8') as tf:
        tf.write(script); path = tf.name
    try:
        r = subprocess.run(['node', path], capture_output=True, text=True)
        sys.stdout.write(r.stdout)
        if r.stderr.strip():
            sys.stderr.write(r.stderr)
        sys.exit(r.returncode)
    finally:
        os.unlink(path)

if __name__ == '__main__':
    main()
