from slack_bolt import App
from listeners.app_home.app_home_opened import register as reg_home
from listeners.actions.provider_changed import register as reg_action
from listeners.commands.ask_bolty import register as reg_cmd
from listeners.events.app_mentioned import register as reg_mention
from listeners.messages.message_im import register as reg_dm
from listeners.workflows.summarize_function import register as reg_wf

def register_listeners(app: App):
    reg_home(app)
    reg_action(app)
    reg_cmd(app)
    reg_mention(app)
    reg_dm(app)
    reg_wf(app)
