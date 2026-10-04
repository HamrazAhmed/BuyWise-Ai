"""Persistent worker: run separately from a serverless API in production."""
import asyncio
import logging
from pathlib import Path
from data import jobs, runtime
from models.product import ResearchProductsRequest
from llm.base import LLMRateLimitError

logger = logging.getLogger(__name__)


async def run_one():
    claimed = await asyncio.to_thread(jobs.claim)
    if not claimed:
        return False
    identifier, payload, owner = claimed
    async def progress(event):
        await asyncio.to_thread(jobs.progress, identifier, owner, event)
    async def renew():
        while True:
            await asyncio.sleep(10)
            await asyncio.to_thread(jobs.heartbeat, identifier, owner)
    async def compute():
        from agents.orchestrator import run_pipeline
        body = ResearchProductsRequest.model_validate(payload)
        return await asyncio.wait_for(run_pipeline(body.request_id, body.requirements, raw_text=body.raw_text, progress_callback=progress, comparison_id=identifier, persist=False), 180)
    heartbeat = asyncio.create_task(renew())
    computation = asyncio.create_task(compute())
    try:
        done, _ = await asyncio.wait([heartbeat, computation], return_when=asyncio.FIRST_COMPLETED)
        if heartbeat in done:
            heartbeat.result()
            raise RuntimeError('Heartbeat stopped')
        result = computation.result()
        await asyncio.to_thread(jobs.finish, identifier, owner, result)
    except asyncio.CancelledError:
        # Leave the job leased; another worker can retry after expiration.
        raise
    except Exception as exc:
        event = {'type': 'error', 'code': 'PIPELINE_ERROR', 'message': 'Research could not complete; please retry.'}
        if isinstance(exc, LLMRateLimitError):
            event = {'type': 'error', 'code': 'RATE_LIMITED', 'message': str(exc), 'retry_after': exc.retry_after}
        try:
            await asyncio.to_thread(jobs.finish, identifier, owner, error=event)
        except Exception:
            logger.warning('Job completion deferred after storage/lease failure')
    finally:
        heartbeat.cancel()
        computation.cancel()
        await asyncio.gather(heartbeat, computation, return_exceptions=True)
    return True


async def serve():
    await asyncio.to_thread(runtime.ensure)
    while True:
        try:
            if not await run_one():
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning('Worker storage unavailable; retrying')
            await asyncio.sleep(5)


if __name__ == '__main__':
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / '.env', override=False)
    asyncio.run(serve())
