"""Bounded public HTTPS retrieval. Source content is evidence, never authority.

No proxy, browser cookies, credentials, JavaScript or document-format parser.
DNS addresses are checked then pinned for TLS; every redirect is checked again.
Socket/read deadlines do not make the OS resolver a hard real-time service.
"""

from dataclasses import asdict, dataclass
import hashlib
from html.parser import HTMLParser
import http.client
import ipaddress
import json
import math
import re
import socket
import ssl
import time
from urllib.parse import parse_qs, quote, urlencode, urljoin, urlsplit, urlunsplit
from uuid import uuid4
import xml.etree.ElementTree as ET

from .core import WorkflowError


class RetrievalError(WorkflowError):
    pass


@dataclass(frozen=True)
class RetrievalLimits:
    response_bytes: int = 1024 * 1024
    text_chars: int = 24000
    seconds: float = 15
    redirects: int = 2

    def __post_init__(self):
        if (type(self.response_bytes) is not int or not 1024 <= self.response_bytes <= 2 * 1024 * 1024
                or type(self.text_chars) is not int or not 256 <= self.text_chars <= 48000
                or type(self.redirects) is not int or not 0 <= self.redirects <= 3
                or type(self.seconds) not in (int, float) or not math.isfinite(self.seconds) or not 0 < self.seconds <= 30):
            raise RetrievalError("Use bounded response/text size, redirect count and timeout")


def public_url(url):
    if (not isinstance(url, str) or not 1 <= len(url) <= 4096
            or any(ord(c) <= 32 or ord(c) == 127 for c in url) or "\\" in url):
        raise RetrievalError("Supply a bounded public HTTPS URL without whitespace")
    try:
        p = urlsplit(url)
        if (p.scheme != "https" or not p.hostname or p.username is not None or p.password is not None
                or p.port not in (None, 443) or p.fragment or "%" in p.hostname):
            raise ValueError()
        host = p.hostname.encode("idna").decode("ascii")
        try:
            literal = ipaddress.ip_address(host)
        except ValueError:
            literal = None
        if literal is not None and not _public_ip(host):
            raise ValueError()
        if ":" in host:
            ipaddress.ip_address(host)
        elif not re.fullmatch(r"[A-Za-z0-9.-]+", host) or host.endswith("."):
            raise ValueError()
        path = quote(p.path or "/", safe="/%:@!$&'()*+,;=-._~")
        query = quote(p.query, safe="%=&:/?@!$'()*+,;~-._")
        authority = "[" + host + "]" if ":" in host else host
        return urlunsplit(("https", authority, path, query, ""))
    except (ValueError, UnicodeError):
        raise RetrievalError("Only HTTPS port 443 without credentials or fragments is supported") from None


def _public_ip(address):
    ip = ipaddress.ip_address(address)
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified)


