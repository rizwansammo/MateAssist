"""Chat API: retrieval-grounded answers, streamed over SSE (D-003, D-041, D-056)."""

from __future__ import annotations

import json
import logging

from django.db import connection, transaction
from django.http import StreamingHttpResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ai import router
from apps.ai.engines import EngineError, NoKeyAvailable
from apps.knowledge import storage
from apps.tenancy.context import tenant_context

from . import escalation, prompts, retrieval
from .models import Conversation, Message, MessageFeedback, Role
from .serializers import (
    ConversationSerializer,
    FeedbackSerializer,
    MessageSerializer,
    SendMessageSerializer,
)

logger = logging.getLogger(__name__)

MAX_HISTORY = 12  # turns carried into the prompt


def _arm(tenant_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.tenant_id', %s, true)", [str(tenant_id)])


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        return Conversation.objects.filter(user=self.request.user).prefetch_related("messages")

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant, user=self.request.user)

    # -- the turn -------------------------------------------------------

    @extend_schema(request=SendMessageSerializer, responses={200: MessageSerializer})
    @action(detail=True, methods=["post"], url_path="send")
    def send(self, request, pk=None):
        """Non-streaming turn. Simpler to test and to call from a script."""
        conversation = self.get_object()
        payload = SendMessageSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        try:
            user_message, hits, attachment_description = self._prepare(
                request, conversation, payload.validated_data
            )
        except EngineError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        messages = prompts.build_messages(
            tenant_name=request.tenant.name,
            history=self._history(conversation, exclude=user_message.pk),
            question=user_message.text,
            hits=hits,
            attachment_description=attachment_description,
        )

        try:
            result = router.call_text(
                messages,
                tenant=request.tenant,
                user=request.user,
                tools=[prompts.ESCALATION_TOOL],
                # Generous on purpose: a reasoning model with a tight cap spends
                # the budget thinking and returns empty content (A-010).
                max_tokens=1500,
            )
        except NoKeyAvailable:
            return Response(
                {"detail": "No text engine is configured. Ask your platform administrator."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except EngineError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        assistant = self._persist_answer(conversation, result, hits)
        return Response(MessageSerializer(assistant).data)

    @action(detail=True, methods=["post"], url_path="stream")
    def stream(self, request, pk=None):
        """Same turn, streamed as SSE.

        Everything that needs the database - retrieval, history, saving the user
        message - happens BEFORE the generator starts. Django consumes a
        streaming response after the request transaction has closed, so the
        transaction-scoped app.tenant_id would already be gone inside the
        generator. The final write re-establishes tenant context explicitly.
        """
        conversation = self.get_object()
        payload = SendMessageSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        tenant = request.tenant
        user = request.user

        try:
            user_message, hits, attachment_description = self._prepare(
                request, conversation, payload.validated_data
            )
        except EngineError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)

        messages = prompts.build_messages(
            tenant_name=tenant.name,
            history=self._history(conversation, exclude=user_message.pk),
            question=user_message.text,
            hits=hits,
            attachment_description=attachment_description,
        )
        citations = [hit.citation for hit in hits]

        def event(name: str, data: dict) -> str:
            return f"event: {name}\ndata: {json.dumps(data)}\n\n"

        def generate():
            yield event("start", {"user_message_id": user_message.pk, "citations": citations})

            collected: list[str] = []
            try:
                key = router.acquire("TEXT")
                from apps.ai.engines.factory import build_text_engine

                client = build_text_engine(key, key.reveal())
                for delta in client.stream(messages):
                    collected.append(delta)
                    yield event("delta", {"text": delta})
            except NoKeyAvailable as exc:
                # Report the pool's own reason. A generic "not configured"
                # message hides whether the pool is empty, cooling down or
                # quota-exhausted - three problems with three different fixes.
                logger.warning("chat stream could not acquire a text key: %s", exc)
                yield event("error", {"detail": f"No usable text engine: {exc}"})
                return
            except Exception as exc:  # noqa: BLE001
                logger.exception("chat stream failed")
                yield event("error", {"detail": str(exc)[:300]})
                return

            answer = "".join(collected).strip()
            usage = getattr(client, "last_usage", None)

            # Re-arm tenant context: the request transaction is long gone by now.
            with tenant_context(tenant.id), transaction.atomic():
                _arm(tenant.id)
                assistant = Message.all_objects.create(
                    tenant=tenant,
                    conversation=conversation,
                    role=Role.ASSISTANT,
                    text=answer,
                    citations=citations,
                    prompt_tokens=usage.prompt_tokens if usage else 0,
                    completion_tokens=usage.completion_tokens if usage else 0,
                    latency_ms=usage.latency_ms if usage else 0,
                )
                Conversation.all_objects.filter(pk=conversation.pk).update(
                    updated_at=timezone.now()
                )
                # D-110: the streaming path bypasses call_text, so it must meter
                # itself. Otherwise the most frequent call in the product would
                # be the one that never appears on a bill.
                if usage:
                    router._meter(
                        tenant=tenant,
                        user=user,
                        engine="TEXT",
                        model=client.model,
                        operation="chat",
                        result=usage,
                    )

            yield event("done", {"message_id": assistant.pk, "citations": citations})

        response = StreamingHttpResponse(generate(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        # D-143: without this, a buffering proxy holds the whole response and the
        # stream arrives as one lump at the end - which looks like a hang.
        response["X-Accel-Buffering"] = "no"
        return response

    @extend_schema(responses={200: dict})
    @action(detail=True, methods=["post"], url_path="escalate")
    def escalate(self, request, pk=None):
        """Send the escalation email. Only reachable by an explicit user action.

        The model's tool call produced a proposal; this is the click that sends
        it (D-126).
        """
        conversation = self.get_object()
        proposal = request.data.get("proposal") or {}
        if not proposal.get("subject"):
            last = (
                conversation.messages.filter(proposed_escalation__isnull=False)
                .order_by("-created_at")
                .first()
            )
            proposal = (last.proposed_escalation if last else {}) or {}
        if not proposal:
            return Response(
                {"detail": "There is nothing to escalate yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = escalation.send_escalation(
            tenant=request.tenant,
            user=request.user,
            conversation=conversation,
            proposal=proposal,
        )
        return Response(
            result, status=status.HTTP_200_OK if result["sent"] else status.HTTP_502_BAD_GATEWAY
        )

    @extend_schema(request=FeedbackSerializer, responses={201: FeedbackSerializer})
    @action(detail=True, methods=["post"], url_path="feedback")
    def feedback(self, request, pk=None):
        conversation = self.get_object()
        payload = FeedbackSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        message = conversation.messages.filter(pk=payload.validated_data["message"]).first()
        if message is None:
            return Response({"detail": "Unknown message."}, status=status.HTTP_404_NOT_FOUND)

        MessageFeedback.all_objects.update_or_create(
            message=message,
            defaults={
                "tenant": request.tenant,
                "helpful": payload.validated_data["helpful"],
                "note": payload.validated_data.get("note", ""),
            },
        )
        return Response({"recorded": True}, status=status.HTTP_201_CREATED)

    # -- internals ------------------------------------------------------

    def _history(self, conversation, *, exclude=None):
        queryset = conversation.messages.order_by("-created_at")
        if exclude:
            queryset = queryset.exclude(pk=exclude)
        return list(reversed(list(queryset[:MAX_HISTORY])))

    def _prepare(self, request, conversation, data):
        """Persist the user's turn, describe any screenshot, and retrieve.

        The screenshot goes to the vision engine and stops there. Only the text
        it returns continues (D-042) - which is why this returns a description
        string, never bytes.
        """
        question = data["text"].strip()
        upload = data.get("image")

        attachment_key = ""
        attachment_description = ""

        if upload:
            raw = upload.read()
            attachment_key = storage.build_key(request.tenant.id, upload.name or "screenshot.png")
            storage.put(attachment_key, raw, upload.content_type or "image/png")

            result = router.call_vision(
                raw,
                mime_type=upload.content_type or "image/png",
                purpose="screenshot",
                tenant=request.tenant,
                user=request.user,
            )
            attachment_description = (result.text or "").strip()

        user_message = Message.objects.create(
            tenant=request.tenant,
            conversation=conversation,
            role=Role.USER,
            text=question,
            attachment_key=attachment_key,
            attachment_description=attachment_description,
        )

        if not conversation.title:
            conversation.title = question[:120]
            conversation.save(update_fields=["title", "updated_at"])

        # The screenshot description is part of the search query: a user who
        # pastes an error dialog and types "what's this?" has told you nothing,
        # but the transcribed error code is highly retrievable.
        search_text = f"{question} {attachment_description}".strip()
        hits = retrieval.retrieve(search_text)

        return user_message, hits, attachment_description

    def _persist_answer(self, conversation, result, hits):
        proposal = None
        for call in result.tool_calls or []:
            if call["name"] == "escalate_via_email":
                try:
                    proposal = json.loads(call["arguments"] or "{}")
                except json.JSONDecodeError:
                    proposal = {"subject": "Escalation requested"}
                break

        message = Message.objects.create(
            tenant=conversation.tenant,
            conversation=conversation,
            role=Role.ASSISTANT,
            text=result.text,
            citations=[hit.citation for hit in hits],
            proposed_escalation=proposal,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            latency_ms=result.latency_ms,
        )
        conversation.save(update_fields=["updated_at"])
        return message
