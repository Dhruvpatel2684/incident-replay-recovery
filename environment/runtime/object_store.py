"""Object store operations for reading and writing objects."""

import os
import json


STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "store")
OBJECTS_DIR = os.path.join(STORE_DIR, "objects")
REFS_DIR = os.path.join(STORE_DIR, "refs")
INDEX_FILE = os.path.join(STORE_DIR, "index.json")


def ensure_dirs():
    """Ensure store directories exist."""
    os.makedirs(OBJECTS_DIR, exist_ok=True)
    os.makedirs(REFS_DIR, exist_ok=True)


def write_object(obj_hash, content):
    """Write an object to the store with the given hash as filename."""
    ensure_dirs()
    path = os.path.join(OBJECTS_DIR, obj_hash)
    with open(path, "w") as f:
        f.write(content)


def read_object(obj_hash):
    """Read an object's content by its hash."""
    path = os.path.join(OBJECTS_DIR, obj_hash)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return f.read()


def object_exists(obj_hash):
    """Check if an object exists in the store."""
    return os.path.exists(os.path.join(OBJECTS_DIR, obj_hash))


def list_objects():
    """List all object hashes in the store."""
    ensure_dirs()
    return os.listdir(OBJECTS_DIR)


def write_ref(ref_name, commit_hash):
    """Write a reference (branch pointer) to a commit hash."""
    ensure_dirs()
    path = os.path.join(REFS_DIR, ref_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(commit_hash)


def read_ref(ref_name):
    """Read a reference's commit hash."""
    path = os.path.join(REFS_DIR, ref_name)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return f.read().strip()


def write_index(index_data):
    """Write the index (staging area) mapping paths to blob hashes."""
    ensure_dirs()
    with open(INDEX_FILE, "w") as f:
        json.dump(index_data, f, indent=2)


def read_index():
    """Read the index mapping."""
    if not os.path.exists(INDEX_FILE):
        return {}
    with open(INDEX_FILE, "r") as f:
        return json.load(f)
