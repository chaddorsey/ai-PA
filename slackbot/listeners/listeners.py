from slack_bolt import App
# from listeners.app_home.app_home_opened import register as reg_home
from listeners.actions.provider_changed import register as reg_action
from listeners.actions.proposal_actions import register as reg_proposal_actions
from listeners.actions.notification_actions import register as reg_notification_actions
from listeners.actions.modal_actions import register_modal_actions
from listeners.commands.ask_bolty_debug import register as reg_cmd
from listeners.commands.schedule_command import register as reg_schedule_cmd
from listeners.events.app_mentioned import register as reg_mention
from listeners.events.assistant_thread_started import register as reg_assistant_started
from listeners.events.assistant_thread_context_changed import register as reg_assistant_context
# from listeners.events.message_reaction import register as reg_reaction
from listeners.messages.message_im_hybrid import register as reg_dm
from listeners.shortcuts import register as reg_shortcuts
from listeners.views.proposal_confirm import register as reg_proposal_confirm
from listeners.views.notification_modify import register as reg_notification_modify
from listeners.workflows.summarize_function import register as reg_wf

def register_listeners(app: App):
    # reg_home(app)  # Disabled to reduce views.publish noise
    reg_action(app)
    reg_proposal_actions(app)
    reg_notification_actions(app)
    register_modal_actions(app)
    reg_cmd(app)
    reg_schedule_cmd(app)
    reg_mention(app)
    reg_assistant_started(app)
    reg_assistant_context(app)
    # reg_reaction(app)
    reg_dm(app)
    reg_shortcuts(app)
    reg_proposal_confirm(app)
    reg_notification_modify(app)
    reg_wf(app)
