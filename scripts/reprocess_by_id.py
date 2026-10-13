import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv()

from config import Settings
from main import process_single_message
from metaforge_api import IdAllocator
from outlook_graph import acquire_token_from_env, fetch_message_by_id
from processed_store import ProcessedStore
from utils import setup_logging

def reprocess_message(mid: str):
    settings = Settings.from_env()
    setup_logging(settings.log_level)
    token = acquire_token_from_env()
    mailbox = settings.mailbox_upn

    print(f"Fetching message {mid} from {mailbox}...")
    raw = fetch_message_by_id(token, mailbox, mid)
    subject = raw.get("subject", "")
    print(f"Fetched subject: {subject}")

    id_db = settings.metaforge_sqlite_path if settings.metaforge_mode == "sqlite" else settings.metaforge_id_db
    allocator = IdAllocator(id_db)

    with ProcessedStore(settings.processed_db) as store:
        # Clear pipeline state
        store._conn.execute("DELETE FROM pipeline_state WHERE graph_id = ?", (mid,))
        store._conn.execute("DELETE FROM processed WHERE graph_id = ?", (mid,))
        store._conn.execute("DELETE FROM requirement_fingerprints WHERE graph_id = ?", (mid,))
        store._conn.execute("DELETE FROM seen_messages WHERE graph_id = ?", (mid,))
        store._conn.execute("DELETE FROM email_dispositions WHERE message_id = ? OR graph_id = ?", (mid, mid))
        store._conn.commit()
        print("Cleared previous state from processed_messages.db")

        synced = process_single_message(
            raw,
            token=token,
            mailbox=mailbox,
            settings=settings,
            allocator=allocator,
            store=store,
            skip_classifier=False,
            sync_via_task=False,
        )

    allocator.close()
    print(f"Done! Synced requirement rows: {synced}")
    return synced

if __name__ == "__main__":
    mid = sys.argv[1] if len(sys.argv) > 1 else 'AAMkADE3NDllMmZlLTU3NmUtNGI2MS1hZjA4LTEwNzAzZWZjYzUxOABGAAAAAABG8jimhHIeTrzzeDCLnQR9BwAIHnK_cnn0TIdFuplFGEzAAAAAAAEMAAAIHnK_cnn0TIdFuplFGEzAAACF0dRDAAA='
    reprocess_message(mid)
