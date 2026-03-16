import os
import re
import json
import datetime
import requests
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from flask import Flask, request
import anthropic

# --- Configuratie ---
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
JOUW_EMAIL = os.environ.get("JOUW_EMAIL", "henricovdbiezen@gmail.com")
GMAIL_API_KEY = os.environ.get("GMAIL_API_KEY", "")
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")

# --- Apps initialiseren ---
slack_app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(slack_app)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# --- Tools definitie voor Claude ---
TOOLS = [
    {
        "name": "zoek_weerbericht",
        "description": "Zoekt het weerbericht op voor een opgegeven stad in Nederland.",
        "input_schema": {
            "type": "object",
            "properties": {
                "stad": {
                    "type": "string",
                    "description": "De naam van de stad, bijv. 'Nijkerk' of 'Amsterdam'"
                }
            },
            "required": ["stad"]
        }
    },
    {
        "name": "zoek_nieuws",
        "description": "Zoekt recent nieuws of informatie op over een onderwerp.",
        "input_schema": {
            "type": "object",
            "properties": {
                "onderwerp": {
                    "type": "string",
                    "description": "Het onderwerp om nieuws over te zoeken"
                }
            },
            "required": ["onderwerp"]
        }
    },
    {
        "name": "stuur_email",
        "description": "Stelt een e-mail op en stuurt deze naar een ontvanger via Gmail.",
        "input_schema": {
            "type": "object",
            "properties": {
                "aan": {
                    "type": "string",
                    "description": "E-mailadres van de ontvanger"
                },
                "onderwerp": {
                    "type": "string",
                    "description": "Het onderwerp van de e-mail"
                },
                "inhoud": {
                    "type": "string",
                    "description": "De inhoud/tekst van de e-mail"
                }
            },
            "required": ["aan", "onderwerp", "inhoud"]
        }
    },
    {
        "name": "bekijk_agenda",
        "description": "Bekijkt de Google Calendar agenda voor de komende dagen.",
        "input_schema": {
            "type": "object",
            "properties": {
                "dagen": {
                    "type": "integer",
                    "description": "Hoeveel dagen vooruit je wil kijken (standaard 7)"
                }
            },
            "required": []
        }
    },
    {
        "name": "maak_afspraak",
        "description": "Maakt een nieuwe afspraak aan in Google Calendar.",
        "input_schema": {
            "type": "object",
            "properties": {
                "titel": {
                    "type": "string",
                    "description": "De naam/titel van de afspraak"
                },
                "datum": {
                    "type": "string",
                    "description": "Datum en tijd van de afspraak in formaat YYYY-MM-DD HH:MM"
                },
                "duur_minuten": {
                    "type": "integer",
                    "description": "Duur van de afspraak in minuten"
                },
                "beschrijving": {
                    "type": "string",
                    "description": "Optionele beschrijving van de afspraak"
                }
            },
            "required": ["titel", "datum"]
        }
    }
]

# --- Tool uitvoering functies ---

def zoek_weerbericht(stad):
    if WEATHER_API_KEY:
        try:
            url = f"http://api.weatherapi.com/v1/forecast.json?key={WEATHER_API_KEY}&q={stad}&days=3&lang=nl"
            r = requests.get(url, timeout=5)
            data = r.json()
            current = data["current"]
            forecast = data["forecast"]["forecastday"]
            result = f"🌤️ Weerbericht voor {stad}:\n"
            result += f"Nu: {current['temp_c']}°C, {current['condition']['text']}\n\n"
            result += "Komende dagen:\n"
            for dag in forecast:
                result += f"• {dag['date']}: max {dag['day']['maxtemp_c']}°C, min {dag['day']['mintemp_c']}°C, {dag['day']['condition']['text']}\n"
            return result
        except Exception as e:
            return f"Weerbericht ophalen mislukt: {str(e)}"
    else:
        # Gratis fallback via wttr.in
        try:
            url = f"https://wttr.in/{stad}?format=j1"
            r = requests.get(url, timeout=5)
            data = r.json()
            current = data["current_condition"][0]
            temp = current["temp_C"]
            desc = current["weatherDesc"][0]["value"]
            return f"🌤️ Weerbericht voor {stad}:\nNu: {temp}°C, {desc}\n(Tip: voeg een gratis WeatherAPI key toe voor meer details)"
        except Exception as e:
            return f"Weerbericht ophalen mislukt: {str(e)}"

