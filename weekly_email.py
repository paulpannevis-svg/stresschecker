#!/usr/bin/env python3
import sqlite3, os
from datetime import datetime
import sendgrid
from sendgrid.helpers.mail import Mail
from dotenv import load_dotenv

# Expliciet pad: cron draait dit script vanuit /root, niet vanuit /opt/stresschecker.
load_dotenv('/opt/stresschecker/.env')

METING_DB = "/opt/stresschecker/data/sc_measurements.db"
SG_KEY = os.environ['SENDGRID_API_KEY']

def get_naam(email):
    return email.split("@")[0].split(".")[0].split("+")[0].capitalize()

def get_patroon(user_key):
    db = sqlite3.connect(METING_DB)
    db.row_factory = sqlite3.Row
    now = int(datetime.now().timestamp()*1000)
    week = 7*24*3600*1000
    rows = db.execute("SELECT ri, ctx_dimensie, ts FROM metingen WHERE user_key=? AND pending=0 ORDER BY ts DESC LIMIT 30", (user_key,)).fetchall()
    db.close()
    if len(rows) == 0:
        return {'status': 'nieuw'}
    if len(rows) < 3:
        return {'status': 'starter', 'count': len(rows)}
    recent_ts = [r['ts'] for r in rows if r['ts'] and now-r['ts']<week]
    if not recent_ts:
        return {'status': 'inactief', 'count': len(rows)}
    recent = [r["ri"] for r in rows if r["ts"] and now-r["ts"]<week and r["ri"]]
    older  = [r["ri"] for r in rows if r["ts"] and week<=now-r["ts"]<2*week and r["ri"]]
    ar = round(sum(recent)/len(recent),1) if recent else None
    ao = round(sum(older)/len(older),1) if older else None
    dims = [r["ctx_dimensie"] for r in rows if r["ctx_dimensie"]]
    dc = {}
    for d in dims: dc[d] = dc.get(d,0)+1
    td = max(dc, key=dc.get) if dc else None
    return {"avg_recent":ar,"avg_older":ao,"top_dim":td,"top_dim_count":dc.get(td,0) if td else 0,"top_dim_total":len(dims),"count":len(rows)}

def build_nudge(email, lang, status="nieuw", count=0):
    naam = get_naam(email)
    aanhef = {"nl":f"Beste {naam},","de":f"Liebe/r {naam},","en":f"Dear {naam},"}.get(lang, f"Beste {naam},")
    subj = {"nl":"Hoe gaat het met je?","de":"Wie geht es dir?","en":"How are you doing?"}.get(lang,"Hoe gaat het met je?")
    tekst = {"nl":"Je hebt deze week nog niet gemeten. Neem 90 seconden voor jezelf en ontdek hoe je lichaam er echt voor staat.","de":"Diese Woche hast du noch keine Messung durchgefuehrt. Nimm dir 90 Sekunden fuer dich und entdecke, wie es deinem Koerper wirklich geht.","en":"You have not measured this week yet. Take 90 seconds for yourself and find out how your body is really doing."}.get(lang,"")
    groet = {"nl":"Hartelijke groet,\nTeam Lifestyle Monitors","de":"Herzliche Gruesse,\nTeam Lifestyle Monitors","en":"Kind regards,\nTeam Lifestyle Monitors"}.get(lang,"")
    return subj, aanhef + "\n\n" + tekst + "\n\n" + groet

