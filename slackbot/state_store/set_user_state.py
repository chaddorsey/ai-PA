import json
import os
from state_store.user_identity import UserIdentity
from state_store.file_state_store import FileStateStore

store = FileStateStore()

def set_user_state(user_id: str, provider: str, model: str | None = None, is_app_home: bool = False):
    """
    Save the user's chosen provider/model to ./data/{user_id}.
    Always writes a JSON with 'provider' and 'model' keys.
    """
    try:
        ident = UserIdentity(user_id=user_id, provider=provider, model=model)
        filepath = f"./data/{user_id}"
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w") as f:
            json.dump({"provider": ident.provider, "model": ident.model}, f)
        # Also keep the FileStateStore in sync if you want to reuse it
        store.set(ident)
    except Exception as e:
        raise ValueError(f"Error saving user state: {e}")
