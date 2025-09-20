# state_store/get_user_state.py
import logging
from state_store.user_identity import UserIdentity  # keep import for type hinting

logger = logging.getLogger(__name__)

def get_user_state(user_id: str, is_app_home: bool = False) -> UserIdentity | None:
    """
    Provider selection is disabled for now. Always return None.
    """
    return None
