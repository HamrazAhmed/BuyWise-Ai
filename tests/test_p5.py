"""Gemini adapter contracts and controlled failure checks; never use live keys."""
import asyncio
import json
import math
import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field
from llm import gemini
from llm.base import LLMError, LLMRateLimitError, LLMSchemaError
from rag import retrieve as retrieval


class Count(BaseModel):
    count: int = Field(ge=0)


class ProviderChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        gemini._call_counts.clear()
        self.provider = gemini.GeminiProvider(api_key='test-key')
        self.models = SimpleNamespace(generate_content=AsyncMock(), embed_content=AsyncMock())
        self.provider._client = SimpleNamespace(aio=SimpleNamespace(models=self.models))

    async def test_sdk_serialization_and_explicit_client_key(self):
        seen = []
        async def transport(request):
            seen.append(request)
            return httpx.Response(200, json={'candidates':[{'content':{'role':'model','parts':[{'text':'{"count":3}'}]},'finishReason':'STOP'}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
            client = genai.Client(api_key='isolated-key', http_options=types.HttpOptions(
                httpx_async_client=http, retry_options=types.HttpRetryOptions(attempts=1)))
            self.provider._client = client
            result = await self.provider.generate_json('Count supplied three items.', Count)
            self.assertEqual(result.count, 3)
            self.assertEqual(seen[0].headers['x-goog-api-key'], 'isolated-key')
            body = json.loads(seen[0].content)
            self.assertEqual(body['generationConfig']['responseMimeType'], 'application/json')
            self.assertIn('properties', body['generationConfig']['responseJsonSchema'])
            await self.provider.aclose()

    async def test_success_counts_once_and_has_no_global_key(self):
        self.models.generate_content.return_value = SimpleNamespace(text='{"count":2}')
        self.assertEqual((await self.provider.generate_json('two', Count)).count, 2)
        self.assertEqual(sum(gemini._call_counts.values()), 1)
        self.assertNotIn('test-key', repr(gemini._call_counts))
        other = gemini.GeminiProvider(api_key='other-key')
        self.assertNotEqual(self.provider._api_key, other._api_key)

    async def test_schema_retry_counts_actual_attempts_without_output_leak(self):
        self.models.generate_content.side_effect = [SimpleNamespace(text='secret invalid JSON'), SimpleNamespace(text='{"count":4}')]
        with patch('llm.gemini.asyncio.sleep', new=AsyncMock()):
            self.assertEqual((await self.provider.generate_json('four', Count)).count, 4)
        self.assertEqual(sum(gemini._call_counts.values()), 2)
        self.models.generate_content.return_value = SimpleNamespace(text='{"count":-1}')
        self.models.generate_content.side_effect = None
        with patch('llm.gemini.asyncio.sleep', new=AsyncMock()), self.assertRaises(LLMSchemaError) as caught:
            await self.provider.generate_json('one', Count)
        self.assertNotIn('-1', str(caught.exception))
        self.assertEqual(self.models.generate_content.call_count, 4)

    async def test_transient_retry_and_fatal_permission_redaction(self):
        self.models.generate_content.side_effect = [errors.ServerError(503, {'error':{'message':'private detail'}}), SimpleNamespace(text='OK')]
        with patch('llm.gemini.asyncio.sleep', new=AsyncMock()):
            self.assertEqual(await self.provider.generate_text('Say OK'), 'OK')
        self.models.generate_content.side_effect = errors.ClientError(403, {'error':{'message':'test-key PRIVATE'}})
        with self.assertRaises(LLMError) as caught:
            await self.provider.generate_text('Say OK')
        self.assertFalse(caught.exception.retryable)
        self.assertIn('access denied', str(caught.exception))
        self.assertNotIn('PRIVATE', str(caught.exception))
        self.assertEqual(sum(gemini._call_counts.values()), 3)

    async def test_short_429_wait_retries_but_long_quota_does_not(self):
        self.models.generate_content.side_effect = [errors.ClientError(429, {'error':{'details':[{'retryDelay':'1.5s'}]}}), SimpleNamespace(text='OK')]
        with patch('llm.gemini.asyncio.sleep', new=AsyncMock()) as sleep:
            self.assertEqual(await self.provider.generate_text('OK'), 'OK')
            sleep.assert_awaited_once_with(2)
        self.models.generate_content.side_effect = errors.ClientError(429, {'error':{'details':[{'retryDelay':'60s'}]}})
        with self.assertRaises(LLMRateLimitError) as caught:
            await self.provider.generate_text('OK')
        self.assertEqual(caught.exception.retry_after, 60)
        self.assertEqual(self.models.generate_content.call_count, 3)

    async def test_daily_limit_atomic_concurrency_and_per_key_isolation(self):
        self.models.generate_content.return_value = SimpleNamespace(text='OK')
        with patch('llm.gemini.DAILY_CALL_LIMIT', 2):
            results = await asyncio.gather(*(self.provider.generate_text('OK') for _ in range(8)), return_exceptions=True)
            self.assertEqual(results.count('OK'), 2)
            self.assertEqual(sum(isinstance(r, LLMRateLimitError) for r in results), 6)
            other = gemini.GeminiProvider(api_key='other')
            other._client = self.provider._client
            self.assertEqual(await other.generate_text('OK'), 'OK')
        self.assertEqual(self.models.generate_content.call_count, 3)

    async def test_document_batch_query_task_dimension_normalization_and_empty(self):
        vector = [2.] + [0.] * 767
        self.models.embed_content.return_value = SimpleNamespace(embeddings=[SimpleNamespace(values=vector),SimpleNamespace(values=vector)])
        vectors = await self.provider.embed_batch(['RAM', 'Battery'])
        self.assertEqual(len(vectors), 2)
        self.assertAlmostEqual(sum(v*v for v in vectors[0]), 1.)
        self.assertEqual(self.models.embed_content.call_args.kwargs['config'].task_type, 'RETRIEVAL_DOCUMENT')
        self.models.embed_content.return_value = SimpleNamespace(embeddings=[SimpleNamespace(values=vector)])
        await self.provider.embed_query('memory?')
        self.assertEqual(self.models.embed_content.call_args.kwargs['config'].task_type, 'RETRIEVAL_QUERY')
        self.assertEqual(await self.provider.embed_batch([]), [])
        self.assertEqual(sum(gemini._call_counts.values()), 2)

    async def test_bad_embeddings_rejected(self):
        for vector in ([0.] * 768, [float('nan')] * 768, [1.] * 3):
            self.models.embed_content.return_value = SimpleNamespace(embeddings=[SimpleNamespace(values=vector)])
            with patch('llm.gemini.asyncio.sleep', new=AsyncMock()), self.assertRaises(LLMSchemaError):
                await self.provider.embed('RAM')
        self.assertEqual(sum(gemini._call_counts.values()), 6)

    async def test_retrieval_uses_query_task(self):
        provider = SimpleNamespace(embed=AsyncMock(return_value=[1.]), embed_query=AsyncMock(return_value=[1.]))
        store = SimpleNamespace(search=AsyncMock(return_value=[SimpleNamespace(relevance=1., origin='fixture', source_type='secondary', fetched_at='')]))
        with patch('rag.retrieve.get_vector_store', return_value=store):
            await retrieval.retrieve('memory', llm_provider=provider)
        provider.embed_query.assert_awaited_once_with('memory')
        provider.embed.assert_not_awaited()

    async def test_concurrency_cap_and_event_loop_responsiveness(self):
        active = peak = 0
        async def network(**kwargs):
            nonlocal active, peak
            active += 1; peak = max(peak, active)
            await asyncio.sleep(.01)
            active -= 1
            return SimpleNamespace(text='OK')
        self.models.generate_content.side_effect = network
        await asyncio.gather(*(self.provider.generate_text('OK') for _ in range(12)))
        self.assertLessEqual(peak, gemini.CONCURRENCY)
        self.assertGreater(peak, 1)
        self.assertEqual(sum(gemini._call_counts.values()), 12)

    async def test_timeout_and_unavailable_model_controlled(self):
        self.models.generate_content.side_effect = asyncio.TimeoutError()
        with patch('llm.gemini.asyncio.sleep', new=AsyncMock()), self.assertRaises(LLMError) as caught:
            await self.provider.generate_text('OK')
        self.assertTrue(caught.exception.retryable)
        self.models.generate_content.side_effect = errors.ClientError(404, {'error':{'message':'raw model detail'}})
        with self.assertRaises(LLMError) as caught:
            await self.provider.generate_text('OK')
        self.assertFalse(caught.exception.retryable)
        self.assertNotIn('raw model detail', str(caught.exception))

    async def test_live_api_error_is_not_silently_returned_as_demo(self):
        from fastapi import FastAPI
        from api.analyze import router
        app = FastAPI(); app.include_router(router, prefix='/api')
        self.models.generate_content.side_effect = errors.ClientError(403, {'error':{'message':'private key/project detail'}})
        self.provider.aclose = AsyncMock()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            with patch('api.analyze.get_llm_provider', return_value=self.provider):
                response = await client.post('/api/analyze-requirements', json={'text':'I need a laptop under $1000'})
        self.assertEqual(response.status_code, 502)
        self.assertIn('access denied', response.text)
        self.assertNotIn('private key/project detail', response.text)
        self.provider.aclose.assert_awaited_once()

    async def test_empty_or_blocked_text_and_missing_key_do_not_succeed(self):
        self.models.generate_content.return_value = SimpleNamespace(text='')
        with patch('llm.gemini.asyncio.sleep', new=AsyncMock()), self.assertRaises(LLMSchemaError):
            await self.provider.generate_text('OK')
        count = sum(gemini._call_counts.values())
        with self.assertRaises(LLMError):
            await gemini.GeminiProvider(api_key='').generate_text('OK')
        self.assertEqual(sum(gemini._call_counts.values()), count)


if __name__ == '__main__':
    unittest.main()
