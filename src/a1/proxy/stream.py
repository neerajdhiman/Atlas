import json
import uuid
from collections.abc import AsyncIterator

from starlette.responses import StreamingResponse

from a1.proxy.response_models import ChatCompletionChunk


async def sse_stream(chunks: AsyncIterator[ChatCompletionChunk]) -> StreamingResponse:
    async def generate():
        async for chunk in chunks:
            if not chunk.choices and chunk.usage is not None:
                # Usage-only chunk — emit as plain data to avoid clients indexing choices[0]
                yield f"data: {json.dumps({'usage': chunk.usage.model_dump()})}\n\n"
                continue
            data = chunk.model_dump_json(exclude_none=True)
            yield f"data: {data}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def sse_responses_stream(
    response_id: str,
    model: str,
    text: str,
    usage: dict,
    metadata: dict | None = None,
) -> StreamingResponse:
    """Stream a complete response in OpenAI Responses API SSE format."""
    return await sse_responses_stream_live(response_id, model, None, text, usage, metadata)


async def sse_responses_stream_live(
    response_id: str,
    model: str,
    chunk_iterator=None,
    full_text: str | None = None,
    usage: dict | None = None,
    metadata: dict | None = None,
) -> StreamingResponse:
    """Stream response as SSE — either from live chunk iterator or pre-built text.

    If chunk_iterator is provided, streams tokens as they arrive from the provider.
    If full_text is provided, chunks it into ~20 char pieces for simulated streaming.
    """
    msg_id = f"msg_{uuid.uuid4().hex[:8]}"
    item_idx = 0
    content_idx = 0

    async def generate():
        nonlocal full_text, usage

        # 1. response.created
        yield _sse_event(
            "response.created",
            {
                "type": "response.created",
                "response": {
                    "id": response_id,
                    "object": "response",
                    "status": "in_progress",
                    "model": model,
                    "output": [],
                },
            },
        )

        # 2. response.output_item.added
        yield _sse_event(
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "output_index": item_idx,
                "item": {
                    "type": "message",
                    "id": msg_id,
                    "role": "assistant",
                    "status": "in_progress",
                    "content": [],
                },
            },
        )

        # 3. response.content_part.added
        yield _sse_event(
            "response.content_part.added",
            {
                "type": "response.content_part.added",
                "item_id": msg_id,
                "output_index": item_idx,
                "content_index": content_idx,
                "part": {"type": "output_text", "text": ""},
            },
        )

        # 4. Stream deltas — either from live iterator or chunked text
        accumulated_text = ""

        if chunk_iterator is not None:
            # Live streaming from provider
            stream_usage = None
            async for chunk in chunk_iterator:
                if chunk.choices and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    accumulated_text += delta
                    yield _sse_event(
                        "response.output_text.delta",
                        {
                            "type": "response.output_text.delta",
                            "item_id": msg_id,
                            "output_index": item_idx,
                            "content_index": content_idx,
                            "delta": delta,
                        },
                    )
                if chunk.usage:
                    stream_usage = chunk.usage
            full_text = accumulated_text
            text = accumulated_text
            if stream_usage:
                usage = {
                    "input_tokens": stream_usage.prompt_tokens,
                    "output_tokens": stream_usage.completion_tokens,
                    "total_tokens": stream_usage.total_tokens,
                }
        else:
            # Simulated streaming from pre-built text
            text = full_text or ""
            chunk_size = 20
            for i in range(0, len(text), chunk_size):
                chunk = text[i : i + chunk_size]
                yield _sse_event(
                    "response.output_text.delta",
                    {
                        "type": "response.output_text.delta",
                        "item_id": msg_id,
                        "output_index": item_idx,
                        "content_index": content_idx,
                        "delta": chunk,
                    },
                )
            accumulated_text = text

        # 5. response.output_text.done
        yield _sse_event(
            "response.output_text.done",
            {
                "type": "response.output_text.done",
                "item_id": msg_id,
                "output_index": item_idx,
                "content_index": content_idx,
                "text": text,
            },
        )

        # 6. response.content_part.done
        yield _sse_event(
            "response.content_part.done",
            {
                "type": "response.content_part.done",
                "item_id": msg_id,
                "output_index": item_idx,
                "content_index": content_idx,
                "part": {"type": "output_text", "text": text},
            },
        )

        # 7. response.output_item.done
        yield _sse_event(
            "response.output_item.done",
            {
                "type": "response.output_item.done",
                "output_index": item_idx,
                "item": {
                    "type": "message",
                    "id": msg_id,
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": text}],
                },
            },
        )

        # 8. response.completed
        yield _sse_event(
            "response.completed",
            {
                "type": "response.completed",
                "response": {
                    "id": response_id,
                    "object": "response",
                    "status": "completed",
                    "model": model,
                    "output": [
                        {
                            "type": "message",
                            "id": msg_id,
                            "role": "assistant",
                            "status": "completed",
                            "content": [{"type": "output_text", "text": text}],
                        }
                    ],
                    "usage": usage,
                    **({"metadata": metadata} if metadata else {}),
                },
            },
        )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse_event(event_type: str, data: dict) -> str:
    """Format a single SSE event."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
