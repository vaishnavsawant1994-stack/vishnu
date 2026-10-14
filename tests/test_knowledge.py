from knowledge.store import KnowledgeError, KnowledgeStore
import io
import json
import zipfile


def test_knowledge_ingestion_search_provenance_update_and_delete(tmp_path):
    store = KnowledgeStore(tmp_path / 'knowledge.sqlite3', tmp_path / 'objects')
    data = b'Project Aurora launch date is 14 October. The owner approved the final plan.'

    document = store.ingest(
        filename='aurora-notes.txt',
        data=data,
        source='owner-upload:test',
        access_class='owner',
    )

    assert document['filename'] == 'aurora-notes.txt'
    assert document['chunks'][0]['content'].startswith('Project Aurora')
    listed = store.list()[0]
    assert listed['source'] == 'owner-upload:test'
    assert listed['indexed_chunk_count'] == len(document['chunks'])
    assert store.list('Aurora launch')[0]['indexed_chunk_count'] == len(document['chunks'])
    result = store.search('Aurora launch')[0]
    assert result['citation']['document_id'] == document['id']
    assert result['citation']['source'] == 'owner-upload:test'
    assert result['citation']['checksum'] == document['checksum']

    duplicate = store.ingest(filename='copy.txt', data=data)
    assert duplicate['id'] == document['id']
    assert store.update(document['id'], title='Aurora launch plan')['title'] == 'Aurora launch plan'
    assert store.delete(document['id']) is True
    assert store.detail(document['id']) is None
    assert list((tmp_path / 'objects').iterdir()) == []


def test_knowledge_rejects_unsafe_unsupported_or_empty_uploads(tmp_path):
    store = KnowledgeStore(tmp_path / 'knowledge.sqlite3', tmp_path / 'objects')
    for filename, data in [('../unsafe.exe', b'data'), ('empty.txt', b'')]:
        try:
            store.ingest(filename=filename, data=data)
        except KnowledgeError:
            pass
        else:
            raise AssertionError('unsafe knowledge upload was accepted')


def test_available_to_vishnu_gate_and_collection_lifecycle(tmp_path):
    store = KnowledgeStore(tmp_path / 'knowledge.sqlite3', tmp_path / 'objects')
    collection = store.create_collection('Project notes', 'Scoped project material')
    document = store.ingest(
        filename='project.txt', data=b'The private launch milestone is ready.',
        metadata={'collection_id': collection['id'], 'available_to_vishnu': True},
    )
    assert store.collections()[0]['item_count'] == 1
    assert store.search('private launch')

    metadata = dict(document['metadata'])
    metadata['available_to_vishnu'] = False
    store.update(document['id'], metadata=metadata)
    assert store.list()[0]['metadata']['available_to_vishnu'] is False
    assert store.search('private launch') == []

    store.delete_collection(collection['id'])
    assert store.detail(document['id'])['metadata'].get('collection_id') is None
    assert store.detail(document['id']) is not None


def test_markdown_notes_support_empty_creation_editing_versions_and_links(tmp_path):
    store = KnowledgeStore(tmp_path / 'knowledge.sqlite3', tmp_path / 'objects')
    target = store.create_note(title='Project Notes', content='# Decisions\nApproved the launch plan.', tags=['project', '#launch'])
    source = store.create_note(title='Meeting Notes', content='See [[Project Notes|the decisions]] and [[Missing Note]].')
    empty = store.create_note(title='Draft')

    assert empty['content'] == ''
    assert {item['title']: item['content'] for item in store.notes()} == {
        'Project Notes': '# Decisions\nApproved the launch plan.',
        'Meeting Notes': 'See [[Project Notes|the decisions]] and [[Missing Note]].',
        'Draft': '',
    }
    links = store.note_links(source['id'])
    assert links['outgoing'] == [{'id': target['id'], 'title': 'Project Notes', 'label': 'the decisions'}]
    assert links['backlinks'] == []
    assert links['unresolved'] == [{'target': 'Missing Note', 'label': 'Missing Note'}]
    updated = store.update_note(source['id'], title='Meeting Notes', content='Updated: [[Project Notes]]', tags=['meeting'])
    assert updated['version'] == 2
    assert updated['content'] == 'Updated: [[Project Notes]]'
    assert store.history(source['id'])[1]['id'] == source['id']
    assert store.note_links(target['id'])['backlinks'] == [{'id': updated['id'], 'title': 'Meeting Notes'}]