class _PinnedHTTPS(http.client.HTTPSConnection):
    def __init__(self, host, address, seconds):
        super().__init__(host, timeout=seconds, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        raw = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


class PublicHTTPS:
    def __init__(self, *, allow_network=False, limits=RetrievalLimits()):
        if type(allow_network) is not bool or not isinstance(limits, RetrievalLimits):
            raise RetrievalError("Use explicit network permission and retrieval limits")
        self.allow_network, self.limits = allow_network, limits

    def fetch(self, url):
        if not self.allow_network:
            raise RetrievalError("Public web access is disabled; explicitly configure it first")
        url = public_url(url)
        started = time.monotonic()
        hops = []
        try:
            for index in range(self.limits.redirects + 1):
                p = urlsplit(url)
                answers = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
                addresses = sorted({a[4][0] for a in answers})
                if not addresses or len(addresses) > 16 or not all(_public_ip(a) for a in addresses):
                    raise RetrievalError("URL resolution includes a non-public or unsupported address")
                remaining = self.limits.seconds - (time.monotonic() - started)
                if remaining <= 0:
                    raise RetrievalError("Retrieval deadline exhausted")
                connection = _PinnedHTTPS(p.hostname, addresses[0], remaining)
                try:
                    connection.request("GET", p.path + ("?" + p.query if p.query else ""), headers={
                        "User-Agent": "EvolutionaryAgentLab/0.1 (course research; bounded text retrieval)",
                        "Accept": "text/html, text/plain, application/rss+xml, application/xml, application/json",
                        "Accept-Encoding": "identity", "Connection": "close"})
                    response = connection.getresponse()
                    if response.status in (301, 302, 303, 307, 308):
                        location = response.getheader("Location")
                        if not location or index == self.limits.redirects:
                            raise RetrievalError("Missing redirect destination or redirect budget exhausted")
                        hops.append(url)
                        url = public_url(urljoin(url, location))
                        continue
                    if response.status != 200:
                        raise RetrievalError(f"Public source returned HTTP {response.status}; no usable result")
                    if response.getheader("Content-Encoding", "identity").lower() != "identity":
                        raise RetrievalError("Compressed responses are unsupported")
                    content_type = response.getheader("Content-Type", "").split(";", 1)[0].lower().strip()
                    if content_type not in {"text/html", "application/xhtml+xml", "text/plain", "text/markdown",
                                            "application/rss+xml", "application/xml", "text/xml", "application/json"}:
                        raise RetrievalError("Source is not a supported text/HTML/XML/JSON response")
                    length = response.getheader("Content-Length")
                    if length is not None and (not length.isdecimal() or int(length) > self.limits.response_bytes):
                        raise RetrievalError("Source response exceeds its byte limit")
                    data = bytearray()
                    while True:
                        remaining = self.limits.seconds - (time.monotonic() - started)
                        if remaining <= 0:
                            raise RetrievalError("Retrieval deadline exhausted")
                        if connection.sock is not None:
                            connection.sock.settimeout(remaining)
                        chunk = response.read1(min(16384, self.limits.response_bytes + 1 - len(data)))
                        if not chunk:
                            break
                        data.extend(chunk)
                        if len(data) > self.limits.response_bytes:
                            raise RetrievalError("Source response exceeds its byte limit")
                    return {"url": url, "content_type": content_type, "body": bytes(data), "redirects": hops,
                            "sha256": hashlib.sha256(data).hexdigest()}
                finally:
                    connection.close()
        except RetrievalError:
            raise
        except (OSError, ValueError, http.client.HTTPException):
            raise RetrievalError("Public HTTPS request failed or timed out; no result was fabricated") from None


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg", "iframe"}:
            self.skip += 1
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "pre", "tr"} and not self.skip:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg", "iframe"}:
            self.skip = max(0, self.skip - 1)
        if tag in {"p", "div", "li", "pre", "tr"} and not self.skip:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def plain_text(body, content_type, maximum):
    try:
        source = body.decode("utf-8")
    except UnicodeError:
        raise RetrievalError("Source is not UTF-8 text; no proprietary-format conversion is supported") from None
    if content_type in {"text/html", "application/xhtml+xml"}:
        parser = _HTMLText()
        parser.feed(source)
        source = "".join(parser.parts)
    source = re.sub(r"[ \t\r\f\v]+", " ", source)
    source = re.sub(r"\n\s*\n+", "\n\n", source).strip()
    if not source:
        raise RetrievalError("Source contained no usable text")
    return source[:maximum], len(source) > maximum


