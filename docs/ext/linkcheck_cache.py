"""
Sphinx extension to cache linkcheck results
"""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from queue import Queue
from threading import Lock
from typing import TYPE_CHECKING

from sphinx._cli.util.colour import darkgreen
from sphinx.builders.linkcheck import (
    CHECK_IMMEDIATELY,
    CheckRequest,
    CheckResult,
    Hyperlink,
    RateLimit,
    _Status,
    logger,
)
from sphinx.builders.linkcheck import (
    CheckExternalLinksBuilder as _CheckExternalLinksBuilder,
)
from sphinx.builders.linkcheck import HyperlinkAvailabilityChecker as _HyperlinkAvailabilityChecker
from sphinx.builders.linkcheck import (
    HyperlinkAvailabilityCheckWorker as _HyperlinkAvailabilityCheckWorker,
)
from sphinx.locale import __

if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.builders.linkcheck import _URIProperties
    from sphinx.config import Config
    from sphinx.util._pathlib import _StrPath

cache_file_lock = Lock()


class CheckExternalLinksBuilder(_CheckExternalLinksBuilder):
    def process_result(self, result: CheckResult) -> None:
        if result.status == "cached":
            filename = self.env.doc2path(result.docname, False)
            res_uri = result.uri

            linkstat: dict[str, str | int] = {
                'filename': str(filename),
                'lineno': result.lineno,
                'status': "cached",
                'code': result.code,
                'uri': res_uri,
                'info': result.message,
            }
            self.write_linkstat(linkstat)
            if result.lineno:
                # unchecked links are not logged
                logger.info('(%16s: line %4d) ', result.docname, result.lineno, nonl=True)
            logger.info(darkgreen('cached    ') + f'{res_uri} - {result.message}')
        else:
            super().process_result(result)

    def finish(self) -> None:
        cache_file = (
            self.outdir / self.config.linkcheck_cache_file if self.config.linkcheck_cache else None
        )
        checker = HyperlinkAvailabilityChecker(self.config, cache_file)
        logger.info('')

        output_text = self.outdir / 'output.txt'
        output_json = self.outdir / 'output.json'
        with (
            open(output_text, 'w', encoding='utf-8') as self.txt_outfile,
            open(output_json, 'w', encoding='utf-8') as self.json_outfile,
        ):
            for result in checker.check(self.hyperlinks):
                self.process_result(result)

        if self.broken_hyperlinks or self.timed_out_hyperlinks:
            self._app.statuscode = 1


class HyperlinkAvailabilityChecker(_HyperlinkAvailabilityChecker):
    def __init__(self, config: Config, cache_file: _StrPath | None) -> None:
        super().__init__(config)
        self.last_cache_result = {}
        self.cache_file = cache_file
        if self.cache_file and self.cache_file.exists():
            with self.cache_file.open('r') as f:
                self.last_cache_result = json.load(f)
        self.now = datetime.now(UTC)
        self.cache_duration = timedelta(days=self.config.linkcheck_cache_duration)

    def check(self, hyperlinks: dict[str, Hyperlink]) -> Iterator[CheckResult]:
        self.invoke_threads()

        total_links = 0
        for hyperlink in hyperlinks.values():
            if self.is_ignored_uri(hyperlink.uri):
                yield CheckResult(
                    uri=hyperlink.uri,
                    docname=hyperlink.docname,
                    lineno=hyperlink.lineno,
                    status=_Status.IGNORED,
                    message='',
                    code=0,
                )
            else:
                if self.config.linkcheck_cache and hyperlink.uri in self.last_cache_result:
                    last_succesfful_time = datetime.fromtimestamp(
                        self.last_cache_result[hyperlink.uri], UTC
                    )
                    age = self.now - last_succesfful_time
                    if age < self.cache_duration:
                        # Cache is still valid
                        yield CheckResult(
                            uri=hyperlink.uri,
                            docname=hyperlink.docname,
                            lineno=hyperlink.lineno,
                            status="cached",
                            message=last_succesfful_time.strftime('%Y-%m-%d %H:%M'),
                            code=0,
                        )
                        continue
                self.wqueue.put(CheckRequest(CHECK_IMMEDIATELY, hyperlink), False)
                total_links += 1

        done = 0
        while done < total_links:
            yield self.rqueue.get()
            done += 1

        self.shutdown_threads()

    def invoke_threads(self) -> None:
        for _i in range(self.num_workers):
            thread = HyperlinkAvailabilityCheckWorker(
                self.config, self.rqueue, self.wqueue, self.rate_limits, self.cache_file
            )
            thread.start()
            self.workers.append(thread)


class HyperlinkAvailabilityCheckWorker(_HyperlinkAvailabilityCheckWorker):
    def __init__(
        self,
        config: Config,
        rqueue: Queue[CheckResult],
        wqueue: Queue[CheckRequest],
        rate_limits: dict[str, RateLimit],
        cache_file: _StrPath | None = None,
    ) -> None:
        self.cache_file = cache_file
        super().__init__(config, rqueue, wqueue, rate_limits)

    def _check(self, docname: str, uri: str, hyperlink: Hyperlink) -> _URIProperties:
        status, info, code = super()._check(docname, uri, hyperlink)
        # Only cache successful results which actually ran the _check_uri
        if self.cache_file and status == _Status.WORKING:
            with cache_file_lock:
                if self.cache_file.exists():
                    with self.cache_file.open('r') as f:
                        cache_state = json.load(f)
                    if not isinstance(cache_state, dict):
                        logger.warning(__('Previous linkcheck cache is malformed. Recreating it.'))
                        cache_state = {}
                else:
                    cache_state = {}
                cache_state[uri] = datetime.now(UTC).timestamp()
                with self.cache_file.open('w') as f:
                    json.dump(cache_state, f)
        return status, info, code


def setup(app: "Sphinx"):
    app.add_builder(CheckExternalLinksBuilder, override=True)
    app.add_config_value('linkcheck_cache', False, '', types=frozenset({bool}))
    app.add_config_value(
        'linkcheck_cache_file', 'linkcheck_cache.json', '', types=frozenset({str})
    )
    app.add_config_value('linkcheck_cache_duration', 7.0, '', types=frozenset({float}))
