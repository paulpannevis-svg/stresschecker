(function(g){



var B=[40, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120];
var C=[-20, -10, 0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95, 100, 105, 110, 115, 120, 125, 130, 135, 140, 145, 150, 155, 160, 165, 170, 175, 180, 185, 190, 220];
var T=[[0, 0, 0, 0, 0, 0, 1, 2, 3, 5, 7, 9, 10, 20, 30, 40, 50, 60, 80, 85, 92, 100, 102, 105, 107, 110, 112, 115, 117, 120, 122, 125, 127, 130, 132, 135, 137, 140, 142, 145, 150, 160], [0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 15, 22, 30, 37, 45, 52, 57, 77, 82, 87, 90, 92, 95, 97, 100, 102, 105, 107, 110, 112, 115, 117, 120, 122, 125, 127, 130, 132, 135, 137, 140, 150], [0, 0, 1, 2, 4, 5, 6, 7, 15, 22, 30, 37, 45, 50, 55, 60, 65, 75, 80, 82, 85, 87, 90, 92, 95, 97, 100, 102, 105, 107, 110, 112, 115, 117, 120, 122, 125, 127, 130, 132, 135, 140], [0, 0, 1, 3, 5, 7, 12, 20, 27, 35, 42, 50, 52, 55, 60, 65, 67, 70, 75, 77, 80, 82, 85, 87, 90, 92, 95, 97, 100, 102, 105, 107, 110, 112, 115, 117, 120, 122, 125, 127, 130, 135], [0, 2, 3, 5, 7, 12, 17, 25, 30, 37, 45, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82, 85, 87, 90, 92, 95, 97, 100, 102, 105, 107, 110, 112, 115, 117, 120, 122, 125, 130], [0, 3, 5, 7, 12, 17, 25, 32, 37, 42, 47, 50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82, 85, 87, 90, 92, 95, 97, 100, 102, 105, 107, 110, 112, 115, 117, 120, 122, 125], [0, 5, 7, 8, 11, 15, 22, 30, 35, 40, 45, 47, 50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82, 85, 87, 90, 92, 95, 97, 100, 102, 105, 107, 110, 112, 115, 117, 120, 122], [0, 4, 6, 7, 8, 12, 15, 22, 30, 37, 42, 45, 47, 50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82, 85, 87, 90, 92, 95, 97, 100, 102, 105, 107, 110, 112, 115, 117, 120], [0, 2, 4, 5, 7, 10, 12, 20, 27, 35, 40, 42, 45, 47, 50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82, 85, 87, 90, 92, 95, 97, 100, 102, 105, 107, 110, 112, 115, 117], [0, 1, 3, 4, 6, 8, 11, 15, 22, 30, 35, 40, 42, 45, 47, 50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82, 85, 87, 90, 92, 95, 97, 100, 102, 105, 107, 110, 112, 115], [0, 1, 2, 3, 5, 7, 10, 12, 20, 27, 32, 35, 37, 40, 42, 45, 47, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82, 85, 87, 90, 92, 95, 97, 100, 102, 105, 107, 110, 112], [0, 1, 2, 2, 4, 6, 8, 9, 10, 17, 22, 27, 32, 35, 37, 40, 42, 47, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82, 85, 87, 90, 92, 95, 97, 100, 102, 105, 107, 110], [0, 0, 1, 2, 3, 4, 6, 8, 9, 10, 15, 20, 25, 30, 32, 35, 37, 42, 47, 50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82, 85, 87, 90, 92, 95, 97, 100, 102, 105], [0, 0, 1, 2, 2, 3, 3, 4, 5, 6, 7, 12, 15, 17, 22, 25, 27, 32, 37, 40, 42, 45, 47, 50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82, 85, 87, 90, 92, 95], [0, 0, 1, 1, 1, 1, 1, 2, 3, 4, 5, 7, 10, 12, 15, 17, 20, 22, 27, 30, 32, 35, 37, 40, 42, 45, 47, 50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75, 77, 80, 82, 85], [0, 0, 1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 17, 20, 22, 25, 27, 30, 32, 35, 37, 40, 42, 45, 47, 50, 52, 55, 57, 60, 62, 65, 67, 70, 72, 75]];
// RMSSD reference = healthy median per age/sex. Source: Tegegne et al. 2020,
// Lifelines Cohort (n=84.772), Eur J Prev Cardiol. Median = 100%.
// Values in ms, ECG-scale (PPG ÷2.5 applied upstream).
// Bins 18-24/25-29/.../70-74/75+; jeugd-bins (<18) bewust weggelaten — meting <18 wordt geblokkeerd in de pagina-flow.
var N=[{a:24,m:47.6,f:52.1},{a:29,m:42.3,f:47.5},{a:34,m:36.9,f:42.3},{a:39,m:32.8,f:37.9},{a:44,m:29.0,f:33.9},{a:49,m:26.0,f:29.2},{a:54,m:23.7,f:26.6},{a:59,m:21.0,f:22.5},{a:64,m:19.1,f:20.5},{a:69,m:17.7,f:17.8},{a:74,m:16.0,f:18.3},{a:999,m:14.9,f:16.1}];



function filterRR(rr, threshold, windowSize) {
    if (!rr || rr.length < 4) return {filtered: rr, quality: 100};
    threshold = threshold || 100;
    windowSize = windowSize || 10;
    var result = rr.slice();
    var n = result.length;
    var validMask = [];
    for (var i = 0; i < n; i++) {
        validMask.push(result[i] >= 300 && result[i] <= 2000);
    }
    var meanRR = 0, vc = 0;
    for (var i = 0; i < n; i++) {
        if (validMask[i]) { meanRR += result[i]; vc++; }
    }
    meanRR = vc > 0 ? meanRR / vc : 800;
    var scaledTh = threshold * (meanRR / 1000);
    // Kubios mediaan-drempel met threshold=100ms (Strong+)
    for (var i = 0; i < n; i++) {
        if (!validMask[i]) continue;
        var halfWin = Math.floor(windowSize / 2);
        var ws = Math.max(0, i - halfWin);
        var we = Math.min(n, i + halfWin + 1);
        var win = [];
        for (var j = ws; j < we; j++) {
            if (validMask[j] || j === i) win.push(result[j]);
        }
        win.sort(function(a, b) { return a - b; });
        var med = win[Math.floor(win.length / 2)];
        if (Math.abs(result[i] - med) > scaledTh) {
            validMask[i] = false;
        }
    }
    // Interpolatie
    var correctedCount = 0;
    for (var i = 0; i < n; i++) {
        if (validMask[i]) continue;
        correctedCount++;
        var left = -1, right = -1;
        for (var j = i - 1; j >= 0; j--) {
            if (validMask[j]) { left = j; break; }
        }
        for (var j = i + 1; j < n; j++) {
            if (validMask[j]) { right = j; break; }
        }
        if (left >= 0 && right >= 0) {
            result[i] = result[left] + (result[right] - result[left]) * ((i - left) / (right - left));
        } else if (left >= 0) {
            result[i] = result[left];
        } else if (right >= 0) {
            result[i] = result[right];
        }
    }
    var qualityPct = Math.round(((n - correctedCount) / n) * 100);
    if (typeof console !== 'undefined') {
        console.log('HRV Filter: ' + correctedCount + '/' + n +
                     ' gecorrigeerd (' + (100-qualityPct) + '%) th=' +
                     scaledTh.toFixed(0) + 'ms (Kubios 100)');
    }
    return {filtered: result, quality: qualityPct};
}

function calculateRMSSD(r){if(r&&r.length>15)r=r.slice(15);var res=filterRR(r);r=res.filtered;if(!r||r.length<2)return 0;var s=0;for(var i=1;i<r.length;i++){var d=r[i]-r[i-1];s+=d*d;}return Math.sqrt(s/(r.length-1));}
function calculateHRVPercent(r,age,gen){if(!r||r.length<2)return 0;var a=age||50,g=gen||"male";var ms=calculateRMSSD(r);var n=N[N.length-1];for(var i=0;i<N.length;i++){if(a<=N[i].a){n=N[i];break;}}var nv;if(g==="female")nv=n.f;else if(g==="divers"||g==="unspecified")nv=(n.m+n.f)/2;else nv=n.m;return Math.min(220,Math.max(0,Math.round((ms/nv)*100)));}
function lookupRelaxIndex(bpm,h){if(!bpm||h===undefined)return 1.0;var br=B.length-1;for(var i=0;i<B.length;i++){if(bpm<=B[i]){br=i;break;}}var ci=C.length-1;for(var j=0;j<C.length;j++){if(h<=C[j]){ci=j;break;}}return Math.min(10, Math.round((T[br][ci]/12)*10)/10);}
function getLabel(r){var L=({
  nl:["Zwaar belast","Belast","Licht belast","In balans","Veerkrachtig"],
  de:["Schwer belastet","Belastet","Leicht belastet","Im Gleichgewicht","Vital"],
  en:["Heavily strained","Strained","Lightly strained","In balance","Resilient"]
})[window.SC_LANG]||["Zwaar belast","Belast","Licht belast","In balans","Veerkrachtig"];
if(r>=8)return L[4];if(r>=6)return L[3];if(r>=4)return L[2];if(r>=2)return L[1];return L[0];}
// Kleur-grenzen exact gelijk aan getLabel (2/4/6/8): kleur en label vertellen hetzelfde
// zone-verhaal. Canonieke grens "Licht belast → In balans" = RI 6.0.
function getColor(r){if(r>=8)return "#27ae60";if(r>=6)return "#2ecc71";if(r>=4)return "#f1c40f";if(r>=2)return "#e67e22";return "#c0392b";}
function getMeetKwaliteit(r){if(r&&r.length>30)r=r.slice(15);if(!r||r.length<3)return 100;return filterRR(r).quality;}
// Kwaliteits-gate (KWALITEITS_GATE_ONTWERP.md): vertrouwbaarheidsklasse van een meting.
// >=85 'trusted' · 70-84 'limited' (toon met voorbehoud, blokkeer positieve "Veerkrachtig")
// · <70 'untrusted' (RI/zone onderdrukken). Ontbrekende kwaliteit = vertrouwd (besluit 5: legacy).
function riConfidence(kw){kw=(kw===null||kw===undefined||kw==='')?100:Number(kw);if(isNaN(kw))return 'trusted';return kw>=85?'trusted':kw>=70?'limited':'untrusted';}
// ===========================================================================
// NIEUWE tweelaags-meetkwaliteit (qualityClassify) — APART van rrIrregularity.
// Gebouwd op read-only PI-Zwolle-analyse (juni 2026). De oude SD1/SD2-gate
// hierboven (rrIrregularity) blijft als REFERENTIE staan tijdens A/B-testen;
// deze functie vervangt 'm (nog) NIET.
//  LAAG 1 — puntartefacten: Kubios per-interval, venster W=21 (gecentreerd,
//    asymmetrisch/trailing aan de randen, testinterval uitgesloten). Markeer als
//    |RR_i - lokaalgemiddelde| > 25% van dat lokaalgemiddelde (intrinsiek
//    hartslag-geschaald). Tel artefact-%.
//  CORRECTIE (variant B) — lineaire interpolatie van losse artefacten EN gaten van 2
//    (run-lengte 1 of 2) tussen geldige buren. Bij >=3 OPEENVOLGENDE gemarkeerde
//    intervallen NIET interpoleren (zou verzonnen data zijn): die meting wordt Slecht
//    via de aaneengesloten-regel.
//  LAAG 2 — Poincaré-vorm SD1/SD2 >= 0.70 EN RMSSD >= 25 ms.
//    ONTWERPKEUZE: Laag 2 rekent op de GECORRIGEERDE RR. Een puntartefact blaast
//    SD1/RMSSD op en maakt de wolk kunstmatig rond; op ruwe RR zou Laag 2 dus
//    her-vlaggen wat Laag 1 al ving (puntruis != echte ritme-onregelmatigheid).
//    Laag 2 oordeelt over het RESTERENDE ritme na puntcorrectie. De RMSSD-vloer
//    (25) weert het vlak-kalme lage-HRV-artefact waar SD1/SD2 spurieus -> 1 loopt.
//  LABEL: Slecht = artefact-% >15% OF aaneengesloten OF Laag2 -> GEEN RI.
//         Redelijk = artefact-% 5-15% (en niet Slecht) -> RI met voorbehoud.
//         Goed = artefact-% <=5% (en niet Slecht) -> normale RI.
//  RI hoort (door de caller) op de GECORRIGEERDE RR berekend te worden.
var QUAL_W=21, QUAL_ART_REL=0.25, QUAL_BAND_GOED=5, QUAL_BAND_SLECHT=15;
var QUAL_L2_SD1SD2=0.70, QUAL_L2_RMSSD_MIN=25;
function _poincare(rr){
  var n=rr.length, mean=0, i; for(i=0;i<n;i++)mean+=rr[i]; mean/=n;
  var ss=0; for(i=0;i<n;i++){var dv=rr[i]-mean; ss+=dv*dv;} var sdnn=Math.sqrt(ss/n);
  var s=0,md=0; for(i=1;i<n;i++){var d=rr[i]-rr[i-1]; s+=d*d; md+=d;} var nd=n-1; md/=nd;
  var rmssd=Math.sqrt(s/nd);
  var sx=0; for(i=1;i<n;i++){var d2=(rr[i]-rr[i-1])-md; sx+=d2*d2;} var sdsd=Math.sqrt(sx/nd);
  var sd1=Math.sqrt(0.5)*sdsd, sd2=Math.sqrt(Math.max(2*sdnn*sdnn-0.5*sdsd*sdsd,0));
  return {ratio: sd2>0?sd1/sd2:99, rmssd:rmssd};
}
function qualityClassify(rr){
  if(typeof rr==='string'){try{rr=JSON.parse(rr);}catch(e){return {band:'onbepaald',reason:'parse'};}}
  if(!rr||rr.length<20) return {band:'onbepaald',reason:'te kort (<20 RR)'};
  var n=rr.length, half=Math.floor(QUAL_W/2), i, j;
  // LAAG 1 — detectie van puntartefacten
  var flag=new Array(n);
  for(i=0;i<n;i++){
    var lo=Math.max(0,i-half), hi=Math.min(n-1,i+half), sum=0, cnt=0;
    for(j=lo;j<=hi;j++){ if(j!==i){ sum+=rr[j]; cnt++; } }
    var lm=cnt>0?sum/cnt:rr[i];
    flag[i]=Math.abs(rr[i]-lm) > QUAL_ART_REL*lm;
  }
  // run-lengtes per index bepalen (voor de interpolatie-grens en de aaneengesloten-regel)
  var artCount=0, maxRun=0, runLen=new Array(n), k;
  for(i=0;i<n;i++) runLen[i]=0;
  for(i=0;i<n;i++) if(flag[i]) artCount++;
  k=0; while(k<n){ if(flag[k]){ var st=k; while(k<n && flag[k]) k++; var L=k-st; for(var p=st;p<k;p++) runLen[p]=L; if(L>maxRun)maxRun=L; } else k++; }
  var artPct=100*artCount/n, consecutive=(maxRun>=3);
  // CORRECTIE — losse artefacten EN gaten van 2 (run-lengte 1 of 2) lineair interpoleren
  // tussen geldige buren. Runs van >=3 worden NIET geinterpoleerd (Slecht via consecutive).
  var corr=rr.slice();
  for(i=0;i<n;i++){
    if(!flag[i] || runLen[i]>2) continue;
    var left=i-1, right=i+1;
    while(left>=0 && flag[left]) left--;
    while(right<n && flag[right]) right++;
    if(left>=0 && right<n) corr[i]=rr[left]+(rr[right]-rr[left])*((i-left)/(right-left));
    else if(left>=0) corr[i]=rr[left];
    else if(right<n) corr[i]=rr[right];
  }
  // LAAG 2 — Poincaré-vorm op de GECORRIGEERDE RR (zie ontwerpkeuze hierboven)
  var pc=_poincare(corr);
  var laag2=(pc.ratio>=QUAL_L2_SD1SD2 && pc.rmssd>=QUAL_L2_RMSSD_MIN);
  // LABEL
  var band, reason;
  if(artPct>QUAL_BAND_SLECHT){ band='slecht'; reason='Laag1 artefact '+(Math.round(artPct*10)/10)+'% > 15%'; }
  else if(consecutive){ band='slecht'; reason='aaneengesloten artefacten (run='+maxRun+'), niet interpoleerbaar'; }
  else if(laag2){ band='slecht'; reason='Laag2 SD1/SD2 '+(Math.round(pc.ratio*100)/100)+' >= 0.70'; }
  else if(artPct>QUAL_BAND_GOED){ band='redelijk'; reason='Laag1 artefact '+(Math.round(artPct*10)/10)+'% (5-15%)'; }
  else { band='goed'; reason='schoon'; }
  return {
    band:band, reason:reason,
    artefactPct:Math.round(artPct*10)/10, artefactCount:artCount, maxRun:maxRun,
    sd1sd2:Math.round(pc.ratio*1000)/1000, rmssd:Math.round(pc.rmssd*10)/10,
    laag1Slecht:(artPct>QUAL_BAND_SLECHT||consecutive), laag2:laag2,
    corrected:corr, scoreOK:(band==='goed'||band==='redelijk')
  };
}
function calculateSDNN(r){var res=filterRR(r);var f=res.filtered;if(!f||f.length<2)return 0;var m=f.reduce(function(a,b){return a+b;},0)/f.length;return Math.round(Math.sqrt(f.reduce(function(a,b){return a+Math.pow(b-m,2);},0)/f.length)*10)/10;}
function calculatePNN50(r){var res=filterRR(r);var f=res.filtered;if(!f||f.length<2)return 0;var n=0;for(var i=1;i<f.length;i++)if(Math.abs(f[i]-f[i-1])>50)n++;return Math.round((n/(f.length-1))*1000)/10;}
var HRV={filterRR:filterRR,calculateRMSSD:calculateRMSSD,calculateSDNN:calculateSDNN,calculatePNN50:calculatePNN50,calculateHRVPercent:calculateHRVPercent,getMeetKwaliteit:getMeetKwaliteit,riConfidence:riConfidence,qualityClassify:qualityClassify,QUAL_L2_SD1SD2:QUAL_L2_SD1SD2,QUAL_L2_RMSSD_MIN:QUAL_L2_RMSSD_MIN,lookupRelaxIndex:lookupRelaxIndex,getLabel:getLabel,getColor:getColor,RMSSD_NORMS:N};
if(typeof module!=="undefined"&&module.exports){module.exports=HRV;}else{g.HRV=HRV;}
})(typeof window!=="undefined"?window:this);
