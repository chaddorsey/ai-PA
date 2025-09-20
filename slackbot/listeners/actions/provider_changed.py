from slack_bolt import App
from state_store.set_user_state import set_user_state

def register(app: App):
    @app.action("provider_changed")
    def provider_changed(ack, body, client):
        ack()
        user = body["user"]["id"]
        provider = body["actions"][0]["selected_option"]["value"]
        set_user_state(user, provider)
        client.chat_postMessage(channel=user, text=f"Got it — provider set to *{provider}*.")