def test_note_links_respect_visible_access_classes_and_portable_export_includes_original_files(tmp_path):
    store = KnowledgeStore(tmp_path / 'knowledge.sqlite3', tmp_path / 'objects')
    private = store.create_note(title='Secret Note', content='Private text', access_class='private')
    public = store.create_note(title='Shared Note', content='See [[Secret Note]].')
    attachment = store.ingest(filename='diagram.txt', data=b'attachment bytes', access_class='owner')

    links = store.note_links(public['id'], access_classes={'owner'})
    assert links['outgoing'] == []
    assert links['unresolved'] == [{'target': 'Secret Note', 'label': 'Secret Note'}]
    archive = zipfile.ZipFile(io.BytesIO(store.export_portable_archive(access_classes={'owner'})))
    manifest = json.loads(archive.read('manifest.json'))
    paths = {item['path'] for item in manifest['files']}
    assert f'notes/{public["id"]}/{public["filename"]}' in paths
    assert f'files/{attachment["id"]}/diagram.txt' in paths
    assert not any(private['id'] in path for path in paths)
    note_path = next(path for path in paths if path.startswith(f'notes/{public["id"]}/'))
    assert archive.read(note_path) == b'See [[Secret Note]].'


def test_portable_archive_roundtrip_is_idempotent_and_keeps_note_links(tmp_path):
    source = KnowledgeStore(tmp_path / 'source.sqlite3', tmp_path / 'source-objects')
    collection = source.create_collection('Research', 'Portable references')
    source.create_note(title='Evidence', content='Verified source text.', collection_id=collection['id'])
    source.create_note(title='Summary', content='See [[Evidence]].', collection_id=collection['id'])
    archive = source.export_portable_archive()

    target = KnowledgeStore(tmp_path / 'target.sqlite3', tmp_path / 'target-objects')
    imported = target.import_portable_archive(archive, allowed_access_classes={'owner'})
    assert imported['imported_count'] == 2
    assert target.collections()[0]['title'] == 'Research'
    copied_note = next(item for item in target.notes() if item['title'] == 'Summary')
    copied_evidence = next(item for item in target.notes() if item['title'] == 'Evidence')
    assert target.note_links(copied_note['id'])['outgoing'][0]['id'] == copied_evidence['id']
    assert target.import_portable_archive(archive, allowed_access_classes={'owner'})['imported_count'] == 0


def test_portable_archive_rejects_path_traversal_before_writing_anything(tmp_path):
    store = KnowledgeStore(tmp_path / 'knowledge.sqlite3', tmp_path / 'objects')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('manifest.json', json.dumps({'format': 'vishnu-knowledge-archive-v1', 'files': [{'path': '../escape.txt'}]}))
        archive.writestr('../escape.txt', b'unsafe')
    try:
        store.import_portable_archive(buffer.getvalue(), allowed_access_classes={'owner'})
    except KnowledgeError:
        pass
    else:
        raise AssertionError('Path traversal archive was accepted')
    assert store.list() == []


def test_portable_archive_validates_all_collections_before_creating_any(tmp_path):
    store = KnowledgeStore(tmp_path / 'knowledge.sqlite3', tmp_path / 'objects')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('manifest.json', json.dumps({
            'format': 'vishnu-knowledge-archive-v1', 'files': [],
            'collections': [{'id': 'ok', 'title': 'Valid'}, {'id': 'bad', 'title': ''}],
        }))
    try:
        store.import_portable_archive(buffer.getvalue(), allowed_access_classes={'owner'})
    except KnowledgeError:
        pass
    else:
        raise AssertionError('Archive with invalid collection was accepted')
    assert store.collections() == []
