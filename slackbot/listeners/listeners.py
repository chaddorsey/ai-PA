import logging
from slack_bolt import App
from listeners.app_home.app_home_opened import register as reg_home

_probe_log = logging.getLogger("bolt_event_probe")
_probe_log.setLevel(logging.INFO)
from listeners.actions.provider_changed import register as reg_action
from listeners.actions.proposal_actions import register as reg_proposal_actions
from listeners.actions.notification_actions import register as reg_notification_actions
from listeners.actions.modal_actions import register_modal_actions
from listeners.commands.ask_bolty_debug import register as reg_cmd
from listeners.commands.schedule_command import register as reg_schedule_cmd
from listeners.commands.clear_command import register as reg_clear_cmd
from listeners.events.app_mentioned import register as reg_mention
from listeners.events.chad_mention_signal import register as reg_chad_mention_signal
from listeners.events.assistant_thread_started import register as reg_assistant_started
from listeners.events.assistant_thread_context_changed import register as reg_assistant_context
# from listeners.events.message_reaction import register as reg_reaction
from listeners.messages.message_im_hybrid import register as reg_dm
from listeners.shortcuts import register as reg_shortcuts
from listeners.views.proposal_confirm import register as reg_proposal_confirm
from listeners.views.notification_modify import register as reg_notification_modify
from listeners.workflows.summarize_function import register as reg_wf

def register_listeners(app: App):
    @app.use
    def _probe_every_event(body, next, logger):
        try:
            top = body.get("type", "?")
            ev = body.get("event") or {}
            ev_type = ev.get("type", "?")
            ev_subtype = ev.get("subtype", "-")
            ev_channel_type = ev.get("channel_type", "-")
            ev_channel = ev.get("channel", "-")
            ev_user = ev.get("user", "-")
            _probe_log.info(
                "BOLT_PROBE top=%s event=%s subtype=%s ch_type=%s ch=%s user=%s",
                top, ev_type, ev_subtype, ev_channel_type, ev_channel, ev_user,
            )
        except Exception as e:
            _probe_log.warning("BOLT_PROBE error: %s", e)
        next()

    reg_home(app)  # silent no-op; acks app_home_opened without publishing a view
    reg_action(app)
    reg_proposal_actions(app)
    reg_notification_actions(app)
    register_modal_actions(app)
    reg_cmd(app)
    reg_schedule_cmd(app)
    reg_clear_cmd(app)
    reg_mention(app)
    reg_chad_mention_signal(app)  # 2026-05-12: now middleware (next-chaining), not a competing @app.event("message") listener — see chad_mention_signal.register() for rationale
    reg_assistant_started(app)
    reg_assistant_context(app)
    # reg_reaction(app)
    reg_dm(app)
    reg_shortcuts(app)
    reg_proposal_confirm(app)
    reg_notification_modify(app)
    reg_wf(app)
