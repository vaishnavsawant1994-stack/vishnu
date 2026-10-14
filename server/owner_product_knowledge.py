from __future__ import annotations

import base64
import binascii
from urllib.parse import urlparse

from fastapi import APIRouter, Cookie, HTTPException, Request, Response

from knowledge.store import KnowledgeError
from server.owner_product_schemas import (
    KnowledgeAvailabilityBody,
    KnowledgeCollectionBody,
    KnowledgeCollectionUpdateBody,
    KnowledgeNoteBody,
    KnowledgeNoteUpdateBody,
    KnowledgeUpdateBody,
    KnowledgeUploadBody,
)


def create_owner_knowledge_router(runtime, *, authenticate, audit, knowledge_access, bounded_mapping):
    router = APIRouter(prefix='/iphone/api', tags=['owner-product'])
    knowledge = runtime['knowledge']

    @router.get('/knowledge/collections')
    def knowledge_collections(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, 'knowledge:read')
        return {'collections': knowledge.collections()}

    @router.get('/knowledge/sources')
    def knowledge_sources(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        authenticate(pa_device, pa_token, 'knowledge:read')
        sources = knowledge.sources(limit=100)
        return {'sources': [{key: item.get(key) for key in ('id', 'source_type', 'display_name', 'status', 'sync_status', 'last_sync_at', 'last_error_code', 'project_id')} for item in sources]}

    @router.post('/knowledge/collections', status_code=201)
    def knowledge_collection_create(body: KnowledgeCollectionBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'knowledge:write')
        try:
            item = knowledge.create_collection(body.title, body.description)
        except KnowledgeError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit('knowledge.collection.created', device_id=device_id, collection_id=item['id'])
        return item

    @router.patch('/knowledge/collections/{collection_id}')
    def knowledge_collection_update(collection_id: str, body: KnowledgeCollectionUpdateBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'knowledge:write')
        changes = body.model_dump(exclude_none=True)
        if not changes:
            raise HTTPException(422, 'Provide a collection name or description')
        try:
            item = knowledge.update_collection(collection_id, **changes)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except KnowledgeError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit('knowledge.collection.updated', device_id=device_id, collection_id=collection_id)
        return item

    @router.delete('/knowledge/collections/{collection_id}')
    def knowledge_collection_delete(collection_id: str, confirm: bool = False, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'knowledge:write')
        if not confirm:
            raise HTTPException(409, 'Deleting a collection requires confirm=true')
        if not knowledge.delete_collection(collection_id):
            raise HTTPException(404, 'Knowledge collection not found')
        audit('knowledge.collection.deleted', device_id=device_id, collection_id=collection_id)
        return {'ok': True, 'collection_id': collection_id, 'items_retained': True}

    @router.get('/knowledge')
    def knowledge_list(
        q: str = '',
        limit: int = 100,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'knowledge:read')
        return {'documents': knowledge.list(q, limit=min(limit, 100), access_classes=knowledge_access(device_id))}

    @router.get('/knowledge/search')
    def knowledge_search(
        q: str,
        limit: int = 12,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'knowledge:read')
        return {'results': knowledge.search(q, limit=min(limit, 50), access_classes=knowledge_access(device_id))}

    @router.get('/knowledge/notes')
    def knowledge_notes(q: str = '', limit: int = 100, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'knowledge:read')
        return {'notes': knowledge.notes(q, limit=min(limit, 100), access_classes=knowledge_access(device_id))}

    @router.post('/knowledge/notes', status_code=201)
    def knowledge_note_create(body: KnowledgeNoteBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'knowledge:write')
        allowed = knowledge_access(device_id)
        if body.access_class == 'private' and 'private' not in allowed:
            raise HTTPException(403, 'This device cannot create private knowledge')
        if body.collection_id and not knowledge.collection(body.collection_id):
            raise HTTPException(400, 'Knowledge collection not found')
        try:
            note = knowledge.create_note(title=body.title, content=body.content, access_class=body.access_class,
                                         collection_id=body.collection_id, tags=body.tags)
        except KnowledgeError as exc:
            raise HTTPException(400, str(exc)) from exc
        audit('knowledge.note.created', device_id=device_id, document_id=note['id'])
        return note

    @router.put('/knowledge/notes/{document_id}')
    def knowledge_note_update(document_id: str, body: KnowledgeNoteUpdateBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'knowledge:write')
        existing = knowledge.detail(document_id)
        if not existing or existing['access_class'] not in knowledge_access(device_id) or (existing.get('metadata') or {}).get('knowledge_kind') != 'note' or not existing.get('current', True):
            raise HTTPException(404, 'Current Knowledge note not found')
        try:
            note = knowledge.update_note(document_id, title=body.title, content=body.content, tags=body.tags)
        except (KnowledgeError, KeyError) as exc:
            raise HTTPException(400, str(exc)) from exc
        audit('knowledge.note.updated', device_id=device_id, document_id=document_id)
        return note

    @router.get('/knowledge/notes/{document_id}/links')
    def knowledge_note_links(document_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'knowledge:read')
        allowed = knowledge_access(device_id)
        note = knowledge.detail(document_id)
        if not note or note['access_class'] not in allowed:
            raise HTTPException(404, 'Knowledge note not found')
        try:
            return knowledge.note_links(document_id, access_classes=allowed)
        except KeyError as exc:
            raise HTTPException(404, 'Knowledge note not found') from exc

    @router.get('/knowledge/portable-export')
    def knowledge_portable_export(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'knowledge:read')
        try:
            payload = knowledge.export_portable_archive(access_classes=knowledge_access(device_id))
        except KnowledgeError as exc:
            raise HTTPException(413, str(exc)) from exc
        audit('knowledge.portable_exported', device_id=device_id, bytes=len(payload))
        return Response(payload, media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="vishnu-knowledge.zip"'})

    @router.post('/knowledge/portable-import')
    async def knowledge_portable_import(request: Request, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'knowledge:write')
        declared_size = request.headers.get('content-length')
        if declared_size:
            try:
                if int(declared_size) < 0:
                    raise ValueError
            except ValueError as exc:
                raise HTTPException(400, 'Invalid Content-Length header') from exc
            if int(declared_size) > knowledge.MAX_PORTABLE_ARCHIVE_BYTES:
                raise HTTPException(413, 'The Knowledge archive exceeds the 50 MB limit')
        if request.headers.get('content-type', '').split(';', 1)[0].strip().lower() not in {'application/zip', 'application/octet-stream', 'application/x-zip-compressed'}:
            raise HTTPException(415, 'Upload a Vishnu Knowledge ZIP archive')
        payload = await request.body()
        if len(payload) > knowledge.MAX_PORTABLE_ARCHIVE_BYTES:
            raise HTTPException(413, 'The Knowledge archive exceeds the 50 MB limit')
        allowed = knowledge_access(device_id)
        try:
            result = knowledge.import_portable_archive(payload, allowed_access_classes=allowed)
        except KnowledgeError as exc:
            raise HTTPException(400, str(exc)) from exc
        audit('knowledge.portable_imported', device_id=device_id, imported_count=result['imported_count'])
        return result

    @router.get('/knowledge/export')
    def knowledge_export(pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'knowledge:read')
        audit('knowledge.exported', device_id=device_id)
        return knowledge.export(access_classes=knowledge_access(device_id))

    @router.post('/knowledge')
    def knowledge_upload(
        body: KnowledgeUploadBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'knowledge:write')
        if body.access_class == 'private' and 'private' not in knowledge_access(device_id):
            raise HTTPException(403, 'This device cannot create private knowledge')
        try:
            if body.collection_id and not knowledge.collection(body.collection_id):
                raise KnowledgeError('Knowledge collection not found')
            if body.item_kind == 'link':
                parsed = urlparse(str(body.link_url or '').strip())
                if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
                    raise KnowledgeError('Enter a valid http or https link')
                body.filename = (body.filename or 'Saved link.txt')
                body.title = body.title or parsed.netloc
                data = f'Saved link (not fetched): {parsed.geturl()}'.encode('utf-8')
            elif body.content_base64 is not None:
                data = base64.b64decode(body.content_base64, validate=True)
            elif body.text is not None:
                data = body.text.encode('utf-8')
            else:
                raise KnowledgeError('File content is required')
            metadata = bounded_mapping(body.metadata)
            metadata.update({
                'knowledge_kind': body.item_kind,
                'available_to_vishnu': body.item_kind != 'link',
                'link_url': urlparse(body.link_url).geturl() if body.item_kind == 'link' and body.link_url else None,
                'link_status': 'saved_only' if body.item_kind == 'link' else None,
                'collection_id': body.collection_id or None,
            })
            document = knowledge.ingest(
                filename=body.filename,
                data=data,
                title=body.title,
                media_type=body.media_type,
                source=body.source,
                access_class=body.access_class,
                metadata={key: value for key, value in metadata.items() if value is not None},
            )
        except (KnowledgeError, binascii.Error) as exc:
            raise HTTPException(400, str(exc)) from exc
        audit('knowledge.ingested', device_id=device_id, document_id=document['id'], checksum=document['checksum'])
        return document

    @router.get('/knowledge/{document_id}')
    def knowledge_detail(document_id: str, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'knowledge:read')
        document = knowledge.detail(document_id)
        if not document or document['access_class'] not in knowledge_access(device_id):
            raise HTTPException(404, 'Knowledge document not found')
        return document

    @router.patch('/knowledge/{document_id}')
    def knowledge_update(
        document_id: str,
        body: KnowledgeUpdateBody,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'knowledge:write')
        existing = knowledge.detail(document_id)
        if not existing or existing['access_class'] not in knowledge_access(device_id):
            raise HTTPException(404, 'Knowledge document not found')
        if body.access_class == 'private' and 'private' not in knowledge_access(device_id):
            raise HTTPException(403, 'This device cannot mark knowledge private')
        try:
            changes = body.model_dump(exclude_none=True)
            collection_id = changes.pop('collection_id', None)
            if 'metadata' in changes:
                changes['metadata'] = bounded_mapping(changes['metadata'])
            if collection_id is not None:
                if collection_id and not knowledge.collection(collection_id):
                    raise KnowledgeError('Knowledge collection not found')
                metadata = dict(existing.get('metadata') or {})
                if collection_id:
                    metadata['collection_id'] = collection_id
                else:
                    metadata.pop('collection_id', None)
                changes['metadata'] = metadata
            document = knowledge.update(document_id, **changes)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        except KnowledgeError as exc:
            raise HTTPException(400, str(exc)) from exc
        audit('knowledge.updated', device_id=device_id, document_id=document_id)
        return document

    @router.patch('/knowledge/{document_id}/availability')
    def knowledge_availability(document_id: str, body: KnowledgeAvailabilityBody, pa_device: str | None = Cookie(default=None), pa_token: str | None = Cookie(default=None)):
        device_id = authenticate(pa_device, pa_token, 'knowledge:write')
        existing = knowledge.detail(document_id)
        if not existing or existing['access_class'] not in knowledge_access(device_id):
            raise HTTPException(404, 'Knowledge document not found')
        metadata = dict(existing.get('metadata') or {})
        if body.available_to_vishnu and metadata.get('link_status') == 'saved_only':
            raise HTTPException(409, 'This saved link has not been fetched or indexed; it cannot be used by Vishnu yet')
        metadata['available_to_vishnu'] = body.available_to_vishnu
        result = knowledge.update(document_id, metadata=metadata)
        audit('knowledge.availability.updated', device_id=device_id, document_id=document_id, available_to_vishnu=body.available_to_vishnu)
        return result

    @router.delete('/knowledge/{document_id}')
    def knowledge_delete(
        document_id: str,
        confirm: bool = False,
        pa_device: str | None = Cookie(default=None),
        pa_token: str | None = Cookie(default=None),
    ):
        device_id = authenticate(pa_device, pa_token, 'knowledge:write')
        if not confirm:
            raise HTTPException(409, 'Knowledge deletion requires confirm=true')
        existing = knowledge.detail(document_id)
        if not existing or existing['access_class'] not in knowledge_access(device_id):
            raise HTTPException(404, 'Knowledge document not found')
        if not knowledge.delete(document_id):
            raise HTTPException(404, 'Knowledge document not found')
        audit('knowledge.deleted', device_id=device_id, document_id=document_id)
        return {'ok': True, 'document_id': document_id}
    return router
