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

# --- Apps initialiseren ---
slack_app = App(token=SLACK_BOT_TOKEN, signing_secret=SLACK_SIGNING_SECRET)
flask_app = Flask(__name__)
handler = SlackRequestHandler(slack_app)
claude = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# --- Systeem prompt ---
SYSTEEM_PROMPT = f"""Je bent Henrico's persoonlijke AI-assistent via Slack.
Vandaag is het: {datetime.datetime.now().strftime("%A %d %B %Y")}
Henrico's e-mailadres: {JOUW_EMAIL}

Je kunt het volgende doen:
- 🌤️ Weerbericht opzoeken
- 💬 Vragen beantwoorden
- 📰 Algemene informatie geven

Voor e-mails en agenda: geef aan dat Henrico dit via Claude.ai moet regelen.
Antwoord altijd in het Nederlands, kort en duidelijk.
"""

# --- Weerbericht ophalen via wttr.in ---
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

# --- Verwerk bericht ---
def verwerk_bericht(gebruiker_bericht):
    bericht_lower = gebruiker_bericht.lower()

    # Weerbericht detecteren
    weer_woorden = ["weerbericht", "weer", "temperatuur", "regen", "zon", "graden", "buien"]
    if any(w in bericht_lower for w in weer_woorden):
        stad = "Nijkerk"
        woorden = gebruiker_bericht.split()
        for i, woord in enumerate(woorden):
            if woord.lower() in ["voor", "in", "van"] and i + 1 < len(woorden):
                mogelijke_stad = woorden[i + 1].strip(".,!?")
                if len(mogelijke_stad) > 2:
                    stad = mogelijke_stad
                    break
        return zoek_weerbericht(stad)

    # E-mail detecteren — doorsturen naar Claude.ai
    email_woorden = ["mail", "e-mail", "email", "stuur", "verstuur"]
    if any(w in bericht_lower for w in email_woorden):
        return (
            f"📧 *E-mail verzoek ontvangen!*\n\n"
            f"Ik kan e-mails helaas niet zelf versturen vanuit Slack.\n\n"
            f"✅ *Ga naar Claude.ai en typ:*\n"
            f"_{gebruiker_bericht}_\n\n"
            f"Claude.ai verstuurt de e-mail dan direct via Gmail! 🚀"
        )

    # Agenda detecteren
    agenda_woorden = ["agenda", "afspraak", "calendar", "planning", "vergadering"]
    if any(w in bericht_lower for w in agenda_woorden):
        return (
            f"📅 *Agenda verzoek ontvangen!*\n\n"
            f"Ik kan je agenda helaas nog niet beheren vanuit Slack.\n\n"
            f"✅ *Ga naar Claude.ai en typ:*\n"
            f"_{gebruiker_bericht}_\n\n"
            f"Claude.ai regelt het dan direct! 🚀"
        )

    # Algemene vraag via Claude
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
    say("Eén momentje... ⏳")
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
    return "Henrico Agent v5 draait! 🤖", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)