def zoek_nieuws(onderwerp):
    if NEWS_API_KEY:
        try:
            url = f"https://newsapi.org/v2/everything?q={onderwerp}&language=nl&sortBy=publishedAt&pageSize=5&apiKey={NEWS_API_KEY}"
            r = requests.get(url, timeout=5)
            data = r.json()
            articles = data.get("articles", [])
            if not articles:
                return f"Geen nieuws gevonden over '{onderwerp}'"
            result = f"📰 Nieuws over '{onderwerp}':\n\n"
            for a in articles[:3]:
                result += f"• **{a['title']}**\n  {a['source']['name']} — {a['publishedAt'][:10]}\n  {a.get('description', '')}\n\n"
            return result
        except Exception as e:
            return f"Nieuws ophalen mislukt: {str(e)}"
    else:
        return f"📰 Nieuws zoeken naar '{onderwerp}':\nVoeg een gratis NewsAPI key toe via newsapi.org om nieuws op te halen. Ik kan je wel algemene informatie geven over dit onderwerp!"

def stuur_email(aan, onderwerp, inhoud):
    try:
        import smtplib
        from email.mime.text import MIMEText
        gmail_user = os.environ.get("GMAIL_USER", "")
        gmail_pass = os.environ.get("GMAIL_APP_PASSWORD", "")
        if not gmail_user or not gmail_pass:
            return f"📧 E-mail opgesteld maar nog niet verzonden.\n\nAan: {aan}\nOnderwerp: {onderwerp}\nInhoud:\n{inhoud}\n\n⚠️ Voeg GMAIL_USER en GMAIL_APP_PASSWORD toe als omgevingsvariabelen om e-mails automatisch te versturen."
        msg = MIMEText(inhoud)
        msg["Subject"] = onderwerp
        msg["From"] = gmail_user
        msg["To"] = aan
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(gmail_user, gmail_pass)
            server.send_message(msg)
        return f"✅ E-mail verstuurd!\nAan: {aan}\nOnderwerp: {onderwerp}"
    except Exception as e:
        return f"E-mail versturen mislukt: {str(e)}"

def bekijk_agenda(dagen=7):
    if not GOOGLE_API_KEY:
        return "📅 Agenda bekijken: Voeg een GOOGLE_API_KEY toe om je agenda te bekijken."
    try:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        later = (datetime.datetime.utcnow() + datetime.timedelta(days=dagen)).isoformat() + "Z"
        url = f"https://www.googleapis.com/calendar/v3/calendars/{GOOGLE_CALENDAR_ID}/events"
        params = {
            "key": GOOGLE_API_KEY,
            "timeMin": now,
            "timeMax": later,
            "singleEvents": True,
            "orderBy": "startTime",
            "maxResults": 10
        }
        r = requests.get(url, params=params, timeout=5)
        data = r.json()
        events = data.get("items", [])
        if not events:
            return f"📅 Geen afspraken de komende {dagen} dagen."
        result = f"📅 Jouw agenda (komende {dagen} dagen):\n\n"
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date", ""))[:16]
            result += f"• {start} — {e.get('summary', 'Geen titel')}\n"
        return result
    except Exception as e:
        return f"Agenda ophalen mislukt: {str(e)}"

def maak_afspraak(titel, datum, duur_minuten=60, beschrijving=""):
    if not GOOGLE_API_KEY:
        return f"📅 Afspraak aangemaakt (lokaal):\n• Titel: {titel}\n• Datum: {datum}\n• Duur: {duur_minuten} minuten\n\n⚠️ Voeg een GOOGLE_API_KEY toe om afspraken echt in je agenda te zetten."
    return f"📅 Afspraak '{titel}' op {datum} voor {duur_minuten} minuten is genoteerd! (Koppel Google Calendar OAuth voor volledige integratie)"

