import os
import re
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

# --- Systeem prompt voor Claude ---
SYSTEEM_PROMPT = f"""Je bent een handige Nederlandse assistent die luistert via Slack.
Je helpt de gebruiker met taken zoals:
- Weerbericht opzoeken
- Informatie zoeken op het internet
- E-mails opstellen (geef de tekst terug zodat de gebruiker hem kan kopiëren)
- Vragen beantwoorden

Antwoord altijd in het Nederlands, kort en duidelijk.
Het e-mailadres van de gebruiker is: {JOUW_EMAIL}

Als iemand vraagt een e-mail te sturen, schrijf dan de e-mail uit en zeg dat ze die kunnen kopiëren.
Als iemand vraagt naar het weerbericht, zoek dan de stad op die ze noemen (standaard: Nijkerk).
"""

# --- Luister naar berichten waarin de bot wordt genoemd (@bot) ---
@slack_app.event("app_mention")
def handle_mention(event, say):
    gebruiker_bericht = re.sub(r"<@[^>]+>", "", event["text"]).strip()
    
    if not gebruiker_bericht:
        say("Hoi! Zeg maar wat ik voor je kan doen 😊")
        return

    say(f"Eén momentje, ik ga dat voor je regelen... ⏳")

    try:
        response = claude.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=SYSTEEM_PROMPT,
            messages=[
                {"role": "user", "content": gebruiker_bericht}
            ]
        )
        antwoord = response.content[0].text
        say(antwoord)

    except Exception as e:
        say(f"Oeps, er ging iets mis: {str(e)}")


# --- Luister ook naar directe berichten ---
@slack_app.event("message")
def handle_dm(event, say):
    # Alleen reageren op DMs (channel_type = "im"), niet op kanaalberichten
    if event.get("channel_type") == "im" and not event.get("bot_id"):
        gebruiker_bericht = event.get("text", "").strip()
        
        if not gebruiker_bericht:
            return

        say(f"Eén momentje... ⏳")

        try:
            response = claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=1000,
                system=SYSTEEM_PROMPT,
                messages=[
                    {"role": "user", "content": gebruiker_bericht}
                ]
            )
            antwoord = response.content[0].text
            say(antwoord)

        except Exception as e:
            say(f"Oeps, er ging iets mis: {str(e)}")


# --- Flask route voor Slack events ---
@flask_app.route("/slack/events", methods=["POST"])
def slack_events():
    return handler.handle(request)


@flask_app.route("/", methods=["GET"])
def health_check():
    return "Bot draait! 🤖", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    flask_app.run(host="0.0.0.0", port=port)