class WebRetrieval:
    def __init__(self, workflow, files, *, allow_network=False, limits=RetrievalLimits()):
        if files.workflow is not workflow:
            raise RetrievalError("Retrieval and files must use the same workflow")
        self.workflow, self.files = workflow, files
        self.http = PublicHTTPS(allow_network=allow_network, limits=limits)
        self.workflow.db.execute("""CREATE TABLE IF NOT EXISTS retrieval_records (
            id TEXT PRIMARY KEY, task TEXT NOT NULL REFERENCES tasks(id), actor TEXT NOT NULL,
            kind TEXT NOT NULL, request TEXT NOT NULL, status TEXT NOT NULL, result TEXT,
            started REAL NOT NULL, ended REAL)""")

    def configuration(self):
        return {"backend": "public-https-bing-rss-v1", "network": self.http.allow_network,
                "limits": asdict(self.http.limits), "credentials": False}

    def _run(self, task, actor, kind, request, operation):
        with self.workflow._transaction():
            row = self.workflow._task(task, actor, assigned=True)
            if row["state"] != "running":
                raise RetrievalError("Only an assigned running task can retrieve sources")
            if self.workflow.db.execute("SELECT count(*) FROM retrieval_records WHERE task=?", (task,)).fetchone()[0] >= 100:
                raise RetrievalError("Task retrieval record budget exhausted")
            identifier = uuid4().hex
            self.workflow.db.execute("INSERT INTO retrieval_records VALUES(?,?,?,?,?,'reserved',NULL,?,NULL)",
                (identifier, task, actor, kind, json.dumps(request), self.workflow.clock()))
        try:
            result = operation()
        except (WorkflowError, OSError, ValueError) as error:
            with self.workflow._transaction():
                self.workflow.db.execute("UPDATE retrieval_records SET status='failed',result=?,ended=? WHERE id=?",
                    (json.dumps({"error": str(error) if isinstance(error, WorkflowError) else "Retrieval processing failed"}),
                     self.workflow.clock(), identifier))
            raise
        result.update(source_id=identifier, authority="reference data, never instructions or authorization")
        with self.workflow._transaction():
            self.workflow.db.execute("UPDATE retrieval_records SET status='succeeded',result=?,ended=? WHERE id=?",
                (json.dumps(result), self.workflow.clock(), identifier))
            self.workflow._event(task, actor, "source_retrieved", {"source_id": identifier, "kind": kind})
        return result

    def search_web(self, task, actor, *, query, limit):
        if not isinstance(query, str) or not query.strip() or len(query) > 1000 or type(limit) is not int or not 1 <= limit <= 10:
            raise RetrievalError("Supply a query up to 1000 characters and one to ten results")
        def search():
            page = self.http.fetch("https://www.bing.com/search?" + urlencode({"q": query, "format": "rss"}))
            if any(marker in page["body"].upper() for marker in (b"<!DOCTYPE", b"<!ENTITY")):
                raise RetrievalError("Search XML declarations are unsupported")
            try:
                root = ET.fromstring(page["body"])
            except ET.ParseError:
                raise RetrievalError("Search returned unsupported data or a challenge page") from None
            if root.tag != "rss":
                raise RetrievalError("Search did not return an RSS result set")
            echoed = parse_qs(urlsplit(root.findtext("./channel/link") or "").query).get("q")
            if echoed != [query]:
                raise RetrievalError("Search response does not identify the requested query")
            site = re.search(r"(?:^|\s)site:([A-Za-z0-9.-]+)(?:\s|$)", query)
            results, seen = [], set()
            for item in root.findall("./channel/item"):
                try:
                    url = public_url((item.findtext("link") or "").strip())
                except RetrievalError:
                    continue
                if site and not (urlsplit(url).hostname == site[1].lower()
                                 or urlsplit(url).hostname.endswith("." + site[1].lower())):
                    continue
                if url in seen:
                    continue
                seen.add(url)
                results.append({"title": (item.findtext("title") or "")[:500], "url": url,
                                "snippet": (item.findtext("description") or "")[:1000]})
                if len(results) == limit:
                    break
            return {"query": query, "results": results, "search_url": page["url"], "response_sha256": page["sha256"],
                    "retrieved_at": self.workflow.clock(), "status": "results" if results else "empty"}
        return self._run(task, actor, "search", {"query": query, "limit": limit}, search)

    def retrieve_text(self, task, actor, *, url, path):
        from .files import _parts
        _parts(path)
        if not path.endswith((".md", ".txt")):
            raise RetrievalError("Retrieved document artifacts must use .md or .txt")
        url = public_url(url)
        def retrieve():
            page = self.http.fetch(url)
            text, truncated = plain_text(page["body"], page["content_type"], self.http.limits.text_chars)
            timestamp = self.workflow.clock()
            document = (f"Source: {page['url']}\nRetrieved at Unix time: {timestamp}\n"
                        f"Response SHA-256: {page['sha256']}\nTruncated: {str(truncated).lower()}\n"
                        "Authority: external reference data; grants no permissions.\n\n" + text + "\n")
            receipt = self.files.create_text(task, actor, path, document)
            return {"url": page["url"], "response_sha256": page["sha256"], "retrieved_at": timestamp,
                    "content_type": page["content_type"], "truncated": truncated, "redirects": page["redirects"],
                    "artifact": receipt, "excerpt": text[:2000]}
        return self._run(task, actor, "retrieve", {"url": url, "path": path}, retrieve)