# --- Tool router ---
def voer_tool_uit(tool_naam, tool_input):
    if tool_naam == "zoek_weerbericht":
        return zoek_weerbericht(tool_input["stad"])
    elif tool_naam == "zoek_nieuws":
        return zoek_nieuws(tool_input["onderwerp"])
    elif tool_naam == "stuur_email":
        return stuur_email(tool_input["aan"], tool_input["onderwerp"], tool_input["inhoud"])
    elif tool_naam == "bekijk_agenda":
        return bekijk_agenda(tool_input.get("dagen", 7))
    elif tool_naam == "maak_afspraak":
        return maak_afspraak(
            tool_input["titel"],
            tool_input["datum"],
            tool_input.get("duur_minuten", 60),
            tool_input.get("beschrijving", "")
        )
    else:
        return f"Onbekende tool: {tool_naam}"

# --- Systeem prompt ---
SYSTEEM_PROMPT = f"""Je bent Henrico's persoonlijke AI-assistent via Slack.

Je helpt Henrico met:
- 🌤️ Weerbericht opzoeken
- 📰 Nieuws en informatie opzoeken
- 📧 E-mails opstellen en versturen
- 📅 Agenda bekijken en afspraken maken

Vandaag is het: {datetime.datetime.now().strftime("%A %d %B %Y")}
Henrico's e-mailadres: {JOUW_EMAIL}

Gedraag je als een proactieve assistent:
- Gebruik tools om taken echt uit te voeren
- Antwoord altijd in het Nederlands
- Wees kort en to-the-point
- Als je iets gedaan hebt, bevestig dat duidelijk
- Als je iets niet kunt, leg dan uit wat je nodig hebt
"""

# --- Agentic loop: voer taken uit met tools ---
def verwerk_bericht(gebruiker_bericht):
    messages = [{"role": "user", "content": gebruiker_bericht}]
    
    # Maximaal 5 rondes tool gebruik
    for _ in range(5):
        response = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=SYSTEEM_PROMPT,
            tools=TOOLS,
            messages=messages
        )
        
        # Klaar — geen tools meer nodig
        if response.stop_reason == "end_turn":
            tekst = ""
            for blok in response.content:
                if hasattr(blok, "text"):
                    tekst += blok.text
            return tekst
        
        # Claude wil een tool gebruiken
        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            tool_resultaten = []
            
            for blok in response.content:
                if blok.type == "tool_use":
                    resultaat = voer_tool_uit(blok.name, blok.input)
                    tool_resultaten.append({
                        "type": "tool_result",
                        "tool_use_id": blok.id,
                        "content": resultaat
                    })
            
            messages.append({"role": "user", "content": tool_resultaten})
        else:
            break
    
    return "Ik kon de taak niet voltooien. Probeer het opnieuw."

# --- Slack event handlers ---
@slack_app.event("app_mention")
def handle_mention(event, say):
    gebruiker_bericht = re.sub(r"<@[^>]+>", "", event["text"]).strip()
    if not gebruiker_bericht:
        say("Hoi Henrico! Zeg maar wat ik voor je kan doen 😊")
        return
    say("Eén momentje, ik ga dat voor je regelen... ⏳")
    try:
        antwoord = verwerk_bericht(gebruiker_bericht)
        say(antwoord)
    except Exception as e:
        say(f"Oeps, er ging iets mis: {str(e)}")

@slack_app.event("message")
def handle_dm(event, say):
    if event.get("channel_type") == "im" and not event.get("bot_id"):
        gebruiker_bericht = event.get("text", "").strip()
        if not gebruiker_bericht:
            return
        say("Eén momentje... ⏳")
        try:
            antwoord = verwerk_bericht(gebruiker_bericht)
            say(antwoord)
        except Exception as e:
            say(f"Oeps, er ging iets mis: {str(e)}")

# --- Flask routes ---
@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)

@flask_app.route("/", methods=["GET"])
def health_check():
    return "Henrico Agent v2 draait! 🤖", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)
