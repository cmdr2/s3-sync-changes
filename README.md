## s3-sync-changes

Deploy to S3 by checking whether the file contents have actually changed, rather than simply checking the file timestamp like `aws s3 sync` does.

### Why?
- `aws s3 sync` ends up uploading *everything* when run in a GitHub Action, because git resets the file timestamps upon checkout. The commonly recommended workaround of `--size-only` is risky, since you might miss uploading changes if the file size doesn't change (e.g. changing a single digit in a config file).
- Static site generators for large static websites, which often regenerate thousands of files even if the contents haven't changed.

### Usage
```bash
python s3-sync-changes.py [-h] [--acl ACL] [--dryrun] [--workers WORKERS] [--verbose] [--exclude EXCLUDE] source dest
```

### Example
```bash
python s3-sync-changes.py . s3://my-bucket/path/to/dir --exclude .git --exclude README.md --acl public-read
```

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
