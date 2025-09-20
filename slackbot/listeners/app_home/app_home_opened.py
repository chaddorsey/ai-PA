# listeners/app_home/app_home_opened.py
from slack_bolt import App

def register(app: App):
    @app.event("app_home_opened")
    def show_home(event, client, logger):
        user = event["user"]
        blocks = [
            {"type":"section","text":{"type":"mrkdwn","text":"*Welcome!*"}},
            {"type":"section","text":{"type":"mrkdwn","text":"This bot is currently **locked to OpenAI**.\n• DM me from the *Messages* tab\n• Or mention me in a channel with `@YourBot`"}},
            {"type":"context","elements":[{"type":"mrkdwn","text":"You can re-enable provider selection later."}]}
        ]
        client.views_publish(user_id=user, view={"type":"home","blocks":blocks})
