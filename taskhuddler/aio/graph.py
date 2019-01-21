"""Helpful wrapper around release related taskcluster operations."""

import logging
import os

import aiohttp
from asyncinit import asyncinit
from taskcluster.aio import Queue

from taskhuddler.graph import TaskGraph as SyncTaskGraph
from taskhuddler.task import Task
from taskhuddler.utils import tc_options

log = logging.getLogger(__name__)


@asyncinit
class TaskGraph(SyncTaskGraph):
    """Helper class for dealing with Task Graphs, asyncio version."""

    async def __init__(self, groupid):
        """init."""
        self.groupid = groupid
        self.tasklist = None

        # if multiple caches are defined use the first as the primary
        if 'TC_CACHE_DIR' in os.environ:
            self.cache_files = [os.path.join(c, "{}.json".format(self.groupid)) for c in
                                os.environ['TC_CACHE_DIR'].split(";")]
            self.cache_file = self.cache_files[0]
        else:
            self.cache_files = []
            self.cache_file = None

        await self.fetch_tasks()

    async def fetch_tasks(self, limit=None):
        """Return tasks with the associated group ID.

        Handles continuationToken without the user being aware of it.

        Enforces the limit parameter as a limit of the total number of tasks
        to be returned.
        """
        if self.cache_file:
            if self._read_file_cache():
                return

        query = {}
        if limit:
            # Default taskcluster-client api asks for 1000 tasks.
            query['limit'] = min(limit, 1000)

        def under_limit(length):
            """Indicate if we've returned enough tasks."""
            if not limit or length < limit:
                return True
            return False

        async with aiohttp.ClientSession() as session:
            queue = Queue(options=tc_options(), session=session)
            outcome = await queue.listTaskGroup(self.groupid, query=query)
            tasks = outcome.get('tasks', [])

            while under_limit(len(tasks)) and outcome.get('continuationToken'):
                query.update({
                    'continuationToken': outcome.get('continuationToken')
                })
                outcome = await queue.listTaskGroup(self.groupid, query=query)
                tasks.extend(outcome.get('tasks', []))

            if limit:
                tasks = tasks[:limit]
            self.tasklist = [Task(json=data) for data in tasks]

            if self.cache_file:
                self._write_file_cache()
