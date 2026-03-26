import json
from collections.abc import AsyncIterator

from starlette.responses import StreamingResponse

from a1.proxy.response_models import ChatCompletionChunk


async def sse_stream(chunks: AsyncIterator[ChatCompletionChunk]) -> StreamingResponse:
    async def generate():
        async for chunk in chunks:
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
