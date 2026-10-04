"""Bounded HTTPS fetching with allowlisted hosts and public-IP pinning."""
import asyncio
import http.client
import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urljoin

MAX_BYTES = 1_000_000
MAX_REDIRECTS = 3


@dataclass
class FetchedDocument:
    text: str
    url: str
    fetched_at: str


def allowed_url(url, domains):
    try:
        parsed = urlsplit(url)
        host = parsed.hostname or ''
        return (parsed.scheme == 'https' and not parsed.username and not parsed.password
                and parsed.port in (None,443) and not parsed.fragment
                and not any(c in url for c in ('\\', '\r', '\n', '\t'))
                and bool(host) and any(host == d or host.endswith('.'+d) for d in domains))
    except ValueError:
        return False


def public_addresses(host):
    answers = socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(item[4][0] for item in answers))
    if not addresses:
        raise ValueError('Host has no addresses')
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            raise ValueError('Private/local/nonpublic address blocked')
    return addresses


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, address, timeout):
        super().__init__(host,443,timeout=timeout,context=ssl.create_default_context())
        self.address=address

    def connect(self):
        # Connect to the validated numeric address: no second hostname resolution.
        sock = socket.create_connection((self.address,443),self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock,server_hostname=self.host)
        except BaseException:
            sock.close()
            raise


def fetch_sync(url, domains, timeout_s):
    deadline=time.monotonic()+timeout_s
    for _ in range(MAX_REDIRECTS+1):
        if not allowed_url(url,domains):
            return None
        parsed=urlsplit(url)
        addresses=public_addresses(parsed.hostname)
        remaining=deadline-time.monotonic()
        if remaining <= 0:
            return None
        connection=PinnedHTTPSConnection(parsed.hostname,addresses[0],remaining)
        try:
            target=parsed.path or '/'
            if parsed.query: target+='?'+parsed.query
            connection.request('GET',target,headers={'User-Agent':'BuyWiseAI/0.1','Accept-Encoding':'identity'})
            response=connection.getresponse()
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location: return None
                url=urljoin(url,location)
                continue
            if response.status != 200:
                return None
            if response.getheader('Content-Type','').split(';')[0].strip().lower() not in ('text/html','text/plain'):
                return None
            if response.getheader('Content-Encoding','identity').lower() != 'identity':
                return None
            if int(response.getheader('Content-Length','0')) > MAX_BYTES:
                return None
            data=bytearray()
            while time.monotonic() < deadline:
                block=response.read(min(16384,MAX_BYTES+1-len(data)))
                if not block:
                    return FetchedDocument(data.decode('utf-8',errors='replace'),url,time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()))
                data.extend(block)
                if len(data)>MAX_BYTES: return None
            return None
        finally:
            connection.close()
    return None


async def fetch_document(url,domains,timeout_s=15):
    if not allowed_url(url,domains):
        return None
    try:
        return await asyncio.wait_for(asyncio.to_thread(fetch_sync,url,domains,timeout_s),timeout=timeout_s)
    except (OSError,ValueError,http.client.HTTPException,asyncio.TimeoutError):
        return None
