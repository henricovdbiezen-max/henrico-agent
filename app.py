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
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY", "")
NEWS_API_KEY = os.environ.get("NEWS_API_KEY", "")

# --- Apps initialiseren ---
slack_app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(slack_app)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# --- Systeem prompt ---
SYSTEEM_PROMPT = f"""Je bent Henrico's persoonlijke AI-assistent via Slack.

Vandaag is het: {datetime.datetime.now().strftime("%A %d %B %Y")}
Henrico's e-mailadres: {JOUW_EMAIL}

Je kunt de volgende dingen doen:

1. 🌤️ WEERBERICHT: Haal het weerbericht op via wttr.in voor elke stad
2. 📰 NIEUWS: Zoek informatie op via je eigen kennis of geef aan wat je weet
3. 📧 EMAIL: Stuur e-mails via Gmail MCP. Gebruik de gmail tool om een draft aan te maken.
4. 📅 AGENDA: Geef aan dat Google Calendar koppeling nog in aanbouw is

Voor e-mails: gebruik de mcp tool 'gmail' om een draft aan te maken met create_draft.
De draft wordt aangemaakt in Gmail van {JOUW_EMAIL}.

Antwoord altijd in het Nederlands, kort en duidelijk.
Bevestig altijd wat je hebt gedaan.
"""

# --- Weerbericht ophalen ---
def zoek_weerbericht(stad):
    try:
        url = f"https://wttr.in/{stad}?format=j1"
        r = requests.get(url, timeout=8)
        data = r.json()
        current = data["current_condition"][0]
        temp = current["temp_C"]
        feels = current["FeelsLikeC"]
        desc = current["weatherDesc"][0]["value"]
        humidity = current["humidity"]

        forecast = data.get("weather", [])
        result = f"🌤️ Weerbericht voor {stad}:\n"
        result += f"Nu: {temp}°C (voelt als {feels}°C), {desc}, vochtigheid: {humidity}%\n\n"

        dagen = ["Vandaag", "Morgen", "Overmorgen"]
        for i, dag in enumerate(forecast[:3]):
            max_temp = dag["maxtempC"]
            min_temp = dag["mintempC"]
            dag_desc = dag["hourly"][4]["weatherDesc"][0]["value"]
            neerslag = dag["hourly"][4].get("precipMM", "0")
            result += f"• {dagen[i]}: {min_temp}°C - {max_temp}°C, {dag_desc}, neerslag: {neerslag}mm\n"

        return result
    except Exception as e:
        return f"Weerbericht ophalen mislukt: {str(e)}"

# --- Email versturen via Claude met Gmail MCP ---
def stuur_email_via_mcp(aan, onderwerp, inhoud):
    try:
        response = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=f"Je bent een e-mail assistent. Maak een Gmail draft aan met de opgegeven gegevens. Bevestig daarna in het Nederlands dat de draft is aangemaakt.",
            mcp_servers=[
                {
                    "type": "url",
                    "url": "https://gmail.mcp.claude.com/mcp",
                    "name": "gmail"
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": f"Maak een Gmail draft aan:\nAan: {aan}\nOnderwerp: {onderwerp}\nInhoud: {inhoud}"
                }
            ]
        )
        # Haal de tekstresponse op
        for blok in response.content:
            if hasattr(blok, "text"):
                return f"📧 {blok.text}"
        return f"📧 E-mail draft aangemaakt!\nAan: {aan}\nOnderwerp: {onderwerp}"
    except Exception as e:
        return f"E-mail aanmaken mislukt: {str(e)}"

# --- Agentic verwerking ---
def verwerk_bericht(gebruiker_bericht):
    bericht_lower = gebruiker_bericht.lower()

    # Weerbericht detecteren
    weer_woorden = ["weerbericht", "weer", "temperatuur", "regen", "zon", "graden"]
    if any(w in bericht_lower for w in weer_woorden):
        # Stad uit bericht halen
        steden = ["nijkerk", "amsterdam", "utrecht", "arnhem", "rotterdam", "den haag", "eindhoven", "nijmegen"]
        stad = "Nijkerk"  # standaard
        for s in steden:
            if s in bericht_lower:
                stad = s.capitalize()
                break
        # Kijk of er een andere stad wordt genoemd
        woorden = gebruiker_bericht.split()
        for i, woord in enumerate(woorden):
            if woord.lower() in ["voor", "in", "van"] and i + 1 < len(woorden):
                mogelijke_stad = woorden[i + 1].strip(".,!?")
                if len(mogelijke_stad) > 2:
                    stad = mogelijke_stad
                    break
        return zoek_weerbericht(stad)

    # E-mail detecteren
    email_woorden = ["mail", "e-mail", "email", "stuur", "verstuur", "bericht sturen"]
    if any(w in bericht_lower for w in email_woorden):
        # Probeer gegevens uit bericht te halen, anders gebruik standaard
        aan = JOUW_EMAIL
        onderwerp = "Bericht van Henrico Agent"
        inhoud = gebruiker_bericht

        # Zoek naar emailadres in bericht
        import re as re2
        email_match = re2.search(r'[\w.-]+@[\w.-]+\.\w+', gebruiker_bericht)
        if email_match:
            aan = email_match.group()

        # Laat Claude de details invullen
        try:
            prep_response = claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                system="Extraheer uit het verzoek: aan wie (emailadres), het onderwerp en de inhoud van de e-mail. Geef terug als JSON: {\"aan\": \"...\", \"onderwerp\": \"...\", \"inhoud\": \"...\"}. Alleen JSON, geen uitleg.",
                messages=[{"role": "user", "content": f"Verzoek: {gebruiker_bericht}\nStandaard emailadres als niets opgegeven: {JOUW_EMAIL}"}]
            )
            import json as json2
            tekst = prep_response.content[0].text.strip()
            tekst = tekst.replace("```json", "").replace("```", "").strip()
            email_data = json2.loads(tekst)
            aan = email_data.get("aan", aan)
            onderwerp = email_data.get("onderwerp", onderwerp)
            inhoud = email_data.get("inhoud", inhoud)
        except:
            pass

        return stuur_email_via_mcp(aan, onderwerp, inhoud)

    # Algemene vraag — stuur naar Claude
    try:
        response = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=SYSTEEM_PROMPT,
            messages=[{"role": "user", "content": gebruiker_bericht}]
        )
        for blok in response.content:
            if hasattr(blok, "text"):
                return blok.text
        return "Ik kon geen antwoord genereren. Probeer het opnieuw."
    except Exception as e:
        return f"Fout: {str(e)}"

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
    return "Henrico Agent v3 draait! 🤖", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)
