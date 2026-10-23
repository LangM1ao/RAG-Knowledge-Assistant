"""SQLite 文档级显式别名；别名只确认身份，不提供学校、成绩等事实。"""
import json
import re
import sqlite3
from contextlib import closing

from app.db.document_repository import get_connection
from app.services.query_normalizer import normalize_query


def _init_table(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS entity_aliases (
        document_id TEXT PRIMARY KEY,
        entity_name TEXT NOT NULL,
        aliases_json TEXT NOT NULL
    )''')


def set_document_aliases(document_id: str, entity_name: str, aliases: list[str]) -> dict:
    entity_name = entity_name.strip()
    if not entity_name or len(entity_name) > 120 or len(aliases) > 12:
        raise ValueError('实体名称须为 1–120 字符，最多登记 12 个别名。')
    cleaned = []
    seen = set()
    for value in [*aliases, entity_name]:
        value = value.strip()
        if not value or len(value) > 120:
            raise ValueError('每个别名须为 1–120 字符。')
        normalized = normalize_query(value)
        if normalized not in seen:
            cleaned.append(value)
            seen.add(normalized)
    with closing(get_connection()) as conn, conn:
        conn.row_factory = sqlite3.Row
        _init_table(conn)
        if conn.execute('SELECT 1 FROM documents WHERE document_id=?', (document_id,)).fetchone() is None:
            raise ValueError('Document not found.')
        conn.execute('''INSERT INTO entity_aliases VALUES(?,?,?)
            ON CONFLICT(document_id) DO UPDATE SET
            entity_name=excluded.entity_name, aliases_json=excluded.aliases_json''',
            (document_id, entity_name, json.dumps(cleaned, ensure_ascii=False)))
    return {'document_id': document_id, 'entity_name': entity_name, 'aliases': cleaned}


def list_aliases(document_ids=None, source_files=None) -> list[dict]:
    with closing(get_connection()) as conn, conn:
        conn.row_factory = sqlite3.Row
        _init_table(conn)
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents'").fetchone() is None:
            return []
        # INNER JOIN 排除已删除文档，避免遗留别名重新扩大检索范围。
        rows = conn.execute('''SELECT a.document_id,a.entity_name,a.aliases_json,d.filename
            FROM entity_aliases a JOIN documents d ON a.document_id=d.document_id
            ORDER BY a.document_id''').fetchall()
    return [
        {'document_id': row['document_id'], 'source_file': row['filename'],
         'entity_name': row['entity_name'], 'aliases': json.loads(row['aliases_json'])}
        for row in rows
        if (document_ids is None or row['document_id'] in document_ids)
        and (not source_files or row['filename'] in source_files)
    ]


def get_document_aliases(document_id: str) -> dict:
    rows = list_aliases(document_ids=[document_id])
    return rows[0] if rows else {'document_id': document_id, 'entity_name': '', 'aliases': []}


def delete_document_aliases(document_id: str) -> None:
    with closing(get_connection()) as conn, conn:
        conn.row_factory = sqlite3.Row
        _init_table(conn)
        conn.execute('DELETE FROM entity_aliases WHERE document_id=?', (document_id,))


def _alias_pattern(alias: str) -> str:
    # 英文词边界避免 Ann 匹配 Joanne；中文别名允许紧接“的”等汉字。
    left = r'(?<![a-z0-9_])' if alias[:1].isascii() and alias[:1].isalnum() else ''
    right = r'(?![a-z0-9_])' if alias[-1:].isascii() and alias[-1:].isalnum() else ''
    return left + re.escape(alias) + right


def resolve_aliases(question: str, rows: list[dict]) -> dict:
    """Resolve explicit names; only an unambiguous subject may constrain scope.

    Several entities are valid in comparison questions. Ambiguous names remain
    unchanged rather than silently selecting one entity or refusing all retrieval.
    """
    normalized = normalize_query(question)
    matches = []
    for row in rows:
        names = sorted(set(row['aliases'] + [row['entity_name']]), key=len, reverse=True)
        for name in names:
            alias = normalize_query(name)
            found = re.search(_alias_pattern(alias), normalized) if alias else None
            if found:
                matches.append({'document_id': row['document_id'],
                                'entity_name': row['entity_name'], 'matched_alias': alias,
                                'start': found.start(), 'end': found.end()})
                break
    by_alias = {}
    for match in matches:
        by_alias.setdefault(match['matched_alias'], []).append(match)
    ambiguous_aliases = {alias for alias, group in by_alias.items()
                         if len({m['document_id'] for m in group}) > 1}
    usable = [m for m in matches if m['matched_alias'] not in ambiguous_aliases]
    spans = []
    for match in sorted(usable, key=lambda m: (-(m['end']-m['start']), m['start'])):
        if not any(match['start'] < old['end'] and old['start'] < match['end'] for old in spans):
            spans.append(match)
    expanded = normalized
    for match in sorted(spans, key=lambda m:m['start'], reverse=True):
        expanded = expanded[:match['start']] + normalize_query(match['entity_name']) + expanded[match['end']:]
    subject = len(spans) == 1 and spans[0]['start'] == 0 and not ambiguous_aliases
    content = expanded
    constraint_ids = []
    if subject:
        name = normalize_query(spans[0]['entity_name'])
        remainder = re.sub(_alias_pattern(name), '', expanded, count=1).strip()
        # Preserve names when identity itself is the requested information.
        identity_only = re.sub(r'\b(?:who|what|is|are|tell|me|about|please)\b|是谁|是什么|介绍|一下|概况|背景|的|[\W_]+', '', remainder).strip() == ''
        if not identity_only:
            content = remainder
            constraint_ids = [spans[0]['document_id']]
    return {'query': expanded, 'content_query': content,
            'matches': matches, 'ambiguous': bool(ambiguous_aliases),
            'ambiguous_aliases': sorted(ambiguous_aliases),
            'constraint_document_ids': constraint_ids}
