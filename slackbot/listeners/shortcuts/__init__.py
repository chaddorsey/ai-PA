from slack_bolt import App
from listeners.shortcuts.sample_shortcut import sample_shortcut_callback
from listeners.shortcuts.send_to_tasks import (
    send_to_tasks_callback,
    send_to_tasks_modal_callback,
    send_to_tasks_view_callback,
)


def register(app: App):
    app.shortcut("sample_shortcut_id")(sample_shortcut_callback)
    app.shortcut("send_to_tasks")(send_to_tasks_callback)
    app.shortcut("send_to_tasks_modal")(send_to_tasks_modal_callback)
    app.view("send_to_tasks_view")(send_to_tasks_view_callback)
