# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *
import json
from datetime import datetime, timezone


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())

def valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def valid_address(value: str) -> bool:
    return len(value) == 42 and value[:2] == '0x' and all(ch in '0123456789abcdefABCDEF' for ch in value[2:])


def pinned_url(url: str) -> bool:
    # Only immutable, commit-addressed GitHub evidence is accepted.
    prefix = 'https://raw.githubusercontent.com/'
    if not url.startswith(prefix) or len(url) > 320 or '?' in url or '#' in url:
        return False
    parts = url[len(prefix):].split('/')
    if len(parts) < 4 or not parts[0] or not parts[1] or not parts[3]:
        return False
    sha = parts[2]
    return len(sha) == 40 and all(ch in '0123456789abcdef' for ch in sha)


class SpecRegistry(gl.Contract):
    owner: Address
    suite_count: u256
    suites: TreeMap[u256, str]
    suite_owners: TreeMap[u256, Address]

    def __init__(self) -> None:
        self.owner = gl.message.sender_address
        self.suite_count = u256(0)

    @gl.public.write
    def register_suite(self, name: str, target: str, source_url: str,
                       source_sha256: str, spec_url: str, spec_sha256: str,
                       behavior: str, parent_id: u256) -> u256:
        if not (3 <= len(name) <= 72 and 24 <= len(behavior) <= 1200):
            raise gl.vm.UserError('invalid name or behavioral specification')
        if not valid_address(target) or not pinned_url(source_url) or not pinned_url(spec_url):
            raise gl.vm.UserError('target or immutable evidence URL invalid')
        if not valid_sha256(source_sha256) or not valid_sha256(spec_sha256):
            raise gl.vm.UserError('source and spec hashes must be lowercase SHA-256')
        if parent_id != u256(0):
            if parent_id > self.suite_count or self.suite_owners[parent_id] != gl.message.sender_address:
                raise gl.vm.UserError('only parent author may register a successor')
            previous = json.loads(self.suites[parent_id])
            if previous['target'].lower() != target.lower():
                raise gl.vm.UserError('successor must preserve the protected target')
        self.suite_count += u256(1)
        suite_id = self.suite_count
        record = {
            'id': int(suite_id), 'owner': str(gl.message.sender_address), 'name': name,
            'target': target.lower(), 'source_url': source_url, 'source_sha256': source_sha256,
            'spec_url': spec_url, 'spec_sha256': spec_sha256,
            'behavior': behavior, 'parent_id': int(parent_id), 'created_at': _now(),
            'chain_id': int(gl.message.chain_id)
        }
        self.suites[suite_id] = json.dumps(record, sort_keys=True, separators=(',', ':'))
        self.suite_owners[suite_id] = gl.message.sender_address
        return suite_id

    @gl.public.view
    def get_suite(self, suite_id: u256) -> str:
        if suite_id == u256(0) or suite_id > self.suite_count:
            raise gl.vm.UserError('suite does not exist')
        return self.suites[suite_id]

    @gl.public.view
    def get_suite_count(self) -> u256:
        return self.suite_count

    @gl.public.view
    def list_suites(self, start: u256, limit: u256) -> str:
        if limit == u256(0) or limit > u256(30):
            raise gl.vm.UserError('limit 1..30')
        items = []
        n = int(self.suite_count)
        for index in range(max(int(start), 1), min(n + 1, int(start) + int(limit))):
            items.append(json.loads(self.suites[u256(index)]))
        return json.dumps(items, separators=(',', ':'))
