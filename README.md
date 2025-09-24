## s3-sync-changes

Deploy to S3 by checking whether the file contents have actually changed, rather than simply checking the file timestamp like `aws s3 sync` does.

### Why?
- `aws s3 sync` ends up uploading *everything* when run in a GitHub Action, because git resets the file timestamps upon checkout. The commonly recommended workaround of `--size-only` is risky, since you might miss uploading changes if the file size doesn't change (e.g. changing a single digit in a config file).
- Static site generators for large static websites often regenerate thousands of files even if the contents haven't changed.

**Important:** This script isn't a good idea for large buckets (>10k objects) or buckets with frequent syncs (several times a day), because `ListBucket` requests cost more.

### Usage
`
python s3-sync-changes.py [-h] [--acl ACL] [--dryrun] [--workers WORKERS] [--max-objects MAX_OBJECTS] [--verbose] [--exclude EXCLUDE] [--content-encoding ENCODING] [--auto-content-type] source dest
`

It calls the `aws s3api` command under-the-hood, so please ensure that [AWS CLI](https://docs.aws.amazon.com/streams/latest/dev/setup-awscli.html) is installed and configured correctly.

### Example

`
python s3-sync-changes.py . s3://my-bucket/path/to/dir --exclude .git --exclude README.md --acl public-read --auto-content-type
`

#### About --auto-content-type
Use `--auto-content-type` to automatically set the `Content-Type` header based on the file extension (using Python's `mimetypes`). This helps browsers and clients interpret files correctly when served from S3.

### How does this work?
It calls `aws s3api list-objects-v2` upon a bucket (with an optional `prefix`), and compares the returned `Etag` values with the `Etag` values of the local files. It then uploads the changed files by calling `aws s3 cp` for each file, applying any specified flags such as `--acl`, `--content-encoding`, and `--content-type` (if `--auto-content-type` is enabled).

The files are uploaded on multiple threads, configurable using the `--workers` argument. E.g. `--workers 4` to upload on 4 threads.

### About --max-objects
By default, the script will sync up to 3000 objects. This is a safety limit to prevent accidental mass operations on very large buckets or local directories. If you need to sync more than 3000 files, you can increase this limit using the `--max-objects` argument:

```bash
python s3-sync-changes.py . s3://my-bucket/path --max-objects 10000
```

If the number of local files or remote S3 objects exceeds this limit, the script will exit with an error. This helps avoid excessive AWS API calls and accidental large syncs. Adjust the value as needed for your use case.

### Required IAM Permissions

The script uses the AWS CLI to interact with S3. The following IAM permissions are required for the S3 bucket you are syncing to:

```json
{
	"Version": "2012-10-17",
	"Statement": [
		{
			"Effect": "Allow",
			"Action": [
				"s3:ListBucket",
				"s3:PutObject"
			],
			"Resource": [
				"arn:aws:s3:::YOUR_BUCKET_NAME",
				"arn:aws:s3:::YOUR_BUCKET_NAME/YOUR_PREFIX/*"
			]
		}
	]
}
```

If you use the `--acl` option, you will also need `s3:PutObjectAcl` permission:

```json
"Action": [
	"s3:ListBucket",
	"s3:PutObject",
	"s3:PutObjectAcl"
]
```

Replace `YOUR_BUCKET_NAME` with the actual name of your S3 bucket.
