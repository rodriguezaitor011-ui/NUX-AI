import json
from app import database


def test_save_and_load_users(tmp_path):
    users_file = tmp_path / "users.json"
    database.USERS_FILE = str(users_file)

    # initialize empty file
    users_file.write_text(json.dumps([]), encoding="utf-8")

    users = [{"id": 1, "username": "u1", "email": "a@b.com", "hashed_password": "x"}]
    database.save_users(users)

    loaded = database.load_users()
    assert isinstance(loaded, list)
    assert loaded and loaded[0]["username"] == "u1"


def test_save_and_load_history(tmp_path):
    hist_file = tmp_path / "chat_history.json"
    database.CHAT_HISTORY_FILE = str(hist_file)

    hist_file.write_text(json.dumps([]), encoding="utf-8")

    history = [{"id": 1, "username": "u1", "message": "hi"}]
    database.save_chat_history(history)

    loaded = database.load_chat_history()
    assert isinstance(loaded, list)
    assert loaded and loaded[0]["message"] == "hi"
