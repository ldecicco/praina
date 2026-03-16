import json
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.chat import (
    ChatConversationCreate,
    ChatConversationListRead,
    ChatConversationRead,
    ChatConversationUpdate,
    ChatCardRead,
    ChatMessageCreate,
    ChatMessageExchangeRead,
    ChatMessageListRead,
    ChatMessageRead,
    CitationRead,
)
from app.services.chat_service import ChatService
from app.services.onboarding_service import NotFoundError, ValidationError

router = APIRouter()


@router.get("/{project_id}/chat/conversations", response_model=ChatConversationListRead)
def list_conversations(
    project_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ChatConversationListRead:
    service = ChatService(db)
    try:
        items, total = service.list_conversations(project_id, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ChatConversationListRead(
        items=[_conversation_read(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/chat/conversations", response_model=ChatConversationRead)
def create_conversation(
    project_id: uuid.UUID,
    payload: ChatConversationCreate,
    db: Session = Depends(get_db),
) -> ChatConversationRead:
    service = ChatService(db)
    try:
        conversation = service.create_conversation(
            project_id=project_id,
            title=payload.title,
            created_by_member_id=_uuid_or_none(payload.created_by_member_id),
        )
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _conversation_read(conversation)


@router.patch("/{project_id}/chat/conversations/{conversation_id}", response_model=ChatConversationRead)
def update_conversation(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ChatConversationUpdate,
    db: Session = Depends(get_db),
) -> ChatConversationRead:
    service = ChatService(db)
    try:
        conversation = service.update_conversation(project_id, conversation_id, title=payload.title)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _conversation_read(conversation)


@router.delete("/{project_id}/chat/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
) -> None:
    service = ChatService(db)
    try:
        service.delete_conversation(project_id, conversation_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{project_id}/chat/conversations/{conversation_id}/messages", response_model=ChatMessageListRead)
def list_messages(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> ChatMessageListRead:
    service = ChatService(db)
    try:
        items, total = service.list_messages(project_id, conversation_id, page, page_size)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return ChatMessageListRead(
        items=[_message_read(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{project_id}/chat/conversations/{conversation_id}/messages", response_model=ChatMessageExchangeRead)
def post_message(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
) -> ChatMessageExchangeRead:
    service = ChatService(db)
    try:
        user_message, assistant_message = service.post_message(
            project_id=project_id,
            conversation_id=conversation_id,
            content=payload.content,
            created_by_member_id=_uuid_or_none(payload.created_by_member_id),
        )
    except NotFoundError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValidationError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return ChatMessageExchangeRead(user_message=_message_read(user_message), assistant_message=_message_read(assistant_message))


@router.post("/{project_id}/chat/conversations/{conversation_id}/messages/stream")
def post_message_stream(
    project_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ChatMessageCreate,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    service = ChatService(db)

    def _event_stream():
        yield _sse("start", {"conversation_id": str(conversation_id)})
        try:
            user_message, assistant_message = service.post_message(
                project_id=project_id,
                conversation_id=conversation_id,
                content=payload.content,
                created_by_member_id=_uuid_or_none(payload.created_by_member_id),
            )
        except NotFoundError as exc:
            db.rollback()
            yield _sse("error", {"detail": str(exc)})
            return
        except ValidationError as exc:
            db.rollback()
            yield _sse("error", {"detail": str(exc)})
            return

        for token in _token_chunks(assistant_message.content):
            yield _sse("token", {"token": token})
        exchange = ChatMessageExchangeRead(user_message=_message_read(user_message), assistant_message=_message_read(assistant_message))
        yield _sse("done", exchange.model_dump(mode="json"))

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(_event_stream(), media_type="text/event-stream", headers=headers)


def _uuid_or_none(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValidationError("Invalid UUID provided.") from exc


def _conversation_read(item) -> ChatConversationRead:
    return ChatConversationRead(
        id=str(item.id),
        project_id=str(item.project_id),
        title=item.title,
        created_by_member_id=str(item.created_by_member_id) if item.created_by_member_id else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _message_read(item) -> ChatMessageRead:
    citations = item.citations or []
    return ChatMessageRead(
        id=str(item.id),
        conversation_id=str(item.conversation_id),
        project_id=str(item.project_id),
        role=item.role,
        content=item.content,
        citations=[CitationRead(**citation) for citation in citations],
        cards=[ChatCardRead(**card) for card in (item.cards or [])],
        created_by_member_id=str(item.created_by_member_id) if item.created_by_member_id else None,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=True)}\n\n"


def _token_chunks(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r"\S+\s*|\n", text)
