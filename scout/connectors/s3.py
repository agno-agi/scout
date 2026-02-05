"""S3 connector with support for real S3 buckets and mock data for development.

S3 is the primary connector for demos and most enterprise deployments.
"""

from typing import Any

from scout.connectors.base import BaseConnector
from scout.connectors.s3_mock_data import MOCK_BUCKETS, MOCK_CONTENTS, MOCK_FILES

# Optional boto3 import - only required for real S3 connections
try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError

    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    boto3 = None  # type: ignore
    ClientError = Exception  # type: ignore
    NoCredentialsError = Exception  # type: ignore


class S3Connector(BaseConnector):
    """S3 connector with support for real S3 buckets and mock data fallback.

    Args:
        bucket: Default bucket name to use
        access_key: AWS access key ID (optional, uses env/IAM if not provided)
        secret_key: AWS secret access key (optional, uses env/IAM if not provided)
        region: AWS region (default: us-east-1)
        use_mock: Force mock mode even if credentials are available
    """

    def __init__(
        self,
        bucket: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
        use_mock: bool = False,
    ):
        self._authenticated = False
        self._default_bucket = bucket
        self._access_key = access_key
        self._secret_key = secret_key
        self._region = region
        self._use_mock = use_mock
        self._s3_client = None
        self._s3_resource = None
        self._mock_reason: str | None = None  # Why we're in mock mode

    @property
    def source_type(self) -> str:
        return "s3"

    @property
    def source_name(self) -> str:
        return "S3"

    @property
    def is_mock_mode(self) -> bool:
        """Check if connector is running in mock mode."""
        return self._use_mock or not BOTO3_AVAILABLE or self._s3_client is None

    @property
    def connection_status(self) -> dict[str, Any]:
        """Get detailed connection status for debugging."""
        return {
            "is_mock_mode": self.is_mock_mode,
            "mock_reason": self._mock_reason,
            "boto3_available": BOTO3_AVAILABLE,
            "use_mock_forced": self._use_mock,
            "authenticated": self._authenticated,
            "has_client": self._s3_client is not None,
            "region": self._region,
            "has_explicit_credentials": bool(self._access_key and self._secret_key),
        }

    def authenticate(self) -> bool:
        """Authenticate with S3 using provided credentials or environment/IAM."""
        if self._use_mock:
            self._mock_reason = "use_mock=True was set explicitly"
            self._authenticated = True
            return True

        if not BOTO3_AVAILABLE:
            self._mock_reason = "boto3 is not installed (pip install boto3)"
            self._authenticated = True
            return True

        try:
            # Build client kwargs
            client_kwargs: dict[str, Any] = {"region_name": self._region}
            if self._access_key and self._secret_key:
                client_kwargs["aws_access_key_id"] = self._access_key
                client_kwargs["aws_secret_access_key"] = self._secret_key

            self._s3_client = boto3.client("s3", **client_kwargs)
            self._s3_resource = boto3.resource("s3", **client_kwargs)

            # Verify credentials by listing buckets
            self._s3_client.list_buckets()
            self._mock_reason = None  # Successfully connected to real S3
            self._authenticated = True
            return True

        except NoCredentialsError:
            # No credentials available, fall back to mock mode
            self._s3_client = None
            self._s3_resource = None
            self._mock_reason = (
                "No AWS credentials found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY "
                "environment variables, or pass access_key/secret_key to the constructor, "
                "or configure IAM role credentials."
            )
            self._authenticated = True
            return True

        except ClientError as e:
            # Invalid credentials or permissions
            self._s3_client = None
            self._s3_resource = None
            self._authenticated = False
            raise ValueError(f"S3 authentication failed: {e}")

    def list_buckets(self) -> list[dict[str, Any]]:
        """List available S3 buckets."""
        if self.is_mock_mode:
            # Add a hint that we're using mock data
            buckets = [dict(b) for b in MOCK_BUCKETS]  # Copy to avoid mutating
            for b in buckets:
                b["_mock"] = True
            return buckets

        try:
            response = self._s3_client.list_buckets()
            buckets = []
            for bucket in response.get("Buckets", []):
                # Get bucket region
                try:
                    location = self._s3_client.get_bucket_location(Bucket=bucket["Name"])
                    region = location.get("LocationConstraint") or "us-east-1"
                except ClientError:
                    region = "unknown"

                buckets.append({
                    "name": bucket["Name"],
                    "region": region,
                    "created": bucket.get("CreationDate", "").isoformat() if bucket.get("CreationDate") else "",
                })
            return buckets

        except ClientError as e:
            raise ValueError(f"Failed to list buckets: {e}")

    def list_items(
        self,
        parent_id: str | None = None,
        item_type: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List files in a bucket or prefix."""
        bucket = parent_id or self._default_bucket

        if not bucket:
            # List buckets if no bucket specified
            buckets = self.list_buckets()
            return [{"id": b["name"], "name": b["name"], "type": "bucket"} for b in buckets]

        # Parse bucket/prefix
        if "/" in bucket:
            bucket_name, prefix = bucket.split("/", 1)
            if not prefix.endswith("/"):
                prefix += "/"
        else:
            bucket_name = bucket
            prefix = ""

        if self.is_mock_mode:
            return self._list_items_mock(bucket_name, prefix, limit)

        return self._list_items_real(bucket_name, prefix, limit)

    def _list_items_mock(self, bucket_name: str, prefix: str, limit: int) -> list[dict[str, Any]]:
        """List items from mock data."""
        files = MOCK_FILES.get(bucket_name, [])

        # Filter by prefix
        if prefix:
            files = [f for f in files if f["key"].startswith(prefix)]

        # Get unique directories at this level
        items: list[dict[str, Any]] = []
        seen_dirs: set[str] = set()

        for f in files:
            key = f["key"]
            if prefix:
                key = key[len(prefix) :].lstrip("/")

            if "/" in key:
                # This is a directory
                dir_name = key.split("/")[0]
                if dir_name not in seen_dirs:
                    seen_dirs.add(dir_name)
                    full_prefix = f"{prefix}{dir_name}/" if prefix else f"{dir_name}/"
                    items.append({
                        "id": f"{bucket_name}/{full_prefix}".rstrip("/"),
                        "name": dir_name,
                        "type": "directory",
                        "prefix": full_prefix,
                    })
            else:
                # This is a file
                items.append({
                    "id": f"s3://{bucket_name}/{f['key']}",
                    "name": key,
                    "type": "file",
                    "key": f["key"],
                    "size": f.get("size", 0),
                    "modified": f.get("modified", ""),
                })

        return items[:limit]

    def _list_items_real(self, bucket_name: str, prefix: str, limit: int) -> list[dict[str, Any]]:
        """List items from real S3 bucket."""
        try:
            items: list[dict[str, Any]] = []

            # Use delimiter to get folder-like behavior
            paginator = self._s3_client.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(
                Bucket=bucket_name,
                Prefix=prefix,
                Delimiter="/",
                PaginationConfig={"MaxItems": limit},
            )

            for page in page_iterator:
                # Add folders (common prefixes)
                for prefix_info in page.get("CommonPrefixes", []):
                    folder_prefix = prefix_info["Prefix"]
                    folder_name = folder_prefix.rstrip("/").split("/")[-1]
                    items.append({
                        "id": f"{bucket_name}/{folder_prefix}".rstrip("/"),
                        "name": folder_name,
                        "type": "directory",
                        "prefix": folder_prefix,
                    })

                # Add files
                for obj in page.get("Contents", []):
                    key = obj["Key"]
                    # Skip if this is just the prefix itself (folder marker)
                    if key == prefix:
                        continue

                    name = key.split("/")[-1]
                    if not name:  # Skip folder markers
                        continue

                    items.append({
                        "id": f"s3://{bucket_name}/{key}",
                        "name": name,
                        "type": "file",
                        "key": key,
                        "size": obj.get("Size", 0),
                        "modified": obj.get("LastModified", "").isoformat() if obj.get("LastModified") else "",
                        "etag": obj.get("ETag", "").strip('"'),
                    })

                if len(items) >= limit:
                    break

            return items[:limit]

        except ClientError as e:
            raise ValueError(f"Failed to list objects in {bucket_name}: {e}")

    def search(
        self,
        query: str,
        filters: dict[str, Any] | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Search for files matching the query.

        Note: S3 does not have native search. This performs:
        - Mock mode: Searches filenames and mock content
        - Real mode: Lists objects and filters by key name (prefix search)

        For full-text search of file contents, consider using a search index.
        """
        if self.is_mock_mode:
            return self._search_mock(query, filters, limit)

        return self._search_real(query, filters, limit)

    def _search_mock(self, query: str, filters: dict[str, Any] | None, limit: int) -> list[dict[str, Any]]:
        """Search in mock data (filename and content)."""
        query_lower = query.lower()
        results: list[dict[str, Any]] = []

        # Determine which buckets to search
        buckets = [filters.get("bucket")] if filters and filters.get("bucket") else list(MOCK_FILES.keys())

        for bucket in buckets:
            if bucket not in MOCK_FILES:
                continue

            for file in MOCK_FILES[bucket]:
                file_key = f"{bucket}/{file['key']}"
                content_key = file_key

                # Search in filename
                if query_lower in file["key"].lower():
                    results.append({
                        "id": f"s3://{file_key}",
                        "bucket": bucket,
                        "key": file["key"],
                        "name": file["key"].split("/")[-1],
                        "match_type": "filename",
                        "modified": file.get("modified", ""),
                    })
                    continue

                # Search in content
                if content_key in MOCK_CONTENTS:
                    content = MOCK_CONTENTS[content_key]
                    if query_lower in content.lower():
                        snippet = _extract_snippet_with_context(content, query)
                        results.append({
                            "id": f"s3://{file_key}",
                            "bucket": bucket,
                            "key": file["key"],
                            "name": file["key"].split("/")[-1],
                            "match_type": "content",
                            "snippet": snippet,
                            "modified": file.get("modified", ""),
                        })

        return results[:limit]

    def _search_real(self, query: str, filters: dict[str, Any] | None, limit: int) -> list[dict[str, Any]]:
        """Search in real S3 by listing and filtering by key name.

        Note: This is a basic filename search. S3 doesn't support content search.
        """
        query_lower = query.lower()
        results: list[dict[str, Any]] = []

        # Determine bucket to search
        bucket_name = filters.get("bucket") if filters else self._default_bucket
        if not bucket_name:
            # Search all accessible buckets
            buckets = self.list_buckets()
            bucket_names = [b["name"] for b in buckets]
        else:
            bucket_names = [bucket_name]

        for bucket in bucket_names:
            try:
                prefix = filters.get("prefix", "") if filters else ""
                paginator = self._s3_client.get_paginator("list_objects_v2")

                for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        # Check if query matches the key
                        if query_lower in key.lower():
                            results.append({
                                "id": f"s3://{bucket}/{key}",
                                "bucket": bucket,
                                "key": key,
                                "name": key.split("/")[-1],
                                "match_type": "filename",
                                "size": obj.get("Size", 0),
                                "modified": obj.get("LastModified", "").isoformat()
                                if obj.get("LastModified")
                                else "",
                            })

                            if len(results) >= limit:
                                return results

            except ClientError:
                # Skip buckets we can't access
                continue

        return results[:limit]

    def read(
        self,
        item_id: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Read file content from S3."""
        # Parse s3://bucket/key format
        if item_id.startswith("s3://"):
            item_id = item_id[5:]

        parts = item_id.split("/", 1)
        if len(parts) != 2:
            return {"error": f"Invalid S3 path: {item_id}"}

        bucket, key = parts

        if self.is_mock_mode:
            return self._read_mock(bucket, key, options)

        return self._read_real(bucket, key, options)

    def _read_mock(self, bucket: str, key: str, options: dict[str, Any] | None) -> dict[str, Any]:
        """Read from mock content."""
        content_key = f"{bucket}/{key}"

        if content_key not in MOCK_CONTENTS:
            return {"error": f"File not found: s3://{content_key}"}

        content = MOCK_CONTENTS[content_key]

        # Handle pagination for large files
        if options and options.get("offset"):
            lines = content.split("\n")
            offset = options.get("offset", 0)
            limit = options.get("limit", 100)
            content = "\n".join(lines[offset : offset + limit])

        return {
            "id": f"s3://{bucket}/{key}",
            "bucket": bucket,
            "key": key,
            "content": content,
            "metadata": {
                "size": len(content),
                "modified": _get_file_modified(bucket, key),
            },
        }

    def _read_real(self, bucket: str, key: str, options: dict[str, Any] | None) -> dict[str, Any]:
        """Read from real S3 bucket."""
        try:
            response = self._s3_client.get_object(Bucket=bucket, Key=key)

            # Read content
            content_bytes = response["Body"].read()

            # Try to decode as text, fall back to base64 for binary
            try:
                content = content_bytes.decode("utf-8")
                is_binary = False
            except UnicodeDecodeError:
                import base64

                content = base64.b64encode(content_bytes).decode("ascii")
                is_binary = True

            # Handle pagination for large text files
            if not is_binary and options and options.get("offset"):
                lines = content.split("\n")
                offset = options.get("offset", 0)
                limit = options.get("limit", 100)
                content = "\n".join(lines[offset : offset + limit])

            return {
                "id": f"s3://{bucket}/{key}",
                "bucket": bucket,
                "key": key,
                "content": content,
                "is_binary": is_binary,
                "metadata": {
                    "size": response.get("ContentLength", 0),
                    "content_type": response.get("ContentType", ""),
                    "modified": response.get("LastModified", "").isoformat() if response.get("LastModified") else "",
                    "etag": response.get("ETag", "").strip('"'),
                },
            }

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "NoSuchKey":
                return {"error": f"File not found: s3://{bucket}/{key}"}
            return {"error": f"Failed to read s3://{bucket}/{key}: {e}"}

    def write(
        self,
        parent_id: str,
        title: str,
        content: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Write a file to S3."""
        # Parse bucket from parent_id
        if parent_id.startswith("s3://"):
            parent_id = parent_id[5:]

        bucket = parent_id.split("/")[0]
        prefix = parent_id.split("/", 1)[1] if "/" in parent_id else ""
        key = f"{prefix}/{title}".lstrip("/") if prefix else title

        if self.is_mock_mode:
            return {
                "id": f"s3://{bucket}/{key}",
                "bucket": bucket,
                "key": key,
                "message": "File written (mock mode - not persisted)",
            }

        try:
            # Determine content type
            content_type = "text/plain"
            if options and options.get("content_type"):
                content_type = options["content_type"]
            elif title.endswith(".json"):
                content_type = "application/json"
            elif title.endswith(".md"):
                content_type = "text/markdown"
            elif title.endswith(".html"):
                content_type = "text/html"

            self._s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType=content_type,
            )

            return {
                "id": f"s3://{bucket}/{key}",
                "bucket": bucket,
                "key": key,
                "message": "File written successfully",
            }

        except ClientError as e:
            return {"error": f"Failed to write s3://{bucket}/{key}: {e}"}

    def update(
        self,
        item_id: str,
        content: str | None = None,
        properties: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a file in S3 (S3 doesn't support partial updates, so this replaces the file)."""
        if self.is_mock_mode:
            return {
                "id": item_id,
                "message": "File updated (mock mode - not persisted)",
            }

        if content is None:
            return {"error": "Content is required for S3 update (S3 doesn't support metadata-only updates)"}

        # Parse item_id
        if item_id.startswith("s3://"):
            item_id = item_id[5:]

        parts = item_id.split("/", 1)
        if len(parts) != 2:
            return {"error": f"Invalid S3 path: {item_id}"}

        bucket, key = parts

        try:
            content_type = properties.get("content_type", "text/plain") if properties else "text/plain"

            self._s3_client.put_object(
                Bucket=bucket,
                Key=key,
                Body=content.encode("utf-8"),
                ContentType=content_type,
            )

            return {
                "id": f"s3://{bucket}/{key}",
                "bucket": bucket,
                "key": key,
                "message": "File updated successfully",
            }

        except ClientError as e:
            return {"error": f"Failed to update s3://{bucket}/{key}: {e}"}

    def delete(self, item_id: str) -> dict[str, Any]:
        """Delete a file from S3."""
        if self.is_mock_mode:
            return {
                "id": item_id,
                "message": "File deleted (mock mode - not persisted)",
            }

        # Parse item_id
        if item_id.startswith("s3://"):
            item_id = item_id[5:]

        parts = item_id.split("/", 1)
        if len(parts) != 2:
            return {"error": f"Invalid S3 path: {item_id}"}

        bucket, key = parts

        try:
            self._s3_client.delete_object(Bucket=bucket, Key=key)
            return {
                "id": f"s3://{bucket}/{key}",
                "message": "File deleted successfully",
            }

        except ClientError as e:
            return {"error": f"Failed to delete s3://{bucket}/{key}: {e}"}

    def get_presigned_url(
        self,
        item_id: str,
        expiration: int = 3600,
        operation: str = "get_object",
    ) -> dict[str, Any]:
        """Generate a presigned URL for direct access to an S3 object.

        Args:
            item_id: S3 path (s3://bucket/key)
            expiration: URL expiration time in seconds (default: 1 hour)
            operation: S3 operation ('get_object' or 'put_object')

        Returns:
            Dictionary with 'url' or 'error'
        """
        if self.is_mock_mode:
            return {"error": "Presigned URLs not available in mock mode"}

        # Parse item_id
        if item_id.startswith("s3://"):
            item_id = item_id[5:]

        parts = item_id.split("/", 1)
        if len(parts) != 2:
            return {"error": f"Invalid S3 path: {item_id}"}

        bucket, key = parts

        try:
            url = self._s3_client.generate_presigned_url(
                operation,
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expiration,
            )
            return {
                "url": url,
                "expires_in": expiration,
                "bucket": bucket,
                "key": key,
            }

        except ClientError as e:
            return {"error": f"Failed to generate presigned URL: {e}"}


def _get_file_modified(bucket: str, key: str) -> str:
    """Get file modified date from mock data."""
    files = MOCK_FILES.get(bucket, [])
    for f in files:
        if f["key"] == key:
            return f.get("modified", "")
    return ""


def _extract_snippet_with_context(content: str, query: str, context_lines: int = 2) -> str:
    """Extract a snippet with surrounding context lines (grep-like)."""
    query_lower = query.lower()
    lines = content.split("\n")

    for i, line in enumerate(lines):
        if query_lower in line.lower():
            start = max(0, i - context_lines)
            end = min(len(lines), i + context_lines + 1)

            snippet_lines = []
            for j in range(start, end):
                prefix = ">" if j == i else " "
                snippet_lines.append(f"{prefix} {lines[j]}")

            return "\n".join(snippet_lines)

    return content[:200] + "..."
