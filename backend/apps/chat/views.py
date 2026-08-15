"""Chat API: retrieval-grounded answers, streamed over SSE (D-003, D-041, D-056)."""

from __future__ import annotations

import json
import logging

from django.db import connection, transaction
from django.db.models import Count
from django.http import Http404, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.ai import router, user_messages
from apps.ai.engines import EngineError, NoKeyAvailable, RateLimited
from apps.knowledge import storage
from apps.metering.budgets import BudgetExceeded
from apps.tenancy.context import tenant_context

from . import escalation, prompts, retrieval
from .models import Conversation, Message, MessageFeedback, Role
from .serializers import (
    ConversationListSerializer,
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


def _escalation_proposal(tool_calls) -> dict | None:
    """The escalate_via_email arguments, if the model asked for one.

    Tolerant of malformed JSON on purpose. A truncated arguments string means
    the model wanted to escalate and ran out of tokens mid-object; discarding
    that would silently drop a request for help. A proposal with only a subject
    is still a proposal the user can send.
    """
    for call in tool_calls or []:
        if call.get("name") != "escalate_via_email":
            continue
        try:
            parsed = json.loads(call.get("arguments") or "{}")
        except json.JSONDecodeError:
            return {"subject": "Escalation requested"}
        return parsed if isinstance(parsed, dict) else {"subject": "Escalation requested"}
    return None


def _status_for(exc) -> int:
    """HTTP status by failure kind, so a client can react correctly.

    429 tells a caller to back off and retry; 402 says the workspace has to act
    commercially; 503 means nothing is configured. Returning 502 for all three
    would make every failure look like a broken upstream.
    """
    if isinstance(exc, BudgetExceeded):
        return status.HTTP_402_PAYMENT_REQUIRED
    if isinstance(exc, RateLimited):
        return status.HTTP_429_TOO_MANY_REQUESTS
    if isinstance(exc, NoKeyAvailable):
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_502_BAD_GATEWAY


# Inferred from the stored key's extension rather than persisted. Uploads are
# already restricted to these types at the door, so a key with any other suffix
# is not a format to guess at.
_MIME_BY_SUFFIX = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}


def _attachment_mime(key: str) -> str:
    return _MIME_BY_SUFFIX.get(key.rsplit(".", 1)[-1].lower(), "application/octet-stream")


