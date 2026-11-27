
"""DUCORTINHO Cloud V2.1"""
import os
import asyncio
import aiohttp
from urllib.parse import urlencode


class Roblox:
    stage = 'inicialização'

    def __init__(self):
        self.id = int(
            os.getenv('ROBLOX_SERVER_ID', '5048828340')
        )

        self.csrf = ''
        self.sessions = {}
        self.tokens = {}

    async def get_session(self, host):
        cookie = os.getenv('ROBLOX_SESSION', '').strip()

        if not cookie:
            raise RuntimeError(
                'ROBLOX_SESSION não configurado.'
            )

        session = self.sessions.get(host)

        if session is None or session.closed:
            session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20),
                headers={
                    'Accept': 'application/json'
                }
            )

            session.cookie_jar.update_cookies({
                '.ROBLOSECURITY': cookie
            })

            self.sessions[host] = session

        return session

    async def request(self, method, host, path, body=None):

        allowed_hosts = (
            'games.roblox.com',
            'accountsettings.roblox.com',
            'users.roblox.com',
            'apis.roblox.com'
        )

        if host not in allowed_hosts:
            raise RuntimeError('Host não autorizado.')

        session = await self.get_session(host)

        headers = {}

        for attempt in range(2):

            token = self.tokens.get(host)

            if token:
                headers['X-CSRF-TOKEN'] = token

            async with session.request(
                method,
                'https://' + host + path,
                json=body,
                headers=headers,
                allow_redirects=False
            ) as response:

                status = response.status

                if status == 403:
                    csrf = response.headers.get(
                        'x-csrf-token'
                    )

                    if csrf and attempt == 0:
                        self.tokens[host] = csrf
                        continue

                if not 200 <= status < 300:

                    print(
                        f'[ROBLOX] Etapa: {self.stage}',
                        flush=True
                    )

                    print(