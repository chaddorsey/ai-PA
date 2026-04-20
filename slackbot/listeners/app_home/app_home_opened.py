# listeners/app_home/app_home_opened.py
#
# Silent handler for the `app_home_opened` event. Without a registered handler
# Bolt logs "Unsuccessful Bolt execution result (status: 404, body: unhandled
# request)" every time someone opens the bot's Home tab or DM pane.
#
# Previously this file published a Home view via client.views_publish, but that
# produced too much API noise (one publish per user per open). We keep the file
# so the event is ack'd cleanly, but do nothing — no view, no logging.
from slack_bolt import App


def register(app: App):
    @app.event("app_home_opened")
    def handle_app_home_opened(event, logger):
        # Intentional no-op: acknowledge the event so Bolt doesn't log a 404.
        pass