class ConversationViewSet(viewsets.ModelViewSet):
    serializer_class = ConversationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "delete"]

    def get_queryset(self):
        queryset = Conversation.objects.filter(user=self.request.user)
        if self.action == "list":
            # The sidebar needs titles and a count, not every message ever sent.
            # prefetch_related here would pull the whole history of every thread
            # to render a list of one-line labels.
            return queryset.annotate(message_count=Count("messages")).order_by("-updated_at")
        return queryset.prefetch_related("messages")

    def get_serializer_class(self):
        if self.action == "list":
            return ConversationListSerializer
        return ConversationSerializer

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.tenant, user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        """Deleting a conversation removes its messages by cascade.

        Left as a hard delete rather than a flag: this is the user's own
        transcript of their own support requests, and a "deleted" thread that
        quietly persists is the kind of thing that turns up in a data-subject
        request later.
        """
        return super().destroy(request, *args, **kwargs)

    # -- the turn -------------------------------------------------------

    @extend_schema(request=SendMessageSerializer, responses={200: MessageSerializer})
    @action(detail=True, methods=["post"], url_path="send")
    def send(self, request, pk=None):
        """Non-streaming turn. Simpler to test and to call from a script."""
        conversation = self.get_object()
        payload = SendMessageSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        try:
            user_message, grounded, citable, attachment_description = self._prepare(
                request, conversation, payload.validated_data
            )
        except (EngineError, BudgetExceeded) as exc:
            return Response(
                {
                    "detail": user_messages.report(
                        exc, context="chat.attachment", tenant=request.tenant, user=request.user
                    )
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        messages = prompts.build_messages(
            tenant_name=request.tenant.name,
            history=self._history(conversation, exclude=user_message.pk),
            question=user_message.text,
            hits=grounded,
            attachment_description=attachment_description,
            workspace_instructions=request.tenant.workspace_instructions,
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
        # BudgetExceeded is not an EngineError, so before D-135 it escaped both
        # handlers and returned a 500 - an enforced cap crashed the chat instead
        # of explaining itself.
        except (EngineError, BudgetExceeded) as exc:
            return Response(
                {
                    "detail": user_messages.report(
                        exc, context="chat.send", tenant=request.tenant, user=request.user
                    )
                },
                status=_status_for(exc),
            )

        assistant = self._persist_answer(conversation, result, citable)
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
            user_message, grounded, citable, attachment_description = self._prepare(
                request, conversation, payload.validated_data
            )
        except (EngineError, BudgetExceeded) as exc:
            return Response(
                {
                    "detail": user_messages.report(
                        exc, context="chat.stream.attachment", tenant=tenant, user=user
                    )
                },
                status=_status_for(exc),
            )

        messages = prompts.build_messages(
            tenant_name=tenant.name,
            history=self._history(conversation, exclude=user_message.pk),
            question=user_message.text,
            hits=grounded,
            attachment_description=attachment_description,
            workspace_instructions=tenant.workspace_instructions,
        )
        citations = [hit.citation for hit in citable]

        def event(name: str, data: dict) -> str:
            return f"event: {name}\ndata: {json.dumps(data)}\n\n"

        def generate():
            yield event("start", {"user_message_id": user_message.pk, "citations": citations})

            collected: list[str] = []
            try:
                key = router.acquire("TEXT")
                from apps.ai.engines.factory import build_text_engine

                client = build_text_engine(key, key.reveal())
                # The escalation tool, same as the non-streaming path (D-161).
                # Its absence here meant the model was instructed to use a tool
                # it was never handed, so it narrated the tool to the user
                # instead of calling it - and escalation could not be reached
                # from the chat box at all.
                for delta in client.stream(messages, tools=[prompts.ESCALATION_TOOL]):
                    collected.append(delta)
                    yield event("delta", {"text": delta})
            except Exception as exc:  # noqa: BLE001
                # D-135: the user gets a sentence, never the provider's text.
                # This is the path that leaked a raw Gemini 429 - vendor name,
                # quota position, Google's docs URL and Python dict formatting -
                # into a helpdesk user's chat window.
                #
                # `report` writes the real error to the log and the audit trail,
                # so an operator loses nothing by the user gaining clarity.
                detail = user_messages.report(exc, context="chat.stream", tenant=tenant, user=user)
                yield event("error", {"detail": detail})
                return

            answer = "".join(collected).strip()
            usage = getattr(client, "last_usage", None)

            # Read only after the loop: arguments arrive a few characters per
            # chunk and are not valid JSON until the stream ends.
            proposal = _escalation_proposal(getattr(client, "last_tool_calls", None))

            # A model that calls the tool often emits no prose at all, which
            # would render as an empty bubble above the escalation card.
            if proposal and not answer:
                answer = (
                    "I can't resolve this from your runbooks, so I've drafted an "
                    "escalation for your IT team. Review it and send when you're ready."
                )

            # Re-arm tenant context: the request transaction is long gone by now.
            with tenant_context(tenant.id), transaction.atomic():
                _arm(tenant.id)
                assistant = Message.all_objects.create(
                    tenant=tenant,
                    conversation=conversation,
                    role=Role.ASSISTANT,
                    text=answer,
                    citations=citations,
                    proposed_escalation=proposal,
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

            yield event(
                "done",
                {
                    "message_id": assistant.pk,
                    "citations": citations,
                    # The portal reloads the conversation on `done`, so it would
                    # find the proposal anyway - but sending it here lets the
                    # escalation card appear with the answer instead of after a
                    # round trip.
                    "proposed_escalation": proposal,
                },
            )

        response = StreamingHttpResponse(generate(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        # D-143: without this, a buffering proxy holds the whole response and the
        # stream arrives as one lump at the end - which looks like a hang.
        response["X-Accel-Buffering"] = "no"
        return response

    @extend_schema(responses={200: dict})
    @action(
        detail=True,
        methods=["get"],
        url_path=r"messages/(?P<message_id>[0-9]+)/attachment",
    )
    def attachment(self, request, pk=None, message_id=None):
        """Serve a message's screenshot back to the person who sent it.

        Routed under the conversation rather than as a flat /messages/<id>/ so
        authorisation is structural: get_object() already restricts to
        conversations owned by this user in this tenant, and the message is then
        looked up WITHIN that conversation. There is no id an attacker can
        substitute that escapes both checks.

        Streamed through Django instead of a presigned URL because the object
        store is not reachable from a browser, and a self-authorising link to a
        user's screenshot would survive in logs and history.
        """
        conversation = self.get_object()
        message = get_object_or_404(
            Message.all_objects.filter(conversation=conversation), pk=message_id
        )
        if not message.attachment_key:
            raise Http404("This message has no attachment.")

        try:
            data = storage.get(message.attachment_key)
        except Exception:  # noqa: BLE001
            logger.warning("attachment missing from storage: %s", message.attachment_key)
            raise Http404("The attachment is no longer available.") from None

        response = HttpResponse(data, content_type=_attachment_mime(message.attachment_key))
        # Private, not public: this is one user's screenshot, and a shared cache
        # holding it would serve it to whoever asked next.
        response["Cache-Control"] = "private, max-age=3600"
        return response

    @action(detail=True, methods=["post"], url_path="escalate")
    def escalate(self, request, pk=None):
        """Send the escalation email. Only reachable by an explicit user action.

        The model's tool call produced a proposal; this is the click that sends
        it (D-126).
        """
        conversation = self.get_object()

        # The message carrying the proposal, not just the proposal text. It is
        # what gets stamped as sent, and what the guard below reads.
        carrier = (
            conversation.messages.filter(proposed_escalation__isnull=False)
            .order_by("-created_at")
            .first()
        )
        proposal = request.data.get("proposal") or {}
        if not proposal.get("subject"):
            proposal = (carrier.proposed_escalation if carrier else {}) or {}
        if not proposal:
            return Response(
                {"detail": "There is nothing to escalate yet."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Claim the send before doing it, in one atomic UPDATE ... WHERE NOT
        # SENT (D-163). Checking the field and then sending would still let two
        # clicks a few milliseconds apart both pass the check and both send -
        # and a duplicate escalation is a second ticket in a real helpdesk
        # queue, not a cosmetic glitch.
        if carrier is not None:
            claimed = Message.objects.filter(pk=carrier.pk, escalation_sent_at__isnull=True).update(
                escalation_sent_at=timezone.now()
            )
            if not claimed:
                carrier.refresh_from_db()
                return Response(
                    {
                        "sent": False,
                        "already_sent": True,
                        "detail": "This request has already been sent to your IT team.",
                        "recipient": carrier.escalation_recipient,
                        "sent_at": carrier.escalation_sent_at,
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        result = escalation.send_escalation(
            tenant=request.tenant,
            user=request.user,
            conversation=conversation,
            proposal=proposal,
        )

        if carrier is not None:
            if result["sent"]:
                Message.objects.filter(pk=carrier.pk).update(
                    escalation_recipient=result.get("recipient", "")
                )
            else:
                # Release the claim. A failed send that stayed marked would
                # leave the user with no button and no email - the worst of both.
                Message.objects.filter(pk=carrier.pk).update(escalation_sent_at=None)

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

        # Two lists, not one (D-138). `grounded` is what the model is shown;
        # `citable` is what the UI is allowed to claim as a source. A greeting
        # produces neither, so it gets a plain reply with no fabricated
        # "Sources: VPN Runbook" chip underneath it.
        # focus() before gate(): narrow to one document first, THEN decide what
        # is good enough to show and cite. Gating first would let a strong
        # passage from the losing runbook survive into the prompt.
        grounded, citable = retrieval.gate(retrieval.focus(retrieval.retrieve(search_text)))

        return user_message, grounded, citable, attachment_description

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
