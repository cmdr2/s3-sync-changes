import os
import sys
import subprocess
import hashlib
import fnmatch
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import argparse


def get_local_etag(path: Path, chunk_size=8 * 1024 * 1024):
    md5s = []
    with open(path, "rb") as f:
        while True:
            data = f.read(chunk_size)
            if not data:
                break
            md5s.append(hashlib.md5(data).digest())

    if not md5s:
        return None

    if len(md5s) == 1:
        # For single-part, S3 ETag is the MD5 of the file content
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    else:
        digests = b"".join(md5s)
        return f"{hashlib.md5(digests).hexdigest()}-{len(md5s)}"


def get_remote_etags(bucket: str, prefix: str = ""):
    cmd = ["aws", "s3api", "list-objects-v2", "--bucket", bucket, "--output", "json"]
    if prefix:
        cmd += ["--prefix", prefix]
    result = subprocess.run(cmd, capture_output=True, check=True, text=True)
    data = json.loads(result.stdout)
    objects = data.get("Contents", [])
    etags = {}
    for obj in objects:
        etags[obj["Key"]] = obj["ETag"].strip('"')
    return etags


def upload_file(
    bucket: str,
    key: str,
    path: Path,
    idx: int,
    total: int,
    lock: Lock,
    acl: str = None,
    dryrun: bool = False,
    verbose: bool = False,
):
    cmd = ["aws", "s3api", "put-object", "--bucket", bucket, "--key", key, "--body", str(path)]
    if acl:
        cmd += ["--acl", acl]
    if verbose:
        print(cmd)
    # if not dryrun:
    #     subprocess.run(cmd, check=True)
    with lock:
        print(f"[{idx}/{total}] Uploaded {key}")


def parse_s3_dest(dest):
    if not dest.startswith("s3://"):
        print("Destination must start with s3://")
        sys.exit(1)
    dest_path = dest[5:]
    if "/" in dest_path:
        bucket, prefix = dest_path.split("/", 1)
    else:
        bucket, prefix = dest_path, ""
    return bucket, prefix


def is_excluded(rel_key, excludes):
    for pattern in excludes:
        if fnmatch.fnmatch(rel_key, pattern):
            return True
    return False


def discover_files(source_path, excludes):
    files = []
    if source_path.is_file():
        rel_key = source_path.name
        if not is_excluded(rel_key, excludes):
            files.append((rel_key, source_path))
    else:
        for root, dirs, fnames in os.walk(source_path):
            # Exclude directories
            dirs[:] = [
                d
                for d in dirs
                if not is_excluded(str(Path(root, d).relative_to(source_path)).replace("\\", "/"), excludes)
            ]
            for fname in fnames:
                path = Path(root) / fname
                rel_key = str(path.relative_to(source_path)).replace("\\", "/")
                if not is_excluded(rel_key, excludes):
                    files.append((rel_key, path))
    return files


def plan_uploads(files, bucket, prefix, verbose):
    to_upload = []
    remote_etags = get_remote_etags(bucket, prefix)
    for rel_key, path in files:
        key = f"{prefix}/{rel_key}" if prefix else rel_key
        key = key.lstrip("/")
        local_etag = get_local_etag(path)
        remote_etag = remote_etags.get(key)
        if local_etag != remote_etag:
            if verbose:
                print(f"Scheduling upload: {key} (local etag: {local_etag}, remote etag: {remote_etag})")
            to_upload.append((key, path))
    return to_upload


def sync(
    source: str, dest: str, workers: int = 4, acl: str = None, dryrun: bool = False, excludes=[], verbose: bool = False
):
    bucket, prefix = parse_s3_dest(dest)
    source_path = Path(source)
    if not source_path.exists():
        print(f"Source path does not exist: {source}")
        sys.exit(1)

    files = discover_files(source_path, excludes)
    to_upload = plan_uploads(files, bucket, prefix, verbose)
    total = len(to_upload)
    if total == 0:
        print("All files are up to date.")
        return

    print(f"Uploading {total} files...")
    lock = Lock()
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(upload_file, bucket, key, path, i + 1, total, lock, acl, dryrun, verbose)
            for i, (key, path) in enumerate(to_upload)
        ]
        for _ in as_completed(futures):
            pass


if __name__ == "__main__":
    print("WARNING: The current version only syncs up to 1000 files!\n")

    parser = argparse.ArgumentParser(description="Sync local files to S3 path.")
    parser.add_argument("source", help="Source file or directory")
    parser.add_argument("dest", help="Destination S3 path (s3://bucket/prefix)")
    parser.add_argument("--acl", help="Canned ACL to apply to uploaded files", default=None)
    parser.add_argument("--dryrun", action="store_true", help="Perform a dry run without uploading")
    parser.add_argument("--workers", type=int, default=4, help="Number of parallel uploads")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Exclude files/folders (supports wildcards, can be used multiple times)",
    )
    args = parser.parse_args()
    sync(args.source, args.dest, args.workers, args.acl, args.dryrun, args.exclude, args.verbose)
