"""DUCORTINHO Cloud V1.9 - rollback experimental de punicoes."""
import os, asyncio, aiohttp
from urllib.parse import urlencode

class Roblox:
    stage='inicialização'
    def __init__(self):
        self.id=int(os.getenv('ROBLOX_SERVER_ID','5048828340'))
        self.csrf=''
    async def request(self, method, host, path, body=None):
        cookie=os.getenv('ROBLOX_SESSION','').strip()
        if not cookie: raise RuntimeError('Configure ROBLOX_SESSION no ambiente privado.')
        if host not in ('games.roblox.com','accountsettings.roblox.com','users.roblox.com'): raise RuntimeError('Host não autorizado.')
        headers={'Cookie':'.ROBLOSECURITY='+cookie,'Accept':'application/json'}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as sess:
            for attempt in range(2):
                if self.csrf: headers['X-CSRF-TOKEN']=self.csrf
                async with sess.request(method,'https://'+host+path,json=body,headers=headers,allow_redirects=False) as r:
                    if r.status==403 and r.headers.get('x-csrf-token') and attempt==0:
                        self.csrf=r.headers['x-csrf-token']; continue
                    if not 200<=r.status<300:
                        self.stage=f'{self.stage} (HTTP {r.status})'
                        raise RuntimeError(f'Roblox HTTP {r.status}')
                    if r.status==204: return {}
                    return await r.json()
        raise RuntimeError('Autorização Roblox não confirmada.')
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
