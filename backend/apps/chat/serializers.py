from rest_framework import serializers

from .models import Conversation, Message


class MessageSerializer(serializers.ModelSerializer):
    """The attachment KEY is not exposed - it is an internal storage path, and a
    client that needs the image fetches it through an endpoint that performs the
    authorisation check.

    `has_attachment` is a boolean rather than a URL on purpose. The object store
    is not reachable from a browser, and minting a link that carries its own
    authority would put a working handle to a user's screenshot into anything
    that logs a URL.
    """

    has_attachment = serializers.SerializerMethodField()

    def get_has_attachment(self, obj) -> bool:
        return bool(obj.attachment_key)

    class Meta:
        model = Message
        fields = (
            "id",
            "role",
            "text",
            "citations",
            "attachment_description",
            "has_attachment",
            "proposed_escalation",
            "escalation_sent_at",
            "escalation_recipient",
            "created_at",
        )
        read_only_fields = fields


class ConversationSerializer(serializers.ModelSerializer):
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = (
            "id",
            "title",
            "resolved",
            "escalated_at",
            "created_at",
            "updated_at",
            "messages",
        )
        read_only_fields = fields


class ConversationListSerializer(serializers.ModelSerializer):
    """The sidebar shape - deliberately without `messages`.

    The list is loaded on every visit to the chat page. Nesting every message of
    every conversation would send an entire history to render a list of titles,
    and it grows without bound as a user keeps talking. The detail endpoint
    already returns the full thread when one is opened.
    """

    message_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Conversation
        fields = (
            "id",
            "title",
            "resolved",
            "escalated_at",
            "created_at",
            "updated_at",
            "message_count",
        )
        read_only_fields = fields


class SendMessageSerializer(serializers.Serializer):
    text = serializers.CharField(allow_blank=True, trim_whitespace=True)
    image = serializers.ImageField(required=False, allow_null=True)

    def validate(self, attrs):
        """A screenshot on its own is a valid question - "what is this?" is
        implied - but an empty turn with nothing attached is not."""
        if not attrs.get("text") and not attrs.get("image"):
            raise serializers.ValidationError("Type a message or attach a screenshot.")
        if not attrs.get("text"):
            attrs["text"] = "What does this screenshot show, and how do I fix it?"
        return attrs


class FeedbackSerializer(serializers.Serializer):
    message = serializers.IntegerField()
    helpful = serializers.BooleanField()
    note = serializers.CharField(required=False, allow_blank=True)
