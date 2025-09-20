from slack_bolt import App
from listeners.views.sample_view import sample_view_callback


def register(app: App):
    app.view("sample_view_id")(sample_view_callback)
