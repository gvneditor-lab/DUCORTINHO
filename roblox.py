
"""DUCORTINHO Cloud V1.7"""
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
                        f'[ROBLOX] Metodo: {method}',
                        flush=True
                    )

                    print(
                        f'[ROBLOX] Rota: {host}{path}',
                        flush=True
                    )

                    print(
                        f'[ROBLOX] Status: {status}',
                        flush=True
                    )

                    try:
                        error = await response.json()

                        if isinstance(error, dict):
                            for item in error.get('errors', []):
                                if not isinstance(item, dict):
                                    continue

                                code = item.get('code')

                                if isinstance(code, int):
                                    print(
                                        f'[ROBLOX] Codigo: {code}',
                                        flush=True
                                    )

                            descriptions = str(error).lower()

                            if 'browsertracker' in descriptions:
                                print(
                                    '[ROBLOX] Contexto de navegador exigido.',
                                    flush=True
                                )

                            elif 'csrf' in descriptions:
                                print(
                                    '[ROBLOX] Falha de validacao CSRF.',
                                    flush=True
                                )

                            elif 'challenge' in descriptions:
                                print(
                                    '[ROBLOX] Verificacao de seguranca exigida.',
                                    flush=True
                                )

                            elif 'authorization' in descriptions:
                                print(
                                    '[ROBLOX] Autorizacao recusada.',
                                    flush=True
                                )

                            else:
                                print(
                                    '[ROBLOX] Motivo nao classificado.',
                                    flush=True
                                )

                    except Exception:
                        print(
                            '[ROBLOX] Resposta de erro sem JSON valido.',
                            flush=True
                        )

                    self.stage = (
                        f'{self.stage} (HTTP {status})'
                    )

                    raise RuntimeError(
                        f'Roblox HTTP {status}'
                    )

                if status == 204:
                    return {}

                return await response.json()

        raise RuntimeError(
            'Autorização Roblox não confirmada.'
        )

    async def shutdown(self):
        for session in self.sessions.values():
            if not session.closed:
                await session.close()

        self.sessions.clear()
        self.tokens.clear()

    # ==================================
    # GERENCIAMENTO DA CIDADE
    # ==================================

    async def info(self):
        return await self.request(
            'GET',
            'games.roblox.com',
            f'/v1/vip-servers/{self.id}'
        )

    async def set_access(self, enabled):
        self.stage = 'consultar acesso'

        info = await self.info()

        if not isinstance(info.get('active'), bool):
            raise RuntimeError(
                'Campo active não reconhecido.'
            )

        if info['active'] != enabled:
            self.stage = 'alterar acesso'

            await self.request(
                'PATCH',
                'games.roblox.com',
                f'/v1/vip-servers/{self.id}',
                {'active': enabled}
            )

        if (await self.info()).get('active') is not enabled:
            raise RuntimeError(
                'Acesso não confirmado.'
            )

    async def close(self):
        await self.set_access(False)

    async def open(self):
        await self.set_access(True)

        self.stage = 'gerar convite'
        before = await self.info()

        def code_of(data):
            for key in (
                'linkCode',
                'privateServerLinkCode',
                'joinCode'
            ):
                value = data.get(key)

                if isinstance(value, str) and value.strip():
                    return value.strip()

            return None

        old = code_of(before)

        result = await self.request(
            'PATCH',
            'games.roblox.com',
            f'/v1/vip-servers/{self.id}',
            {'newJoinCode': True}
        )

        candidate = code_of(result)

        for delay in (0, 1, 2, 3, 4):

            if delay:
                await asyncio.sleep(delay)

            info = await self.info()
            code = code_of(info)

            if info.get('active') is not True:
                continue

            if not code or code == old:
                if candidate and candidate != old:
                    code = candidate
                else:
                    continue

            place = os.getenv(
                'ROBLOX_PLACE_ID',
                '101953291486308'
            ).strip()

            if not place.isdigit() or int(place) <= 0:
                self.stage = 'identificar mapa'

                raise RuntimeError(
                    'Place ID não confirmado.'
                )

            return (
                f'https://www.roblox.com/games/{place}?'
                + urlencode({
                    'privateServerLinkCode': code
                })
            )

        self.stage = 'confirmar novo convite'

        raise RuntimeError(
            'Novo código não confirmado.'
        )

    # ==================================
    # SISTEMA DE PUNICOES
    # ==================================

    async def blocked(self, uid):
        uid = int(uid)

        self.stage = 'consultar bloqueio individual'

        data = await self.request(
            'GET',
            'apis.roblox.com',
            f'/user-blocking-api/v1/users/{uid}/is-blocked'
        )

        if isinstance(data, bool):
            return data

        if isinstance(data, dict):

            nested = data.get('data')

            for response in (data, nested):

                if isinstance(response, bool):
                    return response

                if not isinstance(response, dict):
                    continue

                for key in (
                    'isBlocked',
                    'blocked',
                    'isUserBlocked'
                ):
                    value = response.get(key)

                    if isinstance(value, bool):
                        print(
                            f'[ROBLOX] Bloqueado: {value}',
                            flush=True
                        )

                        return value

        raise RuntimeError(
            'Resposta de bloqueio não reconhecida.'
        )

    async def change_block(self, uid, block):
        uid = int(uid)

        current = await self.blocked(uid)

        if current == block:
            return False

        self.stage = 'alterar bloqueio'

        action = 'block' if block else 'unblock'

        await self.request(
            'POST',
            'apis.roblox.com',
            f'/user-blocking-api/v1/users/{uid}/{action}-user',
            {}
        )

        for delay in (1, 2, 3):

            await asyncio.sleep(delay)

            if await self.blocked(uid) == block:

                print(
                    '[ROBLOX] Punicao confirmada.'
                    if block else
                    '[ROBLOX] Desbloqueio confirmado.',
                    flush=True
                )

                return True

        raise RuntimeError(
            'Alteração de bloqueio não confirmada.'
        )
