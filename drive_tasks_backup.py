import os
import json
import base64
import sqlite3
import tempfile

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive"]
FILE_NAME = os.environ.get("TAREAS_DRIVE_FILENAME", "tareas_simple.db")


def _load_json_from_b64(env_name):
    raw_b64 = (os.environ.get(env_name) or "").strip()
    if not raw_b64:
        raise RuntimeError(f"Falta {env_name}")

    raw_json = base64.b64decode(raw_b64).decode("utf-8")
    return json.loads(raw_json)


def _get_oauth_token_info():
    token_info = _load_json_from_b64("GOOGLE_OAUTH_TOKEN_JSON_B64")

    if token_info.get("client_id") and token_info.get("client_secret"):
        return token_info

    client_info = _load_json_from_b64("GOOGLE_OAUTH_CLIENT_SECRET_JSON_B64")

    oauth_client = (
        client_info.get("installed")
        or client_info.get("web")
        or client_info
    )

    if not token_info.get("client_id"):
        token_info["client_id"] = oauth_client.get("client_id")

    if not token_info.get("client_secret"):
        token_info["client_secret"] = oauth_client.get("client_secret")

    if not token_info.get("token_uri"):
        token_info["token_uri"] = oauth_client.get("token_uri", "https://oauth2.googleapis.com/token")

    return token_info


def _get_drive_service():
    token_info = _get_oauth_token_info()

    creds = Credentials.from_authorized_user_info(token_info, scopes=SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _get_folder_id():
    folder_id = (os.environ.get("GOOGLE_DRIVE_FOLDER_ID") or "").strip()
    if not folder_id:
        raise RuntimeError("Falta GOOGLE_DRIVE_FOLDER_ID")
    return folder_id


def _find_file(service, folder_id, file_name):
    safe_file_name = file_name.replace("'", "\\'")
    q = f"name = '{safe_file_name}' and '{folder_id}' in parents and trashed = false"

    result = service.files().list(
        q=q,
        spaces="drive",
        fields="files(id, name, modifiedTime)",
        orderBy="modifiedTime desc",
        pageSize=10,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True
    ).execute()

    files = result.get("files", [])
    return files[0] if files else None


def _make_sqlite_snapshot(db_path):
    fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    src = None
    dst = None

    try:
        src = sqlite3.connect(db_path, timeout=30, check_same_thread=False)
        dst = sqlite3.connect(temp_path, timeout=30, check_same_thread=False)
        src.backup(dst)
        dst.commit()
        return temp_path
    finally:
        try:
            if dst:
                dst.close()
        except:
            pass

        try:
            if src:
                src.close()
        except:
            pass


def backup_db_to_drive(db_path):
    if not os.path.exists(db_path):
        return False

    folder_id = _get_folder_id()
    service = _get_drive_service()
    snapshot_path = _make_sqlite_snapshot(db_path)

    try:
        existing = _find_file(service, folder_id, FILE_NAME)
        media = MediaFileUpload(
            snapshot_path,
            mimetype="application/octet-stream",
            resumable=False
        )

        if existing:
            service.files().update(
                fileId=existing["id"],
                media_body=media,
                supportsAllDrives=True
            ).execute()
        else:
            service.files().create(
                body={
                    "name": FILE_NAME,
                    "parents": [folder_id]
                },
                media_body=media,
                fields="id",
                supportsAllDrives=True
            ).execute()

        return True
    finally:
        try:
            os.remove(snapshot_path)
        except:
            pass


def restore_db_from_drive_if_missing(db_path):
    if os.path.exists(db_path) and os.path.getsize(db_path) > 0:
        return False

    folder_id = _get_folder_id()
    service = _get_drive_service()
    existing = _find_file(service, folder_id, FILE_NAME)

    if not existing:
        return False

    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    try:
        request = service.files().get_media(
            fileId=existing["id"],
            supportsAllDrives=True
        )

        with open(temp_path, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()

        os.replace(temp_path, db_path)
        return True
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except:
            pass


def backup_db_to_drive_safely(db_path):
    try:
        ok = backup_db_to_drive(db_path)
        print(f"[DRIVE BACKUP] ok={ok}")
    except Exception as e:
        print(f"[DRIVE BACKUP ERROR] {e}")


def restore_db_from_drive_if_missing_safely(db_path):
    try:
        ok = restore_db_from_drive_if_missing(db_path)
        print(f"[DRIVE RESTORE] ok={ok}")
    except Exception as e:
        print(f"[DRIVE RESTORE ERROR] {e}")