def build_email(email, lang, p):
    naam = get_naam(email)
    aanhef = {"nl":f"Beste {naam},","de":f"Liebe/r {naam},","en":f"Dear {naam},"}.get(lang, f"Beste {naam},")
    subj = {"nl":"Je weekoverzicht van StressChecker","de":"Deine Wochenzusammenfassung von StressChecker","en":"Your weekly StressChecker summary"}.get(lang,"Je weekoverzicht")
    delen = []
    if p["avg_recent"] and p["avg_older"]:
        if p["avg_recent"] > p["avg_older"]:
            t = {"nl":f"Je RI steeg van {p['avg_older']} naar {p['avg_recent']}. Je lichaam ontspant meer deze week.","de":f"Dein RI stieg von {p['avg_older']} auf {p['avg_recent']}. Dein Koerper erholt sich besser.","en":f"Your RI rose from {p['avg_older']} to {p['avg_recent']}. Your body is relaxing more this week."}
        else:
            t = {"nl":f"Je RI daalde van {p['avg_older']} naar {p['avg_recent']}. Je lichaam vraagt aandacht.","de":f"Dein RI sank von {p['avg_older']} auf {p['avg_recent']}. Dein Koerper braucht Aufmerksamkeit.","en":f"Your RI dropped from {p['avg_older']} to {p['avg_recent']}. Your body needs attention."}
        delen.append(t.get(lang,""))
    dn_map = {"lichamelijk":{"nl":"lichamelijks","de":"Koerperliches","en":"something physical"},"mentaal":{"nl":"mentaals","de":"Mentales","en":"something mental"},"emotioneel":{"nl":"emotioneeels","de":"Emotionales","en":"something emotional"},"spiritueel":{"nl":"spiritueels","de":"Spirituelles","en":"something deeper"}}
    vragen = {"lichamelijk":{"nl":"Wat zegt je lichaam waaraan je aandacht moet besteden?","de":"Was sagt dir dein Koerper, dem du Aufmerksamkeit schenken solltest?","en":"What is your body telling you needs attention?"},"mentaal":{"nl":"Welke gedachte vraagt om aandacht?","de":"Welcher Gedanke braucht deine Aufmerksamkeit?","en":"Which thought needs your attention?"},"emotioneel":{"nl":"Welk gevoel wacht op aandacht?","de":"Welches Gefuehl wartet op Aufmerksamkeit?","en":"Which feeling is waiting for your attention?"},"spiritueel":{"nl":"Handel je vanuit wat je echt belangrijk vindt?","de":"Handelst du aus dem, was dir wirklich wichtig ist?","en":"Are you acting from what truly matters to you?"}}
    v2_map = {"nl":"Wat spreek je met jezelf af om hieraan iets te gaan doen?","de":"Was nimmst du dir vor, um daran etwas zu aendern?","en":"What will you commit to doing about this?"}
    if p["top_dim"] and p["top_dim_count"] >= 2:
        dn = dn_map.get(p["top_dim"],{}).get(lang, p["top_dim"])
        t2 = {"nl":f"Bij {p['top_dim_count']} van je laatste {p['top_dim_total']} metingen heb je aangegeven dat er iets {dn} speelt.","de":f"Bei {p['top_dim_count']} von {p['top_dim_total']} Messungen hast du angegeben, dass {dn} eine Rolle spielt.","en":f"In {p['top_dim_count']} of your last {p['top_dim_total']} measurements you indicated {dn} is at play."}
        delen.append(t2.get(lang,""))
    if p["top_dim"]:
        vraag = vragen.get(p["top_dim"],{}).get(lang,"")
        v2 = v2_map.get(lang,"")
        if vraag: delen.append(vraag)
        if v2: delen.append(v2)
    groet = {"nl":"Hartelijke groet,\nTeam Lifestyle Monitors","de":"Herzliche Gruesse,\nTeam Lifestyle Monitors","en":"Kind regards,\nTeam Lifestyle Monitors"}.get(lang,"")
    return subj, aanhef + "\n\n" + "\n\n".join(delen) + "\n\n" + groet

def send_weekly():
    db = sqlite3.connect(METING_DB)
    db.row_factory = sqlite3.Row
    users = db.execute("SELECT user_key, email, lang FROM user_profiles WHERE email != '' ORDER BY last_seen DESC").fetchall()
    db.close()
    sg = sendgrid.SendGridAPIClient(SG_KEY)
    sent = 0
    for u in users:
        lang = u["lang"] or "nl"
        p = get_patroon(u["user_key"])
        if not p or "status" in p:
            status = p["status"] if p else "nieuw"
            count = p.get("count",0) if p else 0
            subj, body = build_nudge(u["email"], lang, status, count)
            label = f"Nudge({status})"
        else:
            subj, body = build_email(u["email"], lang, p)
            label = "Patroon"
        msg = Mail(from_email="noreply@lifestylemonitors.com", to_emails=u["email"], subject=subj, plain_text_content=body)
        try:
            sg.send(msg)
            sent += 1
            print(f"{label} verzonden: {u['email']}")
        except Exception as e:
            print(f"Fout {u['email']}: {e}")
    print(f"Klaar: {sent} emails verzonden")

if __name__ == "__main__":
    send_weekly()
