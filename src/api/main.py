#!/usr/bin/env python3

"""
HTTP API for Recoll reads

DB being queried can be configured with RECOLL_CONFDIR.
Host and port can be configured with FLASK_RUN_HOST and FLASK_RUN_PORT.
"""

from typing import Any
from base64 import urlsafe_b64decode, urlsafe_b64encode
from werkzeug.http import parse_accept_header
from contextlib import closing, contextmanager
from recoll import recoll, rclextract
from flask import Flask, request, jsonify, abort, Response, stream_with_context
from dataclasses import dataclass
from itertools import islice


@dataclass(frozen=True)
class Params:
    query: str
    skip: int = 0
    limit: int = -1


def get_readonly_db():
    maxchars = 120
    contextwords = 4
    db = recoll.connect(writable=False)  # type: ignore
    db.setAbstractParams(maxchars=maxchars, contextwords=contextwords)
    return closing(db)


@contextmanager
def get_query():
    with get_readonly_db() as db, closing(db.query()) as query:
        yield query


def get_param(params: dict[str, Any], key: str, dflt: Any = None):
    try:
        return params[key]
    except KeyError:
        if dflt is None:
            return abort(400, "Missing {} parameter".format(key))
        else:
            return dflt


def is_param(kind: Any, key: str, value: Any):
    if not isinstance(value, kind):
        abort(400, "{} has incorrect type".format(key))


def get_params(params: dict[str, Any]):
    """
    >>> get_params({'query': 'x', 'skip': 10, 'limit': 10})
    Params(query='x', skip=10, limit=10)
    """
    query = get_param(params, "query")
    is_param(str, "query", query)

    skip = get_param(params, "skip", dflt=0)
    is_param(int, "skip", skip)

    limit = get_param(params, "limit", dflt=-1)
    is_param(int, "limit", limit)

    return Params(query, skip, limit)


class Highlighter:
    def startMatch(self, _):
        return "<m>"

    def endMatch(self):
        return "</m>"


highlighter = Highlighter()


def format_results(q: Any):
    def f(doc: Any):
        return {
            **doc.items(),
            "id": urlsafe_b64encode(doc.getbinurl()).decode(),
            "part": urlsafe_b64encode(doc.ipath.encode()).decode() if doc.ipath else "",
            "url": doc.url,
            "binurl": urlsafe_b64encode(doc.getbinurl()).decode(),
            "filename": doc.filename,
            "abstract": q.makedocabstract(doc, methods=highlighter),
            "snippets": q.getsnippets(doc, sortbypage=True, methods=highlighter),
        }

    return f


def search(input_params: dict[str, Any]):
    params = get_params(input_params)

    print("Query string: {}".format(params.query))
    with get_query() as q:
        count = q.execute(params.query)
        print("Number of results: {}".format(count))

        q.scroll(params.skip, mode="absolute")

        documents = list(map(format_results(q), q if params.limit < 0 else islice(q, params.limit)))

        realskip = min(params.skip, count)
        reallimit = min(params.limit, count - realskip)
        groups = q.getgroups()

        return {
            "groups": groups,
            "count": count,
            "skip": realskip,
            "limit": reallimit,
            "documents": documents,
        }


api = Flask(__name__)


@api.route("/search", methods=["POST"])
def search_route():
    if request.json is None:
        abort(400, "request JSON payload is empty")
    results = search(request.json)
    return jsonify(results)


def chunked_path(path: bytes, chunk_size: int = 64 * 1024):
    with open(path, "rb") as fd:
        while True:
            chunk = fd.read(chunk_size)

            if not chunk:
                break

            yield chunk


def chunked_str(string: str, chunk_size: int = 64 * 1024):
    i = 0
    n = len(string)
    while i < n:
        j = i + chunk_size
        chunk = string[i:j]
        yield chunk
        i = j


def serve_text(text: str, mime_type: str):
    chunks = chunked_str(text)
    return Response(
        stream_with_context(chunks),
        content_type=f"{mime_type}; charset=utf-8",
    )


def serve_file(path: bytes, mime_type: str):
    chunks = chunked_path(path)
    return Response(
        stream_with_context(chunks),
        mimetype=mime_type,
    )


def get_doc(db: Any, binurl: bytes, ipath: str, mime_type: str):
    doc = db.doc()
    doc.setbinurl(binurl)
    doc.ipath = ipath
    doc.mimetype = mime_type
    return doc


def get_path(binurl: bytes, ipath: str, mime_type: str):
    if binurl.startswith(b"file://") and not ipath:
        # TODO Also check (not "rclbes" in doc.keys() or doc["rclbes"] == # "FS").
        return binurl[7:]
    else:
        with get_readonly_db() as db:
            doc = get_doc(db, binurl, ipath, mime_type)

            extractor = rclextract.Extractor(doc)
            return extractor.idoctofile(doc.ipath, mime_type)


def get_text(binurl: bytes, ipath: str):
    with get_readonly_db() as db:
        doc = get_doc(db, binurl, ipath, "")

        extractor = rclextract.Extractor(doc)
        return extractor.textextract(ipath)


@api.route("/contents/<id>", methods=["GET"])
def id_contents_route(id: str):
    from flask import request

    binurl = urlsafe_b64decode(id)
    accept_header = request.headers.get("accept")
    accept = parse_accept_header(accept_header)
    mime_type = accept.best
    path = get_path(binurl, "", mime_type)
    return serve_file(path, mime_type)


@api.route("/contents/<id>/<part>", methods=["GET"])
def id_part_contents_route(id: str, part: str):
    from flask import request

    binurl = urlsafe_b64decode(id)
    ipath = urlsafe_b64decode(part).decode()
    accept_header = request.headers.get("accept")
    accept = parse_accept_header(accept_header)
    mime_type = accept.best
    path = get_path(binurl, ipath, mime_type)
    return serve_file(path, mime_type)


@api.route("/text/<id>", methods=["GET"])
def id_text_route(id: str):
    binurl = urlsafe_b64decode(id)
    doc = get_text(binurl, "")
    return serve_text(doc.text, doc.mimetype)


@api.route("/text/<id>/<part>", methods=["GET"])
def id_part_text_route(id: str, part: str):
    binurl = urlsafe_b64decode(id)
    ipath = urlsafe_b64decode(part).decode()
    doc = get_text(binurl, ipath)
    return serve_text(doc.text, doc.mimetype)


if __name__ == "__main__":
    from os import environ

    host = environ.get("FLASK_RUN_HOST", "127.0.0.1")
    port = int(environ.get("FLASK_RUN_PORT", "5000"))
    api.run(host=host, port=port)
